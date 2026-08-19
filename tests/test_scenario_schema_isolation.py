"""SPEC §7's stack schema belongs to a PROCESS, and the sweep never takes a live one.

The e2e half of bead `dq-mc0` costs three minutes and three billed model calls, twice
over, because the failure only shows up with two runners going at once. Both halves of
the fix are decidable without any of that: whether the name carries something unique to
the process, and whether the way-in sweep would take a schema out from under a run that
is still going. `tests/e2e/scenario_stack.py` argues why; this is what holds it.

The module under test sits in the directory pytest only puts on `sys.path` when it
collects the browser layer, so the path is stated here rather than assumed — the same
reason `tests/fixtures_demo.py` reaches it by a deferred import. Importing it is cheap
and connects to nothing: it names its DSN and token variables as strings precisely so
that collection costs no driver and no SDK.
"""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import REPO

E2E = str(REPO / "tests" / "e2e")
if E2E not in sys.path:
    sys.path.insert(0, E2E)

from scenario_stack import (  # noqa: E402 — the path above is what makes this importable
    LEGACY_SCHEMA,
    SCENARIO_PREFIX,
    SCENARIO_SCHEMA,
    _stale_scenario_schemas,
)


def _dead_pid() -> int:
    """A process id that certainly does not exist: one this process started and reaped.

    A large number picked out of the air would do the same job until the day it did not
    — pid ceilings differ per platform and are settable. This interpreter, doing nothing,
    is a few tens of milliseconds and needs nothing on PATH."""
    child = subprocess.Popen([sys.executable, "-c", ""])
    assert child.wait(timeout=60) == 0, "the child this asks for a spent pid did not exit"
    return child.pid


def test_the_scenario_schema_is_derived_from_this_process() -> None:
    """Not a literal. A literal is one schema for however many runners there are, and
    this one is DROPPED on the way in — so the second runner drops the first one's store
    and writes into it, which is exactly what `dq-mc0` recorded."""
    assert SCENARIO_SCHEMA == f"{SCENARIO_PREFIX}{os.getpid()}", (
        f"SPEC §7's stack schema is {SCENARIO_SCHEMA!r}, which does not name this process "
        f"({os.getpid()}). It is dropped and recreated on the way in, so a name two runs "
        "can share is two writers in one append-only store — bead dq-mc0."
    )
    assert SCENARIO_SCHEMA != LEGACY_SCHEMA


def test_the_sweep_leaves_a_running_scenario_alone() -> None:
    """The way-in sweep is the cleanup, so it is also the second chance to reintroduce
    the bug: dropping every `dq_scenario_*` it finds would take the store away from a run
    in flight, on the way in rather than by name collision. It may only take what no
    living process owns."""
    parent = f"{SCENARIO_PREFIX}{os.getppid()}"  # a live process that is not this one
    dead = f"{SCENARIO_PREFIX}{_dead_pid()}"
    names = [SCENARIO_SCHEMA, parent, dead, LEGACY_SCHEMA, "dq_check", "dq"]

    assert _stale_scenario_schemas(names) == [dead, LEGACY_SCHEMA], (
        "the sweep took the wrong set. It must leave every schema whose process is still "
        f"alive — this run's own {SCENARIO_SCHEMA!r} and a concurrent runner's {parent!r} "
        "— and every schema that is not a scenario schema at all, and take the ones no "
        f"process owns: {dead!r} and the pre-dq-mc0 literal {LEGACY_SCHEMA!r}."
    )
