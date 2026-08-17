"""F9 · a completed run becomes a record, and the record is what a reload renders.

A run costs 2.28 s for one rule and 13.97 s for the full catalog, and streaming it
costs about 1.6x that total (LT-1b, `app/dq/run.py`). A screen that re-executed on
every load would spend that on every refresh, every back button and every deep
link — and would answer differently each time for reasons that have nothing to do
with the data. So a run that COMPLETES becomes a record, and a page load reads the
record.

THIS MODULE IS THE DURABLE HALF OF THE SEAM `app/dq/run.py` LEAVES OPEN. That
module is the run: a generator that yields a verdict as each rule lands and, from
its last line, hands the completed payload to an injected `Store`. This is that
store — `save(specs, payload)`, wired up as one lambda at the call site, which is
also where the submitted specs are in scope. `run.completed()` decides what a
completed run SAYS; this decides what it means for one to be written down.

FOUR THINGS IN HERE ARE NOT STYLE.

1 · ONLY A COMPLETED RUN ENTERS THE CACHE (SPEC F9). Execution is synchronous but
    progressive (SPEC O-3): verdicts stream to the caller as they land, and the
    half-finished run lives in the CALLER, never here. `save()` therefore takes the
    specs the run SUBMITTED alongside the payload it produced, and compares them
    before anything is written — a run missing a verdict has no representation in
    this module at all. That is a second lock on a door `run.stream()` already
    closes structurally (an abandoned generator never reaches its last line), and
    it is worth having because the two fail differently: theirs covers the run that
    was walked away from, this one covers the caller that assembles a payload by
    hand.
    ponytail, and it is a deliberate ceiling: an interrupted run leaves NO record
    and the previous record stays the most recent. There is no `running` row to
    resume from and none to garbage-collect. Run history is an explicit non-goal,
    so nobody is owed the record of a run that did not finish.

2 · THE STATUS SET IS TERMINAL. A run's status is the roll-up of its rules'
    verdicts, over the same three-value vocabulary as a rule (`app/dq/status.py`),
    which has no `running` value and never will: a rule that has not reported is
    the ABSENCE of a verdict, not a kind of one. `runs.sql` repeats the three in a
    CHECK constraint and the gate fails if the two lists ever disagree.

3 · A RECORD IS NEVER EDITED. Re-running appends a record under a new id and the
    previous one stays readable, exactly as a rule is amended by appending a
    revision (F6). `runs.sql` refuses UPDATE, DELETE and TRUNCATE from every role
    including the one that owns the table, so "immutable" is a property of the
    database rather than of this module's manners.

4 · NOTHING IN A RECORD IS TAKEN ON TRUST, AND AN OUTAGE IS NOT A RECORD. `record()`
    recomputes the status from the verdicts and DERIVES coverage from them too — that
    number is the one thing the `errored` third state exists to protect, so a payload
    does not get to state it beside verdicts that contradict it. And a run in which
    every rule errored reached the table zero times: that is an outage, not a
    description of the data, and storing it would make it the record a page load
    renders in place of the last run that actually checked something.

WHAT THIS MODULE IS NOT: the trigger, the stream or the executor. It imports
nothing that imports the framework, which is what makes "renders without
re-executing" structural rather than careful — there is no path from a page load
through here to Great Expectations, and
`tests/test_inv3_single_ge_import.py::test_reading_the_run_cache_cannot_reach_the_executor`
walks this module's import graph and fails the gate the day one appears — a deferred
import inside a function included. That is also why `_identity` below is a copy rather than an
import of the one in `app/dq/normalise.py`: reaching for it would put the rule
store, the validator and its deferred framework import on this module's graph.

The connection is `app/db/system.py`'s — the same one the rule store writes
through, because it is the same role against the same database, and two of them
was two connects and two `Unavailable` types for one condition.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from psycopg2.extras import Json

from app.db import system
from app.dq import status

DDL = pathlib.Path(__file__).with_name("runs.sql").read_text()

# A run's status vocabulary IS a rule's verdict vocabulary — the run is the roll-up
# of its rules. One source, so there is no second list to drift and the absence of a
# `running` value is inherited rather than restated.
RUN_STATUSES: tuple[str, ...] = status.VERDICTS

# The roll-up, in precedence order. A failure outranks an error because bad data is
# the louder fact; an error outranks a pass because a rule that could not run left a
# hole, and a run reported as `passed` with a hole in it is the coverage lie this
# product exists to not tell.
_PRECEDENCE: tuple[str, ...] = ("failed", "errored", "passed")

_COLUMNS = "record_id, table_name, status, scanned_rows, total_rows, coverage, results, finished_at"

# One statement with two optional filters. Both readers want exactly one row — the
# newest for a table, or this one by id — so the limit is part of the statement
# rather than an argument with one value.
_READ = f"""
    select {_COLUMNS}
      from {{schema}}.runs
     where (%(table)s::text is null or table_name = %(table)s::text)
       and (%(record_id)s::uuid is null or record_id = %(record_id)s::uuid)
     order by finished_at desc, record_id desc
     limit 1
