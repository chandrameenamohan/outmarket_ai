"""Behavioural browser checks for F10, F11, F12, F14 — drive the running app.

Every assertion below is deterministic: a route, a DOM-order fact, an element
count, an attribute presence, or a network request that did or did not fire.
None of them needs an eye or a judge. The subjective residue ("does this feel
like one product") is the ONLY thing left for the LLM evaluator — see
VERIFICATION.md §7.

F13 is absent on purpose. Its own file is test_f13_results_dashboard.py. F11's
review queue is absent for the same reason and lives in test_f11_review_queue.py, and
F12's desk in test_f12_translation_desk.py — one screen asserted from many directions,
where this file is the route-and-role map across four features. What stays here is F11's
OTHER half: the role door, which is about where a domain expert lands rather than about
what is on the screen when they do.

Route map these assert against (roles are never route segments, or every F14
permalink forks in two):
    /                        role door
    /tables                  F10
    /tables/[t]/rules        F12
    /rules/[ruleId]          F12 + F14 permalink
    /review                  F11   (?table=orders scopes it; a query param, not a segment)
    /runs, /runs/[recordId]  F13   (?table= moves, /runs/<id> is fixed for ever)
"""

from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

import pytest
from fixtures_f13 import RUN_MS, start_run

from conftest import DOOR, Driver

pytestmark = pytest.mark.e2e


def _path(driver: Driver) -> str:
    """Where the browser actually is, with the origin and any query stripped off."""
    return urlparse(driver.page.url).path


# --- F11 · role door and the domain expert's door -----------------------------


def test_role_door_sends_domain_expert_to_review_and_remembers_it(driver) -> None:
    """/ with no stored role -> role door. Click 'Domain expert' -> lands on /review,
    NOT /tables. Reload -> still /review. Assert on driver.page.url, not on a class name.

    The two halves are one check because neither is worth anything alone: a door that
    routes correctly but forgets asks the question again on every visit, and a
    remembered choice that routed to the wrong screen is worse than no memory at all.
    """
    driver.goto("/")
    assert _path(driver) == "/", "a device with no stored role must be asked, not guessed at"
    assert driver.page.query_selector_all(".door button"), "no role door on / with no cookie"

    driver.page.click(DOOR.format(role="expert"))
    driver.page.wait_for_load_state("networkidle")
    assert _path(driver) == "/review", (
        f"the domain expert landed on {_path(driver)}. Their door is the review queue; "
        "/tables is the engineer's, and F11 says they never meet a table list."
    )

    driver.goto("/")
    driver.page.wait_for_load_state("networkidle")
    assert _path(driver) == "/review", (
        f"returning to / asked again and left the browser at {_path(driver)}. The choice is "
        "remembered on the device, or it is a question every visit rather than a role."
    )


# --- F14 · stable URLs --------------------------------------------------------


