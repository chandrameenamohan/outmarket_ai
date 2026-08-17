"""F11 · the queue is exactly two populations, and the budget line is INV-1 made visible.

The interesting half of a review queue is what is NOT in it. A queue that quietly
included `proposed` rules would put unsaved suggestions in front of somebody as though
a decision were owed on them; one that included `rejected` rules would turn a rejection
into a snooze; one that included `errored` results would ask a domain expert to judge
data that nobody actually read. Each of those is a screen that still looks right, so
each is asserted here rather than eyeballed.

All of it is PURE. `app/rules/view.py::queued` takes revisions and run records and
`awaiting` takes pairs and profiles, so the meaning of the queue is checkable in
`make check` with no database and no browser. What the browser layer adds on top is
different in kind and lives in `tests/e2e/test_ui_behaviour.py`: that no table list
exists in the rendered DOM, and that the budget sentence is the one on the screen.

INV-1 IS OWNED BY THIS SCREEN BY PROXY, and the proxy is `status.budget()`. Timing a
human is deliberately not a gate check (bead dq-rbf.3 says so in its own words), so
what is checkable is that the five minutes are stated, that they are stated per TABLE
rather than per queue, and that the count never runs past the end of the queue it
indexes.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.dq import profile, runs, status
from app.rules import store, view

ORDERS, PAYMENTS = "orders", "payments"

# Four specs, each a distinct rule, in the shape `validate()` returns and the store
# holds — ours, two keys, framework-normalised.
NEGATIVE: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0},
}
STATUSES: dict[str, Any] = {
    "type": "expect_column_values_to_be_in_set",
    "kwargs": {"column": "status", "value_set": ["shipped", "pending"]},
}
DATED: dict[str, Any] = {
    "type": "expect_column_values_to_not_be_null",
    "kwargs": {"column": "order_date"},
}
METHOD: dict[str, Any] = {
    "type": "expect_column_values_to_be_in_set",
    "kwargs": {"column": "method", "value_set": ["card", "paypal"]},
}


def revision(spec: dict[str, Any], state: str, table: str = ORDERS, rule_id: str = "") -> Any:
    """One stored revision. `rule_id` defaults to the spec's column, which keeps the
    ids readable in a failure message and stable under the queue's id sort."""
    return store.Revision(
        rule_id=rule_id or f"{table}-{spec['kwargs'].get('column', 'table')}",
        revision=1,
        table=table,
        spec=spec,
        status=state,
        reason="rejected in an earlier week" if state == store.REJECTED else None,
    )


def result(spec: dict[str, Any], verdict: str) -> dict[str, Any]:
    """One rule's entry in a stored run record, in `normalise.Result.record()`'s shape.

    Only the four fields the queue reads are filled in. The atom is composed by the
    single writer, exactly as the real record's is — a hand-typed one here would let
    this file pass while the sampling clause went missing on the way to the screen.
    """
    return {
        "spec": spec,
        "verdict": verdict,
        "status": status.status_atom(status.RuleResult(verdict, 400_000, 512_400)),  # type: ignore[arg-type]
        "magnitude": status.magnitude(150, 400_000) if verdict == "failed" else None,
    }


def record(table: str, *results: dict[str, Any]) -> runs.Record:
    return runs.Record(
        record_id=f"record-for-{table}",
        table=table,
        status="failed",
        scanned_rows=400_000,
        total_rows=512_400,
        coverage=len(results),
        results=results,
    )


def profiled(table: str, *columns: str) -> profile.TableProfile:
    return profile.TableProfile(
        table=table,
        total_rows=512_400,
        columns=tuple(
            profile.ColumnProfile(
                name=name,
                data_type="text",
                total_rows=512_400,
                non_null=512_400,
                distinct=4,
                minimum=None,
                maximum=None,
                values=None,
            )
            for name in columns
        ),
        sample=(),
    )


