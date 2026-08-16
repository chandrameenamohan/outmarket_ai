"""The live schema, read once per table. The thing an identifier is checked against.

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

import psycopg2

# Same variable app/dq/ge_runtime.py runs against, restated rather than imported:
# importing it from there would drag the framework into a module that has to work
# without it. `tests/test_inv2_authoring_rejection.py` pins the two together.
DSN_VAR = "SUPABASE_DB_URL_DIRECT"

# The table name is a bind parameter. It arrives from outside — ultimately from
# model output — and this is the only SQL this product composes itself.
_QUERY = """
    select column_name
      from information_schema.columns
     where table_schema = current_schema()
       and table_name = %s
"""


class Unavailable(RuntimeError):
    """The schema could not be read. An operator's problem, not the rule author's."""


class UnknownTable(LookupError):
    """No such table in the live schema — so no rule can be authored against it."""


@functools.cache
def columns(table: str) -> frozenset[str]:
    """The live column names of `table`, cached for the life of the process.

    Cached because a schema read is a round trip to Singapore and authoring asks
    for the same table repeatedly (LT-1b measured the RTT at 51 ms direct). The
    ceiling is the obvious one: a column added while the process is running is not
    seen until it restarts. That is the right trade for authoring — the cost of
    being briefly stale is a rule refused, and the cost of not caching is a round
    trip per proposal. `functools.cache` does not cache a raise, which is the
    behaviour that matters here: an unreachable database is retried, not remembered.
    """
    dsn = os.environ.get(DSN_VAR, "")
    if not dsn:
        raise Unavailable(
            f"{DSN_VAR} is not set, so no identifier can be checked against the live schema. "
            "Load the environment (`set -a; . ./.env; set +a`) — see .env.example."
        )
    try:
        with psycopg2.connect(dsn, connect_timeout=15) as conn, conn.cursor() as cur:
            cur.execute(_QUERY, (table,))
            found = frozenset(row[0] for row in cur.fetchall())
    except psycopg2.Error as exc:
        raise Unavailable(f"{DSN_VAR} did not answer: {exc}") from exc
    if not found:
        raise UnknownTable(
            f"{table!r} is not a table in the live schema. A table name that does not resolve "
            "is a hallucination as surely as a column name is."
        )
    return found
