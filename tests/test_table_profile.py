"""B11 · F2 — one statistics query per table, and a cache that is counted, not timed.

The two unit checks drive `app/dq/profile.py`'s pure halves — the statement it
builds and the answer it reads back — so the two decisions worth getting wrong
(when a column's values are safe to state, and which types PostgreSQL can order)
are checked by `make check`, offline, with no database anywhere near them.

The two `ge` checks need the seeded database. The second of them is the reason
this file exists in the shape it does: "a repeat request does not re-query" is
trivially satisfiable by a fast second call, so it is asserted by COUNTING the
statements that reach the database rather than by timing anything. The counter is
a `psycopg2` cursor subclass patched over `psycopg2.connect` itself, so it sees
every statement from every module in the process — including the
`information_schema` read in `app/rules/schema.py`, which is a query against the
target database too and would otherwise slip past a counter that only watched the
profiler's own connection.
"""

from __future__ import annotations

import time

import psycopg2
import pytest

from app.dq import profile

# Every statement any module in this process sends, in order of arrival.
_STATEMENTS: list[str] = []


class _CountingCursor(psycopg2.extensions.cursor):
    """A real cursor that writes down what it was asked to run before running it."""

    def execute(self, query, vars=None):  # noqa: ANN001, ANN201, A002
        _STATEMENTS.append(str(query).strip()[:120])
        return super().execute(query, vars)


def _counting(monkeypatch) -> list[str]:
    """Point every `psycopg2.connect` in the process at the counting cursor."""
    connect = psycopg2.connect

    def counted(dsn, **kwargs):
        return connect(dsn, cursor_factory=_CountingCursor, **kwargs)

    monkeypatch.setattr(psycopg2, "connect", counted)
    _STATEMENTS.clear()
    return _STATEMENTS


def test_low_cardinality_returns_values_and_high_cardinality_does_not() -> None:
    """A four-value column states its four values; a 500,000-value column states none.

    The high-cardinality row below is what the database actually returns — the
    statement asks for `LOW_CARDINALITY + 1` values precisely so that "too many to
    enumerate" is a fact rather than a guess, and 21 values come back for a column
    with half a million. Handing those 21 on as if they were the column's vocabulary
    is the LT-2b failure mode with a smaller sample: a rule that is true of every
    value it was shown and wrong about the table.
    """
    columns = (("status", "text"), ("order_id", "integer"))
    row: tuple[object, ...] = (
        500_000,
        [],
        # status — four distinct values, and the whole set came back
        500_000,
        4,
        "cancelled",
        "shipped",
        ["cancelled", "paid", "shipped", "shippd"],
        # order_id — one per row; the LIMIT cut the list off at 21
        500_000,
        500_000,
        "1",
        "500000",
        [str(n) for n in range(21)],
    )

    status, order_id = profile._profile("orders", columns, row).columns
    assert status.values == ("cancelled", "paid", "shipped", "shippd"), (
        f"a {status.distinct}-value column must report the values themselves — that list is "
        f"the evidence a proposal about `status` cites; got {status.values}"
    )
    assert order_id.values is None, (
        f"a column with {order_id.distinct:,} distinct values reported {order_id.values}. The "
        "21 values the LIMIT returned are a truncation, and passing a truncation on as a "
        "vocabulary is how a rule ends up true of the sample and false of the table."
    )
    assert (
        order_id.distinct == 500_000
    ), "the exact distinct COUNT survives even when the values do not"

    with pytest.raises(ValueError, match="distinct COUNT"):
        profile.ColumnProfile(
            name="order_id",
            data_type="integer",
            total_rows=500_000,
            non_null=500_000,
            distinct=500_000,
            minimum="1",
            maximum="500000",
            values=tuple(str(n) for n in range(profile.LOW_CARDINALITY + 1)),
        )


def test_min_and_max_omitted_for_unordered_types() -> None:
    """`json` has neither `<` nor `=`, so the statement must not ask it for either.

    This is not a tidiness point. `min(json_col)` is not an empty result, it is
    `function min(json) does not exist` — one unorderable column would take the
    whole table's profile down with it, because there is only one statement.
    """
    columns = (("payload", "json"), ("order_total", "numeric"))
    statement = profile._statement("orders", columns)

    assert (
        'min("order_total")::text' in statement and 'max("order_total")::text' in statement
    ), f"an ordered column must be asked for its bounds; got: {statement}"
    assert (
        'min("payload")' not in statement and 'max("payload")' not in statement
    ), f"`json` is in UNORDERED, so the statement may not ask it to order; got: {statement}"
    assert 'count(distinct "payload"::text)' in statement, (
        "a type with no ordering has no equality operator either, so DISTINCT has to go "
        f"through the same cast that makes the value printable; got: {statement}"
    )
    assert (
        "%(cardinality)s" in statement and "%(sample)s" in statement
    ), f"both bounds travel as bind parameters, never as interpolated values; got: {statement}"

    row: tuple[object, ...] = (
        3,
        [],
        3,
        2,
        None,
        None,
        ['{"a": 1}', '{"b": 2}'],
        3,
        3,
        "-389.59",
        "3736.32",
        None,
    )
    payload, total = profile._profile("orders", columns, row).columns
    assert (
        payload.minimum is None and payload.maximum is None
    ), f"an unordered column carries no bounds; got {payload.minimum!r}..{payload.maximum!r}"
    assert (total.minimum, total.maximum) == (
        "-389.59",
        "3736.32",
    ), f"an ordered column keeps the bounds the database printed; got {total}"


