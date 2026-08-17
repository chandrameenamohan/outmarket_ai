"""F12 · the translation desk, driven in a real browser.

One screen asserted from six directions, which is the same arrangement F10, F11 and F13
already use — `test_ui_behaviour.py` next door is the route-and-role MAP across four
features, and a screen's own checks live with the screen.

WHAT IS DETERMINISTIC HERE AND WHAT IS NOT. Everything below reads an element count, an
attribute, a class list, a rendered string compared against the writer that composed it,
or a number of rules the store holds before and after a click. None of it needs an eye.

THE TWO BILLED CHECKS ARE MARKED `live` AS WELL AS `e2e`, and they still run in
`make check-ui` — `-m e2e` selects them, and `make check`'s `not live` keeps them out of
the gate anyone runs on save. They cost one real model call each (~$0.04, ~6.6 s — LT-2b)
and they are worth it: F4's refusal and the unsaved-until-accepted promise are the
product's two headline claims, and a gate that skipped them would prove neither. The
third billed call is `?propose=1`, shared by three checks through the five-minute memo in
`app/rules/suggest.py`.
"""

from __future__ import annotations

import json

import pytest
from fixtures_f12 import BILLED_MS, DRAFT, PROPOSED, REFUSAL, RULES, answered, translate

from conftest import Driver, api_rules, choose_role

pytestmark = pytest.mark.e2e

# RULES, PROPOSED and BILLED_MS are `tests/fixtures_f12.py`'s — the same three the §7
# scenario's steps read, from the one file that already owns this screen's fixtures. The
# three checks below that need a selectable row all navigate to PROPOSED, so they share
# ONE billed model call per session (~$0.04, ~6.6 s — LT-2b, memoised for five minutes).


def _open(driver: Driver, route: str, timeout: int = 30_000) -> None:
    """Navigate and wait for the network to settle, with a timeout this screen can need."""
    driver.page.goto(driver.base_url.rstrip("/") + route, timeout=timeout)
    driver.page.wait_for_load_state("networkidle")


def test_catalog_renders_exactly_the_canonical_number_of_entries(driver) -> None:
    """Count the rendered catalog entries and compare to the catalog FILE, not to 15.

    B6's whole point is that four consumers — the model's menu, the validator, this
    screen and the gate — read one list, and a design review already caught a mockup
    shipping fifteen entries that did not map 1:1 onto real expectation types. So the
    expected number is `len(catalog.ENTRIES)`, read from `app/rules/catalog.json` at the
    moment of the check, and a hardcoded number here would be the second copy.
    """
    from app.rules import catalog  # noqa: PLC0415 — pure: json and pathlib, no framework

    entries = "[data-catalog] li"
    listed = "els => els.map(e => e.textContent.trim())"

    choose_role(driver, "engineer")
    _open(driver, RULES)
    rendered = driver.page.eval_on_selector_all(entries, listed)
    assert rendered == list(catalog.TYPES), (
        f"the rail rendered {len(rendered)} entries and the catalog file holds "
        f"{len(catalog.TYPES)}. Rendered: {rendered}. One list, four consumers — a screen "
        "offering a type the validator does not know is a menu that lies."
    )

    # THE MENU IS BILINGUAL TOO, and the count is the invariant rather than the words: the
    # domain expert gets the same fifteen entries as the sentence each one turns into,
    # because `expect_column_values_to_be_between` is a name from the other language and
    # Rev 0.4 keeps it out of their document entirely.
    choose_role(driver, "expert")
    _open(driver, RULES)
    theirs = driver.page.eval_on_selector_all(entries, listed)
    assert len(theirs) == len(catalog.ENTRIES) and theirs == [
        e["english"] for e in catalog.ENTRIES
    ], (
        f"the domain expert's rail is {theirs}. It is the same menu, one entry per catalog "
        "line, in the language they judge rules in."
    )


