"""F12 · the translation desk, checked where it is cheapest: with no database at all.

The three checks this bead's DoD names as unit work are all here, and each one is a
refusal that has to happen BEFORE a write rather than instead of one. That ordering is
the whole subject: the rule store is append-only and the database refuses UPDATE
outright, so a bulk accept that discovers its problem halfway through has already left
rows nobody can take back out.

What is deliberately NOT here: whether the screen renders any of it. That is
`tests/e2e/test_ui_behaviour.py`, driving the real app in a real browser — a DOM
assertion is the only honest place for "the checkbox is absent", and this file has no
opinion about markup.
"""

from __future__ import annotations

import ast
from typing import Any

import pytest

from app.dq import status
from app.rules import catalog
from conftest import REPO

TABLE = "orders"

# A spec that would pass the validator, so nothing below is refused for the wrong reason.
GOOD: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0},
}

# The reason a rejection has to carry, in the words somebody would actually type.
REASON = "cancelled orders use a fourth status that is not in this sample"


def _store() -> Any:
    """The store, imported inside the check — psycopg2 and a DSN are not owed to `make check`."""
    from app.rules import store  # noqa: PLC0415

    return store


def test_bulk_accept_refuses_a_selection_above_the_cap() -> None:
    """Past the cap is refused, and refused BEFORE the first revision is written.

    The cap is not a rounding of the screen's layout: it exists so that every selected
    evidence line is on screen at the moment of the click (UX_HARNESS_FINDINGS §4), and
    LT-2b is what makes that expensive — every rule the model proposed was true of the
    rows it saw and wrong about the business. A control that hides what it is accepting
    is how forty of those enter at once.

    ORDERING IS THE ASSERTION, and it is what makes this checkable with no database:
    `judge_batch` refuses on the count alone, so nothing it would need a connection for
    is ever reached. A version that validated the cap after `propose()` would raise here
    too — with `Unavailable` from the store, which is what the second assertion pins.
    Under the cap the same call gets past the count and fails at the CONNECTION, which is
    the proof that the refusal above was the cap and not the network.
    """
    store = _store()
    assert store.BULK_CAP >= 2, "a cap of one is not a bulk control"

    with pytest.raises(ValueError) as refused:
        store.judge_batch(TABLE, [], [f"rule-{n}" for n in range(store.BULK_CAP + 1)], "accepted")
    complaint = str(refused.value)
    assert str(store.BULK_CAP) in complaint and "cap" in complaint, (
        f"refusing an oversized selection must name the cap, since the caller's next move is "
        f"to select fewer: {complaint}"
    )
    assert "Unavailable" not in type(refused.value).__name__, (
        "the refusal came from the store's connection, which means the cap was checked after "
        "something had already been written. Revisions are append-only; a batch that fails "
        "halfway leaves rules nobody can remove."
    )

    # And an empty selection is refused rather than being a quiet no-op: the screen
    # disables the control at zero, so an empty batch arriving here got past it.
    with pytest.raises(ValueError):
        store.judge_batch(TABLE, [], [], "accepted")


def test_reject_without_a_reason_is_refused() -> None:
    """A rejection with no reason is refused at the door, not after revision 1 exists.

    F12 requires a rejection to capture WHY, and `Revision.__post_init__` has always
    refused one that does not. What this check is about is the SEQUENCE the bulk door
    introduced: an unsaved proposal is written by `propose()` and judged by
    `set_status()`, so a reasonless rejection discovered at the second step would leave
    a machine-authored rule sitting in an append-only table, proposed by nobody and
    judged by nobody.

    `judgeable()` is the one copy of the rule, called by both — asserted here by driving
    it directly and by driving the batch door that must consult it first.
    """
    store = _store()

    for empty in (None, "", "   ", "\n"):
        with pytest.raises(ValueError) as refused:
            store.judgeable(store.REJECTED, empty)
        assert "reason" in str(refused.value)
    store.judgeable(store.REJECTED, REASON)  # and a real one passes

    # The batch door, with one unsaved proposal and no reason. It must refuse on the
    # judgment rather than reach `propose()` — which has no database here and would
    # raise something else entirely.
    with pytest.raises(ValueError) as batch:
        store.judge_batch(TABLE, [GOOD], [], store.REJECTED, None)
    assert "reason" in str(batch.value), (
        f"the batch door refused for {batch.value!r} rather than for the missing reason, so it "
        "got past `judgeable()` and into the store before noticing"
    )

    # An unknown state is refused by the same function, so a fifth one cannot arrive
    # through the bulk door either.
    with pytest.raises(ValueError):
        store.judgeable("approved", None)


