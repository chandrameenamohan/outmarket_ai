"""F13 · Results Dashboard — UNBLOCKED by LT-1b, and the screen it unblocked
renders a run that is still going.

O-3 is settled: **synchronous, but progressive.** Not a job queue. The measured
worst case is 14.84 s for the 10-rule shipping suite over 500,000 rows on the
direct connection — past the 10 s bar — but the cost is a 2.3 s floor plus about
0.83 s per rule, paid as a sequence of independent statements. A worker returns
the same total later and adds a polling endpoint and a staleness problem. What
the shape argues for instead is a request that streams each rule's verdict as it
lands: first result at about 2 s (one rule over the whole table measures 2.28 s),
and a list that fills.

So F13 is not "a page that renders a completed run record". It is a page that
must be correct halfway through one, and that is what this file checks. The
things a background-job version would have needed — cancel, poll termination,
stale-record staleness — are not here because there is no job to cancel and no
poll to terminate.

NOTHING BELOW ASSERTS A CLOCK. The progressive checks wait for a STATE to appear
and then read the DOM once, so what is asserted is which states were present at
one moment. The run they watch is real: three rules over 500,000 seeded rows,
about 17 s end to end (tests/conftest.py::run_table explains the table choice).

The rest of F13's surface is already checked where it belongs and is not
duplicated here: the verdict-plus-sampling text node is the surface layer of
tests/test_inv5_sampling_disclosure.py, and run-record immutability is in
tests/e2e/test_ui_behaviour.py.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

import pytest
from fixtures_f13 import PENDING_ROW, ROW, RUN_MS, SETTLED_ROW, start_run

from app.dq import status
from conftest import Driver

pytestmark = pytest.mark.e2e

# The rows and the run ceiling are defined once, in `tests/fixtures_f13.py`, beside the
# fixtures that produce the run they describe — see that file for why they are data
# attributes rather than class names. The counter is this file's alone.
COUNTER = "[data-reported]"

# One DOM snapshot, taken in the page in a single evaluation. All three progressive
# facts are read from the SAME snapshot: a check that queried the settled rows and then
# the counter would be comparing two different moments of a list that fills, and could
# report a disagreement that never existed on screen.
SNAPSHOT = """
() => {
  const rows = [...document.querySelectorAll('[data-verdict]')];
  const counter = document.querySelector('[data-reported]');
  return {
    rows: rows.length,
    pending: rows.filter((r) => r.dataset.verdict === 'pending').length,
    settled: rows.filter((r) => r.dataset.verdict !== 'pending').length,
    counted: rows
      .filter((r) => r.dataset.verdict === 'pending' && r.querySelector('[data-magnitude]'))
      .map((r) => r.textContent.trim()),
    classes: rows
      .filter((r) => r.dataset.verdict === 'pending')
      .map((r) => r.querySelector('[data-status-atom]').className),
    atoms: rows.map((r) => r.querySelector('[data-status-atom]').textContent.trim()),
    reported: Number(counter.dataset.reported),
    total: Number(counter.dataset.total),
    counterText: counter.textContent.trim(),
  };
}
"""


def _accepted(api_url: str, table: str) -> int:
    """How many rules a run of `table` will submit, read off the product's own surface."""
    with urllib.request.urlopen(f"{api_url.rstrip('/')}/rules?table={table}", timeout=60) as body:
        rules = json.load(body)["rules"]
    return sum(1 for rule in rules if rule["status"] == "accepted")


def _row_for(driver: Driver, statement: str) -> Any:
    """The one rendered row whose statement is `statement`. Fails loudly if it is not there."""
    found = [row for row in driver.page.query_selector_all(ROW) if statement in row.inner_text()]
    assert len(found) == 1, (
        f"{len(found)} rows on screen carry the statement {statement!r}. Every accepted rule "
        "gets exactly one row, or the list is not the run."
    )
    return found[0]


