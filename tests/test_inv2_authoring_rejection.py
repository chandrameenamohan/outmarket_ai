"""INV-2 · An invalid or non-existent expectation can never reach the rule store.

The point of this file, stated once so nobody weakens it later:

    Rejection must happen AT AUTHORING TIME, when the author is still looking at
    the screen and can be told why. An expectation that blows up during execution
    has already been stored, already counts toward coverage, and already lied
    about the table being protected.

The learning tests proved that "instantiate it against the framework" is NOT a
sufficient gate. Of 25 deliberately invalid rule probes, the framework REJECTED
15 and ACCEPTED 10. The 10 it accepts are listed below and are the real content
of this check. So the validator is two layers, in this order:

    1. our own per-type sanity table  (min <= max, non-empty value_set,
       re.compile-able regex, known SQL type name, at least one bound present)
    2. construction against the framework, via app/dq/ge_runtime.py

Layer 1 must run FIRST, because layer 2 alone lets all ten of these through.
The asymmetries are authoring drift in the framework, not policy we can lean on:
`not_match_regex` without a regex raises but `match_regex` without one does not;
`row_count_to_be_between` with min > max raises but `values_to_be_between` does not.
Required-ness lives in two incomplete places (`.schema()["required"]` and a root
validator), which is also why the catalog cannot be generated from introspection.
"""

from __future__ import annotations

import ast
import copy
import pathlib
from typing import Any

import pytest

from app.rules import catalog
from conftest import pending

# --- The ten probes the framework ACCEPTS. Our validator must reject every one. ---
# (type, kwargs, why it is nonsense)
FRAMEWORK_ACCEPTS_THESE_TEN: list[tuple[str, dict[str, Any], str]] = [
    (
        "expect_column_values_to_be_between",
        {"column": "x", "min_value": 100, "max_value": 1},
        "inverted bounds",
    ),
    (
        "expect_column_values_to_match_regex",
        {"column": "e", "regex": "[unclosed"},
        "regex does not compile",
    ),
    ("expect_column_values_to_match_regex", {"column": "e"}, "no regex at all"),
    ("expect_column_values_to_be_in_type_list", {"column": "e"}, "no type_list at all"),
    ("expect_table_row_count_to_be_between", {}, "no bounds at all"),
    ("expect_column_mean_to_be_between", {"column": "x"}, "no bounds at all"),
    ("expect_column_unique_value_count_to_be_between", {"column": "x"}, "no bounds at all"),
    (
        "expect_column_values_to_be_in_set",
        {"column": "s", "value_set": []},
        "empty value_set can never pass",
    ),
    (
        "expect_column_values_to_be_of_type",
        {"column": "x", "type_": "NOT_A_TYPE"},
        "not a real SQL type name",
    ),
    (
        "expect_column_values_to_be_unique",
        {"column": "no_such_column"},
        "column absent from the live schema",
    ),
]

# --- Probes the framework itself rejects. Our validator must still surface a
# --- readable reason rather than leaking a framework traceback to the author.
FRAMEWORK_REJECTS_THESE: list[tuple[str, dict[str, Any], str]] = [
    (
        "expect_column_values_to_be_vibey",
        {"column": "x"},
        "hallucinated type -> ExpectationNotFoundError",
    ),
    (
        "expect_column_values_to_be_between",
        {"column": "x", "min_valu": 0},
        "misspelled kwarg -> ValidationError 'extra fields not permitted'",
    ),
    (
        "expect_column_values_to_not_match_regex",
        {"column": "e"},
        "missing declared kwarg -> ValidationError",
    ),
    (
        "expect_column_values_to_not_be_null",
        {"column": "x", "mostly": 1.5},
        "mostly outside 0..1 -> ValidationError",
    ),
]

ALL_PROBES = FRAMEWORK_ACCEPTS_THESE_TEN + FRAMEWORK_REJECTS_THESE