"""

# `finished_at` is the database's to set, so it is read back rather than sent.
_WRITE = """
    insert into {schema}.runs
        (record_id, table_name, status, scanned_rows, total_rows, coverage, results)
    values (%s, %s, %s, %s, %s, %s, %s)
    returning finished_at
"""


class UnknownRun(LookupError):
    """No run record with that id has ever been written here."""


class Incomplete(ValueError):
    """A run that has not finished is not a run record. See point 1 in the module docstring."""


@dataclasses.dataclass(frozen=True)
class Record:
    """One completed run, exactly as it was written. A fact, not a row to be edited.

    The fields are `app/dq/run.py::completed()`'s payload, plus the three things
    only storage can say: the id it was stored under, the roll-up status, and when
    it landed. Nothing is dropped and nothing is recomputed, so what a screen
    renders from the cache is what the run itself produced.

    `scanned_rows` and `total_rows` are INV-5's marker and are required fields with
    no defaults: there is no record shape that omits what the run saw. They are
    carried from the asset definition by the code that built it — Great
    Expectations records nothing that would let them be recovered afterwards
    (LT-1a), so a record that lost them could never get them back.

    `results` are the dicts `app/dq/normalise.py::Result.record()` produces — plain
    JSON with the rendered status atom already inside them, so the disclosure
    survives the round trip as a string and nothing downstream recomposes it.

    `finished_at` is None until the row exists, which is the honest reading of a
    record that has been built and not yet written: the database owns the clock.
    """

    record_id: str
    table: str
    status: str
    scanned_rows: int
    total_rows: int
    coverage: int
    results: tuple[Mapping[str, Any], ...]
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.status not in RUN_STATUSES:
            raise ValueError(
                f"{self.status!r} is not a run status; the three are {RUN_STATUSES}. There is "
                "no running or partial value: a run in flight lives in the caller, and only a "
                "completed run is written down (SPEC F9, O-3)."
            )
        if not self.results:
            raise Incomplete(
                "a run record with no results would report a table as checked while checking "
                "nothing, which is the one result this product may never produce"
            )
        if not 0 <= self.scanned_rows <= self.total_rows:
            raise ValueError(
                f"scanned {self.scanned_rows:,} of a {self.total_rows:,}-row table; the scanned "
                "count is a subset of the total, not a separate measurement (INV-5)"
            )

    @property
    def atom(self) -> str:
        """The run's roll-up verdict as display text, with INV-5's clause welded in.

        Here rather than at the reader, because this is the type that has already
        proven the three numbers agree — `__post_init__` refuses a status outside the
        vocabulary and a scanned count larger than the total, which are exactly the two
        things `status.RuleResult` would otherwise re-check. The `cast` is what that
        proof buys: the string is a `str` on a database row and a `Verdict` by the time
        anything can call this.
        """
        reading = status.RuleResult(
            cast(status.Verdict, self.status), self.scanned_rows, self.total_rows
        )
        return status.status_atom(reading)

    def payload(self) -> dict[str, Any]:
        """The record as the JSON a screen renders — the run's own payload, plus its identity."""
        return {
            "record_id": self.record_id,
            "table": self.table,
            "status": self.status,
            "scanned_rows": self.scanned_rows,
            "total_rows": self.total_rows,
            "coverage": self.coverage,
            "results": [dict(result) for result in self.results],
            "finished_at": None if self.finished_at is None else self.finished_at.isoformat(),
        }


def record(specs: Sequence[Mapping[str, Any]], payload: Mapping[str, Any]) -> Record:
    """A completed run's payload in, the record it will be stored as out — or a refusal.

    `specs` is what the run SUBMITTED (`app/dq/normalise.py::executable()`) and
    `payload` is what `app/dq/run.py::completed()` produced from what reported. The
    comparison between them is the mechanism SPEC F9 asks for: a payload assembled
    while a run is still streaming names fewer rules than the run submitted, and it
    is refused here rather than stored as though the run had finished.

    Pure, so the whole cache clause is checkable in `make check` with no database.
    """
    if not specs:
        raise Incomplete(
            "a run submitted no rules. A record of it would say a table was checked and "
            "report nothing, which reads as a clean table (F6: only accepted rules run)."
        )
    results = list(payload["results"])
    reported = {_identity(result["spec"]) for result in results}
    missing = [spec for spec in specs if _identity(spec) not in reported]
    if missing:
        raise Incomplete(
            f"{len(specs) - len(missing)} of {len(specs)} submitted rules have reported; "
            f"{[spec['type'] for spec in missing]} have not. Only a completed run enters the "
            "cache (SPEC F9) — a partial run belongs to the caller streaming it, and a reload "
            "during one shows the last completed record instead."
        )
    if not (covered := _covered(results)):
        raise Incomplete(
            f"every one of {len(results)} rules errored, so this run reached the table zero "
            "times. That is an outage, not a description of the data — and storing it would "
            "make it the record a page load renders, displacing the last run that did check "
            f"something. Details: {[r.get('detail') for r in results]}"
        )
    return Record(
        record_id=str(uuid.uuid4()),
        table=payload["table"],
        # Derived here, never taken from the payload. It is the one number the third
        # state exists to protect, so it may not be a field a hand-assembled payload
        # gets to state next to verdicts that contradict it.
        coverage=covered,
        status=_roll_up(results),
        scanned_rows=payload["scanned_rows"],
        total_rows=payload["total_rows"],
        results=tuple(results),
    )


