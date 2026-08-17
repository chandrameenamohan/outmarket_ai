"""F1 · the table listing: shape, size and coverage, and the row that reads zero.

Two of these three need nothing but Python. That is deliberate: the rule this
view exists for — a table with no rules is listed WITH A ZERO, not dropped — is a
property of a fold over a list of revisions, so it belongs in `make check` where
it runs on every save rather than in the layer that needs Singapore.

It is also the rule an implementation loses by accident. Write the join in SQL,
or iterate the rules and count by table, and what comes back is the set of tables
that HAVE rules — which looks correct in a demo where everything has a rule, and
silently hides the uncovered table that is the only reason anyone opened the page.

The `ge` check is the one thing pure Python cannot answer: that the types are the
real ones the database reports, and that a rule accepted through the real store
moves the real count.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Any

import pytest

from app.db import tables
from app.rules import store
from conftest import REPO

TABLE = "orders"
OTHER = "customers"

# A spec exactly as `validate()` returns it — ours, two keys (F6).
SPEC: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0},
}

# Any aggregate over the rows themselves, in any spelling. `count (*)` with a
# space is valid SQL, and `sum(1)` is the same sequential scan wearing a hat.
FULL_SCAN = re.compile(r"\b(count|sum)\s*\(", re.I)

# A string that IS a statement, rather than prose mentioning one — the same
# distinction `tests/test_rule_store.py` draws, and needed here for the same
# reason: app/db/tables.py explains at length why it does not run `count(*)`, so
# a grep over the file text finds the explanation and fails.
STATEMENT = re.compile(r"^\s*(select|insert|update|delete|with)\b", re.I)


def _statements(path: pathlib.Path) -> list[str]:
    """Every SQL statement in a module, found by `ast` rather than by grep."""
    tree = ast.parse(path.read_text(), filename=str(path))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and STATEMENT.match(node.value)
    ]


def _revision(table: str, status: str, rule_id: str, revision: int = 1) -> store.Revision:
    return store.Revision(rule_id=rule_id, revision=revision, table=table, spec=SPEC, status=status)


def test_table_with_no_rules_reports_zero_and_is_not_omitted() -> None:
    """The whole point of a coverage view, asserted on the row that carries it.

    `customers` has no revisions at all and `orders` has three, one of which is
    accepted. Three things are checked together because dropping any one of them
    lets a plausible wrong implementation through: both tables come back (a join
    that iterates rules loses `customers`), the uncovered one reads 0 rather than
    None or a missing key, and the covered one counts only what was ACCEPTED —
    a proposal and a rejection are not coverage.
    """
    found = (
        tables.Table(TABLE, {"order_total": "numeric(10,2)"}, 500_000),
        tables.Table(OTHER, {"customer_id": "integer"}, 50_000),
    )
    revs = (
        _revision(TABLE, store.ACCEPTED, "a"),
        _revision(TABLE, store.PROPOSED, "b"),
        store.Revision("c", 2, TABLE, SPEC, store.REJECTED, reason="not a business invariant"),
    )

    listed = {table.name: table for table in tables.with_coverage(found, revs)}

    assert set(listed) == {TABLE, OTHER}, (
        f"the listing came back as {sorted(listed)}. Every table read from the schema is in the "
        "answer; a table with no rules is the one row a coverage view exists to show."
    )
    assert (
        listed[OTHER].accepted_rules == 0
    ), f"{OTHER} has no rules and reported {listed[OTHER].accepted_rules!r} rather than 0."
    assert listed[TABLE].accepted_rules == 1, (
        f"{TABLE} has one accepted rule, one proposed and one rejected, and reported "
        f"{listed[TABLE].accepted_rules}. Only accepted rules execute, so only accepted rules "
        "count toward coverage (SPEC F6)."
    )


def test_row_count_is_approximate_not_a_full_scan() -> None:
    """The size number is the planner's estimate, and the query proves it.

    `count(*)` over `orders` is a sequential scan of 500,000 rows, paid on every
    load of the front door, for a number rendered as "~500,000". F1 asks for an
    approximate count for exactly this reason. The catalog estimate is already in
    the `pg_class` row the column list joins against, so it costs nothing at all.
    """
    sql = _statements(REPO / "app/db/tables.py")
    scans = [s for s in sql if FULL_SCAN.search(s)]

    assert sql, (
        "no SQL statement was found in app/db/tables.py at all, so this check has gone blind — "
        "it reads string constants that begin with a SQL verb, not the whole file, because the "
        "module's own prose says the words it is looking for."
    )
    assert any("reltuples" in s for s in sql), (
        "nothing in app/db/tables.py reads pg_class.reltuples, so the row count is coming from "
        "somewhere else. F1 asks for an approximate count."
    )
    assert not scans, (
        f"a statement in app/db/tables.py aggregates over the rows themselves: {scans}. That is "
        "a sequential scan of every table on every load of the front door."
    )


# `-> None` is omitted here and nowhere else: the check name the bead names, plus the
# annotation, is 105 columns. The name is the more useful of the two in a test report.
@pytest.mark.ge
def test_seeded_schema_lists_orders_customers_and_payments_with_types_and_accepted_rule_counts():
    """The whole listing against the real database, including a count that moves.

    The types are asserted as the database spells them — `numeric(10,2)`, not
    "number" — because a listing that reported `information_schema`'s truncated
    view of them would be useless to the person deciding which rule to write.

    Coverage is asserted as a DELTA rather than an absolute: the store is
    append-only and this layer writes to a scratch schema that accumulates across
    runs, so "orders has one accepted rule" is not a stable fact, whereas
    "accepting one more rule adds exactly one" is the claim being made.
    """
    before = {table.name: table for table in tables.tables()}

    assert {TABLE, OTHER, "payments"} <= set(before), (
        f"the seeded schema listed {sorted(before)}; seed/MANIFEST.md loaded orders, customers "
        "and payments."
    )
    assert before[TABLE].columns["order_total"] == "numeric(10,2)", (
        f"order_total came back as {before[TABLE].columns['order_total']!r}. The type is the "
        "one the database reports, precision included."
    )
    assert (
        before[TABLE].columns["ordered_at"] == "timestamp with time zone"
    ), f"ordered_at came back as {before[TABLE].columns['ordered_at']!r}."
    assert before[TABLE].approx_rows > 100_000, (
        f"orders estimated at {before[TABLE].approx_rows} rows; the seed loaded 500,000. An "
        "estimate of 0 means the table has never been analysed, not that it is empty."
    )

    rule = store.propose(TABLE, SPEC["type"], SPEC["kwargs"])
    proposed_only = {table.name: table for table in tables.tables()}
    store.set_status(rule.rule_id, store.ACCEPTED)
    after = {table.name: table for table in tables.tables()}

    assert proposed_only[TABLE].accepted_rules == before[TABLE].accepted_rules, (
        "proposing a rule changed the coverage count. A proposal is not coverage — nobody has "
        "agreed to it and it does not execute."
    )
    assert after[TABLE].accepted_rules == before[TABLE].accepted_rules + 1, (
        f"accepting one rule took the count from {before[TABLE].accepted_rules} to "
        f"{after[TABLE].accepted_rules}."
    )
    assert (
        after[OTHER].accepted_rules == before[OTHER].accepted_rules
    ), "accepting a rule on orders moved the count on customers. The count is per table."
