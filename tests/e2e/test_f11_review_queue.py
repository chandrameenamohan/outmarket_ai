"""F11 · the domain expert's door, in a browser: judgment, and no table list anywhere.

Its own file rather than four more checks in `test_ui_behaviour.py`, for the reason
that file's own size threshold enforces: that one is the route-and-role map across four
features, and this is one screen asserted from four directions. `test_f13_results_
dashboard.py` split off first, for the same reason.

WHAT IS ONLY CHECKABLE HERE. The queue's MEANING — which rules are on it, what the
budget line says — is pure and is pinned in `tests/test_review_queue.py` with no
browser. What needs a rendered document is the shape of the absence: that no navigation
exists in the DOM, that no table name is a link, and that `?table=` narrows the page
without becoming an address. An absence is exactly the assertion a screenshot cannot
make and a unit test cannot reach.

INV-1 IS OWNED BY THIS SCREEN, BY PROXY. Nothing here times a human and nothing here
ever will: bead dq-rbf.3 states that as a decision rather than an omission. The
commitment is the visible budget indicator plus the zero-navigation DOM — a five-minute
promise that is stated on screen, and a screen with nowhere to wander off to.
"""

from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

import pytest

from conftest import Driver

pytestmark = pytest.mark.e2e


def _path(driver: Driver) -> str:
    """Where the browser actually is, with the origin and any query stripped off."""
    return urlparse(driver.page.url).path


def _queue(api_url: str, table: str | None = None) -> dict:
    """F11's payload, straight from the process the screen reads.

    Every F11 check below compares the DOM against THIS rather than against a literal,
    for the reason `test_rule_permalink_renders_standalone_in_a_fresh_context` gives at
    length: a sentence typed into this file passes on a page that has quietly started
    composing its own.

    An EMPTY queue fails rather than skips, and the fixture that has to say so is this
    one — the same contract `conftest.rule_id` states for an empty store. Every check
    here is an assertion about a screen full of decisions; against an empty one, "no
    table list appears" is true of a blank page and proves nothing at all.
    """
    query = f"?table={table}" if table else ""
    with urllib.request.urlopen(f"{api_url.rstrip('/')}/review{query}", timeout=60) as body:
        queue = json.load(body)
    if not queue["items"]:
        pytest.fail(
            f"the review queue behind DQ_API_URL={api_url} is empty{query and ' for ' + query}, "
            "so F11's checks would assert absences against a blank screen. Put a rule in "
            "needs_review or leave one failing (POST /rules/<id> {\"status\": \"needs_review\"}) "
            "and re-run; an empty queue must not skip its way past F11."
        )
    return queue


# Anything that would let a reader NAVIGATE by table, or navigate at all. The point of
# the set is that it is wider than "a list of tables": F11 says a user reaching this
# screen never ENCOUNTERS a table list, and a `<select>` of table names, a nav landmark
# or a link to /tables each puts one in front of them by a different route.
NAVIGATION = ("a[href]", "nav", "[role='navigation']", "select", "option", "[role='listbox']")


def test_review_queue_contains_no_table_list_anywhere(driver, api_url) -> None:
    """SPEC F11: 'A user reaching this screen never encounters a table list.'

    An absence assertion over the WHOLE DOM, which is exactly the kind a screenshot
    cannot make — a table list pushed below the fold, folded into a `<details>` or
    rendered `display:none` is still a table list a person can meet.

    The second half is the one that actually decays. It is easy to keep a nav out and
    then render the table name as a link "for convenience", at which point the screen
    has a table list made of one entry per card. So every element whose text is a table
    name is checked for being a link and for SITTING INSIDE one.
    """
    queue = _queue(api_url)
    driver.goto("/review")
    driver.page.wait_for_load_state("networkidle")

    found = {selector: driver.page.query_selector_all(selector) for selector in NAVIGATION}
    offenders = {
        s: [e.evaluate("e => e.outerHTML") for e in els] for s, els in found.items() if els
    }
    assert not offenders, (
        f"the review queue carries navigation: {offenders}. F11's door opens on judgment; "
        "every decision on it is taken in place, and a table name is a word in a sentence."
    )

    tables = sorted({item["table"] for item in queue["items"]})
    assert tables, "the queue names no table at all, so this check is asserting nothing"
    rendered = driver.page.inner_text("body")
    assert all(table in rendered for table in tables), (
        f"the queue's tables {tables} are not on the screen. They are CONTEXT and must be "
        "present as context — a decision about a table nobody names is unjudgeable."
    )
    linked = driver.page.evaluate(
        """(tables) => [...document.querySelectorAll('*')]
             .filter((e) => !e.children.length && tables.includes(e.textContent.trim()))
             .filter((e) => e.tagName === 'A' || e.closest('a'))
             .map((e) => e.outerHTML)""",
        tables,
    )
    assert linked == [], (
        f"a table name is a link: {linked}. Table names appear as context, never as "
        "navigation — one link per card IS a table list, spelled differently."
    )


