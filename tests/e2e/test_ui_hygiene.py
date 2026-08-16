"""Non-functional browser checks: console-clean, accessibility, visual regression.

These are the three that catch "looks fine, secretly broken" without a human
looking at anything. They run over the same route set as the behavioural checks
(F10, F11, F12, F14) and are deliberately parametrised over routes rather than
written once per screen — a new route should inherit them for free.
"""

from __future__ import annotations

import pytest

from conftest import pending

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


@pytest.mark.parametrize("route", ROUTES)
def test_console_is_clean(route: str, driver) -> None:
    """Zero console errors, zero unhandled rejections, zero failed network requests.

    The recorder is wired in the `driver` fixture (console / pageerror / requestfailed),
    so this is:
        driver.goto(route); driver.page.wait_for_load_state("networkidle")
        assert driver.console_errors == []
        assert driver.failed_requests == []
    Cheapest high-yield check in the whole gate.
    """
    pending("no running app yet")


@pytest.mark.parametrize("route", ROUTES)
def test_accessibility_has_no_violations(route: str) -> None:
    """axe-core, injected into the page as a script and run in-page.

    NEEDS INSTALLING: the axe-core JS bundle (vendored as one file, no npm
    dependency on the python side) — there is no axe binding in the current
    environment. Until then this is not silently green, it is PENDING.
    Fail on serious/critical violations; log moderate ones.

    Deliberately does NOT request `driver`: that fixture pends first and would
    mask this reason with "APP_URL is unset". The blocker here needs a human to
    act (vendor the bundle), so it has to be the reason that reaches `-ra`. Add
    the `driver` parameter back at the same time as the bundle.
    """
    pending("axe-core bundle not vendored yet — vendor it as one JS file under tests/e2e/")


@pytest.mark.parametrize(
    "state",
    [
        "role-door",
        "tables-three-buckets",
        "tables-bucket-two-errored",
        "rules-catalog-collapsed",
        "rules-proposal-needs-review-held",
        "review-queue-with-caveat",
        "rule-permalink-standalone",
        "run-record-in-flight",
    ],
)
def test_visual_regression_against_committed_baseline(state: str, driver) -> None:
    """Screenshot each key state; diff against tests/e2e/__baselines__/<state>.png.

    First run WRITES the baseline and fails loudly (`BASELINE WRITTEN — a human
    must look at it once and commit it`). Thereafter a pixel diff over a
    threshold fails. The human approval happens exactly once per state, which is
    what keeps this deterministic rather than subjective.

    Deliberately narrow: eight states, not every screen at every breakpoint.
    Baselines are a maintenance cost and each one has to earn itself. The eighth,
    `run-record-in-flight`, earns it because a half-finished progressive run
    (LT-1b, O-3) is the state most likely to look plausible and be wrong.
    """
    pending("no running app yet — baselines cannot be established against a mockup")


def test_no_layout_shift_on_first_paint(driver) -> None:
    """Optional and currently unclaimed. Listed so it is a decision, not an oversight:
    worth adding only if a CLS problem actually shows up."""
    pending("not claimed — see VERIFICATION.md §8, deliberately not verified yet")
