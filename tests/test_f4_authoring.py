"""F4 · English becomes a validated unsaved rule, or an honest refusal that writes nothing.

SPEC F4's acceptance is three sentences, and all three are recognisable below by name:
"order total can never be negative" -> a rule on orders.order_total with a lower bound of
zero, unsaved; "shipped_date must be after order_date" -> refused, naming the limitation;
ambiguous or unparseable -> an explanation, never a guess.

HOW THE LAYERS SPLIT. `app/rules/authoring.py` is two functions on purpose:
`interpret()` is pure and takes a reply, `author()` is the same thing with a billed call
in front. So every reply SHAPE runs through the real validator here for free; the `ge`
layer runs those shapes through the real framework and the real store; and exactly one
check spends money proving the real model produces those shapes from the three real
English sentences — `set -a; . ./.env; set +a; python3 -m pytest -m live`.

THE ASSERTION THAT MATTERS MOST IS THE ONE ABOUT WRITING, because a refusal that stored
an `unsupported` rule would satisfy every other check here and still report coverage the
table does not have. It is asserted from both ends — structurally, as an import graph
with no store in it, so no refusal CAN write, including the ones nobody probed; and
dynamically, as a row count through the store's own front door.

NO REFUSAL COPY IS TYPED IN THIS FILE. Every sentence is read out of the single writer,
`app/dq/status.py`; what IS written down is the handful of words each sentence must
contain, since "the message names the limitation" is a judgement no constant makes
about itself.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
import re
from typing import Any

import pytest

from app.dq import status
from app.rules import authoring, catalog, validator
from conftest import REPO

MODULE = pathlib.Path("app/rules/authoring.py")

# SPEC F4's own three sentences, so these checks read as the acceptance does.
NEGATIVE_TOTAL = "order total can never be negative"
SHIPPED_AFTER_ORDER = "shipped_date must be after order_date"
GIBBERISH = "make sure the numbers are, you know, sensible"

# A stand-in live schema, so a refusal is checkable with no database; ge reads the real one.
ORDERS = frozenset(
    {"order_id", "customer_id", "order_total", "status", "order_date", "shipped_date", "email"}
)


def _check(etype: str, **kwargs: Any) -> dict[str, Any]:
    """A model reply carrying one check, in the contract's own shape."""
    return {"check": {"type": etype, "kwargs": kwargs}}


# F4's first sentence. Only the SHAPE is canned; `test_live_...` asserts the real reply.
A_RULE = _check("expect_column_values_to_be_between", column="order_total", min_value=0)

A_MULTI_COLUMN_REFUSAL = {
    "cannot": "multi_column",
    "why": "shipped_date and order_date are two different columns.",
}

# Every way a reply can fail to be a check, including the model ignoring the contract
# outright. All are `unclear`: nobody knows what rule was wanted.
AMBIGUOUS_REPLIES: list[tuple[dict[str, Any], str]] = [
    ({"cannot": "unclear", "why": "I cannot tell which column 'the numbers' means."}, "declared"),
    ({}, "empty object"),
    ({"check": "expect_column_values_to_be_between"}, "check is not an object"),
    ({"check": {"kwargs": {"column": "order_total"}}}, "check names no type"),
    ({"check": {"type": "expect_column_values_to_be_unique", "kwargs": []}}, "kwargs not a map"),
    ({"cannot": "i_would_rather_not"}, "a refusal code we never defined"),
]

# Replies the VALIDATOR refuses rather than the model declining. Both are what a model
# ignoring the menu plausibly produces, and both must come back as a value.
REFUSED_BY_THE_VALIDATOR: list[tuple[dict[str, Any], str, str]] = [
    (
        _check(
            "expect_column_pair_values_a_to_be_greater_than_b",
            column_A="shipped_date",
            column_B="order_date",
        ),
        validator.NOT_IN_CATALOG,
        "a real multi-column type, ignoring the menu",
    ),
    (
        _check("expect_column_values_to_not_be_null", column="shipping_date"),
        "shipping_date",
        "a column that does not exist",
    ),
]

# Everything `app/rules/authoring.py` may import, dotted to the leaf. The point is what is
# missing: `app.rules.store` is the product's only writer and is absent, so a refusal has
# nowhere to leave a row. `app.rules.schema` is not a hole — it holds the SELECT-only
# analysis role, which PostgreSQL refuses a write on (tests/test_db_privilege_split.py).
PERMITTED_IMPORTS = {
    "__future__.annotations",
    "collections.abc.Collection",
    "collections.abc.Mapping",
    "collections.abc.Sequence",
    "dataclasses.dataclass",
    "typing.Any",
    "app.model",
    "app.dq.status",
    "app.rules.catalog",
    "app.rules.schema",
    "app.rules.validator",
}