def test_a_run_in_flight_renders_unfinished_rules_as_pending(driver, api_url, run_table) -> None:
    """The progressive-render check. Three states, and all three must be visible.

    With the run mid-flight, every accepted rule for the table has a row: the
    settled ones show their verdict, the unsettled ones show a pending state.
    Assert all three facts, because each rules out a different lie:

        rows == len(accepted rules)      not absent  — a rule that has not
                                         answered yet must not be missing from
                                         the list, or the run looks smaller and
                                         more finished than it is
        pending rows carry no verdict    not passing — an unfinished rule must
        class and no violating count     never wear the pass class; silence is
                                         not a green tick
        at least one row has settled     not a spinner — the whole point of
                                         progressive is that the first verdict
                                         arrives while the rest are still out

        the reported counter reads       not lying — SPEC F13 says the screen
        settled_rows / total_rows,       states how many of how many rules have
        both read off the same           reported, and a counter that disagrees
        DOM snapshot                     with the list it sits above is worse
                                         than no counter

    Read off the DOM, no stopwatch: the assertion is on states present at one
    moment, not on how long anything took. The moment is chosen by waiting for the
    FIRST settled row and reading immediately — the rules that follow it are seconds
    away, so the window is wide, and the check says so rather than sleeping into it.
    """
    submitted = _accepted(api_url, run_table)
    assert submitted >= 2, (
        f"{run_table} has {submitted} accepted rule(s). Progressive rendering is a claim about "
        "one rule settling while another is still out, and one rule cannot make it."
    )

    driver.goto(f"/runs?table={run_table}")
    start_run(driver)
    driver.page.wait_for_selector(SETTLED_ROW, timeout=RUN_MS)
    seen = driver.page.evaluate(SNAPSHOT)

    assert seen["rows"] == submitted, (
        f"{seen['rows']} rows for {submitted} accepted rules. A rule that has not reported yet "
        "must be on the screen as itself; a list that grows as verdicts land shows a run that "
        "looks smaller and more finished than it is."
    )
    assert seen["settled"] >= 1 and seen["pending"] >= 1, (
        f"the snapshot caught {seen['settled']} settled and {seen['pending']} pending rows, so "
        "the two states were never on screen together and progressiveness is not what was "
        "tested. The whole point of O-3 is a first verdict while the rest are still out."
    )
    assert seen["counted"] == [], (
        f"a pending row carries a violating count: {seen['counted']}. A rule that has not run "
        "has counted nothing, and a number beside it is a finding this run never made."
    )
    passing = [c for c in seen["classes"] if "passed" in c.split()]
    assert not passing, (
        f"a pending row wears the pass class: {passing}. Silence is not a green tick — an "
        "unfinished rule read as passing is the one misreading this screen may never allow."
    )
    assert status.UNSETTLED_ATOM in seen["atoms"], (
        f"no row carries the pending atom {status.UNSETTLED_ATOM!r}; the atoms on screen are "
        f"{seen['atoms']}. It is written once (app/dq/status.py) and arrives in the run's "
        "opening event, so a screen composing its own would show something else here."
    )
    assert (seen["reported"], seen["total"]) == (seen["settled"], seen["rows"]), (
        f"the counter says {seen['reported']} of {seen['total']} while the list shows "
        f"{seen['settled']} settled of {seen['rows']}. Both were read from one snapshot, so "
        "this is a disagreement on screen and not a race in the check."
    )
    assert f"{seen['reported']} of {seen['total']}" in seen["counterText"], (
        f"the counter renders {seen['counterText']!r}, which does not state the two numbers it "
        "carries. SPEC F13: the screen says how many of how many rules have reported."
    )


