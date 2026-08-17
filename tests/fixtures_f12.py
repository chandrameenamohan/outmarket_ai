"""F12's browser fixtures — the one condition its desk cannot be checked without.

Next door to `tests/fixtures_f13.py` and for the same reason that file gives: a fixture
that needs the product's own writers does not belong in `conftest.py`, which every layer
imports, and the size threshold in `tests/test_code_quality_thresholds.py` is what keeps
that honest.

Everything here goes over HTTP. `store.propose()` validates against Great Expectations
(INV-2, layer 2) and the framework is not in `make check-ui`'s interpreter — it is in the
API process, which is where the writing should happen anyway. `POST /rules` is the same
endpoint the screen's own Accept buttons reach.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

import pytest

# F12's two addresses and its one wait ceiling, defined HERE because two browser modules
# need them — `tests/e2e/test_f12_translation_desk.py` and the §7 scenario's steps — and
# two copies of a route string is how two checks end up addressing different screens
# while agreeing they pass. This file is already the shared F12 module both of them
# import, so it is the one that owns them.
RULES = "/tables/orders/rules"

# `?propose=1` is the one URL on this screen that costs money: it asks the model for F3's
# candidates (~$0.04, ~6.6 s — LT-2b). `app/rules/suggest.py` memoises the batch for five
# minutes, so every check that needs a selectable row shares ONE call per session.
PROPOSED = f"{RULES}?propose=1"

# How long a real model call may take before a check gives up — ONE number, not the two
# that used to sit in the two modules (120 s and 180 s for the same wait). Deliberately
# not "generous": a check that waits four minutes for a screen turns a hang into a coffee
# break. The run's own ceiling is the other one, and it lives in fixtures_f13.py.
BILLED_MS = 180_000

# F12 · the rule this screen has to be able to render with no checkbox beside it. A
# `needs_review` rule is the population SPEC F12 excludes from bulk selection outright,
# and nothing in a normal session produces one reliably: a rule lands there when somebody
# presses "Ask business" or when an amendment supersedes it, both of which are decisions
# a person takes. So it is created, once, through the product's own door.
HELD_SPEC: dict[str, Any] = {
    "type": "expect_column_values_to_not_be_null",
    "kwargs": {"column": "customer_id"},
}


# F4's one input and its one button, on the desk both users author from.
AUTHOR_FIELD = "[data-author-field]"
TRANSLATE = ".nl-input-row button"

# What the button looks like once the browser has taken the press: `useActionState`'s
# pending flag, rendered as `aria-busy` (web/app/tables/[table]/rules/desk.tsx). It is
# false in the server-rendered markup, so this selector matching PROVES two things at
# once — the component hydrated, and the action it owns has started.
TRANSLATING = f'{TRANSLATE}[aria-busy="true"]'


def translate(driver: Any, sentence: str) -> None:
    """Write a rule in English and press Translate, and make sure the press LANDED.

    THE SAME TRAP `fixtures_f13.start_run` DOCUMENTS, on the other billed control, and it
    cost a §7 run to find: a React page is markup before it is an application, and
    Playwright will happily click a button whose handler is not attached yet. The click is
    swallowed — no request is made, no refusal is rendered, nothing at all happens — and
    the check then waits its whole billed ceiling for a draft nobody asked for. Observed
    twice under `make check-ui` on a loaded machine, and never in isolation, which is what
    a hydration race looks like from the outside.

    So the press is confirmed rather than assumed, and a press that changed nothing is
    repeated — which is safe precisely because it changed nothing: a call that HAD started
    sets `aria-busy` within a frame, and the model behind this button takes seconds
    (LT-2b), so there is no window in which a second click costs a second call.

    Four checks did this by hand before this existed — two here, two in the §7 steps — and
    one of them had already grown a two-selector fallback for the button.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeout  # noqa: PLC0415

    driver.page.fill(AUTHOR_FIELD, sentence)
    for _ in range(5):
        driver.page.click(TRANSLATE)
        try:
            driver.page.wait_for_selector(TRANSLATING, timeout=3_000)
            return
        except PlaywrightTimeout:
            continue
    raise AssertionError(
        f"pressing Translate on {sentence!r} never put the button into its pending state. "
        "Either the handler is not attached — the page is still markup — or the one control "
        "F4 is reached through has stopped saying that it is working."
    )


