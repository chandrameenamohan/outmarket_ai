# Learning test findings

One section per learning test, most recent first; add new sections at the top
and a row to the index below. Each section records what was verified against the
**really installed** library, what was measured, and what surprised us — because
a surprise is the only part of a learning test that changes the design.

The scripts themselves carry the same findings in their module docstrings; this
file is the index a reader hits first.

| Test | Subject | Status | Script |
|---|---|---|---|
| LT-2a | Great Expectations 1.x — object model and registry | passed | `lt2a_ge_registry.py` |
| LT-2b | Claude Agent SDK — auth, tool suppression, structured output | passed | `lt2b_agent_sdk.py` |

---

## LT-2a · Great Expectations 1.x object model and registry

**Bead** `dq-chf` · **Run** 2026-08-16 · **great-expectations 1.20.0**, Python 3.12.5
**Feeds** SPEC O-1 (catalog composition), F5 (curated catalog and validation),
F7 (compilation), INV-2, INV-3
**Run it:** `uv run --with great-expectations python learning-tests/lt2a_ge_registry.py`

### What was verified

- [x] Installed version is **1.20.0** — a genuine 1.x, so every pre-1.0 memory
      (`ExpectationConfiguration` as the primary object, `DataContext`
      everywhere, `expectation_type` as the wire key) had to be re-derived.
- [x] The registry holds **56** expectation types.
- [x] A **15-type catalog** was selected from that registry and every entry
      confirmed present, with zero multi-column types.
- [x] The object model is **pydantic v1** (`pydantic.v1.main.BaseModel`,
      vendored inside pydantic 2). Introspection is `__fields__` / `.schema()`,
      never `model_fields` / `model_json_schema()`.
- [x] Construction, serialisation, round-trip and suite assembly all work with
      **no `DataContext` at all**.
- [x] A hallucinated expectation type cannot be resolved — the floor under
      INV-2 holds.

### Measured

| | |
|---|---|
| registry types | 56 |
| — `ColumnMapExpectation` (per-row, single column) | 25 |
| — `ColumnAggregateExpectation` (whole-column statistic) | 15 |
| — `BatchExpectation` (table-level) | 10 |
| — `ColumnPairMapExpectation` + `MulticolumnMapExpectation` | 6 (excluded, v2) |
| curated catalog | 15 |
| invalid-rule probes | 25 — GE rejects 15, **accepts 10** |
| `import great_expectations` cold | ~3.2 s |

`great_expectations.expectations` exports 58 capitalised names — the 56
registered types plus the `Expectation` base and `UnexpectedRowsExpectation`
(a raw-SQL escape hatch, out of scope). **Count from the registry, not the
module.**

### The curated catalog (resolves O-1)

Single-column and table-level only. Multi-column is deferred to v2 — the six
excluded types are `expect_column_pair_values_a_to_be_greater_than_b`,
`expect_column_pair_values_to_be_equal`, `expect_column_pair_values_to_be_in_set`,
`expect_compound_columns_to_be_unique`, `expect_multicolumn_sum_to_equal`,
`expect_select_column_values_to_be_unique_within_record`.

| # | Family | Type | Base | GE-required kwargs | `mostly` |
|---|---|---|---|---|---|
| 1 | nulls | `expect_column_values_to_not_be_null` | ColumnMap | `column` | yes |
| 2 | nulls | `expect_column_values_to_be_null` | ColumnMap | `column` | yes |
| 3 | uniqueness | `expect_column_values_to_be_unique` | ColumnMap | `column` | yes |
| 4 | uniqueness | `expect_column_unique_value_count_to_be_between` | ColumnAggregate | `column` | no |
| 5 | value sets | `expect_column_values_to_be_in_set` | ColumnMap | `column`, `value_set` | yes |
| 6 | value sets | `expect_column_values_to_not_be_in_set` | ColumnMap | `column`, `value_set` | yes |
| 7 | ranges | `expect_column_values_to_be_between` | ColumnMap | `column` | yes |
| 8 | ranges | `expect_column_mean_to_be_between` | ColumnAggregate | `column` | no |
| 9 | regex/format | `expect_column_values_to_match_regex` | ColumnMap | `column` | yes |
| 10 | regex/format | `expect_column_values_to_not_match_regex` | ColumnMap | `column`, `regex` | yes |
| 11 | regex/format | `expect_column_value_lengths_to_be_between` | ColumnMap | `column` | yes |
| 12 | type | `expect_column_values_to_be_of_type` | ColumnMap | `column`, `type_` | yes |
| 13 | type | `expect_column_values_to_be_in_type_list` | ColumnMap | `column` | yes |
| 14 | row count | `expect_table_row_count_to_be_between` | Batch | *(none)* | no |
| 15 | column existence | `expect_column_to_exist` | Batch | `column` | no |