def test_a_settled_run_has_no_pending_rows_left(driver, record, record_id) -> None:
    """The other end of the same mechanism, and the reason it is a separate check.

    A progressive list that never clears its pending state looks exactly like a
    finished run to a screenshot and exactly like a hung one to a user. When the
    record's status is settled, zero rows carry the pending state and the run
    record's own status atom is no longer running.

    Asserted against the STORED record rather than against the run that produced it:
    this is the address a reload lands on, so what it renders is the cache (SPEC F9),
    and the row count it must agree with is the one that was written down.
    """
    driver.goto(f"/runs/{record_id}")
    driver.page.wait_for_load_state("networkidle")

    assert driver.page.query_selector_all(PENDING_ROW) == [], (
        "a completed record still shows pending rows. Every rule in it reported — that is "
        "what made it a record — so a pending row here is a screen that never cleared."
    )
    assert len(driver.page.query_selector_all(ROW)) == len(record["results"]), (
        f"{len(driver.page.query_selector_all(ROW))} rows for a record holding "
        f"{len(record['results'])} readings. The record is the whole run; a screen showing "
        "fewer rules than it recorded is claiming coverage it does not have."
    )
    assert status.UNSETTLED_ATOM not in driver.page.inner_text("body"), (
        f"the pending atom {status.UNSETTLED_ATOM!r} is on a settled run's page. There is no "
        "verdict it could belong to — every rule in a record has one."
    )


def test_failure_shows_english_statement_count_proportion_and_real_values(
    driver, record, record_id
) -> None:
    """INV-4, on the screen: a failure a person who has never seen this table can judge.

    SPEC F13's own sentence, in three parts, all of them read out of the STORED record
    rather than typed here — a literal in this file would pass on a page that had
    quietly started composing its own, which is the failure `app/dq/status.py`'s single
    writer exists to prevent:

        the rule's English statement      what somebody vouched for, not a rule id
        the count and the proportion      150 alone is a catastrophe in a 500-row table
                                          and a rounding error in 500,000
        real offending values             with the row they came from, because that is
                                          what turns a number into something a person
                                          can go and look at

    The second assertion is the one an implementation gets wrong by accident: an ERRORED
    rule must not read as a failure that found nothing. So the mapping is checked in both
    directions over every reading in the record — a magnitude is on screen exactly when
    the record carries one, and a rule that could not run carries none.
    """
    driver.goto(f"/runs/{record_id}")
    driver.page.wait_for_load_state("networkidle")

    failing = next(r for r in record["results"] if r["verdict"] == "failed" and r["evidence"])
    row = _row_for(driver, failing["statement"])
    rendered = row.inner_text()

    assert failing["magnitude"] and failing["magnitude"] in rendered, (
        f"the failure's size is not on its row: {failing['magnitude']!r} against {rendered!r}. "
        "The count, the rows it is a count OF and the share travel as one sentence from one "
        "writer precisely so that a screen cannot render two thirds of it."
    )
    missing = [value for value in failing["evidence"][:3] if value not in rendered]
    assert not missing, (
        f"the offending values {missing} are not on the row. A count says how much is wrong; "
        "an identified row is what somebody opens the table and looks at."
    )

    shown = {
        reading["statement"]: bool(
            _row_for(driver, reading["statement"]).query_selector("[data-magnitude]")
        )
        for reading in record["results"]
    }
    expected = {
        reading["statement"]: reading["magnitude"] is not None for reading in record["results"]
    }
    assert shown == expected, (
        f"a count is rendered where the record holds none, or the other way round: {shown} "
        f"against {expected}. The two shapes that carry no count are the aggregate types, "
        "which report an observed value instead, and EVERY errored rule — 'errored' is a third "
        "state, and '0 violating rows' beside it is exactly the confusion catch_exceptions "
        "creates (LT-1a)."
    )


def test_raw_panel_is_collapsed_on_first_paint(driver, record, record_id) -> None:
    """The framework's own output is there, and it is shut.

    SPEC F13 wants the raw result available and not in the way. Asserted on the ABSENCE
    OF THE `open` ATTRIBUTE rather than on anything visual: attribute presence is
    deterministic, and `<details>` with no `open` is closed in every browser and in
    every stylesheet, which is more than can be said for a div somebody hid with CSS.

    Both halves are load-bearing. A page with no raw panel at all would pass a check
    that only looked for open ones — and INV-4's fallback, the thing a reader reaches
    for when our reading of the result is not enough, would be gone.
    """
    driver.goto(f"/runs/{record_id}")
    driver.page.wait_for_load_state("networkidle")

    panels = driver.page.evaluate(
        "[...document.querySelectorAll('details')].map((d) => d.hasAttribute('open'))"
    )
    assert panels, (
        "no raw framework output anywhere on a record whose readings all carry one. The "
        "normalised reading is lossy by design; the raw panel is what a person falls back to."
    )
    assert not any(panels), (
        f"{sum(panels)} of {len(panels)} raw panels are open on first paint. Collapsed by "
        "default is the whole arrangement — the framework's output is the fallback, not the "
        "first thing a domain expert meets."
    )


