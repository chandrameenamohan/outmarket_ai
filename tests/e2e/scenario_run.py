"""SPEC §7 steps 7 and 8: the run, and the loop that closes behind it.

Split from `scenario_steps.py` at the seam the 400-line file threshold made visible, and
it is a real seam rather than an arbitrary cut: everything in that file happens before any
rule has ever executed, and everything here is about execution — a run watched while it is
still going, a record read back after it is over, and a second run that has to agree with
the first about the data rather than about itself.

`assert_planted_defect` is here rather than in either step because BOTH call it, and that
is what makes "re-running produces the same outcome" a comparison against `seed/MANIFEST.md`
instead of against the previous run: two runs agreeing on the wrong number would sail
through a check that only compared them to each other.
"""

from __future__ import annotations

import re
from typing import Any

from fixtures_f13 import PENDING_ROW, RUN_MS, SETTLED_ROW, start_run
from scenario_stack import Scenario
from test_demo_seed import _manifest_counts  # the committed ground truth, parsed once

from app.dq import status
from conftest import Driver

# The rows and the run ceiling are `tests/fixtures_f13.py`'s — one definition each, shared
# with F13's own checks, because a run of `orders` here and a run of `payments` there are
# the same screen waiting the same way.

# seed/MANIFEST.md's defect D1: negative `order_total`. Read from the committed manifest
# rather than typed here, and NOT from §7's prose, which still quotes the 2.4M rows the
# demo dataset does not have. The manifest is generated from the seeder's own constants,
# and its own header says it is not adjusted to match an engine that finds fewer.
PLANTED_TABLE, PLANTED_ROWS = _manifest_counts()["D1"]

# `#88231 -450.0` — an identifier and the offending value, which is what turns a count into
# something a person can go and look at (app/dq/normalise.py::evidence).
OFFENDING = re.compile(r"^#\S+ -\d")

# One DOM snapshot, read in the page in a single evaluation, so step 7's progressive facts
# all describe the same moment of a list that is still filling.
SNAPSHOT = """
() => {
  const rows = [...document.querySelectorAll('[data-verdict]')];
  const counter = document.querySelector('[data-reported]');
  return {
    rows: rows.length,
    pending: rows.filter((r) => r.dataset.verdict === 'pending').length,
    settled: rows.filter((r) => r.dataset.verdict !== 'pending').length,
    atoms: rows.map((r) => r.querySelector('[data-status-atom]').textContent.trim()),
    reported: Number(counter.dataset.reported),
    total: Number(counter.dataset.total),
  };
}
"""


def step_7_execution_finds_the_planted_defect(
    driver: Driver, scenario: Scenario, authored: dict[str, Any]
) -> str:
    """§7.7 · verdicts arrive progressively, and the authored rule finds exactly the planted set.

    The progressive half is true for a few seconds only, so it is read from ONE snapshot
    taken as the first verdict lands: a check that queried the settled rows and then the
    counter would compare two moments of a list that fills. Nothing here times anything.
    """
    accepted = [rule for rule in scenario.rules() if rule["status"] == "accepted"]
    driver.goto("/runs?table=orders")
    driver.page.wait_for_load_state("networkidle")
    start_run(driver)
    driver.page.wait_for_selector(SETTLED_ROW, timeout=RUN_MS)
    seen = driver.page.evaluate(SNAPSHOT)

    assert seen["rows"] == len(accepted), (
        f"{seen['rows']} rows for {len(accepted)} accepted rules. A rule that has not reported "
        "must be on screen as itself, or the run looks smaller and more finished than it is."
    )
    assert seen["settled"] >= 1 and seen["pending"] >= 1, (
        f"the snapshot caught {seen['settled']} settled and {seen['pending']} pending rows, so "
        "the two states were never on screen together and progressiveness was not tested."
    )
    assert (seen["reported"], seen["total"]) == (seen["settled"], seen["rows"]), (
        f"the counter says {seen['reported']} of {seen['total']} while the list shows "
        f"{seen['settled']} settled of {seen['rows']}; both came from one snapshot."
    )
    assert (
        status.UNSETTLED_ATOM in seen["atoms"]
    ), f"no row carries the pending atom {status.UNSETTLED_ATOM!r}: {seen['atoms']}"

    driver.page.wait_for_url(lambda url: "/runs/" in url, timeout=RUN_MS)
    driver.page.wait_for_load_state("networkidle")
    record_id = driver.page.url.rstrip("/").rsplit("/", 1)[-1]
    assert_planted_defect(driver, scenario, record_id, authored)
    return record_id


