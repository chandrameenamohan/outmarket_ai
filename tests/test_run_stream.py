"""F8 · a run is triggered, and its verdicts are watched arriving one at a time.

The observable acceptance is what a CALLER SEES, so that is what is asserted: the
rule list before the first rule runs, a verdict per rule as it lands rather than a
block at the end, a rule that dies without taking the run with it, and a record that
exists only if the run finished. Nothing here asserts a clock. LT-1b measured 8.3%
drift inside one run on a burstable free tier, and VERIFICATION.md §9.1 records the
decision that a latency threshold in this gate would teach everyone that red means
re-run it. Ordering is asserted against a fake executor, which is deterministic.

THE FAKE EXECUTOR IS THE POINT, not a shortcut. `app/dq/run.py` holds no connection,
no framework import and no SQL, so every shape check below runs inside `make check`
with no network — including the transport one, which drives a real socket against a
real handler and never reaches a database. The `ge` layer at the bottom then runs the
same path against the live 500,000-row table.

WHAT IS CHECKED NEXT DOOR AND NOT REPEATED HERE: which rules a run submits and the
asset it builds (`tests/test_rule_execution.py`), the reading of a report
(`tests/test_result_normalisation.py`), that no shipping path builds a capped asset
(`tests/test_inv5_sampling_disclosure.py::test_no_shipping_code_path_constructs_a_capped_asset`),
and that nothing outside the runtime creates a context
(`tests/test_inv3_single_ge_import.py`, half C — which already covers every request
handler in `app/`, so the check this bead names would have been a fourth copy).
"""

from __future__ import annotations

import json
import pathlib
import threading
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from app.db import system
from app.dq import normalise, run, runs, status

TABLE = "orders"
SEEDED_ROWS = 500_000

# No cap ships (SPEC O-2), so the whole table is scanned and nothing is a sample.
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
SPECS = [NEGATIVE, IN_SET, UNIQUE]

SERVER = pathlib.Path("app/api/server.py")


class Recorder:
    """A stand-in for the framework that records the order it was asked things in.

    `raises_at` makes one rule's SUBMISSION blow up — the failure `catch_exceptions`
    cannot catch, because it happens before the framework has a report to catch it in.
    """

    def __init__(self, raises_at: int | None = None) -> None:
        self.submitted: list[str] = []
        self.raises_at = raises_at

    def __call__(
        self,
        name: str,
        specs: Sequence[Mapping[str, Any]],
        table: str,
        identifiers: Sequence[str],
    ) -> Mapping[str, Any]:
        self.submitted.append(specs[0]["kwargs"]["column"])
        if self.raises_at is not None and len(self.submitted) == self.raises_at:
            raise RuntimeError("the connection dropped mid-run")
        return {
            "success": True,
            "suite_name": name,
            "results": [
                {
                    "success": True,
                    "expectation_config": {
                        "type": specs[0]["type"],
                        "kwargs": {**specs[0]["kwargs"], "batch_id": "postgres-orders"},
                    },
                    "result": {"element_count": SEEDED_ROWS, "unexpected_count": 0},
                    "exception_info": {"raised_exception": False, "exception_message": None},
                }
            ],
        }


class Ledger:
    """A stand-in for the INSERT in B15's record store, and for nothing else.

    `runs.record()` is pure — it shapes the record and refuses an incomplete one without
    touching the database — so a fake that delegates to it exercises the real record and
    skips only the INSERT. It counts, so "exactly once" is checkable.
    """

    def __init__(self) -> None:
        self.written: list[runs.Record] = []

    def __call__(
        self, specs: Sequence[Mapping[str, Any]], payload: Mapping[str, Any]
    ) -> runs.Record:
        self.written.append(runs.record(specs, payload))
        return self.written[-1]


def _events(**kwargs: Any) -> list[dict[str, Any]]:
    ledger = kwargs.pop("store", Ledger())
    return list(run.stream(SCAN, SPECS, store=ledger, execute=kwargs.pop("execute", Recorder())))


