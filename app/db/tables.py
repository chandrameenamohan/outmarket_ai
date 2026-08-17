"""F1 · every table in the schema, with its shape, its size and its coverage.

The engineer's front door (SPEC §7) and the data behind it. Three facts per
table — what its columns are, roughly how big it is, and how many rules actually
guard it — because that is the smallest set from which someone can say "payments
has six columns, half a million rows and nothing checking it".

WHY THE ROW COUNT IS AN ESTIMATE. `pg_class.reltuples`, the planner's own number,
kept current by autovacuum. `count(*)` on `orders` is a sequential scan of
500,000 rows on every page load, and F1 asks for an approximate count precisely
so the front door does not pay that. The estimate is free — it is already in the
catalog row this query reads for the column list anyway. Ceiling: a table
inserted into heavily since the last ANALYZE reads low, and PostgreSQL 14+ writes
`-1` for a table that has never been analysed at all, which `greatest(..., 0)`
turns into 0 rather than a nonsense negative. Both are the right trade for a
number rendered as "~500,000".

WHY COVERAGE IS ONLY `accepted`. `app/rules/store.accepted()` is the one place
that decides, and it is the same function that decides what EXECUTES (F6). A
table listing that counted proposals would report coverage nobody agreed to.

WHY THE FOLD IS A SEPARATE, PURE FUNCTION. `with_coverage()` takes the tables and
the revisions and joins them, so the rule this whole view exists for — a table
with no rules reports zero rather than being dropped — is checkable with no
database at all, in `make check`. It is exactly the rule an implementation loses
by writing the join in SQL or by iterating the rules instead of the tables.

CONNECTIONS. This module holds no credential at all. The live schema is read
through `app/rules/schema.py::connect()`, the one door to the ANALYSIS role, which
cannot write anywhere (SPEC §3.1, app/db/roles.sql); the rule counts come through
`app/rules/store.py`, which connects as the system role and can write nowhere near
`public`. Composing the two is all this module does with a database.
"""

from __future__ import annotations

import collections
import dataclasses
from collections.abc import Iterable, Mapping

import psycopg2

from app.rules import schema as live
from app.rules import store

# One statement for the whole listing: `pg_class` carries the row estimate and
# `pg_attribute` the columns, so joining them here costs one round trip to
# Singapore instead of two (or one per table). `information_schema.columns` would
# read better and would not have `reltuples` — it is a view over these same
# catalogs with the estimate left out.
#
#   relkind = 'r'         ordinary tables. Views and matviews are not "tables in
#                         the connected database" for F1, and a matview's coverage
#                         would be a claim about a snapshot.
#   attnum > 0            excludes the system columns (ctid, xmin, ...).
#   not attisdropped      a dropped column keeps its `pg_attribute` row forever.
#   current_schema()      the same ceiling app/rules/schema.py accepts, and for the
#                         same reason: the search path decides, and the upgrade
#                         path is the connection string. Cross-schema listing is an
#                         explicit non-goal.
_SHAPE = """
    select c.relname,
           greatest(c.reltuples, 0)::bigint,
           a.attname,
           format_type(a.atttypid, a.atttypmod)
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
     where n.nspname = current_schema()
       and c.relkind = 'r'
     order by c.relname, a.attnum
"""


@dataclasses.dataclass(frozen=True)
class Table:
    """One table as the front door sees it: shape, size, coverage.

    `columns` is name -> type in the table's own column order — `format_type`
    output, so `numeric(10,2)` and `timestamp with time zone` rather than the
    `information_schema` spelling that drops the precision into three more columns.

    `accepted_rules` defaults to 0 because that IS the F1 rule: a table arrives
    from the schema read with no rules attached, and stays in the list saying zero.
    """

    name: str
    columns: Mapping[str, str]
    approx_rows: int
    accepted_rules: int = 0


def tables() -> tuple[Table, ...]:
    """Every table in the target schema, in name order, with coverage filled in."""
    return with_coverage(shapes(), store.revisions())


def with_coverage(found: Iterable[Table], revs: Iterable[store.Revision]) -> tuple[Table, ...]:
    """Attach the accepted-rule count to each table. Pure, and iterates the TABLES.

    The direction is the whole point. Counting per rule and returning that mapping
    would produce a list of the tables that have rules, which is the one shape a
    coverage view must not have — the interesting row is the table with a zero on
    it. Here every table that came out of the schema read comes out of this
    function, and `.get(..., 0)` supplies the zero.
    """
    counted = collections.Counter(rev.table for rev in store.accepted(revs))
    return tuple(
        dataclasses.replace(table, accepted_rules=counted.get(table.name, 0)) for table in found
    )


def shapes() -> tuple[Table, ...]:
    """The live schema half: columns, types and the row estimate. No rules involved."""
    try:
        with live.connect() as conn, conn.cursor() as cur:
            cur.execute(_SHAPE)
            rows = cur.fetchall()
    except psycopg2.Error as exc:
        raise live.Unavailable(f"{live.DSN_VAR} did not answer: {exc}") from exc

    # Grouped in Python rather than with an aggregate: the query already returns
    # the rows in (table, column) order, so this is a fold over a sorted stream,
    # and it keeps the SQL something a reader can check against the catalog docs.
    columns: dict[str, dict[str, str]] = collections.defaultdict(dict)
    estimate: dict[str, int] = {}
    for name, approx_rows, column, data_type in rows:
        columns[name][column] = data_type
        estimate[name] = approx_rows
    return tuple(Table(name, cols, estimate[name]) for name, cols in columns.items())
