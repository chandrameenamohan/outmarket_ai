"""F9 · the completed run as a stored record — the half that needs no database.

B15's claim is that a run becomes an IMMUTABLE RECORD which RE-RENDERS WITHOUT
RE-EXECUTING, and three of its four moving parts are checkable offline:

  WHAT ENTERS THE CACHE   only a completed run. A progressive run streams verdicts
                          to its caller (SPEC O-3, `app/dq/run.py`) and the caller
                          holds the partial one; `record()` compares what the run
                          submitted against what reported and refuses the
                          difference. So "a reload mid-run shows the last completed
                          run" is not a race the UI has to win — there is no
                          partial record to find.
  WHAT A STATUS CAN SAY   three terminal values and no `running`. Asserted against
                          `app/dq/status.py` and against the CHECK constraint in
                          `app/dq/runs.sql`, because a value the dataclass allows
                          and the database refuses is an error nobody sees until a
                          user clicks the button.
  WHAT A RECORD CARRIES   INV-4's deterministic half: per rule, the plain-English
                          statement, the size of the problem, real offending values
                          and the rendered status atom — in the stored dict, before
                          any screen exists.

The payloads here are built by `app/dq/run.py::completed()`, the real producer,
rather than typed out: B15 persists exactly what a run says, so a check that
invented its own payload would stop noticing the day the two disagree.

The fourth part — that reading the cache never re-executes — is an import-boundary
claim, so it lives with the rest of INV-3 in
`tests/test_inv3_single_ge_import.py::test_reading_the_run_cache_cannot_reach_the_executor`,
and again in `tests/test_run_records_on_postgres.py` as a count against the real
framework. Both, because the structural check cannot see a call nobody made and the
counting check cannot see a path nobody took.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
from typing import Any

import pytest

from app.dq import normalise, run, runs, status
from conftest import REPO

CACHE = pathlib.Path("app/dq/runs.py")
DDL = pathlib.Path("app/dq/runs.sql")

TABLE = "orders"
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
UNIQUE: dict[str, Any] = {
    "type": "expect_column_values_to_be_unique",
    "kwargs": {"column": "order_reference"},
}
SPECS: list[dict[str, Any]] = [NEGATIVE, IN_SET, UNIQUE]

NOTHING_RAISED = {"raised_exception": False, "exception_message": None}
RAISED = {
    "MetricConfigurationID(metric_name='column_values.unique.condition', ...)": {
        "raised_exception": True,
        "exception_message": "KeyError: 'type'",
    }
}


def reported(spec: dict[str, Any], success: bool, info: Any = None, **body: Any) -> dict[str, Any]:
    """One `results` entry in the shape `to_json_dict()` produces (LT-1a)."""
    return {
        "success": success,
        "expectation_config": {
            "type": spec["type"],
            "kwargs": {**spec["kwargs"], "batch_id": "postgres-orders"},
        },
        "result": body,
        "exception_info": info or NOTHING_RAISED,
    }


def specs_for(*answers: dict[str, Any]) -> list[dict[str, Any]]:
    """The specs a run submitted, recovered from what it reported — minus the provenance kwarg."""
    return [
        {
            "type": answer["expectation_config"]["type"],
            "kwargs": {
                k: v for k, v in answer["expectation_config"]["kwargs"].items() if k != "batch_id"
            },
        }
        for answer in answers
    ]


def payload_for(*answers: dict[str, Any], scan: normalise.Scan = SCAN) -> dict[str, Any]:
    """What a finished run hands its store — built by the real producer, never by hand."""
    report = {"success": False, "results": list(answers)}
    return run.completed(scan, normalise.normalise(specs_for(*answers), report, scan))


ALL_THREE = (
    reported(NEGATIVE, False, unexpected_count=150, partial_unexpected_list=[-450.0, -12.5]),
    reported(IN_SET, False, unexpected_count=240, partial_unexpected_list=["refunded"]),
    reported(UNIQUE, True),
)


def test_only_a_completed_run_can_become_a_record() -> None:
    """SPEC F9's cache clause, as a mechanism rather than as a convention.

    A run streams its verdicts (SPEC O-3), so the interesting moment is the one
    where two of three rules have reported. `record()` is handed what the run
    SUBMITTED alongside the payload built from what has answered, and the
    difference is the refusal — a partial run has no representation here at all,
    which is what makes "a reload mid-run shows the last completed run" true by
    construction rather than by timing. Both directions are asserted: the refusal,
    and the same call succeeding once the third rule lands, or a `record()` that
    refused everything would pass.
    """
    with pytest.raises(runs.Incomplete) as refused:
        runs.record(SPECS, payload_for(*ALL_THREE[:2]))
    assert "2 of 3" in str(refused.value) and UNIQUE["type"] in str(refused.value), (
        f"the refusal reads {str(refused.value)!r}. It has to name how much of the run reported "
        "and which rules did not — INV-4: a failure is readable by whoever has to judge it."
    )

    with pytest.raises(runs.Incomplete):
        runs.record([], payload_for(*ALL_THREE))

    complete = runs.record(SPECS, payload_for(*ALL_THREE))
    assert len(complete.results) == 3 and complete.table == TABLE
    assert (
        complete.finished_at is None
    ), "a record that has not been written has no time; the database owns the clock"


def test_a_run_that_reached_the_table_zero_times_is_an_outage_and_not_a_record() -> None:
    """The cache may not lose its last real answer to a database that went away.

    `app/dq/run.py::_settle` turns every raise into that rule's `errored` verdict,
    which is right per rule — but when the executor is unreachable it fires for ALL
    of them, the generator still reaches its last line, and the record store is a
    different role on a different connection that is very likely still up. Without
    this refusal a total outage writes a complete, honest-looking record with
    coverage 0, and `latest()` hands it to the next page load in place of the last
    run that actually checked something.

    Asserted in both directions: one surviving rule is still a record, because a run
    that checked one of three things has something to say about the table.
    """
    outage = tuple(reported(spec, False, RAISED) for spec in SPECS)
    with pytest.raises(runs.Incomplete) as refused:
        runs.record(SPECS, payload_for(*outage))
    assert "outage" in str(refused.value) and "KeyError" in str(refused.value), (
        f"the refusal reads {str(refused.value)!r}. It has to say the run reached the table "
        "zero times AND carry what raised — otherwise it reads as a bug in the refusal."
    )

    survived = (*outage[:2], reported(UNIQUE, True))
    partial = runs.record(SPECS, payload_for(*survived))
    assert (partial.coverage, partial.status) == (1, "errored")


def test_the_stored_coverage_is_derived_from_the_verdicts_beside_it() -> None:
    """The one number the third state exists to protect is not a field a caller states.

    Everything else in `record()` is cross-checked — the specs against what reported,
    the status recomputed by `_roll_up` — and `coverage` used to be taken verbatim
    from the payload. A hand-assembled payload could therefore store "2 of 2 rules
    checked this table" beside one verdict saying a rule never ran, which is exactly
    the coverage lie `errored` was made a third state to prevent.
    """
    mixed = (reported(NEGATIVE, False, RAISED), reported(IN_SET, True))
    lying = payload_for(*mixed) | {"coverage": 2}
    stored = runs.record(specs_for(*mixed), lying)
    assert stored.coverage == 1, (
        f"a payload claiming coverage 2 over verdicts {[r['verdict'] for r in stored.results]} "
        f"was stored as {stored.coverage}. Coverage is what the verdicts say, not what the "
        "payload says about them."
    )


def test_the_two_rule_identity_functions_agree() -> None:
    """`runs._identity` and `normalise._identity` are copies, pinned rather than shared.

    They compute the completeness comparison in `record()` from both sides — the
    specs a run SUBMITTED go through this module's, and the specs that REPORTED go
    through the normaliser's — so if one side's serialisation ever changes, a
    completed run silently stops matching itself and is refused as partial. Sharing
    one function is not the fix: importing the normaliser would put the rule store,
    the validator and its deferred framework import onto this module's graph, which
    is the property `test_reading_the_cache_cannot_reach_the_executor` above holds.
    Same house rule as `DSN_VAR` in `app/rules/schema.py`: restate, and pin.
    """
    for spec in SPECS:
        assert runs._identity(spec) == normalise._identity(spec), (
            f"the two readings of {spec['type']} disagree. The normaliser's additionally strips "
            f"{normalise.PROVENANCE_KWARG!r}, which our own stored specs never carry — so on "
            "these inputs they are required to be the same string."
        )


def test_the_status_value_set_contains_no_running_value() -> None:
    """A run's status is terminal, in both places that say what a status may be.

    The vocabulary is `app/dq/status.py`'s three verdicts — a run is the roll-up of
    its rules and has no state of its own — and `app/dq/runs.sql` repeats them in a
    CHECK constraint. A `running` value would be the one thing that could put a
    half-finished run in the cache, so its absence is asserted by name rather than
    left as a property of a list nobody reads.
    """
    assert runs.RUN_STATUSES == status.VERDICTS == ("passed", "failed", "errored")

    constraint = re.search(r"check \(status in \(([^)]*)\)\)", (REPO / DDL).read_text())
    assert constraint, "app/dq/runs.sql no longer constrains `status` at the database"
    assert set(re.findall(r"'([a-z_]+)'", constraint.group(1))) == set(runs.RUN_STATUSES), (
        f"the database allows {constraint.group(1)} and the code allows {runs.RUN_STATUSES}. A "
        "status one accepts and the other refuses fails at the INSERT, in front of a user."
    )

    for absent in ("running", "in_progress", "partial", "pending", "queued"):
        assert absent not in runs.RUN_STATUSES
        with pytest.raises(ValueError):
            runs.Record("id", TABLE, absent, SEEDED_ROWS, SEEDED_ROWS, 1, ({"verdict": "passed"},))
    assert not any(absent in status.VERDICTS for absent in ("running", "pending")), (
        "a rule that has not reported renders UNSETTLED_ATOM in the CALLER; it is the absence "
        "of a verdict, and neither it nor a running state ever reaches storage"
    )


def test_a_runs_status_is_the_roll_up_of_the_verdicts_it_recorded() -> None:
    """One run, one status, and the precedence is the interesting part.

    A failure outranks an error because bad data is the louder fact; an error
    outranks a pass because a rule that could not run left a hole, and a run
    reported as `passed` with a hole in it is exactly the coverage lie this product
    exists to not tell. Each case carries at least one passing rule, so a roll-up
    that returned the first verdict it saw could not pass.
    """
    errored = reported(UNIQUE, False, RAISED)
    passed = reported(UNIQUE, True)

    def status_of(*answers: dict[str, Any]) -> str:
        return runs.record(specs_for(*answers), payload_for(*answers)).status

    assert status_of(passed, reported(IN_SET, True)) == "passed"
    assert status_of(errored, reported(IN_SET, True)) == "errored"
    assert status_of(errored, reported(IN_SET, False, unexpected_count=240)) == "failed", (
        "a run with both a failing rule and an errored one is a failing run: the data is bad, "
        "and that is what the person reading the roll-up needs first"
    )
    assert status_of(passed, reported(IN_SET, False, unexpected_count=240)) == "failed"

    mixed = (errored, reported(IN_SET, True))
    covered = runs.record(specs_for(*mixed), payload_for(*mixed))
    assert covered.coverage == 1 and len(covered.results) == 2, (
        f"the record stores coverage {covered.coverage} over {len(covered.results)} rules. An "
        "errored rule is reported and NOT counted — it checked nothing, so counting it would "
        "claim protection the table does not have."
    )


def test_a_record_cannot_be_built_without_the_marker_of_what_it_scanned() -> None:
    """INV-5 at the storage layer: the marker is a required field, not an option.

    The two counts come from the ASSET DEFINITION, carried by `normalise.Scan` from
    the module that built the batch (LT-1a: the framework records nothing that would
    let them be recovered afterwards). Neither has a default, so there is no record
    shape that omits what the run saw — and the disclosure itself is already a
    string inside each stored result, so nothing downstream recomposes it.

    No cap ships at this scale, so what is stored today always says the whole table
    was scanned. The check is on the SHAPE for that exact reason: switching a cap on
    later changes a value and not a schema.
    """
    fields = {f.name: f for f in dataclasses.fields(runs.Record)}
    required = ("scanned_rows", "total_rows")
    assert all(fields[name].default is dataclasses.MISSING for name in required), (
        "the sampling marker acquired a default. A record that can be built without saying what "
        "it scanned is a record that can quietly claim it saw the whole table."
    )
    with pytest.raises(TypeError):
        runs.Record("id", TABLE, "passed")  # type: ignore[call-arg]

    uncapped = runs.record(SPECS, payload_for(*ALL_THREE))
    assert (uncapped.scanned_rows, uncapped.total_rows) == (SEEDED_ROWS, SEEDED_ROWS)
    assert all("sampled" not in r["status"] for r in uncapped.results)

    capped = runs.record(
        SPECS, payload_for(*ALL_THREE, scan=normalise.Scan(TABLE, SEEDED_ROWS, 100_000))
    )
    assert (capped.scanned_rows, capped.total_rows) == (100_000, SEEDED_ROWS)
    assert all("sampled 100,000 / 500,000" in r["status"] for r in capped.results), (
        f"a capped run stored {[r['status'] for r in capped.results]}. The disclosure lives "
        "INSIDE the status token and is stored as a string, so nothing downstream can drop it."
    )


def test_the_stored_record_carries_the_statement_the_count_and_real_values() -> None:
    """INV-4's deterministic half, asserted where the record is actually written.

    A domain expert judging a failure needs three things — what was expected, how
    big the problem is, and what a wrong row looks like — and they have to be in the
    record BEFORE any screen exists, or the screen is where they get invented. The
    raw framework output is kept alongside rather than instead: four of the fifteen
    catalog types carry no count and no samples at all, and the raw panel is what a
    person falls back to when the normalised reading is not enough.
    """
    stored = runs.record(SPECS, payload_for(*ALL_THREE))
    failing = stored.results[0]

    assert failing["statement"] and "order_total" in failing["statement"], (
        f"the stored statement is {failing['statement']!r} — it is the rule in the language it "
        "was written in, not its expectation type"
    )
    assert (failing["verdict"], failing["status"]) == ("failed", "FAILED")
    assert failing["unexpected_count"] == 150, "the size of the problem did not reach the record"
    assert failing["samples"] == [-450.0, -12.5], "the offending values did not reach the record"
    assert failing["raw"]["expectation_config"]["kwargs"]["batch_id"] == "postgres-orders", (
        "the framework's own output is retained separately, whole — including the provenance "
        "kwarg it adds, which is what a raw panel is for"
    )
    assert [r["spec"]["type"] for r in stored.results] == [s["type"] for s in SPECS], (
        "the record stores rules in the order the run submitted them, never the order verdicts "
        "arrived in — otherwise re-running a table reshuffles the screen"
    )
    assert stored.payload()["results"] == [dict(r) for r in stored.results], (
        "what a screen renders is what was stored; a payload that rebuilds anything is a second "
        "reading of the same run"
    )


def test_re_running_appends_a_new_record_and_edits_nothing() -> None:
    """Immutability, in the two places it can be lost: the id, and the SQL.

    Every `record()` call mints its own id, so two runs of one table are two records
    rather than one row that changed its mind — and the database enforces the second
    half, exactly as it does for a rule revision. The live proof is in
    `tests/test_run_records_on_postgres.py`; this is the shape of it.
    """
    first = runs.record(SPECS, payload_for(*ALL_THREE))
    second = runs.record(SPECS, payload_for(*ALL_THREE))
    assert first.record_id != second.record_id, "a re-run reused the previous record's id"

    ddl = (REPO / DDL).read_text()
    assert "before update or delete or truncate" in ddl and "for each statement" in ddl, (
        "app/dq/runs.sql no longer refuses UPDATE/DELETE/TRUNCATE at the database, so 'a run "
        "record is a record of what happened' is a promise about our own code again"
    )
    assert (REPO / CACHE).read_text().lower().count("insert into") == 1, (
        "the record store has more than one INSERT. One writer, reached by every path — the SQL "
        "that could edit a stored row is scanned for across all of app/ by "
        "tests/test_rule_store.py::test_no_mutation_route_exists_for_a_stored_rule_or_run_record."
    )
