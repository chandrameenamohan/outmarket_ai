"""SPEC F12 Rev 0.4 · a machine proposal is accepted by NAME, never by sending its rule back.

BEAD dq-8zj, AND IT IS THE ONE LEAK `web/app/framework.ts` COULD NOT CLOSE. That door
strips the framework out of every payload by key name — `configuration`, `raw`, `spec` —
and a machine proposal defeated it by BEING a spec: having no row in the store (F3 —
accepting is the first moment anything is persisted), it identified itself to the accept
path as its own compiled `{type, kwargs}`, carried in the value attribute of its
checkbox. So a domain expert who pressed "Suggest rules from this table's statistics" was
served the framework's own vocabulary in their document, on the one screen both users
work on, and taking it out would have left them a checkbox that accepted nothing.

The fix is a handle: `app/rules/suggest.py` was already memoising the batch for five
minutes, so the browser is told the batch's id and a row's index in it, and nothing else.
This file is the mechanism's half of the check — pure, no database, no model, no browser,
so it runs in `make check`. The OBSERVABLE half is
`tests/e2e/test_framework_absence.py`, which reads the raw bytes of
`/tables/orders/rules?propose=1` as both readers; a mechanism that is right here and
wrong on the wire fails there.

WHAT IS ACTUALLY BEING PINNED IS THE REFUSAL. A handle is a name for something held in a
process's memory, so it stops meaning anything after five minutes, after a restart, and
if somebody makes one up. Each of those has to end in a sentence and NO WRITE (INV-2) —
never in the nearest batch that would have resolved, which would accept eight rules in
place of the eight a person actually read.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Iterator

import pytest
from test_rule_suggestion import CAP, TABLE, proposals

from app.rules import suggest
from app.rules.validator import RuleRejected


def _memoise(table: str, made: tuple[suggest.Proposal, ...], age: float = 0.0) -> suggest.Batch:
    """Put a batch in the memo the way `for_table` would, without paying for a model call.

    It reaches into `_MEMO` on purpose: the alternative is a seam in the product whose
    only caller is this file, and the memo IS the mechanism under test — a check that
    mocked it would be checking a mock. `age` is subtracted from the clock so expiry can
    be exercised without waiting five real minutes for it.
    """
    batch = suggest.Batch(id=secrets.token_urlsafe(9), at=time.monotonic() - age, proposals=made)
    suggest._MEMO[(table, CAP)] = batch
    return batch


@pytest.fixture(autouse=True)
def _clean_memo() -> Iterator[None]:
    """No batch outlives the check that made it — the memo is module state and shared."""
    suggest._MEMO.clear()
    yield
    suggest._MEMO.clear()


def test_a_handle_names_a_proposal_without_carrying_it() -> None:
    """Both halves at once: it resolves to the right row, and it is not that row's rule.

    The first half alone would be satisfied by the defect this replaced — a spec resolves
    to itself perfectly. The second is the one SPEC F12 Rev 0.4 is about.
    """
    made = proposals()
    batch = _memoise(TABLE, made)
    for index, proposal in enumerate(made):
        handle = batch.handle(index)
        assert suggest.resolve(TABLE, handle) is proposal, (
            f"{handle} resolved to something other than the proposal it names. A checkbox is "
            "read through this function; the wrong row here accepts a rule nobody read."
        )
        assert not any(word in handle for word in (proposal.type, "kwargs", "expect_")), (
            f"the handle {handle!r} carries the rule it stands for, so the framework is back "
            "in the domain expert's document under a different name."
        )


def test_a_handle_from_an_expired_batch_is_refused_rather_than_guessed() -> None:
    """INV-2 at the accept path: a name this process no longer holds writes nothing.

    Five minutes is the memo's whole lifetime and a screen left open outlives it, so this
    is the ordinary case rather than the exotic one. The refusal has to say that nothing
    was saved, because that is the claim the reader cannot check from the screen.
    """
    batch = _memoise(TABLE, proposals(), age=suggest.MEMO_SECONDS + 1)
    with pytest.raises(RuleRejected) as refused:
        suggest.resolve(TABLE, batch.handle(0))
    assert "nothing was saved" in str(refused.value), (
        f"the refusal does not say nothing was saved: {refused.value}. A person who has just "
        "pressed Accept on eight rules cannot tell from the screen whether they landed."
    )


def test_a_forged_handle_is_refused_rather_than_resolved() -> None:
    """Five shapes of a name that stands for nothing, and one refusal for all of them.

    An id never issued, an index past the end of a real batch, a bare id with no index, a
    bare index, and nothing at all. `Batch.id` is `secrets.token_urlsafe`, so guessing one
    is not reachable by counting — but the refusal is what makes that true rather than
    merely likely, and it is what stands between a forged value attribute and a write.
    """
    batch = _memoise(TABLE, proposals())
    forged = ("nosuchbatch.0", batch.handle(len(batch.proposals)), batch.id, ".0", "")
    resolved = []
    for handle in forged:
        try:
            resolved.append((handle, suggest.resolve(TABLE, handle)))
        except RuleRejected:
            continue
    assert not resolved, (
        f"these handles name nothing and resolved anyway: {resolved}. Every one of them would "
        "reach store.judge_batch as a rule somebody is about to be told they accepted."
    )


def test_a_handle_cannot_carry_a_proposal_onto_another_table() -> None:
    """The batch was inferred from ONE table's statistics, and it stays on it.

    `store.judge_batch` takes the table from the body and the specs from `resolve()`, so a
    handle that resolved regardless of table would let a rule proposed for `orders` be
    written against another table — with an evidence line measured somewhere else, which
    is the one thing standing between a reviewer and LT-2b's business-naive proposal.
    """
    batch = _memoise(TABLE, proposals())
    with pytest.raises(RuleRejected) as refused:
        suggest.resolve("payments", batch.handle(0))
    assert str(refused.value), "a refusal with no sentence in it"