def test_rerun_changes_the_record_id_in_the_url(driver, record_id, run_table) -> None:
    """Pressing the control leaves you at a DIFFERENT address, holding a different run.

    A run record is immutable (F9), so re-running cannot mean "the same page, refreshed".
    It writes a new record under a new id, and the browser has to end up there — otherwise
    the address bar still names the run you were reading when you pressed the button, and
    the two runs are one page wearing one URL.

    What happens to the OLD record is the other half and lives next door
    (tests/e2e/test_ui_behaviour.py::test_rerun_appends_a_new_record_id_rather_than_editing
    _the_old_one), which is why this check asserts the new address and stops.
    """
    driver.goto(f"/runs/{record_id}")
    start_run(driver)
    driver.page.wait_for_url(lambda url: "/runs/" in url and record_id not in url, timeout=RUN_MS)

    landed = driver.page.url.rstrip("/").rsplit("/", 1)[-1]
    assert landed and landed != record_id, (
        f"the re-run ended at {driver.page.url}. A new record has a new address, and a "
        "re-run that stayed put would mean the previous run had been overwritten."
    )
    driver.page.wait_for_load_state("networkidle")
    # BOTH HALVES, because the absence alone is satisfied by a blank page: a new address
    # rendering nothing at all has no pending rows either, and would read as a clean
    # re-run. The rows are what say a record is there to have no pending rows IN.
    assert driver.page.query_selector_all(ROW), (
        "the new address renders no readings at all. A re-run that lands on an empty record "
        "page is not a re-run that was written down."
    )
    assert driver.page.query_selector_all(PENDING_ROW) == [], (
        "the new address renders pending rows, so what was written down is a run that had "
        "not finished. Only a completed run enters the cache (SPEC F9)."
    )


def test_a_reload_after_an_interrupted_run_shows_the_last_completed_record(
    driver, record_id, run_table
) -> None:
    """A run nobody waited for leaves no trace, and the previous record is still the answer.

    The half-finished run lives in the CALLER and nowhere else (SPEC F9, `app/dq/run.py`):
    the generator that would store it never reaches its last line, so an interrupted run
    writes nothing. What this asserts is the consequence on screen — reload during one and
    you get the last run that actually finished, whole, rather than the four verdicts that
    had happened to arrive.

    The interruption is a real navigation, which is how it happens to a person: the browser
    drops the request, the server's next write fails, and the run stops where it stood.
    """
    driver.goto(f"/runs?table={run_table}")
    before = driver.page.get_attribute("[data-record-id]", "data-record-id")
    assert before, f"/runs?table={run_table} names no record before the run; the fixture ran one"

    start_run(driver)
    driver.page.wait_for_selector(SETTLED_ROW, timeout=RUN_MS)
    assert driver.page.query_selector_all(PENDING_ROW), (
        "the run finished before it could be interrupted, so nothing here was tested. The "
        "fixture table is sized so that this cannot normally happen — see tests/conftest.py."
    )

    driver.goto(f"/runs?table={run_table}")
    driver.page.wait_for_load_state("networkidle")
    after = driver.page.get_attribute("[data-record-id]", "data-record-id")

    assert after == before, (
        f"the reload shows record {after} where {before} was the last completed run. An "
        "interrupted run is not a record: storing one would put a partial account of the "
        "table in the place a reader looks for the whole one."
    )
    assert driver.page.query_selector_all(PENDING_ROW) == [], (
        "the reload rendered pending rows. There is no run in flight after a navigation — "
        "what is on screen is a stored record, and every rule in one has reported."
    )
