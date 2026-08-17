"""F8 · the trigger, and the verdicts a caller watches arrive one at a time.

A RUN IS A GENERATOR. An explicit action starts one, it yields an event per rule as
that rule lands, and its last event carries the id of the single record the completed
run stored. There is no job id, no 202, no polling endpoint and no worker — SPEC O-3,
settled by LT-1b: the cost is a floor plus a lumpy per-rule increment paid as
independent statements, so a queue returns the same total later and adds a staleness
problem to it. A generator is the smallest thing that is honestly progressive; the
transport that carries it to a browser is `app/api/server.py`, and it is the only
thing that would change if the answer to SPEC O-4 ever changed.

FOUR THINGS IN HERE ARE NOT STYLE.

1 · THE FIRST EVENT IS THE WHOLE RULE LIST, AND IT IS EMITTED BEFORE ANY RULE RUNS.
    That is the mechanism that makes a blank spinner impossible rather than
    discouraged: from the first line of the response the caller already has a row per
    accepted rule, each carrying `status.UNSETTLED_ATOM`, and every later event
    replaces one of them. A screen cannot render an empty waiting state from this
    stream because the stream never describes one. The pending text comes from the
    single writer (`app/dq/status.py`) and rides in the payload, so `web/` still never
    composes a verdict of any kind.

2 · ONE VALIDATE PER RULE, AND IT IS NOT FREE. The framework returns a suite's
    results only when the whole suite is done, so streaming means submitting each
    rule on its own — which loses the metric-graph sharing a single suite gets.
    Measured on the live 500,000-row `orders` table, three rules, direct connection,
    warm process: one validate of all three costs **7.94 s** and the caller sees
    nothing until 7.94 s; three validates of one rule each cost **12.64 s** and the
    first verdict lands at **2.98 s**. So progressive costs about **1.6x the total**
    and buys the first verdict **2.7x sooner**. LT-1b's suite-size table is why that
    trade is taken and not the reverse: the total was already past the ten-second bar
    where a spinner stops being honest, and no arrangement of these statements brings
    it back under. SPEC F8's phrase "at no cost in total time" describes the wait, not
    the sum; the sum is here, measured, so nobody has to rediscover it.

3 · A RULE THAT RAISES DOES NOT END THE RUN. `catch_exceptions` turns a rule's own
    failure into an `errored` result inside the report (LT-1a), but the CALL can still
    raise — a spec that stopped compiling after an upgrade, a connection dropped
    mid-run. Each rule is therefore submitted inside its own attempt, and a raise
    becomes that rule's `errored` verdict rather than the end of everyone else's.
    `errored` is a third state, never a kind of failure: it is a coverage fact, and
    `normalise.coverage()` excludes it.

4 · ONLY A COMPLETED RUN IS STORED, AND THE TERMINAL EVENT ARRIVES EITHER WAY. The
    writer is called once, from the generator's LAST LINE — so a caller that walks
    away mid-run leaves no record at all and a reload shows the previous one (SPEC
    F9). That is not a rule somebody has to remember: an abandoned generator never
    reaches the line, and `app/dq/runs.py` refuses a record whose results do not
    cover its specs, and refuses a run in which every rule errored (that is an
    outage, not a description of the data). Both refusals are EXPECTED at this line,
    which is why the store call is wrapped: a stream that ended after the last
    verdict with no terminal event is byte-indistinguishable from a dropped
    connection, so `record_id` goes out as None with the store's own sentence beside
    it. Every verdict has already been yielded and is correct; what the caller
    learns is that the run finished and was not saved. Deliberate ceiling: the
    partial run lives in the caller and nowhere else, so a browser closed at rule 4
    of 10 has thrown away four real verdicts. The upgrade path is a record with a
    non-terminal status, which SPEC F9 and B15 both currently refuse.

WHAT THIS MODULE IS NOT: the thing that decides WHICH rules run (`normalise.executable`),
the thing that reads a report (`normalise.normalise`), the thing that shapes or writes
the record (`app/dq/runs.py`), or the thing that speaks HTTP (`app/api/server.py`). It
OPENS no connection, imports no framework and holds no SQL of its own, which is why
every check on its shape runs inside `make check` with no network at all. The one thing
it takes from `app/db/system.py` is an exception TYPE, so that the terminal event above
can name the store's failure without guessing at it from a base class.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping, Sequence
from typing import Any

from app.db import system
from app.dq import normalise, runs, status
from app.rules import catalog

# One line of the stream. Plain data — `json.dumps`-able as it stands, because the
# transport's only job is framing.
Event = dict[str, Any]

# `(suite_name, specs, table, identifiers) -> the framework's raw report`. Injected so
# every shape check in this file runs offline: the default reaches the one module that
# imports the framework, and it is imported inside the call rather than at the top,
# because importing this module must never cost a framework import.
Executor = Callable[[str, Sequence[Mapping[str, Any]], str, Sequence[str]], Mapping[str, Any]]

# `(the rules the run submitted, the completed run's payload) -> the written record`.
# The default IS the real writer; it is a parameter only so the ordering checks below can
# run with no database. Both arguments are passed because `app/dq/runs.py` compares them:
# a payload naming fewer rules than the run submitted is a run still in flight, and it is
# refused there rather than stored as though it had finished.
Store = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any]], runs.Record]

STARTED, VERDICT, COMPLETED = "started", "verdict", "completed"


def _framework(
    name: str, specs: Sequence[Mapping[str, Any]], table: str, identifiers: Sequence[str]
) -> Mapping[str, Any]:
    """The shipping executor. The import is deferred so `make check` can load this file."""
    from app.dq import ge_runtime

    return ge_runtime.run(
        name, [dict(spec) for spec in specs], table=table, identifiers=identifiers
    )


def stream(
    scan: normalise.Scan,
    specs: Sequence[Mapping[str, Any]],
    identifiers: Sequence[str] = (),
    store: Store = runs.save,
    execute: Executor = _framework,
) -> Generator[Event, None, None]:
    """Run every spec against `scan.table`, yielding each verdict the moment it lands.

    `scan` is the run's whole account of what it saw, and it arrives from the CALLER
    because it carries INV-5's marker: the row limit is a property of the asset
    definition (`app/dq/ge_runtime.py::ROW_LIMIT`) and the framework records nothing
    that would let it be recovered afterwards (LT-1a).

    The caller supplies `specs` already folded to the accepted set
    (`normalise.executable`) and `identifiers` already read off the live schema, for
    the same reason `ge_runtime.run` takes a resolved table: this module never touches
    the database, so it is in no position to check either.

    The last event carries the id of the ONE record the completed run wrote. It is the
    last line of the generator on purpose — see point 4 in the module docstring.
    """
    yield {
        "event": STARTED,
        "table": scan.table,
        "total": len(specs),
        "reported": 0,
        "rules": [
            {
                "index": index,
                "statement": catalog.english(spec["type"], spec["kwargs"]),
                "status": status.UNSETTLED_ATOM,
            }
            for index, spec in enumerate(specs)
        ],
    }

    results: list[normalise.Result] = []
    for index, spec in enumerate(specs):
        results.append(_settle(scan, spec, index, identifiers, execute))
        yield {
            "event": VERDICT,
            "index": index,
            "total": len(specs),
            "reported": len(results),
            "result": results[-1].record(),
        }

    record_id, detail = _stored(store, specs, completed(scan, results))
    yield {
        "event": COMPLETED,
        "table": scan.table,
        "total": len(specs),
        "reported": len(results),
        "coverage": normalise.coverage(results),
        "record_id": record_id,
        "detail": detail,
    }


def completed(scan: normalise.Scan, results: Sequence[normalise.Result]) -> dict[str, Any]:
    """The payload of the ONE record a finished run stores. Plain data, all the way down.

    Named and public because `app/dq/runs.py` is built around it: B15 turns exactly this
    into the stored record, and B16 renders that back without re-executing. `coverage` is
    computed here rather than on read for the reason the number exists at all — an
    errored rule is excluded from it, and a reader recomputing it from the rows would
    have to know that too.
    """
    return {
        "table": scan.table,
        "scanned_rows": scan.scanned_rows,
        "total_rows": scan.total_rows,
        "coverage": normalise.coverage(results),
        "results": [result.record() for result in results],
    }


def _stored(
    store: Store, specs: Sequence[Mapping[str, Any]], payload: Mapping[str, Any]
) -> tuple[str | None, str | None]:
    """`(record_id, None)` if the run was written down, `(None, why not)` if it was not.

    The two refusals are `app/dq/runs.py`'s own and both are ordinary outcomes here —
    a record store that cannot be reached, and a run in which every rule errored. See
    point 4 in the module docstring for why they may not escape: the terminal event is
    the only thing that distinguishes a finished run from a dropped connection.
    """
    try:
        return store(specs, payload).record_id, None
    except (system.Unavailable, runs.Incomplete) as exc:
        return None, f"the run finished; the result was not saved. {exc}"


def _settle(
    scan: normalise.Scan,
    spec: Mapping[str, Any],
    index: int,
    identifiers: Sequence[str],
    execute: Executor,
) -> normalise.Result:
    """One rule, submitted alone, and never allowed to take the rest of the run with it."""
    try:
        report = execute(f"{scan.table} rule {index + 1}", [spec], scan.table, identifiers)
        return normalise.normalise([spec], report, scan)[0]
    except Exception as exc:  # deliberate and broad — see point 3 in the module docstring
        return _unreported(scan, spec, exc)


def _unreported(scan: normalise.Scan, spec: Mapping[str, Any], exc: Exception) -> normalise.Result:
    """The verdict for a rule whose submission never came back with a report at all.

    Built here rather than in `app/dq/normalise.py` because there is nothing to
    normalise: the framework said nothing. It is the same third state a rule reaches
    when the framework catches the error internally, and it renders identically —
    which is the point, since a domain expert should not have to know which side of
    the boundary a rule died on.
    """
    return normalise.Result(
        statement=catalog.english(spec["type"], spec["kwargs"]),
        spec={"type": spec["type"], "kwargs": dict(spec["kwargs"])},
        verdict="errored",
        unexpected_count=None,
        samples=(),
        identified=(),
        observed=None,
        detail=f"{type(exc).__name__}: {exc}",
        scan=scan,
        raw={},
    )
