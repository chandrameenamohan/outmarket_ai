"""F9 · the run record against the real PostgreSQL it ships on, and the real framework.

The half of `tests/test_run_records.py` that no amount of pure Python can answer.
Four claims, and each is the kind only a database (or a real run) can settle:

  THE CACHE IS READ, NOT RE-RUN   a table is executed once and every later page load
                                  reads the record. Proven by COUNTING entries into
                                  the executor — a timer proves nothing here, since a
                                  fast load may still have executed and a slow one may
                                  not have.
  A RE-RUN APPENDS                the second run gets its own id and the first record
                                  reads back exactly as it was written.
  AN UNFINISHED RUN LEAVES IT     a payload assembled mid-stream is refused, and what a
                                  page load renders is still the last completed record.
  THERE IS NO OTHER DOOR          raw UPDATE, DELETE and TRUNCATE against the record
                                  table, on the connection that OWNS it, are refused by
                                  the database rather than by this codebase's manners.
                                  A REVOKE against an owner is a no-op, so the trigger
                                  is the only thing that can do this job.

They WRITE, and the table is append-only by design, so they cannot clean up after
themselves — they write to the GE layer's own scratch schema (`dq_check_ge`,
`tests/scratch.py`) and never to the store the demo reads from, nor to the browser
layer's, which is what lets the two targets run at once (bead dq-cyi.4).

Marked `ge` with the rest of the layer that needs a live database and the framework,
and run by `make check-ge`.
"""

from __future__ import annotations

import threading
from typing import Any

import psycopg2
import pytest

from app.db import system

TABLE = "orders"
SEEDED_ROWS = 500_000

# Two rules aimed at two planted defect classes (seed/MANIFEST.md): 150 negative
# totals (D1) and 240 statuses outside the vocabulary (D3). Deliberately NOT
# `be_unique`, which costs 6.59 s alone (LT-1b) and would buy nothing here — this
# file is about the record, not about the engine.
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
SPECS = [NEGATIVE, IN_SET]


def _modules() -> tuple[Any, Any, Any, Any]:
    """Imported inside the checks: `make check` has neither the framework nor a database."""
    from app.dq import ge_runtime, normalise, run, runs  # noqa: PLC0415

    return ge_runtime, normalise, run, runs


@pytest.mark.ge
def test_page_load_renders_the_cached_record_and_fires_no_execution_request() -> None:
    """The whole point of F9's cache, counted rather than timed.

    One real progressive run against the 500,000-row table, then five reads of the
    kind a page load performs.

    The counter replaces `ge_runtime.run` ITSELF rather than the executor injected
    into `run.stream()`, and that is the difference between this check and a weaker
    one: the injected seam counts only the executions that go through the stream, so
    a cache read that reached the framework by any other route would be invisible to
    it. Nothing else is stubbed — the executor calls through and the store is the
    shipping default — so what is counted is every entry into Great Expectations
    from anywhere, and the verdicts are real ones graded against the planted defects.
    """
    ge_runtime, normalise, run, runs = _modules()
    executions: list[Any] = []
    executor = ge_runtime.run

    def counting(*args: Any, **kwargs: Any) -> Any:
        executions.append(args[0] if args else kwargs.get("name"))
        return executor(*args, **kwargs)

    scan = normalise.Scan(TABLE, SEEDED_ROWS, ge_runtime.ROW_LIMIT)
    ge_runtime.run = counting
    try:
        events = list(run.stream(scan, SPECS))
        stored = events[-1]["record_id"]
        assert len(executions) == len(
            SPECS
        ), f"a progressive run submits one rule at a time; the executor was entered {executions}"
        loads = [runs.latest(TABLE) for _ in range(5)]
    finally:
        ge_runtime.run = executor
    written = runs.find(stored)
    assert written.finished_at is not None, "the database owns the clock; a written row has one"
    assert [r["unexpected_count"] for r in written.results] == [150, 240], (
        f"the record stored {[r['unexpected_count'] for r in written.results]}; seed/MANIFEST.md "
        "plants 150 negative totals (D1) and 240 statuses outside the vocabulary (D3)"
    )
    assert (written.status, written.coverage) == ("failed", 2)

    assert len(executions) == len(SPECS), (
        f"reading the cached record entered the executor {len(executions) - len(SPECS)} extra "
        "times. A page load renders the stored run; re-running is an explicit action (SPEC F9)."
    )
    assert all(load == written for load in loads), (
        "the cached record did not read back as it was written. It is the record of what "
        "happened, so a round trip that changes it is a round trip that rewrites history."
    )
    assert loads[0] is not None and loads[0].results == written.results, (
        "the per-rule readings did not survive the round trip — the statements, counts, sample "
        "values and rendered status atoms are what a page load has to render (INV-4, INV-5)"
    )


@pytest.mark.ge
def test_rerun_creates_a_new_record_id_and_leaves_the_prior_record_intact() -> None:
    """Re-running is an append. The previous record is still exactly the previous record.

    No framework needed: the point is what the STORE does with two completed runs, so
    the second is built from a report that differs from the first. If re-running
    edited a row, the earlier record would come back changed — and it is read back by
    id, through the same door `/runs/[recordId]` will use.
    """
    _, normalise, run, runs = _modules()

    first = runs.save(SPECS, _payload(normalise, run, failing=True))
    second = runs.save(SPECS, _payload(normalise, run, failing=False))

    assert first.record_id != second.record_id, "the re-run overwrote the previous record's id"
    assert (first.status, second.status) == ("failed", "passed")
    assert runs.latest(TABLE) == second, "the newest completed record is what a page load renders"

    assert runs.find(first.record_id) == first, (
        "the earlier record changed when the table was re-run. A run record is a record of what "
        "happened; history that rewrites itself cannot be used to judge anything."
    )
    with pytest.raises(runs.UnknownRun):
        runs.find("00000000-0000-0000-0000-000000000000")


