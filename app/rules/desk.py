"""F12 · the translation desk — what the screen where the two users meet is handed.

THE SCREEN THIS MODULE FEEDS IS THE ONE THE WHOLE UI DIRECTION WAS CHOSEN FOR. Its idea
is a BILINGUAL SPREAD: the plain-English statement and the Great Expectations
configuration as facing pages, warm paper against cool
(`design/ux-variant-workbench.html`). SPEC F12 was amended to Rev 0.4 for it, and the
amendment is the reason `configuration` is a PARAMETER here rather than a field a client
filters:

    asked for      every rule carries the configuration it compiles to, and the engineer
                   gets facing pages.
    not asked for  the word does not appear in the answer. The domain expert's document
                   holds no framework to reveal by scrolling, by viewing source, or by a
                   stylesheet failing to load.

That is stronger than the "collapsed by default" it replaced, and it is why the decision
is taken on the server: a pane hidden with CSS is a pane that shipped.

WHY THIS IS ITS OWN MODULE AND NOT MORE OF `app/rules/view.py`. Everything in there is a
READ — one rule, a listing, the queue, a run record. Three of the five things below are
not reads at all: two of them spend money on a model call and one of them appends a
revision. The seam is real, and the size threshold in
`tests/test_code_quality_thresholds.py` is what made it visible.

WHAT IS NOT HERE, AND WHERE IT IS INSTEAD. No cap, no state machine, no reason
requirement: `app/rules/store.py::judge_batch` owns all three, because a limit enforced
next to the screen is a limit anybody can post past. No sentences either — every word
this screen renders comes from `app/dq/status.py` through `copy()` below, and the gate
fails on a second copy of any of them under `web/app`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from app.dq import profile, status
from app.rules import authoring, catalog, store, suggest
from app.rules.view import configuration_of, judgments, summary


def catalog_rail(
    revs: Iterable[store.Revision], configuration: bool = False
) -> tuple[dict[str, Any], ...]:
    """B6 · the whole menu, from the one file, with this table's types marked.

    The rail answers "what can this thing even express?", which is the question every
    refusal raises and the only honest place to answer it. It is rendered from
    `catalog.ENTRIES` and nothing here declares how long that is — the count is `len()`
    on both sides of the wire, which is what makes UI/compiler drift impossible rather
    than unlikely (`tests/test_catalog_and_copy.py`).

    THE MENU IS BILINGUAL TOO, and `configuration` decides which language it arrives in.
    An expectation's `type` is a framework identifier, so it goes to the engineer only;
    the domain expert gets the same entries as the sentence each one turns into — *"Every
    {column} has a value"* — which is a better answer to their version of the question
    anyway. Both readers see one menu of the same length, and neither meets a name from
    the other's language.
    """
    used = {rev.spec["type"] for rev in revs}
    return tuple(
        {
            "english": entry["english"],
            "in_use": entry["type"] in used,
            **({"type": entry["type"]} if configuration else {}),
        }
        for entry in catalog.ENTRIES
    )


def workbench(table: str, configuration: bool = False) -> dict[str, Any]:
    """This table's rules, the menu behind them, and the screen's own copy. One document.

    Rules arrive ordered by state and then by id, so the two populations that need a
    decision — `needs_review` and, after a suggestion, whatever a person has staged —
    do not move around under the reader between renders. It is a deterministic order and
    deliberately not a priority: SPEC §5 lists severity as not built, and a screen that
    ranked rules would be claiming to know which one matters.

    `bulk` and `held` TRAVEL AS BOOLEANS rather than being derived in the component from
    `status`, and it is the same argument `judgments()` makes about `primary`: a state
    name typed into a `.tsx` is the store's closed set living in a second language, in
    the one place where getting it wrong puts a checkbox on a rule nobody has settled.
    They are also the two facts SPEC F12's acceptance is stated in — a `needs_review`
    proposal carries no checkbox ELEMENT at all, not a disabled one — so the screen is
    told which rows are which rather than working it out.

    THE PROFILE IS FETCHED BEFORE THE RULES ARE READ, and unconditionally, because it is
    also SPEC §3.1's identifier check: a table name that reached us from a URL is proven
    real against the live schema before anything is composed from it, and an unknown one
    raises `schema.UnknownTable` — a 404 — instead of rendering a perfectly calm screen
    saying this table has no rules. A typo in an address is not an empty table, and the
    two must not look alike. It costs nothing on a warm cache (F2, five minutes) and the
    screen needed the profile anyway, for the evidence line under every rule.

    One framework construction per rule when the configuration is asked for, and no
    database work per rule at all.
    """
    profiled = profile.of(table)
    revs = store.current(store.revisions(table=table))
    rules = []
    for rev in sorted(revs, key=lambda r: (r.status, r.rule_id)):
        rules.append(
            {
                **summary(rev, profiled),
                "judgments": judgments(rev.status),
                "bulk": rev.status == store.PROPOSED,
                "held": rev.status == store.NEEDS_REVIEW,
                **({"configuration": configuration_of(rev.spec)} if configuration else {}),
            }
        )
    return {
        "table": table,
        "rules": rules,
        "catalog": list(catalog_rail(revs, configuration)),
        "cap": store.BULK_CAP,
        "copy": copy(),
    }


async def proposals(table: str, configuration: bool = False) -> dict[str, Any]:
    """F3's candidates, dressed for the screen and still unsaved.

    One billed model call, memoised for five minutes by `app/rules/suggest.py` so a
    reload is free. NOTHING HERE HAS AN ID, because nothing here has a row: the `Accept`
    under each one is what reaches `store.judge_batch()`, and that is the first moment
    anything is persisted (SPEC F12).

    `status` travels from the generator's own frozen field rather than being written
    here, so the screen cannot render an unsaved proposal as anything but the one state
    a proposal can be in. The evidence line travels for the harder reason: LT-2b's
    proposal was true of every row it saw and still wrong about the business, so the
    numbers are the only thing that shows a reviewer which is which.

    HOW MANY ARE ASKED FOR IS `store.BULK_CAP`, HANDED OVER. The generator owns no count
    of its own — it asked for ten while this screen's own sentence promised eight, and
    the sentence is the argument for why bulk accept is safe rather than a note about
    list length. One number, from the module that refuses a selection past it, reaching
    the prompt, the slice and `copy()` below.

    A PROPOSAL THE TABLE ALREADY HAS IS DROPPED, and the comparison is between COMPILED
    specs rather than between what the model typed: the store holds the framework's own
    normalisation (`min_value=0` as `0.0`), so comparing raw kwargs would re-offer a rule
    somebody accepted five minutes ago with a differently-spelled number. Offering it
    again is not merely noise — accepting it twice writes two rules that check the same
    thing, and coverage then counts a table as better protected than it is.

    A ROW TRAVELS AS A `handle`, NEVER AS THE SPEC IT NAMES (bead dq-8zj). This function
    used to spread `**spec` into every row, because the checkbox that accepts a proposal
    had nothing else to identify it by — which put the compiled expectation's own type
    name and kwargs in the DOMAIN EXPERT's document, on the one screen both users work on,
    and `web/app/framework.ts`'s key-name filter could not take them out without leaving
    that reader a checkbox that accepts nothing. The handle is `app/rules/suggest.py`'s
    batch id and an index into it, resolved back on the way in by `resolve()`; the index
    is into the WHOLE batch and not into `rendered`, because the loop skips the ones the
    table already holds. The engineer still gets `configuration` under the flag, so the
    facing pane is unchanged and only the identity moved.
    """
    batch = await suggest.for_table(table, store.BULK_CAP)
    held = {_key(rev.spec) for rev in store.current(store.revisions(table=table))}
    rendered = []
    for index, proposal in enumerate(batch.proposals):
        spec = configuration_of({"type": proposal.type, "kwargs": dict(proposal.kwargs)})
        if _key(spec) in held:
            continue
        rendered.append(
            {
                "handle": batch.handle(index),
                "column": proposal.column,
                "statement": proposal.statement,
                "evidence": proposal.evidence,
                "status": proposal.status,
                # The same pair `view.summary()` sends for a stored rule: the raw state
                # for the DOM and the English one for the reader. A proposal is the row
                # where that matters most — it is the one a screen must not let anybody
                # mistake for something that is already saved.
                "state_label": status.STATE_LABELS[proposal.status],
                # ALL THREE JUDGMENTS ARE OPEN, and that falls out of `judgments()` rather
                # than being asserted here: it drops the state a rule is already in, and a
                # proposal is in none of the three — it is `proposed`, which is not a
                # judgment anybody made. So the same function that answers for a stored
                # rule answers for this one, and the labels stay the single writer's.
                "judgments": judgments(proposal.status),
                # Always selectable, and never held: a machine proposal is the population
                # bulk accept exists for. `Proposal.__post_init__` refuses any status but
                # `proposed`, so this is a fact about the type rather than a claim here.
                "bulk": True,
                "held": False,
                **({"configuration": configuration_of(spec)} if configuration else {}),
            }
        )
    return {"table": table, "proposals": rendered}


async def draft(request: str, table: str, configuration: bool = False) -> dict[str, Any]:
    """F4 · one English sentence in; a draft to confirm, or a refusal that wrote nothing.

    BOTH OUTCOMES ARE A 200, and that is not a shrug about status codes. A refusal is
    this endpoint working: the product's headline claim is that a rule it cannot express
    is refused with a reason rather than approximated into the nearest one that compiles.
    So "we could not express that" is an ANSWER, and an HTTP error would file it beside
    "the database is not answering" — two things a person reads differently and a screen
    has to render differently.

    The refusal's sentence already ends with `NOTHING_SAVED`, welded on by the single
    writer (`status.refusal`) for the same reason the sampling clause is welded to a
    verdict: it is the claim a reader cannot check from the screen.
    """
    outcome = await authoring.author(request, table)
    if isinstance(outcome, authoring.Refused):
        return _refusal(table, request, outcome)
    return {
        "table": table,
        "request": request,
        "draft": {
            "type": outcome.spec["type"],
            "kwargs": dict(outcome.spec["kwargs"]),
            "statement": outcome.english,
            **({"configuration": configuration_of(outcome.spec)} if configuration else {}),
        },
        "refusal": None,
    }


async def revise(rule_id: str, spec: Mapping[str, Any] | None, statement: str | None) -> Any:
    """One rule, one revision on — from either side of the spread.

    THE TWO DOORS ARE ONE FUNCTION BECAUSE THEY ARE ONE OUTCOME, and that is the whole
    bilingual claim made mechanical. The engineer hands over a configuration and it is
    revalidated; the domain expert hands over a sentence and it is COMPILED AGAIN through
    F4's authoring path, which produces a spec that has been through the same validator.
    Both end at `store.amend()`, which validates once more on the way in and lands the
    rule in `needs_review` — because a change to what a rule CHECKS is judged by a person
    before it runs, or the two-user workflow is decoration.

    The expert's door can REFUSE and the engineer's cannot in the same way: a sentence
    can be inexpressible, where a configuration either validates or raises. So a refusal
    comes back in F4's own shape and nothing is amended — the same promise the authoring
    field makes, kept on a rule that already exists.
    """
    prior = store.latest(rule_id)
    if statement is not None:
        outcome = await authoring.author(statement, prior.table)
        if isinstance(outcome, authoring.Refused):
            return _refusal(prior.table, statement, outcome)
        spec = outcome.spec
    if spec is None:
        raise ValueError(
            "a revision carries either a configuration or a sentence, and this one carried "
            "neither. There is no third way to change what a rule checks."
        )
    store.amend(rule_id, str(spec["type"]), dict(spec.get("kwargs") or {}))
    return {"rule_id": rule_id, "revised": True}


def copy() -> dict[str, str]:
    """Every load-bearing sentence F12's screen renders, from the one writer.

    A dict rather than a dozen top-level keys, so the boundary is visible in both
    languages: what is inside it is `app/dq/status.py`'s and is rendered verbatim, what
    is outside it is data. `tests/test_inv5_sampling_disclosure.py` fails the gate on any
    of these appearing as a literal under `web/app`.

    `bulk_action` is the one that travels as a TEMPLATE rather than a sentence, and the
    reason is in that constant: its number changes on every click of a checkbox, which is
    not a fact worth a server round trip.
    """
    return {
        "compiled_token": status.COMPILED_TOKEN,
        "compiled_caveat": status.COMPILED_CAVEAT,
        "unsaved": status.UNSAVED_NOTE,
        "bulk_note": status.bulk_note(store.BULK_CAP),
        "bulk_action": status.BULK_ACTION_TEMPLATE,
        "bulk_excluded": status.BULK_EXCLUDED,
        "restate": status.RESTATE_LABEL,
        "reconfigure": status.RECONFIGURE_LABEL,
        "amended": status.AMENDED_NOTE,
        "reason_label": status.REASON_LABEL,
        # F4's refusal wears a chip like every other outcome on this screen — see
        # `status.REFUSED_TOKEN` for why prose alone reads as a message rather than as
        # a decision that was recorded.
        "refused_token": status.REFUSED_TOKEN,
    }


def _key(spec: Mapping[str, Any]) -> str:
    """One spec as a comparable string — the type and its kwargs, key order removed.

    `json.dumps(..., sort_keys=True)` rather than a frozenset of items, because a kwarg's
    value can be a list (`value_set`) and lists are not hashable. It is a comparison key
    and never travels anywhere: `app/dq/normalise.py::_identity` is the equivalent join
    on the run side, and the two are deliberately not shared — that one is about matching
    a result to the spec that produced it, this one about two rules meaning the same thing.
    """
    return json.dumps({"type": spec["type"], "kwargs": spec["kwargs"]}, sort_keys=True, default=str)


def _refusal(table: str, request: str, refused: authoring.Refused) -> dict[str, Any]:
    """One refusal shape for both doors that can produce one — the field, and the edit.

    `detail` is the model's own wording and is carried separately from `message`, which
    is ours: a refusal phrased by the model is a refusal whose wording changes between
    calls, and the sentence naming our capability boundary has to be ours or it is not a
    promise (`app/rules/authoring.py`).
    """
    return {
        "table": table,
        "request": request,
        "draft": None,
        "refusal": {
            "reason": refused.reason,
            "message": refused.message,
            "detail": refused.detail,
        },
    }