def test_queue_contains_only_needs_review_and_currently_failing_rules() -> None:
    """SPEC F11's two populations, and the four exclusions that make them mean something.

    Six rules go in. Two come out, and each of the four that does not is a different
    reason a screen could quietly grow a decision nobody owes:

      proposed          F3 leaves proposals unsaved beside their evidence. A proposal
                        nobody staged is a suggestion, not a decision.
      rejected          a rejected rule reappearing in the queue is a snooze button,
                        and the reason it was rejected is already stored with it.
      accepted, passing a rule doing its job is not a question.
      accepted, errored the third state earning its keep (LT-1a). A rule that could not
                        RUN is an engineer's problem; asking a domain expert whether a
                        violation matters, when nothing was read, is asking them to
                        judge an outage.
    """
    revs = [
        revision(NEGATIVE, store.ACCEPTED),  # failing in the run below -> IN
        revision(STATUSES, store.NEEDS_REVIEW),  # somebody asked -> IN
        revision(DATED, store.ACCEPTED),  # passing -> out
        revision(METHOD, store.ACCEPTED, table=PAYMENTS),  # errored -> out
        revision(NEGATIVE, store.PROPOSED, rule_id="unsaved"),  # out
        revision(DATED, store.REJECTED, rule_id="already-said-no"),  # out
    ]
    records = {
        ORDERS: record(ORDERS, result(NEGATIVE, "failed"), result(DATED, "passed")),
        PAYMENTS: record(PAYMENTS, result(METHOD, "errored")),
    }

    queued = view.queued(revs, records)

    assert [rev.rule_id for rev, _ in queued] == ["orders-order_total", "orders-status"], (
        f"the queue holds {[rev.rule_id for rev, _ in queued]}. It is exactly two populations "
        "— needs_review, and accepted rules the last run reports as failing — and every other "
        "row on it is a decision nobody is waiting for."
    )
    failing, asked = queued
    assert failing[1] is not None and failing[1]["verdict"] == "failed"
    assert asked[1] is None, (
        "a needs_review rule was paired with a run result it did not produce. The join is by "
        "spec identity, so a rule only carries a verdict when that exact rule ran."
    )


def test_an_amended_rule_never_inherits_the_previous_specs_verdict() -> None:
    """The join is by spec, so a rule whose meaning changed drops its old verdict.

    This is the failure the id-based join would produce and no screen could show as
    wrong: the sentence on the card would be the new one and the verdict beside it
    would belong to the sentence it replaced.
    """
    amended = revision(NEGATIVE, store.ACCEPTED).amended(
        {"type": NEGATIVE["type"], "kwargs": {"column": "order_total", "min_value": 1.0}}
    )
    queued = view.queued([amended], {ORDERS: record(ORDERS, result(NEGATIVE, "failed"))})

    assert len(queued) == 1 and queued[0][1] is None, (
        "an amended rule inherited the verdict of the spec it replaced. `amended()` lands in "
        "needs_review, so it belongs in the queue — but with no verdict, because the run "
        "reported on a rule that no longer exists."
    )


def test_a_table_with_no_completed_run_still_shows_what_was_flagged() -> None:
    """`runs.latest()` returns None for a table nobody has run, and that is not an error.

    F11's queue is not a results screen. A rule somebody flagged is waiting on a person
    whether or not anything has ever executed, and a queue that needed a run record to
    render would be empty on exactly the tables where the review workflow starts.
    """
    revs = [revision(STATUSES, store.NEEDS_REVIEW), revision(NEGATIVE, store.ACCEPTED)]
    queued = view.queued(revs, {ORDERS: None})
    assert [rev.rule_id for rev, _ in queued] == ["orders-status"]


