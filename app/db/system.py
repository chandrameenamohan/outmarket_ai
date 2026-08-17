"""The system-role connection: one per process, one thread at a time, one door.

Two modules persist system state — `app/rules/store.py` (rules) and `app/dq/runs.py`
(run records) — against the same database, as the same role, under the same schema
override, with the same idempotent-DDL-on-connect trick. They had a connection each,
identical line for line apart from one word in an error message. That cost two
connects to Singapore at 1.16 s each (LT-1b) for one credential, and gave one
condition — "the system database is down" — two unrelated exception types, so a
caller had to catch both to mean it once.

THE ONLY THING THAT ACTUALLY DIFFERS between the two is the DDL, so that is the one
argument `cursor()` takes.

WHY IT HANDS BACK A CURSOR AND NEVER A CONNECTION. `app/api/server.py` serves on a
`ThreadingHTTPServer`, so two concurrent runs land in two threads — and psycopg2's
`with conn` is a TRANSACTION block whose exit COMMITS. Two threads sharing one
connection means thread B's exit commits thread A's half-written work, and one
thread's failed statement leaves the other's statements failing inside a transaction
it never started. Handing out a connection makes that the caller's problem in a place
the caller cannot see it; handing out a cursor puts the transaction and the lock in
the same `with`, so the two cannot be separated.

ponytail: one lock, held for the whole block. System writes therefore serialise
across the process. They are single-row INSERTs and one indexed SELECT against
tables that are only ever appended to, so the contention is milliseconds against a
1.16 s connect — the wrong thing to optimise first. Ceiling: a long transaction here
blocks every other system write. The upgrade path is `threading.local()` for `_CONN`,
which trades the lock for a connection per thread and the connect cost with it.

WHAT THIS IS NOT: the analysis path. That is `app/rules/schema.py::connect()`, a
different role with SELECT and nothing else (SPEC §3.1, app/db/roles.sql). The two
credentials are read in two modules, and neither can be reached from the other.
"""

from __future__ import annotations

import contextlib
import os
import re
import threading
from collections.abc import Iterator
from typing import Any

import psycopg2

# The write-capable role, and the ONLY module that names it (SPEC §3.1,
# app/db/roles.sql). Same database as the analysis path — INV-2's sibling constraint
# holds, an identifier is still verified against the database that will execute it —
# but a different role, holding no privilege whatsoever on `public`. The store is
# refused a write to `orders` by PostgreSQL, not by its own manners.
DSN_VAR = "SUPABASE_DB_URL_SYSTEM"

# The system schema. An override exists for exactly one reason, and it is a real one:
# the integration checks write real rows through the real front door, and an
# append-only table cannot be cleaned up afterwards. They point at a scratch schema so
# that `make check-ge` does not accumulate junk in the store the demo reads from.
SCHEMA_VAR = "DQ_SCHEMA"
DEFAULT_SCHEMA = "dq"

_CONN: Any = None

# The (schema, DDL) pairs already established on `_CONN`. A pair rather than a flag
# because one connection now carries two schemas' worth of DDL, and because pointing
# `DQ_SCHEMA` somewhere new has to re-establish both.
_ENSURED: set[tuple[str, str]] = set()

_LOCK = threading.Lock()


class Unavailable(RuntimeError):
    """The system database could not be reached. The operator's problem, not the author's."""


@contextlib.contextmanager
def cursor(ddl: str) -> Iterator[Any]:
    """A cursor in its own transaction, on the process's one system connection.

    The whole block runs under the lock — see the module docstring. `ddl` is the
    caller's own idempotent schema, established once per connection.
    """
    with _LOCK:
        conn = _connect(ddl)
        with conn, conn.cursor() as cur:
            yield cur


def sql(statement: str) -> str:
    """`{schema}` substituted by replacement rather than by `str.format`.

    Not a style choice: `app/rules/store.sql`'s own comments show a stored spec, and
    `{"type": ..., "kwargs": {...}}` is a format string full of unknown keys. One
    substitution rule for every statement, so nobody has to remember which of them
    may mention a brace.
    """
    return statement.replace("{schema}", schema())


def schema() -> str:
    name = os.environ.get(SCHEMA_VAR) or DEFAULT_SCHEMA
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise Unavailable(
            f"{SCHEMA_VAR}={name!r} is not a bare lowercase identifier, and it is substituted "
            "into SQL. Rename the schema rather than quoting it."
        )
    return name


def _connect(ddl: str) -> Any:
    """One connection for the process, with the caller's schema established on the way up.

    Connecting costs 1.16 s to Singapore (LT-1b), which is why it is not done per call.
    The DDL is idempotent and runs once per connection rather than through a migration
    tool — see the ceiling noted in `app/rules/store.sql`.
    """
    global _CONN
    dsn = os.environ.get(DSN_VAR, "")
    if not dsn:
        raise Unavailable(
            f"{DSN_VAR} is not set, so there is nowhere to store a rule or record a run. "
            "Load the environment (`set -a; . ./.env; set +a`) — see .env.example."
        )
    try:
        if _CONN is None or _CONN.closed:
            _CONN = psycopg2.connect(dsn, connect_timeout=15)
            _ENSURED.clear()
        if (established := (schema(), ddl)) not in _ENSURED:
            with _CONN, _CONN.cursor() as cur:
                cur.execute(sql(ddl))
            _ENSURED.add(established)
    except psycopg2.Error as exc:
        _CONN = None
        _ENSURED.clear()
        raise Unavailable(f"{DSN_VAR} did not answer: {exc}") from exc
    return _CONN
