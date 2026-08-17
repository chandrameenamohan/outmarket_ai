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
so nothing pends for being unbuilt any more; six of the seven states pend because what
they render is not a function of the code alone, and each says which way by name. What
this check NEVER does is approve its own screenshot; see that test.
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
ENGINEER_ROUTES = {"/tables", "/tables/orders/rules"}


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


# state -> the route it lives on. SEVEN named states, not every screen at every
# breakpoint, because each baseline is a maintenance cost and has to earn itself.
#
# It was eight until this bead. `tables-bucket-two-errored` mapped to `/tables`, exactly
# as `tables-three-buckets` does, and `_settled()` only navigates — so the two states
# were the same full-page photograph by construction, and the two written PNGs were
# byte-identical (md5 251d2012bccdbdc52ebb0341b5fbbd54, twice, on two independent runs).
# A baseline that cannot fail while its neighbour passes asserts nothing its neighbour
# does not, and approving both would have put a human signature on a duplicate. Scoping
# the second shot to the bucket element was the alternative and was not taken: it would
# still be a strict subset of the first image, i.e. the same maintenance cost for the
# same information. The middle bucket is checked where it is actually derived —
# `tests/test_table_coverage.py` for the derivation, INV-5's browser check for its atom.
STATES = {
    "role-door": "/",
    "tables-three-buckets": "/tables",
    # Renamed with bead dq-rbf.4. It was `rules-catalog-collapsed`, from F12's original
    # "collapsed by default" clause — which SPEC Rev 0.4 replaced with facing pages, so a
    # baseline named for a disclosure control would be a photograph of something that no
    # longer exists. Same state, correctly named.
    "rules-facing-panes": "/tables/orders/rules",
    "rules-proposal-needs-review-held": "/tables/orders/rules",
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

# States whose rendered content is not a function of the code alone. `rule_id` resolves
# to whichever rule the store hands over first, so that screenshot is a picture of a
# RULE rather than of a screen, and committing one would go red the next time anybody
# proposes a rule with a lower id. Named here rather than skipped quietly — the fix is a
# fixed demo rule, which bead dq-cyi.2 (B23) needs for its own reasons.
DATA_DEPENDENT = {
    # F10's screen, named with THIS bead — and it is the same reason as F12's below,
    # arrived at the same way: the screen was built, the shot was taken, and the picture
    # turned out to be of a database. Every row carries `accepted_rules`, and this layer
    # accepts rules (`test_draft_compile_does_not_persist_until_accept` saves one per run
    # by design); the middle bucket's row carries the RECORD ID of a record
    # `conftest.coverage_records` mints fresh every session, rendered as link text. Two
    # things that are supposed to differ, on every run, in the same 1280x727 frame.
    "tables-three-buckets": (
        "every row states how many accepted rules the table has and this layer accepts "
        "rules, and the middle bucket's row prints the id of a record minted by the "
        "fixture this session — so the shot differs from the last one in two places that "
        "are SUPPOSED to differ. It needs B23's fixed demo data, like the four below"
    ),
    # F11's, named with this bead for the same reason and with the loudest evidence: the
    # written PNG was 1280x12430 and 1.3 MB — thirty-eight cards, most of them the same
    # rule, accumulated by repeated runs of this layer into an append-only store (F6).
    "review-queue-with-caveat": (
        "the queue renders every rule anybody has flagged, and the store is append-only "
        "(F6) while THIS LAYER WRITES TO IT — the first shot was 12,430 pixels tall and "
        "held thirty-eight cards, most of them duplicates left by earlier runs. That is a "
        "photograph of a database, and it would go red on the next run of the target that "
        "produced it. B23's fixed demo data is what makes this screen photographable"
    ),
    "rule-permalink-standalone": (
        "the rule it renders is whichever the store hands over first, so a baseline of it "
        "would be a picture of one rule and would break when another is proposed. It needs "
        "a fixed demo rule id (B23) before a screenshot of it means anything"
    ),
    # F12's two states, named with bead dq-rbf.4 — the bead that finally rendered the
    # screen underneath them, which is also what made the problem visible.
    "rules-facing-panes": (
        "the desk renders every rule the table has, and THIS LAYER WRITES RULES: "
        "fixtures_f12.held_rule creates one when none is held, and "
        "test_draft_compile_does_not_persist_until_accept saves one on every run by "
        "design — the store is append-only (F6), so neither can clean up after itself. A "
        "baseline here would be a photograph of a database rather than of a screen, and "
        "it would go red on every run. It needs the fixed demo table B23 already needs"
    ),
    "rules-proposal-needs-review-held": (
        "the same screen and the same reason, doubled: the held row it is named for sits "
        "in a list whose length changes every session, and the proposals above it come "
        "from a model call whose wording is not a function of the code. B23's fixed demo "
        "data is what makes both photographable"
    ),
    "run-record-in-flight": (
        "a run record's id and the moment it finished are ON the screen, and both are minted "
        "by the run that wrote it — records are immutable, so the fixture executes a new one "
        "each session and every screenshot differs from the last in two places that are "
        "supposed to differ. The mid-flight state is worse still: which rules have settled "
        "depends on how far a real 17 s run had got when the shutter opened. Both need a "
        "FIXED demo record (B23), which is the same thing the rule permalink needs and for "
        "the same reason — until then a baseline here would go red on every run and teach "
        "people to re-approve it without looking, which is the one habit this check exists "
        "to prevent"
    ),
}


def _approved(baseline: pathlib.Path) -> bool:
    """Is this baseline tracked by git — i.e. has a person put their name on it?

    THE MACHINE THAT TOOK THE SCREENSHOT MAY NOT CERTIFY IT. Every other check here
    compares the app against something written down by a human; a visual baseline is
    the one artefact the run produces itself, so without this it would write a picture
    of whatever it rendered and start passing against it on the next run — a green
    check over an image nobody ever looked at, which is the exact shape VERIFICATION
    §10 exists to prevent.

    `git ls-files` is read-only and asks the one question that has a real answer:
    somebody staged this file. A repository with no git (a tarball, a Docker layer)
    answers "no" and the state keeps pending, which is the right way round — the
    unapproved case must never be the silent one.
    """
    found = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(baseline)],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    return baseline.exists() and found.returncode == 0


