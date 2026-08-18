"""F3 · candidate rules, each carrying the numbers it was inferred from — and none of them saved.

WHAT THE MODEL IS ACTUALLY ASKED FOR, AND WHAT IT IS NOT. It picks a `type` from the
catalog and fills in its `kwargs`. That is the whole of its output surface. The plain
English sentence comes from `app/rules/catalog.py::english()` — the writer F4's authoring
path shares, because a formatter here as well would be the second copy the catalog exists
to prevent — and the evidence line comes from the profile. So **every number a human
reads here was measured, not written by a model**. LT-2b is why the split is drawn
exactly there: the model proposed `order_total BETWEEN 0 AND 89,400`, which is true of
every row it saw, overfits the observed maximum, and is indistinguishable from a good
rule until you can see that 89,400 is simply the largest value in the table. A model that
also authored its own evidence line would be authoring the one thing that exposes it.

THE EVIDENCE LINE IS THE MODEL'S OWN INPUT, NOT A STORY TOLD ABOUT IT AFTERWARDS.
`evidence()` builds one line per column and `_prompt()` puts those same lines in front of
the model. One function, both uses — so "the reviewer sees what the model saw" is a
property of the code rather than an intention.

NOTHING HERE CAN SAVE OR RUN ANYTHING. This module imports neither `app/rules/store.py`
nor `app/dq/ge_runtime.py`, which is asserted rather than promised
(`tests/test_rule_suggestion.py::test_the_generator_can_neither_store_nor_execute`).
A `Proposal` is not a stored rule and has no id: it is a row on a screen with an Accept
button, and pressing that button is what calls `store.propose()` — the one door where
INV-2's full gate (our sanity table AND the framework's constructor) runs.

WHAT IT DOES ENFORCE, BEFORE A HUMAN EVER SEES IT:
  · the type is in the catalog. A type outside it raises `RuleRejected` — the same
    exception the authoring door raises — and takes the whole batch with it. SPEC F3
    calls it a defect, and a defect that silently drops one rule out of ten hides the
    only signal there is that the menu handed to the model stopped constraining it.
  · `validator.sanity()` — layer 1 of INV-2, called by name rather than re-typed. It is
    pure, so it costs nothing and needs no framework, and it is what stops an inverted
    bound or an empty value set reaching a review screen. The column name is checked
    against the LIVE schema (SPEC §3.1) using the profile's own column list, which came
    from `information_schema` — so the check costs no second round trip.
  · a proposal without evidence cannot be constructed at all: the field is required and
    blank is refused.

WHAT IT DELIBERATELY DOES NOT DO: rank, score, or filter out the business-naive ones. The
meaning is not in the sample (LT-2b), so the countermeasure is the evidence line plus a
human (F12) — not a cleverer filter that would be wrong more quietly.

HOW MANY IT PROPOSES IS NOT THIS MODULE'S NUMBER. `limit` is an argument on every
function that has an opinion about the count, and its one caller passes
`app/rules/store.py::BULK_CAP` — the same number the screen prints on the bulk control
and the same one `judge_batch` refuses a selection past. It used to be a constant here,
and the two drifted: this module asked for TEN while the screen promised EIGHT and
explained itself with "every evidence line is on screen when you press it", which is the
ARGUMENT for why bulk accept is safe rather than a preference about list length. A
sentence that stops being true at the tenth proposal stops being true exactly when it
matters. The number lives with the module that refuses one past it; the prompt, the
slice and the copy all take it as an argument.

ponytail: the model is asked ONCE and its reply is used or refused — no retry, no repair
prompt, no second call to fix a malformed rule, so one bad rule costs the whole $0.04
batch. The upgrade path is a retry at the call site, and it stays unbuilt until a real
reply has actually failed here.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app import model
from app.dq import profile
from app.rules import catalog
from app.rules.validator import NOT_IN_CATALOG, RuleRejected, sanity

# The one state a proposal can be in. Written here rather than imported from
# `app/rules/store.py`: the store owns the workflow, and importing it would put the
# INSERT into this module's import graph for the sake of an eight-letter string. The
# gate asserts the two agree.
PROPOSED = "proposed"

SEPARATOR = " · "

SYSTEM = (
    "You propose data quality rules for a database table from its statistics. "
    "You may only use expectation types from the catalog you are given, and only the "
    "parameters each one lists. Reply with a single JSON object and nothing else — no "
    "prose, no code fences, no explanation."
)


@dataclass(frozen=True)
class Proposal:
    """One candidate rule, unsaved, with the numbers behind it attached.

    `status` is a field with exactly one legal value rather than a constant nobody can
    see: a caller that tries to build an `accepted` proposal is refused here, so "no
    proposal is stored as an active rule" cannot be undone with a keyword argument.
    `accepted` is reachable only through `store.set_status()`, by a person.

    `evidence` has no default. Omitting it is a `TypeError` from Python itself and
    blanking it is refused below — which is the mechanism behind SPEC F3's promise that
    every proposal cites what justifies it. A proposal that has lost its evidence line is
    exactly LT-2b's `order_total BETWEEN 0 AND 89,400` with nothing left to give it away.
    """

    type: str
    kwargs: Mapping[str, Any]
    statement: str
    evidence: str
    status: str = PROPOSED

    def __post_init__(self) -> None:
        if self.type not in catalog.TYPES:
            raise RuleRejected(
                f"{self.type!r} {NOT_IN_CATALOG} — there are {len(catalog.TYPES)}, and this is "
                "not one of them. The catalog IS the menu the model was handed, so a type "
                "outside it means the menu stopped constraining the reply (SPEC F3)."
            )
        if self.status != PROPOSED:
            raise RuleRejected(
                f"a proposal is {PROPOSED!r}, never {self.status!r}. Nothing this module "
                "produces has been judged by anyone; a rule becomes accepted only through a "
                "person, and only then does it execute or count toward coverage."
            )
        if not self.statement.strip():
            raise RuleRejected(
                f"{self.type} was proposed with no plain-English statement. A domain expert "
                "judges the sentence, not the expectation type."
            )
        if not self.evidence.strip():
            raise RuleRejected(
                f"{self.type} was proposed with no evidence. LT-2b's proposal was true of "
                "every row it saw and still wrong about the business; the numbers it was "
                "inferred from are the only thing that shows a reviewer which is which."
            )

    @property
    def column(self) -> str | None:
        """The column this rule names, or None for a table-level rule. Derived, never passed."""
        named = self.kwargs.get("column")
        return str(named) if named is not None else None


# How long a batch of proposals stays on the screen without being asked for again.
# `app/dq/profile.py::CACHE_SECONDS`, deliberately the same number and for a stronger
# version of the same reason: the evidence line under a proposal comes from the profile,
# so a memo that outlived the profile would show a reviewer numbers the proposal was not
# inferred from. Five minutes is also the budget INV-1 gives one table's review.
MEMO_SECONDS = profile.CACHE_SECONDS

_MEMO: dict[tuple[str, int], tuple[float, tuple[Proposal, ...]]] = {}


async def for_table(table: str, limit: int) -> tuple[Proposal, ...]:
    """Profile `table`, ask the model for at most `limit` rules, hand back proposals.

    Saves nothing.

    Three steps, and the split is what makes the rest of this testable without spending
    money: the profile is cached (F2), the model call is the one billed line, and
    everything that turns a reply into proposals is a pure function of a profile and a
    dict.

    THE MEMO IS NOT STORAGE, and the distinction is the one this whole module rests on.
    A proposal is still unsaved: it has no id, no row, no state anyone can act on, and
    `tests/test_rule_suggestion.py::test_the_generator_can_neither_store_nor_execute`
    still holds, because this dict is in a process and the store is a table. What it
    buys is that F12's screen can be RELOADED. Without it, every reload of the rules
    page is another $0.04 and another 6.6 s (LT-2b) for a list the reader was already
    looking at — and a screen that charges for the back button is a screen people stop
    pressing buttons on.

    ponytail: a module-level dict with a timestamp, exactly like `profile.of`. No
    eviction, no size bound, no lock. Ceiling: one entry per table for five minutes, in
    a single-process demo server. The upgrade path is the same one that module names.
    The key carries the limit as well as the table, so a memo cannot answer a request
    for eight with a batch of ten somebody asked for first.
    """
    memoised = _MEMO.get((table, limit))
    if memoised is not None and time.monotonic() - memoised[0] < MEMO_SECONDS:
        return memoised[1]

    profiled = profile.of(table)
    reply = await model.ask_json(_prompt(profiled, limit), SYSTEM)
    made = proposals(profiled, reply.data, limit)
    _MEMO[(table, limit)] = (time.monotonic(), made)
    return made


def proposals(
    profiled: profile.TableProfile, reply: Mapping[str, Any], limit: int
) -> tuple[Proposal, ...]:
    """A parsed model reply in, proposals out. Pure — no database, no model, no store.

    Raises `RuleRejected` for a reply with no rules in it rather than returning an empty
    tuple, for the same reason `app/model.py` refuses to return `{}`: on a review screen
    "no proposals" reads as "this table needs no rules", which is a claim nobody made.

    `limit` is enforced HERE as well as being asked for in the prompt, because a prompt
    is a request and this is the only thing that makes the count true: a model that
    replies with twelve is a reply, not an error, and the eleventh proposal on that
    screen is one the bulk control's own sentence has stopped covering.
    """
    rules = reply.get("rules")
    if not isinstance(rules, list) or not rules:
        raise RuleRejected(
            f"the model's reply carried no rules: {str(reply)[:200]}. An empty proposal list "
            "reads on screen as 'this table needs none', so it surfaces as a failure instead."
        )
    columns = frozenset(column.name for column in profiled.columns)
    return tuple(_proposal(profiled, columns, rule) for rule in rules[:limit])


def _proposal(profiled: profile.TableProfile, columns: frozenset[str], rule: Any) -> Proposal:
    """One rule from the model, checked, and dressed in the profile's own numbers."""
    if not isinstance(rule, Mapping) or not isinstance(rule.get("type"), str):
        raise RuleRejected(
            f"a proposal must be an object carrying a `type`; got {str(rule)[:120]}. The reply "
            "shape is stated in the prompt, so another shape means the prompt was not followed."
        )
    etype = str(rule["type"])
    given = rule.get("kwargs")
    kwargs = dict(given) if isinstance(given, Mapping) else {}
    # Layer 1 of INV-2, by name from the one module that owns it: the catalog membership
    # refusal, unknown or missing parameters, a tolerance that is not a proportion, the
    # per-type sanity table, and the live-schema check on any column the model named.
    # Pure, framework-free, free. Layer 2 runs at the store, on the rule a person accepted.
    sanity(etype, kwargs, profiled.table, columns)
    return Proposal(
        type=etype,
        kwargs=kwargs,
        statement=catalog.english(etype, kwargs),
        evidence=evidence(profiled, kwargs.get("column")),
    )


