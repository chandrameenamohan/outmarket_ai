"""Non-functional browser checks: console-clean, layout stability, accessibility,
visual regression.

These are the four that catch "looks fine, secretly broken" without a human
looking at anything. They run over the same route set as the behavioural checks
(F10, F11, F12, F14) and are deliberately parametrised over routes rather than
written once per screen — a new route should inherit them for free.

Three of the four went REAL with B1: the shell renders on every route, so
console-clean, CLS and axe all have something true to say about it and say it.
The fourth, visual regression, went real with F14 (bead dq-rbf.1) — the first bead
that renders a screen rather than a placeholder. Every route now renders a real screen,
so nothing pends for being unbuilt any more.

**THE THREE HYGIENE CHECKS AND THE PHOTOGRAPHS NOW RUN ON DIFFERENT STACKS, AND THAT IS
THE POINT OF BEAD dq-vix.** Console errors, layout shift and axe violations are properties
of the CODE, so they belong on the shared stack the rest of this layer drives, whatever is
in its store. A photograph is not: five of the six states used to pend because what they
rendered was a function of an append-only store THIS LAYER WRITES TO, so the picture was
of a database. They now open the demo store instead — a fixed fixture, in a schema nothing
here writes to (`tests/fixtures_demo.py`, `seed/seed_demo_rules.py`). What this check
NEVER does is approve its own screenshot; see that test.
"""

from __future__ import annotations

import pathlib
import subprocess
import warnings
from typing import Any

import pytest

from conftest import REPO, Driver, choose_role, pending

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
#
# EVERY ROUTE HERE ANSWERS 200, AND THAT IS A CONSTRAINT ON THE LIST, not a coincidence.
# `/rules/not-a-uuid` and `/runs/not-a-uuid` now answer a real 404 with the not-found
# page (bead dq-abs), which is correct HTTP — and Chrome logs "Failed to load resource:
# the server responded with a status of 404" for the document itself, so adding one of
# them here would take `test_console_is_clean` red for the browser doing its job. A
# not-found route needs its own check with that entry allowed for, rather than a seventh
# parametrisation of this one.

HERE = pathlib.Path(__file__).parent
AXE = HERE / "axe.min.js"  # vendored, MPL-2.0, banner intact — see the axe test
BASELINES = HERE / "__baselines__"  # committed; .gitignore excludes the .actual.png beside them

# The one route above that names a thing rather than a screen. It stays a placeholder
# in ROUTES so the parametrised ids read the same on every machine, and is swapped for
# a real id at navigation time — a permalink to a rule that does not exist would test
# the 404 page, which is not the page any of these checks is about.
RULE_PLACEHOLDER = "RULE_FIXTURE_ID"

# The same arrangement for the run record, and it arrived with F13 (bead dq-klv.4). A
# record id cannot be a constant either: records are immutable and append-only, so the
# id in a URL is minted by the run that wrote it. `conftest.record` runs one and hands
# over what it stored, so these four checks meet the real screen — a `<details>`, a list
# of readings and a control that starts a run — instead of the page that says there is
# no such record.
RECORD_PLACEHOLDER = "RECORD_FIXTURE_ID"


# Routes whose screen belongs to the ENGINEER. A fresh context has chosen no role and
# therefore renders the domain expert's view (web/app/role.ts explains why that is the
# conservative default), and F10's `/tables` deliberately has no coverage dashboard in
# that view at all — F11: a domain expert never encounters a table list. A hygiene check
# arriving cold would be photographing, and measuring, a signpost. So these walk through
# the door first, by pressing it, exactly as a user does.
# Routes whose screen is DIFFERENT for the engineer, so a check that arrived with no role
# would photograph or audit the conservative view (web/app/role.ts). `/tables` is the
# coverage dashboard, which the domain expert's render does not fetch at all; the rules
# desk is F12's bilingual spread, and its second pane exists only here (SPEC Rev 0.4).
#
# THE TWO RUN SCREENS JOINED WITH BEAD dq-220, and the reason is coverage rather than
# tidiness. They used to render the same document for everybody — which was the bug: the
# raw framework panel is the engineer's, and the domain expert's page does not contain it
# at all now. Whichever role these checks arrive as, they audit ONE of the two documents,
# and the engineer's is the superset: it is the expert's markup plus the `<details>`
# panels, which nothing else puts under axe or under a layout-shift budget.
ENGINEER_ROUTES = {"/tables", "/tables/orders/rules", "/runs", "/runs/RECORD_FIXTURE_ID"}