# The three things F4 can put on the screen after a press. The first two are answers —
# a compiled draft to confirm, or a refusal naming a capability boundary — and both are a
# 200 (`app/rules/desk.py::draft` says why). The third is not an answer at all: it is what
# `web/app/api.ts` renders when the call did not complete.
DRAFT = "[data-save-draft]"
REFUSAL = "[data-refusal]"
CALL_FAILED = ".refused"


def answered(driver: Any, wanted: str) -> None:
    """Wait for F4 to answer, and insist the answer is `wanted` and not one of the others.

    WAITING FOR ONE OUTCOME TURNS EVERY OTHER OUTCOME INTO A THREE-MINUTE HANG, and this
    cost a `make check-ui` run to learn: the `claude` CLI the Agent SDK spawns exited 1
    mid-call, the server's handler died, the screen rendered "did not answer" — and the
    check sat waiting for a draft until `BILLED_MS` ran out and reported a timeout, which
    names neither the failure nor where to read it. Waiting for the UNION and then
    asserting which one arrived turns that into an immediate failure quoting the sentence
    the product actually rendered.
    """
    driver.page.wait_for_selector(f"{DRAFT}, {REFUSAL}, {CALL_FAILED}", timeout=BILLED_MS)
    if driver.page.query_selector(wanted) is None:
        rendered = [
            el.inner_text().strip()[:300]
            for el in driver.page.query_selector_all(f"{REFUSAL}, {CALL_FAILED}")
        ]
        raise AssertionError(
            f"F4 answered, and the answer was not {wanted}. What rendered instead: {rendered}. "
            "A refusal here is the product working and is checked next door; anything about the "
            "server not answering is the model call itself failing — the API process's log names "
            "it, and it is not a product defect."
        )


def api_rules(api_url: str, table: str) -> list[dict[str, Any]]:
    """This table's rules, read over HTTP — the same surface the browser reads.

    Imported rather than reimplemented by every check that needs a before-and-after
    count, which is what "accepting is the first moment anything is persisted" (SPEC F12)
    is actually asserted with: a number that does not move, and then does.
    """
    with urllib.request.urlopen(f"{api_url.rstrip('/')}/rules?table={table}", timeout=60) as body:
        return list(json.load(body)["rules"])


@pytest.fixture(scope="session")
def held_rule(api_url: str) -> dict[str, Any]:
    """One `orders` rule in `needs_review`, created through the product's door if absent.

    OVER HTTP, NOT BY IMPORTING THE STORE, and the reason is not style: `store.propose()`
    validates against Great Expectations (INV-2, layer 2) and the framework is not in
    `make check-ui`'s interpreter — it is in the API process, which is exactly where this
    check wants the writing to happen anyway. `POST /rules` is the same endpoint the
    screen's own Accept buttons reach.

    It reuses an existing held rule when there is one, because the store is append-only
    (F6) and a fixture that wrote unconditionally would add a rule to the scratch schema
    on every run of the browser layer, forever.
    """
    table = "orders"
    found = next((rule for rule in api_rules(api_url, table) if rule["held"]), None)
    if found is not None:
        return found
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/rules",
        data=json.dumps(
            {"table": table, "specs": [HELD_SPEC], "rule_ids": [], "status": "needs_review"}
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(request, timeout=60).close()
    made = next((rule for rule in api_rules(api_url, table) if rule["held"]), None)
    if made is None:
        pytest.fail(
            "POST /rules answered, and `orders` still holds no rule in needs_review. F12's "
            "no-checkbox row would then be asserted against an empty list, which is the one "
            "outcome VERIFICATION §10 forbids."
        )
    return made