# An import allowlist cannot see a builtin: `__import__` needs no import statement.
CANNOT_BE_CALLED = {"__import__", "eval", "exec", "open", "connect", "execute", "_append"}

A_TYPE_NAME = re.compile(r"\bexpect_[a-z_]+[a-zA-Z_]*\b")


# --- The first sentence: a rule, shown for confirmation -----------------------


def test_the_confirmation_sentence_reads_as_the_rule_the_author_stated() -> None:
    """A draft is confirmed by reading it, so the sentence IS the deliverable, and
    "Every order_total is between 0 and None" is what an unformatted template produces
    for F4's headline case."""
    between = "expect_column_values_to_be_between"
    rendered = [
        catalog.english(between, {"column": "order_total", "min_value": 0.0}),
        catalog.english(between, {"column": "order_total", "max_value": 500.0}),
        catalog.english(between, {"column": "order_total", "min_value": 0.0, "max_value": 500.0}),
        catalog.english("expect_column_values_to_be_in_set", {"column": "s", "value_set": [1, 2]}),
        catalog.english("expect_column_values_to_not_be_null", {"column": "e", "mostly": 0.98}),
    ]
    assert rendered == [
        "Every order_total is at least 0",
        "Every order_total is at most 500",
        "Every order_total is between 0 and 500",
        "Every s is one of 1, 2",
        "Every e has a value, in at least 98% of rows",
    ], rendered


def test_every_two_bounded_template_can_be_half_bounded() -> None:
    """`catalog.english` swaps one phrase; a template without it renders "and None".
    Read off the catalog, so a sixteenth bounded entry fails this check rather than
    reaching a user as a broken sentence."""
    missing = [
        e["type"]
        for e in catalog.ENTRIES
        if {"min_value", "max_value"} <= set(e["required"]) | set(e["optional"])
        and catalog.BOUNDED not in e["english"]
    ]
    assert not missing, (
        f"{missing} take both bounds but do not contain {catalog.BOUNDED!r}, so a rule with one "
        "bound renders as '... and None'. Phrase the template with it, or teach catalog._bounds."
    )


# --- The second sentence: refused, and the refusal names the limitation -------


def test_multi_column_request_is_refused_with_the_named_limitation() -> None:
    """SPEC F4's second case. The sentence is read out of the single writer, never typed
    here; the three fragments are the judgement a constant cannot make about itself. The
    message must name what the product cannot do AND what it can, or the reader learns
    only that it said no."""
    refused = authoring.interpret(SHIPPED_AFTER_ORDER, "orders", A_MULTI_COLUMN_REFUSAL, ORDERS)
    assert isinstance(refused, authoring.Refused), f"expected a refusal, got {refused}"
    assert refused.reason == authoring.MULTI_COLUMN
    assert refused.message == status.refusal(status.MULTI_COLUMN_LIMIT)
    for fragment in ("two columns", "single-column", "table-level"):
        assert fragment in refused.message, (
            f"the refusal never says {fragment!r}: {refused.message!r}. A capability gap the "
            "reader cannot see the shape of is indistinguishable from a bug."
        )
    assert status.NOTHING_SAVED in refused.message
    assert (
        refused.detail == A_MULTI_COLUMN_REFUSAL["why"]
    ), "the model's own sentence is dropped; it is the part that names the two columns"


@pytest.mark.parametrize(
    "reply,expected,why", [pytest.param(r, e, w, id=w) for r, e, w in REFUSED_BY_THE_VALIDATOR]
)
def test_a_rule_the_validator_refuses_comes_back_as_a_refusal_naming_the_fault(
    reply: dict[str, Any], expected: str, why: str
) -> None:
    """The belt to the model's braces — why classification is not safety-critical.

    A model that ignores the menu and answers the multi-column request with a real pair
    expectation is refused anyway: by INV-2, at authoring time, carrying the validator's
    own reason. And it comes back as a VALUE, never an exception — a `RuleRejected`
    escaping here would reach the user as a 500 instead of the promised explanation.
    """
    refused = authoring.interpret(SHIPPED_AFTER_ORDER, "orders", reply, ORDERS)
    assert isinstance(refused, authoring.Refused), f"{why}: expected a refusal, got {refused}"
    assert refused.reason == authoring.INVALID
    assert expected in refused.message, f"{why}: refusal never names it — {refused.message!r}"
    assert status.NOTHING_SAVED in refused.message


# --- The third sentence: an explanation, never a guess ------------------------


