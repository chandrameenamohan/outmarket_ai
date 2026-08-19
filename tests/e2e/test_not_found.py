"""Bead dq-abs, the browser half: what a PERSON meets at an address that names nothing.

`tests/test_malformed_requests.py` proves the server side — a malformed rule id is a 404
with a sentence, an unexpected content type is a 422, and no body a stranger can read
names a host, a port or a driver. This is the rung the bead's own check ladder puts above
it, and it is a different claim: that the refusal ARRIVES as a page somebody can act on.

WHY IT IS NOT A SEVENTH PARAMETRISATION OF `test_ui_hygiene.py`. Every route in that
file's list answers 200, and that is a constraint on the list rather than a coincidence:
Chrome logs *"Failed to load resource: the server responded with a status of 404"* for the
document itself, so adding a not-found address there would take `test_console_is_clean`
red for the browser doing its job. The 404 needed its own file, and this is it.

THE COPY IS READ OUT OF THE PAGE'S SOURCE, not typed here. `web/app/not-found.tsx` is its
one home; a literal in this file would be the second copy, and the second copy is what
drifts. Same reason `test_malformed_requests.py` reads the refusal banner out of
`web/app/api.ts` rather than restating it.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from test_malformed_requests import MALFORMED_IDS, PRIVATE

from conftest import REPO, Driver, choose_role

pytestmark = pytest.mark.e2e

# The two addresses in this product that carry an id somebody can mistype or edit. Both
# call `notFound()` on a 404 from the API, and `app/rules/store.py::latest` and
# `app/dq/runs.py::find` both refuse a non-uuid before PostgreSQL is asked — so "no
# record under that id" and "that is not an id at all" reach this page as one answer.
CARRY_AN_ID = ("/rules/{}", "/runs/{}")

NOT_FOUND = pathlib.Path("web/app/not-found.tsx")

# The engineer's front door. `/review` is the domain expert's and is offered to both.
ENGINEER_DOOR = 'a[href="/tables"]'


def _heading() -> str:
    """The page's own `<h1>`, read from its source so this file owns no copy."""
    found = re.search(r"<h1>([^<]+)</h1>", (REPO / NOT_FOUND).read_text())
    assert found, (
        f"{NOT_FOUND} no longer renders an <h1> this check can read. The heading is the "
        "sentence a reader gets first; if it moved, this check has to move with it."
    )
    return found.group(1).strip()


def test_a_mistyped_id_lands_on_a_page_that_says_so_and_names_nothing_private(
    driver: Driver,
) -> None:
    """The whole of the reader's half: a 404, a sentence, a way out, and no topology.

    THE STATUS IS ASSERTED AS WELL AS THE TEXT. A 200 carrying "there is nothing here" is
    the shape `test_run_record_deep_link_targets_are_stable` was once satisfied by — a
    refusal echoing its own input on a screen holding no record — and it is also what a
    crawler, a monitor and a browser's history all read wrongly. It used to be a **502**
    whose sentence named `api.railway.internal:8000`.

    Every id from the server-side table is driven through both addresses that carry one,
    because the fix is a shape guard shared by two stores rather than a branch in a route:
    a check that tried one id on one route would pass on either half alone.
    """
    heading = _heading()
    for template in CARRY_AN_ID:
        for bad in MALFORMED_IDS:
            route = template.format(bad)
            response = driver.goto(route)
            assert response is not None and response.status == 404, (
                f"{route} answered {response and response.status}. A link that points at "
                "nothing is a 404 — a 200 tells every machine that reads it the page was "
                "found, and a 5xx says this service broke over somebody's typo."
            )
            text = driver.page.inner_text("body")
            assert heading in text, (
                f"{route} rendered {text[:120]!r}, which does not carry {heading!r}. A status "
                "code with no sentence on the screen leaves the reader guessing whether they "
                "mistyped the link or the product fell over (INV-4)."
            )
            leaked = [secret for secret in PRIVATE if secret in driver.page.content()]
            assert not leaked, (
                f"the page at {route} names something private: {leaked}. SPEC §3.1 — the "
                "reader has no use for the internal address and a prober has every use for "
                "it, and this is the exact page the live 502 printed it on."
            )


def test_the_domain_expert_is_not_sent_through_the_engineers_front_door(
    driver: Driver,
) -> None:
    """The way out is role-dependent, and that is F11 rather than tidiness.

    `/tables` is the coverage dashboard and it refuses a domain expert BY NAME when they
    reach it. This is the one page in the product whose only job is to be somewhere to
    leave from, so offering that link to everybody would make it the one page that walks
    a reader into a refusal — a second dead end reached from the first.

    Both directions are asserted. Only checking the expert's would pass on a page that had
    quietly lost the link for everyone, which is a worse page and the same green.
    """
    route = CARRY_AN_ID[0].format(MALFORMED_IDS[0])

    # `main` and not the whole DOM: since bead dq-448 the topbar carries the mockup's
    # screen tabs for both roles, and the F10 tab is an `/tables` link by definition —
    # the expert who follows it lands on the signpost, which points them back. What this
    # check owns is the PAGE's own way out: the not-found body may not walk the expert
    # into the engineer's door, and must hand the engineer theirs.
    choose_role(driver, "expert")
    driver.goto(route)
    assert driver.page.query_selector(f"main {ENGINEER_DOOR}") is None, (
        f"{route} offers the domain expert {ENGINEER_DOOR} in its body. `/tables` refuses "
        "them by name (F11), so this page would be sending them from one dead end to the "
        "next."
    )

    choose_role(driver, "engineer")
    driver.goto(route)
    assert driver.page.query_selector(f"main {ENGINEER_DOOR}") is not None, (
        f"{route} offers the engineer no way back to /tables in its body. The link is not "
        "merely harmless for this reader, it is their front door — a not-found page with "
        "nothing on it is where a session ends."
    )
