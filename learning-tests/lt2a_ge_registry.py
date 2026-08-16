"""
LT-2a — Great Expectations 1.x: object model, expectation registry, and the
        real strength of "validate before persist" (INV-2).

WHY THIS EXISTS
    SPEC F5 says every generated rule is instantiated as a real Great
    Expectations object before it is written anywhere, and F7 says exactly one
    module in the codebase imports GE (INV-3). Both were designed against
    remembered, pre-1.0 GE — `ExpectationConfiguration` dicts, `DataContext`
    everywhere, `expectation_type` as the wire key. None of that could be
    assumed. This script pins the real object model of the installed 1.x, picks
    the O-1 catalog from the actual registry rather than from memory, and — most
    importantly — measures how much of INV-2 GE will actually enforce for us.

FINDINGS — run 2026-08-16, great-expectations 1.20.0, Python 3.12.5

    [x] Registry holds 56 expectation types. Census by base class:
            ColumnMapExpectation         25   (per-row, single column)
            ColumnAggregateExpectation   15   (whole-column statistic)
            BatchExpectation             10   (table-level)
            ColumnPairMapExpectation      3   } 6 multi-column types,
            MulticolumnMapExpectation     3   } all deliberately excluded (v2)
        `great_expectations.expectations` also exports `Expectation` (the base)
        and `UnexpectedRowsExpectation` (raw-SQL escape hatch, out of scope),
        so `dir()` shows 58 names against a registry of 56. Count from the
        registry, not from the module.

    [x] 15-type catalog selected and verified present in the live registry
        (printed in full by this script). Covers all eight families the MVP
        needs: nulls, uniqueness, value sets, ranges, regex/format, type,
        row count, column existence. Single-column and table-level only.

    [x] The object model is pydantic **v1** (`pydantic.v1.main.BaseModel`),
        vendored inside pydantic 2. Introspection is `__fields__` / `.schema()`,
        NOT `model_fields` / `model_json_schema()`. Getting this wrong is a
        silent AttributeError at the exact moment the compiler introspects.

    [x] Construction, serialisation and round-trip all work with no
        `DataContext` at all. `ExpectationSuite(name=..., expectations=[...])`
        builds context-free; only `suite.add_expectation()` demands a context
        (`DataContextRequiredError`). Build suites by constructor.

    MEASURED
        registry types         56  (25 col-map / 15 col-agg / 10 table / 6 multi)
        catalog types          15  (0 multi-column)
        invalid-rule probes    25, of which GE rejects 15 and accepts 10
        `import great_expectations`  ~3.2 s cold — import it once at process
                                     start, never per request

    UNEXPECTED — this is the important one, and it weakens INV-2 as written

        "Instantiate it against GE before persisting" is a WEAKER gate than the
        spec assumes. GE's constructor validation is real but *inconsistent
        between expectation types*, and it validates shape, never sense.

        Silently accepted (constructs fine, is a bad rule):
            values_to_be_between(min_value=100, max_value=1)   contradictory
            match_regex(regex="[unclosed")                     invalid regex
            match_regex(column="e")                            NO regex at all
            in_type_list(column="e")                           NO type_list
            table_row_count_to_be_between()                    no bounds at all
            column_mean_to_be_between(column="e")              no bounds at all
            unique_value_count_to_be_between(column="e")       no bounds at all
            values_to_be_in_set(value_set=[])                  can never pass
            values_to_be_of_type(type_="NOT_A_TYPE")           bogus SQL type

        And the asymmetries are the tell — these are not a coherent policy:
            not_match_regex WITHOUT regex           -> RAISES
            match_regex     WITHOUT regex           -> accepted
            row_count_to_be_between  min>max        -> RAISES
            values_to_be_between     min>max        -> accepted
            values_to_be_between     no bounds      -> RAISES (root validator)
            mean_to_be_between       no bounds      -> accepted

        So `.schema()["required"]` is NOT the source of truth either: it lists
        only `['column']` for values_to_be_between, yet a root validator rejects
        both-bounds-None. Required-ness lives in two places and neither is
        complete.

        Second: `ExpectationConfiguration(type="expect_column_values_to_be_vibey",
        kwargs={...})` constructs WITHOUT ERROR. A hallucinated type passes
        straight through the config object. It only raises at
        `.to_domain_obj()`. If the compiler persists ExpectationConfiguration,
        INV-2 does not hold at all.

        CONSEQUENCE FOR THE DESIGN (F5 / F7):
          1. The gate is `get_expectation_impl(type)(**kwargs)` — the concrete
             class — never `ExpectationConfiguration`.
          2. GE construction is necessary but NOT sufficient. The catalog must
             carry OUR OWN per-type required-parameter and sanity table
             (min<=max, non-empty value_set, compilable regex, known SQL type)
             and run it before handing kwargs to GE. That table is a small
             amount of code and it is the part that actually makes INV-2 true.
          3. This is the same shape as the LT-2b finding: the tool confirms the
             rule is well-formed, never that it is meaningful.

THE API CONTRACT FOR THE ONE MODULE THAT IMPORTS GE (INV-3)

    construct     from great_expectations.expectations.registry import (
                      get_expectation_impl)                  # str -> class
                  obj = get_expectation_impl(type_str)(**kwargs)
                  # equivalently, statically:
                  #   import great_expectations.expectations as gxe
                  #   gxe.ExpectColumnValuesToBeInSet(column=..., value_set=[...])
                  # unknown type -> ExpectationNotFoundError
                  # bad kwargs   -> pydantic.v1.ValidationError
                  # unknown kwarg -> ValidationError "extra fields not permitted"
                  #                  (constructor is strict; typos cannot slip)

    introspect    cls = get_expectation_impl(type_str)
                  cls.expectation_type          -> the snake_case name
                  cls.schema()["required"]      -> declared required kwargs
                  cls.__fields__                -> pydantic v1 FieldInfo map;
                                                   f.required, f.outer_type_
                  "mostly" in cls.__fields__    -> True only for map expectations
                  cls.__mro__[1].__name__       -> ColumnMapExpectation |
                                                   ColumnAggregateExpectation |
                                                   BatchExpectation | ...
                                                   (this is how we exclude
                                                   multi-column at catalog time)

    serialise     obj.configuration.to_json_dict()
                  -> {"type": str, "kwargs": {...}, "meta": {}, "severity": str}
                  NOTE the wire key is "type", not "expectation_type" (that is
                  the 1.x rename). The instance itself has NO .to_json_dict()
                  and NO .type attribute — go through .configuration.
                  obj.dict() also works but leaks defaults (result_format,
                  catch_exceptions, mostly=1). Store OUR spec, not this.

    deserialise   d = json.loads(...)
                  obj = get_expectation_impl(d["type"])(**d["kwargs"])
                  # round-trips exactly; verified in this script
                  # or: ExpectationConfiguration(**d).to_domain_obj()
                  #     — validates only at to_domain_obj(), see UNEXPECTED

    suite         import great_expectations as gx
                  gx.ExpectationSuite(name="orders", expectations=[obj, ...])
                  # context-free. suite.to_json_dict() is the executable form.
                  # suite.add_expectation(obj) REQUIRES gx.get_context() first
                  # and raises DataContextRequiredError otherwise — do not use
                  # it in the compiler.

    Everything above is import-free for the rest of the codebase: the compiler's
    public surface takes and returns our own dicts, so `great_expectations`
    appears in exactly one file.

RUN
    uv run --with great-expectations python learning-tests/lt2a_ge_registry.py
"""

