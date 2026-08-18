"""One scratch schema per LAYER, and the two guards that keep them apart (bead dq-cyi.4).

`make check-ge` and `make check-ui` are both minutes long, both WRITE, and the rule store
is append-only (F6) — so a check that counts rules before and after an action is reading a
number the other layer can move. Run at the same time on one machine they took each other
red with nothing wrong with either; VERIFICATION §4.7.2 has the numbers. The assertion that
caught it — *"the store went from 89 rules to 91 on a refusal"* — is exactly right and is
untouched. What was wrong was two writers in one schema.

So the schema is a property of the LAYER, not of whoever exported `DQ_SCHEMA` last:

    ge    -> dq_check_ge    the GE layer's store and run-record integration checks
    e2e   -> dq_check       the browser layer, plus the API process it drives

The browser layer keeps the name it has always had, and the GE layer is the one that moves.
That asymmetry is deliberate rather than arbitrary: `dq_check` carries state the browser
fixtures lean on — an accepted `orders` rule, a held rule, run records — and `conftest.rule_id`
FAILS on an empty store by design, so handing that layer a virgin schema would break it on
its first run. Every GE check seeds what it reads, so the GE layer is the one that can start
from nothing.

TWO GUARDS, because there are two ways into the wrong schema and neither may be silent:

  `for_layers` reads the markers pytest actually COLLECTED. No target, shell or `.env` can
  point a layer somewhere else, and a process that collected both layers is refused before
  it writes a row — one process is one schema, and the refusal says which two it collected.

  `agrees` closes the cross-process hole, which is the browser layer's alone: its writes are
  split between pytest (`conftest.coverage_records`) and an API process a person starts by
  hand, and only a matching `DQ_SCHEMA` makes those two the same store. It asks the server
  for a record this process just wrote; a server on any other schema answers 404.

`reset()` is `make reset-scratch`. `DROP SCHEMA ... CASCADE` is the only reset an append-only
store has — both stores refuse DELETE and TRUNCATE by trigger, from the owner included — and
`dq_system` owns these schemas because `app/rules/store.py` created them, so dropping them
needs the system DSN and never the owner's (app/db/roles.sql).
"""

from __future__ import annotations

import contextlib
import os
import sys
import urllib.error
import urllib.request
from typing import Any

import pytest

VARIABLE = "DQ_SCHEMA"

# The store the demo reads and a reviewer looks at (`app/db/system.py::DEFAULT_SCHEMA`).
# No check may write here: the store is append-only, so it could not clean up after itself,
# and an accepted junk rule would execute and count toward coverage.
DEMO_SCHEMA = "dq"

# One schema per WRITING layer, keyed by the marker that names the layer.
LAYERS = {"ge": "dq_check_ge", "e2e": "dq_check"}

# `make check` collects neither layer and connects to nothing at all, so it borrows the
# browser layer's name rather than minting a third: a schema no check ever writes to would
# be a name to explain and a schema to clean.
DEFAULT = LAYERS["e2e"]


def pin(schema: str) -> str:
    """Point this process's store at `schema` — read per call by `app/db/system.py`.

    UNCONDITIONAL, never a `setdefault`. `DQ_SCHEMA` is a documented key in .env.example
    and both heavy targets source `.env` with `set -a`, so a pin that deferred to the
    environment would be switched off by the very variable the setup instructions tell an
    operator to set — and the layer would start writing unremovable rules into the demo's
    own store. A debug escape hatch is not worth a guard that fails open.
    """
    if schema == DEMO_SCHEMA:
        raise pytest.UsageError(
            f"a layer asked to be pinned at {DEMO_SCHEMA!r}, which is the store the demo "
            "reads and the one nothing here may write to. Scratch schemas are in "
            "tests/scratch.py::LAYERS."
        )
    os.environ[VARIABLE] = schema
    return schema


def for_layers(items: list[Any]) -> str:
    """The scratch schema belonging to the layer these collected items are from."""
    layers = sorted({mark for item in items for mark in LAYERS if item.get_closest_marker(mark)})
    if len(layers) > 1:
        raise pytest.UsageError(
            f"this run collected the {' and '.join(layers)} layers together, and they write to "
            f"different scratch schemas ({', '.join(LAYERS[mark] for mark in layers)}). One "
            "process can only be in one schema, so select one layer — `make check-ge` or "
            "`make check-ui`. Since dq-cyi.4 the two are independent and may be run at the "
            "same time, in two processes (VERIFICATION §4.7.2)."
        )
    return LAYERS[layers[0]] if layers else DEFAULT


def agrees(api_url: str, record_id: str) -> None:
    """Fail unless the API process behind `api_url` can see a record THIS process just wrote.

    The browser layer is two processes on one store, and only `DQ_SCHEMA` makes them one.
    Without this the mismatch is not an error anywhere — it is F10's middle bucket coming
    up empty and a check blaming the product for a variable somebody typed once.
    """
    try:
        urllib.request.urlopen(f"{api_url.rstrip('/')}/records/{record_id}", timeout=30).close()
    except urllib.error.HTTPError as exc:
        pytest.fail(
            f"the API process on {api_url} cannot see run record {record_id}, which this "
            f"process just wrote to {os.environ[VARIABLE]} ({exc}), so the two are on "
            f"different schemas. Start it with DQ_SCHEMA={os.environ[VARIABLE]} — the command "
            "is in VERIFICATION.md §1 — and never with the demo store or the GE layer's."
        )


def reset() -> None:
    """`make reset-scratch [ARGS='dq_check_ge ...']`: drop scratch schemas, as their owner.

    Every scratch schema by default, or the ones named on the command line — resetting one
    layer without disturbing the other is the common case, and the schema is interpolated
    into DDL, so the names are checked against `LAYERS` rather than quoted. That check is
    also what makes `ARGS=dq` an error instead of the worst thing this file could do.
    """
    import psycopg2  # noqa: PLC0415 — a driver `make check` is not owed

    known = sorted({*LAYERS.values(), DEFAULT})
    wanted = sys.argv[1:] or known
    if unknown := sorted(set(wanted) - set(known)):
        raise SystemExit(f"not a scratch schema: {unknown}. This target drops {known}, only.")

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL_SYSTEM"], connect_timeout=30)
    conn.autocommit = True
    with contextlib.closing(conn), conn.cursor() as cur:
        for schema in wanted:
            cur.execute(f"drop schema if exists {schema} cascade")
            print(f"dropped {schema}")
