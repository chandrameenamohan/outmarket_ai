"""Shared test fixtures and the one helper that keeps stubs honest.

`pending()` is the only sanctioned way to stub a check. It skips with a reason
that starts with "PENDING", which `-ra` prints on every run. A stub that quietly
passes would poison the whole harness, so there is deliberately no other route:
if a check cannot run yet, it says what it is waiting for.

That is a claim, so it is checked rather than trusted —
tests/test_code_quality_thresholds.py enumerates every other spelling of a skip
(mark.skipif, pytest.importorskip, the imperative pytest.xfail, and the bare
names you get from `from pytest import skip`) and fails the gate on all of them.
This file is the one exemption, because pending() is where pytest.skip is called.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, NoReturn

import pytest

import scratch

REPO = pathlib.Path(__file__).resolve().parent.parent

# No check writes to the schema the demo reads from, and no layer writes into another
# layer's. `tests/scratch.py` owns the names, the argument and the guards — including
# why this pin is unconditional rather than deferring to a `DQ_SCHEMA` in the environment.
scratch.pin(scratch.DEFAULT)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items: list[Any]) -> None:
    """Narrow that pin to the layer pytest actually SELECTED, or refuse to run at all.

    `trylast` because `-m` is itself implemented in this hook: without it we would see
    every collected item and `make check` would look like all three layers at once.
    """
    scratch.pin(scratch.for_layers(items))


def pending(what: str) -> NoReturn:
    """Skip with a loud, greppable reason. Never returns."""
    pytest.skip(f"PENDING — {what}")


@pytest.fixture(scope="session")
def app_url() -> str:
    """Base URL of the RUNNING app. Browser checks refuse to fake it.

    Two different outcomes, and the difference is the whole point:
      - APP_URL UNSET  -> PENDING. That is `make check` deliberately leaving the
        browser layer out; skipping is honest because nobody asked for it.
      - APP_URL SET but nothing answering -> FAIL, never skip. `make check-ui` is
        the only authority for "a UI feature works", so it may not report success
        when its one prerequisite is absent. Any HTTP response counts as alive —
        a 404 on `/` still means a server is there.
    """
    url = os.environ.get("APP_URL")
    if not url:
        pending("APP_URL is unset — browser checks drive the running app, never a static DOM")
    try:
        urllib.request.urlopen(url, timeout=5).close()
    except urllib.error.HTTPError:
        pass
    except OSError as exc:
        pytest.fail(
            f"APP_URL={url} does not answer ({exc}). The browser layer must not skip its way "
            "past a dead server — start the app, or unset APP_URL to leave the layer out."
        )
    return url


@pytest.fixture(scope="session")
def api_url() -> str:
    """Base URL of the RUNNING Python process behind the app. Same contract as `app_url`.

    The browser layer grew a second prerequisite with F14 (bead dq-rbf.1), and the
    reason is worth stating rather than discovering: a permalink that renders a rule's
    English statement, evidence line and actions has to READ a rule, so the screen is
    only real if the thing behind it is. A frontend that rendered a plausible rule from
    a fixture file would make `make check-ui` green against a lie, which VERIFICATION §10
    exists to prevent.

    Unset -> PENDING (the layer was not asked for). Set but silent -> FAIL, never skip.
    """
    url = os.environ.get("DQ_API_URL")
    if not url:
        pending("DQ_API_URL is unset — the rule screens read a real store, never a fixture")
    try:
        urllib.request.urlopen(f"{url.rstrip('/')}/rules", timeout=10).close()
    except urllib.error.HTTPError:
        pass  # a 422 for a missing ?table= still means the process is answering
    except OSError as exc:
        pytest.fail(
            f"DQ_API_URL={url} does not answer ({exc}). Start it with the command in "
            "VERIFICATION.md §1, or unset DQ_API_URL to leave the layer out."
        )
    return url


@pytest.fixture(scope="session")
def rule_id(api_url: str) -> str:
    """The id of a real stored rule, discovered the way the product exposes them.

    Read over HTTP rather than by importing `app.rules.store`, so the check depends on
    the same surface the browser does — if the read route breaks, this fails here
    instead of producing a green permalink check against a store the app cannot reach.

    An empty store FAILS. `make check-ui` claims a permalink renders a rule; with no
    rules there is nothing to render and skipping would report success on the strength
    of an empty database.
    """
    table = "orders"
    with urllib.request.urlopen(f"{api_url.rstrip('/')}/rules?table={table}", timeout=30) as body:
        rules = json.load(body)["rules"]
    if not rules:
        pytest.fail(
            f"the rule store behind DQ_API_URL={api_url} holds no rules for {table}, so no "
            "permalink can be opened. Propose one (app/rules/store.py::propose) and re-run; "
            "an empty store must not skip its way past F14."
        )
    return str(rules[0]["rule_id"])


@dataclass
class Driver:
    """A browser page plus the two recorders every UI check needs.

    Bundled rather than monkeypatched onto Page so the console/network evidence
    is part of the fixture's contract, not an attribute someone can forget to wire.
    """

    page: Any
    base_url: str
    console_errors: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)

    def goto(self, route: str) -> Any:
        return self.page.goto(self.base_url.rstrip("/") + route)


# The role door's own buttons. Choosing a view is done by PRESSING one of them rather
# than by writing the cookie into the context, which is a deliberate refusal to know
# how the role is stored: `web/app/role.ts` owns that, and a check that wrote the
# cookie itself would keep passing on the day the mechanism changed underneath it.
DOOR = ".door button[value='{role}']"

# The OTHER control that sets a role: the switch in the header, on every route. A device
# that has already chosen never sees the door again — `/` redirects past it — so a check
# that changes its mind mid-test has to use the same affordance a person would.
SWITCH = ".role-seg button[value='{role}']"


def choose_role(driver: Driver, role: str) -> None:
    """Be `role` from here on, whether or not this context has chosen before.

    Engineer-facing screens need it because the DEFAULT view is the domain expert's
    (web/app/role.ts explains why a cold arrival gets the conservative one), so a fresh
    context asking for `/tables` is a reader who has not said they want coverage — and
    F10's dashboard is deliberately not in that document at all.

    F12's desk needs the second half: it is the one screen BOTH users work on, so its
    checks look at it twice, and the second `choose_role` in a test arrives at a `/` that
    redirects to the role already chosen. Pressing the header switch instead is what a
    person does, and it is the control F11 promises can be reached from any screen.
    """
    driver.goto("/")
    # Wait for `/` to FINISH before pressing anything on it. Without this the door's form
    # submission can start while the page's own subresources are still in flight, and the
    # browser cancels them — which `test_console_is_clean` records as a failed request and
    # reports against whichever route the check was actually about. A race in the fixture
    # that fails the screen is the worst kind of red.
    driver.page.wait_for_load_state("networkidle")
    door = DOOR.format(role=role)
    driver.page.click(door if driver.page.query_selector(door) else SWITCH.format(role=role))
    # Wait for the HEADER to agree, rather than for the network to go quiet. The switch is
    # a server action that re-renders the page it was pressed on, so "idle" can be true
    # again before the new document arrives — and the next navigation then carries the old
    # cookie and the check reads the wrong role's screen. `aria-pressed` is the product's
    # own statement about which view this is, so waiting for it waits for the right thing.
    driver.page.wait_for_selector(
        f"{SWITCH.format(role=role)}[aria-pressed='true']", timeout=15_000
    )
    driver.page.wait_for_load_state("networkidle")


# One rule spec per verdict a seeded run needs. Two is the smallest number that can
# carry a HOLE — one rule reporting and another erroring — which is the case F10's
# middle bucket exists for and the one a single-rule fixture cannot express.
# They carry the bounds a real rule carries, and that is not tidiness either: a bounded
# type with neither bound is a spec `app/rules/validator.py::sanity` refuses, so it has
# no English sentence and could not have reached a record in the first place.
RUN_SPECS: tuple[dict[str, Any], ...] = (
    {
        "type": "expect_column_values_to_be_between",
        "kwargs": {"column": "order_total", "min_value": 0},
    },
    {"type": "expect_column_values_to_not_be_null", "kwargs": {"column": "customer_id"}},
)


def completed_run(
    table: str, verdicts: tuple[str, ...], scanned: int, total: int
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    """The `(specs, payload)` pair a finished run hands to `app/dq/runs.py::save()`.

    Written once here because two layers need the same shape for different reasons: the
    offline checks build records from it to assert the bucket derivation, and the
    browser layer writes them to the scratch schema so the screen has something true to
    render. Both go through `runs.record()`, which recomputes the roll-up status and the
    coverage count — so a fixture cannot state a combination a real run could not produce.
    """
    from app.dq import status  # noqa: PLC0415 — pure, and the only writer of an atom
    from app.rules import catalog  # noqa: PLC0415 — json and pathlib, no framework

    specs = RUN_SPECS[: len(verdicts)]
    return specs, {
        "table": table,
        "scanned_rows": scanned,
        "total_rows": total,
        "results": [
            {
                "spec": spec,
                "verdict": verdict,
                # THROUGH THE PRODUCT'S OWN WRITERS, BOTH OF THEM, because a fixture that
                # can write a record the product cannot render honestly is a fixture that
                # hides a class of bug — and this one did, twice. `verdict.upper()` was a
                # SECOND WRITER of a status atom: it produced a bare "ERRORED" on a run
                # that scanned 10,000 of 50,000 rows, so F13's page rendered a verdict
                # with no sampling clause in it (INV-5) and nothing anywhere else on the
                # row said so. And with no `statement` the same page was naked chips with
                # nothing to judge, one click from F10 (INV-4). A real run composes both
                # in `app/dq/normalise.py::Result.record()`; this composes them the same
                # way, from the same two modules.
                "status": status.status_atom(status.RuleResult(verdict, scanned, total)),  # type: ignore[arg-type]
                "statement": catalog.english(spec["type"], spec["kwargs"]),
            }
            for spec, verdict in zip(specs, verdicts, strict=True)
        ],
    }


# The ONE run record no real run can produce: `customers`, where a rule blew up AND the
# scan was partial. Both facts on one record on purpose — it is the middle bucket by
# either route, and it is the only row in the demo that can carry INV-5's sampling
# clause, because the shipped cap is off (SPEC O-2).
#
# Nothing else is seeded, and that is the restraint that matters. The other two buckets
# are produced by the product itself: a table nobody has run is bucket one for free, and
# a real run is bucket three. Writing records for those would be a fixture standing in
# front of the thing under test — and, since a record is the LATEST record, it would also
# displace whatever a real run had just written.
#
# The row counts are seed/MANIFEST.md's. They are this run's own account of what it saw
# rather than a reading of the table, but they are the real numbers, because a screenshot
# of this screen is a screenshot of the demo.
SEEDED_RUNS: tuple[tuple[str, tuple[str, ...], int, int], ...] = (
    ("customers", ("errored", "passed"), 10_000, 50_000),
)


@pytest.fixture(scope="session")
def coverage_records(api_url: str) -> dict[str, Any]:
    """The one run record F10's middle bucket needs, written through the product's own writer.

    WHY THIS SEEDS RATHER THAN EXECUTES. A real run against the demo produces a full
    scan in which every rule reports — bucket three, every time. Nothing in the shipping
    configuration can produce the middle bucket: the row cap is off (SPEC O-2) so no run
    is sampled, and no seeded table makes a catalog rule blow up. The bucket that exists
    to say "a result exists, a verdict does not" would therefore be checked by nothing,
    which is the one outcome VERIFICATION §10 forbids. So the condition is created, in
    the scratch schema, through `runs.save()` — the same door a run uses, which validates
    the payload and derives the status and the coverage count itself.

    Records are immutable and append-only (F9), so this cannot clean up after itself and
    does not try: each run of the browser layer appends one more record per table and the
    newest is the one the screen reads. It writes to the browser layer's own scratch
    schema (`tests/scratch.py`), never to the store the demo reads from — and it checks
    that the API process is in that same schema rather than assuming it.

    Depends on `api_url` so it never runs during `make check`, and on a DSN it refuses to
    guess at: unset -> PENDING naming the line that sets it; set and silent -> the store's
    own `Unavailable`, which is a failure and not a skip.
    """
    from app.db import system  # noqa: PLC0415 — psycopg2 and a DSN, neither owed to `make check`
    from app.dq import runs  # noqa: PLC0415

    if not os.environ.get(system.DSN_VAR):
        pending(
            f"{system.DSN_VAR} is unset, so F10's buckets have no records to be derived from. "
            "`make check-ui` sources ./.env; run it through the make target, or export it."
        )
    saved = {
        table: runs.save(*completed_run(table, verdicts, scanned, total))
        for table, verdicts, scanned, total in SEEDED_RUNS
    }
    # ONE STORE, TWO PROCESSES, and `DQ_SCHEMA` is the only thing making them one — a
    # mismatch is otherwise not an error anywhere, just F10's middle bucket coming up
    # empty and blaming the product for a variable somebody typed once.
    for written in saved.values():
        scratch.agrees(api_url, written.record_id)
    return saved


@pytest.fixture(scope="session")
def chromium(app_url: str) -> Iterator[Any]:
    """One headless Chromium per session. Never launches when `app_url` pends first.

    Python playwright 1.57.0 is already installed and the chromium builds are
    already in the shared cache, so this needs no `pip install` and no
    `playwright install`.

    Session-scoped because the isolation boundary a browser check needs is the
    CONTEXT — cookies, storage, permissions — not the process. Launching a
    process per test cost about a second each across ~43 checks and bought
    nothing.
    """
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def driver(chromium: Any, app_url: str) -> Iterator[Driver]:
    """A page in a fresh context, pointed at the RUNNING app.

    Fresh context per test, so F14's "no cookies, no prior navigation"
    requirement is the default rather than a special case.

    The three recorders are wired BEFORE the fixture yields, which is the only
    moment that works: they are attached to a page that has not navigated
    anywhere, so an error thrown during the first paint of the first navigation
    is recorded. Wire them after a `goto` and `test_console_is_clean` becomes
    blind to exactly the class of bug it exists to catch.
    """
    context = chromium.new_context()
    drv = Driver(page=context.new_page(), base_url=app_url)

    def on_console(msg: Any) -> None:
        if msg.type == "error":
            drv.console_errors.append(msg.text)

    drv.page.on("console", on_console)
    drv.page.on("pageerror", lambda e: drv.console_errors.append(str(e)))
    drv.page.on("requestfailed", lambda r: drv.failed_requests.append(r.url))
    yield drv
    context.close()


def module_constant(relative: str, name: str) -> Any:
    """Read one module-level literal out of a source file, without importing it.

    `app/dq/ge_runtime.py` imports Great Expectations at module level, so `make
    check`'s interpreter cannot import it — and the two facts that module owns which
    the offline gate has to pin (the shipping `result_format`, and the row cap that
    is INV-5's origin) are plain literals sitting at its top. `ast.literal_eval` on
    the assignment reads exactly what will run, which a text scan cannot claim.
    """
    tree = ast.parse((REPO / relative).read_text(), filename=relative)
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        targets = [target] if target else getattr(node, "targets", [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets) and node.value:  # type: ignore[attr-defined]
            return ast.literal_eval(node.value)  # type: ignore[attr-defined]
    raise AssertionError(f"{relative} declares no module-level {name}")


def source_files(*subdirs: str) -> list[pathlib.Path]:
    """Every gate-scoped Python source file. learning-tests/ and seed/ are out of
    scope (one-shot empirical scripts — see pyproject.toml for why)."""
    out: list[pathlib.Path] = []
    for d in subdirs:
        root = REPO / d
        if root.exists():
            out += [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]
    return out


# F12's and F13's browser fixtures live next door and are imported here so pytest
# registers them — `held_rule` is the row F12 must render with no checkbox, and `record`
# and `record_id` are what the run-record route and its hygiene checks are addressed by.
# See those two files for why they are not in this one.
# B25's are the other half of the same argument: the two below WRITE, so the screens they
# set up cannot be photographed. `fixtures_demo` boots the product on the DEMO store — the
# one nothing here writes to — and is what the visual-regression states are addressed by.
from fixtures_demo import demo, demo_driver, demo_record_id, demo_rule_id  # noqa: E402, F401
from fixtures_f12 import api_rules, held_rule  # noqa: E402, F401
from fixtures_f13 import record, record_id, run_table  # noqa: E402, F401
