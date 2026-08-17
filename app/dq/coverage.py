"""F10 · what the engineer's front door is handed: coverage, worst first.

THE SCREEN IS AN ARGUMENT ABOUT ORDER, and this module is where the argument is
made. A database browser lists tables; a coverage dashboard ranks them by how
little is known about them, so the first thing on screen is the thing nobody has
checked. The ranking has two levels and both are here:

  THE BUCKET   what kind of evidence exists at all — none, some but unusable, or a
               real verdict. Derived from the stored run record (F9), never from a
               list of names. `design/ux-variant-workbench.html` files `customers`
               under "never run" while its own results screen holds a running record
               for the same table; that is a defect of a hand-written mockup and it
               is structurally impossible here, because `bucket()` below has nothing
               to consult BUT the record.
  THE SORT     inside a bucket, a table with no accepted rules outranks one with
               rules, and a bigger table outranks a smaller one. SPEC F10 asks for
               the first ("default sort places zero-coverage tables first"); the
               second is the tie-break, and it points the way it does because among
               tables nobody has vouched for, the big one is the larger exposure.

WHY `verified` IS NARROWER THAN `passed`. A run lands in bucket three only if it
scanned the whole table AND every rule it submitted actually reached the data. The
roll-up status alone would not carry that: `_PRECEDENCE` in `app/dq/runs.py` ranks
`failed` above `errored`, so a run where one rule failed and another blew up rolls
up to `failed` — a real verdict with a hole in it. `coverage` is the field that
counts the rules that ran, and comparing it against the number of results is what
keeps a hole out of the bucket labelled "the verdict is real".

WHAT THIS MODULE DOES NOT DO. It words nothing. Every string it emits comes from
`app/dq/status.py` — the atoms through `coverage_atom` / `Record.atom`, the bucket
headings from `BUCKETS`. It also never triggers a run: `runs.latest()` reads the
cache and has no path to the executor, which is what lets the engineer's front door
cost three statements instead of fourteen seconds.

`arrange()` is pure and takes both halves as arguments, so the whole ordering
argument — buckets, tie-breaks, the mockup's defect — is checkable in `make check`
with no database at all. `listing()` is the two-line function that goes and gets
them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.db import tables
from app.dq import runs, status

# The three bucket ids, unpacked from the single list so the derivation below and the
# headings the screen renders can never name different sets.
NEVER_RUN, UNVERIFIABLE, VERIFIED = status.BUCKET_IDS


def bucket(record: runs.Record | None) -> str:
    """Which of the three a table belongs in, decided by its last record and nothing else.

    Three questions in the order that makes each one cheap:

      no record            NEVER RUN. Not "assumed fine", not "probably clean" — the
                           absence of evidence, which is the whole top of the screen.
      a partial scan       UNVERIFIABLE. INV-5's marker, read back off the record where
                           it was stored; what the run saw is not what the table holds.
      a hole in coverage   UNVERIFIABLE. `coverage` counts the rules that reached the
                           data, so anything short of all of them means a rule left no
                           evidence either way. An all-errored run subsumes into this
                           (its coverage is 0), which is why `status == "errored"` is
                           not tested separately — it would be a second, weaker copy
                           of the same question.

    Everything else is VERIFIED: the whole table was read and every rule reported.
    """
    if record is None:
        return NEVER_RUN
    if record.scanned_rows < record.total_rows or record.coverage < len(record.results):
        return UNVERIFIABLE
    return VERIFIED


def row(table: tables.Table, record: runs.Record | None) -> dict[str, Any]:
    """One line of the dashboard: the table, its shape, its coverage, its last verdict.

    `status` occupies one slot whether or not a run exists, and both writers of it are
    in `app/dq/status.py` — `coverage_atom` for a table with no record and the record's
    own atom for one with. That is INV-5 holding at the point it is easiest to lose:
    the sampling clause is INSIDE this string, so a component rendering the slot cannot
    render the verdict and drop the disclosure.

    `rows` is formatted here rather than in the browser for the same reason the atom is:
    the atom's own disclosure clause carries a row count with thousands separators, and a
    row count formatted by a second party in a second language is how "500,000" and
    "500000" end up in adjacent columns of one line.
    """
    return {
        "table": table.name,
        "rows": f"{table.approx_rows:,}",
        "accepted_rules": table.accepted_rules,
        "status": status.coverage_atom(table.accepted_rules) if record is None else record.atom,
        # The verdict travels as a bare NAME, next to the atom that renders it, and is
        # the screen's only handle for styling one differently from another. It is not a
        # second copy of the atom and cannot become one: it is a member of a closed
        # three-value set with no numbers, no punctuation and no disclosure in it, so a
        # component that rendered this instead of `status` would print "failed" and be
        # obviously broken rather than quietly missing a sampling clause.
        "verdict": None if record is None else record.status,
        "record_id": None if record is None else record.record_id,
    }


def arrange(
    found: Iterable[tables.Table], records: Mapping[str, runs.Record | None]
) -> tuple[dict[str, Any], ...]:
    """Every table, bucketed and sorted. Pure: the ordering argument, with no database.

    All three buckets are always returned, empty ones included. An empty bucket is a
    fact the engineer wants — "nothing here is verified" is the loudest thing this
    screen can say — and it is also what makes the DOM order assertable at all: a
    screen that renders only its non-empty buckets can pass an ordering check by
    having one bucket.

    ponytail: one `sorted` per bucket over a list that is the schema's table count.
    No index, no pagination, no secondary sort controls (an explicit non-goal). The
    key is a tuple, so `False < True` puts the zero-rule tables first without a
    comparator. Ceiling: a thousand-table schema renders a thousand rows.
    """
    ordered = sorted(found, key=lambda t: (t.accepted_rules > 0, -t.approx_rows, t.name))
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in status.BUCKET_IDS}
    for table in ordered:
        record = records.get(table.name)
        grouped[bucket(record)].append(row(table, record))
    return tuple({**described, "tables": grouped[described["id"]]} for described in status.BUCKETS)


def listing() -> dict[str, Any]:
    """The whole screen's payload: three buckets, and the sentence that explains the order.

    ponytail: one `runs.latest()` per table, so a schema of N tables costs N+1 round
    trips rather than 2. At the demo's three tables that is ~150 ms against Singapore,
    and the alternative is a `select distinct on (table_name) ... order by table_name,
    finished_at desc` — a second read statement in `app/dq/runs.py` whose only caller
    would be this line. Ceiling: this is the first thing to change if the schema grows,
    and the query above is the change.
    """
    found = tables.tables()
    return {
        "buckets": arrange(found, {table.name: runs.latest(table.name) for table in found}),
        "sort_note": status.SORT_NOTE,
    }