import json
import time
from collections import Counter

t_import = time.perf_counter()
import great_expectations as gx
import great_expectations.expectations as gxe
from great_expectations.expectations.registry import (
    get_expectation_impl,
    list_registered_expectation_implementations,
)
from great_expectations.expectations.expectation_configuration import (
    ExpectationConfiguration,
)
from great_expectations.exceptions.exceptions import ExpectationNotFoundError

IMPORT_SECONDS = time.perf_counter() - t_import

RULE = "=" * 78


# ---------------------------------------------------------------------------
# The O-1 catalog. Chosen from the real registry, not from memory.
# Single-column and table-level only — multi-column is deferred to v2.
# Each entry: (type, family, why it earns a slot in an e-commerce MVP)
# ---------------------------------------------------------------------------

CATALOG: list[tuple[str, str, str]] = [
    # -- nulls ---------------------------------------------------------------
    ("expect_column_values_to_not_be_null", "nulls",
     "orders.customer_id is always present; with mostly= it also expresses "
     "'at most 2% of emails may be missing'"),
    ("expect_column_values_to_be_null", "nulls",
     "the negation — a deprecated/never-populated column must stay empty"),
    # -- uniqueness ----------------------------------------------------------
    ("expect_column_values_to_be_unique", "uniqueness",
     "orders.order_id, customers.email — the single most common rule"),
    ("expect_column_unique_value_count_to_be_between", "uniqueness",
     "cardinality: payments.method has between 3 and 8 distinct values"),
    # -- value sets ----------------------------------------------------------
    ("expect_column_values_to_be_in_set", "value sets",
     "orders.status is one of the known lifecycle states"),
    ("expect_column_values_to_not_be_in_set", "value sets",
     "denylist: payments.status must never be a legacy/retired code"),
    # -- ranges --------------------------------------------------------------
    ("expect_column_values_to_be_between", "ranges",
     "orders.order_total >= 0 — the business invariant LT-2b showed the model "
     "will not volunteer on its own"),
    ("expect_column_mean_to_be_between", "ranges",
     "aggregate range: average order value stays in a plausible band; catches "
     "unit/currency drift that no per-row bound catches"),
    # -- regex / format ------------------------------------------------------
    ("expect_column_values_to_match_regex", "regex/format",
     "customers.email shape, orders.order_ref prefix"),
    ("expect_column_values_to_not_match_regex", "regex/format",
     "negative format: no test/placeholder addresses in production data"),
    ("expect_column_value_lengths_to_be_between", "regex/format",
     "postcode / country_code / card_last4 fixed-width fields"),
    # -- type ----------------------------------------------------------------
    ("expect_column_values_to_be_of_type", "type",
     "orders.order_total is numeric, not text — catches a bad ETL cast"),
    ("expect_column_values_to_be_in_type_list", "type",
     "the tolerant form, for columns valid as any of several SQL types"),
    # -- row count -----------------------------------------------------------
    ("expect_table_row_count_to_be_between", "row count",
     "freshness/volume: the orders load landed neither empty nor doubled"),
    # -- column existence ----------------------------------------------------
    ("expect_column_to_exist", "column existence",
     "schema drift: the column a rule depends on is still there"),
]