def test_generated_config_is_absent_for_the_expert_and_a_facing_pane_for_the_engineer(
    driver, held_rule
) -> None:
    """SPEC F12, REV 0.4 — and this check is the amendment, so read the name change.

    It used to be `test_generated_config_is_collapsed_on_first_paint` and asserted that a
    `<details>` carried no `open` attribute. That clause is gone: the author selected the
    Diglot Workbench direction, whose idea is the two languages as FACING PAGES, and F12
    was amended rather than bent. The new acceptance is strictly stronger, so the check is
    too — absent beats collapsed, and a facing pane beats a disclosure control.

    THE EXPERT'S HALF IS ASSERTED ON THE WHOLE DOCUMENT, script tags included, which is
    what makes it about the PAYLOAD rather than about the markup. Next serialises the
    server-rendered tree into a hydration payload, so a page that fetched the
    configuration and merely declined to print it would still carry it in there — and
    `driver.page.content()` would find it. It does not, because
    `web/app/tables/[table]/rules/page.tsx` only asks for `?configuration=1` in the
    engineer's render.

    THE ENGINEER'S HALF ASSERTS THE PANE IS A PANE. Not a `<details>`, not behind a
    control: a `.ge-pane` inside a `.spread` alongside the English one, present on first
    paint with nothing clicked.
    """
    marker = held_rule["statement"]

    choose_role(driver, "expert")
    _open(driver, RULES)
    assert marker in driver.page.inner_text("body"), (
        f"the held rule is not on the screen at all ({marker!r}), so nothing below is being "
        "tested. Both users work here — F12 is the one screen they share."
    )
    document = driver.page.content()
    assert "ge-pane" not in document and "expect_column_values" not in document, (
        "the domain expert's document contains the Great Expectations configuration. SPEC "
        "F12 Rev 0.4: hidden ENTIRELY — not collapsed, not display:none. A pane the payload "
        "carried is a pane one refactor away from rendering."
    )

    choose_role(driver, "engineer")
    _open(driver, RULES)
    panes = driver.page.query_selector_all(".spread .ge-pane")
    assert panes, "the engineer gets no configuration pane; the bilingual spread is half a design"
    assert driver.page.query_selector_all("details") == [], (
        "the configuration is behind a disclosure control. Rev 0.4 replaced 'collapsed by "
        "default' with facing pages precisely so the engineer reads both languages at once."
    )
    assert any(
        pane.query_selector("pre") is not None and "expect_" in pane.inner_text() for pane in panes
    ), f"the pane rendered no expectation configuration: {[p.inner_text()[:60] for p in panes]}"


def test_needs_review_rows_carry_no_checkbox_at_all(driver, held_rule) -> None:
    """Not a DISABLED checkbox — no `input[type=checkbox]` anywhere in the row's subtree.

    A disabled control still says "this is bulk-acceptable, just not right now", and a
    `needs_review` rule is the opposite of that: somebody looked at it and could not
    settle it. The row says so in words instead.

    THE SECOND HALF IS WHAT STOPS THIS PASSING VACUOUSLY. A screen with no checkboxes at
    all satisfies the first assertion perfectly, so the check also requires that some
    OTHER row on the same screen has one — which is why it opens the proposed view.
    """
    _open(driver, PROPOSED, BILLED_MS)
    held = driver.page.query_selector("[data-row='needs_review']")
    assert (
        held is not None
    ), f"no held row rendered, though the store holds {held_rule['rule_id']} in needs_review"
    assert held.query_selector_all("input[type=checkbox]") == [], (
        "a rule waiting on somebody's judgment carries a checkbox. SPEC F12 excludes that "
        "population from bulk selection by not offering the control, not by disabling it."
    )
    assert driver.page.query_selector_all("input[type=checkbox]"), (
        "there is no checkbox anywhere on the screen, so the assertion above proved nothing. "
        "The proposed view is what puts selectable rows on it."
    )


def test_bulk_accept_cap_and_empty_state(driver) -> None:
    """0 selected -> disabled. Past the cap -> the extra tick is refused, not swallowed.

    Both read off the DOM. `data-selected` and `data-cap` are the component's own count
    and the server's own cap, so this compares the control against the limit that will
    actually be enforced (`app/rules/store.py::judge_batch`) rather than against a number
    typed here.
    """
    _open(driver, PROPOSED, BILLED_MS)
    button = driver.page.query_selector("[data-bulk-accept]")
    count = driver.page.query_selector(".count")
    assert button is not None and count is not None, "the bulk control did not render"

    assert (
        count.get_attribute("data-selected") == "0" and button.get_attribute("disabled") is not None
    ), (
        "the bulk control is live with nothing selected. Accepting nothing is not an act; the "
        "store refuses an empty batch, and the screen should not offer one."
    )
    cap = int(count.get_attribute("data-cap") or 0)
    assert cap >= 2, f"a cap of {cap} is not a bulk control"

    boxes = driver.page.query_selector_all("input[type=checkbox]")
    assert len(boxes) > 1, f"only {len(boxes)} selectable rows; the cap cannot be exercised"
    for box in boxes:
        box.click()
    ticked = int(count.get_attribute("data-selected") or -1)
    assert ticked == min(len(boxes), cap), (
        f"{len(boxes)} rows were clicked and the control counts {ticked} with a cap of {cap}. "
        "Past the cap the extra tick is refused; silently evicting an earlier one would accept "
        "a rule the reader had stopped looking at."
    )
    assert button.get_attribute("disabled") is None, "the control is still dead with rows selected"
    assert (
        str(cap) in count.inner_text()
    ), f"the cap is not visible to the person it constrains: {count.inner_text()!r}"


