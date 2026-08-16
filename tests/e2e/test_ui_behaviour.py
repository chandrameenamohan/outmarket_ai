"""Behavioural browser checks for F10, F11, F12, F14 — drive the running app.

Every assertion below is deterministic: a route, a DOM-order fact, an element
count, an attribute presence, or a network request that did or did not fire.
None of them needs an eye or a judge. The subjective residue ("does this feel
like one product") is the ONLY thing left for the LLM evaluator — see
VERIFICATION.md §7.

F13 is absent on purpose. Its placeholder is test_f13_results_dashboard.py.

Route map these assert against (roles are never route segments, or every F14
permalink forks in two):
    /                        role door
    /tables                  F10
    /tables/[t]/rules        F12
    /rules/[ruleId]          F12 + F14 permalink
    /review                  F11   (?table=orders scopes it; a query param, not a segment)
    /runs, /runs/[recordId]  F13 target strings, fixed now, page unbuilt
"""

from __future__ import annotations

import pytest

from conftest import pending

pytestmark = pytest.mark.e2e


# --- F11 · role door and the domain expert's door -----------------------------


def test_role_door_sends_domain_expert_to_review_and_remembers_it(driver) -> None:
    """/ with no stored role -> role door. Click 'Domain expert' -> lands on /review,
    NOT /tables. Reload -> still /review. Assert on driver.page.url, not on a class name."""
    pending("no running app yet — F11 unbuilt")


def test_review_queue_contains_no_table_list_anywhere(driver) -> None:
    """SPEC F11: 'A user reaching this screen never encounters a table list.'
    Assert zero elements match the table-nav selector across the whole DOM —
    an absence assertion, which is exactly the kind a screenshot cannot make."""
    pending("no running app yet — F11 unbuilt")


def test_review_queue_shows_the_epistemic_caveat(driver) -> None:
    """The 'a rule can be true of every row here and still be wrong' sentence is
    present, compared against the shared copy module rather than a literal."""
    pending("no running app yet — F11 unbuilt")


# --- F10 · Table Explorer -----------------------------------------------------


def test_tables_buckets_render_in_the_prescribed_dom_order(driver) -> None:
    """never run -> ran, but unverifiable -> verified. DOM order, not CSS order:
    read the heading texts in document order and compare the list."""
    pending("no running app yet — F10 unbuilt")


def test_an_errored_or_sampled_table_lands_in_bucket_two(driver) -> None:
    """The bucket assignment is the product's honesty about what it actually knows.
    Assert the row is a descendant of bucket II and not of bucket III."""
    pending("no running app yet — F10 unbuilt")


def test_zero_coverage_tables_sort_first(driver) -> None:
    """SPEC F10 default sort."""
    pending("no running app yet — F10 unbuilt")


# --- F12 · Rule Management ----------------------------------------------------


def test_catalog_renders_exactly_the_canonical_number_of_entries(driver) -> None:
    """Count the rendered catalog entries and compare to the catalog FILE, not to a
    hardcoded 15 — that is what makes UI/compiler drift impossible."""
    pending("no running app yet — F12 unbuilt")


def test_generated_config_is_collapsed_on_first_paint(driver) -> None:
    """SPEC F12: 'collapsed by default'. Assert the <details> has no `open` attribute
    before any interaction. Attribute presence is deterministic; visual state is not."""
    pending("no running app yet — F12 unbuilt")


def test_needs_review_rows_carry_no_checkbox_at_all(driver) -> None:
    """Not a DISABLED checkbox — no input[type=checkbox] in the row's subtree.
    A disabled control still says 'this is bulk-acceptable, just not right now'."""
    pending("no running app yet — F12 unbuilt")


def test_bulk_accept_cap_and_empty_state(driver) -> None:
    """0 selected -> button disabled. cap+1 selected -> the extra selection is refused
    and the label still reads the cap. Both read off the DOM, no screenshot."""
    pending("no running app yet — F12 unbuilt")


def test_compiled_ok_token_is_neutral_not_a_pass_verdict(driver) -> None:
    """'Compiling proves the rule is well-formed — never that it is right.'
    Assert the compiled token's class list is NOT the pass-verdict class. Class
    equality is deterministic; colour is not, which is why the check is on class."""
    pending("no running app yet — F12 unbuilt")


def test_inexpressible_rule_is_rejected_and_writes_nothing(driver) -> None:
    """'shipped date must be after order date' ->
       renders 'Nothing was saved. Your coverage did not change.'
       AND zero POST/PUT hits the rules endpoint (read off the network log).
    The network half is the real assertion: rejection must not write."""
    pending("no running app yet — F4/F12 unbuilt")


def test_draft_compile_does_not_persist_until_accept(driver) -> None:
    """Unsaved-until-accepted is a network fact, not a label. Compile fires the
    compile endpoint; no persistence endpoint is touched until 'Save as accepted'."""
    pending("no running app yet — F12 unbuilt")


# --- F14 · stable URLs --------------------------------------------------------


def test_rule_permalink_renders_standalone_in_a_fresh_context(driver) -> None:
    """Fresh browser context, no cookies, no prior navigation, no login:
    GET /rules/<id> -> 200, and the English statement, evidence line and Accept
    action all render. This is the check the mockups could not make at all —
    all four variants were single-page tab switchers with no routing."""
    pending("no running app yet — F14 unbuilt (100% uninvented at design time)")


def test_role_is_never_a_route_segment(driver) -> None:
    """/eng/tables and /expert/review must not resolve. Role is view state layered
    on one URL space, or every permalink forks in two."""
    pending("no running app yet — F14 unbuilt")


def test_run_record_deep_link_targets_are_stable(driver) -> None:
    """F10/F11/F12 all link into run records. The TARGET strings /runs and
    /runs/[recordId] are fixed now so the deep-link contract is stable; the page
    behind them is F13, which LT-1b unblocked (O-3: synchronous, progressive) and
    which is not built yet."""
    pending("link targets fixed, page unbuilt — F13 is buildable, blocked on nothing")


# --- write-resistance ---------------------------------------------------------


def test_no_mutation_route_exists_for_a_stored_rule_or_run_record(driver) -> None:
    """Amendment drafts a new revision; re-run appends a new record. Assert no
    PATCH/PUT/DELETE route resolves for a run record, and that 'Re-run' produces
    a NEW record id in the URL rather than editing the old one."""
    pending("no running app yet")