def test_engineer_editing_the_configuration_revalidates_before_save() -> None:
    """The engineer's edited configuration walks the same door a brand-new rule does.

    Two halves, and neither of them needs a database.

    THE PURE HALF: an edited configuration with an inverted bound is refused by layer 1
    of INV-2, which is the layer LT-2a proved is the one that matters — Great
    Expectations accepted 10 of 25 deliberately invalid probes while reporting success,
    inverted bounds among them. So this is a rule the framework alone would have taken.

    THE STRUCTURAL HALF: the only write the revision route can reach is `store.amend()`,
    and `tests/test_rule_store.py::test_the_store_has_no_writer_that_skips_the_validator`
    already asserts that `amend` calls `validate`. Read together they are the claim in the
    bead's title — there is no path from the textarea to the table that skips the
    validator — and it is a property of the import graph rather than of anybody's care.
    """
    from app.rules import validator  # noqa: PLC0415 — pure, but it belongs with its check

    with pytest.raises(validator.RuleRejected) as refused:
        validator.sanity(
            "expect_column_values_to_be_between",
            {"column": "order_total", "min_value": 10, "max_value": 0},
            TABLE,
            {"order_total"},
        )
    assert "min_value=10" in str(refused.value) and "max_value=0" in str(refused.value), (
        f"the refusal does not name the offending values (INV-4): {refused.value}. The engineer "
        "is looking at the textarea they just typed; a refusal that does not point into it is a "
        "refusal they cannot act on."
    )

    source = (REPO / "app/rules/desk.py").read_text()
    revise = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "revise"
    )
    called = {
        node.func.attr
        for node in ast.walk(revise)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "amend" in called, (
        f"the revision door reaches {sorted(called)} and not `store.amend`. Every other way to "
        "write a spec either skips the validator or is not append-only."
    )
    assert not called & {"propose", "set_status", "judge_batch", "_append"}, (
        f"the revision door also reaches {sorted(called)}. Editing a rule appends ONE revision "
        "in `needs_review`; anything that also judged it would be an edit accepting itself."
    )


def test_the_desk_writes_none_of_its_own_copy() -> None:
    """Every sentence F12's screen renders comes out of the single writer, by identity.

    `tests/test_inv5_sampling_disclosure.py` fails the gate on a second copy under
    `web/app`, which catches the sentence being retyped in TSX. This catches the other
    direction — the payload quietly composing its own — by comparing what `copy()`
    returns against `app/dq/status.py`'s own constants, object by object.

    `bulk_action` is checked as a TEMPLATE rather than a sentence, which is the one place
    a component is allowed to build a string: its number changes on every click of a
    checkbox. The slot is asserted to be there, because a template that lost it renders
    the literal `{n}` to a user.
    """
    from app.rules import desk  # noqa: PLC0415

    written = desk.copy()
    assert written["compiled_token"] == status.COMPILED_TOKEN
    assert written["compiled_caveat"] == status.COMPILED_CAVEAT
    assert written["unsaved"] == status.UNSAVED_NOTE
    assert written["bulk_excluded"] == status.BULK_EXCLUDED
    assert written["reason_label"] == status.REASON_LABEL
    assert written["amended"] == status.AMENDED_NOTE

    assert "{n}" in written["bulk_action"], (
        f"the bulk label has no slot for its count: {written['bulk_action']!r}. The component "
        "substitutes a number into it, so a template without one renders the braces."
    )
    assert str(_store().BULK_CAP) in written["bulk_note"], (
        "the note explaining the cap does not contain the cap. It is composed by "
        "status.bulk_note() from the store's own number precisely so it cannot drift."
    )

    assert not any(
        status.COMPILED_TOKEN in str(value)
        for key, value in written.items()
        if key != "compiled_token"
    ), "one sentence is spliced into another; each of these has exactly one home"


def test_the_desk_asks_the_generator_for_exactly_the_cap_it_prints() -> None:
    """The number in the copy and the number of proposals are one constant (bead dq-5da).

    THE COPY IS AN ARGUMENT, NOT A PREFERENCE. "Up to N at a time, so every evidence line
    is on screen when you press it" is the reason a bulk control is safe at all; eight
    fit on screen with their evidence and ten do not. The generator used to hold its own
    constant of ten, and the live deployment answered `POST /proposals/payments` with ten
    proposals under a control that said eight — the sentence stopped being true exactly
    where it mattered.

    ASSERTED ON THE CALL SITE rather than on a returned count, because that is where the
    drift would come back: `desk.proposals()` needs a database to run, and a check that
    counted its output would go green on a literal `8` typed in beside `store.BULK_CAP`.
    The argument must be the store's attribute, so there is one number and no second
    place to change it. `tests/test_f3_model_call.py` holds the other half — the slice
    and the prompt honour whatever it is.
    """
    call = next(
        (
            node
            for node in ast.walk(ast.parse((REPO / "app/rules/desk.py").read_text()))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "for_table"
        ),
        None,
    )
    assert call is not None, (
        "app/rules/desk.py no longer calls suggest.for_table(). If the proposer moved, this "
        "check has to move with it — the cap reaching the generator is the assertion."
    )
    passed = [ast.unparse(argument) for argument in call.args[1:]] + [
        ast.unparse(keyword.value) for keyword in call.keywords
    ]
    assert "store.BULK_CAP" in passed, (
        f"the desk asks the generator for {passed}, not for store.BULK_CAP. The screen prints "
        "that number under the bulk control, so any other value here is a promise the "
        "proposal list does not keep."
    )


def test_the_catalog_rail_offers_the_whole_menu_and_marks_what_is_used() -> None:
    """B6 · the rail is the catalog file, and nothing here declares how long it is.

    A design review already caught a mockup shipping fifteen entries that did not map
    1:1 onto real expectation types, so the count is read from `catalog.ENTRIES` on both
    sides of the wire and compared to nothing. What this adds is the `in_use` mark, which
    is the rail's only claim: the reader is being told which of the menu this table has
    already spent, and a mark on a type nobody used would be a coverage claim.
    """
    from app.rules import desk  # noqa: PLC0415

    store = _store()
    used = store.Revision(rule_id="r1", revision=1, table=TABLE, spec=GOOD, status=store.ACCEPTED)
    rail = desk.catalog_rail([used])

    assert len(rail) == len(catalog.ENTRIES) > 0
    assert all("type" not in entry for entry in rail), (
        "the rail handed the framework's identifiers to a caller that did not ask for the "
        "configuration. The menu is bilingual for the same reason the panes are (Rev 0.4)."
    )
    rail = desk.catalog_rail([used], configuration=True)
    assert [entry["type"] for entry in rail] == list(catalog.TYPES), (
        "the rail reordered or dropped the menu. It is the catalog file, rendered — the order "
        "is the file's, so a reader comparing the two sees one list."
    )
    marked = [entry["type"] for entry in rail if entry["in_use"]]
    assert marked == [GOOD["type"]], (
        f"the rail marks {marked} as in use on a table with one rule of type {GOOD['type']!r}. "
        "A mark on an unused type is a claim about coverage this table does not have."
    )
    assert desk.catalog_rail([]) and not any(e["in_use"] for e in desk.catalog_rail([])), (
        "a table with no rules still gets the whole menu — that is what the rail is FOR on an "
        "empty table — and nothing on it is marked as used"
    )