def test_the_first_event_lists_every_rule_before_any_of_them_runs() -> None:
    """The blank spinner is not discouraged here, it is unrepresentable.

    The stream's first event carries a row for every accepted rule, each already
    wearing the pending text, and it is emitted before the executor is asked for
    anything. A screen driven by this stream cannot render an empty waiting state
    because the stream never describes one — which is the whole of SPEC F8's "no
    rendering may be a blank spinner for the duration of the run".

    The pending text is asserted to be the single writer's constant rather than any
    string that looks like it: a second spelling of "pending" is a second author of a
    load-bearing sentence (INV-5's sibling argument, `app/dq/status.py`).
    """
    executor = Recorder()
    events = run.stream(SCAN, SPECS, store=Ledger(), execute=executor)
    first = next(events)

    assert executor.submitted == [], (
        f"{executor.submitted} ran before the caller was told what would run. The rule list "
        "has to be on screen before the first rule costs anything, or the first seconds are "
        "a blank wait however the client renders them."
    )
    assert first["event"] == run.STARTED
    assert [r["statement"] for r in first["rules"]] == [
        "Every order_total is at least 0",
        "Every status is one of pending, paid, shipped, delivered, cancelled, returned",
        "No two rows share a order_reference",
    ], f"the list reads {[r['statement'] for r in first['rules']]}"
    assert {r["status"] for r in first["rules"]} == {status.UNSETTLED_ATOM}, (
        "a not-yet-reported rule must carry the single writer's pending text; anything else "
        "is a second author of a verdict-shaped string"
    )
    assert (first["reported"], first["total"]) == (0, 3), (
        "every event states how many of how many rules have reported — that pair is what "
        "makes a partial run identifiable as partial, and it starts at none of them"
    )
    events.close()


def test_each_verdict_is_emitted_as_it_lands_not_after_the_last_one() -> None:
    """Progressive, asserted as ordering rather than as timing.

    Drive the generator one event at a time and check, at each step, that exactly as
    many rules have been submitted to the executor as have reported back. A run that
    executed everything and then yielded the verdicts would show 3 submissions before
    the first verdict — the failure this rules out, and the one a stopwatch could only
    guess at on a burstable free tier (VERIFICATION.md §9.1).
    """
    executor = Recorder()
    events = run.stream(SCAN, SPECS, store=Ledger(), execute=executor)
    next(events)

    for expected in (1, 2, 3):
        event = next(events)
        assert event["event"] == run.VERDICT
        assert len(executor.submitted) == expected, (
            f"{len(executor.submitted)} rules had run when verdict {expected} arrived. The "
            "caller must see each verdict as it lands, not the whole run at the end."
        )
        assert event["reported"] == expected and event["total"] == 3
        assert event["result"]["status"] == "PASSED", event["result"]["status"]

    assert next(events)["event"] == run.COMPLETED
    events.close()


def test_an_errored_rule_does_not_abort_the_rules_after_it() -> None:
    """A rule that dies is one verdict, never the end of the run.

    The framework's own `catch_exceptions` handles a rule that fails INSIDE a report
    (LT-1a). This is the other half: the submission itself raising — a spec that
    stopped compiling, a connection dropped mid-run — which arrives with no report at
    all. It must still be `errored` and never `failed`: the two mean different things
    to a domain expert, and coverage counts one of them.
    """
    events = _events(execute=Recorder(raises_at=2))
    verdicts = [e for e in events if e["event"] == run.VERDICT]

    assert len(verdicts) == 3, (
        f"{len(verdicts)} of 3 rules reported. A rule that could not run must not silently "
        "shorten the run — the rules after it are the coverage nobody would notice missing."
    )
    assert [v["result"]["verdict"] for v in verdicts] == ["passed", "errored", "passed"]
    assert verdicts[1]["result"]["status"] == "ERRORED · rule could not run"
    assert "the connection dropped mid-run" in verdicts[1]["result"]["detail"]
    assert (
        verdicts[1]["result"]["unexpected_count"] is None
    ), "an errored rule has no violating count; a zero there reads as a clean column"
    assert events[-1]["coverage"] == 2, (
        f"coverage reported {events[-1]['coverage']} of 3. A rule that did not run did not "
        "check the data, and counting it inflates what this product claims to have checked."
    )


