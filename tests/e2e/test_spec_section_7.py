"""SPEC §7 · the acceptance test for the system as a whole, run once, as one flow.

§7 says it out loud — *"This scenario is the acceptance test for the system as a whole"*
and *"is automated as the single end-to-end flow in the verification gate"*. This is that
flow. Its eight steps are ONE test function on purpose: what this check owns is the seam
between the features rather than their internals, and eight independent checks sharing
set-up would prove eight things about a system nobody ever walked through.

NOTHING HERE IS FAKED, AND THAT IS THE WHOLE VALUE OF IT. A real Chromium drives a real
Next process in front of a real Python process, against the real seeded Supabase database
and the real model — three billed calls, about $0.12 and ~20 s (LT-2b), plus two real runs
of `orders`. Every other check in this harness is allowed to seed a condition it could not
otherwise reach (`conftest.coverage_records` says so in as many words); this one is not,
because a scenario with a fixture in it is a demo.

IT RUNS ON ITS OWN STACK. §7 opens on *"No rules exist"* and the shared store is
append-only, so the flow gets its own store schema and its own two processes —
`tests/e2e/scenario_stack.py` argues that at length. **It is idempotent rather than
self-cleaning:** the schema is dropped and recreated on the way in, so a second run is
never polluted by a first, and what the flow wrote survives so a red run can be read.

WHERE THE NUMBERS COME FROM. `seed/MANIFEST.md`, not §7's prose: the narrative still says
2.4M rows and the seeded database holds 500,000, among them the 150 negative-total orders
of defect D1. The manifest is generated from the seeder's own constants and is what two
other checks already grade against.

WHAT IT DOES NOT ASSERT. Any wall-clock or latency threshold — it asserts ordering and DOM
states, never elapsed time. And nothing a per-feature bead already owns: F10's bucket
derivation, F11's absent navigation from every direction, F12's cap arithmetic, F13's raw
panel. Those have their own files; this one walks the line between them.
"""

from __future__ import annotations

import pytest
from scenario_run import step_7_execution_finds_the_planted_defect, step_8_the_loop_closes
from scenario_stack import Scenario, scenario  # noqa: F401 — `scenario` is the fixture
from scenario_steps import (
    step_1_coverage_is_visible,
    step_2_proposals_arrive_with_evidence,
    step_3_review_splits_by_confidence,
    step_4_the_second_user_acts_independently,
    step_5_english_becomes_an_executable_rule,
    step_6_an_impossible_rule_fails_honestly,
)

# `live` as well as `e2e`, exactly as F12's authoring checks carry both: `make check`
# excludes it twice over and `make check-ui`'s `-m e2e` selects it deliberately.
pytestmark = [pytest.mark.e2e, pytest.mark.live]


def test_spec_section_7_end_to_end_scenario(scenario: Scenario) -> None:  # noqa: F811
    """The eight steps, in order, as one person's afternoon and then another's.

    Each step asserts the facts of its own screen next door in `scenario_steps.py`, where
    the DOM it reads is in view. WHAT IS ASSERTED HERE IS THE SEAM — the value each step
    hands the next — because that is the only thing eight separate checks could not have
    proven between them: the rule the engineer flagged is the rule the domain expert opens
    from a pasted link, the sentence the expert wrote is the rule that executes, and the
    record the run wrote is the record the reload renders.

    TWO BROWSERS, NEVER ONE. The engineer and the domain expert are separate contexts with
    separate cookies, so "role is remembered on the device" is what makes the two views
    differ here rather than a toggle pressed between assertions — and step 4 opens a THIRD,
    cold, which is the arrival F14 exists for.
    """
    engineer, expert = scenario.driver(), scenario.driver()

    step_1_coverage_is_visible(engineer, scenario)
    step_2_proposals_arrive_with_evidence(engineer, scenario)
    flagged = step_3_review_splits_by_confidence(engineer, scenario)
    assert flagged["rule_id"] and flagged["status"] == "needs_review", (
        f"step 3 handed step 4 {flagged}. The URL an engineer copies is only worth copying if "
        "it addresses a rule that is actually waiting on somebody's judgment."
    )

    step_4_the_second_user_acts_independently(expert, scenario, flagged)
    authored = step_5_english_becomes_an_executable_rule(expert, scenario)
    assert authored["rule_id"] != flagged["rule_id"], (
        "step 5's sentence landed on the rule step 3 flagged. Authoring appends a new rule; "
        "it does not re-judge one somebody else was already arguing about."
    )

    step_6_an_impossible_rule_fails_honestly(expert, scenario)
    record_id = step_7_execution_finds_the_planted_defect(engineer, scenario, authored)
    assert record_id, "step 7 produced no run record, so there is nothing for step 8 to reload"

    step_8_the_loop_closes(engineer, scenario, record_id, authored)