# What each refusal must NAME, keyed by the probe's own description. Written out
# rather than derived, because "the message mentions the thing that was wrong" is
# not computable from the input — it is the judgement being asserted. Keyed by
# `why` so a new probe with no entry fails collection rather than passing silently.
NAMES_THE_FAULT: dict[str, str] = {
    "inverted bounds": "100",
    "regex does not compile": "[unclosed",
    "no regex at all": "regex",
    "no type_list at all": "type_list",
    "no bounds at all": "min_value",
    "empty value_set can never pass": "value_set",
    "not a real SQL type name": "NOT_A_TYPE",
    "column absent from the live schema": "no_such_column",
    "hallucinated type -> ExpectationNotFoundError": "expect_column_values_to_be_vibey",
    "misspelled kwarg -> ValidationError 'extra fields not permitted'": "min_valu",
    "missing declared kwarg -> ValidationError": "regex",
    "mostly outside 0..1 -> ValidationError": "mostly",
}

# Everything the validator is allowed to reach, dotted to the LEAF. The point is the
# absence: no store, no filesystem, no database driver, so a rejection has nowhere to
# leave a partial write. At PACKAGE granularity `app.rules` admits
# `from app.rules import store`, and this whole check is then satisfied by a validator
# that raises after writing a row — the precise thing INV-2 forbids. A new stdlib name
# here is a deliberate edit in front of a failing check, like `test_rule_store.WRITERS`.
PURE_IMPORTS = {
    "__future__.annotations",
    "re",
    "collections.abc.Callable",
    "collections.abc.Collection",
    "collections.abc.Mapping",
    "typing.Any",
    "app.rules.catalog",
    "app.dq.ge_runtime",
}

# An import allowlist cannot see `__import__`: it is a builtin, so reaching the store
# through it needs no import statement at all. These are the call shapes that would
# make one, or write without one.
CANNOT_BE_CALLED = {"__import__", "eval", "exec", "open", "connect", "execute", "_append"}

# Real framework types, deliberately outside the catalog: F4 defers multi-column
# rules to v2, so this is the boundary the framework itself cannot help us hold.
MULTI_COLUMN_TYPES = (
    "expect_column_pair_values_a_to_be_greater_than_b",
    "expect_column_pair_values_to_be_equal",
    "expect_compound_columns_to_be_unique",
)


def _validator():
    try:
        from app.rules import validator  # noqa: PLC0415
    except ImportError:
        pending("app/rules/validator.py does not exist yet — F5 is unbuilt")
    return validator


@pytest.mark.parametrize(
    "etype,kwargs,why",
    [pytest.param(t, k, w, id=f"{t}:{w}") for t, k, w in ALL_PROBES],
)
def test_invalid_spec_is_rejected_at_authoring_time(etype: str, kwargs: dict, why: str) -> None:
    v = _validator()
    with pytest.raises(v.RuleRejected) as exc:
        v.validate(etype, kwargs, table="orders")
    assert str(exc.value), f"rejection for '{why}' must carry a reason the author can read"