# The weakest slot is `expect_column_values_to_be_null` — real e-commerce use is
# rare. If a 16th type is ever needed, drop it for
# `expect_column_proportion_of_non_null_values_to_be_between`, which states a
# null budget as a first-class threshold instead of via `mostly=`.

MULTI_COLUMN_BASES = ("ColumnPairMapExpectation", "MulticolumnMapExpectation")


def base_class_name(impl) -> str:
    for b in impl.__mro__[1:]:
        if b.__name__.endswith("Expectation"):
            return b.__name__
    return "?"


def attempt(fn):
    """Run fn; return (raised: bool, label: str)."""
    try:
        fn()
        return False, "accepted"
    except Exception as exc:  # noqa: BLE001 — we are cataloguing failure modes
        return True, type(exc).__name__


# ---------------------------------------------------------------------------
# 1. Version and the real registry
# ---------------------------------------------------------------------------

print(RULE)
print("1. INSTALLED VERSION AND REAL REGISTRY")
print(RULE)

registry = sorted(list_registered_expectation_implementations())
module_names = sorted(n for n in dir(gxe) if n[0].isupper())

print(f"great_expectations.__version__ : {gx.__version__}")
print(f"registered expectation types   : {len(registry)}")
print(f"names exported by gx.expectations: {len(module_names)} "
      f"(= registry + Expectation base + UnexpectedRowsExpectation)")
print(f"import cost                    : {IMPORT_SECONDS:.1f} s")

