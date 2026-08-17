"""F10 · the ordering argument, checked with no database and no browser.

The Table Explorer's whole claim is that its ORDER is derived rather than typed —
which bucket a table is in comes from its stored run record, and where it sits
inside that bucket comes from its rule count. `app/dq/coverage.py::arrange` is pure
precisely so those two claims are checkable here, in the layer that runs on every
save, instead of only in the browser layer that needs two processes and a database.

THE DEFECT THESE CHECKS EXIST TO MAKE IMPOSSIBLE has a name and a screenshot:
`design/ux-variant-workbench.html` files `customers` under "1 · Never run" on its
F10 screen while its own F13 screen holds a run record for that same table. That is
what a hand-written bucket looks like, and the last check below is the one that
would go red if the bucket ever stopped being a function of the record.

The records here are built through `app/dq/runs.py::record()` — the same function
`save()` calls — rather than by constructing `Record` directly. It derives the
roll-up status and the coverage count from the verdicts, so these fixtures cannot
state a combination the product could never produce.
"""

from __future__ import annotations

from app.db import tables
from app.dq import coverage, runs, status
from conftest import completed_run

TABLE = "orders"
ROWS = 500_000


def _record(*verdicts: str, scanned: int = ROWS, table: str = TABLE) -> runs.Record:
    """A completed run over `conftest.RUN_SPECS`, one verdict each, built as a real one is.

    The payload shape is `conftest.completed_run`'s so that the browser layer, which
    WRITES records of exactly this shape into the scratch schema to give F10's buckets
    something true to render, and these offline checks cannot drift apart.
    """
    return runs.record(*completed_run(table, verdicts, scanned, ROWS))


def _table(name: str, *, rules: int = 0, rows: int = ROWS) -> tables.Table:
    return tables.Table(name=name, columns={"id": "bigint"}, approx_rows=rows, accepted_rules=rules)


def test_bucket_assignment_derives_from_the_record_status() -> None:
    """Every bucket is a function of the record — including the two easy ones to lose.

    The four cases that matter, and what each would look like if it were wrong:

      no record            NEVER RUN. The mockup's defect is exactly this cell filled
                           in by hand, so it is asserted from the other side too, below.
      a partial scan       UNVERIFIABLE even though every rule passed. A sampled PASSED
                           is the most dangerous row on this screen: it reads as a clean
                           table and is a statement about the rows that were looked at.
      an errored rule      UNVERIFIABLE. `catch_exceptions` makes an errored rule
                           byte-identical to a failing one (LT-1a), which is why the
                           third state exists at all.
      a FAILED run with a  UNVERIFIABLE — and this is the case a status-only check
      hole in it           misses. `_PRECEDENCE` ranks `failed` above `errored`, so a run
                           where one rule failed and another blew up rolls up to
                           `failed`; reading the status alone would file it under
                           "the verdict is real" with a rule missing from it.
    """
    assert coverage.bucket(None) == coverage.NEVER_RUN, (
        "a table with no run record is the top of this screen. Anything else means the "
        "absence of evidence is being rendered as a kind of evidence."
    )

    sampled = _record("passed", "passed", scanned=100_000)
    assert sampled.status == "passed" and sampled.coverage == 2
    assert coverage.bucket(sampled) == coverage.UNVERIFIABLE, (
        "a run that read 100,000 of 500,000 rows and passed was filed as verified. It is a "
        "statement about a sample, and INV-5 exists because that difference is invisible."
    )

    errored = _record("errored", "passed")
    assert errored.status == "errored", f"the roll-up came out {errored.status!r}"
    assert coverage.bucket(errored) == coverage.UNVERIFIABLE

    holed = _record("failed", "errored")
    assert holed.status == "failed" and holed.coverage == 1, (
        f"the fixture did not produce the case under test: {holed.status!r}, "
        f"coverage {holed.coverage} of {len(holed.results)}"
    )
    assert coverage.bucket(holed) == coverage.UNVERIFIABLE, (
        "a run that rolled up to FAILED with an errored rule inside it was filed as "
        "verified. The roll-up hides the hole; `coverage` is the field that does not."
    )

    for verdicts in (("passed", "passed"), ("failed", "passed")):
        whole = _record(*verdicts)
        assert coverage.bucket(whole) == coverage.VERIFIED, (
            f"{verdicts} over the whole table is a real verdict and belongs in the last "
            "bucket. A screen where nothing is ever verified is a screen nobody believes."
        )


