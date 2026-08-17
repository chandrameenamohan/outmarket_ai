"""INV-4 · a failure reads as something a non-engineer can judge — the data half.

SPEC F13 states the target as a sentence:

    "150 orders have a negative total · of 500,000 rows scanned · 0.03% · #88231 −450.00 …"

Take it apart and it is four claims, and every one of them is a thing that has to
be IN the record before any screen exists — because a screen is where numbers get
invented, and the gate cannot check arithmetic written in TSX:

    the rule's own English statement   `app/rules/catalog.py::english()`, already
                                       the sentence its author approved
    how big the problem is             the count, the denominator it is a count OF,
                                       and the share — one string, one writer
    what a wrong row looks like        real values with the identifier that lets
                                       somebody go and open the row
    and the framework's own output     kept whole and separate, for when the
                                       reading is not enough

WHY THE COUNT IS NEVER ALONE. 150 is a catastrophe in a 500-row table and a
rounding error in 500,000. A count with no denominator is not a small failure of
presentation, it is an unjudgeable number, which is exactly what INV-4 forbids.

THE THREE SHAPES THIS FILE EXISTS TO KEEP APART, all of which look alike at the
framework's own output (LT-1a):

    failed          a count, a share, and offending rows
    errored         none of those. `catch_exceptions` makes an errored rule arrive
                    as `success: false` with an empty `result`, so a reading that
                    defaults its count to zero renders "0 violating rows · 0.00%"
                    beside a red badge — a rule that found nothing wrong, painted
                    as a failure, sending somebody hunting a defect that is not there
    countless       the four aggregate and table-level types report an observed
                    value and no count at all. Their reading is that value against
                    the range the statement already names — not an empty failure

And a FOURTH that is none of the above: `success: true` with a non-zero count, the
tolerance a `mostly` clause asked for. Both readings survive or the pass looks like
this product failed to notice the rows.

The numbers asserted here are `seed/MANIFEST.md`'s planted defects, so they are the
numbers the product will really print; the same sentence is asserted against the
live table in `tests/test_rule_execution.py`'s `ge` check. The rendering half of
F13 — the collapsed raw panel, the pending row, the re-run control — is the browser
layer, in `tests/e2e/test_f13_results_dashboard.py`.
"""

from __future__ import annotations

import json
from typing import Any

from app.dq import normalise

TABLE = "orders"

# The disclosure's denominator and the share's, and it is OURS (INV-5).
SEEDED_ROWS = 500_000

# The whole-table scan that ships: no cap, so nothing is a sample (SPEC O-2).
SCAN = normalise.Scan(TABLE, SEEDED_ROWS)

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

# Two of the four types that can never carry a violating count or an offending value
# — a ColumnAggregate and a Batch shape (LT-1a). A reading built only against
# ColumnMap results renders a quarter of the catalog as empty failures.
MEAN: dict[str, Any] = {
    "type": "expect_column_mean_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0, "max_value": 500.0},
}
EXISTS: dict[str, Any] = {"type": "expect_column_to_exist", "kwargs": {"column": "order_total"}}

# A rule whose violating rows are exactly the rows with no value — the one case
# where an offending value cannot be printed as itself.
NOT_NULL: dict[str, Any] = {
    "type": "expect_column_values_to_not_be_null",
    "kwargs": {"column": "ship_country"},
}

# seed/MANIFEST.md is the ground truth: D1 plants 150 negative order_totals and D3
# plants 240 statuses outside the vocabulary, both in the 500,000-row `orders` table.
D1_NEGATIVE_TOTALS = 150
D3_BAD_STATUSES = 240

# The keyed shape of `exception_info`, verbatim from LT-1a — what a rule that could
# not run carries, and the only thing separating it from one that found bad data.
NOTHING_RAISED = {"raised_exception": False, "exception_traceback": None}
KEYED_RAISE = {
    "MetricConfigurationID(metric_name='column_values.between.condition', ...)": {
        "raised_exception": True,
        "exception_traceback": "Traceback (most recent call last): ...",
        "exception_message": "KeyError: 'type'",
    }
}


def _one(
    spec: dict[str, Any],
    success: bool,
    info: Any = None,
    scan: normalise.Scan = SCAN,
    **body: Any,
) -> normalise.Result:
    """One rule's framework output, read through F9 against the given asset definition."""
    report = {
        "success": success,
        "results": [
            {
                "success": success,
                "expectation_config": {
                    "type": spec["type"],
                    "kwargs": {**spec["kwargs"], "batch_id": "postgres-orders"},
                },
                "result": body,
                "exception_info": info or NOTHING_RAISED,
            }
        ],
    }
    return normalise.normalise([spec], report, scan)[0]


