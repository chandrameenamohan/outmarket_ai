"""Non-functional browser checks: console-clean, layout stability, accessibility,
visual regression.

These are the four that catch "looks fine, secretly broken" without a human
looking at anything. They run over the same route set as the behavioural checks
(F10, F11, F12, F14) and are deliberately parametrised over routes rather than
written once per screen — a new route should inherit them for free.

Three of the four are REAL as of B1: the shell renders on every route, so
console-clean, CLS and axe all have something true to say about it and say it.
The fourth, visual regression, pends per state on evidence read off the running
app — every state it names still renders the placeholder — see that test.
"""

from __future__ import annotations

import pathlib
import warnings
from typing import Any

import pytest

from conftest import Driver, pending

pytestmark = pytest.mark.e2e

ROUTES = [
    "/",
    "/tables",
    "/tables/orders/rules",
    "/review",
    "/rules/RULE_FIXTURE_ID",
    "/runs",
    "/runs/RECORD_FIXTURE_ID",
]
# The last two joined when LT-1b unblocked F13 (O-3: synchronous, progressive).

HERE = pathlib.Path(__file__).parent
AXE = HERE / "axe.min.js"  # vendored, MPL-2.0, banner intact — see the axe test

# What web/app/unbuilt.tsx renders on every route B1 does not own. Any route
# still showing it is a route whose product state does not exist yet.
SHELL_PLACEHOLDER = "is not built yet"


def _settled(driver: Driver, route: str) -> None:
    """Navigate and wait for the network to go quiet. Every check here starts here."""
    driver.goto(route)
    driver.page.wait_for_load_state("networkidle")


@pytest.mark.parametrize("route", ROUTES)
def test_console_is_clean(route: str, driver: Driver) -> None:
    """Zero console errors, zero unhandled rejections, zero failed network requests.

    The recorders (console / pageerror / requestfailed) are wired in the `driver`
    fixture before it yields, so they are watching during the first paint of this
    navigation — which is where the errors this check exists to catch actually
    happen. Cheapest high-yield check in the whole gate.
    """
    _settled(driver, route)
    assert driver.console_errors == [], f"{route} logged console errors: {driver.console_errors}"
    assert driver.failed_requests == [], f"{route} had failed requests: {driver.failed_requests}"


# Reads the same layout-shift entries Chrome reports as the Core Web Vital. It is
# registered as an INIT script, i.e. before any navigation, because `buffered:
# true` only replays shifts that happened after the observer's document existed —
# calling this after `goto` would measure a page that had already finished moving.
CLS_PROBE = """
window.__cls = 0;
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (!entry.hadRecentInput) window.__cls += entry.value;
  }
}).observe({ type: 'layout-shift', buffered: true });
"""

# Google's published "good" bar for Cumulative Layout Shift. Borrowed rather than
# invented: a threshold nobody can argue with is worth more than a stricter one we
# would have to defend. The shell measures 0.
CLS_BUDGET = 0.1


@pytest.mark.parametrize("route", ROUTES)
def test_no_layout_shift_on_first_paint(route: str, driver: Driver) -> None:
    """First paint must not move under the reader.

    Claimed as of B1 (VERIFICATION.md §8 listed it as unclaimed): the shell paints
    on every route, so the number exists and is checkable now. It is also the check
    most likely to catch a future regression by accident — a font swap, an image
    without dimensions, a banner that mounts late — none of which any other check
    in this file would notice.
    """
    driver.page.add_init_script(CLS_PROBE)
    _settled(driver, route)
    cls = driver.page.evaluate("window.__cls")
    assert cls <= CLS_BUDGET, f"{route} shifted {cls:.4f} on first paint (budget {CLS_BUDGET})"


@pytest.mark.parametrize("route", ROUTES)
def test_accessibility_has_no_violations(route: str, driver: Driver) -> None:
    """axe-core injected into the page and run in-page. Serious/critical fail.

    The bundle is vendored as ONE file, `tests/e2e/axe.min.js` (axe-core 4.13.0,
    MPL-2.0, copyright banner intact as that licence requires). Vendored rather
    than taken from `web/node_modules`: `tests/` is Python, and reaching sideways
    into a sibling toolchain's install directory for a runtime asset is how a test
    starts failing for reasons that have nothing to do with the app.

    Moderate and minor violations are WARNED, not failed — the impact scale is
    axe's own judgement call, and a gate that fails on `minor` teaches people to
    delete the gate. `warnings.warn` rather than `print` because pytest captures
    stdout and only replays it for a FAILING test, i.e. never at the moment the
    moderate list is the interesting part; the warnings summary prints on green.
    """
    _settled(driver, route)
    driver.page.add_script_tag(path=str(AXE))
    result: dict[str, Any] = driver.page.evaluate(
        "axe.run(document, { resultTypes: ['violations'] })"
    )
    blocking = [v for v in result["violations"] if v["impact"] in ("serious", "critical")]
    for v in result["violations"]:
        if v not in blocking:
            warnings.warn(
                f"axe {route}: {v['impact']} · {v['id']} · {len(v['nodes'])} node(s)",
                stacklevel=2,
            )
    assert not blocking, f"{route} axe violations: " + "; ".join(
        f"{v['impact']} {v['id']} at {v['nodes'][0]['target']}" for v in blocking
    )


# state -> the route it lives on. The eight states are VERIFICATION.md §4.3's list,
# unchanged: eight named states, not every screen at every breakpoint, because each
# baseline is a maintenance cost and has to earn itself.
STATES = {
    "role-door": "/",
    "tables-three-buckets": "/tables",
    "tables-bucket-two-errored": "/tables",
    "rules-catalog-collapsed": "/tables/orders/rules",
    "rules-proposal-needs-review-held": "/tables/orders/rules",
    "review-queue-with-caveat": "/review",
    "rule-permalink-standalone": "/rules/RULE_FIXTURE_ID",
    "run-record-in-flight": "/runs/RECORD_FIXTURE_ID",
}


@pytest.mark.parametrize("state", list(STATES))
def test_visual_regression_against_committed_baseline(state: str, driver: Driver) -> None:
    """Screenshot-and-diff each key state against a committed baseline. Not yet claimed.

    **The pend is read off the running app rather than hardcoded**, which is the
    only part of this worth having today. Every route in the shell still renders
    `web/app/unbuilt.tsx`, so a file called `tables-three-buckets.png` would be a
    picture of a paragraph saying F10 is not built — a baseline nobody could
    meaningfully approve, and one that would need re-approving the moment the state
    it is named after existed.

    So this navigates, looks, and reports which of the two it saw. It pends either
    way, deliberately: the day the placeholder disappears the PENDING line changes
    text and names the bead's next move, instead of the check going quietly green
    over a screen nothing has ever compared.

    ponytail: no diff yet. The Pillow tolerance mask, the baseline-write path and the
    `.actual.png` / `.diff.png` dump were written and exercised end to end (§4.3), then
    removed — with all eight states pending they were unreachable code the gate could
    not run. Ceiling: the first bead that ships a real screen has to approve a baseline
    anyway, and writes the diff in the same breath.
    """
    route = STATES[state]
    _settled(driver, route)
    unbuilt = SHELL_PLACEHOLDER in driver.page.inner_text("body")
    pending(
        f"{state} — {route} "
        + (
            "still renders the shell placeholder; a baseline of it would lock in a "
            "picture of an unbuilt screen"
            if unbuilt
            else "no longer renders the placeholder: this state is REAL. Write the "
            "baseline diff and approve the first screenshot once."
        )
    )
