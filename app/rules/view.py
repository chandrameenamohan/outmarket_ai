"""What a screen is handed about a rule — composed once, here, in the server.

F14 says a rule has an address and renders standalone: a stranger opens the URL cold,
with no prior navigation, and has to be able to judge the thing in front of them. That
means four separate modules have to agree on one payload — the sentence
(`app/rules/catalog.py`), the numbers behind it (`app/rules/suggest.py`), the
configuration it compiles to (`app/dq/ge_runtime.py`, INV-3) and the words on the
buttons (`app/dq/status.py`, INV-5's single writer).

WHY A MODULE AND NOT A DICT LITERAL IN THE HANDLER. `app/api/server.py` says out loud
what it is not allowed to become — a second place where rules are read or verdicts are
worded — and a payload assembled inside a request handler is exactly that. It is also
the shape every remaining screen in this wave needs (F10's coverage counts, F11's
queue, F12's rule list), so the alternative is the same four imports written out three
more times in three route handlers.

WHY `web/` DOES NOT COMPOSE ANY OF IT. The frontend renders what this returns and
nothing else. That is not a preference: `tests/test_inv5_sampling_disclosure.py`
fails the gate on a second copy of any load-bearing sentence in `web/app`, and the
English statement and the evidence line are the two a component would most naturally
re-derive from `spec` — at which point the sentence a person vouched for and the
sentence the rule executes stop being the same sentence.

ponytail: no cache, no pagination, no field selection. `app/dq/profile.py` already
caches the expensive half (one statistics query per table, five minutes) and every
listing here is scoped to one table, so a page costs one profile lookup however many
rules it renders. Ceiling: a table with hundreds of rules renders all of them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.dq import normalise, profile, runs, status
from app.rules import catalog, store, suggest
from app.rules import schema as live

# The three judgments, paired with the state each one writes. The states are imported
# from the store rather than re-typed: it owns the closed set, and a fourth pair here
# would be a fifth state the CHECK constraint would refuse at 3 a.m. instead of now.
JUDGMENTS: tuple[tuple[str, str], ...] = (
    (store.ACCEPTED, status.ACCEPT_ACTION),
    (store.REJECTED, status.REJECT_ACTION),
    (store.NEEDS_REVIEW, status.ASK_ACTION),
)


def judgments(current: str) -> tuple[dict[str, Any], ...]:
    """The judgments still open to a rule in `current` — which is all of them but its own.

    A button that moves a rule to the state it is already in is a button that appends a
    revision saying nothing changed. The store would accept it (nothing there is
    forbidden); the history is what would carry the noise.
    """
    return tuple(
        # `primary` travels rather than being inferred in the component, because the
        # alternative is `judgment.status === "accepted"` typed into a `.tsx` — a state
        # name in a second language, in the one place where getting it wrong styles the
        # rejection as the obvious thing to press.
        {"status": s, "label": label, "primary": s == store.ACCEPTED}
        for s, label in JUDGMENTS
        if s != current
    )


def summary(rev: store.Revision, profiled: profile.TableProfile) -> dict[str, Any]:
    """One rule as a row: the sentence, the numbers it was inferred from, its state.

    `profiled` is passed in rather than fetched here so a listing pays for one profile
    and not one per rule. It is the caller's job to hand over the profile OF `rev.table`
    — `workbench()`, `queue()` and `of()` are the three that choose it — and handing
    over another table's would produce an evidence line about the wrong table.

    `status` and `state_label` are the same fact in two languages and both travel: the
    raw state is the styling hook and the attribute the browser checks read, the label
    is what a person is shown (`app/dq/status.py::STATE_LABELS`). A screen that rendered
    the raw one would be putting `needs_review` in front of the reader F11 promises no
    schema knowledge to.
    """
    column = rev.spec["kwargs"].get("column")
    return {
        "rule_id": rev.rule_id,
        "revision": rev.revision,
        "table": rev.table,
        "column": column,
        "status": rev.status,
        "state_label": status.STATE_LABELS[rev.status],
        "statement": catalog.english(rev.spec["type"], rev.spec["kwargs"]),
        "evidence": suggest.evidence(profiled, column),
        "reason": rev.reason,
    }


def of(rule_id: str, configuration: bool = False) -> dict[str, Any]:
    """Everything the permalink screen renders. Raises `store.UnknownRule` if there is none.

    `configuration` IS THE ROLE (SPEC F12, Rev 0.4), the same parameter `workbench()`
    below takes and for the same reason: asked for, the rule carries the Great
    Expectations configuration it compiles to; not asked for, the framework is not in
    the answer at all. A payload that always carried it and left the hiding to the
    component would be a promise the DOM could break — and this is the one address a
    domain expert reaches cold, from somebody else's pasted link.

    The configuration is COMPILED, not echoed (`configuration_of()`), so an engineer
    reading the facing pane sees the value that will actually be checked.
    """
    rev = store.latest(rule_id)
    return {
        **summary(rev, profile.of(rev.table)),
        **({"configuration": configuration_of(rev.spec)} if configuration else {}),
        "judgments": judgments(rev.status),
        "reason_label": status.REASON_LABEL,
    }


def configuration_of(spec: Mapping[str, Any]) -> dict[str, Any]:
    """The Great Expectations configuration one spec compiles to, as data.

    `construct()` rather than a copy of the stored spec, because the facing pane is a
    promise about what will EXECUTE: the framework normalises on the way in
    (`min_value=0` becomes `0.0`), and an engineer editing a value that is not the value
    being checked is editing a picture. It is also the moment a stored rule that stopped
    being expressible fails by name, on the screen where somebody can do something
    about it.

    ponytail: one construction per rule rather than one `compile_suite()` over a whole
    table's set. The suite call is cheaper by a constant and fails ALL of them when one
    spec has gone bad — which on the rules screen means an engineer with one broken rule
    loses the page they would fix it on. Ceiling: N framework constructions per render,
    none of which touch the database.
    """
    from app.dq import ge_runtime  # noqa: PLC0415 — INV-3: the framework loads on demand

    return ge_runtime.construct(str(spec["type"]), dict(spec["kwargs"]))


# --- F11 · the review queue ---------------------------------------------------

# One queued item before it is rendered: the rule at its current revision, paired with
# the failing result from the last run if that is what put it here. `None` means the
# rule is queued for the other reason — a person asked for it to be looked at.
Queued = tuple[store.Revision, Mapping[str, Any] | None]


def queued(
    revs: Iterable[store.Revision], records: Mapping[str, runs.Record | None]
) -> tuple[Queued, ...]:
    """The two things a domain expert is the only available answer to. Pure, so it is
    checkable in `make check` with no database — the meaning of the queue is not a
    property of the network.

    F11's acceptance names exactly two populations and this function is the whole of
    that sentence:

      `needs_review`     somebody looked at this rule and could not settle it. That is
                         a REQUEST for this person specifically, and it is the state
                         `amended()` also lands in — a rule whose meaning changed has
                         not been vouched for by anyone.
      currently failing  an accepted rule that the last completed run reports as
                         failing. Nobody asked, but the question "does this violation
                         matter?" has no answer anywhere else in the product.

    NOTHING ELSE IS IN THE QUEUE, and the exclusions are the load-bearing half.
    `proposed` rules are not here: F3 leaves them unsaved beside their evidence on the
    rules screen, and a proposal nobody has staged is not a decision anybody is waiting
    on. `rejected` rules are not here, or a rejection would be a snooze button.
    `passed` accepted rules are not here — a rule doing its job is not a decision.
    `errored` results are not here either, and that is the third state earning its keep
    (LT-1a): a rule that could not RUN is an engineer's problem, and putting it in front
    of a domain expert asks them to judge data nobody looked at.

    The join is by SPEC IDENTITY rather than by rule id, which is what makes an amended
    rule drop out on its own: the run reported on the spec that executed, so a rule
    whose meaning has since changed simply does not match, and the queue never shows a
    verdict beside a sentence that did not produce it.

    ponytail: sorted by table and then by rule id — deterministic, and deliberately NOT
    by severity, which SPEC §5 lists as not built. Ceiling: a hundred-item queue is a
    hundred items in id order, and the first thing to add is a per-table split, which
    is what `?table=` already is.
    """
    out: list[Queued] = []
    for rev in revs:
        record = records.get(rev.table)
        # ONLY AN ACCEPTED RULE MAY CARRY A VERDICT. A run executes accepted rules and
        # nothing else (F6, `normalise.executable`), so a proposed or rejected rule that
        # happens to share a spec with one that ran did not run — and the first version
        # of this function put an unsaved proposal in the queue with somebody else's
        # failure attached to it. The state gate is what stops a verdict being evidence
        # about a rule that never executed.
        failing = None if record is None or rev.status != store.ACCEPTED else _failing(record, rev)
        if rev.status == store.NEEDS_REVIEW or failing is not None:
            out.append((rev, failing))
    return tuple(sorted(out, key=lambda pair: (pair[0].table, pair[0].rule_id)))


def awaiting(
    pairs: Sequence[Queued], profiles: Mapping[str, profile.TableProfile]
) -> tuple[dict[str, Any], ...]:
    """Queued items as the screen renders them — in business language, with the budget.

    Everything a card shows is composed here and nothing is composed in `web/`: the
    English statement, the evidence line, the failing verdict (INV-5's atom, already
    carrying its own sampling clause because it is the string the RUN wrote), INV-4's
    magnitude sentence, the words on the three buttons, and INV-1's position line.

    THE POSITION IS COUNTED WITHIN THE ITEM'S OWN TABLE, not within the queue. INV-1 is
    a promise about "a table's proposals", so a five-minute budget spanning three tables
    would be a different and much weaker claim — and the indicator would go on reading
    "of 14" to somebody who only cares about `orders`. `?table=` narrows the queue; it
    does not change what a decision's position means, which is what stops the scoped and
    unscoped screens disagreeing about the same rule.

    ponytail: no pagination and no client state. The queue is short by construction —
    it is what one person has to settle — and a list that fits on a page needs neither.
    Ceiling: every queued item renders, and the budget line is the only thing telling
    the reader that a long one is long.
    """
    totals = Counter(rev.table for rev, _ in pairs)
    seen: Counter[str] = Counter()
    rendered = []
    for rev, failing in pairs:
        seen[rev.table] += 1
        rendered.append(
            {
                **summary(rev, profiles[rev.table]),
                # The atom, verbatim from the run record. It is not recomposed here and
                # it is not split: the sampling clause lives INSIDE it (INV-5), and the
                # only way to keep that true through a second surface is to move the
                # whole string and never look at its parts.
                "failing": None if failing is None else failing["status"],
                "magnitude": None if failing is None else failing["magnitude"],
                "budget": status.budget(seen[rev.table], totals[rev.table], rev.table),
                "judgments": judgments(rev.status),
                "reason_label": status.REASON_LABEL,
            }
        )
    return tuple(rendered)


def queue(table: str | None = None) -> dict[str, Any]:
    """F11's whole payload: the caveat, and everything waiting on one person's judgment.

    `table` is a FILTER and never a route segment (SPEC F11, bead dq-rbf.3): passing it
    narrows the same queue rather than addressing a different one, which is why it
    arrives as `?table=` and why the unscoped call is the default rather than an error.
    There is no endpoint here that lists tables, and that absence is the feature — the
    only table names that reach this screen are the ones attached to a decision.

    The caveat travels in the payload for the same reason every other sentence does: it
    is `app/dq/status.py`'s, it is the UI expression of LT-2b (every rule the model
    proposed was true of the sample and wrong about the business), and a copy of it
    typed into a component is a copy that can be softened without anyone noticing.

    Two reads per table with rules — the run record and the cached profile — and the
    profile only for tables that actually put something in the queue.
    """
    if table is not None:
        # SPEC §3.1, and the same guard `desk.workbench` and `plan()` already run: a
        # table name that arrived in a URL is proven against the live schema before it
        # selects anything. Without it this was the one route in the product that
        # answered 200 for a table nobody has — an empty queue and a made-up name look
        # identical, and `/rules?table=nope` and `POST /runs/nope` both refuse it.
        live.columns(table)
    revs = store.current(store.revisions(table=table))
    # ONE READ PER TABLE, not one per rule. The set comprehension is the whole of that
    # and it is not a micro-optimisation: keyed off `revs` directly, a table with thirty
    # rules cost thirty round trips to Supabase for thirty copies of the same record,
    # and `/review` took 22.9 s to answer. The same reasoning is why `profiles` is keyed
    # off the queued pairs rather than off every table that has rules at all.
    records = {name: runs.latest(name) for name in {rev.table for rev in revs}}
    pairs = queued(revs, records)
    profiles = {rev.table: profile.of(rev.table) for rev, _ in pairs}
    return {
        "table": table,
        "caveat": status.REVIEW_CAVEAT,
        "items": list(awaiting(pairs, profiles)),
    }


def _failing(record: runs.Record, rev: store.Revision) -> Mapping[str, Any] | None:
    """The last run's failing result for this exact rule, or None.

    `normalise._identity` rather than a fourth copy of the same three lines: it is the
    join `normalise.normalise()` already makes between a submitted spec and the result
    that came back, and this is the same question asked later. `app/dq/runs.py` keeps
    its own copy for a reason that does not apply here — its import graph may not touch
    the rule store — and `tests/test_run_records.py` pins the two together.
    """
    wanted = normalise._identity(rev.spec)  # noqa: SLF001 — the same join, not a second one
    return next(
        (
            result
            for result in record.results
            if result["verdict"] == "failed" and normalise._identity(result["spec"]) == wanted  # noqa: SLF001
        ),
        None,
    )


# --- F13 · a run record, as the screen that renders it is handed it ------------


def run_record(record_id: str) -> dict[str, Any]:
    """One completed run by id. Raises `runs.UnknownRun` if none was ever written.

    This is the permalink half of F13 and the whole of F9's cache clause on the read
    side: it re-renders a run WITHOUT re-executing it, which is a property of the
    import graph rather than of anyone's manners — `app/dq/runs.py` has no path to the
    executor, and `tests/test_inv3_single_ge_import.py` walks it.

    Nothing here recomposes a verdict. `Record.payload()` already carries the rendered
    status atom that `app/dq/status.py` wrote at the moment the run saw the table, so
    the sampling disclosure survives the round trip as a string (INV-5) instead of
    being rebuilt by a reader that could forget it.
    """
    return _rendered(runs.find(record_id))


def last_run(table: str) -> dict[str, Any]:
    """The most recent completed record for `table`, or the honest absence of one.

    `/runs?table=` is a moving address and `/runs/<recordId>` is a fixed one, which is
    why both exist: the first answers "what does this table look like now", the second
    is the thing you paste into a chat client. Both are answered in the same shape, so
    the screen behind them is one screen.

    A table with no record gets `status.coverage_atom()` — NEVER RUN, and NO RULES on
    top of it when there is nothing that could ever produce a verdict. It occupies the
    same slot a verdict would, so it comes from the same writer; composing "not run
    yet" in a component is how that slot acquires a second author.
    """
    found = runs.latest(table)
    if found is not None:
        return _rendered(found)
    accepted = normalise.executable(store.revisions(table=table))
    return {
        "table": table,
        "record": None,
        "atom": status.coverage_atom(len(accepted)),
        "pending": status.UNSETTLED_ATOM,
    }


def _rendered(record: runs.Record) -> dict[str, Any]:
    """One shape for both readers above: the table, the record, and the empty slot.

    `atom` is None when a record exists because the record's own results carry their
    atoms; the field is present either way so the screen has one shape to render and
    not two.

    `pending` travels on every answer for a reason that is easy to miss: the SCREEN needs
    it before any run has started. A person who presses Run is looking at the previous
    run's verdicts, and those stop being true the instant they press it — so every row
    goes pending on the click rather than a second later when the stream's opening event
    arrives. The text for that is still the single writer's; it just has to be in the
    reader's hands first (`app/dq/status.py`, INV-5's argument one step out).
    """
    return {
        "table": record.table,
        "record": record.payload(),
        "atom": None,
        "pending": status.UNSETTLED_ATOM,
    }
