"""F13's browser fixtures: a table with rules to run, and a run that finished.

They live beside `conftest.py` rather than in it, and are imported there so pytest
registers them. Two reasons, in order: the browser layer is the only caller, and
`conftest.py` is a shared file three features are adding to at once — it sits on the
400-line threshold `tests/test_code_quality_thresholds.py` enforces, and a fixture set
that belongs to one screen is the first thing that should move out of it.

They cost a real run of a real table against Supabase — about 17 s, once per session.
That is the price of checking a screen whose whole claim is that what it shows came out
of the data (VERIFICATION §10), and the table below is chosen to keep it to 17 s.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

import pytest

from conftest import pending

# The table the browser layer RUNS, and it is not `orders`: sessions of checking left
# that one with twenty-eight accepted rules, each submitted on its own (SPEC O-3) — 2 min
# 21 s, measured. `payments` is the same 500,000 rows and the same seeded defects with a
# rule set this file owns: three rules, 17 s, one per SHAPE F13 renders — one that passes,
# one that fails with real offending values (65,361 payments have no paid_at), and an
# aggregate, which carries no count at all and reports an observed value instead.
RUN_TABLE = "payments"
RUN_TABLE_SPECS: tuple[dict[str, Any], ...] = (
    {"type": "expect_column_values_to_not_be_null", "kwargs": {"column": "payment_id"}},
    {"type": "expect_column_values_to_not_be_null", "kwargs": {"column": "paid_at"}},
    {"type": "expect_table_row_count_to_be_between", "kwargs": {"min_value": 1}},
)


@pytest.fixture(scope="session")
def run_table(api_url: str) -> str:
    """`RUN_TABLE`, with the three rules above accepted — proposed here if they are not.

    IT SEEDS RATHER THAN DEMANDS, and only what is missing: a screen full of readings
    checked against a table with no accepted rules would be empty, and every absence
    assertion on it would pass. Seeding only the gap keeps it bounded — the store is
    append-only (F6), and appending unconditionally is how `orders` got to twenty-eight.
    """
    from app.db import system  # noqa: PLC0415 — psycopg2 and a DSN, neither owed to `make check`
    from app.dq import normalise  # noqa: PLC0415
    from app.rules import store  # noqa: PLC0415

    if not os.environ.get(system.DSN_VAR):
        pending(f"{system.DSN_VAR} is unset, so F13 has no store to accept its rules in")
    accepted = list(normalise.executable(store.revisions(table=RUN_TABLE)))
    for spec in RUN_TABLE_SPECS:
        if spec not in accepted:
            rev = store.propose(RUN_TABLE, spec["type"], spec["kwargs"])
            store.set_status(rev.rule_id, store.ACCEPTED)
    return RUN_TABLE


@pytest.fixture(scope="session")
def record(api_url: str, run_table: str) -> dict[str, Any]:
    """A COMPLETED run, executed for real through the door the product's own screen uses.

    NOT SEEDED, and this is the fixture where that matters most: F13's claim is that a
    failure can be judged from the sentence somebody vouched for, its size, and rows they
    can go and look at — all of which come out of Great Expectations against 500,000 real
    rows, and a hand-built record would check the renderer against the fixture's own
    imagination (VERIFICATION §10). Read back over HTTP because that is what a reload does.
    """
    started = urllib.request.Request(f"{api_url.rstrip('/')}/runs/{run_table}", method="POST")
    with urllib.request.urlopen(started, timeout=300) as body:
        events = [json.loads(line) for line in body if line.strip()]
    terminal = events[-1] if events else {}
    if terminal.get("event") != "completed" or not terminal.get("record_id"):
        pytest.fail(
            f"a run of {run_table} ended on {terminal!r} rather than on a stored record. F13 "
            "renders records; skipping here would report success on a run that did not happen."
        )
    with urllib.request.urlopen(
        f"{api_url.rstrip('/')}/records/{terminal['record_id']}", timeout=60
    ) as body:
        stored: dict[str, Any] = json.load(body)["record"]
    if not any(r["verdict"] == "failed" and r["evidence"] for r in stored["results"]):
        pytest.fail(
            f"the run of {run_table} found no failing rule with offending values: "
            f"{[(r['verdict'], r['statement']) for r in stored['results']]}. F13's acceptance "
            "is that a failure reads as something a non-engineer can judge, and a clean table "
            "cannot demonstrate it — check seed/MANIFEST.md is loaded."
        )
    return stored


@pytest.fixture(scope="session")
def record_id(record: dict[str, Any]) -> str:
    """The id the run above was stored under — F13's permalink, and the hygiene route."""
    return str(record["record_id"])


# THE SCREEN'S CONTRACT, IN ONE PLACE. They are DATA ATTRIBUTES rather than class names
# on purpose: a class is a styling decision somebody is entitled to change, and a check
# pinned to one turns a restyle into a red gate. They live here, with the fixtures that
# produce the run, because four browser modules read them — and two spellings of
# `[data-verdict="pending"]` in two files is how two checks come to address different DOM
# while both reporting green.
#
# `PENDING_ROW` is what the list looks like the instant a run is under way: every row
# pending. It is the selector `start_run` waits for, and it is a fact about the SCREEN
# rather than about the server — the rows go pending on the click, before the stream has
# said anything.
ROW = "[data-verdict]"
PENDING_ROW = '[data-verdict="pending"]'
SETTLED_ROW = ROW + ':not([data-verdict="pending"])'
RUN_BUTTON = "[data-run]"

# How long a run of a seeded table may take before a check gives up — ONE number for
# every waiter, where there used to be two (240 s and 300 s for the same wait). Measured
# at 17 s for this file's table and 2 min 21 s for the demo's own `orders`; the ceiling is
# deliberately far above both, because what it bounds is a network round trip to Supabase
# from wherever the gate is running, and a check that fails on a slow morning teaches
# people to re-run rather than to read. The billed-call ceiling is the other one, and it
# lives in fixtures_f12.py.
RUN_MS = 300_000


def start_run(driver: Any) -> None:
    """Press Run, and make sure the press LANDED.

    A React page is markup before it is an application, and Playwright will happily click
    a button whose handler has not been attached yet — the click is swallowed, no run
    starts, and the check that follows then reads the previous record's verdicts and calls
    them the new run's. That failure is silent, intermittent and reads like a product bug,
    which is the worst kind of check to leave in a gate.

    So the press is confirmed rather than assumed: the rows go pending the moment the
    handler runs, so waiting for one proves the click was received. A press that changed
    nothing is repeated, which is safe precisely because it changed nothing.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeout  # noqa: PLC0415

    for _ in range(5):
        driver.page.click(RUN_BUTTON)
        try:
            driver.page.wait_for_selector(PENDING_ROW, timeout=3_000)
        except PlaywrightTimeout:
            continue
        return
    raise AssertionError(
        "pressing Run never put the list into a pending state. Either the button's handler "
        "is not attached — the page is still markup — or a run no longer marks the readings "
        "it is about to replace, which is the stale window SPEC F13 forbids."
    )
