"""F9 · the normalised result — and the third state the framework hides.

`catch_exceptions` defaults to `True` (LT-1a), so a rule that could not run does
not abort the suite. It lands as `success: false` with `result: {}`, which is
identical in every visible way to a rule that ran and found bad data. Only
`exception_info` separates them, and it has two shapes: flat when nothing raised
(`{"raised_exception": False, ...}`) and keyed by MetricConfigurationID string
when something did. So the read is `"raised_exception" in exception_info`, else
iterate `.values()`.

Why this is an invariant and not a nicety: a rule that did not run has a COVERAGE
meaning, not a data-quality meaning. Folding errored into failed tells a domain
expert their data is bad when what is actually bad is the rule — and it inflates
the count of things the product claims to have checked.

LT-1b made it sharper. The two type expectations break on a query asset with a
bare KeyError 'type', which under the default `catch_exceptions` renders as two
red rules with no offending rows and no explanation. The cap that would have
caused that does not ship (SPEC O-2), but the failure mode is generic: any rule
whose column is dropped or renamed errors exactly the same silent way.

THE OTHER HALF of what B14a owns — which rules a run submits, the asset it builds,
the result format it asks for, and the whole path run against the real seeded table
— is next door in `tests/test_rule_execution.py`. This file is the READING: given
framework output, what a person is told.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.dq import normalise
from app.rules import catalog

TABLE = "orders"

# The whole seeded table, and the disclosure's denominator — OURS, never the
# framework's (INV-5, seed/MANIFEST.md).
SEEDED_ROWS = 500_000

# Three rules aimed at three planted defect classes, in the shape the store holds.
NEGATIVE: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0},
}
IN_SET: dict[str, Any] = {
    "type": "expect_column_values_to_be_in_set",
    "kwargs": {
        "column": "status",
        "value_set": ["pending", "paid", "shipped", "delivered", "cancelled", "returned"],
    },
}
UNIQUE: dict[str, Any] = {
    "type": "expect_column_values_to_be_unique",
    "kwargs": {"column": "order_reference"},
}
SPECS: list[dict[str, Any]] = [NEGATIVE, IN_SET, UNIQUE]

# The whole-table scan that actually ships: no cap, so nothing is a sample (O-2).
SCAN = normalise.Scan(TABLE, SEEDED_ROWS)

# The two shapes of `exception_info`, verbatim from LT-1a. The flat one is what
# every honest result carries; the keyed one is what an errored rule carries, and
# reading only the first is what makes an errored rule look like a failing one.
NOTHING_RAISED = {
    "raised_exception": False,
    "exception_traceback": None,
    "exception_message": None,
}
FLAT_RAISE = {
    "raised_exception": True,
    "exception_traceback": "Traceback (most recent call last): ...",
    "exception_message": "column order_totl does not exist",
}
KEYED_RAISE = {
    "MetricConfigurationID(metric_name='column_values.between.condition', ...)": {
        "raised_exception": True,
        "exception_traceback": "Traceback (most recent call last): ...",
        "exception_message": "KeyError: 'type'",
    }
}


def _reported(spec: dict[str, Any], success: bool, info: Any = None, **body: Any) -> dict[str, Any]:
    """One `results` entry, in the shape `to_json_dict()` produces (LT-1a).

    `batch_id` rides on the evaluated kwargs — the one thing the framework adds on
    the way through — so the join has to survive it here as it does in a real run.
    """
    return {
        "success": success,
        "expectation_config": {
            "type": spec["type"],
            "kwargs": {**spec["kwargs"], "batch_id": "postgres-orders"},
        },
        "result": body,
        "exception_info": info or NOTHING_RAISED,
    }


def _report(*results: dict[str, Any]) -> dict[str, Any]:
    return {"success": False, "suite_name": TABLE, "results": list(results)}


def _one(spec: dict[str, Any], success: bool, info: Any = None, **body: Any) -> normalise.Result:
    return normalise.normalise([spec], _report(_reported(spec, success, info, **body)), SCAN)[0]


def test_an_errored_rule_is_a_third_state_not_a_failure() -> None:
    """Feed the normaliser both shapes of exception_info and assert they diverge.

    A rule with `raised_exception: True` normalises to `errored` and carries the
    exception message; a genuine `success: false` with no exception normalises to
    `failed` and carries the violating count. The assertion is that the two are
    not equal — asserting only that the errored one says "errored" would pass on a
    normaliser that labels everything errored.
    """
    failed = _one(NEGATIVE, False, unexpected_count=150, partial_unexpected_list=[-450.0])
    errored = _one(NEGATIVE, False, KEYED_RAISE)

    assert failed.raw["success"] is errored.raw["success"] is False, (
        "the trap only exists while both arrive as `success: false`; if this fixture drifts, "
        "the check below stops proving anything"
    )
    assert (failed.verdict, errored.verdict) == ("failed", "errored")
    assert failed.verdict != errored.verdict
    assert failed.atom != errored.atom, "two different states rendering the same text is the bug"

    assert failed.unexpected_count == 150 and failed.samples == (-450.0,)
    assert failed.detail is None
    assert (
        errored.unexpected_count is None
    ), "an errored rule counted nothing; reporting 0 violations would read as a clean column"
    assert errored.detail and "KeyError" in errored.detail, (
        f"an errored rule must carry why it could not run, got {errored.detail!r} — INV-4: "
        "every failure is readable by someone who can judge whether it matters"
    )


def test_errored_is_distinguished_from_failed_via_exception_info_both_shapes() -> None:
    """`exception_info` has two shapes and only one of them is the obvious one.

    Flat when nothing raised, keyed by MetricConfigurationID when something did
    (LT-1a). A normaliser that reads `info["raised_exception"]` and stops handles
    the honest case perfectly and calls every genuinely errored rule a failure —
    which is the exact direction the mistake goes, because the flat shape is the
    one you see while everything is working.
    """
    for info, needle in ((FLAT_RAISE, "order_totl"), (KEYED_RAISE, "KeyError")):
        errored = _one(NEGATIVE, False, info)
        assert errored.verdict == "errored", f"{info!r} was read as a data failure"
        assert needle in (errored.detail or ""), (
            f"the message from {sorted(info)[0][:40]!r} did not reach the result; the two shapes "
            "must both be read, not just the one that appears when nothing is wrong"
        )

    assert _one(NEGATIVE, False, NOTHING_RAISED).verdict == "failed", (
        "the flat shape with raised_exception False is what EVERY honest result carries; "
        "treating its presence as an error would make every failing rule errored"
    )
    assert _one(NEGATIVE, True, NOTHING_RAISED).verdict == "passed"


def test_a_tolerated_rule_passes_while_still_reporting_its_violations() -> None:
    """`success` is the verdict. `unexpected_count == 0` is a different question.

    A rule carrying `mostly` succeeds WITH violations — LT-1a measured `success:
    true` alongside `unexpected_count: 25` — because that is the tolerance its
    author asked for. Deriving the verdict from the count instead would paint a rule
    red next to the allowance that makes it green. Both readings therefore survive
    normalisation: F13 shows the pass and the 25, or a green rule sitting beside bad
    rows reads as a bug in this product rather than as the rule working.
    """
    tolerated = _one(NEGATIVE, True, unexpected_count=25, partial_unexpected_list=[-1.0])
    assert tolerated.verdict == "passed", "the violating count overrode the rule's own tolerance"
    assert tolerated.unexpected_count == 25, "the passing rule dropped the violations it tolerated"
    assert tolerated.samples == (-1.0,)
    assert tolerated.atom == "PASSED"


def test_an_errored_rule_never_counts_as_coverage() -> None:
    """The consequence of the state, asserted where it actually matters.

    Only `accepted` rules count toward coverage (SPEC F6); a rule that errored did
    not check anything, so a table whose only rule errored is not covered. Assert
    the coverage number, not the badge.
    """
    mixed = normalise.normalise(
        SPECS,
        _report(
            _reported(NEGATIVE, True),
            _reported(IN_SET, False, unexpected_count=240),
            _reported(UNIQUE, False, KEYED_RAISE),
        ),
        SCAN,
    )
    assert normalise.coverage(mixed) == 2, (
        f"three rules ran and one of them errored; coverage is {normalise.coverage(mixed)}. "
        "A rule that could not run has checked nothing, and counting it reports protection "
        "the table does not have."
    )
    assert len(mixed) == 3, "the errored rule is still reported — it is uncounted, not hidden"

    assert (
        normalise.coverage([_one(NEGATIVE, False, FLAT_RAISE)]) == 0
    ), "a table whose only rule errored is not a covered table"
    assert normalise.coverage([_one(NEGATIVE, True)]) == 1


def test_results_are_joined_by_expectation_config_not_index() -> None:
    """The framework reorders `results` the moment one errors (LT-1a). Joining by
    position then prints one rule's verdict under another rule's sentence — a
    silent, plausible, entirely wrong screen.

    So the report here is deliberately in reverse order and every rule carries a
    distinct count, which is what makes a mis-join visible rather than merely
    possible.
    """
    shuffled = _report(
        _reported(UNIQUE, False, unexpected_count=3),
        _reported(IN_SET, False, unexpected_count=2),
        _reported(NEGATIVE, False, unexpected_count=1),
    )
    results = normalise.normalise(SPECS, shuffled, SCAN)

    assert [r.spec["type"] for r in results] == [s["type"] for s in SPECS], (
        "results come back in the order the rules were submitted, whatever order the "
        "framework answered in — a progressive run renders against that list"
    )
    assert [r.unexpected_count for r in results] == [1, 2, 3], (
        f"got {[r.unexpected_count for r in results]}; joined by index this reads [3, 2, 1] "
        "and every number is attached to the wrong sentence"
    )
    assert results[0].statement == catalog.english(NEGATIVE["type"], NEGATIVE["kwargs"])

    with pytest.raises(ValueError) as dropped:
        normalise.normalise(SPECS, _report(_reported(NEGATIVE, True)), SCAN)
    assert IN_SET["type"] in str(dropped.value), (
        "a submitted rule that never reported must be named and refused; silently returning "
        "the two that did report is a run record claiming coverage it does not have"
    )
