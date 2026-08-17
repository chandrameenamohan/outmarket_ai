"""B12 · F3 — what the model is given, and what it is allowed to hand back.

The other half of F3 lives in `tests/test_rule_suggestion.py`, which checks the proposals
themselves. This file checks the call: the payload that goes out (SPEC §3.1 — aggregate
statistics and a bounded sample, never full table contents) and the replies that come
back, including the ones that are wrong. Two files because they are two jobs; the
recorded profile has one home and is imported from the other rather than recorded twice.

ONE check here spends money. It is marked `live`, it is deselected from `make check`, and
it is the only proof that the whole path holds against the real model rather than against
our reading of it. It needs the database and the credential:

    set -a; . ./.env; set +a
    python3 -m pytest -m live
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import pytest
from test_rule_suggestion import REPLY, TABLE, orders_profile, proposals, unsubstituted

from app.dq import profile
from app.rules import catalog, store, suggest
from app.rules.validator import RuleRejected

# --- what goes out ------------------------------------------------------------


def test_the_menu_the_model_is_given_is_the_whole_catalog_and_only_the_catalog() -> None:
    """'Only from the catalog', held on the way IN, which is where it is cheapest.

    The list is `catalog.TYPES` here as everywhere else — a literal roster in a prompt
    would be exactly the second source of truth `tests/test_catalog_and_copy.py` exists
    to prevent, and the one that would silently stop matching the validator.
    """
    prompt = suggest._prompt(orders_profile())
    missing = [t for t in catalog.TYPES if t not in prompt]
    assert not missing, f"the model is never shown {missing}, so it can never propose them"
    named = set(re.findall(r"\bexpect_[a-z_]+\b", prompt))
    assert named == set(catalog.TYPES), (
        f"the prompt offers {sorted(named - set(catalog.TYPES))} beyond the catalog. The menu "
        "is what makes 'only from the catalog' true before a reply is ever parsed."
    )


def test_prompt_payload_contains_no_full_table_rows() -> None:
    """SPEC §3.1: aggregate statistics and a bounded sample, never full table contents.

    Asserted as a COUNT of rows in the payload rather than as a length budget: a prompt
    that grew with the table is the leak, and a prompt that merely got wordier is not.
    The 500,000-row table is present throughout as a NUMBER, which is the whole
    distinction this check exists to draw.
    """
    profiled = orders_profile()
    prompt = suggest._prompt(profiled)

    serialised = re.search(r"^\[.*\]$", prompt, re.M)
    assert serialised, f"the sample rows are not in the prompt at all: {prompt[:400]!r}"
    rows = json.loads(serialised.group(0))
    assert len(rows) == profile.SAMPLE_ROWS == len(profiled.sample), (
        f"{len(rows)} example rows reached the prompt; the bound is {profile.SAMPLE_ROWS}. "
        "This payload is what the model receives INSTEAD of the table."
    )
    assert prompt.count('"order_id"') == profile.SAMPLE_ROWS, (
        "row data appears in the prompt outside the bounded sample — every occurrence of a "
        "row key must belong to one of the sample rows"
    )
    assert "500,000 rows scanned" in prompt, (
        "the table's size must reach the model as a statistic; that is what makes the sample "
        "a sample rather than the table"
    )
    assert "45,102 distinct" in prompt and "45,102 distinct:" not in prompt, (
        "a high-cardinality column must contribute its COUNT and none of its values — 45,102 "
        "order totals listed in a prompt is the table, one value at a time"
    )


def test_the_evidence_a_reviewer_reads_is_the_evidence_the_model_was_given() -> None:
    """One writer, two uses — so the review screen cannot describe a different table.

    If the evidence line were composed separately for display it could be right about a
    profile the model never saw, and the reviewer would be checking the proposal against
    numbers that did not produce it.
    """
    prompt = suggest._prompt(orders_profile())
    for made in proposals():
        assert made.evidence in prompt, (
            f"{made.type}'s evidence line ({made.evidence!r}) is not in the prompt. The line "
            "is only worth reading if it is what the model actually saw."
        )


# --- what comes back ----------------------------------------------------------


@pytest.mark.parametrize(
    "etype,kwargs,why",
    [
        (
            "expect_column_values_to_be_between",
            {"column": "order_total", "min_value": 100, "max_value": 0},
            "inverted bounds",
        ),
        ("expect_column_values_to_be_in_set", {"column": "status", "value_set": []}, "empty set"),
        (
            "expect_column_values_to_not_be_null",
            {"column": "nonexistent_column"},
            "a column the live schema does not have",
        ),
        (
            "expect_column_values_to_not_be_null",
            {"column": "order_total", "mostly": 98},
            "a tolerance that is not a proportion",
        ),
        (
            "expect_column_values_to_match_regex",
            {"column": "status", "regx": "^S"},
            "a misspelled parameter",
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_a_rule_whose_parameters_are_nonsense_never_becomes_a_proposal(
    etype: str, kwargs: dict[str, Any], why: str
) -> None:
    """Layer 1 of INV-2, reached THROUGH the generator rather than re-typed inside it.

    None of these is a hallucinated type — each is a catalog type carrying kwargs that
    make the rule meaningless, which is the class LT-2a proved the framework itself
    accepts. They are refused before a human ever sees them, and a refusal saves nothing.
    """
    with pytest.raises(RuleRejected) as raised:
        suggest.proposals(orders_profile(), {"rules": [{"type": etype, "kwargs": kwargs}]})
    assert str(raised.value), f"a proposal refused for {why} must carry a readable reason"


def test_a_reply_with_no_rules_fails_rather_than_returning_nothing() -> None:
    """An empty list reads on screen as 'this table needs no rules'. Nobody said that.

    The same argument `app/model.py` makes for refusing to return `{}`: the worst failure
    available to this product is the one that renders as a confident absence of findings.
    """
    empty: tuple[dict[str, Any], ...] = (
        {},
        {"rules": []},
        {"rules": "none"},
        {"proposals": [{"type": "x"}]},
    )
    for reply in empty:
        with pytest.raises(RuleRejected) as raised:
            suggest.proposals(orders_profile(), reply)
        assert "no rules" in str(raised.value), (
            f"{reply} was refused with {str(raised.value)[:80]!r} — the reason has to say that "
            "the reply was empty, because the caller's alternative reading is 'all clear'."
        )


def test_a_reply_whose_rules_are_not_objects_is_refused() -> None:
    """The shape a half-parsed or improvised reply arrives in."""
    shapes: tuple[Any, ...] = (
        "expect_column_values_to_be_unique",
        ["order_total"],
        {"kwargs": {}},
        None,
    )
    for rule in shapes:
        with pytest.raises(RuleRejected) as raised:
            suggest.proposals(orders_profile(), {"rules": [rule]})
        assert "type" in str(raised.value), str(raised.value)


def test_more_rules_than_the_review_budget_are_not_all_returned() -> None:
    """INV-1: five minutes to act on a table's proposals is the constraint, not token cost.

    LT-1b also prices a full-catalog run at 13.97 s, so a reply of forty rules is not a
    bonus — it is a review queue nobody finishes and a run nobody watches.
    """
    reply = {"rules": REPLY["rules"] * 5}
    assert len(reply["rules"]) > suggest.MAX_PROPOSALS, "this check needs an oversized reply"
    assert len(suggest.proposals(orders_profile(), reply)) == suggest.MAX_PROPOSALS


# --- the one check that spends money ------------------------------------------


@pytest.mark.live
def test_suggestions_for_orders_are_all_catalog_types_and_none_is_persisted_as_accepted() -> None:
    """One real call, against the real table. The only check here that proves the path.

    It asserts the store is untouched by counting revisions across the call rather than by
    reading the generator's source: this is the dynamic companion to
    `test_the_generator_can_neither_store_nor_execute`, and it is the one that would catch
    a caller wired up wrongly rather than a module written wrongly.
    """
    before = store.revisions(table=TABLE)
    made = asyncio.run(suggest.for_table(TABLE))
    after = store.revisions(table=TABLE)

    assert made, "the model returned no proposals for a 500,000-row table with planted defects"
    assert len(after) == len(before), (
        f"the store grew from {len(before)} to {len(after)} revisions while proposals were "
        "generated. F3 proposes; only a person accepts."
    )
    for proposal in made:
        assert proposal.type in catalog.TYPES, f"{proposal.type} is outside the catalog"
        assert proposal.status == store.PROPOSED, f"{proposal.type} is {proposal.status!r}"
        assert (
            "rows scanned" in proposal.evidence
        ), f"{proposal.type}'s evidence does not cite the scan: {proposal.evidence!r}"
        assert proposal.statement.strip() and not unsubstituted(
            proposal
        ), f"{proposal.type} has no readable statement: {proposal.statement!r}"
