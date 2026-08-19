"""SPEC §7 steps 1 to 6: everything that happens before a rule has ever executed.

One function per step, with the assertions beside the DOM they read. They live next door to
`test_spec_section_7.py` for the reason `fixtures_f12.py` and `fixtures_f13.py` live next
door to `conftest.py`: `tests/test_code_quality_thresholds.py` caps a file at 400 lines, the
flow plus its steps is past that, and the file that has to stay readable is the one holding
the scenario. Steps 7 and 8 are in `scenario_run.py`, split at the seam between a store
being filled and a suite being run.

WHAT IS ASSERTED WHERE. Each step asserts the facts of its own screen. The SEAM between
them is asserted in the test function itself, because that is the only thing eight
independent checks could not have proven between them.

Nothing here seeds a condition. Every state the flow needs was produced by the step before
it, through the product, in a browser.
"""

from __future__ import annotations

from typing import Any

from fixtures_f12 import BILLED_MS, DRAFT, PROPOSED, REFUSAL, RULES, answered, translate
from scenario_stack import Scenario

from app.dq import status
from conftest import DOOR, Driver, choose_role

# The desk's own two rows. Everything else this file reads is defined once next door and
# imported — F12's addresses and its billed-call ceiling from `tests/fixtures_f12.py`
# above, the run's rows from `tests/fixtures_f13.py` in `scenario_run.py` — because a
# selector spelled twice is two checks that can drift onto different DOM.
PROPOSED_ROW = "[data-row='proposed']"
HELD_ROW = "[data-row='needs_review']"
STATUS_ATOM = ".rr-top .atom:not([data-compiled])"

# §7 step 3's own example: a proposal constraining `status` to observed values, which the
# engineer cannot verify because it encodes a business assumption. The flow does not DEPEND
# on the model proposing it — the step is about one proposal being held back from the bulk
# accept, and any proposal can play that part, so the fallback is the last one.
FLAGGED_COLUMN = "status"

# §7 steps 4, 5 and 6, word for word from the spec.
REJECTION = "cancelled orders use a fourth status not in this sample"
AUTHORED = "order total can never be negative"
INEXPRESSIBLE = "shipped date must be after order date"


def step_1_coverage_is_visible(driver: Driver, scenario: Scenario) -> None:
    """§7.1 · `orders` at the top of the Table Explorer, with a rule count of zero.

    The zero is what makes the rest of the flow mean anything — every later claim about
    coverage is a difference from here — and it is read off the row's own
    `data-accepted-rules`, the number the server put there rather than a count of markup.
    """
    choose_role(driver, "engineer")
    driver.goto("/tables")
    driver.page.wait_for_load_state("networkidle")

    listed = [
        row.get_attribute("data-table")
        for row in driver.page.query_selector_all("[data-bucket] tbody [data-table]")
    ]
    assert listed[:1] == ["orders"], (
        f"the Table Explorer opens on {listed}. `orders` is the largest table nobody has "
        "written a rule for, and this screen's argument is that it is therefore first."
    )
    row = driver.page.query_selector("[data-table='orders'] [data-accepted-rules]")
    assert row is not None and row.get_attribute("data-accepted-rules") == "0", (
        f"`orders` opens with {row and row.get_attribute('data-accepted-rules')} accepted rules. "
        "§7 starts from a store nobody has written to — hence this flow's own schema."
    )
    atom = driver.page.query_selector("[data-table='orders'] [data-status-atom]")
    assert atom is not None and atom.inner_text().strip() == status.coverage_atom(0), (
        f"the verdict column reads {atom and atom.inner_text()!r}; the writer composed "
        f"{status.coverage_atom(0)!r}. A table with no rules cannot produce a verdict."
    )