census = Counter(base_class_name(get_expectation_impl(t)) for t in registry)
print("\ncensus by base class:")
for base, n in census.most_common():
    print(f"  {base:30} {n:3}")

multi = [t for t in registry
         if base_class_name(get_expectation_impl(t)) in MULTI_COLUMN_BASES]
print(f"\nmulti-column types excluded from the MVP catalog ({len(multi)}):")
for t in multi:
    print(f"  - {t}")

assert gx.__version__.startswith("1."), f"expected GE 1.x, got {gx.__version__}"
assert len(registry) == 56, f"registry size changed: {len(registry)}"
assert len(module_names) == len(registry) + 2, "module/registry drift"


# ---------------------------------------------------------------------------
# 2. The curated catalog (SPEC O-1)
# ---------------------------------------------------------------------------

print()
print(RULE)
print(f"2. CURATED CATALOG — {len(CATALOG)} TYPES (SPEC O-1)")
print(RULE)

registry_set = set(registry)
current_family = None
for type_name, family, why in CATALOG:
    impl = get_expectation_impl(type_name)
    base = base_class_name(impl)
    required = impl.schema().get("required", [])
    mostly = "mostly" in impl.__fields__
    if family != current_family:
        print(f"\n[{family}]")
        current_family = family
    print(f"  {type_name}")
    print(f"      base={base}  required={required or '[]'}  mostly={mostly}")
    print(f"      why: {why}")

    assert type_name in registry_set, f"{type_name} is not in the real registry"
    assert base not in MULTI_COLUMN_BASES, f"{type_name} is multi-column"

names = [t for t, _, _ in CATALOG]
assert len(names) == len(set(names)) == 15, "catalog must be 15 unique types"
print(f"\nall {len(names)} present in the live registry, 0 multi-column: OK")


# ---------------------------------------------------------------------------
# 3. A valid expectation constructs
# ---------------------------------------------------------------------------

print()
print(RULE)
print("3. VALID INSTANTIATION")
print(RULE)

valid = gxe.ExpectColumnValuesToBeInSet(
    column="status",
    value_set=["shipped", "pending", "cancelled", "returned"],
)
print(f"class        : {type(valid).__name__}")
print(f"module       : {type(valid).__module__}")
print(f"base classes : {[b.__name__ for b in type(valid).__mro__[1:5]]}")
pydantic_bases = [b for b in type(valid).__mro__ if b.__name__ == "BaseModel"]
print(f"pydantic base: {[b.__module__ + '.' + b.__name__ for b in pydantic_bases]}")
print(f"cls.expectation_type : {type(valid).expectation_type}")
print(f"instance .type attr  : {getattr(valid, 'type', 'ABSENT')}  <- absent in 1.x")
print(f"instance .to_json_dict: {hasattr(valid, 'to_json_dict')}  <- absent in 1.x")

assert type(valid).expectation_type == "expect_column_values_to_be_in_set"
assert any("pydantic.v1" in b.__module__ for b in pydantic_bases), \
    "object model is no longer pydantic v1 — introspection code must change"
assert hasattr(type(valid), "__fields__") and not hasattr(type(valid), "model_fields"), \
    "introspection surface changed: use __fields__/.schema(), not pydantic v2 names"


# ---------------------------------------------------------------------------
# 4. Invalid expectations — the empirical basis of INV-2
#    Each row is (label, thunk, expected_to_raise). expected_to_raise records
#    what GE ACTUALLY does, discovered empirically. Rows marked False are the
#    holes in INV-2, not permission to relax the check.
# ---------------------------------------------------------------------------

print()
print(RULE)
print("4. INVALID EXPECTATIONS — WHAT GE ACTUALLY REJECTS")
print(RULE)