def test_a_table_with_any_record_is_never_in_the_never_run_bucket() -> None:
    """The mockup's defect, asserted as an absence: no record shape reaches bucket one.

    `design/ux-variant-workbench.html` shows `customers` under "1 · Never run" while
    holding a run for it elsewhere. That is only possible where the bucket is typed;
    here the derivation has nothing to consult but the record, so this check is a proof
    that the mockup's arrangement cannot be reproduced rather than a promise not to.
    """
    every = [
        _record("passed", "passed"),
        _record("failed", "passed"),
        _record("errored", "passed"),
        _record("failed", "errored"),
        _record("passed", "passed", scanned=1),
        _record("passed"),
    ]
    misfiled = [r.status for r in every if coverage.bucket(r) == coverage.NEVER_RUN]
    assert not misfiled, (
        f"records with status {misfiled} were filed under 'never run'. A run happened; the "
        "screen said it did not — which is the one thing a coverage dashboard may not do."
    )


def test_zero_coverage_tables_sort_first_inside_every_bucket() -> None:
    """SPEC F10's default sort, and the tie-break under it.

    A table nobody has written a rule for is the least trustworthy thing on the screen,
    so it leads its bucket whatever its size; among tables that are equal on that, the
    bigger one leads, because it is the larger exposure. Both are asserted at once by
    laying out a set where the two orderings disagree — `payments` has rules and half a
    million rows, `refunds` has none and thirty thousand — so a sort that used size
    alone would put `payments` first and fail here.
    """
    found = [
        _table("payments", rules=5, rows=500_000),
        _table("refunds", rules=0, rows=31_440),
        _table("customers", rules=0, rows=184_203),
        _table("order_items", rules=2, rows=6_112_730),
    ]
    buckets = coverage.arrange(found, {})
    never = next(b for b in buckets if b["id"] == coverage.NEVER_RUN)
    assert [row["table"] for row in never["tables"]] == [
        "customers",
        "refunds",
        "order_items",
        "payments",
    ], (
        f"the order came out {[row['table'] for row in never['tables']]}. Zero-coverage "
        "first (customers, refunds — larger first), then the covered tables by size."
    )
    assert [b["id"] for b in buckets] == list(status.BUCKET_IDS), (
        "the buckets came back in a different order from the one the headings number. The "
        "ordinal in the heading is the argument; it may not disagree with the sequence."
    )
    assert all(
        b["tables"] == [] for b in buckets if b["id"] != coverage.NEVER_RUN
    ), "a table with no record reached a bucket other than the first one"


def test_every_bucket_is_returned_even_when_it_is_empty() -> None:
    """Three buckets always, so 'nothing here is verified' is something the screen says.

    It is also what makes the browser's DOM-order assertion worth anything: a page that
    rendered only its non-empty buckets could satisfy an ordering check by having one.
    """
    buckets = coverage.arrange([], {})
    assert [b["id"] for b in buckets] == list(status.BUCKET_IDS)
    assert all(b["heading"] and b["why"] for b in buckets), (
        "a bucket arrived without its heading or the sentence under it; both are written "
        "once in app/dq/status.py and travel in the payload"
    )


def test_the_verdict_slot_is_filled_by_the_single_writer_in_both_shapes() -> None:
    """One column, two writers, both in `app/dq/status.py` — and neither is this module.

    A table that has never been run and a table that has still occupy the same slot, and
    the point of asserting it here is that the strings are compared against the formatter
    rather than against literals: `NEVER RUN · NO RULES` typed into this file would keep
    passing on the day somebody started composing that sentence somewhere else.
    """
    assert coverage.row(_table("refunds"), None)["status"] == status.coverage_atom(0)
    assert coverage.row(_table("payments", rules=5), None)["status"] == status.coverage_atom(5)

    sampled = _record("passed", "passed", scanned=100_000)
    rendered = coverage.row(_table(TABLE, rules=2), sampled)
    assert (
        rendered["status"]
        == sampled.atom
        == status.status_atom(status.RuleResult("passed", 100_000, ROWS))
    ), f"the row composed its own verdict: {rendered['status']!r}"
    assert "sampled" in rendered["status"], (
        "INV-5: a partial scan discloses itself INSIDE the verdict string, so there is no "
        "arrangement of elements that can render the verdict and drop the disclosure"
    )
    assert rendered["verdict"] == "passed" and rendered["record_id"] == sampled.record_id