def test_review_queue_shows_the_epistemic_caveat(driver, api_url) -> None:
    """The sentence that tells a reader what the evidence in front of them cannot settle.

    Compared against the payload rather than typed here, so what is asserted is that the
    screen renders the copy module's sentence — not that it renders A sentence about
    samples. LT-2b is why it is load-bearing: every rule the model proposed was true of
    every row it had seen and still wrong about the business, and this line is the only
    place the product says so before somebody vouches for one.
    """
    queue = _queue(api_url)
    driver.goto("/review")
    driver.page.wait_for_load_state("networkidle")
    assert queue["caveat"] in driver.page.inner_text("body"), (
        f"the review queue does not carry its caveat: {queue['caveat']!r}. It is "
        "app/dq/status.py's sentence and it travels in the payload; a screen missing it is "
        "a screen presenting a sample as if it settled the question."
    )


def test_time_budget_indicator_reflects_queue_position(driver, api_url) -> None:
    """INV-1, made visible to the person it constrains — and positionally true.

    INV-1 says a domain expert can act on a table's proposals in five minutes. Nothing in
    a gate can time a human, and bead dq-rbf.3 says so out loud: the invariant is owned
    here BY PROXY, and the proxy is that the budget is stated, that it counts this
    decision's position, and that the count is within the decision's own TABLE. The
    arithmetic is pinned without a browser in tests/test_review_queue.py; what is asserted
    here is that the sentences on the screen are the server's, in the server's order.
    """
    queue = _queue(api_url)
    driver.goto("/review")
    driver.page.wait_for_load_state("networkidle")

    on_screen = [e.inner_text().strip() for e in driver.page.query_selector_all(".budget")]
    expected = [item["budget"] for item in queue["items"]]
    assert on_screen == expected, (
        f"the queue renders {on_screen} where the server composed {expected}. Every card "
        "carries its own position, so a reader knows how far through the five minutes they "
        "are wherever they are looking."
    )
    assert len(on_screen) == len(driver.page.query_selector_all(".decision")), (
        "there are cards with no budget line, or budget lines with no card. The indicator "
        "is per decision because that is the only place it can be true."
    )


def test_table_query_param_scopes_the_queue_without_changing_the_route(driver, api_url) -> None:
    """`?table=orders` narrows the queue. It is a query parameter and never a segment.

    The distinction is F11's and web/app/role.ts's, for the same reason: an address that
    encodes WHO or WHAT you are browsing forks the URL space, and the review queue is
    the one screen a domain expert is sent to by someone else. `/review/orders` must not
    resolve, or the scoped queue quietly becomes a table's page — and a page per table is
    a table list waiting for an index.
    """
    queue = _queue(api_url)
    table = sorted({item["table"] for item in queue["items"]})[0]

    response = driver.goto(f"/review?table={table}")
    driver.page.wait_for_load_state("networkidle")
    assert response is not None and response.status == 200
    assert _path(driver) == "/review", (
        f"scoping the queue moved the reader to {_path(driver)}. The scope is a parameter on "
        "one address, so the scoped and unscoped screens are the same route."
    )

    scoped = _queue(api_url, table)
    on_screen = [e.inner_text().strip() for e in driver.page.query_selector_all(".budget")]
    assert on_screen == [item["budget"] for item in scoped["items"]], (
        "the scoped screen does not render the scoped queue. `?table=` is a filter the "
        "server applies, not a hint the page is free to ignore."
    )
    assert {item["table"] for item in scoped["items"]} == {table}, (
        f"?table={table} returned decisions about other tables, so the parameter narrows "
        "nothing and the reader is told it does."
    )
    assert driver.page.query_selector_all("a[href]") == [], (
        "the scoped queue grew links the unscoped one does not have. Scoping must not be a "
        "back door for the navigation F11 forbids."
    )

    segment = driver.goto(f"/review/{table}")
    assert segment is not None and segment.status >= 400, (
        f"/review/{table} resolves ({segment and segment.status}). A table in the path is a "
        "second address for the same queue, and the first step towards a page per table."
    )