def test_a_failure_carries_the_size_of_the_problem_as_a_count_and_a_share() -> None:
    """INV-4's arithmetic half: 150 is unjudgeable, 150 of 500,000 is 0.03%.

    A count with no denominator is the same number in a 500-row table and in a
    500,000-row one, and those are a catastrophe and a rounding error. So the
    count, what it is a count OF, and the share travel as one string from the single
    writer — the same reason the sampling clause travels inside the verdict.

    The numbers are seed/MANIFEST.md's: D1 plants 150 negative totals in 500,000
    rows, which is SPEC F13's own 0.03%, and D3 plants 240, which is 0.05%. Both,
    because one of them alone is satisfied by a hard-coded string.
    """
    failed = _one(
        NEGATIVE, False, unexpected_count=D1_NEGATIVE_TOTALS, partial_unexpected_list=[-450.0]
    )
    assert failed.statement == "Every order_total is at least 0", (
        f"the rule reads {failed.statement!r} — a failure a domain expert judges starts with "
        "the sentence they approved, never with an expectation type"
    )
    assert failed.magnitude == "150 violating rows · of 500,000 rows scanned · 0.03%", (
        f"the size of the problem reads {failed.magnitude!r}. SPEC F13: the count AND the "
        "proportion, because neither one alone says whether this matters."
    )

    statuses = _one(IN_SET, False, unexpected_count=D3_BAD_STATUSES)
    assert statuses.magnitude == "240 violating rows · of 500,000 rows scanned · 0.05%"

    tiny = _one(NEGATIVE, False, unexpected_count=1)
    assert tiny.magnitude and tiny.magnitude.endswith("<0.01%"), (
        f"one bad row in 500,000 renders as {tiny.magnitude!r}. A share that rounds to '0.00%' "
        "tells someone nothing happened, and something did — the row is right there."
    )


def test_the_share_is_of_the_rows_scanned_never_of_the_rows_that_exist() -> None:
    """The denominator is the one the run can defend, and it is the one it discloses.

    Hold the framework's output constant and cap the asset: the same 150 violating
    rows are a larger share of a smaller scan. A share taken over rows nobody looked
    at would be a number this run cannot support, and it would contradict the
    sampling clause sitting in the atom beside it.
    """
    capped = _one(
        NEGATIVE,
        False,
        scan=normalise.Scan(TABLE, SEEDED_ROWS, 100_000),
        unexpected_count=D1_NEGATIVE_TOTALS,
    )
    assert capped.magnitude == "150 violating rows · of 100,000 rows scanned · 0.15%", (
        f"the capped run reports {capped.magnitude!r}; 150 of the 100,000 rows it actually read "
        "is 0.15%, and 0.03% would be a share of rows it never saw"
    )
    assert "sampled 100,000 / 500,000" in capped.atom, (
        "the share and the disclosure must name the same denominator, or the screen states two "
        "different sizes of the same table"
    )


def test_offending_values_arrive_with_the_row_they_came_from() -> None:
    """SPEC F13's last clause: `#88231 -450.00`, not `-450.00`.

    The identifier is what turns a statistic into something a domain expert can go
    and look at, and it is why F8 ships `unexpected_index_column_names` at all
    (LT-1a). The framework returns a bare dict per row with nothing marking which key
    is the identity, so the pairing is ours: the rule's own column is the value and
    everything else identifies the row.
    """
    failed = _one(
        NEGATIVE,
        False,
        unexpected_count=D1_NEGATIVE_TOTALS,
        partial_unexpected_list=[-450.0, -12.5],
        partial_unexpected_index_list=[
            {"order_id": 88231, "order_total": -450.0},
            {"order_id": 91002, "order_total": -12.5},
        ],
    )
    assert failed.evidence == ("#88231 -450.0", "#91002 -12.5"), (
        f"the offending rows read {failed.evidence}. Without the identifier nobody can open the "
        "order and decide whether it matters, which is the whole of INV-4."
    )

    unidentified = _one(
        NEGATIVE, False, unexpected_count=2, partial_unexpected_list=[-450.0, -12.5]
    )
    assert unidentified.evidence == ("-450.0", "-12.5"), (
        "a table with no identifier columns still has to show what a wrong row looks like; "
        f"it showed {unidentified.evidence}"
    )

    empty = _one(
        NOT_NULL,
        False,
        unexpected_count=3,
        partial_unexpected_index_list=[{"order_id": 4471, "ship_country": None}],
    )
    assert empty.evidence == ("#4471 (empty)",), (
        f"the rows violating 'Every ship_country has a value' read {empty.evidence}. Printing "
        "the null as None reads as a bug in this product rather than as the defect it found."
    )