def save(specs: Sequence[Mapping[str, Any]], payload: Mapping[str, Any]) -> Record:
    """Write a completed run. The only door to the table, and it opens once per run.

    Building and writing are one call on purpose: a two-step API would leave a
    `Record` a caller could assemble by hand and hand to a writer, and the whole
    point of `record()` is that there is no route past it.

    ponytail: the private writer below is `_insert`, where the rule store calls its
    equivalent `_append`. Not a distinction — that store's closed-writer check greps
    all of `app/` for calls to its own private writer by name, so sharing the name
    would make this module look like a caller reaching into that one.
    """
    return _insert(record(specs, payload))


def latest(table: str) -> Record | None:
    """The cached run a page load renders — the most recent COMPLETED record, or None.

    No execution, ever: this module has no path to the executor (see the module
    docstring). A table that has never been run has no record and says so, rather
    than starting a run in order to have something to show.
    """
    found = _read(table=table)
    return found[0] if found else None


def find(record_id: str) -> Record:
    """One record by id — what `/runs/[recordId]` resolves, and what a re-run leaves alone.

    A string that is not a uuid is an UNKNOWN RUN and not a database error. The id
    arrives from a URL somebody pasted, so the malformed case is ordinary rather than
    exceptional — and without this guard PostgreSQL refuses the `::uuid` cast in
    `_READ`, which reaches the screen as "the server did not answer" instead of as
    "there is no such record". The reader is told the same thing either way, and only
    one of the two is true.
    """
    try:
        uuid.UUID(record_id)
    except ValueError as exc:
        raise UnknownRun(
            f"{record_id!r} is not a run record id, so no record was ever written under it"
        ) from exc
    found = _read(record_id=record_id)
    if not found:
        raise UnknownRun(f"no run record {record_id!r} has ever been written here")
    return found[0]


def _roll_up(results: Sequence[Mapping[str, Any]]) -> str:
    """The run's own status: the loudest verdict among its rules, by `_PRECEDENCE`."""
    verdicts = {result["verdict"] for result in results}
    return next(verdict for verdict in _PRECEDENCE if verdict in verdicts)


def _covered(results: Sequence[Mapping[str, Any]]) -> int:
    """How many rules actually checked the data — `app/dq/normalise.py::coverage`, on dicts."""
    return sum(1 for result in results if result["verdict"] != "errored")


def _identity(spec: Mapping[str, Any]) -> str:
    """A rule's identity within one run: its type and its kwargs, as a comparable key.

    A string because kwargs hold lists (`value_set`), which are not hashable, and
    `sort_keys` makes it independent of dict ordering on both sides.

    A copy of `app/dq/normalise.py`'s, restated rather than imported for the reason
    the module docstring gives — importing it would drag the store, the validator and
    a deferred framework import onto this module's graph, which is the one property
    `tests/test_run_records.py::test_reading_the_cache_cannot_reach_the_executor`
    exists to hold. Same house rule as `DSN_VAR` in `app/rules/schema.py`: restated,
    and pinned to its twin by a check
    (`tests/test_run_records.py::test_the_two_rule_identity_functions_agree`), because
    the two sides of `record()`'s completeness comparison are produced by both.
    """
    return json.dumps([spec["type"], spec["kwargs"]], sort_keys=True, default=str)


def _insert(written: Record) -> Record:
    """The only INSERT. A record is written exactly once; the primary key says so."""
    with system.cursor(DDL) as cur:
        cur.execute(
            system.sql(_WRITE),
            (
                written.record_id,
                written.table,
                written.status,
                written.scanned_rows,
                written.total_rows,
                written.coverage,
                Json([dict(result) for result in written.results]),
            ),
        )
        (finished_at,) = cur.fetchone()
    return dataclasses.replace(written, finished_at=finished_at)


def _read(table: str | None = None, record_id: str | None = None) -> tuple[Record, ...]:
    with system.cursor(DDL) as cur:
        cur.execute(system.sql(_READ), {"table": table, "record_id": record_id})
        return tuple(_row(row) for row in cur.fetchall())


def _row(row: Sequence[Any]) -> Record:
    """One database row back into the record that was written, marker and all."""
    return Record(
        record_id=str(row[0]),
        table=row[1],
        status=row[2],
        scanned_rows=row[3],
        total_rows=row[4],
        coverage=row[5],
        results=tuple(row[6]),
        finished_at=row[7],
    )