def test_a_rejected_spec_writes_nothing() -> None:
    """The half a unit test usually misses: rejection must not persist a row.

    Asserted on the SHAPE of the validator, not on its control flow, which is the
    stronger of the two readings available: a row count taken before and after the
    25 probes says those 25 wrote nothing, while an import graph with no store, no
    filesystem and no database driver in it says NO rejection can ever write —
    including the ones nobody thought to probe. A validator that raises and a store
    that already wrote are both possible at once only if the validator can reach a
    store, and this asserts it cannot.

    The call scan is the same claim from the side no import allowlist can see:
    `__import__` is a builtin and needs no import statement at all.

    The last assertion is the other thing a rejection must leave alone: the author's
    own kwargs dict. A validator that normalises in place has edited the rule under
    the person it just refused.

    Its dynamic companion is
    `tests/test_rule_store_on_postgres.py::test_a_rejected_spec_writes_no_row`,
    which counts the store's rows across these same probes. It lives there because
    it needs a live store; it is not a replacement for this one, which says no
    rejection CAN write, including the ones nobody thought to probe.
    """
    v = _validator()
    tree = ast.parse(pathlib.Path(v.__file__).read_text())
    imported = {
        f"{node.module}.{alias.name}" if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert imported == PURE_IMPORTS, (
        f"the validator's imports are {sorted(imported)}, this check knows about "
        f"{sorted(PURE_IMPORTS)}. INV-2 holds because a rejection has nowhere to leave a "
        "partial write: no store, no filesystem, no database driver. Take the spec, return "
        "the spec, let the caller persist it — and add a new stdlib name here deliberately."
    )

    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not (reached := sorted(called & CANNOT_BE_CALLED)), (
        f"the validator calls {reached}. The import allowlist above cannot see a builtin, so "
        "this is the other half: no dynamic import, no file, no cursor, no INSERT."
    )

    for etype, kwargs, why in ALL_PROBES:
        before = copy.deepcopy(kwargs)
        with pytest.raises(v.RuleRejected):
            v.validate(etype, kwargs, table="orders")
        assert kwargs == before, (
            f"the rejection for '{why}' mutated the caller's kwargs: {before} -> {kwargs}. "
            "A refused rule must be returned to its author exactly as they wrote it."
        )


def test_only_catalog_types_are_accepted() -> None:
    """F3/F5 constraint: a proposal outside the curated 15 is a defect, not a request.

    The six multi-column types are the probe that matters, because every one of
    them is REAL — the framework constructs them without complaint and would run
    them. They are out by policy (F4 defers multi-column to v2), so this is the one
    boundary the framework cannot help us hold.
    """
    v = _validator()
    assert v.ALLOWED_TYPES is catalog.TYPES, (
        "the validator's allowed set is a copy of the catalog rather than the catalog. "
        "Two lists drift, and the direction that hurts is silent: a type offered to the "
        "model and refused here produces a proposal nobody can save."
    )

    for etype in MULTI_COLUMN_TYPES:
        with pytest.raises(v.RuleRejected) as exc:
            v.validate(etype, {"column_A": "a", "column_B": "b"}, table="orders")
        assert etype in str(exc.value) and v.NOT_IN_CATALOG in str(exc.value), (
            f"{etype} is a real framework type outside our catalog; the refusal must say so "
            f"and name it. Got: {exc.value}"
        )

    for etype in catalog.TYPES:
        with pytest.raises(v.RuleRejected) as exc:
            v.validate(etype, {}, table="orders")
        assert v.NOT_IN_CATALOG not in str(exc.value), (
            f"{etype} is IN the catalog and was refused as if it were not: {exc.value}. "
            "Every one of these must be refused for its parameters, never for its identity."
        )


@pytest.mark.parametrize(
    "etype,kwargs,why",
    [pytest.param(t, k, w, id=f"{t}:{w}") for t, k, w in ALL_PROBES],
)
def test_rejection_message_names_the_fault(etype: str, kwargs: dict, why: str) -> None:
    """A refusal an author cannot act on is a refusal they will work around.

    INV-4 applied at authoring time: the message has to name the offending thing —
    the parameter, the value, the identifier — not merely report that something was
    wrong. `test_invalid_spec_is_rejected_at_authoring_time` asserts a reason exists;
    this asserts the reason is about THIS fault.
    """
    v = _validator()
    with pytest.raises(v.RuleRejected) as exc:
        v.validate(etype, kwargs, table="orders")
    assert NAMES_THE_FAULT[why] in str(exc.value), (
        f"the refusal for '{why}' never mentions {NAMES_THE_FAULT[why]!r}: {exc.value}\n"
        "The author has to be able to see what to change from the message alone."
    )


def test_identifier_absent_from_live_schema_is_rejected() -> None:
    """SPEC §3.1 — an identifier from model output is checked before anything is built.

    Two halves, and the first is the one that is easy to leave out. A missing schema
    is not permission to skip the check: the validator FAILS CLOSED, because
    "we could not verify this column" and "this column is fine" are the same outcome
    only if nobody is paying attention.
    """
    v = _validator()
    spec = ("expect_column_values_to_be_unique", {"column": "order_reference"})

    with pytest.raises(v.RuleRejected) as unverified:
        v.validate(*spec, table="orders")
    assert "order_reference" in str(unverified.value) and "orders" in str(unverified.value), (
        f"a rule validated with no schema must be refused, naming what could not be "
        f"verified and where: {unverified.value}"
    )

    live = {"order_id", "order_reference", "order_total", "status"}
    with pytest.raises(v.RuleRejected) as absent:
        v.validate("expect_column_to_exist", {"column": "custmer_id"}, table="orders", columns=live)
    assert "custmer_id" in str(absent.value) and "orders" in str(absent.value), (
        f"refusing a column absent from the live schema must name the column and the table: "
        f"{absent.value}"
    )


@pytest.mark.ge
def test_a_well_formed_rule_survives_both_layers_against_the_live_schema() -> None:
    """The positive path, end to end, against the real database — the check with teeth.

    Everything above proves things are refused. Refusing everything is a trivial way
    to pass all of it, so this is the assertion that stops the gate being satisfiable
    by a validator that says no. It reads the LIVE schema of the seeded `orders`
    table rather than a set written down here, which is the only way "validated
    against the live schema" is a mechanism rather than a promise.

    The returned spec is the framework's own normalisation (`min_value=0` -> `0.0`),
    which is the shape the store holds and F7 compiles — nothing reaches the store
    that did not come out of `validate()`.
    """
    from app.dq import ge_runtime  # noqa: PLC0415
    from app.rules import schema  # noqa: PLC0415

    v = _validator()
    assert schema.DSN_VAR == ge_runtime.DSN_VAR, (
        f"the schema reader connects via {schema.DSN_VAR} and the rule runtime via "
        f"{ge_runtime.DSN_VAR}. Validating identifiers against one database and running the "
        "rules against another is the one way this check can pass and still be wrong."
    )

    live = schema.columns("orders")
    assert {"order_total", "order_reference", "status"} <= live, (
        f"the seeded orders table is missing columns seed/MANIFEST.md documents; got "
        f"{sorted(live)}. Run: python3 seed/seed_demo_data.py"
    )

    spec = v.validate(
        "expect_column_values_to_be_between",
        {"column": "order_total", "min_value": 0},
        table="orders",
        columns=live,
    )
    assert spec == {
        "type": "expect_column_values_to_be_between",
        "kwargs": {"column": "order_total", "min_value": 0.0},
    }, f"a valid rule must come back as the storable spec, and only that; got {spec}"

    with pytest.raises(v.RuleRejected) as exc:
        v.validate(
            "expect_column_values_to_be_unique",
            {"column": "no_such_column"},
            table="orders",
            columns=live,
        )
    assert "no_such_column" in str(exc.value)

    with pytest.raises(schema.UnknownTable):
        schema.columns("no_such_table_here")


@pytest.mark.ge
def test_framework_alone_would_let_ten_of_these_through() -> None:
    """The evidence for why layer 1 exists, re-asserted so it cannot rot.

    Run by the `uv run` line in VERIFICATION.md §1, not by `make check`. If a
    framework upgrade starts rejecting these, this
    test fails and we get to DELETE sanity rules instead of guessing.

    It goes through app/dq/ge_runtime.py, which is the only module allowed to
    construct an expectation — so this is also the proof that layer 2 IS the
    framework's own constructor and not a paraphrase of it.
    """
    from app.dq import ge_runtime  # noqa: PLC0415

    accepted, refused = [], []
    for etype, kwargs, why in ALL_PROBES:
        try:
            ge_runtime.construct(etype, kwargs)
            accepted.append(why)
        except ge_runtime.Rejected as exc:
            refused.append((why, str(exc)))

    assert accepted == [why for _, _, why in FRAMEWORK_ACCEPTS_THESE_TEN], (
        f"the framework now accepts {accepted}. LT-2a measured exactly these ten. If the list "
        "SHRANK, delete the matching sanity rule from app/rules/validator.py — layer 1 exists "
        "only to cover what layer 2 misses. If it GREW, layer 1 is now missing a case."
    )
    assert [why for why, _ in refused] == [why for _, _, why in FRAMEWORK_REJECTS_THESE]
    assert all(reason for _, reason in refused), (
        f"a refusal with no reason: {refused}. Layer 2's rejections reach the author too, and "
        "an empty message is a framework traceback's worth of nothing."
    )