@pytest.mark.ge
def test_an_incomplete_run_writes_no_record() -> None:
    """The streaming half of SPEC F9, against the real store.

    A payload carrying one of the two submitted rules is refused at the door, and the
    assertion that matters is the second one: what a page load sees while that run is
    in flight is the PREVIOUS record, unchanged and complete, rather than a half-filled
    one or nothing at all.
    """
    _, normalise, run, runs = _modules()
    complete = runs.save(SPECS, _payload(normalise, run, failing=True))

    partial = dict(_payload(normalise, run, failing=True))
    partial["results"] = partial["results"][:1]
    with pytest.raises(runs.Incomplete):
        runs.save(SPECS, partial)

    assert runs.latest(TABLE) == complete, (
        "a run still streaming its verdicts changed what a page load renders. Only a completed "
        "run enters the cache — the partial one belongs to the caller that is streaming it."
    )


@pytest.mark.ge
def test_reaching_past_the_record_store_with_raw_sql_is_refused() -> None:
    """The check worth more than every front-door one: a stored run has no edit route.

    Raw SQL on the record store's own connection, as the role that OWNS the table —
    the strongest attacker the role split of SPEC §3.1 leaves standing, and the one
    privilege cannot touch. The trigger refuses all three statements, so "immutable"
    is a property of the database.
    """
    _, normalise, run, runs = _modules()
    written = runs.save(SPECS, _payload(normalise, run, failing=True))

    # Reaching past the front door is the whole point of this check.
    schema = system.schema()
    for statement in (
        f"update {schema}.runs set status = 'passed'",
        f"delete from {schema}.runs",
        f"truncate {schema}.runs",
    ):
        with pytest.raises(psycopg2.Error) as refused, system.cursor(runs.DDL) as cur:
            cur.execute(statement)
        assert "record of what happened" in str(
            refused.value
        ), f"{statement!r} was refused for the wrong reason: {refused.value}"

    assert runs.find(written.record_id) == written, "the record survived, unchanged, as written"


@pytest.mark.ge
def test_concurrent_writers_share_one_connection_without_corrupting_each_other() -> None:
    """The threading hazard `app/api/server.py` actually creates, driven through the REAL store.

    `serve()` is a `ThreadingHTTPServer`, so two concurrent `POST /runs/<table>` land
    in two threads — and both reach the same process-wide system connection, one
    through `runs.save()` at a stream's last line and one through `store.revisions()`
    while planning. psycopg2's `with conn` is a TRANSACTION block whose exit COMMITS,
    so unguarded that is thread B committing thread A's half-written record, and one
    thread's failed statement leaving the other's statements failing inside a
    transaction it never opened.

    The only concurrency check next door injects an in-memory `Ledger()` as the
    store, so the real connection is never driven by two threads at all — which is
    why this one exists and why it uses no fake: what is under test is the
    connection, and a stand-in for it would be testing the stand-in.
    """
    _, normalise, run, runs = _modules()
    from app.rules import store  # noqa: PLC0415

    written: list[Any] = []
    read: list[int] = []
    failures: list[BaseException] = []
    barrier = threading.Barrier(6)

    def writer() -> None:
        barrier.wait()
        written.append(runs.save(SPECS, _payload(normalise, run, failing=True)))

    def reader() -> None:
        barrier.wait()
        read.append(len(store.revisions(table=TABLE)))

    threads = [
        threading.Thread(target=_collect, args=(fn, failures)) for fn in (writer, reader) * 3
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not failures, (
        f"{len(failures)} of 6 concurrent system-database calls raised: "
        f"{[repr(f) for f in failures]}. Two threads on one connection is what the server "
        "does under any real load, and a shared transaction fails in ways that read as "
        "corruption rather than as contention."
    )
    assert len(written) == 3 and len({r.record_id for r in written}) == 3
    assert all(runs.find(r.record_id) == r for r in written), (
        "a record written from one thread did not read back as written. That is the shared "
        "transaction: another thread's commit or rollback landed across this one's INSERT."
    )
    assert read == [read[0]] * 3 and read[0] > 0, (
        f"three concurrent reads of the same table saw {read} revisions. They interleaved "
        "with the writers above, which touch a different table entirely."
    )


def _collect(fn: Any, failures: list[BaseException]) -> None:
    try:
        fn()
    except BaseException as exc:  # noqa: BLE001 — the whole point is that nothing raises
        failures.append(exc)


def _payload(normalise: Any, run: Any, failing: bool) -> dict[str, Any]:
    """A completed run's payload for `SPECS`, without going near the framework or the table."""
    scan = normalise.Scan(TABLE, SEEDED_ROWS)
    report = {
        "success": not failing,
        "results": [
            {
                "success": not failing,
                "expectation_config": {
                    "type": spec["type"],
                    "kwargs": {**spec["kwargs"], "batch_id": "postgres-orders"},
                },
                "result": {"unexpected_count": count if failing else 0},
                "exception_info": {"raised_exception": False, "exception_message": None},
            }
            for spec, count in zip(SPECS, (150, 240), strict=True)
        ],
    }
    return run.completed(scan, normalise.normalise(SPECS, report, scan))