def test_a_profile_older_than_the_window_is_not_served(monkeypatch) -> None:
    """The other half of the cache: it has to let go. Asserted as state, never as a clock.

    Nothing else exercises the expiry branch, so a cache that never expired would
    pass the whole suite — and the staleness is not confined to an evidence line.
    `app/api/server.py::plan()` takes INV-5's disclosure denominator from
    `profile.of(table).total_rows`, so a permanently-fresh entry is a permanently
    stale denominator inside the sampling clause and inside every `magnitude` string.

    The stale timestamp is planted rather than waited for — the same move the
    counting cursor makes for the hit path — so this stays in `make check` with no
    database and no sleep. What proves the entry was dropped is that the call went on
    to read the live schema, which is the first thing `of()` does on a miss.
    """
    profile._CACHE.clear()
    kept = profile.TableProfile("orders", 500_000, (), ())
    profile._CACHE["orders"] = (time.monotonic() - profile.CACHE_SECONDS - 1, kept)

    def refuse(table: str) -> tuple[tuple[str, str], ...]:
        raise AssertionError(f"re-read the schema for {table}")

    monkeypatch.setattr(profile.live, "column_types", refuse)
    with pytest.raises(AssertionError, match="re-read the schema for orders"):
        profile.of("orders")

    # And the same seeding one second inside the window IS served, or the check above
    # would pass against a cache that never returns anything at all.
    profile._CACHE["orders"] = (time.monotonic() - profile.CACHE_SECONDS + 1, kept)
    assert profile.of("orders") is kept


@pytest.mark.ge
def test_profile_of_orders_has_the_expected_shape() -> None:
    """The real 500,000-row table, against `seed/MANIFEST.md`'s ground truth.

    Every assertion here is something a proposal will later cite as evidence, so
    each is checked against a number the seeder documents rather than against
    whatever the query happened to return.
    """
    profile._CACHE.clear()
    profiled = profile.of("orders")

    assert profiled.total_rows == 500_000, (
        f"seed/MANIFEST.md documents 500,000 orders; profiled {profiled.total_rows:,}. "
        "Run: python3 seed/seed_demo_data.py"
    )
    columns = {column.name: column for column in profiled.columns}
    assert {"order_id", "order_reference", "status", "order_total", "shipped_at"} <= set(
        columns
    ), f"the seeded orders table is missing columns the manifest documents; got {sorted(columns)}"

    status = columns["status"]
    assert status.values is not None and "shippd" in status.values, (
        f"`status` has {status.distinct} distinct values, so the values themselves are what "
        f"makes defect D3 (casing and typo drift) visible to a reviewer; got {status.values}"
    )

    order_id = columns["order_id"]
    assert (order_id.distinct, order_id.values) == (
        500_000,
        None,
    ), f"`order_id` is unique per row, so it reports a count and no values; got {order_id}"

    total = columns["order_total"]
    assert total.minimum is not None and float(total.minimum) < 0, (
        f"defect D1 plants 150 negative order totals, so the observed minimum must be below "
        f"zero — this is the evidence line for the rule the demo turns on; got {total.minimum!r}"
    )

    shipped = columns["shipped_at"]
    assert 0 < shipped.non_null < shipped.total_rows, (
        f"unshipped orders have no shipped_at, so the non-null count must sit strictly inside "
        f"the row count; got {shipped.non_null:,} of {shipped.total_rows:,}"
    )

    assert (
        len(profiled.sample) == profile.SAMPLE_ROWS
    ), f"SPEC F2: twenty sample rows accompany the block; got {len(profiled.sample)}"
    assert set(profiled.sample[0]) == set(
        columns
    ), f"a sample row is a whole row of this table; got keys {sorted(profiled.sample[0])}"


@pytest.mark.ge
def test_second_request_within_the_window_issues_zero_target_db_statements(monkeypatch) -> None:
    """The cache, asserted by counting statements — never by timing the second call.

    A stopwatch cannot tell a cache from a fast query, and a fast query is exactly
    what a warm database gives you. The counter below sits inside psycopg2, so the
    claim it settles is the literal one: nothing was sent.
    """
    statements = _counting(monkeypatch)
    profile._CACHE.clear()

    first = profile.of("orders")
    assert statements, (
        "profiling a cold table sent no statements at all — the counter is not seeing the "
        "queries, so the assertion below would pass for the wrong reason."
    )
    sent = list(statements)
    assert sum('from "orders"' in s for s in sent) == 1, (
        f"F2 is ONE parameterised statistics query per table, not a profiling subsystem "
        f"(SPEC F2 note, INV-6). Statements sent: {sent}"
    )

    statements.clear()
    again = profile.of("orders")
    assert statements == [], (
        f"a repeat request inside the {profile.CACHE_SECONDS}s window sent {statements}. The "
        "screen redraws on every navigation; a profile that re-queries makes the table's own "
        "explorer the most expensive page in the product."
    )
    assert again is first, (
        "the cached call returned a different object, so something rebuilt the profile without "
        "querying — which is a second source of truth, not a cache"
    )