CASES: list[tuple[str, object, bool]] = [
    # --- hallucinated type -------------------------------------------------
    ("hallucinated type via registry",
     lambda: get_expectation_impl("expect_column_values_to_be_vibey"), True),
    ("hallucinated type via ExpectationConfiguration(...)  [construct only]",
     lambda: ExpectationConfiguration(
         type="expect_column_values_to_be_vibey", kwargs={"column": "x"}), False),
    ("hallucinated type via ExpectationConfiguration(...).to_domain_obj()",
     lambda: ExpectationConfiguration(
         type="expect_column_values_to_be_vibey",
         kwargs={"column": "x"}).to_domain_obj(), True),

    # --- missing required kwargs -------------------------------------------
    ("not_be_null with no kwargs at all",
     lambda: gxe.ExpectColumnValuesToNotBeNull(), True),
    ("be_in_set without value_set",
     lambda: gxe.ExpectColumnValuesToBeInSet(column="status"), True),
    ("be_of_type without type_",
     lambda: gxe.ExpectColumnValuesToBeOfType(column="x"), True),
    ("row_count_to_equal without value",
     lambda: gxe.ExpectTableRowCountToEqual(), True),
    ("not_match_regex without regex",
     lambda: gxe.ExpectColumnValuesToNotMatchRegex(column="e"), True),

    # --- wrong-typed kwargs ------------------------------------------------
    ("column given as an int",
     lambda: gxe.ExpectColumnValuesToNotBeNull(column=123), True),
    ("value_set given as a bare string",
     lambda: gxe.ExpectColumnValuesToBeInSet(column="s", value_set="shipped"), True),
    ("row_count value given as a string",
     lambda: gxe.ExpectTableRowCountToEqual(value="abc"), True),
    ("mostly=1.5 (outside 0..1)",
     lambda: gxe.ExpectColumnValuesToNotBeNull(column="x", mostly=1.5), True),

    # --- misspelled kwarg (the LLM typo case) ------------------------------
    ("misspelled kwarg min_valu=",
     lambda: gxe.ExpectColumnValuesToBeBetween(column="x", min_valu=0), True),

    # --- root validators ---------------------------------------------------
    ("values_to_be_between with neither bound",
     lambda: gxe.ExpectColumnValuesToBeBetween(column="x"), True),
    ("value_lengths_to_be_between with neither bound",
     lambda: gxe.ExpectColumnValueLengthsToBeBetween(column="e"), True),
    ("row_count_to_be_between with min > max",
     lambda: gxe.ExpectTableRowCountToBeBetween(min_value=100, max_value=1), True),

    # --- THE HOLES: well-formed but meaningless. GE accepts all of these. ---
    ("values_to_be_between with min > max",
     lambda: gxe.ExpectColumnValuesToBeBetween(column="x", min_value=100,
                                               max_value=1), False),
    ("match_regex with an uncompilable regex '[unclosed'",
     lambda: gxe.ExpectColumnValuesToMatchRegex(column="e", regex="[unclosed"), False),
    ("match_regex with NO regex at all",
     lambda: gxe.ExpectColumnValuesToMatchRegex(column="e"), False),
    ("in_type_list with NO type_list at all",
     lambda: gxe.ExpectColumnValuesToBeInTypeList(column="e"), False),
    ("row_count_to_be_between with no bounds (vacuously true)",
     lambda: gxe.ExpectTableRowCountToBeBetween(), False),
    ("mean_to_be_between with no bounds (vacuously true)",
     lambda: gxe.ExpectColumnMeanToBeBetween(column="x"), False),
    ("unique_value_count_to_be_between with no bounds (vacuously true)",
     lambda: gxe.ExpectColumnUniqueValueCountToBeBetween(column="x"), False),
    ("be_in_set with an empty value_set (can never pass)",
     lambda: gxe.ExpectColumnValuesToBeInSet(column="s", value_set=[]), False),
    ("be_of_type with a nonexistent SQL type name",
     lambda: gxe.ExpectColumnValuesToBeOfType(column="x", type_="NOT_A_TYPE"), False),
]

holes: list[str] = []
for label, thunk, expected_raise in CASES:
    raised, how = attempt(thunk)
    mark = "REJECTED" if raised else "ACCEPTED"
    flag = "" if raised == expected_raise else "  <<< BEHAVIOUR CHANGED"
    print(f"  [{mark}] {label}")
    print(f"           -> {how}{flag}")
    assert raised == expected_raise, (
        f"GE behaviour changed for {label!r}: expected "
        f"{'raise' if expected_raise else 'accept'}, got "
        f"{'raise' if raised else 'accept'}. This is a finding, not a test bug "
        f"— update the docstring and the compiler's own sanity table."
    )
    if not raised:
        holes.append(label)