def test_terminal_event_carries_the_stored_record_id() -> None:
    """One completed run, one record, and the id is how a caller gets back to it."""
    ledger = Ledger()
    events = _events(store=ledger)

    assert events[-1]["event"] == run.COMPLETED
    assert len(ledger.written) == 1, f"{len(ledger.written)} records written for one run"
    stored = ledger.written[0]
    assert events[-1]["record_id"] == stored.record_id, (
        "the terminal event names a record nobody wrote; it is the only handle a caller "
        "has on the run it just watched"
    )
    assert [r["statement"] for r in stored.results] == [
        v["result"]["statement"] for v in events if v["event"] == run.VERDICT
    ], "the stored record and the streamed verdicts must be the same run, in the same order"
    assert (stored.scanned_rows, stored.total_rows) == (SEEDED_ROWS, SEEDED_ROWS)
    assert not any(r["sampled"] for r in stored.results), "no cap ships (SPEC O-2)"


def test_a_run_that_could_not_be_stored_still_ends_with_a_terminal_event() -> None:
    """A finished run and a dropped connection must not look the same on the wire.

    The store's two refusals are ordinary outcomes at the generator's last line: the
    record store unreachable, and a run in which every rule errored (`app/dq/runs.py`
    refuses that one so an outage cannot displace the last real record). Letting
    either escape ends the response after the final verdict with no terminal frame,
    after a 200 and every header has already gone out — which a browser cannot tell
    from the server dying at rule 7. So `record_id` is None, the store's own sentence
    rides in `detail`, and every verdict before it is still real and still correct.
    """

    def refuses(specs: Sequence[Mapping[str, Any]], payload: Mapping[str, Any]) -> runs.Record:
        raise system.Unavailable("SUPABASE_DB_URL_SYSTEM did not answer: no route to host")

    events = _events(store=refuses)
    verdicts = [e for e in events if e["event"] == run.VERDICT]

    assert len(verdicts) == 3 and all(v["result"]["verdict"] == "passed" for v in verdicts), (
        "the run itself has to be unaffected — the verdicts landed, and only writing them "
        f"down failed; got {[v['result']['verdict'] for v in verdicts]}"
    )
    assert events[-1]["event"] == run.COMPLETED, (
        f"the stream ended on {events[-1]['event']!r}. Without a terminal frame the caller "
        "cannot distinguish a completed run from a connection that died mid-run."
    )
    assert events[-1]["record_id"] is None and events[-1]["coverage"] == 3
    assert "not saved" in events[-1]["detail"] and "no route to host" in events[-1]["detail"], (
        f"the terminal event reads {events[-1]['detail']!r}. It has to say the run finished "
        "AND that the result was not saved, or the missing id reads as a bug (INV-4)."
    )
    assert _events()[-1]["detail"] is None, "a run that WAS stored must carry no failure detail"


def test_an_interrupted_stream_stores_no_record() -> None:
    """Only a completed run enters the store, and abandoning the generator is the proof.

    The caller walks away after one verdict. Nothing is stored — not a partial record,
    not an empty one — so a reload still shows the previous completed run (SPEC F9).
    The mechanism is that `store` is called from the generator's last line, so this is
    not a rule somebody has to remember: an abandoned run never reaches it.
    """
    ledger = Ledger()
    events = run.stream(SCAN, SPECS, store=ledger, execute=Recorder())
    next(events)
    next(events)
    events.close()

    assert ledger.written == [], (
        f"{len(ledger.written)} records written by a run that was abandoned at rule 1 of 3. "
        "A partial run lives in the caller and never in the store."
    )