def _settled(driver: Driver, route: str, rule_id: str, record_id: str) -> None:
    """Navigate and wait for the network to go quiet. Every check here starts here."""
    if route in ENGINEER_ROUTES:
        choose_role(driver, "engineer")
        # THE ROLE DANCE IS NOT THE ROUTE UNDER TEST. Choosing a role posts a server action
        # to `/` and then redirects, and the browser records the superseded request as a
        # failure — intermittently, which is worse than always: it reports an error against
        # whichever engineer route happened to lose the race. `/` has its own entry in
        # ROUTES and its own console check, so nothing is lost by starting the recorders
        # clean at the moment the navigation that matters begins.
        driver.console_errors.clear()
        driver.failed_requests.clear()
    driver.goto(route.replace(RULE_PLACEHOLDER, rule_id).replace(RECORD_PLACEHOLDER, record_id))
    driver.page.wait_for_load_state("networkidle")


@pytest.mark.parametrize("route", ROUTES)
def test_console_is_clean(route: str, driver: Driver, rule_id: str, record_id: str) -> None:
    """Zero console errors, zero unhandled rejections, zero failed network requests.

    The recorders (console / pageerror / requestfailed) are wired in the `driver`
    fixture before it yields, so they are watching during the first paint of this
    navigation — which is where the errors this check exists to catch actually
    happen. Cheapest high-yield check in the whole gate.
    """
    _settled(driver, route, rule_id, record_id)
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
def test_no_layout_shift_on_first_paint(
    route: str, driver: Driver, rule_id: str, record_id: str
) -> None:
    """First paint must not move under the reader.

    Claimed as of B1 (VERIFICATION.md §8 listed it as unclaimed): the shell paints
    on every route, so the number exists and is checkable now. It is also the check
    most likely to catch a future regression by accident — a font swap, an image
    without dimensions, a banner that mounts late — none of which any other check
    in this file would notice.
    """
    driver.page.add_init_script(CLS_PROBE)
    _settled(driver, route, rule_id, record_id)
    cls = driver.page.evaluate("window.__cls")
    assert cls <= CLS_BUDGET, f"{route} shifted {cls:.4f} on first paint (budget {CLS_BUDGET})"


@pytest.mark.parametrize("route", ROUTES)
def test_accessibility_has_no_violations(
    route: str, driver: Driver, rule_id: str, record_id: str
) -> None:
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
    _settled(driver, route, rule_id, record_id)
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


# state -> the route it lives on. SIX named states, not every screen at every
# breakpoint, because each baseline is a maintenance cost and has to earn itself.
#
# TWO STATES HAVE BEEN DELETED RATHER THAN APPROVED, FOR THE SAME REASON, AND THE SECOND
# ONE IS WHY THE FIRST ONE'S ARGUMENT IS WRITTEN DOWN. `_settled()` only navigates, so two
# states on one route are one photograph by construction:
#
#   `tables-bucket-two-errored` shared `/tables` with `tables-three-buckets`, and the two
#   written PNGs were byte-identical (md5 251d2012bccdbdc52ebb0341b5fbbd54, twice, on two
#   independent runs). Scoping the second shot to the bucket element was the alternative
#   and was not taken: it would still be a strict subset of the first image, i.e. the same
#   maintenance cost for the same information. The middle bucket is checked where it is
#   actually derived — `tests/test_table_coverage.py` for the derivation, INV-5's browser
#   check for its atom.
#
#   `rules-proposal-needs-review-held` shared `/tables/orders/rules` with
#   `rules-facing-panes`, and came out byte-identical too (md5
#   ed9a0d4cef028e8996b5aedf8cc9ffcf, on three independent runs). It also could not render
#   what it was named for: a proposal is a model call and the demo fixture makes none, so
#   the pane in its PNG read "Accept 0 — I vouch for each of these · 0 / 8" over an empty
#   list. Giving it a step that produced a real proposal was the alternative and was not
#   taken: a billed, non-deterministic call is the one thing a photograph may not depend
#   on. The proposal pane is checked where it is real — `tests/e2e/test_f12_translation_desk.py`.
#
# A baseline that cannot fail while its neighbour passes asserts nothing its neighbour does
# not, and approving both would have put a human signature on a duplicate.
STATES = {
    "role-door": "/",
    "tables-three-buckets": "/tables",
    # Renamed with bead dq-rbf.4. It was `rules-catalog-collapsed`, from F12's original
    # "collapsed by default" clause — which SPEC Rev 0.4 replaced with facing pages, so a
    # baseline named for a disclosure control would be a photograph of something that no
    # longer exists. Same state, correctly named.
    "rules-facing-panes": "/tables/orders/rules",
    "review-queue-with-caveat": "/review",
    "rule-permalink-standalone": "/rules/RULE_FIXTURE_ID",
    "run-record-in-flight": "/runs/RECORD_FIXTURE_ID",
}