def test_the_budget_line_counts_a_decisions_position_within_its_own_table() -> None:
    """INV-1 is a promise about A TABLE's proposals, so the denominator is the table's.

    Three decisions about `orders` and one about `payments`, in one unscoped queue. The
    `payments` card must read as the only decision about `payments` — a card that said
    "1 of 4" would be describing a five-minute budget that spans three tables, which is
    a different and much weaker claim than the one INV-1 makes.
    """
    pairs = [
        (revision(NEGATIVE, store.NEEDS_REVIEW), None),
        (revision(STATUSES, store.NEEDS_REVIEW), None),
        (revision(DATED, store.NEEDS_REVIEW), None),
        (revision(METHOD, store.NEEDS_REVIEW, table=PAYMENTS), None),
    ]
    profiles = {
        ORDERS: profiled(ORDERS, "order_total", "status", "order_date"),
        PAYMENTS: profiled(PAYMENTS, "method"),
    }

    budgets = [item["budget"] for item in view.awaiting(pairs, profiles)]

    assert budgets == [
        status.budget(1, 3, ORDERS),
        status.budget(2, 3, ORDERS),
        status.budget(3, 3, ORDERS),
        status.budget(1, 1, PAYMENTS),
    ], f"the budget lines count across tables rather than within one: {budgets}"
    assert f"of 3 for {ORDERS}" in budgets[0] and f"of 1 for {PAYMENTS}" in budgets[3]


def test_the_budget_never_says_you_are_finished_before_you_are() -> None:
    """Every position but the last states minutes remaining; only the last is the last.

    The arithmetic rounds, and rounding DOWN is the one direction that lies: at twenty
    seconds a decision, two decisions left is forty seconds, and a line that reported
    that as "0 minutes" would tell somebody with work in front of them that they are
    done. `ceil` is why, and this is the check that would catch it going back to `round`.
    """
    for total in (1, 2, 5, 9, 20):
        lines = [status.budget(position, total, ORDERS) for position in range(1, total + 1)]
        assert lines[-1].endswith(status.BUDGET_LAST), f"the last of {total} is not the last"
        assert all(
            not line.endswith(status.BUDGET_LAST) for line in lines[:-1]
        ), f"a queue of {total} claims to be finished early: {lines}"
        assert all(f"Decision {i + 1} of {total}" in line for i, line in enumerate(lines))
    assert status.budget(3, 5, ORDERS) == f"Decision 3 of 5 for {ORDERS} · about 1 minute left"


def test_the_budget_can_say_the_five_minutes_will_not_be_enough() -> None:
    """THE INSTRUMENT HAS TO BE ABLE TO REPORT THE PROMISE BEING BROKEN.

    The first version divided `BUDGET_MINUTES` by the queue length, so the number it
    printed was bounded above by five however long the queue was: thirty-seven decisions
    read "about 5 minutes left", exactly as five would. design/README.md justified this
    graft as putting INV-1 on screen "where a user can see it being kept OR BROKEN", and
    only one of those two was reachable — a needle painted on the dial.

    So the check is the asymmetry: a queue that fits in the budget never mentions the
    overrun, and one that cannot names a number larger than five AND says what that
    means. Without the second clause the honest number is still just a number.
    """
    fits = [status.budget(1, total, ORDERS) for total in (1, 5, 15)]
    assert not any(status.OVER_BUDGET in line for line in fits), (
        f"a queue that fits inside INV-1's five minutes is being reported as an overrun: "
        f"{fits}. {status.DECISION_SECONDS} s a decision means fifteen of them fit exactly."
    )

    over = status.budget(1, 37, ORDERS)
    assert status.OVER_BUDGET in over, (
        f"thirty-seven decisions report {over!r}. At {status.DECISION_SECONDS} s each that is "
        "twelve minutes of work, and an indicator that cannot say so is decoration."
    )
    found = re.search(r"about (\d+) minute", over)
    assert found is not None, f"the overrun line states no number of minutes at all: {over!r}"
    minutes = int(found.group(1))
    assert minutes > status.BUDGET_MINUTES, (
        f"the overrun line still claims {minutes} minutes, which is inside the budget it "
        "says it is outside of."
    )


