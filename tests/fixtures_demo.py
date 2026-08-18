"""The stack the visual states are photographed on: the DEMO store, and nothing writing to it.

WHY A SECOND STACK RATHER THAN THE ONE EVERY OTHER BROWSER CHECK USES. Five of the six
visual states pended for one reason wearing five dresses — *a screenshot of a screen this
layer writes to is a photograph of a database.* The shared stack points at `dq_check`, and
this layer accepts rules into it by design (`test_draft_compile_does_not_persist_until_accept`
is that assertion), executes a run per session, and creates a held rule when none is held.
The store is append-only (F6), so none of them can clean up after itself: the review queue's
first baseline came out 1280x12430 with thirty-eight cards, most of them the same rule.

So the photographs are taken somewhere nothing writes. `seed/seed_demo_rules.py` seeds the
demo store `dq` — eight rules and two run records, one per STORED state those screens
render; the one state it cannot mint is an unsaved proposal, and the seeder says so — and
this module boots the product on it, on free ports, exactly the way SPEC §7's flow boots
its own (`scenario_stack`, which grew two arguments for this and says so). The only
difference is the one that matters: `reset=False`, because §7 needs a store nobody has
written to YET and this needs a store nobody will write to AGAIN.

**NOTHING HERE MAY BE HANDED TO A CHECK THAT WRITES.** Every navigation the visual states
make is a GET, and the one press among them (`choose_role`) sets a cookie. That is the
whole of the guarantee: the fixture is fixed because the fixture's readers only read. A
check that posted a judgment through this stack would put the demo store back where
`dq_check` is, and the next baseline would go red for a reason nobody could see on screen.

WHY THE IDS ARE DISCOVERED RATHER THAN WRITTEN DOWN HERE. A rule id is a uuid the store
mints, and a record id is minted by the run that wrote it — so a constant in this file
would be a copy of a fact, and the copy would be wrong the first time anyone reset the
demo schema. Both are read the way the product exposes them, off the demo stack's own API,
and they are the same on every run because the store behind them does not move.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

import scratch
from conftest import Driver, pending

# The demo's own store — `app/db/system.py::DEFAULT_SCHEMA`, i.e. what the product reads
# when nobody sets `DQ_SCHEMA`. Taken from `tests/scratch.py`, which is where the name that
# nothing here may WRITE to is already defined and guarded; the seeder is its only writer.
DEMO_SCHEMA = scratch.DEMO_SCHEMA

# The table the fixture tells its story about, and the one three of the five states are
# addressed by. `seed/seed_demo_rules.py` says why it is `orders`.
DEMO_TABLE = "orders"

SEED_COMMAND = "make demo-fixture"


@pytest.fixture(scope="module")
def demo(chromium: Any) -> Iterator[Any]:
    """The product, booted on the demo store, for the length of one test module.

    THE BOOTER IS IMPORTED INSIDE THE FUNCTION, and that is not style: this module is
    imported by `tests/conftest.py` — the file every layer loads, including the offline
    one — while `tests/e2e/scenario_stack.py` sits in a directory pytest only puts on the
    path once it has collected something from it. A module-level import here would make
    `make check` depend on collection order. By the time this body runs, the browser
    module that asked for it has been imported and the path is there.

    Depends on `chromium` for the reason `scenario_stack`'s own fixture does: it inherits
    the browser layer's entry condition, so `APP_URL` unset pends BEFORE two servers are
    started. Module-scoped because booting is seconds and photographing is milliseconds.
    """
    from scenario_stack import scenario_stack  # noqa: PLC0415 — see above

    with scenario_stack(DEMO_SCHEMA, reset=False) as stack:
        yield stack


@pytest.fixture
def demo_driver(chromium: Any, demo: Any) -> Iterator[Driver]:
    """A page in a fresh context, pointed at the demo stack. Read-only by contract."""
    context = chromium.new_context()
    yield Driver(page=context.new_page(), base_url=demo.app_url)
    context.close()


def _get(stack: Any, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{stack.api_url}{path}", timeout=60) as body:
        return dict(json.load(body))


@pytest.fixture(scope="module")
def demo_rule_id(demo: Any) -> str:
    """The rule the permalink state photographs, read off the demo store's own API.

    `rules[0]` is deterministic and not arbitrary: `app/rules/desk.py::workbench` orders
    by (state, id) and the demo store does not change, so this is the same rule on every
    run — the first accepted rule on `orders`. An EMPTY store pends naming the command
    rather than failing, because a demo fixture nobody has seeded is a missing setup step
    and not a defect in the product.
    """
    rules = _get(demo, f"/rules?table={DEMO_TABLE}")["rules"]
    if not rules:
        pending(
            f"the demo store `{DEMO_SCHEMA}` holds no rules for {DEMO_TABLE}, so the "
            f"data-dependent states have nothing fixed to photograph. Seed it: {SEED_COMMAND}"
        )
    return str(rules[0]["rule_id"])


@pytest.fixture(scope="module")
def demo_record_id(demo: Any) -> str:
    """The run record the record state photographs — the demo's own run of `orders`.

    A real one: `seed/seed_demo_rules.py` executed it through `server.plan()` and
    `run.stream()`, so the offending order ids on that screenshot are Great Expectations'
    output against 500,000 real rows rather than a fixture's imagination.
    """
    record = _get(demo, f"/records?table={DEMO_TABLE}")["record"]
    if not record:
        pending(
            f"the demo store `{DEMO_SCHEMA}` holds no run record for {DEMO_TABLE}, so the "
            f"record state has no fixed address to open. Seed it: {SEED_COMMAND}"
        )
    return str(record["record_id"])