def step_2_proposals_arrive_with_evidence(driver: Driver, scenario: Scenario) -> None:
    """§7.2 · one model call; proposals with the numbers behind them; none of them active.

    "None is active" is a claim about the STORE, and a screen of rows labelled `proposed`
    would satisfy a DOM-only reading of it while the rules were already saved. So the DOM
    is read for the labels and the evidence, and the store over HTTP for the emptiness.
    """
    driver.goto(RULES)
    driver.page.wait_for_load_state("networkidle")
    driver.page.click("[data-suggest]")
    driver.page.wait_for_selector(PROPOSED_ROW, timeout=BILLED_MS)

    rows = driver.page.query_selector_all(PROPOSED_ROW)
    assert len(rows) >= 2, (
        f"the model returned {len(rows)} proposal(s); step 3 needs at least two — one to "
        "accept in bulk and one to hold back."
    )
    blank = [_statement(row) for row in rows if not _evidence(row)]
    assert not blank, (
        f"{len(blank)} proposal(s) arrived with no evidence line: {blank}. LT-2b's proposal was "
        "true of every row it saw and still wrong; the numbers are what show which is which."
    )
    # The chip reads the state in ENGLISH (app/dq/status.py::STATE_LABELS) — the raw
    # `proposed` is on the row's own `data-row`, which is what PROPOSED_ROW selected. So
    # the expected text comes off the writer rather than being typed here.
    labels = {row.query_selector(STATUS_ATOM).inner_text().strip() for row in rows}
    assert labels == {status.STATE_LABELS["proposed"]}, (
        f"the proposals render as {sorted(labels)} — `proposed` is the one state a thing with "
        "no row in the store can be in."
    )
    assert scenario.rules() == [], (
        f"the store holds {len(scenario.rules())} rule(s) for `orders` after a screen of "
        "proposals. Nothing is persisted until somebody accepts it (SPEC F12)."
    )


def step_3_review_splits_by_confidence(driver: Driver, scenario: Scenario) -> dict[str, Any]:
    """§7.3 · bulk-accept the unambiguous ones, hold one back, and copy its URL.

    The held-back one is the `status` proposal when the model made one and the last proposal
    otherwise — see `FLAGGED_COLUMN`. The URL is composed from the row's own token, which is
    what is ON THE SCREEN, because copying it is what the engineer is doing.
    """
    rows = driver.page.query_selector_all(PROPOSED_ROW)
    at = next((i for i, row in enumerate(rows) if _column(row) == FLAGGED_COLUMN), len(rows) - 1)
    statement = _statement(rows[at])
    count = driver.page.query_selector(".count")
    assert count is not None, "no bulk control on a screen full of selectable proposals"

    for index, row in enumerate(rows):
        if index != at:
            row.query_selector("input[type=checkbox]").click()
    # The cap REFUSES the extra tick rather than evicting an earlier one, so the selection is
    # the smaller of "everything but the held-back one" and the server's cap. Waited for
    # rather than read on the way past: the count is React state, one click behind the DOM.
    ticked = min(len(rows) - 1, int(count.get_attribute("data-cap") or 0))
    driver.page.wait_for_selector(f".count[data-selected='{ticked}']", timeout=15_000)
    driver.page.click("[data-bulk-accept]")
    _settle(driver, scenario, ticked)

    assert statement not in [rule["statement"] for rule in scenario.rules()], (
        f"the held-back proposal {statement!r} was accepted with the rest — bulk accept is for "
        "the ones the engineer could verify."
    )

    driver.goto(PROPOSED)
    driver.page.wait_for_selector(PROPOSED_ROW, timeout=BILLED_MS)
    remaining = driver.page.query_selector_all(PROPOSED_ROW)
    next(r for r in remaining if _statement(r) == statement).query_selector(
        "button[value='needs_review']"
    ).click()
    driver.page.wait_for_selector(HELD_ROW, timeout=BILLED_MS)

    token = driver.page.query_selector(f"{HELD_ROW} input[name=pick]").get_attribute("value")
    rule_id = str(token).removeprefix("rule:")
    stored = scenario.get(f"/rules/{rule_id}")
    assert stored["statement"] == statement, (
        f"the URL on screen ({rule_id}) addresses {stored['statement']!r}, and the engineer "
        f"flagged {statement!r}. A copied link that opens a different rule is not a permalink."
    )
    return dict(stored, rule_id=rule_id, url=f"/rules/{rule_id}")


