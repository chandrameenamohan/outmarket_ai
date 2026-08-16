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

The rest of F13's surface is already checked where it belongs and is not
duplicated here: the verdict-plus-sampling text node is the surface layer of
tests/test_inv5_sampling_disclosure.py, and "page load renders the cached last
result without firing an execution request", plus run-record immutability, are in
tests/test_ui_behaviour.py.
"""

from __future__ import annotations

import pytest

from conftest import pending

pytestmark = pytest.mark.e2e


def test_a_run_in_flight_renders_unfinished_rules_as_pending(driver) -> None:
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
    moment, not on how long anything took.
    """
    pending("no running app yet — F13 unbuilt (O-3 settled: synchronous, progressive)")


def test_a_settled_run_has_no_pending_rows_left(driver) -> None:
    """The other end of the same mechanism, and the reason it is a separate check.

    A progressive list that never clears its pending state looks exactly like a
    finished run to a screenshot and exactly like a hung one to a user. When the
    record's status is settled, zero rows carry the pending state and the run
    record's own status atom is no longer running.
    """
    pending("no running app yet — F13 unbuilt")