def evidence(profiled: profile.TableProfile, column: str | None) -> str:
    """The line the reviewer reads, and the line the model was shown. One writer, two uses.

    `500,000 rows scanned · 0 nulls · 45,102 distinct · min observed 0.00 · max observed 89,400.00`

    Full digits, never `500K` — the same rule `app/dq/status.py` states for the sampling
    disclosure, and for the same reason: this is the sentence that exists to be checked
    against the table.

    A column whose whole distinct set is known cites the SET instead of its bounds: for
    `status` the four values are strictly more informative than a min and a max, and they
    are what makes a typo like `shippd` visible to the person judging the rule.
    """
    parts = [f"{profiled.total_rows:,} rows scanned"]
    found = next((c for c in profiled.columns if c.name == column), None)
    if found is None:
        return SEPARATOR.join(parts)
    parts.append(f"{found.total_rows - found.non_null:,} nulls")
    if found.values is not None:
        parts.append(f"{found.distinct:,} distinct: {', '.join(found.values)}")
        return SEPARATOR.join(parts)
    parts.append(f"{found.distinct:,} distinct")
    if found.minimum is not None:
        parts.append(f"min observed {found.minimum}")
    if found.maximum is not None:
        parts.append(f"max observed {found.maximum}")
    return SEPARATOR.join(parts)


