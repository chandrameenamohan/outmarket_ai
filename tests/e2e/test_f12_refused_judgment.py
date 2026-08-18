"""B31 · a refused judgment must not destroy the unsaved proposals it was protecting.

Found by a hostile QA pass against the live deployment. Ten proposals for `payments` — a
~25 s billed model call — and pressing Reject with an empty reason produced the CORRECT
refusal ("a rejected rule must carry the reason it was rejected") and then took all ten
proposals off the screen with it. They had to be generated from scratch.

THE REFUSAL IS RIGHT; WHAT FOLLOWED IT WAS THE DEFECT. A guard that protects somebody
from a careless rejection must not charge them the work the rejection was about, and here
the charge was a paid model call and half a minute — which is exactly the tax that
teaches people to route around the guard.

WHAT IT IS NOT FIXED BY, AND THE CHECK BELOW WOULD PASS FOR THE WRONG FIX TOO: storing
the proposals. F3 keeps them unsaved on purpose, because a stored proposal implies
coverage that does not exist, and `tests/test_rule_suggestion.py` holds that door shut
from the other side — this file therefore also counts the store across the refusal, so a
fix that persisted its way out of the problem fails here rather than merely elsewhere.

WHY ITS OWN FILE. `tests/e2e/test_f12_translation_desk.py` is this screen's other six
directions and sits 14 lines under the 400-line cap, so a seventh does not fit; F12's
addresses and its billed ceiling are imported from `tests/fixtures_f12.py`, which is
where this screen's browser fixtures already live.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fixtures_f12 import BILLED_MS, PROPOSED, api_rules

from app.rules import store
from conftest import Driver

pytestmark = pytest.mark.e2e

# The desk's own proposal row, spelled as `scenario_steps.py` spells it — an unsaved
# proposal is the one population whose `data-row` can read `proposed`.
PROPOSED_ROW = "[data-row='proposed']"

# The judgment that needs a reason, and the field that is deliberately left empty.
REJECT = "button[value='rejected']"

# Where a refusal lands on this screen: the query string, rendered as a sentence
# (`web/app/tables/[table]/rules/actions.ts` says why it travels that way).
REFUSAL = ".refused"

# A NUMBER THAT IS AN ASSERTION ABOUT MONEY. A real proposal call is 6.6 s at its fastest
# (LT-2b) and took about 25 s on `payments` when this defect was found, so a refusal that
# came back inside five seconds cannot have made a second one — it re-rendered off the
# five-minute memo in `app/rules/suggest.py`. It is an absolute ceiling rather than a
# fraction of the first navigation because that navigation may itself be a memo hit,
# shared with the three other checks in this layer that need a selectable row, which
# would make the fraction a measurement of nothing.
NO_SECOND_CALL_S = 5.0


def test_a_refused_rejection_keeps_every_proposal_and_costs_no_second_call(
    driver: Driver, api_url: str
) -> None:
    """Generate proposals, reject one with no reason, and read the screen afterwards.

    Three claims, and each is the whole of somebody's complaint:

      the refusal is shown       the guard still fires, with the store's own sentence
      the proposals are intact   same statements, same evidence lines, same count
      nothing was re-generated   the round trip is too fast to contain a model call

    The evidence lines are counted rather than assumed present: a row that came back
    without one is LT-2b's proposal with the only thing that gives it away removed.
    """
    driver.page.goto(driver.base_url.rstrip("/") + PROPOSED, timeout=BILLED_MS)
    driver.page.wait_for_selector(PROPOSED_ROW, timeout=BILLED_MS)
    before = _rows(driver)
    assert before, (
        "no proposal rendered at ?propose=1, so every assertion below would be about an "
        "empty screen — the one outcome VERIFICATION §10 forbids."
    )
    stored_before = len(api_rules(api_url, _table(PROPOSED)))

    started = time.monotonic()
    driver.page.query_selector(f"{PROPOSED_ROW} {REJECT}").click()  # reason left blank
    driver.page.wait_for_selector(REFUSAL, timeout=BILLED_MS)
    took = time.monotonic() - started

    # The expected sentence is the writer's, called rather than copied: `judgeable` is
    # pure, it is the same function `judge_batch` asks before it writes anything, and a
    # literal here would be the second copy that drifts.
    rendered = driver.page.inner_text(REFUSAL).strip()
    assert _refusal_sentence() in rendered, (
        f"the screen says {rendered!r} after a rejection with no reason. The store refuses "
        f"that judgment with {_refusal_sentence()!r}, and the person who pressed the button "
        "is who it was written for."
    )

    after = _rows(driver)
    assert after == before, (
        f"{len(before)} proposal(s) were on screen and {len(after)} survived the refusal. "
        f"Gone: {sorted(set(before) - set(after))}. They cost a billed model call and they "
        "are not stored anywhere (F3), so a refusal that drops them charges the reader "
        "again for reading the guard's own sentence — which is how people learn to fill "
        "the reason box with a full stop."
    )

    assert took < NO_SECOND_CALL_S, (
        f"the refusal took {took:.1f} s to come back, and a model call is 6.6 s at its "
        f"fastest (LT-2b). The proposals are on the screen because they were generated "
        "AGAIN, which is the defect wearing the fix's clothes."
    )

    assert len(api_rules(api_url, _table(PROPOSED))) == stored_before, (
        "the store grew across a refused rejection. Proposals survive because the screen "
        "asks for them again off the memo, never because anything wrote them down — a "
        "stored proposal reports coverage this table does not have (F3)."
    )


def _rows(driver: Driver) -> list[tuple[str, str]]:
    """Every proposal on screen as (statement, evidence). Both, because both must survive."""
    return [
        (
            str(row.query_selector(".b-stmt").inner_text()).strip(),
            str(row.query_selector(".evidence").inner_text()).strip(),
        )
        for row in driver.page.query_selector_all(PROPOSED_ROW)
    ]


def _refusal_sentence() -> str:
    """The store's own words for a reasonless rejection, taken from the store."""
    try:
        store.judgeable(store.REJECTED, "")
    except ValueError as refused:
        return str(refused)
    raise AssertionError(
        "the store accepted a rejection carrying no reason, so this whole file is checking "
        "the behaviour of a guard that has stopped guarding (F12)."
    )


def _table(route: str) -> str:
    """`/tables/orders/rules?propose=1` -> `orders`. The one address, read rather than typed."""
    parts: Any = route.split("?")[0].strip("/").split("/")
    return str(parts[1])