Why each earns its slot is recorded inline in `lt2a_ge_registry.py`. The
weakest slot is **#2 `expect_column_values_to_be_null`** — genuine e-commerce
use is rare. If a 16th type is ever wanted, drop it for
`expect_column_proportion_of_non_null_values_to_be_between`, which states a null
budget as a first-class threshold rather than via `mostly=`.

Note the `mostly` column: it exists only on map expectations. "At most 2% of
emails may be null" is expressible; "the mean is mostly in range" is not.

### UNEXPECTED — this is the finding that changes the design

**"Instantiate it against GE before persisting" is a weaker gate than INV-2
assumes.** GE's constructor validation is real, but it is *inconsistent between
expectation types*, and it checks shape, never sense.

GE **accepts** all of the following. Every one is a bad rule:

| Constructed without error | Why it is wrong |
|---|---|
| `values_to_be_between(column="x", min_value=100, max_value=1)` | contradictory bounds |
| `match_regex(column="e", regex="[unclosed")` | regex does not compile |
| `match_regex(column="e")` | no `regex` at all |
| `in_type_list(column="e")` | no `type_list` at all |
| `table_row_count_to_be_between()` | no bounds — vacuously true |
| `mean_to_be_between(column="x")` | no bounds — vacuously true |
| `unique_value_count_to_be_between(column="x")` | no bounds — vacuously true |
| `values_to_be_in_set(column="s", value_set=[])` | can never pass |
| `values_to_be_of_type(column="x", type_="NOT_A_TYPE")` | bogus SQL type name |

The asymmetries are the tell — this is not a coherent validation policy, it is
per-expectation authoring drift:

| | |
|---|---|
| `not_match_regex` without `regex` | **raises** |
| `match_regex` without `regex` | accepted |
| `row_count_to_be_between` with min > max | **raises** |
| `values_to_be_between` with min > max | accepted |
| `values_to_be_between` with neither bound | **raises** (root validator) |
| `mean_to_be_between` with neither bound | accepted |

And `.schema()["required"]` is **not** the source of truth either: it lists only
`['column']` for `values_to_be_between`, yet a root validator rejects
both-bounds-`None`. Required-ness lives in two places and neither is complete —
so the catalog cannot be generated purely from GE introspection.

**Second surprise:**
`ExpectationConfiguration(type="expect_column_values_to_be_vibey", kwargs={...})`
**constructs without error.** A hallucinated type passes straight through the
configuration object; it only raises at `.to_domain_obj()`. If the compiler ever
persists an `ExpectationConfiguration`, INV-2 does not hold at all.

What GE *does* reliably reject, and what we get for free: unknown types (through
the concrete class), missing required kwargs where they are declared,
wrong-typed kwargs, `mostly` outside 0..1, and — usefully for an LLM-authored
rule — **misspelled kwargs** (`min_valu=` → `extra fields not permitted`; the
constructor is strict, so typos cannot slip through as ignored extras).

### Consequences for F5 / F7

1. The validation gate is `get_expectation_impl(type)(**kwargs)` — the concrete
   class — **never** `ExpectationConfiguration`.
