"""F2 · what the model sees instead of the table: aggregate statistics and 20 rows.

ONE STATEMENT. Not a profiling subsystem — SPEC F2's own note, and INV-6. Every
number here comes back from a single `SELECT` per table: the row count, the five
cells each column needs, and the sample, folded in as a CTE so the twenty rows
cost one extra plan node rather than a second round trip. Measured against the
seeded 500,000-row `orders` (10 columns): **7.98 s**, of which the bounded
distinct-value subqueries are 0.3 s — the price is the ten `count(distinct)`
sorts, and it is the same price whether they arrive as one statement or ten.
That is why the cache below is the feature and the query is not tuned.

WHAT IT MAY NOT CARRY. SPEC §3.1: the model receives aggregate statistics and a
bounded sample, **never full table contents**. `TableProfile` refuses a sample
larger than `SAMPLE_ROWS` in `__post_init__`, so the bound is a property of the
type rather than of the SQL that happens to build it today. The distinct values
are bounded by the same reasoning: the statement asks for `LOW_CARDINALITY + 1`
of them and the profile keeps them only when the exact distinct count says the
whole set fits — a column with 500,000 distinct values reports its count, never
its contents.

WHY THE VALUES ARE TEXT. `min(c)::text` rather than psycopg2's native adaptation:
this block is serialised into a prompt and into JSON, and PostgreSQL's own output
form is the one the database itself would print. The ceiling is that a caller
wanting a `Decimal` back has to parse it — nothing does, and F3's evidence line
("min observed 0.00") wants the string anyway.

READ-ONLY, AND NOT BY MANNERS. The connection comes from
`app/rules/schema.py::connect()`, the SELECT-only `dq_analyst` role — so a
profiler that one day tried to materialise a scratch table would be refused by
PostgreSQL (`tests/test_db_privilege_split.py`), not by this docstring.

IDENTIFIERS. The table name arrives from outside and is resolved through the live
schema first (`UnknownTable` if it is not real); the column names come back from
`information_schema`, never from a caller. Both are then quoted with PostgreSQL's
own doubling rule. `psycopg2.sql.Identifier` would do the same job but cannot
render without a live connection, which would put the statement builder — the
thing worth checking — out of reach of `make check`.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.rules import schema as live

# A column with at most this many distinct values reports the values themselves;
# past it, only the count. Twenty is the number that fits on a review card without
# a scroll — the same budget as the sample, and INV-1's five minutes is what both
# are really spending.
LOW_CARDINALITY = 20

# SPEC F2: "Twenty sample rows accompany the block."
SAMPLE_ROWS = 20

# How long a profile stays fresh. Statistics describe DATA, not structure, so this
# is deliberately shorter than the schema cache next door (which lasts the process):
# a proposal justified by evidence from an hour ago is a proposal justified by a
# table that has since changed. Five minutes covers a review session — the whole
# point of the cache is that redrawing a screen never re-queries.
CACHE_SECONDS = 300

# The four `information_schema.data_type` spellings that mean "we cannot tell", so
# `min`/`max` are not asked for. Not a whitelist: every other built-in type has a
# default btree operator class, and inverting this would silently drop min/max from
# ordinary columns. `USER-DEFINED` and `ARRAY` are the indeterminate ones — an enum
# under that name would order fine, and a geometry under it would fail the WHOLE
# statement, so losing one column's min is the cheaper error. The list stops here on
# purpose (INV-6): naming PostGIS's own types would be defensive handling for a
# database nobody is connecting.
UNORDERED = frozenset({"json", "xml", "ARRAY", "USER-DEFINED"})

# non_null, distinct, minimum, maximum, values — emitted for every column in this
# order, so the answer is read back positionally against the same column list.
_CELLS = 5


@dataclass(frozen=True)
class ColumnProfile:
    """One column's statistics. `values` is the whole distinct set, or nothing.

    There is no "first twenty of many": a truncated value list read as a complete
    one is exactly how a model proposes `status IN {observed values}` for a column
    with four hundred of them (LT-2b). Either the set is small enough to state, or
    the caller gets the count and no values at all.
    """

    name: str
    data_type: str
    total_rows: int
    non_null: int
    distinct: int
    minimum: str | None
    maximum: str | None
    values: tuple[str, ...] | None

    def __post_init__(self) -> None:
        if self.values is not None and len(self.values) > LOW_CARDINALITY:
            raise ValueError(
                f"{self.name} carries {len(self.values)} values; past {LOW_CARDINALITY} a "
                "column reports its distinct COUNT and nothing else (SPEC §3.1 — aggregate "
                "statistics and a bounded sample, never full table contents)."
            )


@dataclass(frozen=True)
class TableProfile:
    """The whole block, and the one place its size is bounded."""

    table: str
    total_rows: int
    columns: tuple[ColumnProfile, ...]
    sample: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if len(self.sample) > SAMPLE_ROWS:
            raise ValueError(
                f"{len(self.sample)} sample rows for {self.table}; the bound is {SAMPLE_ROWS}. "
                "This block is what the model receives instead of the table (SPEC §3.1), so "
                "the limit is enforced where the block is built, not where the SQL is written."
            )


_CACHE: dict[str, tuple[float, TableProfile]] = {}


def of(table: str) -> TableProfile:
    """Profile `table`, or hand back the profile from the last `CACHE_SECONDS`.

    The cache is checked before the schema is even read, so a repeat request inside
    the window issues NO statement of any kind against the target database — which
    is what `tests/test_table_profile.py` counts.
    """
    cached = _CACHE.get(table)
    if cached is not None and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]

    columns = live.column_types(table)
    with live.connect() as conn, conn.cursor() as cur:
        cur.execute(
            _statement(table, columns),
            {"cardinality": LOW_CARDINALITY + 1, "sample": SAMPLE_ROWS},
        )
        row = cur.fetchone()

    profile = _profile(table, columns, row)
    _CACHE[table] = (time.monotonic(), profile)
    return profile


def _statement(table: str, columns: Sequence[tuple[str, str]]) -> str:
    """The one query. Pure, so what gets sent is checkable without a database.

    Both bounds are bind parameters (`%(cardinality)s`, `%(sample)s`); the only
    interpolation is quoted identifiers that came from `information_schema`.
    """
    t = _quoted(table)
    parts = [
        "count(*)",
        # LIMIT with no ORDER BY: whatever the scan reaches first. A representative
        # sample would need a TABLESAMPLE and a second pass, and the model is told
        # these are example rows, not a distribution.
        "(select coalesce(json_agg(to_jsonb(s)), '[]'::json) from s)",
    ]
    for name, data_type in columns:
        c = _quoted(name)
        # An unordered type has no equality operator either (`json`), so DISTINCT
        # goes through the same cast that makes the value printable.
        key = c if data_type not in UNORDERED else f"{c}::text"
        parts += [
            f"count({c})",
            f"count(distinct {key})",
            f"min({c})::text" if data_type not in UNORDERED else "null::text",
            f"max({c})::text" if data_type not in UNORDERED else "null::text",
            f"(select array_agg(v::text) from (select distinct {key} as v from {t} "
            f"where {c} is not null limit %(cardinality)s) d)",
        ]
    return f"with s as (select * from {t} limit %(sample)s) " f"select {', '.join(parts)} from {t}"


def _profile(table: str, columns: Sequence[tuple[str, str]], row: Sequence[Any]) -> TableProfile:
    """The single answer row, read back against the column list that shaped it. Pure."""
    total, sample = row[0], row[1]
    profiled = []
    for i, (name, data_type) in enumerate(columns):
        non_null, distinct, minimum, maximum, values = row[2 + i * _CELLS : 2 + (i + 1) * _CELLS]
        profiled.append(
            ColumnProfile(
                name=name,
                data_type=data_type,
                total_rows=total,
                non_null=non_null,
                distinct=distinct,
                minimum=minimum,
                maximum=maximum,
                values=tuple(values) if values and distinct <= LOW_CARDINALITY else None,
            )
        )
    return TableProfile(table, total, tuple(profiled), tuple(sample))


def _quoted(identifier: str) -> str:
    """PostgreSQL's own rule: wrap in double quotes, double any inside."""
    return '"' + identifier.replace('"', '""') + '"'