def test_the_engineer_edits_the_configuration_and_the_rule_goes_back_for_review(
    driver, api_url
) -> None:
    """SPEC F12's fourth clause, from the engineer's side, driven through the textarea.

    The pane is not read-only decoration: an engineer edits the configuration, presses
    Propose revision, and the rule comes back one revision higher and in `needs_review` —
    because a change to what a rule CHECKS is judged by a person before it runs again
    (`app/rules/store.py::Revision.amended`). Anything else would be an edit in place
    wearing a revision number.

    NOTHING HERE TYPES A CONFIGURATION. The textarea's own value is read, one number in it
    is nudged, and the result is posted — so what is being checked is the round trip
    through the real validator, not this file's idea of a well-formed rule. The revision
    that lands is compared against the one that was there before, read over HTTP.

    The expert's door is the same function with a model call in front of it
    (`app/rules/desk.py::revise`) and is covered by the authoring checks below rather than
    twice here, because the second call would cost $0.04 to exercise one shared line.
    """
    from app.rules import catalog  # noqa: PLC0415 — pure: json and pathlib, no framework

    # WHICH ROW IS EDITED IS CHOSEN FROM THE CATALOG, not from document order: `mostly` is
    # the one kwarg this check can add to a rule without knowing anything else about it,
    # and only the types whose entry lists it accept one. Picking the first textarea on the
    # screen would make the check depend on whatever the store happens to hold first.
    takes_mostly = {e["type"] for e in catalog.ENTRIES if "mostly" in e["optional"]}

    choose_role(driver, "engineer")
    _open(driver, RULES)

    editable = row = None
    for candidate in driver.page.query_selector_all("[data-configuration]"):
        if json.loads(candidate.input_value())["type"] in takes_mostly:
            editable = candidate
            row = candidate.evaluate_handle("node => node.closest('li')").as_element()
            break
    assert editable is not None and row is not None, (
        "no editable configuration on this screen whose type takes `mostly`. The engineer's "
        f"pane is either not editable or the table holds none of {sorted(takes_mostly)}."
    )

    rule_id = row.query_selector("input[name=pick]").get_attribute("value").removeprefix("rule:")
    before = next(r for r in api_rules(api_url, "orders") if r["rule_id"] == rule_id)

    # A proportion, which is exactly what layer 1 of INV-2 checks (`validator._mostly`) —
    # so this edit reaches the framework rather than being refused on the way.
    #
    # THE VALUE HAS TO DIFFER FROM THE ONE ALREADY THERE, and a literal 0.99 did not: the
    # store is append-only, this layer runs against it repeatedly, and the second run of
    # `make check-ui` re-typed the same proportion into the rule its own first run had left
    # at 0.99 — producing an identical English statement and failing the last assertion
    # below for a reason that had nothing to do with the product. Nudged off whatever is in
    # the box instead, so the edit is always an edit.
    spec = json.loads(editable.input_value())
    spec["kwargs"]["mostly"] = 0.98 if spec["kwargs"].get("mostly") == 0.99 else 0.99
    editable.fill(json.dumps(spec, indent=2))
    row.query_selector("form.amend button").click()

    # Poll the STORE rather than wait for the network to fall quiet. Saving is a server
    # action that redirects, and "idle" can be true again in the moment between the click
    # and the request leaving — at which point the read below happens before the write.
    after = before
    for _ in range(30):
        driver.page.wait_for_timeout(1_000)
        after = next(r for r in api_rules(api_url, "orders") if r["rule_id"] == rule_id)
        if after["revision"] != before["revision"]:
            break

    assert after["revision"] == before["revision"] + 1, (
        f"the rule stayed at revision {after['revision']}. Editing the configuration appends a "
        "revision; the store has no way to change one in place and the database refuses it."
    )
    assert after["held"] and not after["bulk"], (
        f"the amended rule came back as {after['status']!r}. It goes back for review — "
        "inheriting `accepted` would mean the new spec runs before anyone judged it."
    )
    assert after["statement"] != before["statement"], (
        f"the sentence did not change: {after['statement']!r}. The two panes are one rule, so "
        "editing the configuration has to move the English with it or the spread is a lie."
    )