def test_rule_permalink_renders_standalone_in_a_fresh_context(driver, rule_id, api_url) -> None:
    """Fresh browser context, no cookies, no prior navigation, no login:
    GET /rules/<id> -> 200, and the English statement, evidence line and Accept
    action all render. This is the check the mockups could not make at all —
    all four variants were single-page tab switchers with no routing.

    NOTHING HERE IS A LITERAL. Every string asserted is read out of the payload the
    server composed, so what is checked is that the page RENDERS WHAT IT WAS GIVEN.
    A copy of the sentence typed into this file would pass on a page that had quietly
    started composing its own — which is the failure `app/dq/status.py`'s single-writer
    rule exists to prevent, and the one a test full of literals cannot see.
    """
    assert driver.page.context.cookies() == [], (
        "the context arrived with cookies, so 'no prior navigation' is not what is being "
        "tested. Every browser check here gets a fresh context; see tests/conftest.py"
    )

    response = driver.goto(f"/rules/{rule_id}")
    assert response is not None and response.status == 200, (
        f"/rules/{rule_id} answered {response and response.status} to a cold request. A "
        "pasted link has to work for someone who has never been here."
    )

    with urllib.request.urlopen(f"{api_url.rstrip('/')}/rules/{rule_id}", timeout=30) as body:
        rule = json.load(body)
    rendered = driver.page.inner_text("body")

    assert rule["statement"] in rendered, (
        f"the rule's English statement is not on its own page: {rule['statement']!r}. That "
        "sentence is the thing a domain expert judges; without it the page is an id."
    )
    assert rule["evidence"] in rendered, (
        f"the evidence line is missing: {rule['evidence']!r}. LT-2b's proposal was true of "
        "every row it saw and still wrong about the business — the numbers are what show it."
    )
    missing = [j["label"] for j in rule["judgments"] if j["label"] not in rendered]
    assert not missing and rule["judgments"], (
        f"the permalink renders no way to act on the rule; missing {missing}. SPEC F14 says "
        "the URL shows the rule, its evidence AND its actions."
    )
    assert driver.page.query_selector_all("input[type=password]") == [], (
        "a password field on a permalink. There is nothing to log into — SPEC's non-goals "
        "settled that one env-configured connection makes authentication realism, not capability"
    )


def test_role_is_never_a_route_segment(driver) -> None:
    """/eng/tables and /expert/review must not resolve. Role is view state layered
    on one URL space, or every permalink forks in two.

    Both directions are asserted, and the second is the one that actually decays: it is
    easy to keep the per-role paths unrouted and then have the ROLE DOOR navigate to
    one. So this also walks through the door and checks the address it produced carries
    no role in it.
    """
    forked = ["/eng/tables", "/engineer/tables", "/expert/review", "/expert/rules/anything"]
    resolved = [path for path in forked if (r := driver.goto(path)) is not None and r.status < 400]
    assert not resolved, (
        f"{resolved} resolve. A per-role URL space means a pasted permalink carries the "
        "sender's role to the receiver, which is exactly what F11 forbids."
    )

    driver.goto("/")
    driver.page.click(DOOR.format(role="engineer"))
    driver.page.wait_for_load_state("networkidle")
    landed = _path(driver)
    assert landed == "/tables", f"the engineer's door led to {landed}"
    assert not any(role in landed for role in ("engineer", "expert", "eng", "exp")), (
        f"choosing a role put it in the path: {landed}. The role is a cookie and a body "
        "class; the address is the same one the other role would have reached."
    )


def test_run_record_deep_link_targets_are_stable(driver, record, record_id) -> None:
    """F10/F11/F12 all link into run records. `/runs/<recordId>` has to be the record.

    THIS CHECK USED TO PASS ON AN ERROR MESSAGE. It navigated to two INVENTED ids and
    asserted a 200 with the id somewhere in the body — and `app/dq/runs.py::find` refuses
    a malformed id with a sentence that quotes it back ("'2f3a9c10-record-one' is not a
    run record id"), rendered at 200 because a bad link is a page and not a server fault.
    So the headline claim — that an id reaches the page it addresses — was satisfied by
    a refusal echoing its own input, on a screen holding no record at all. F13 shipped
    underneath it and nothing noticed; that is what drift looks like.

    What it asserts now is the thing the deep link is FOR, against a record a real run
    wrote this session (`tests/fixtures_f13.py::record`): the address renders that
    record's own readings, and an id nobody ever wrote renders none. The second half is
    what makes the first half mean something — a page that rendered the same rows
    whatever it was handed would pass the first assertion on its own.
    """
    assert (index := driver.goto("/runs")) is not None and index.status == 200, (
        f"/runs answered {index and index.status}; every screen that links to a run reaches "
        "it through this address space, so the bare form has to resolve"
    )

    response = driver.goto(f"/runs/{record_id}")
    assert response is not None and response.status == 200, f"/runs/{record_id} did not resolve"
    rendered = _readings(driver)
    assert [statement for _, statement in rendered] == [
        result["statement"] for result in record["results"]
    ], (
        f"/runs/{record_id} renders {rendered}, and the record it names holds "
        f"{[(r['status'], r['statement']) for r in record['results']]}. A record's address has "
        "to answer with that record, or /runs/<id> is one screen wearing many URLs."
    )

    # A fabricated id is a link somebody mistyped or a record that was never written. It
    # is allowed to answer 200 — it is a page, not a server fault — but it may not answer
    # with READINGS, because readings are the claim that a run happened.
    driver.goto("/runs/2f3a9c10-record-one")
    assert driver.page.query_selector_all("[data-verdict]") == [], (
        "an id no run ever wrote renders verdict rows. Then the page is not reading the "
        "record it is addressed by, and every deep link in the product is decoration."
    )