@pytest.mark.parametrize("reply,why", [pytest.param(r, w, id=w) for r, w in AMBIGUOUS_REPLIES])
def test_ambiguous_input_returns_an_explanation_not_a_guess(
    reply: dict[str, Any], why: str
) -> None:
    """Six shapes, one outcome. The last two catch a bug rather than a designed path: a
    reply following no contract, and a refusal code nobody defined. Inventing a rule from
    either is the most damaging thing this module could do — the result LOOKS asked for."""
    refused = authoring.interpret(GIBBERISH, "orders", reply, ORDERS)
    assert isinstance(refused, authoring.Refused), f"{why}: expected a refusal, got {refused}"
    assert refused.reason == authoring.UNCLEAR
    assert refused.message == status.refusal(status.UNCLEAR_REQUEST)
    assert status.MULTI_COLUMN_LIMIT not in refused.message, (
        f"{why}: an unreadable request was explained as a multi-column limitation. Naming a "
        "limitation that may not apply is a guess wearing a refusal's clothes."
    )
    assert refused.request == GIBBERISH, "the request is returned to its author as they wrote it"


# --- The assertion that matters most -----------------------------------------


def test_refusal_path_performs_zero_writes() -> None:
    """No refusal CAN write, including the ones nobody thought to probe.

    Same mechanism as `test_inv2_authoring_rejection.py::test_a_rejected_spec_writes_nothing`:
    a row count over a few probes says those probes wrote nothing, an import graph with no
    store in it says nothing here ever will. Its dynamic companion counts the store's own
    rows below. The DSN assertion is the third leg — the write role reaches the database
    through one variable, and this module never names it.
    """
    source = (REPO / MODULE).read_text()
    tree = ast.parse(source)
    imported = {
        f"{node.module}.{alias.name}" if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert imported == PERMITTED_IMPORTS, (
        f"{MODULE} imports {sorted(imported)}; this check knows about "
        f"{sorted(PERMITTED_IMPORTS)}. A refusal writes nothing because there is nothing here "
        "to write with — keep the store out, and add a new name deliberately."
    )
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not (reached := sorted(called & CANNOT_BE_CALLED)), (
        f"{MODULE} calls {reached}. The import allowlist cannot see a builtin, so this is the "
        "other half: no dynamic import, no file, no cursor, no INSERT."
    )
    assert "SUPABASE_DB_URL_SYSTEM" not in source, (
        f"{MODULE} names the write role's DSN. Authoring reads a schema and returns a value; "
        "the credential that can write belongs to app/rules/store.py alone."
    )


# --- What the model is shown --------------------------------------------------


def test_the_prompt_offers_the_catalog_the_live_schema_and_nothing_else() -> None:
    """Everything the model is allowed to choose from, and nothing it cannot spell.

    The menu is the catalog in both directions, because they fail differently: a missing
    type is a capability never offered, an extra one is a proposal the user watches be
    refused. The columns come from the live schema (SPEC §3.1 — schema and a bounded
    sample, never table contents; F4 needs no rows at all). The refusal codes are read off
    `EXPLANATION`, so a third cannot be added without appearing in the prompt offering it.
    And the last assertion is LT-2b's: the model proposed `order_total BETWEEN 0 AND
    89,400`, an upper bound read off the observed maximum, so the instructions say not to.
    """
    text = authoring.prompt(NEGATIVE_TOTAL, "orders", [(c, "text") for c in sorted(ORDERS)])
    named, offered = set(A_TYPE_NAME.findall(text)), set(catalog.TYPES)
    assert named == offered, (
        f"the menu and the catalog disagree — only in the menu: {sorted(named - offered)}, "
        f"only in the catalog: {sorted(offered - named)}"
    )
    assert NEGATIVE_TOTAL in text, "the user's own words never reach the model"
    assert not (
        unshown := sorted(c for c in ORDERS if c not in text)
    ), f"columns the model was never shown, and so cannot spell: {unshown}"
    for code in authoring.EXPLANATION:
        assert f'"{code}"' in text, f"{code!r} is a refusal we explain but never offer: {text}"
    assert "lower bound of 0 and no upper bound" in text, (
        "the prompt no longer tells the model to state only the bound the request states — "
        f"the one instruction standing between F4 and LT-2b's overfitted bound:\n{text}"
    )


# --- The ge layer: real framework, real schema, real store --------------------


def _real() -> Any:
    """The store module and the live column set. Imported inside the ge layer only."""
    from app.rules import schema, store  # noqa: PLC0415

    return store, schema.columns("orders")


@pytest.mark.ge
def test_negative_total_phrase_yields_lower_bound_zero_and_is_unsaved() -> None:
    """SPEC F4's first case, end to end bar the model.

    A `ge` check because a VALID rule cannot be validated without the framework: layer 1
    of INV-2 refuses nonsense for free, a good rule has to be constructed. The two
    assertions carrying F4 are the ABSENT upper bound — LT-2b's failure, guarded from the
    other side by the prompt — and the row count, because a draft is not a saved rule.
    """
    store, columns = _real()
    before = len(store.revisions())
    drafted = authoring.interpret(NEGATIVE_TOTAL, "orders", A_RULE, columns)
    assert isinstance(drafted, authoring.Draft), f"expected a draft, got {drafted}"
    assert drafted.spec["kwargs"]["column"] == "order_total"
    assert drafted.spec["kwargs"]["min_value"] == 0
    assert drafted.spec["kwargs"].get("max_value") is None, (
        f"an upper bound nobody asked for: {drafted.spec['kwargs']}. LT-2b's proposal read one "
        "off the observed maximum and was wrong about the business, not about the data."
    )
    assert drafted.english == "Every order_total is at least 0", drafted.english
    assert len(store.revisions()) == before, "a draft shown for confirmation reached the store"


@pytest.mark.ge
def test_authoring_returns_an_unsaved_draft_and_persists_nothing_until_accept() -> None:
    """The network fact behind every "nothing is stored" claim in this file.

    Counted through the store's own front door across the draft AND every refusal, then
    the accept — the one step that must change the count. Without it the check is
    satisfied by a store nobody can write to at all. There is no HTTP endpoint yet (B17
    and B20 own the routes); `interpret()` is the entry point, and a route inherits this
    boundary unchanged, because `store.propose()` is reachable only from an accept.
    """
    store, columns = _real()
    before = len(store.revisions())
    drafted = authoring.interpret(NEGATIVE_TOTAL, "orders", A_RULE, columns)
    assert isinstance(drafted, authoring.Draft)
    for reply, _ in [*AMBIGUOUS_REPLIES, (A_MULTI_COLUMN_REFUSAL, "multi-column")]:
        assert isinstance(
            authoring.interpret(GIBBERISH, "orders", reply, columns), authoring.Refused
        )
    for reply, _, why in REFUSED_BY_THE_VALIDATOR:
        assert isinstance(
            authoring.interpret(SHIPPED_AFTER_ORDER, "orders", reply, columns), authoring.Refused
        ), why
    assert len(store.revisions()) == before, (
        f"authoring wrote {len(store.revisions()) - before} row(s) across one draft and nine "
        "refusals. Every one of them should have written nothing."
    )
    written = store.propose("orders", drafted.spec["type"], drafted.spec["kwargs"])
    assert len(store.revisions()) == before + 1, "accepting a draft wrote no row"
    assert written.status == store.PROPOSED
    assert written.spec == drafted.spec, (
        f"the stored spec is not the drafted one: {written.spec} vs {drafted.spec}. The user "
        "confirmed a sentence rendered from the draft; a different rule reached the store."
    )


# --- The one check that spends money ------------------------------------------


@pytest.mark.live
def test_live_english_becomes_a_rule_a_named_refusal_and_an_explanation() -> None:
    """Three real calls, one per sentence in SPEC F4's acceptance. ~$0.12.

    The two refusals go through `author()` itself — live schema read, billed call and
    interpretation — because a refusal needs no framework, so the whole entry point is
    exercised in an interpreter that has none. The rule is asserted as a REPLY for the
    same reason: validating it needs the framework, and that half is already proven
    against the real one above. Classification is what no canned reply can prove.
    """
    from app import model  # noqa: PLC0415
    from app.rules import schema  # noqa: PLC0415

    text = authoring.prompt(NEGATIVE_TOTAL, "orders", schema.column_types("orders"))
    rule = asyncio.run(model.ask_json(text, authoring.SYSTEM)).data["check"]
    assert rule["type"] in catalog.TYPES, f"a type outside the menu: {rule}"
    assert rule["kwargs"]["column"] == "order_total", f"the wrong column: {rule}"
    assert rule["kwargs"].get("min_value") == 0, f"no lower bound of zero: {rule}"
    assert (
        rule["kwargs"].get("max_value") is None
    ), f"an upper bound the request never stated: {rule}. This is LT-2b's failure exactly."
    for request, code in (
        (SHIPPED_AFTER_ORDER, authoring.MULTI_COLUMN),
        (GIBBERISH, authoring.UNCLEAR),
    ):
        refused = asyncio.run(authoring.author(request, "orders"))
        assert isinstance(refused, authoring.Refused), f"{request!r} produced {refused}"
        assert refused.reason == code, f"{request!r} was classified {refused.reason}: {refused}"
        assert status.NOTHING_SAVED in refused.message
