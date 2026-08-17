"""The stack SPEC §7 runs on: its own store schema, its own two processes, its own ports.

WHY THE SCENARIO CANNOT USE THE STACK EVERY OTHER BROWSER CHECK USES. §7 opens on a
sentence no shared stack can satisfy twice: *"No rules exist."* The store is append-only
(F6) and every session of `make check-ui` adds to it — `orders` was at thirty-four
accepted rules when this was written — so a flow that asserts a rule count of zero, then
watches it become non-zero, needs a store nobody has written to. `DQ_SCHEMA` already
exists for exactly this class of problem (`app/db/system.py`), and it is read from the
PROCESS environment, so pointing the scenario at its own schema means giving it its own
Python process — and therefore its own Next process, because `DQ_API_URL` is read once
per process too (`web/app/api.ts`).

So this module boots the product twice over on two free ports. It is more machinery than
a check normally deserves, and the alternative was worse: resetting the shared schema
mid-session would delete the rules and records the F11, F13 and F14 fixtures are holding,
and would make every other check's outcome depend on whether this one ran first.

**IDEMPOTENT, NOT SELF-CLEANING, AND THAT IS A CHOICE.** The schema is dropped and
recreated on the way IN, so a second run is never polluted by a first, and whatever the
flow wrote is still there afterwards to be looked at when it goes red. Dropping it on the
way out would satisfy the same requirement and destroy the evidence, and a run of this
flow is the one place in the harness where the evidence is a real model's real output
against real data. `DROP SCHEMA ... CASCADE` is also the ONLY reset available: both stores
refuse DELETE and TRUNCATE by trigger, from every role including the owner.

THE DROP HAPPENS BEFORE THE SERVER STARTS, and that ordering is load-bearing rather than
tidy: `app/db/system.py` establishes its idempotent DDL once per connection and remembers
it, so a schema dropped underneath a process that has already connected is a schema
nothing will recreate.

NOTHING HERE TOUCHES THE DEMO DATABASE. `public` — `orders`, `customers`, `payments`,
500,000 rows and 3,950 planted defects (seed/MANIFEST.md) — is read-only to both roles and
is the same data every other check reads. What is disposable is the rule store, which is
ours.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from conftest import REPO, Driver, pending

# The scenario's own store schema. Never `dq` (the demo's) and never `dq_check` (the rest
# of the browser layer's) — this one is dropped on the way in, so it may not be a schema
# anything else is holding state in.
SCENARIO_SCHEMA = "dq_scenario"

# The system DSN, named here rather than imported, because importing `app.db.system` to
# read one string would pull psycopg2 into a module that pends when it is missing.
DSN_VAR = "SUPABASE_DB_URL_SYSTEM"

# How long each half of the stack gets to answer. The Python process pays a framework
# import plus the 1.16 s connect `serve()` does before it binds (LT-1b); Next pays a cold
# start against an already-built `.next`. Both are seconds, and the ceilings are generous
# because what they bound is a laptop under load, not a product claim.
API_BOOT_SECONDS = 180
WEB_BOOT_SECONDS = 120

# The `uv run` line VERIFICATION.md §1 documents and `make check-ge` uses. Great
# Expectations, SQLAlchemy and psycopg2 are not in the interpreter running the gate; uv
# resolves this set from its cache in well under a second once warm.
API_ARGV = (
    "uv run --no-project --with great-expectations --with sqlalchemy>=2 "
    "--with psycopg2-binary python3 -m app.api.server"
).split()

WEB_ARGV = ["npm", "--prefix", "web", "run", "start"]


@dataclass(frozen=True)
class Stack:
    """Where the scenario's own copy of the product is answering."""

    app_url: str
    api_url: str


@dataclass
class Child:
    """A booted process and the file its output went to, so a failure can quote it."""

    proc: subprocess.Popen[bytes]
    log: pathlib.Path
    what: str

    def tail(self, lines: int = 25) -> str:
        return "\n".join(self.log.read_text(errors="replace").splitlines()[-lines:])


@dataclass
class Scenario:
    """The stack, plus the browser the flow drives it with.

    `driver()` hands back a NEW context every time, and the flow uses three of them: the
    engineer, the domain expert, and the cold arrival that opens a pasted permalink. Role
    is remembered per device (`web/app/role.ts`), so two readers are two contexts — not one
    context with a toggle pressed between assertions.
    """

    stack: Stack
    browser: Any
    contexts: list[Any] = field(default_factory=list)

    def driver(self) -> Driver:
        context = self.browser.new_context()
        self.contexts.append(context)
        return Driver(page=context.new_page(), base_url=self.stack.app_url)

    def get(self, path: str) -> Any:
        """One read off the scenario's own API process — the surface the browser reads."""
        with urllib.request.urlopen(f"{self.stack.api_url}{path}", timeout=120) as body:
            return json.load(body)

    def rules(self) -> list[dict[str, Any]]:
        return list(self.get("/rules?table=orders")["rules"])