# --- write-resistance ---------------------------------------------------------


def _readings(driver: Driver) -> list[tuple[str, str]]:
    """Every rendered row as `(atom, statement)`, in document order."""
    return [
        (row[0].strip(), row[1].strip())
        for row in driver.page.evaluate(
            """[...document.querySelectorAll('[data-verdict]')].map((r) => [
                 r.querySelector('[data-status-atom]').textContent,
                 r.querySelector('.stmt').textContent,
               ])"""
        )
    ]


def test_rerun_appends_a_new_record_id_rather_than_editing_the_old_one(
    driver, record, record_id
) -> None:
    """The browser half of write-resistance. The SQL and route-verb halves are real
    already, in tests/test_rule_store.py — this one drives the button: 'Re-run'
    must land on a NEW record id in the URL, with the previous record still
    reachable at its own.

    The SECOND half is the one only a browser can check, and it is the reason this is
    not a duplicate of F13's own URL check: after the re-run, the old address is
    revisited and its readings are compared to what it showed before. A record is a
    record of what happened (F9) — if re-running had edited it, the same URL would now
    answer with the new run's verdicts and nobody would ever see it happen.
    """
    driver.goto(f"/runs/{record_id}")
    driver.page.wait_for_load_state("networkidle")
    was = _readings(driver)
    assert len(was) == len(record["results"]), "the record's own page does not render its readings"

    start_run(driver)
    driver.page.wait_for_url(lambda url: "/runs/" in url and record_id not in url, timeout=RUN_MS)
    appended = driver.page.url.rstrip("/").rsplit("/", 1)[-1]
    assert appended != record_id, f"the re-run stayed at {driver.page.url}"

    driver.goto(f"/runs/{record_id}")
    driver.page.wait_for_load_state("networkidle")
    assert _readings(driver) == was, (
        f"the record at /runs/{record_id} changed after a re-run. Records are append-only and "
        "the database refuses UPDATE outright, so a change here means the page is not reading "
        "the record it is addressed by."
    )


def test_a_page_load_renders_the_cached_record_and_executes_nothing(driver, record_id) -> None:
    """F9's cache clause, from the outside: opening a record costs no run.

    A run costs about 17 s of real database work for the fixture table and 2 min 21 s for
    the demo's own. A screen that re-executed on every load would spend that on every
    refresh, every back button and every pasted link — and would answer differently each
    time for reasons that have nothing to do with the data.

    Asserted on the NETWORK rather than on the clock: every request the page makes is
    recorded, and none of them may be the one that starts a run. `app/dq/runs.py` has no
    import path to the executor, so this cannot fail without something new being wired —
    which is exactly the change worth catching.
    """
    fired: list[str] = []
    driver.page.on("request", lambda request: fired.append(f"{request.method} {request.url}"))
    driver.goto(f"/runs/{record_id}")
    driver.page.wait_for_load_state("networkidle")

    executions = [request for request in fired if request.startswith("POST") and "/run" in request]
    assert not executions, (
        f"opening a stored record fired {executions}. A page load renders the record; only a "
        "person pressing the control starts a run (SPEC F9)."
    )
    assert _readings(driver), "the cached record rendered no readings at all"