@pytest.mark.parametrize("state", list(STATES))
def test_visual_regression_against_committed_baseline(
    state: str, driver: Driver, rule_id: str, record_id: str
) -> None:
    """Screenshot-and-diff each key state against a committed baseline.

    **A BASELINE IS NEVER SELF-APPROVED, AND THAT IS A MECHANISM.** The first time a
    state renders something real this writes the file and PENDS — and it keeps pending
    until the PNG is TRACKED BY GIT, because a person staging a file is the only signal
    available that a person looked at it (`_approved`, below). Writing is automatic;
    approving is not. Without that gate the run would photograph whatever it rendered
    and pass against its own photograph from the next run on.

    **What a state pends FOR is named, one reason per state** (`DATA_DEPENDENT`), and
    every one of them says the same thing in a different way: the screen behind it is
    built and what it renders is not a function of the code alone. A baseline of one of
    those is a photograph of a database — it goes red on the next run and teaches people
    to re-approve without looking, which is the one habit this check exists to prevent.
    They clear together, with B23's fixed demo data.

    ponytail: Pillow, imported inside the function, and a per-channel tolerance rather
    than a perceptual diff. Pillow is not a dependency of `make check` and must not
    become one by sitting at the top of a module the offline gate still imports at
    collection time — that exact mistake is why the first version of this was deleted
    (VERIFICATION.md §4.3). Ceiling: this compares pixels, so a layout that moved
    everything down four pixels is as red as a screen that lost its buttons. That is
    the right trade for eight named states and the wrong one for eighty.
    """
    from PIL import Image, ImageChops  # noqa: PLC0415 — see the ponytail note above

    route = STATES[state]
    _settled(driver, route, rule_id, record_id)
    if state in DATA_DEPENDENT:
        pending(f"{state} — {DATA_DEPENDENT[state]}")

    BASELINES.mkdir(exist_ok=True)
    baseline = BASELINES / f"{state}.png"
    actual = baseline.with_suffix(".actual.png")
    actual.write_bytes(driver.page.screenshot(full_page=True))
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
        "baseline with it and commit that as the approval."
    )
    actual.unlink()
