"""SPEC F12 Rev 0.4 · the framework is ABSENT from the domain expert's document, on
every route that has one — including the route nobody has written yet.

THIS CHECK EXISTS BECAUSE THE INVARIANT WAS A CONVENTION (bead dq-220). Three screens
read the role, asked for `?configuration=1` only on the engineer's behalf, and served the
domain expert a clean payload. `/runs` and `/runs/<recordId>`, written later, did not:
both roles received byte-identical HTML carrying nine expectation configurations, folded
into a `<details>` — the disclosure control Rev 0.4 exists to have deleted. Nothing was
red. Every screen that had been thought about was correct, which is the whole problem
with a rule that lives in four places.

So the route list here IS THE FILESYSTEM. `web/app/**/page.tsx` is walked and every page
found is fetched as both readers; a page added tomorrow is in this check the moment it
exists, and a page with a dynamic segment nobody has taught this file to fill FAILS by
name rather than being skipped. That is the house style of
`tests/test_inv3_single_ge_import.py`, whose import walk returns what it could not follow
for the same reason: a scan that silently drops a node proves nothing about it.

IT READS THE RAW RESPONSE, NEVER THE DOM. The failure being ruled out is a payload that
shipped and was hidden — by a stylesheet, by a `<details>`, by a component that chose not
to print a field it was handed. Every one of those satisfies an assertion made after
hydration. Bytes off the socket do not care what the CSS says.

The two doors of `web/app/api.ts` get one check each: the pages below, and the run stream
in the second test — which is the same leak arriving a click later, and the reason the
redaction lives in the door rather than in a page.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from conftest import REPO

pytestmark = pytest.mark.e2e

PAGES = REPO / "web" / "app"

# The framework's own vocabulary, as it appears in a document. Matched as text, so it
# catches the payload in a `<pre>`, in a hidden input, in a data attribute and in the
# serialised server payload at the foot of the page alike — the four places a leak has
# actually travelled in this repo. `kwargs` and `batch_id` are on the list because they
# are what a reader MEETS when they open the panel; `expect_column` and `expect_table`
# because they are what the configuration is.
NEEDLES = (
    "expect_column",
    "expect_table",
    "kwargs",
    "partial_unexpected",
    "unexpected_percent",
    "batch_id",
    "expectation_config",
    "great_expectations",
)

# What a dynamic segment is filled with. A route naming a segment that is not here fails
# the check — see `test_every_dynamic_segment_has_something_to_fill_it`.
FILLING = {"table": "orders", "ruleId": "rule_id", "recordId": "record_id"}

# The query string a route is fetched WITH, when the bare address is not the state worth
# checking. Two entries, and they are here for opposite reasons.
#
# `/runs` renders nothing without one: it is "this table, now", and an address with no
# table names no table (web/app/runs/page.tsx). Without this it would answer with a
# paragraph saying so and pass while checking nothing.
#
# `?propose=1` IS THE SCREEN THIS CHECK USED TO MISS, and it is bead dq-8zj. F3's machine
# proposals have no row in the store, so the checkbox that accepted one carried its whole
# compiled `{type, kwargs}` as its value — measured off the socket at the time, the domain
# expert's document held 35 occurrences each of `expect_column` and `kwargs`, and this
# check was green because it fetched the bare address. The propose screen is a SUPERSET of
# it: same rules, same rail, plus the proposals, so nothing is lost by fetching this state
# instead of that one.
#
# WHERE THE COST LANDS, DECIDED RATHER THAN DISCOVERED. `?propose=1` is the one URL in the
# product that spends money — F3 asks the model for candidates (~$0.04, ~6.6 s — LT-2b) —
# and that is why the route was not in this list to begin with. It joins here, in the `e2e`
# layer, and NOT in `make check`: the default gate is marker-deselected to be
# network-free and app-free, so no run of it can bill. Inside a browser-layer run the call
# is already paid for — `tests/fixtures_f12.py::PROPOSED` is the same URL and three checks
# already share ONE call through `app/rules/suggest.py`'s five-minute memo, keyed by
# (table, limit) in the API process. This is the fourth sharer on the same key, so the
# usual marginal cost is nothing and the worst case, if this check runs first and alone,
# is one call. The offline half of dq-8zj — that a handle resolves and that an expired or
# forged one refuses — is `tests/test_proposal_handles.py`, which is free and runs in
# `make check`.
QUERIES = {"/runs": "?table=orders", "/tables/[table]/rules": "?propose=1"}

ROLES = ("expert", "engineer")

# The routes that render no framework for ANYBODY, named on purpose.
#
# THE GUARD BELOW USED TO BE POOLED and that is what this replaces: every engineer
# document was concatenated and the needles were required to appear SOMEWHERE, so one
# route satisfied the non-vacuity claim on behalf of all seven. Measured, `/review`
# carries zero needles for both roles — its half of the check already proved nothing,
# and the pooling is what hid that. The route it matters for is `/runs/[recordId]`: if
# the `record_id` fixture regressed to a record with no framework output, that page
# would answer 200 with nothing to leak, the domain expert's clean assertion would be
# vacuous, and the pooled guard would stay green off `/tables/orders/rules`.
#
# So the exemption is a list somebody wrote down. `/` is the role door, `/review` is
# F11's queue — whose payload never carries the framework at all, which is the feature —
# and `/tables` is F10's coverage dashboard, which counts rules rather than showing
# them. A route that grows a framework pane rejoins the real check by leaving this set,
# and a route that stops having one has to be added here by hand.
FRAMEWORKLESS = {"/", "/review", "/tables"}


def _routes() -> list[str]:
    """Every addressable page, as a template — `/runs/[recordId]`, not a filled URL.

    Route groups (`(name)`) are not path segments and are dropped, which is what Next
    does with them. Templates rather than URLs so a failure names the FILE somebody
    added, which is the thing they would go and look at.
    """
    found = []
    for page in sorted(PAGES.rglob("page.tsx")):
        parts = [p for p in page.parent.relative_to(PAGES).parts if not p.startswith("(")]
        found.append("/" + "/".join(parts))
    return found


def _fill(template: str, values: dict[str, str]) -> str:
    filled = "/".join(
        values[part[1:-1]] if part.startswith("[") else part for part in template.split("/")
    )
    return filled + QUERIES.get(template, "")


def _document(app_url: str, route: str, role: str) -> tuple[int, str]:
    """One page, as one reader, off the socket. No browser and no JavaScript on purpose."""
    asked = urllib.request.Request(
        app_url.rstrip("/") + route, headers={"Cookie": f"dq-role={role}"}
    )
    with urllib.request.urlopen(asked, timeout=60) as answer:
        return answer.status, answer.read().decode("utf-8", "replace")


def test_every_dynamic_segment_has_something_to_fill_it() -> None:
    """The guard on the guard: a new `[thing]` joins the check or fails it, never neither.

    A route this file cannot address is a route it cannot check, and the honest thing to
    do with one is to go red naming it — the alternative is a check that quietly covers
    six of seven pages and reports the same green either way.
    """
    unfillable = [
        f"{template} needs [{part[1:-1]}]"
        for template in _routes()
        for part in template.split("/")
        if part.startswith("[") and part[1:-1] not in FILLING
    ]
    assert not unfillable, (
        f"routes this check cannot address: {unfillable}. Add the segment to FILLING with a "
        "fixture that resolves it — a page that cannot be fetched cannot be proven clean, "
        "and SPEC F12 Rev 0.4 is a claim about EVERY page."
    )


def test_no_page_serves_the_framework_to_the_domain_expert(
    app_url: str, rule_id: str, record_id: str
) -> None:
    """The check that bead dq-220 was reported by, over every page at once.

    Both roles are fetched, and the engineer's half is not decoration: it is what makes
    the domain expert's half mean anything. A store with no rules, an app serving error
    pages, a needle list that stopped matching — each of those produces a document with
    no framework in it for everybody, and this check would pass on all three. So the
    engineer's documents have to prove the framework is there to leak before the domain
    expert's are allowed to prove it did not.

    PER ROUTE, NOT POOLED. That claim is made about each page separately, or one page
    makes it for the others — see `FRAMEWORKLESS` for what that cost and for the three
    routes that are allowed to answer it by being named.
    """
    values = {**FILLING, "ruleId": rule_id, "recordId": record_id}
    documents = {}
    for template in _routes():
        route = _fill(template, values)
        for role in ROLES:
            status, body = _document(app_url, route, role)
            assert status == 200, (
                f"{route} answered {status} for the {role}. A page that did not render cannot "
                "be proven clean — every route in this product answers 200 to a cold reader."
            )
            documents[template, role] = body

    empty = {
        template: sorted(n for n in NEEDLES if n in body)
        for (template, role), body in documents.items()
        if role == "engineer"
        and template not in FRAMEWORKLESS
        and not {"expect_column", "kwargs"} <= {n for n in NEEDLES if n in body}
    }
    assert not empty, (
        f"these routes serve the engineer no framework either, so the domain expert's half of "
        f"the check proves nothing about them: {empty}. Seed a rule and a run record, or fix "
        "the app — or, if the page genuinely renders no framework for anybody, say so by name "
        f"in FRAMEWORKLESS (currently {sorted(FRAMEWORKLESS)}) rather than by it passing."
    )
    stale = sorted(FRAMEWORKLESS - set(_routes()))
    assert not stale, (
        f"FRAMEWORKLESS names {stale}, which is not a route any more. An exemption for a page "
        "that no longer exists is an exemption nobody will notice covering the wrong thing."
    )

    leaks = {
        template: sorted(n for n in NEEDLES if n in body)
        for (template, role), body in documents.items()
        if role == "expert" and any(n in body for n in NEEDLES)
    }
    assert not leaks, (
        f"the domain expert's raw response carries the framework: {leaks}. SPEC F12 Rev 0.4 — "
        "hidden ENTIRELY, not collapsed and not styled away. The decision belongs to "
        "web/app/api.ts, which every screen reads through; a page that reaches past it, or a "
        "payload key that filter does not know, lands here."
    )


def test_the_run_stream_carries_no_framework_to_the_domain_expert(
    app_url: str, api_url: str, run_table: str
) -> None:
    """The second door. A page is clean until somebody presses Run — unless it is not.

    The stream is where the framework's output originates, so redacting the page load and
    passing this through would hide the configuration for exactly as long as nobody used
    the screen. It is checked here rather than in the browser for the same reason as
    above: what matters is the bytes the browser was sent.

    ONE RUN, READ TWICE, and that is what makes it non-vacuous without paying for a second
    one. The same record is fetched straight from the Python process afterwards and MUST
    carry the framework — so "the expert's stream was clean" cannot be satisfied by a run
    that produced nothing to be clean about.
    """
    started = urllib.request.Request(
        f"{app_url.rstrip('/')}/run?table={run_table}",
        method="POST",
        headers={"Cookie": "dq-role=expert"},
    )
    with urllib.request.urlopen(started, timeout=300) as body:
        events = [json.loads(line) for line in body if line.strip()]

    verdicts = [e for e in events if e.get("event") == "verdict"]
    finished = events[-1] if events else {}
    if not verdicts or finished.get("event") != "completed" or not finished.get("record_id"):
        pytest.fail(
            f"a run of {run_table} produced {len(verdicts)} verdicts and ended on "
            f"{finished.get('event')!r}. F13 streams a verdict per rule; a run that did not "
            "happen must not report this check green."
        )

    with urllib.request.urlopen(
        f"{api_url.rstrip('/')}/records/{finished['record_id']}", timeout=60
    ) as body:
        stored = body.read().decode()
    assert any(n in stored for n in NEEDLES), (
        f"record {finished['record_id']} holds no framework output at all, so the stream had "
        "none to strip and this check proved nothing. The engineer's raw panel reads that "
        "record — if it is empty, F13's fallback is gone and that is the bug to chase first."
    )

    served = json.dumps(events)
    leaked = sorted(n for n in NEEDLES if n in served)
    assert not leaked, (
        f"the domain expert's run stream carries the framework: {leaked}. The same run's "
        "record does too, which is correct — the engineer reads it there. What may not "
        "happen is it arriving in the browser of the reader F12 Rev 0.4 hides it from."
    )