def test_aggregate_result_renders_observed_value_versus_expected_range() -> None:
    """The four countless types get the second presentation, and it needs no new field.

    A ColumnAggregate or Batch result carries `{"observed_value": ...}` and no count,
    no percentage and no samples at all (LT-1a) — so the count-and-share reading is
    not merely empty for them, it is inapplicable, and `magnitude` is `None` rather
    than "0 violating rows". What a person compares the observed value against is the
    range, and the range is already rendered inside the rule's own English statement
    by the one formatter that renders it anywhere.

    `expect_column_to_exist` returns `{}` — no observed value either. Its verdict IS
    the whole reading, which is why nothing here is faked into a number.
    """
    mean = _one(MEAN, False, observed_value=812.44)
    assert mean.verdict == "failed" and mean.observed == 812.44
    assert mean.statement == "The average order_total is between 0 and 500", (
        f"the expected range reads {mean.statement!r}; it is what the observed value is judged "
        "against, and it comes from the same formatter every other rule uses"
    )
    assert (mean.unexpected_count, mean.magnitude) == (None, None), (
        f"an aggregate rule reported {mean.magnitude!r}. It counted no rows — reporting zero "
        "violations would read as a clean column, and reporting 0% as a clean table."
    )
    assert mean.evidence == ()
    assert mean.raw["result"]["observed_value"] == 812.44, "the framework's own output is kept"

    exists = _one(EXISTS, False)
    assert exists.statement == "The column order_total exists"
    assert (exists.observed, exists.magnitude, exists.evidence) == (None, None, ())


def test_errored_result_renders_as_errored_not_failed() -> None:
    """The confusion `catch_exceptions` creates, closed on the reading rather than the verdict.

    A rule that could not run arrives as `success: false` with an empty `result`
    (LT-1a), so a normaliser that defaults its count to 0 produces "0 violating rows
    · of 500,000 rows scanned · 0.00%" beside a red badge — a rule that found nothing
    wrong, rendered as a failure. Every number an errored rule could show is absent,
    the atom says so in words, and the reason it could not run is carried instead.
    """
    errored = _one(NEGATIVE, False, KEYED_RAISE)
    failed = _one(
        NEGATIVE, False, unexpected_count=D1_NEGATIVE_TOTALS, partial_unexpected_list=[-450.0]
    )

    assert (errored.magnitude, errored.evidence) == (None, ()), (
        f"the errored rule reads {errored.magnitude!r} with values {errored.evidence}. "
        "It counted nothing, so it has no size and no offending rows to show."
    )
    assert errored.atom == "ERRORED · rule could not run", f"it reads {errored.atom!r}"
    assert errored.detail and "KeyError" in errored.detail
    assert (failed.magnitude, failed.evidence) != (errored.magnitude, errored.evidence), (
        "the two states have to READ differently, not merely carry different verdict strings — "
        "they are byte-identical in the framework's own output"
    )


def test_success_true_with_violations_renders_both_readings() -> None:
    """A green rule beside violating rows is the tolerance its author asked for.

    `mostly` lets a rule succeed with violations (LT-1a measured `success: true`
    alongside `unexpected_count: 25`), and both halves have to survive to the screen:
    the atom stays PASSED because that is the verdict, and the magnitude still states
    the 25, or the pass looks like this product failed to notice them.
    """
    tolerated = _one(
        NEGATIVE,
        True,
        unexpected_count=25,
        partial_unexpected_list=[-1.0],
        partial_unexpected_index_list=[{"order_id": 700, "order_total": -1.0}],
    )
    assert tolerated.atom == "PASSED", f"the verdict reads {tolerated.atom!r}"
    assert tolerated.magnitude == "25 violating rows · of 500,000 rows scanned · 0.01%", (
        f"the tolerated violations read {tolerated.magnitude!r} — a passing rule that hides them "
        "makes the tolerance invisible, and the next person deletes it as dead weight"
    )
    assert tolerated.evidence == ("#700 -1.0",)


def test_the_whole_reading_survives_being_stored_and_read_back() -> None:
    """The record is what a screen renders, so the reading has to be IN it (INV-4).

    A payload carrying only the count and the raw output moves the arithmetic and the
    identifier-pairing into whoever renders it — which is a second reading of the same
    run, in a language the gate does not check. So the composed strings are stored, in
    the same way and for the same reason the status atom is.
    """
    stored = json.loads(
        json.dumps(
            _one(
                NEGATIVE,
                False,
                unexpected_count=D1_NEGATIVE_TOTALS,
                partial_unexpected_list=[-450.0],
                partial_unexpected_index_list=[{"order_id": 88231, "order_total": -450.0}],
            ).record()
        )
    )
    assert stored["magnitude"] == "150 violating rows · of 500,000 rows scanned · 0.03%"
    assert stored["evidence"] == ["#88231 -450.0"]
    assert "proportion" not in stored, (
        f"the stored result carries {stored.get('proportion')!r} beside {stored['magnitude']!r}. "
        "One share, in the sentence — a raw float can disagree with it, because magnitude "
        "renders '<0.01%' where the float would round to zero (app/dq/status.py)."
    )
    assert stored["status"] == "FAILED" and stored["statement"] == "Every order_total is at least 0"
    assert stored["raw"]["result"]["partial_unexpected_index_list"], (
        "the framework's own output is stored alongside the reading, never instead of it — it is "
        "the collapsed panel a person opens when the reading is not enough"
    )