def test_a_position_outside_the_queue_is_refused_rather_than_rendered() -> None:
    """A budget line that indexes past the end promises decisions nobody is being asked
    to make, and an empty queue has no position at all."""
    for position, total in ((0, 3), (4, 3), (1, 0), (-1, 5)):
        with pytest.raises(ValueError) as refusal:
            status.budget(position, total, ORDERS)
        assert f"decision {position} of {total}" in str(refusal.value), (
            "the refusal does not name the position it refused, so the one person who can "
            f"fix it reads a stack trace instead of a sentence: {refusal.value}"
        )


def test_every_store_state_has_a_label_a_non_technical_reader_can_act_on() -> None:
    """F11's screens print `state_label`, never `status`, and there is one per state.

    `needs_review` in a monospace chip is the schema arriving on the one screen whose
    acceptance says it needs no schema knowledge. So the states are translated by the
    single writer and the mapping is pinned to the store's own closed set here — a fifth
    state added to `store.STATES` without a label would otherwise reach a reader as a
    KeyError at render time, on a page, in front of the user who can least act on it.
    """
    assert set(status.STATE_LABELS) == set(store.STATES), (
        f"the labels cover {sorted(status.STATE_LABELS)} and the store's states are "
        f"{sorted(store.STATES)}. One label per state, or a screen has a state it cannot name."
    )
    assert not any(
        state in label for state, label in status.STATE_LABELS.items()
    ), f"a label still contains the raw state name it is translating: {status.STATE_LABELS}"

    (item,) = view.awaiting(
        [(revision(STATUSES, store.NEEDS_REVIEW), None)],
        {ORDERS: profiled(ORDERS, "status")},
    )
    assert item["state_label"] == status.STATE_LABELS[store.NEEDS_REVIEW]
    assert item["status"] == store.NEEDS_REVIEW, (
        "the raw state stopped travelling. It is the styling hook and the `data-row` "
        "attribute every browser check reads; the label is the half that is printed."
    )


def test_the_queue_carries_the_caveat_and_the_actions_rather_than_composing_them() -> None:
    """Every load-bearing sentence on this screen comes off `app/dq/status.py`.

    The queue is the one screen whose whole job is to make somebody doubt evidence that
    looks conclusive (LT-2b: every rule the model proposed was true of the rows it saw
    and wrong about the business). So the caveat travels in the payload, and so do the
    words on the buttons — "Accept" alone reads as dismissing a notification, and the
    grafted copy is what says out loud that accepting is vouching.
    """
    pairs = [(revision(STATUSES, store.NEEDS_REVIEW), None)]
    (item,) = view.awaiting(pairs, {ORDERS: profiled(ORDERS, "status")})

    assert item["reason_label"] == status.REASON_LABEL
    labels = [judgment["label"] for judgment in item["judgments"]]
    assert status.ACCEPT_ACTION in labels and status.REJECT_ACTION in labels
    assert status.ASK_ACTION not in labels, (
        "a needs_review rule offers a button that moves it to needs_review. The judgments "
        "open to a rule are all of them but its own (app/rules/view.py::judgments)."
    )


def test_a_failing_decision_carries_the_atom_whole_and_the_magnitude_beside_it() -> None:
    """INV-5 and INV-4 arrive as two finished sentences, not as numbers to reassemble.

    The atom is the run record's own string — verdict and sampling clause welded — and
    the queue moves it without looking inside. The magnitude is the other half INV-4
    needs: a count with no denominator is unjudgeable, which is the whole reason this
    screen exists rather than a list of red rows.
    """
    ran = result(NEGATIVE, "failed")
    pairs = [(revision(NEGATIVE, store.ACCEPTED), ran)]
    (item,) = view.awaiting(pairs, {ORDERS: profiled(ORDERS, "order_total")})

    assert item["failing"] == ran["status"] == "FAILED · sampled 400,000 / 512,400"
    assert item["magnitude"] == status.magnitude(150, 400_000)
    assert "configuration" not in item, (
        "the queue payload carries the Great Expectations configuration. SPEC F12 Rev 0.4 "
        "hides it ENTIRELY from the domain expert — this is their screen, so the framework "
        "is not in the document, not merely not on the screen."
    )
