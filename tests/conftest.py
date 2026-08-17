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
import os
import pathlib
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, NoReturn

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# No check ever writes to the schema the demo reads from. The rule store is
# append-only by design (F6), so a check that writes CANNOT clean up after itself —
# and an accepted junk rule would not merely be untidy, it would execute and count
# toward coverage. Set before any test imports app/rules/store.py.
#
# UNCONDITIONAL, not `setdefault`. `make check-ge` sources `.env` with `set -a`, and
# `DQ_SCHEMA` is a documented key in .env.example — so a `setdefault` guard is
# switched off by the very variable the setup instructions tell an operator to set,
# and the layer starts writing unremovable rules into the demo's own store. A debug
# escape hatch is not worth a guard that fails open on a supported configuration.
SCRATCH_SCHEMA = "dq_check"
os.environ["DQ_SCHEMA"] = SCRATCH_SCHEMA


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
def repo() -> pathlib.Path:
    return REPO


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