@pytest.fixture(scope="module")
def scenario(chromium: Any) -> Iterator[Scenario]:
    """One stack for the whole flow, driven by the session's browser. Module-scoped.

    THE STACK IS THE SCENARIO'S AND THE BROWSER IS NOT, and that asymmetry is a fact about
    Playwright rather than a preference: `sync_playwright()` cannot be entered twice in one
    process — the second raises *"Playwright Sync API inside the asyncio loop"* — so a
    scenario that launched its own browser ERRORED the moment any other browser check ran
    first. It does not need one anyway. `tests/conftest.py::chromium` already says why: the
    isolation boundary a browser check needs is the CONTEXT, not the process, and every
    context here is created fresh and pointed at this flow's own `app_url`.

    Depending on `chromium` also inherits the browser layer's entry condition — `APP_URL`
    unset pends before the stack is booted, which is the right order for a fixture that
    starts two servers and drops a schema.
    """
    with scenario_stack() as stack:
        live = Scenario(stack=stack, browser=chromium)
        yield live
        for context in live.contexts:
            context.close()


@contextlib.contextmanager
def scenario_stack() -> Iterator[Stack]:
    """A pristine store, an API process on it, and a Next process in front of that."""
    for variable in (DSN_VAR, "SUPABASE_DB_URL_DIRECT"):
        if not os.environ.get(variable):
            pending(
                f"{variable} is unset, so SPEC §7 has no database to run against. "
                "`make check-ui` sources ./.env; run it through the make target."
            )
    _reset_schema()
    api_port, web_port = _free_port(), _free_port()
    api_url, app_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    api = {"DQ_SCHEMA": SCENARIO_SCHEMA, "DQ_API_PORT": str(api_port)}
    web = {"PORT": str(web_port), "DQ_API_URL": api_url}
    with _process(API_ARGV, api, "the scenario's Python process") as python_process:
        _await(f"{api_url}/tables", API_BOOT_SECONDS, python_process)
        with _process(WEB_ARGV, web, "the scenario's Next process") as next_process:
            _await(app_url, WEB_BOOT_SECONDS, next_process)
            yield Stack(app_url=app_url, api_url=api_url)


def _reset_schema() -> None:
    """`DROP SCHEMA ... CASCADE`, before anything connects to it.

    The DDL in `app/rules/store.sql` and `app/dq/runs.sql` starts with `create schema if
    not exists`, so the API process rebuilds both tables and both append-only triggers on
    its first write. That is why this is a drop and not a delete: the triggers refuse
    DELETE and TRUNCATE from the owner too, which is what makes F6 a fact about the
    database — and it means the only honest reset is to take the whole schema away.
    """
    import psycopg2  # noqa: PLC0415 — a driver `make check` is not owed

    conn = psycopg2.connect(os.environ[DSN_VAR], connect_timeout=30)
    with contextlib.closing(conn), conn, conn.cursor() as cur:
        cur.execute(f"drop schema if exists {SCENARIO_SCHEMA} cascade")


def _free_port() -> int:
    """A port the operating system has just confirmed is free.

    Not a fixed number: `make check-ui` is normally run with the shared stack already on
    3000 and 8000, and a scenario that collided with it would fail in a way that reads
    like a product bug. The gap between closing this socket and the child binding is a
    race nobody else on a development machine is trying to win.
    """
    with contextlib.closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def _process(argv: list[str], environment: dict[str, str], what: str) -> Iterator[Child]:
    """A child in its own process group, writing to a file, killed as a group on the way out.

    TWO DETAILS THAT ARE NOT STYLE. `npm run start` execs `next start` as a CHILD, so
    terminating the npm process alone leaves a server holding the port — a process group
    is the platform's answer and costs one keyword argument. And the output goes to a FILE
    rather than to a pipe nobody is draining: a full pipe buffer stops the child, and a
    server that stopped talking because the gate stopped listening is the most confusing
    failure this file could produce.
    """
    fd, name = tempfile.mkstemp(prefix="spec7-", suffix=".log")
    log = pathlib.Path(name)
    with os.fdopen(fd, "wb") as handle:
        # `start_new_session` is what makes the group kill below safe as well as
        # effective: without it the child shares the gate's process group, and killing
        # the group would take the test runner with it.
        proc = subprocess.Popen(
            argv,
            cwd=REPO,
            env={**os.environ, **environment},
            stdout=handle,
            stderr=handle,
            start_new_session=True,
        )
    try:
        yield Child(proc=proc, log=log, what=what)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=20)


def _await(url: str, seconds: int, child: Child) -> None:
    """Poll until it answers, and FAIL with the child's own output when it never does.

    Any HTTP response counts as alive, exactly as `conftest.app_url` decides it: a 404 on
    `/` still means a server is there. A stack that was asked for and did not arrive is a
    failure and never a skip — the same contract the rest of the browser layer holds. A
    child that has already EXITED is not waited for: that is the common case (a missing
    build, a bad DSN) and it is reported the moment it happens rather than at the ceiling.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=10).close()
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            pass
        if child.proc.poll() is not None:
            raise AssertionError(
                f"{child.what} exited with {child.proc.returncode} before answering on {url}.\n"
                f"{child.tail()}"
            )
        time.sleep(0.5)
    raise AssertionError(
        f"{child.what} never answered on {url} within {seconds}s. If this is Next, the build "
        "may be missing — run ./init.sh.\n" + child.tail()
    )