def step_8_the_loop_closes(
    driver: Driver, scenario: Scenario, record_id: str, authored: dict[str, Any]
) -> None:
    """§7.8 · the record renders from cache on reload, a re-run agrees, and coverage moved.

    The cache clause is asserted on the NETWORK rather than on a clock: every request the
    reload makes is recorded and none of them may start a run. "Re-running produces the same
    outcome" is asserted on the OUTCOME and not on the record, because records are immutable
    and a re-run writes a new one (F9).
    """
    fired: list[str] = []
    driver.page.on("request", lambda request: fired.append(f"{request.method} {request.url}"))
    driver.goto(f"/runs/{record_id}")
    driver.page.wait_for_load_state("networkidle")

    assert not [r for r in fired if r.startswith("POST") and "/run" in r], (
        f"opening a stored record fired {fired}. A page load renders the record; only a person "
        "pressing the control starts a run (SPEC F9)."
    )
    assert (
        driver.page.query_selector_all(PENDING_ROW) == []
    ), "the cached record renders pending rows, and only a completed run enters the cache."
    assert_planted_defect(driver, scenario, record_id, authored)

    start_run(driver)
    driver.page.wait_for_url(lambda url: "/runs/" in url and record_id not in url, timeout=RUN_MS)
    driver.page.wait_for_load_state("networkidle")
    again = driver.page.url.rstrip("/").rsplit("/", 1)[-1]
    assert_planted_defect(driver, scenario, again, authored)

    driver.goto("/tables")
    driver.page.wait_for_load_state("networkidle")
    covered = driver.page.query_selector("[data-table='orders'] [data-accepted-rules]")
    atom = driver.page.query_selector("[data-table='orders'] [data-status-atom]")
    assert covered is not None and int(covered.get_attribute("data-accepted-rules") or 0) > 0, (
        "the Table Explorer still shows `orders` with no accepted rules after eight steps of "
        "writing them. The count is the coverage, and the coverage moved."
    )
    assert atom is not None and atom.inner_text().strip().startswith("FAILED"), (
        f"the last run on `orders` reads {atom and atom.inner_text()!r}; the table holds "
        f"{PLANTED_ROWS} negative-total rows and a rule saying it should not."
    )


def assert_planted_defect(
    driver: Driver, scenario: Scenario, record_id: str, authored: dict[str, Any]
) -> None:
    """The authored rule's reading — in the record and on the screen — graded against the seed.

    Called by both step 7 and step 8, which is what makes "re-running produces the same
    outcome" a comparison against the ground truth rather than against the previous run:
    two runs agreeing on the wrong number would pass a check that only compared them.
    """
    record = scenario.get(f"/records/{record_id}")["record"]
    reading = next(r for r in record["results"] if r["statement"] == authored["statement"])
    expected = status.magnitude(PLANTED_ROWS, reading["scanned_rows"])

    assert (reading["verdict"], reading["unexpected_count"]) == ("failed", PLANTED_ROWS), (
        f"the {authored['column']} rule reads {reading['verdict']!r} over "
        f"{reading['unexpected_count']} rows; seed/MANIFEST.md plants exactly {PLANTED_ROWS} "
        f"negative-total rows in {PLANTED_TABLE}, and the manifest is not adjusted to match."
    )
    assert reading["scanned_rows"] == reading["total_rows"] and not reading["sampled"], (
        f"the run scanned {reading['scanned_rows']:,} of {reading['total_rows']:,} rows; the "
        "cap is off (SPEC O-2), so it saw the whole table."
    )
    unidentified = [value for value in reading["evidence"] if not OFFENDING.match(value)]
    assert reading["evidence"] and not unidentified, (
        f"the failure's offending rows are {reading['evidence']}. A count says how much is "
        "wrong; an identified row with its value is what somebody goes and looks at."
    )
    atoms = driver.page.eval_on_selector_all(
        "[data-status-atom]", "els => els.map((e) => e.textContent.trim())"
    )
    assert atoms and not [atom for atom in atoms if "sampled" in atom], (
        f"a verdict on this run discloses a sample: {atoms}. Nothing was capped, so such a "
        "clause would disclose a fiction (INV-5 read the other way round)."
    )
    rows = driver.page.query_selector_all("[data-verdict]")
    rendered = next(r.inner_text() for r in rows if authored["statement"] in r.inner_text())
    assert expected in rendered and reading["evidence"][0] in rendered, (
        f"the row shows {rendered!r}, missing the count or the rows behind it. INV-4: every "
        "failure is readable by someone who can judge whether it matters."
    )
