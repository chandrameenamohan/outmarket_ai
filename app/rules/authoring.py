"""F4 · English becomes a validated unsaved rule, or a refusal that writes nothing.

The product's headline claim and its most important refusal, in one module.

THE REFUSAL IS THE LOAD-BEARING HALF. An inexpressible rule is REFUSED with a
reason — never stored as `unsupported`, never approximated into the nearest
single-column rule that does compile. Both dodges are worse than the refusal:
a stored non-rule reports coverage the table does not have, and an approximation
reports the WRONG coverage while looking like the right one. So this module has
exactly two outcomes, `Draft` and `Refused`, and neither of them persists.

NOTHING HERE CAN WRITE, and that is a fact about the import graph rather than
about the control flow below. There is no store, no cursor and no INSERT in
reach; `app/rules/store.py` is the only writer in the product and it is reached
by a person accepting a draft, one layer up. Same mechanism, same argument as
`app/rules/validator.py` — see
`tests/test_f4_authoring.py::test_refusal_path_performs_zero_writes`, which
asserts the imports rather than trusting this paragraph.

THREE WAYS A REQUEST FAILS, and the difference matters to the person reading it:

    multi_column   the request relates two columns. A real capability gap with a
                   named boundary (SPEC F4, and the first thing v2 adds).
    unclear        the request could not be read as a check at all. An
                   explanation, never a guess — LT-2b is the evidence that a
                   guess here would be confident and wrong.
    invalid        the model produced something the validator refused. The
                   validator's own reason is carried through verbatim, because it
                   already names the offending thing (INV-4).

WHO CLASSIFIES, AND WHO WRITES THE SENTENCE. The model classifies, from a closed
set of two codes; we write the copy, from `app/dq/status.py`. That split is the
point — a refusal phrased by the model is a refusal whose wording changes between
calls, and the sentence naming our capability boundary has to be OURS or it is
not a promise. The model's own one-line `why` rides along as `detail`, clearly
marked as its words and never substituted for ours.

AND THE CLASSIFICATION IS NOT LOAD-BEARING FOR SAFETY, only for wording. The
catalog holds no multi-column type at all, so a model that ignored the menu and
answered "shipped_date must be after order_date" with a real pair expectation is
refused anyway — by the validator, as `invalid`. The refusal is honest either
way; the code only decides which of the two sentences a user reads.

WHAT THE MODEL IS GIVEN: the table's column names and types, and the catalog
menu. No rows, no statistics, no sample — this is a translation task, not an
inference one (SPEC §3.1's rule is satisfied by not needing the data at all).
Every identifier it returns is checked against that live schema by the validator
before anything is built from it.

NOT A CONVERSATION. SPEC's non-goal, restated as a shape: one request in, one
outcome out, `max_turns=1` underneath. A rule the system cannot express does not
become expressible by asking again in different words, so a follow-up turn would
only give the model room to approximate.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app import model
from app.dq import status
from app.rules import catalog, validator
from app.rules import schema as live

# The closed set of refusal reasons. The first two are the model's to choose; the
# third is ours and is reached only by the validator saying no.
MULTI_COLUMN, UNCLEAR, INVALID = "multi_column", "unclear", "invalid"

# Which sentence each model-chosen code turns into. This dict is also the whitelist:
# a code outside it is not a refusal we know how to explain, so it degrades to
# `unclear` rather than reaching a user as a bare identifier.
EXPLANATION = {MULTI_COLUMN: status.MULTI_COLUMN_LIMIT, UNCLEAR: status.UNCLEAR_REQUEST}

# The model's own explanation is untrusted text on its way to a screen. Bounded here
# because nothing downstream can be relied on to bound it; one sentence is what the
# prompt asks for and roughly what this allows.
DETAIL_LIMIT = 300

SYSTEM = (
    "You turn one English sentence into one data-quality check on one table, or you refuse. "
    "Reply with exactly one JSON object and nothing else — no prose, no code fences."
)

# The reply contract, stated to the model in the same three shapes this module parses.
# Written out rather than generated: it is instructions, and the only thing in it that
# must track the catalog is the menu, which is rendered from the catalog below.
_CONTRACT = """Reply with exactly ONE of these three objects:

  {"check": {"type": "<a type from the menu>", "kwargs": {...}}}
  {"cannot": "multi_column", "why": "<one sentence>"}
  {"cannot": "unclear", "why": "<one sentence>"}

Choose "multi_column" when the request relates or compares two different columns. \
No such check is on the menu, and the nearest single-column one would claim \
protection the table does not have.

Choose "unclear" when you cannot tell which column is meant, or what would make a \
row wrong. Refusing is correct here; guessing is not.