def step_4_the_second_user_acts_independently(
    driver: Driver, scenario: Scenario, flagged: dict[str, Any]
) -> None:
    """§7.4 · the domain expert picks their role, finds it in their queue with no table list,
    opens the copied link cold, and rejects it with a reason that is stored.

    The reason is the half of this a screen cannot show you, so it is read back out of the
    store — F12 requires a rejection to capture why, and `app/rules/store.py` refuses a
    rejected revision that carries none.
    """
    driver.goto("/")
    driver.page.click(DOOR.format(role="expert"))
    driver.page.wait_for_load_state("networkidle")
    assert driver.page.url.endswith(
        "/review"
    ), f"the domain expert's door led to {driver.page.url}; theirs is the review queue."
    assert flagged["statement"] in driver.page.inner_text("body"), (
        f"the flagged rule {flagged['statement']!r} is not waiting in the queue, which is the "
        "one place somebody's judgment was asked for."
    )
    # Narrowed from "no navigation at all" when bead dq-448 restored the mockup's screen
    # tabs to the topbar: the clause is about a TABLE list, and the tabs name screens.
    # tests/e2e/test_f11_review_queue.py carries the full argument and the wider set of
    # assertions; this step keeps §7.4's own line — nothing below the header navigates.
    navigation = driver.page.evaluate(
        """() => [...document.querySelectorAll("a[href], nav, select, [role='navigation']")]
             .filter((e) => !e.closest('header.topbar'))
             .map((e) => e.outerHTML)"""
    )
    assert navigation == [], (
        f"the queue carries navigation outside the topbar's screen tabs: {navigation}. "
        "F11: a domain expert never encounters a table list, and a table name is a word."
    )

    cold = scenario.driver()
    assert cold.page.context.cookies() == [], "the third context arrived with cookies"
    answer = cold.goto(flagged["url"])
    assert answer is not None and answer.status == 200, (
        f"{flagged['url']} answered {answer and answer.status} cold; §7 has this link arriving "
        "in somebody else's chat client."
    )
    assert flagged["statement"] in cold.page.inner_text(
        "body"
    ), "the pasted link did not land on the rule the engineer was looking at."

    cold.page.fill("input[name=reason]", REJECTION)
    cold.page.click("button[value='rejected']")
    # Polled on the STORE, for the reason `_settle` states below and `choose_role` states
    # in conftest: judging is a server action that redirects, and `networkidle` can be
    # true again between the click and the request leaving — so a read taken straight
    # after it can arrive before the write. This was the one place with that shape that
    # still read immediately, and it took `make check-ui` red once on 2026-08-17 (bead
    # dq-cyi.3) while the same check passed alone and on the next full run.
    #
    # THE ASSERTION IS UNCHANGED and is still the thing that fails: waiting is bounded,
    # so a rejection that never lands reports the store's last answer after 60 s exactly
    # as it did before. A poll that ended in `pass` would be the weakening; this one ends
    # in the same equality on the same two fields.
    after: dict[str, Any] = {}
    for _ in range(60):
        after = scenario.get(f"/rules/{flagged['rule_id']}")
        if after["status"] != flagged["status"]:
            break
        cold.page.wait_for_timeout(1_000)
    assert (after["status"], after["reason"]) == ("rejected", REJECTION), (
        f"the store holds {after['status']!r} with reason {after['reason']!r}; the reason is "
        "kept with the rule forever, which is the point of asking for it."
    )