@pytest.mark.ge
def test_run_against_seeded_orders_streams_a_verdict_per_accepted_rule_and_stores_one_record() -> (
    None
):
    """The acceptance, against the live 500,000-row table, through the shipping path.

    Everything the bead promises in one pass: the rule list arrives before any rule
    runs, each verdict lands on its own, the terminal event carries the id of the one
    record stored, and `element_count` equals the full row count in `seed/MANIFEST.md`
    — so the run really did see the whole table and no cap engaged. No wall-clock
    assertion: what is checked is that the verdicts arrive separately, not when.
    """
    from app.rules import schema as live  # noqa: PLC0415

    ledger = Ledger()
    scan = normalise.Scan(TABLE, SEEDED_ROWS, _row_limit())
    events = list(run.stream(scan, SPECS, live.primary_key(TABLE), store=ledger))

    assert [e["event"] for e in events] == [run.STARTED] + [run.VERDICT] * 3 + [run.COMPLETED]
    verdicts = [e for e in events if e["event"] == run.VERDICT]
    assert [v["result"]["verdict"] for v in verdicts] == ["failed", "failed", "failed"], (
        f"{[(v['result']['verdict'], v['result']['detail']) for v in verdicts]} "
        "— every one of these rules is aimed at a planted defect (seed/MANIFEST.md), and an "
        "errored rule is byte-identical to a failing one in the framework's own output"
    )
    assert [v["reported"] for v in verdicts] == [1, 2, 3]

    scanned = {v["result"]["raw"]["result"]["element_count"] for v in verdicts}
    assert scanned == {SEEDED_ROWS}, (
        f"the run reports {scanned} rows scanned against the {SEEDED_ROWS:,} in "
        "seed/MANIFEST.md. No cap ships (SPEC O-2), so anything else means one engaged."
    )
    assert not any(v["result"]["sampled"] for v in verdicts)
    assert "sampled" not in " ".join(
        v["result"]["status"] for v in verdicts
    ), "an uncapped run must not cry wolf: the disclosure ships, the cap does not"

    assert len(ledger.written) == 1
    assert events[-1]["record_id"] == ledger.written[0].record_id
    stored = json.loads(json.dumps(ledger.written[0].payload()))
    assert stored["results"][0]["raw"]["expectation_config"], (
        "the framework's own output must survive being stored beside the reading of it — it "
        "is the panel a person opens when the reading is not enough (INV-4)"
    )


@pytest.mark.ge
def test_two_concurrent_runs_do_not_orphan_each_others_datasource() -> None:
    """The LT-1b trap, exercised rather than described.

    `gx.get_context()` installs a PROCESS-GLOBAL project, so a second context orphans
    the first one's datasources — and the failure surfaces much later, at validate(),
    as a DatasourceError naming a datasource that is sitting right there. Two runs in
    flight is the arrangement that would trigger it, so two runs in flight is what this
    drives: both must produce the same verdict, with no errored rule between them.
    """
    from app.rules import schema as live  # noqa: PLC0415

    scan = normalise.Scan(TABLE, SEEDED_ROWS, _row_limit())
    identifiers = live.primary_key(TABLE)
    outcomes: dict[int, list[dict[str, Any]]] = {}

    def go(slot: int) -> None:
        outcomes[slot] = list(run.stream(scan, [NEGATIVE], identifiers, store=Ledger()))

    threads = [threading.Thread(target=go, args=(slot,)) for slot in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert sorted(outcomes) == [0, 1], f"only {sorted(outcomes)} finished"
    verdicts = [events[1]["result"] for events in outcomes.values()]
    assert [v["verdict"] for v in verdicts] == ["failed", "failed"], (
        f"{[(v['verdict'], v['detail']) for v in verdicts]} — a DatasourceError naming a "
        "datasource that is present is the orphaned-context failure, not a data problem"
    )
    assert verdicts[0]["unexpected_count"] == verdicts[1]["unexpected_count"] == 150


def _row_limit() -> int | None:
    """INV-5's marker at its origin, carried by the caller as the shipping path does."""
    from app.dq import ge_runtime  # noqa: PLC0415

    return ge_runtime.ROW_LIMIT