2. GE construction is **necessary but not sufficient**. The catalog must carry
   our own per-type required-parameter and sanity table — `min <= max`,
   non-empty `value_set`, `re.compile`-able regex, known SQL type name, at least
   one bound present — and run it *before* handing kwargs to GE. That table is a
   small amount of code and it is the part that actually makes INV-2 true. It is
   also what lets a rejection carry a reason a domain expert can read, which
   pydantic's `ValidationError` text does not.
3. This is the same shape as the LT-2b finding: **the tool confirms the rule is
   well-formed, never that it is meaningful.** LT-2b showed the model produces
   statistically true, business-naive rules; LT-2a shows GE will happily accept
   a rule that is not even statistically meaningful. Two independent
   confirmations that the human review step is load-bearing.

### The API contract for the one module that imports GE (INV-3)

```python
# --- construct -------------------------------------------------------------
from great_expectations.expectations.registry import get_expectation_impl
obj = get_expectation_impl(type_str)(**kwargs)
#   unknown type   -> great_expectations.exceptions.ExpectationNotFoundError
#   bad kwargs     -> pydantic.v1.ValidationError
#   unknown kwarg  -> ValidationError "extra fields not permitted"
# statically, the same classes live at:
import great_expectations.expectations as gxe
gxe.ExpectColumnValuesToBeInSet(column="status", value_set=[...])

# --- introspect ------------------------------------------------------------
cls = get_expectation_impl(type_str)
cls.expectation_type            # -> "expect_column_values_to_be_in_set"
cls.schema()["required"]        # -> declared required kwargs (INCOMPLETE, see above)
cls.__fields__                  # -> pydantic v1 FieldInfo map: .required, .outer_type_
"mostly" in cls.__fields__      # -> True only for map expectations
cls.__mro__[1].__name__         # -> ColumnMapExpectation | ColumnAggregateExpectation
                                #    | BatchExpectation | ColumnPairMapExpectation
                                #    | MulticolumnMapExpectation
                                #    (this is how multi-column is excluded)

# --- serialise -------------------------------------------------------------
obj.configuration.to_json_dict()
# -> {"type": str, "kwargs": {...}, "meta": {}, "severity": "critical"}
# The wire key is "type", NOT "expectation_type" — that is the 1.x rename.
# The instance itself has no .to_json_dict() and no .type attribute.
# obj.dict() works but leaks 10 GE defaults (result_format, catch_exceptions,
# mostly, severity, row_condition, ...). Store OUR spec, not this.

# --- deserialise -----------------------------------------------------------
obj = get_expectation_impl(d["type"])(**d["kwargs"])     # exact round trip
# or ExpectationConfiguration(**d).to_domain_obj()  <- validates only here

# --- suite (F7) ------------------------------------------------------------
import great_expectations as gx
suite = gx.ExpectationSuite(name="orders_suite", expectations=[obj, ...])
suite.to_json_dict()
# Context-free. suite.add_expectation(obj) instead demands an active context
# and raises DataContextRequiredError — do not use it in the compiler.
```

Everything above stays behind that one module: its public surface takes and
returns our own `{type, kwargs}` dicts, so `great_expectations` appears in
exactly one file, as INV-3 requires.

### Out of scope here

Executing a suite against PostgreSQL — that is LT-1a (`dq-dww`), which this
unblocks. Nothing in this test touched a database.

---

## LT-2b · Claude Agent SDK — auth, tool suppression, structured output

**Bead** `dq-uco` · **Run** 2026-08-16 · **claude-agent-sdk 0.1.23**, model `claude-opus-5`

Full findings live in the docstring of `lt2b_agent_sdk.py`. In brief: auth works
from `CLAUDE_CODE_OAUTH_TOKEN` with no API purchase; tools fully suppressed;
`max_turns=1` enforced; structured JSON obtained by instruction alone;
`setting_sources=[]` is required so the developer's own `CLAUDE.md` cannot leak
into a server-side call. Measured 6.6 s wall and $0.041 per call.

The finding that matters: every rule the model proposed was statistically true
and business-naive — it overfit the observed max instead of proposing the actual
business invariant `order_total >= 0`. The meaning is not in the sample.