def step_5_english_becomes_an_executable_rule(driver: Driver, scenario: Scenario) -> dict[str, Any]:
    """§7.5 · the sentence is validated, shown for confirmation, and saved on confirmation.

    Read on the STORE, never on a label: the claim on screen is that nothing has been
    written, and the only check on it is the count of rules the table has — before the
    translation, after it, and after the button.

    THE SECOND HALF IS F12's REV 0.4 AMENDMENT, and the assertion is narrower than F12's own
    check next door for a reason worth writing down rather than quietly weakening. That check
    asserts the framework is absent from the expert's whole DOCUMENT, and it holds for a
    screen of STORED rules — the payload never carries a configuration, because
    `?configuration=1` is asked for only in the engineer's render. It does NOT hold for an
    unsaved draft: a draft has no id, so its Save button has to carry the whole `{type,
    kwargs}` as its form value (`web/app/tables/[table]/rules/token.ts`), and the expectation
    type name is therefore in the markup — invisible, unreadable, and there in view-source.
    So what is asserted here is the pane and the READING: no `.ge-pane` element, and nothing
    a domain expert can actually read that names the framework.
    """
    before = {rule["rule_id"] for rule in scenario.rules()}
    driver.goto(RULES)
    driver.page.wait_for_load_state("networkidle")
    translate(driver, AUTHORED)
    answered(driver, DRAFT)

    assert {rule["rule_id"] for rule in scenario.rules()} == before, (
        "compiling a draft wrote it. Accepting is the first moment anything is persisted "
        "(SPEC F12); a screen that saves on compile has no confirmation step at all."
    )
    assert "ge-pane" not in driver.page.content(), (
        "the domain expert's document contains the configuration pane. SPEC F12 Rev 0.4: not "
        "collapsed and not hidden — never rendered."
    )
    assert "expect_" not in driver.page.inner_text("body"), (
        "an expectation type name is on the domain expert's screen. They are in the business "
        "language of the rule; the framework is the engineer's half of the spread."
    )

    driver.page.click(DRAFT)
    driver.page.wait_for_selector(DRAFT, state="detached", timeout=BILLED_MS)
    added = [rule for rule in scenario.rules() if rule["rule_id"] not in before]
    assert len(added) == 1 and added[0]["status"] == "accepted", (
        f"confirming the draft added {[(r['status'], r['statement']) for r in added]}; one "
        "sentence makes one validated rule, accepted because a person pressed the button."
    )
    assert added[0]["column"] == "order_total", (
        f"{AUTHORED!r} compiled to a rule about {added[0]['column']!r}. The sentence names one "
        "column, and a rule about another one is not a translation of it."
    )
    return added[0]


def step_6_an_impossible_rule_fails_honestly(driver: Driver, scenario: Scenario) -> None:
    """§7.6 · refused with an explanation naming the limitation; nothing stored.

    Both sentences come from the one writer (`app/dq/status.py`); a copy typed here would
    pass on a page that had quietly started composing its own.
    """
    before = {rule["rule_id"] for rule in scenario.rules()}
    translate(driver, INEXPRESSIBLE)
    answered(driver, REFUSAL)

    rendered = driver.page.inner_text(REFUSAL)
    assert status.NOTHING_SAVED in rendered, (
        f"the refusal does not say what did not happen: {rendered!r}. That clause is welded to "
        "every refusal because it is the one thing a reader cannot check for themselves."
    )
    assert status.MULTI_COLUMN_LIMIT in rendered or status.UNCLEAR_REQUEST in rendered, (
        f"the refusal names no limitation: {rendered!r}. A refusal a user cannot act on is a "
        "refusal they will work around."
    )
    assert (
        driver.page.query_selector(DRAFT) is None
    ), "a refusal rendered a Save control. There is nothing to save — that is the point."
    assert {
        rule["rule_id"] for rule in scenario.rules()
    } == before, "the store changed on a refusal, so coverage moved for a rule that does not exist."


def _column(row: Any) -> str | None:
    """The column a proposal row is about, as the screen names it."""
    code = row.query_selector(".rr-top code")
    return code.inner_text().strip() if code else None


def _statement(row: Any) -> str:
    return str(row.query_selector(".b-stmt").inner_text()).strip()


def _evidence(row: Any) -> str:
    """The numbers a proposal was inferred from. Empty when the row carries none."""
    line = row.query_selector(".evidence")
    return line.inner_text().strip() if line else ""


def _settle(driver: Driver, scenario: Scenario, ticked: int) -> None:
    """Wait for the bulk accept to reach the store, then insist it wrote what was selected.

    Polled on the STORE rather than on the network going quiet: accepting is a server action
    that redirects, and `networkidle` can be true again between the click and the request
    leaving — at which point the read happens before the write.

    POLLED ON THE ACCEPTED COUNT AND NOT ON THE ROW COUNT, which is a real distinction and
    cost a red run to learn: `judge_batch` writes each selected spec through `propose()`
    FIRST and then moves every one of them with `set_status()`, so there is a moment when
    the store holds all eight rules and has accepted one. A poll that stopped at "eight
    rules exist" read the batch half-judged and reported the product broken.
    """
    accepted = []
    for _ in range(60):
        accepted = [rule for rule in scenario.rules() if rule["status"] == "accepted"]
        if len(accepted) >= ticked:
            break
        driver.page.wait_for_timeout(1_000)
    assert len(accepted) == ticked, (
        f"{ticked} proposals were selected and the store holds {len(accepted)} accepted rules. "
        "Bulk accept writes exactly the selection, through the validator a single accept walks."
    )
