"""The live schema, read once per table. The thing an identifier is checked against.

It also owns `connect()`, the read-only door every analysis-path query goes through
(`app/dq/profile.py` and `app/db/tables.py` are the other callers). One module reads
`DSN_VAR` and one module opens the connection, so "the analysis path cannot write to
the tables under analysis" stays a fact about the CONNECTION — see the grants in
`app/db/roles.sql` and `tests/test_db_privilege_split.py`.

SPEC §3.1: *identifiers derived from model output are validated against the live
schema before interpolation, and generated SQL is parameterised.* This module is
the first half of that sentence and it obeys the second half itself — the table
name travels as a bind parameter, never as an f-string, because the one query in
here takes a value that came from outside.

WHY IT IS NOT IN THE VALIDATOR. `app/rules/validator.py` stays a pure function of
its arguments: that is what makes "a rejected spec writes nothing" a property of
its import graph rather than a claim about its control flow. So the reader lives
here, the validator takes the column set it produces, and the two are composed by
whoever is authoring — which is also the only place that knows which table is
being talked about.

WHY IT DOES NOT GO THROUGH app/dq/ge_runtime.py. This is not a Great Expectations
question, and routing it through the framework's door would make a plain
`information_schema` read depend on a ~3.2 s import and a process-global project
(INV-3). It also has to work where the framework is absent, which is every run of
`make check`.

ponytail: `current_schema()`, so the search path decides — the same ceiling
`app/dq/ge_runtime.py::_batch` already accepts, and for the same reason (the
framework's own `schema_name=` is deprecated in 1.20.0 and the demo database has
one schema). A table outside the search path is unreachable from both, together,
rather than from one of them in a way the other disagrees with. Upgrade path is
the connection string.
"""

from __future__ import annotations

import functools
import os
from typing import Any

import psycopg2

from app.db import unreachable

# Same variable app/dq/ge_runtime.py runs against, restated rather than imported:
# importing it from there would drag the framework into a module that has to work
# without it. `tests/test_inv2_authoring_rejection.py` pins the two together.
#
# It is the READ-ONLY role (SPEC §3.1, app/db/roles.sql). Validating an identifier
# is a read of `information_schema`, and this module is on the analysis path, so it
# arrives through a connection that cannot write to the table it is describing.
DSN_VAR = "SUPABASE_DB_URL_ANALYSIS"

# The table name is a bind parameter. It arrives from outside — ultimately from
# model output — and this is the only SQL this product composes itself.
#
# `ordinal_position`, so callers get the table's own column order. `app/dq/profile.py`
# builds one statement out of this list and reads the answer back positionally; a set
# would make that ordering an accident of hashing.
_QUERY = """
    select column_name, data_type
      from information_schema.columns
     where table_schema = current_schema()
       and table_name = %s
     order by ordinal_position
"""

# The columns that NAME a row rather than describe it — what F13 puts in front of
# *"#88231 −450.00"*, and what `app/dq/ge_runtime.py::run()` passes as
# `unexpected_index_column_names`. Same bind-parameter rule as the query above.
#
# `pg_catalog` AND NOT `information_schema`, and this one is a measured trap rather
# than a preference: `information_schema.table_constraints` shows only constraints
# on tables the current user owns or holds a privilege on OTHER THAN SELECT. This is
# the SELECT-only analysis role by design (SPEC §3.1, app/db/roles.sql), so the
# standard query returns an empty set for every table in the database and every
# offending value would silently lose its row identifier. `pg_index` is not filtered
# that way. `to_regclass` resolves through the search path — the same ceiling
# `column_types` accepts — and answers NULL rather than raising for a name that is
# not there. `unnest ... with ordinality` keeps a composite key in key order.
_PRIMARY_KEY = """
    select a.attname
      from pg_index i
      cross join lateral unnest(i.indkey::int2[]) with ordinality as k(attnum, ord)
      join pg_attribute a on a.attrelid = i.indrelid and a.attnum = k.attnum
     where i.indrelid = to_regclass(%s) and i.indisprimary
     order by k.ord
"""


class Unavailable(unreachable.Unreachable):
    """The schema could not be read. An operator's problem, not the rule author's."""


class UnknownTable(LookupError):
    """No such table in the live schema — so no rule can be authored against it."""


def connect() -> Any:
    """The read-only door to the analysis database — the only place its DSN is read.

    It lives here because this is already the module that owns `DSN_VAR`, and one
    reader means the analysis path cannot half-migrate to a different credential:
    `app/dq/profile.py` runs its statistics query and `app/db/tables.py` its schema
    listing through this function, so both are on the SELECT-only role by
    construction rather than by remembering.

    Not pooled and not cached. Profiling is cached for minutes (F2) and authoring
    reads a schema at most once per table, so the 1.16 s connect (LT-1b) is paid
    rarely — and a process-wide connection would be a shared mutable transaction
    for the sake of a cost nobody is paying twice.
    """
    dsn = os.environ.get(DSN_VAR, "")
    if not dsn:
        raise Unavailable(
            f"{DSN_VAR} is not set, so there is no read-only connection to the data. "
            "Load the environment (`set -a; . ./.env; set +a`) — see .env.example."
        )
    try:
        return psycopg2.connect(dsn, connect_timeout=15)
    except psycopg2.Error as exc:
        raise Unavailable.not_answering(DSN_VAR, exc) from exc


@functools.cache
def column_types(table: str) -> tuple[tuple[str, str], ...]:
    """`(name, sql_type)` for every column of `table`, in declaration order.

    Cached because a schema read is a round trip to Singapore and authoring asks
    for the same table repeatedly (LT-1b measured the RTT at 51 ms direct). The
    ceiling is the obvious one: a column added while the process is running is not
    seen until it restarts. That is the right trade for authoring — the cost of
    being briefly stale is a rule refused, and the cost of not caching is a round
    trip per proposal. `functools.cache` does not cache a raise, which is the
    behaviour that matters here: an unreachable database is retried, not remembered.

    A tuple rather than a dict because a cached mutable is a caller's rewrite of
    everyone else's schema.
    """
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(_QUERY, (table,))
            found = tuple((row[0], row[1]) for row in cur.fetchall())
    except psycopg2.Error as exc:
        raise Unavailable.not_answering(DSN_VAR, exc) from exc
    if not found:
        raise UnknownTable(
            f"{table!r} is not a table in the live schema. A table name that does not resolve "
            "is a hallucination as surely as a column name is."
        )
    return found


def columns(table: str) -> frozenset[str]:
    """The live column names of `table` — what an identifier is checked against."""
    return frozenset(name for name, _ in column_types(table))


@functools.cache
def primary_key(table: str) -> tuple[str, ...]:
    """The primary-key columns of `table`, in key order — empty if it has none.

    A rule run asks for these so an offending value arrives with the row it came
    from: *"−450.00"* is a number, *"#88231 −450.00"* is something a person can go
    and look at (SPEC F13, INV-4). Empty rather than an error, because a table
    without a key is still worth checking — the sample then carries values only.

    `column_types()` first, so an unreal table name fails the same way here as
    everywhere else rather than answering "no key". Cached for the same reason its
    neighbour is: a key does not change between two rule runs, and the round trip
    to Singapore costs more than the answer is worth twice.
    """
    column_types(table)
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(_PRIMARY_KEY, (table,))
            return tuple(str(row[0]) for row in cur.fetchall())
    except psycopg2.Error as exc:
        raise Unavailable.not_answering(DSN_VAR, exc) from exc
