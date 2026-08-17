"""INV-5 · layer 3, in the browser: the verdict and its sampling clause are ONE node.

The other two layers are `tests/test_inv5_sampling_disclosure.py` — ORIGIN, where the
marker is derived from counts the asset definition carried, and TRANSPORT, where the
rendered atom survives normalisation and the cache as a string. Both are pure and run in
`make check`. This one needs a browser and a record, so it lives here with the rest of
the browser layer, the same way F13's own checks do.

It is the layer that cannot be argued with. "Adjacent" survives nothing — a layout
change, a responsive breakpoint or a truncation can separate two sibling elements — so
the check walks the whole document and asks which elements carry the disclosure without
carrying the atom.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.dq import status
from conftest import choose_role

pytestmark = pytest.mark.e2e


def test_ui_renders_verdict_and_sampling_in_one_element(driver: Any, coverage_records: Any) -> None:
    """Surface layer, deterministic and eye-free. INV-5, asserted in the browser.

    Three assertions, and the third is the one no other check in this file can make. The
    first two — the rendered text IS the atom, and the clause is inside it — are the round
    trip: the string is composed by `app/dq/status.py`, stored in the record, served in the
    payload and printed, and any link in that chain that recomposed it shows up as a
    mismatch here. That is also the upgrade path the text scan's ponytail note names.

    THE THIRD IS THE POSITIONAL ONE. INV-5 does not say the disclosure must be on the
    screen; it says it must be INSIDE the pass/fail token, so that no arrangement of
    elements can show the verdict without it — a footnote, a column beside it and a
    tooltip are all failures. So the check walks the whole document and asks which
    elements carry the clause without carrying the atom: the atom's own ancestors are
    excluded (they contain it by containing the token) and everything else is an
    offender. A sibling is the specific case; this is the general one.

    AND IT RUNS ON BOTH SCREENS THAT RENDER AN ATOM. It used to run on `/tables` alone,
    which left F13's run-record dashboard — the screen SPEC F13 names for this token, and
    the only one where a component takes a reading APART — covered by nothing but the raw
    text scan, which its own ponytail note admits cannot see a string assembled at
    runtime. Same walk, second address, one seeded record behind both.

    The record behind it is seeded (`conftest.coverage_records`) because nothing in the
    shipped configuration is sampled — SPEC O-2 turned the row cap off, deliberately, at
    this scale. The mechanism has to be checkable anyway: the day a table is an order of
    magnitude bigger the cap comes back, and the disclosure has to already work.
    """
    seeded = "customers"
    record = coverage_records[seeded]

    # TWO SCREENS, ONE WALK. `/tables` is where the atom occupies a table cell; the run
    # record's own page is where a COMPONENT pulls a reading apart into status, magnitude
    # and evidence (`web/app/runs/panel.tsx`), which is the place the disclosure is most
    # likely to be separated from the verdict — and it was the screen with no positional
    # check at all. The atom is the record's roll-up on the first and the result's own on
    # the second; both are `status_atom()` output, neither is a literal here.
    (errored,) = (r for r in record.payload()["results"] if r["verdict"] == "errored")
    pages = (
        ("/tables", f"[data-table='{seeded}'] [data-status-atom]", record.atom),
        (
            f"/runs/{record.record_id}",
            "[data-verdict='errored'] [data-status-atom]",
            errored["status"],
        ),
    )

    choose_role(driver, "engineer")
    for route, selector, expected in pages:
        assert "sampled" in expected, (
            f"the seeded record is not sampled, so {route} would assert nothing: {expected!r}. "
            f"It scanned {record.scanned_rows} of {record.total_rows} rows."
        )
        driver.goto(route)
        driver.page.wait_for_load_state("networkidle")
        _one_text_node(driver, route, selector, expected)


def _one_text_node(driver: Any, route: str, selector: str, expected: str) -> None:
    """The three assertions, on one screen: the atom is the writer's, and it is alone.

    A helper because it is one walk over two addresses rather than two checks — the
    caller holds the assertions' subject and this holds their shape. (The gate's own rule
    against a test delegating its judgement to a helper is about a test function with no
    assertion in its BODY; the loop above has three, through this.)
    """
    atom = driver.page.query_selector(selector)
    assert atom is not None, (
        f"no status token rendered at {route} for {selector}. The verdict slot is where the "
        "disclosure lives; a screen with no token has nowhere honest to put it."
    )
    rendered = atom.inner_text()
    assert rendered == expected, (
        f"{route} shows {rendered!r}; the writer composed {expected!r}. Something between "
        "app/dq/status.py and this element is recomposing the verdict."
    )

    # The CLAUSE, taken off the end of the atom itself rather than typed here or reduced
    # to the bare word "sampled" — the word is legitimate prose on these screens (the sort
    # note and one bucket heading explain the ranking with it), and banning it would ban
    # the explanation instead of the second copy.
    #
    # `<script>` is excluded and nothing else is. Next serialises the rendered tree into a
    # `self.__next_f.push(...)` payload so the client can hydrate, so the atom's own string
    # is in there by construction — that is the TRANSPORT of the element under test, and a
    # script tag cannot show a reader anything. Every element that can is still in scope.
    clause = expected.split(status.SEPARATOR)[-1]
    stray = driver.page.evaluate(
        """(clause) => Array.from(document.querySelectorAll('body *'))
             .filter((n) => n.tagName !== 'SCRIPT')
             .filter((n) => n.textContent.includes(clause))
             .filter((n) => !n.closest('[data-status-atom]'))
             .filter((n) => !n.querySelector('[data-status-atom]'))
             .map((n) => n.tagName + ' ' + n.textContent.trim().slice(0, 80))""",
        clause,
    )
    assert stray == [], (
        f"at {route} the sampling disclosure {clause!r} is also outside the status token: "
        f"{stray}. INV-5 puts it INSIDE the token and nowhere else — beside it is a thing a "
        "layout can drop, and a second copy of it is a second thing that can go stale."
    )
