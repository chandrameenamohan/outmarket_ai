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

import os
import pathlib
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, NoReturn

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


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


@pytest.fixture
def driver(app_url: str) -> Iterator[Driver]:
    """Chromium pointed at the RUNNING app.

    Python playwright 1.57.0 is already installed and the chromium builds are
    already in the shared cache, so this needs no `pip install` and no
    `playwright install`. It never launches today: `app_url` pends first when
    APP_URL is unset, which is the whole point — no browser check may run
    against a stub.

    Fresh context per test, so F14's "no cookies, no prior navigation"
    requirement is the default rather than a special case.
    """
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context()
        drv = Driver(page=context.new_page(), base_url=app_url)

        def on_console(msg: Any) -> None:
            if msg.type == "error":
                drv.console_errors.append(msg.text)

        drv.page.on("console", on_console)
        drv.page.on("pageerror", lambda e: drv.console_errors.append(str(e)))
        drv.page.on("requestfailed", lambda r: drv.failed_requests.append(r.url))
        yield drv
        context.close()
        browser.close()


def source_files(*subdirs: str) -> list[pathlib.Path]:
    """Every gate-scoped Python file. learning-tests/ and seed/ are out of scope
    (one-shot empirical scripts — see pyproject.toml for why)."""
    out: list[pathlib.Path] = []
    for d in subdirs:
        root = REPO / d
        if root.exists():
            out += [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]
    return out