# A pixel counts as changed when any channel moves more than this. Antialiasing and
# subpixel text rendering move a channel by a few units between runs of the SAME
# build; a real change moves whole regions by far more.
CHANNEL_TOLERANCE = 12

# And the screen has to change by more than this share of its pixels before the check
# calls it a regression. Not zero: a screenshot that must match bit for bit fails on a
# Chromium point release, and a check that cries wolf teaches people to delete it.
PIXEL_BUDGET = 0.002

# WHAT USED TO BE HERE: `DATA_DEPENDENT`, five states and one named reason each, all of
# them the same reason — the screen behind it was built and green behaviourally, and what
# it RENDERED was a function of an append-only store this layer writes to rather than of
# the code. Bead dq-vix removed the cause instead of the symptom: the photographs are now
# taken on the demo store, which is seeded once by `seed/seed_demo_rules.py` and written
# to by nothing here (`tests/fixtures_demo.py` holds the whole argument). The only
# thing a state can pend for now is the one that must never become automatic — nobody
# has looked at the picture yet.


def _approved(baseline: pathlib.Path) -> bool:
    """Is this baseline the picture a person staged — tracked, AND unmodified since?

    THE MACHINE THAT TOOK THE SCREENSHOT MAY NOT CERTIFY IT. Every other check here
    compares the app against something written down by a human; a visual baseline is
    the one artefact the run produces itself, so without this it would write a picture
    of whatever it rendered and start passing against it on the next run — a green
    check over an image nobody ever looked at, which is the exact shape VERIFICATION
    §10 exists to prevent.

    TWO QUESTIONS, BECAUSE THERE ARE TWO DOORS (bead `dq-zyt`). `git ls-files` answers
    *somebody staged this path*, which is the whole story the first time a state is
    photographed. It stops being the whole story the moment the screen changes: overwriting
    an already-tracked baseline leaves the PATH tracked, so the next run compares the new
    shot against ITSELF and goes green over a picture nobody has looked at — the same habit
    arriving through the second door, and it is not hypothetical (it is how `role-door.png`
    passed once). `git diff --quiet` asks the question that actually matters — *is the
    CONTENT the staged content* — so a re-shot baseline pends with the same sentence the
    untracked case gets, and a re-approval costs a person the same look the first one did.

    Both are read-only. A repository with no git (a tarball, a Docker layer) answers "no"
    to both and the state keeps pending, which is the right way round — the unapproved case
    must never be the silent one.

    ponytail: `git diff` compares the working tree against the INDEX, so `git add` alone is
    enough and a commit is not required. Ceiling: a staged-but-uncommitted approval survives
    exactly as long as the index does. That is the right trade — `git add` is the act the pend
    message asks for, and asking for a commit would make the check refuse a baseline a person
    had just looked at and staged.
    """
    return baseline.exists() and all(
        subprocess.run(argv, cwd=REPO, capture_output=True, check=False).returncode == 0
        for argv in (
            ["git", "ls-files", "--error-unmatch", str(baseline)],
            ["git", "diff", "--quiet", "--", str(baseline)],
        )
    )