Otherwise return a check, under these rules:
- Use only a type from the menu and only its listed parameters.
- Use only the column names listed above, spelled exactly as they appear.
- State only the bound the request states. "can never be negative" is a lower \
bound of 0 and no upper bound at all — an upper bound taken from what the data \
happens to contain today is a rule that fails the first time the business grows.
"""


@dataclass(frozen=True)
class Draft:
    """A validated rule that has NOT been stored, waiting for a person to confirm it.

    There is no `saved` field, and its absence is deliberate: a flag that is always
    False is a label, and this product's claim is stronger than a label. Nothing in
    this module's import graph can persist anything, so an unsaved draft is the only
    kind there is. Accepting one is `app/rules/store.py::propose()`, called by the
    layer that has a person in front of it.

    `spec` is exactly what `validator.validate()` returned — the framework's own
    normalisation, the shape the store holds and the compiler consumes — so
    accepting a draft re-validates nothing and changes nothing.

    `english` is the sentence the person actually judges. They are not confirming an
    expectation type; they are confirming a claim about their business.
    """

    request: str
    table: str
    spec: Mapping[str, Any]
    english: str


@dataclass(frozen=True)
class Refused:
    """A request that produced no rule, and the reason, and nothing else anywhere.

    `message` is composed by `app/dq/status.py::refusal()` and always ends with the
    disclosure that nothing was saved — the one claim a user cannot verify from the
    screen. `detail` is the model's own wording and is never a substitute for the
    sentence: it is `None` whenever the model offered nothing usable, which is why
    `message` alone is always enough to render.
    """

    request: str
    reason: str
    message: str
    detail: str | None = None


async def author(request: str, table: str) -> Draft | Refused:
    """One English sentence in; one draft or one refusal out. The whole of F4.

    The live schema is read here rather than passed in, because this is the layer
    that knows which table is being talked about — `app/rules/validator.py` stays a
    pure function of its arguments and `app/rules/schema.py` stays the one reader.
    An unknown table raises `schema.UnknownTable`: that is an operator's mistake or
    a bad link, not a rule the product declined to express, and dressing it as a
    refusal would put it in the same category as the two that matter.
    """
    columns = live.column_types(table)
    reply = await model.ask_json(prompt(request, table, columns), SYSTEM)
    return interpret(request, table, reply.data, [name for name, _ in columns])


def interpret(
    request: str,
    table: str,
    reply: Mapping[str, Any],
    columns: Collection[str],
) -> Draft | Refused:
    """The model's reply, turned into the one outcome or the other. Pure, and testable.

    Split out from `author()` so that every branch below is reachable without a
    billed call: the checks in `tests/test_f4_authoring.py` drive real reply shapes
    through the real validator, and exactly one check spends money proving the model
    produces those shapes from the three sentences SPEC F4 names.

    A reply that is neither a refusal nor a well-formed check is `unclear` — not an
    error, and never an empty result. The model failing to follow the contract and
    the user writing something unreadable land the same way on purpose: in both
    cases nobody knows what rule was wanted, and that is the honest thing to say.
    """
    reason = reply.get("cannot")
    check = reply.get("check")
    if reason is not None or not isinstance(check, Mapping) or not _well_formed(check):
        code = reason if reason in EXPLANATION else UNCLEAR
        return _refused(request, str(code), reply.get("why"))
    try:
        spec = validator.validate(
            str(check["type"]), dict(check.get("kwargs") or {}), table, columns
        )
    except validator.RuleRejected as exc:
        return Refused(request=request, reason=INVALID, message=status.refusal(str(exc)))
    return Draft(
        request=request,
        table=table,
        spec=spec,
        english=catalog.english(spec["type"], spec["kwargs"]),
    )


def prompt(request: str, table: str, columns: Sequence[tuple[str, str]]) -> str:
    """Everything the model is shown. Three parts: the schema, the menu, the contract.

    The menu is rendered from `catalog.ENTRIES`, so the set of types the model may
    choose from is the set the validator will accept — one list, never two. Nothing
    here declares how long the catalog is.
    """
    schema = "\n".join(f"  {name} ({sql_type})" for name, sql_type in columns)
    menu = "\n".join(
        f"  {e['type']}(" + ", ".join(_parameters(e)) + f") — {e['english']}"
        for e in catalog.ENTRIES
    )
    return f"""Table: {table}

Its columns:
{schema}

The only check types you may use, with their parameters (required first, \
[optional] in brackets) and the sentence each one turns into:
{menu}

{_CONTRACT}
The request, in the user's own words:
{request}
"""


def _parameters(entry: Mapping[str, Any]) -> list[str]:
    return list(entry["required"]) + [f"[{name}]" for name in entry["optional"]]


def _well_formed(check: Mapping[str, Any]) -> bool:
    """Does the reply carry something the validator can even be asked about?

    Deliberately shallow: a type that is a string and kwargs that are a mapping. Any
    judgement past that belongs to the validator, which refuses with a reason naming
    the fault — a shape check that started rejecting types or parameters here would
    be INV-2's second opinion, drifting from the one that counts.
    """
    return isinstance(check.get("type"), str) and isinstance(check.get("kwargs", {}), Mapping)


def _refused(request: str, code: str, why: Any) -> Refused:
    """Our sentence, then the model's, then nothing saved."""
    detail = why.strip()[:DETAIL_LIMIT] if isinstance(why, str) and why.strip() else None
    return Refused(
        request=request,
        reason=code,
        message=status.refusal(EXPLANATION[code]),
        detail=detail,
    )
