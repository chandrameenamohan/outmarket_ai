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

import pytest

from conftest import pending

# --- The ten probes the framework ACCEPTS. Our validator must reject every one. ---
# (type, kwargs, why it is nonsense)
FRAMEWORK_ACCEPTS_THESE_TEN = [
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
FRAMEWORK_REJECTS_THESE = [
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

    Asserted on the store, not on the return value — a validator that raises and
    a store that already wrote are both possible at once.
    """
    pending("needs app/rules/store.py — assert store count is unchanged across all probes")


def test_only_catalog_types_are_accepted() -> None:
    """F3/F5 constraint: a proposal outside the curated 15 is a defect, not a request."""
    pending("needs the canonical catalog file — see tests/test_catalog_and_copy.py")


@pytest.mark.ge
def test_framework_alone_would_let_ten_of_these_through() -> None:
    """The evidence for why layer 1 exists, re-asserted so it cannot rot.

    Run by the `uv run` line in VERIFICATION.md §3, not by `make check`. If a
    framework upgrade starts rejecting these, this
    test fails and we get to DELETE sanity rules instead of guessing.
    """
    pending("needs app/dq/ge_runtime.py — the only module allowed to construct expectations")