def test_compiled_ok_token_is_neutral_not_a_pass_verdict(driver) -> None:
    """A rule that compiled has cleared SHAPE and nothing else.

    Great Expectations accepted 10 of 25 deliberately nonsense rules while reporting
    success (LT-2a), so this token may never be styled as a verdict. Asserted on the
    CLASS LIST rather than on colour, because a class is deterministic and a rendered
    colour is a screenshot — and the class is what carries the colour.
    """
    from app.dq import status  # noqa: PLC0415 — the writer; tests may name what it wrote

    _open(driver, PROPOSED, BILLED_MS)
    tokens = driver.page.query_selector_all("[data-compiled]")
    assert tokens, "no compile token on a screen full of compiled rules"
    for token in tokens:
        classes = set((token.get_attribute("class") or "").split())
        assert classes & {"atom"} and not classes & set(status.VERDICTS), (
            f"the compile token carries {sorted(classes)}. A verdict class here would render "
            "'well-formed' in the colour of 'true', which is the one thing LT-2a disproved."
        )
        assert token.inner_text().strip() == status.COMPILED_TOKEN, (
            f"the token reads {token.inner_text()!r}; the writer composed "
            f"{status.COMPILED_TOKEN!r}. Something is composing it a second time."
        )
    assert status.COMPILED_CAVEAT in driver.page.inner_text("body"), (
        "the token is on screen without the sentence that says what it does not mean. A grey "
        "chip is a weaker statement than a sentence, and this is the sentence."
    )


@pytest.mark.live
def test_inexpressible_rule_is_rejected_and_writes_nothing(driver, api_url) -> None:
    """F4's load-bearing refusal, driven through the field a person actually types in.

    "shipped date must be after order date" relates two columns, and the catalog holds no
    multi-column type at all — so the honest answer is a refusal naming the boundary,
    never an approximation into the nearest single-column rule that compiles.

    THE SECOND ASSERTION IS THE ONE THAT MATTERS, and it is a fact about the STORE rather
    than about the network. An earlier version of this check counted POSTs and could not
    have worked: a Next server action and a page navigation are the same POST to the same
    URL, so "which endpoint fired" is not observable from the browser. The count of rules
    the table has is — and it is also the claim the sentence makes.
    """
    from app.dq import status  # noqa: PLC0415

    before = len(api_rules(api_url, "orders"))
    _open(driver, RULES)
    translate(driver, "shipped date must be after order date")
    answered(driver, REFUSAL)

    rendered = driver.page.inner_text(REFUSAL)
    assert status.NOTHING_SAVED in rendered, (
        f"the refusal does not say what did not happen: {rendered!r}. That clause is welded to "
        "every refusal by the single writer because it is the one thing a reader cannot check."
    )
    assert status.MULTI_COLUMN_LIMIT in rendered or status.UNCLEAR_REQUEST in rendered, (
        f"the refusal names no limitation: {rendered!r}. A refusal a user cannot act on is a "
        "refusal they will work around."
    )
    assert (
        driver.page.query_selector(DRAFT) is None
    ), "a refusal rendered a Save control. There is nothing to save — that is the point."
    assert len(api_rules(api_url, "orders")) == before, (
        f"the store went from {before} rules to {len(api_rules(api_url, 'orders'))} on a "
        "refusal. A stored non-rule reports coverage the table does not have."
    )


@pytest.mark.live
def test_draft_compile_does_not_persist_until_accept(driver, api_url) -> None:
    """Unsaved-until-accepted, asserted on the store rather than on a label.

    A draft is shown for confirmation with its compiled configuration beside it, and the
    claim on screen is that nothing was written. That claim is checked the only way it
    can be: the table's rule count before the translation, after it, and after the person
    presses the button — unchanged, unchanged, then one higher.

    SPEC §7 step 5's own sentence is the input, so this is the scenario the brief asks for
    running end to end through the screen a person uses.
    """
    before = len(api_rules(api_url, "orders"))
    choose_role(driver, "engineer")
    _open(driver, RULES)
    translate(driver, "order total can never be negative")
    answered(driver, DRAFT)

    assert len(api_rules(api_url, "orders")) == before, (
        "compiling a draft wrote it. Accepting is the first moment anything is persisted "
        "(SPEC F12), and a screen that saves on compile has no confirmation step at all."
    )
    assert driver.page.query_selector(".spread .ge-pane") is not None, (
        "the engineer's draft has no facing configuration pane, so there is nothing to confirm "
        "against — the sentence alone is what the model said, not what will execute."
    )

    # Wait for the DRAFT TO BE GONE rather than for the network to go quiet. Saving is a
    # server action that redirects, and "idle" can be true again in the moment between the
    # click and the request leaving — at which point the count below is read before the
    # write and the check fails for a reason that has nothing to do with the product. The
    # draft panel disappearing is the screen's own statement that the round trip finished.
    driver.page.click(DRAFT)
    driver.page.wait_for_selector(DRAFT, state="detached", timeout=BILLED_MS)
    driver.page.wait_for_load_state("networkidle")
    after = len(api_rules(api_url, "orders"))
    assert after == before + 1, (
        f"the store went from {before} to {after} rules on Save; one rule was expected. The "
        "same door a bulk accept uses is what this button reaches, validator and all."
    )