@pytest.mark.parametrize("state", list(STATES))
def test_visual_regression_against_committed_baseline(
    state: str, demo_driver: Driver, request: pytest.FixtureRequest
) -> None:
    """Screenshot-and-diff each key state against a committed baseline.

    **A BASELINE IS NEVER SELF-APPROVED, AND THAT IS A MECHANISM.** The first time a
    state renders something real this writes the file and PENDS — and it keeps pending
    until the PNG is TRACKED BY GIT, because a person staging a file is the only signal
    available that a person looked at it (`_approved`, below). Writing is automatic;
    approving is not. Without that gate the run would photograph whatever it rendered
    and pass against its own photograph from the next run on.

    **IT IS THE DEMO STACK IN THE FRAME, NOT THE ONE THIS LAYER WRITES TO** (bead
    dq-vix). The three checks above take the shared stack, because a console error and a
    layout shift are properties of the code whatever is in the store. A photograph is
    not: five of these six states used to pend by name because the store behind them
    was one this layer appends to on every run, so the picture was of a database — the
    review queue's first shot was 12,430 pixels tall and held thirty-eight cards, most
    of them the same rule. `demo_driver` opens a fixed fixture instead, and the only
    reason left to pend is that nobody has looked at the picture yet.

    THE TWO ID FIXTURES ARE RESOLVED PER ROUTE, NOT PER SIGNATURE. Requesting them by
    signature made every state — `role-door` among them, whose route is `/` and holds
    neither placeholder — depend on a demo store that no make target seeds, so the one
    state with an approved baseline turned into a skip on a fresh clone. `getfixturevalue`
    asks for an id only where a placeholder says a route names a thing.

    ponytail: Pillow, imported inside the function, and a per-channel tolerance rather
    than a perceptual diff. Pillow is not a dependency of `make check` and must not
    become one by sitting at the top of a module the offline gate still imports at
    collection time — that exact mistake is why the first version of this was deleted
    (VERIFICATION.md §4.3). Ceiling: this compares pixels, so a layout that moved
    everything down four pixels is as red as a screen that lost its buttons. That is
    the right trade for six named states and the wrong one for eighty.
    """
    from PIL import Image, ImageChops  # noqa: PLC0415 — see the ponytail note above

    route = STATES[state]
    rule_id = request.getfixturevalue("demo_rule_id") if RULE_PLACEHOLDER in route else ""
    record_id = request.getfixturevalue("demo_record_id") if RECORD_PLACEHOLDER in route else ""
    _settled(demo_driver, route, rule_id, record_id)

    BASELINES.mkdir(exist_ok=True)
    baseline = BASELINES / f"{state}.png"
    actual = baseline.with_suffix(".actual.png")
    actual.write_bytes(demo_driver.page.screenshot(full_page=True))
    if not _approved(baseline):
        actual.replace(baseline)
        pending(
            f"{state} — baseline WRITTEN to {baseline.relative_to(REPO)} and NOT approved. "
            "Open it, decide whether that is the screen you meant, and `git add` it: being "
            "committed is what approval means here, and this check compares nothing until "
            "a person has done that."
        )

    before, after = Image.open(baseline).convert("RGB"), Image.open(actual).convert("RGB")
    assert before.size == after.size, (
        f"{state} changed size: baseline {before.size}, now {after.size}. The new shot is "
        f"kept at {actual.relative_to(REPO)} — look at it, then approve it or fix the page."
    )
    # Per-pixel WORST channel, then a histogram of it. `lighter` is a per-pixel max, so
    # summing the bins above the tolerance counts exactly the pixels that moved — and
    # it does it in C. The obvious `getdata()` loop is both slower and deprecated in
    # Pillow 12, which would put a removal warning in the gate's output.
    red, green, blue = ImageChops.difference(before, after).split()
    worst = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    moved = sum(worst.histogram()[CHANNEL_TOLERANCE + 1 :])
    share = moved / (before.size[0] * before.size[1])
    assert share <= PIXEL_BUDGET, (
        f"{state} moved {share:.2%} of its pixels (budget {PIXEL_BUDGET:.2%}). The new "
        f"screenshot is at {actual.relative_to(REPO)}; if the change was meant, replace the "
        "baseline with it and `git add` that as the approval — a replaced baseline PENDS "
        "until you do rather than quietly becoming the new truth (`_approved`)."
    )
    actual.unlink()