print(f"\n{len(CASES) - len(holes)} of {len(CASES)} rejected by GE.")
print(f"{len(holes)} accepted despite being wrong — INV-2 needs our own layer "
      f"on top:")
for h in holes:
    print(f"  ! {h}")

# INV-2's minimum: a hallucinated type must never reach the store.
try:
    get_expectation_impl("expect_column_values_to_be_vibey")
    raise AssertionError("a hallucinated type was resolved — INV-2 is broken")
except ExpectationNotFoundError:
    print("\nINV-2 floor holds: a hallucinated type cannot be resolved "
          "(ExpectationNotFoundError).")

# ...but only through the concrete class, not through ExpectationConfiguration.
assert not attempt(lambda: ExpectationConfiguration(
    type="expect_column_values_to_be_vibey", kwargs={"column": "x"}))[0], \
    "ExpectationConfiguration now validates its type — the compiler may simplify"
print("INV-2 caveat holds: ExpectationConfiguration does NOT validate its type. "
      "The compiler must instantiate the concrete class.")


# ---------------------------------------------------------------------------
# 5. Serialisation contract for the compiler (F7)
# ---------------------------------------------------------------------------

print()
print(RULE)
print("5. SERIALISATION / DESERIALISATION CONTRACT")
print(RULE)

config = valid.configuration
print(f"obj.configuration -> {type(config).__name__}")
wire = config.to_json_dict()
print(json.dumps(wire, indent=2, default=str))

assert set(wire) == {"type", "kwargs", "meta", "severity"}, \
    f"wire shape changed: {sorted(wire)}"
assert wire["type"] == "expect_column_values_to_be_in_set", \
    "wire key for the type is no longer 'type'"

# Round trip: our stored spec is {type, kwargs}; that is all the compiler needs.
rebuilt = get_expectation_impl(wire["type"])(**wire["kwargs"])
assert rebuilt.configuration.to_json_dict() == wire, "round trip is not exact"
print("\nround trip {type, kwargs} -> object -> {type, kwargs}: exact")

# obj.dict() leaks GE defaults; we store our own spec instead.
leaked = sorted(set(valid.dict()) - set(wire["kwargs"]) - {"id", "meta", "notes"})
print(f"obj.dict() additionally leaks GE defaults: {leaked}")


# ---------------------------------------------------------------------------
# 6. Suite assembly without a DataContext (F7)
# ---------------------------------------------------------------------------

print()
print(RULE)
print("6. SUITE ASSEMBLY — NO DataContext REQUIRED")
print(RULE)

suite = gx.ExpectationSuite(
    name="orders_suite",
    expectations=[
        gxe.ExpectColumnValuesToNotBeNull(column="customer_id"),
        gxe.ExpectColumnValuesToBeUnique(column="order_id"),
        gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=0),
        valid,
        gxe.ExpectTableRowCountToBeBetween(min_value=1, max_value=1_000_000),
    ],
)
print(f"built via constructor, {len(suite.expectations)} expectations, "
      f"no context created")
print(json.dumps(suite.to_json_dict(), indent=2, default=str)[:520] + "\n  ...")

assert len(suite.expectations) == 5

# The trap: add_expectation() reaches for a global project manager.
raised, how = attempt(
    lambda: gx.ExpectationSuite(name="x").add_expectation(
        gxe.ExpectColumnValuesToNotBeNull(column="c")))
print(f"\nsuite.add_expectation() without a context -> "
      f"{'RAISES ' + how if raised else 'works'}")
assert raised and how == "DataContextRequiredError", \
    "add_expectation no longer needs a context — the compiler may use it"
print("=> the compiler builds suites by constructor, never add_expectation().")


print()
print(RULE)
print("ALL ASSERTIONS PASSED")
print(RULE)
