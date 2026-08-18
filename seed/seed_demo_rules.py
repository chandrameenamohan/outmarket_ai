#!/usr/bin/env python3
"""B25 · the fixed demo fixture: the rules the demo store holds, and the runs behind them.

`seed/seed_demo_data.py` seeds the TABLES. This seeds the RULE STORE, which is the other
half of a demo nobody can photograph without: a clean store makes a working product look
broken (SPEC F15's own argument), and a polluted one makes it look worse. Both states were
real on 2026-08-17 — the demo store `dq` held 0 rules while the scratch schema `dq_check`
held 261, most of them the SAME rule left behind by repeated `make check-ge` runs, so the
review queue rendered fifty copies of "Every order_total is at least 0" and its own
time-budget indicator honestly reported "about 16 minutes left".

WHAT IS DELIBERATELY SMALL HERE. Eight rules over three tables, and the eight are chosen
to be every STORED state those screens render, once each:

    accepted and PASSING      orders.order_reference is never null, customers.full_name
    accepted and FAILING      orders.order_total >= 0 (D1, 150 rows) and
                              orders.order_reference is unique (D6, 150 rows)
    needs_review              orders.status in the vocabulary — SPEC §7 step 3's flagged
                              rule, verbatim: a business assumption the engineer cannot
                              verify. Plus one on customers, so the review queue shows
                              INV-1's budget RESTARTING at the second table
    rejected, with its reason orders.shipped_at is never null — a rule that is wrong
                              about the business, refused in words somebody can read
    errored, not failed       one reading on the seeded customers record. LT-1a is the
                              whole reason the state exists (`catch_exceptions` defaults
                              to True, so a rule that BLEW UP looks exactly like one that
                              FAILED), and the distinction is invisible with no instance

and `payments` gets nothing at all, on purpose: a table nobody has written a rule for is
F10's first bucket, and an empty bucket one is the loudest thing that screen can say.

WHAT IT DELIBERATELY DOES NOT COVER, said out loud because a fixture that claims to cover
everything is the more expensive lie: **an unsaved PROPOSAL.** A proposal is a model call
(F3) and is unsaved by definition (F4), so it is not a store state and this seeder cannot
mint one. The rules desk's proposal pane therefore photographs empty here, which is why
the `rules-proposal-needs-review-held` visual state was deleted rather than approved
(`tests/e2e/test_ui_hygiene.py::STATES`) and why the pane is checked where it is real, in
`tests/e2e/test_f12_translation_desk.py` against a billed call.

IDEMPOTENT, AGAINST A STORE THAT CANNOT BE EDITED. Both tables are append-only by trigger
(F6) — no UPDATE, no DELETE, no TRUNCATE, from any role including the owner — so "run it
twice and get the same store" cannot be done by clearing and rewriting. It is done by
asking, per rule, whether the store ALREADY holds this exact validated spec for this
table, and appending only what is missing:

    absent           propose() it, then set_status() it into the state the fixture names
    present, wrong   set_status() only — one revision, no second copy of the rule
    present, right   nothing at all

The same question for the two run records: a table that already has a record keeps it,
because a record is immutable and re-running would append a SECOND one and move every
`record_id` on screen. That is what makes the ids in `/runs/<id>` and F10's middle bucket
the same on the second run as on the first, which is the entire point of a fixture that
gets photographed.

`--reset` is the other half of the honest answer: the ONLY way to take rules back out is
`DROP SCHEMA dq CASCADE`, because the trigger refuses everything else. It is a separate
flag rather than the default for a reason worth stating — a reset mints new rule ids and
a new record id, so every visual baseline taken against the old store is a photograph of
rules that no longer exist and has to be looked at and approved again by a person.

NOTHING HERE REACHES THE STORE PAST THE VALIDATOR (INV-2). Every rule walks
`store.propose()`, which hands the spec to `app/rules/validator.py` with the LIVE column
set before anything is written. A fixture that INSERTed its rows directly would be the
exact back door the keystone invariant exists to close, and it would also be the one
place in the product where a spec nobody validated could reach a screen.

Run it:

    set -a; . ./.env; set +a
    make demo-fixture          # or the uv line that target holds

Great Expectations is needed and is not in the base interpreter (INV-3, and VERIFICATION
§1's promise that `make check` installs nothing): the validator's second layer constructs
every rule against the framework, and the `orders` record below is a REAL run.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import pathlib
import sys
from typing import Any

# THE DEMO'S OWN SCHEMA, PINNED BEFORE `app.db.system` IS IMPORTED AND UNCONDITIONALLY.
# `tests/conftest.py` makes exactly this argument in the opposite direction: `DQ_SCHEMA`
# is a documented `.env` key, so an operator who pointed it at the scratch schema for a
# `make check-ge` run would otherwise seed the demo fixture into `dq_check` — which is
# the polluted store this file exists because of.
DEMO_SCHEMA = "dq"
os.environ["DQ_SCHEMA"] = DEMO_SCHEMA

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.api import server  # noqa: E402
from app.dq import run, runs, status  # noqa: E402
from app.rules import catalog, store, validator  # noqa: E402
from app.rules import schema as live  # noqa: E402

# The vocabulary `orders.status` is supposed to hold, from seed/MANIFEST.md. It is the
# rule SPEC §7 step 3 flags, and the reason it flags it is that this list is an
# ASSUMPTION: 240 rows already sit outside it, and whether those are typos or a status
# nobody told us about is a question only the business can answer.
ORDER_STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled", "returned"]

# One entry per rule: the table, the state it ends in, the spec, and — for a rejection —
# the reason, which the store REFUSES to write without (F6).
FIXTURE: tuple[dict[str, Any], ...] = (
    {
        "table": "orders",
        "status": store.ACCEPTED,
        "type": "expect_column_values_to_be_between",
        "kwargs": {"column": "order_total", "min_value": 0},
    },
    {
        "table": "orders",
        "status": store.ACCEPTED,
        "type": "expect_column_values_to_not_be_null",
        "kwargs": {"column": "order_reference"},
    },
    {
        "table": "orders",
        "status": store.ACCEPTED,
        "type": "expect_column_values_to_be_unique",
        "kwargs": {"column": "order_reference"},
    },
    {
        "table": "orders",
        "status": store.NEEDS_REVIEW,
        "type": "expect_column_values_to_be_in_set",
        "kwargs": {"column": "status", "value_set": ORDER_STATUSES},
    },
    {
        "table": "orders",
        "status": store.REJECTED,
        "reason": (
            "An order that has not shipped yet legitimately has no shipped date, so this "
            "would report every open order as a defect. The rule worth having is a "
            "conditional one and conditions are v2 (SPEC §5) — rejected rather than "
            "amended, so nobody proposes it again next week."
        ),
        "type": "expect_column_values_to_not_be_null",
        "kwargs": {"column": "shipped_at"},
    },
    {
        "table": "customers",
        "status": store.ACCEPTED,
        "type": "expect_column_values_to_not_be_null",
        "kwargs": {"column": "email"},
    },
    {
        "table": "customers",
        "status": store.ACCEPTED,
        "type": "expect_column_values_to_not_be_null",
        "kwargs": {"column": "full_name"},
    },
    {
        "table": "customers",
        "status": store.NEEDS_REVIEW,
        "type": "expect_column_values_to_be_unique",
        "kwargs": {"column": "email"},
    },
)

# The table whose record is a REAL run, and the one whose record is written by hand.
RUN_FOR_REAL = "orders"
SEEDED_TABLE = "customers"

# THE ONE RECORD NO RUN OF THE SHIPPING CONFIGURATION CAN PRODUCE, and the reason is
# `tests/conftest.py::coverage_records`' word for word: the row cap is OFF (SPEC O-2) so
# nothing is ever sampled, and no seeded table makes a catalog rule blow up. So F10's
# middle bucket — "it ran, and the verdict cannot be trusted" — and the errored/failed
# distinction LT-1a bought would both be rendered by nothing. Written through
# `runs.save()`, the same door a run uses, which derives the roll-up and the coverage
# count itself: a fixture cannot state a combination a real run could not produce.
#
# Both facts are on this one record on purpose. A partial scan is INV-5's marker, and an
# errored rule is the hole in coverage; either one alone puts the table in bucket two.
SEEDED_SCAN = (10_000, 50_000)
SEEDED_VERDICTS: tuple[tuple[str, str | None], ...] = (
    (
        "errored",
        "the connection dropped while this rule was reading, so it counted nothing at all "
        "— that is not the same as finding nothing, and it is why the verdict is not a pass",
    ),
    ("passed", None),
)


def validated(entry: dict[str, Any]) -> dict[str, Any]:
    """The fixture's spec as the store would hold it — INV-2's own normalisation.

    The same call `propose()` makes, made a second time here so the "does the store
    already hold this?" comparison is between two specs the validator produced rather
    than between what this file typed and what the framework normalised (`min_value=0`
    is stored as `0.0`). Comparing the raw kwargs would find nothing on the second run
    and append the whole fixture again.
    """
    return validator.validate(
        entry["type"], entry["kwargs"], entry["table"], live.columns(entry["table"])
    )


def seed_rules() -> list[str]:
    """Append what is missing and judge what is in the wrong state. Returns one line each."""
    said = []
    for entry in FIXTURE:
        spec = validated(entry)
        wanted, reason = entry["status"], entry.get("reason")
        held = store.current(store.revisions(table=entry["table"]))
        found = next((rev for rev in held if rev.spec == spec), None)
        if found is None:
            rule = store.propose(entry["table"], entry["type"], entry["kwargs"])
            store.set_status(rule.rule_id, wanted, reason)
            said.append(f"  wrote   {entry['table']:<10} {wanted:<12} {rule.rule_id}")
        elif found.status != wanted:
            store.set_status(found.rule_id, wanted, reason)
            said.append(f"  judged  {entry['table']:<10} {wanted:<12} {found.rule_id}")
        else:
            said.append(f"  held    {entry['table']:<10} {wanted:<12} {found.rule_id}")
    return said


def seed_records() -> list[str]:
    """The two run records the screens read: one executed, one written.

    A table that already has a record keeps it. Records are immutable and append-only
    (F9), so the alternative to skipping is a second record at a second address — and
    every `record_id` on F10's dashboard and in `/runs/<id>` would move, which is the
    one thing a fixture that gets photographed may not do.
    """
    said = []
    for table in (RUN_FOR_REAL, SEEDED_TABLE):
        existing = runs.latest(table)
        if existing is not None:
            said.append(f"  held    {table:<10} record       {existing.record_id}")
            continue
        written = _execute(table) if table == RUN_FOR_REAL else _write(table)
        said.append(f"  wrote   {table:<10} record       {written}")
    return said


def _execute(table: str) -> str:
    """A REAL run of the accepted rules, through the product's own two doors.

    `server.plan()` is what the POST route resolves before it sends a byte, and
    `run.stream()` is the generator behind the NDJSON response — so what the demo store
    ends up holding is a record a user could have produced by pressing Run, not one this
    file imagined. That matters most for the failing rules: the offending order ids and
    values on the screenshot are Great Expectations' own output against 500,000 real rows.
    """
    scan, specs, identifiers = server.plan(table)
    last: dict[str, Any] = {}
    for event in run.stream(scan, specs, identifiers):
        last = dict(event)
    if not last.get("record_id"):
        raise SystemExit(f"the run of {table} ended on {last!r} rather than on a stored record")
    return str(last["record_id"])


def _write(table: str) -> str:
    """The hand-written record — see `SEEDED_VERDICTS` for why it cannot be executed.

    Every string on it comes from the product's own writers: the verdict atom from
    `app/dq/status.py`, which is the single writer of that sentence and the reason the
    sampling clause is INSIDE it (INV-5), and the English statement from
    `app/rules/catalog.py`. A fixture that composed either itself would be a second
    writer, and the first version of the browser layer's equivalent shipped exactly that
    bug — a bare "ERRORED" on a run that scanned 10,000 of 50,000 rows, with the
    disclosure nowhere on the row.
    """
    scanned, total = SEEDED_SCAN
    specs = [
        validated(entry)
        for entry in FIXTURE
        if entry["table"] == table and entry["status"] == store.ACCEPTED
    ]
    results = [
        {
            "spec": spec,
            "verdict": verdict,
            "status": status.status_atom(status.RuleResult(verdict, scanned, total)),  # type: ignore[arg-type]
            "statement": catalog.english(spec["type"], spec["kwargs"]),
            "detail": detail,
        }
        for spec, (verdict, detail) in zip(specs, SEEDED_VERDICTS, strict=True)
    ]
    payload = {
        "table": table,
        "scanned_rows": scanned,
        "total_rows": total,
        "results": results,
    }
    return runs.save(specs, payload).record_id


def reset() -> None:
    """`DROP SCHEMA dq CASCADE` — the only reset an append-only store has.

    Before anything connects: `app/db/system.py` establishes its idempotent DDL once per
    connection and remembers it, so a schema dropped underneath a live connection is a
    schema nothing will recreate. Same ordering `tests/e2e/scenario_stack.py` depends on.
    """
    import psycopg2

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL_SYSTEM"], connect_timeout=30)
    with contextlib.closing(conn), conn, conn.cursor() as cur:
        cur.execute(f"drop schema if exists {DEMO_SCHEMA} cascade")


def main() -> None:
    parsed = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parsed.add_argument(
        "--reset",
        action="store_true",
        help=(
            f"drop {DEMO_SCHEMA} first. Mints new rule ids and a new record id, so every "
            "visual baseline taken against the old store has to be looked at again."
        ),
    )
    if parsed.parse_args().reset:
        reset()
        print(f"dropped schema {DEMO_SCHEMA}")

    print(f"demo fixture · schema {DEMO_SCHEMA}")
    for line in seed_rules() + seed_records():
        print(line)
    print(
        f"\n{len(FIXTURE)} rules, 2 records. Re-running this command changes nothing; "
        f"`--reset` is the only way back to an empty store, and it moves every id."
    )


if __name__ == "__main__":
    main()