def _prompt(profiled: profile.TableProfile, limit: int) -> str:
    """Everything the model is given — and it is a bounded string by construction.

    SPEC §3.1: aggregate statistics and a bounded sample, never full table contents. The
    bound is not enforced here. `profile.TableProfile` refuses a sample larger than
    `SAMPLE_ROWS`, and a column with more distinct values than `LOW_CARDINALITY` reports
    its count and no values at all — so this function cannot leak a table it was never
    handed, whatever it does. It serialises what it was given and nothing else.

    The menu is `catalog.ENTRIES`, rendered. No module here declares how long it is.
    """
    stats = "\n".join(
        f"  {c.name} ({c.data_type}) — {evidence(profiled, c.name)}" for c in profiled.columns
    )
    menu = "\n".join(
        f"  {e['type']}(" + ", ".join(_parameters(e)) + f") — {e['english']}"
        for e in catalog.ENTRIES
    )
    return f"""Table: {profiled.table}

Columns, with statistics measured over the whole table:
{stats}

{len(profiled.sample)} example rows — the rows the scan reached first, not a representative
distribution, and not the table:
{json.dumps(list(profiled.sample), default=str)}

The only check types you may propose, with their parameters (required first, [optional] in
brackets) and the sentence each one turns into:
{menu}

Propose at most {limit} rules for this table. Prefer a rule a business owner would
recognise as an invariant over one that merely restates the statistics above. Reply with
exactly this JSON object:
{{"rules": [{{"type": "<a type from the list above>", "kwargs": {{...}}}}]}}
"""


def _parameters(entry: Mapping[str, Any]) -> Sequence[str]:
    return list(entry["required"]) + [f"[{name}]" for name in entry["optional"]]
