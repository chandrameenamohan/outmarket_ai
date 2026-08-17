"""B12 · F3 — proposals arrive with their evidence, unsaved, and only from the catalog.

This file checks the proposals themselves. The call that produces them — the payload the
model is given and the replies it is allowed to hand back, including the one billed check
that runs the whole path for real — is `tests/test_f3_model_call.py`. Two files because
they are two jobs; the recorded profile below has one home and the other file imports it.

Everything here runs offline against a RECORDED profile and a STUBBED reply, which is
deliberate rather than thrifty: `app/rules/suggest.py` is a pure function of a profile and
a parsed dict with one billed line in the middle of it, so the two claims F3 actually
makes — every proposal names a catalog type, and every proposal carries the numbers it was
inferred from — are checkable without a database, without the framework, and without
spending $0.04 to find out.

The recorded profile is the shape `app/dq/profile.py` returns for the seeded `orders`
table, with its numbers from `seed/MANIFEST.md`. It is built through the real
`TableProfile`, so it cannot be a shape the profiler could not have produced.

The out-of-catalog probes use REAL Great Expectations type names this product deliberately
does not offer (multi-column rules are v2, SPEC F4). A made-up string would prove less:
the failure mode is a model reaching for a type the framework really has.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any

import pytest

from app.dq import profile
from app.rules import catalog, store, suggest
from app.rules.validator import RuleRejected
from conftest import REPO

TABLE = "orders"

# Real GE 1.x types, outside our fifteen on purpose — see the module docstring.
OUTSIDE_THE_CATALOG = (
    "expect_column_pair_values_a_to_be_greater_than_b",
    "expect_compound_columns_to_be_unique",
    "expect_multicolumn_sum_to_equal",
)

# What `app/rules/suggest.py` may not reach for. The point is the absence: no store, so a
# proposal has nowhere to be saved; no GE door, so it has no way to be run.
FORBIDDEN_IMPORTS = ("app.rules.store", "app.dq.ge_runtime", "psycopg2")

SUGGEST = pathlib.Path("app/rules/suggest.py")


def orders_profile() -> profile.TableProfile:
    """The seeded table's profile, recorded. A real `TableProfile`, so the shape is real."""
    total = 500_000
    return profile.TableProfile(
        table=TABLE,
        total_rows=total,
        columns=(
            profile.ColumnProfile(
                name="order_id",
                data_type="integer",
                total_rows=total,
                non_null=total,
                distinct=total,
                minimum="1",
                maximum="500000",
                values=None,
            ),
            profile.ColumnProfile(
                name="order_total",
                data_type="numeric",
                total_rows=total,
                non_null=total,
                distinct=45_102,
                minimum="-389.59",
                maximum="89400.00",
                values=None,
            ),
            profile.ColumnProfile(
                name="status",
                data_type="text",
                total_rows=total,
                non_null=total,
                distinct=4,
                minimum="cancelled",
                maximum="shippd",
                values=("cancelled", "paid", "shipped", "shippd"),
            ),
            profile.ColumnProfile(
                name="shipped_at",
                data_type="timestamp without time zone",
                total_rows=total,
                non_null=310_412,
                distinct=298_003,
                minimum="2024-01-01 00:00:00",
                maximum="2025-12-31 23:59:00",
                values=None,
            ),
        ),
        sample=tuple(
            {"order_id": n, "order_total": "10.00", "status": "shipped", "shipped_at": None}
            for n in range(1, profile.SAMPLE_ROWS + 1)
        ),
    )


# LT-2b's own reply, near enough: statistically true, business-naive, and the second of
# them overfits the observed maximum exactly as the real one did. Every check that needs a
# reply uses this one — a stub proposing only good rules would never exercise what F3 is
# for, which is making a rule like that judgeable rather than filtering it out.
REPLY: dict[str, list[dict[str, Any]]] = {
    "rules": [
        {"type": "expect_column_values_to_not_be_null", "kwargs": {"column": "order_total"}},
        {
            "type": "expect_column_values_to_be_between",
            "kwargs": {"column": "order_total", "min_value": 0, "max_value": 89400},
        },
        {
            "type": "expect_column_values_to_be_in_set",
            "kwargs": {"column": "status", "value_set": ["cancelled", "paid", "shipped"]},
        },
        {"type": "expect_table_row_count_to_be_between", "kwargs": {"min_value": 1}},
    ]
}


def proposals() -> tuple[suggest.Proposal, ...]:
    return suggest.proposals(orders_profile(), REPLY)


def unsubstituted(proposal: suggest.Proposal) -> list[str]:
    """Catalog placeholders that survived into the sentence — the shape of a broken render.

    A bare `{` is NOT the test, and the `live` check is what proved it: the real model
    proposed `^ORD-[0-9]{7}$` for `order_reference`, whose sentence contains a brace and is
    perfectly correct. Only a placeholder this entry actually declares counts.
    """
    entry = next(e for e in catalog.ENTRIES if e["type"] == proposal.type)
    named = (*entry["required"], *entry["optional"])
    return [f"{{{k}}}" for k in named if f"{{{k}}}" in proposal.statement]


# --- only from the catalog ----------------------------------------------------


def test_every_proposal_type_is_in_the_catalog() -> None:
    """The constraint SPEC F3 states, on the way OUT of the generator."""
    made = proposals()
    assert len(made) == len(REPLY["rules"]), f"a rule was dropped on the way out: {made}"
    outside = [p.type for p in made if p.type not in catalog.TYPES]
    assert not outside, (
        f"{outside} are not catalog types. The catalog is the whole menu the model is given, "
        "and a type outside it has no English form, no sanity rules, and has never run here."
    )
    known = {column.name for column in orders_profile().columns}
    assert all(p.column is None or p.column in known for p in made), (
        f"a proposal names a column the profile does not have: {[p.column for p in made]}. The "
        "profile's column list came from the live schema, which is what SPEC §3.1 requires an "
        "identifier derived from model output to be checked against."
    )


@pytest.mark.parametrize("etype", OUTSIDE_THE_CATALOG)
def test_a_proposal_outside_the_catalog_is_refused_rather_than_returned(etype: str) -> None:
    """A defect, not a feature request — and loud, not dropped.

    Both doors are checked: the batch path a model reply arrives through, and direct
    construction, because a `Proposal` is a value other code will build and no caller
    should be able to make one the catalog does not describe.
    """
    reply = {"rules": [{"type": etype, "kwargs": {"column_A": "a", "column_B": "b"}}]}
    with pytest.raises(RuleRejected) as raised:
        suggest.proposals(orders_profile(), reply)
    assert etype in str(raised.value), "the refusal must name the type that was refused"

    with pytest.raises(RuleRejected) as direct:
        suggest.Proposal(type=etype, kwargs={}, statement="anything", evidence="500,000 rows")
    assert etype in str(direct.value), str(direct.value)


def test_one_bad_rule_refuses_the_whole_batch_rather_than_vanishing() -> None:
    """Dropping the offender silently would hide the only signal there is.

    A reply whose types have drifted outside the menu means the prompt has stopped
    constraining the model — a defect in this module, not in the one rule. Nine good
    proposals arriving as if nothing had happened is how that goes unnoticed for weeks.
    """
    good = proposals()
    reply = {"rules": [*REPLY["rules"], {"type": OUTSIDE_THE_CATALOG[0], "kwargs": {}}]}
    with pytest.raises(RuleRejected) as raised:
        suggest.proposals(orders_profile(), reply)
    assert OUTSIDE_THE_CATALOG[0] in str(raised.value), str(raised.value)
    assert len(good) == len(REPLY["rules"]), (
        "the same reply without the bad rule must produce every proposal in it — otherwise "
        "the check above would pass for a generator that refuses everything."
    )


# --- unsaved, and unexecuted --------------------------------------------------


def test_proposal_status_is_proposed() -> None:
    """`proposed` is the store's own first state, and it is the only one buildable here."""
    assert suggest.PROPOSED == store.PROPOSED, (
        f"the generator calls it {suggest.PROPOSED!r} and the store calls it "
        f"{store.PROPOSED!r}. A proposal that does not land in the store's own first state "
        "is a fifth state nobody designed."
    )
    for made in proposals():
        assert made.status == store.PROPOSED, f"{made.type} arrived as {made.status!r}"

    for status in (store.ACCEPTED, store.NEEDS_REVIEW, store.REJECTED):
        with pytest.raises(RuleRejected) as raised:
            suggest.Proposal(
                type=catalog.TYPES[0],
                kwargs={"column": "order_total"},
                statement="Every order_total has a value",
                evidence="500,000 rows scanned",
                status=status,
            )
        assert status in str(raised.value), (
            f"a proposal was buildable as {status!r}, or refused without saying so. Nothing "
            "here has been judged by anyone; only a person moves a rule out of `proposed`."
        )


def test_the_generator_can_neither_store_nor_execute() -> None:
    """Asserted on the module's shape, which is the stronger of the two readings available.

    Counting rows before and after a call says "this call saved nothing". An import graph
    with no store, no GE door and no database driver in it says NO call can save or run
    anything — including the ones nobody thought to write a check for. `_prompt` is a
    string builder and `proposals()` is a pure function; the only impure line in the module
    is the model call in `for_table`, and reading is all it can do.

    Its dynamic companion is the `live` check in `tests/test_f3_model_call.py`, which
    counts the store's revisions across a real call. That one catches a caller wired up
    wrongly; this one catches a module written wrongly.
    """
    tree = ast.parse((REPO / SUGGEST).read_text())
    imported = {
        f"{node.module}.{alias.name}" if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
        if not isinstance(node, ast.ImportFrom) or node.module
    }
    modules = {name.rsplit(".", 1)[0] for name in imported} | imported
    assert modules, (
        f"the import scan found nothing in {SUGGEST} — it has stopped looking, and the "
        "assertion below would go green on an emptied or unparseable module."
    )
    reachable = sorted(m for m in FORBIDDEN_IMPORTS if m in modules)
    assert not reachable, (
        f"{SUGGEST} imports {reachable}. A proposal is not a rule: nothing here may be able "
        "to persist one or to run one. Accepting a proposal is a person's action, through "
        "app/rules/store.py, where INV-2's full gate runs."
    )
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not (dodges := called & {"__import__", "eval", "exec", "open", "connect"}), (
        f"{sorted(dodges)} reaches past the import graph — a builtin needs no import "
        "statement, so an allowlist alone would never see it."
    )


# --- with their evidence ------------------------------------------------------


def test_evidence_line_is_present_and_derived_from_the_profile() -> None:
    """Every number in the line is one the profiler measured, printed in full.

    SPEC F3's example is `500,000 rows scanned · 0 nulls · min observed 0.00`, so the
    grouped digits are part of the contract rather than a rendering choice: this is the
    line a reviewer checks a rule against, and `500K` would round away the thing being
    checked.
    """
    profiled = orders_profile()
    by_column = {made.column: made for made in proposals()}

    total = by_column["order_total"].evidence
    assert total.startswith("500,000 rows scanned"), f"got {total!r}"
    assert "0 nulls" in total, f"order_total has no nulls in the profile; got {total!r}"
    assert "min observed -389.59" in total and "max observed 89400.00" in total, (
        f"the observed bounds are what expose LT-2b's overfitted rule — a proposal capped at "
        f"the observed maximum is only recognisable next to that maximum; got {total!r}"
    )

    status = by_column["status"].evidence
    assert "4 distinct: cancelled, paid, shipped, shippd" in status, (
        f"a column whose whole distinct set is known cites the SET — that is what makes the "
        f"`shippd` typo visible to whoever judges the rule; got {status!r}"
    )

    shipped = suggest.evidence(profiled, "shipped_at")
    assert "189,588 nulls" in shipped, (
        f"the null count is derived from the profile's own non-null count, so a rule about "
        f"missing values is judged against the real gap; got {shipped!r}"
    )

    table_level = by_column[None].evidence
    assert table_level == "500,000 rows scanned", (
        f"a table-level rule names no column, so its evidence is the row count alone; "
        f"got {table_level!r}"
    )


def test_a_proposal_without_evidence_cannot_be_constructed() -> None:
    """The LT-2b countermeasure, as a property of the type rather than of each caller.

    `order_total BETWEEN 0 AND 89,400` is a rule nobody can judge without seeing that
    89,400 is simply the largest value in the table. So there is no way to build a proposal
    that has lost the line: omitting it is Python's own `TypeError`, and blanking it is
    refused with a reason.
    """
    with pytest.raises(TypeError) as omitted:
        suggest.Proposal(  # type: ignore[call-arg]
            type="expect_column_values_to_be_between",
            kwargs={"column": "order_total", "min_value": 0, "max_value": 89400},
            statement="Every order_total is between 0 and 89400",
        )
    assert "evidence" in str(
        omitted.value
    ), f"evidence must be a required field, so omitting it names itself: {omitted.value}"
    for blank in ("", "   "):
        with pytest.raises(RuleRejected) as raised:
            suggest.Proposal(
                type="expect_column_values_to_be_between",
                kwargs={"column": "order_total", "min_value": 0, "max_value": 89400},
                statement="Every order_total is between 0 and 89400",
                evidence=blank,
            )
        assert "evidence" in str(raised.value), str(raised.value)


# --- in plain English ---------------------------------------------------------


def test_every_proposal_states_its_rule_in_plain_english() -> None:
    """The sentence is what a domain expert judges; the expectation type is not."""
    made = {p.type: p for p in proposals()}
    assert made["expect_column_values_to_be_in_set"].statement == (
        "Every status is one of cancelled, paid, shipped"
    ), made["expect_column_values_to_be_in_set"].statement
    assert made["expect_column_values_to_be_between"].statement == (
        "Every order_total is between 0 and 89400"
    ), made["expect_column_values_to_be_between"].statement
    for proposal in made.values():
        assert not unsubstituted(proposal), (
            f"{unsubstituted(proposal)} reached the sentence unsubstituted: "
            f"{proposal.statement!r}. A domain expert judges this line, so a placeholder in "
            "it is the whole feature failing."
        )


def test_a_half_bounded_proposal_reads_as_a_sentence() -> None:
    """The rule F3 most wants proposed is the one a naive template breaks on.

    LT-2b's model never proposed `order_total >= 0` — but showing it the catalog beside
    the evidence is exactly the attempt to make it, and "Every order_total is between 0
    and None" would be an unjudgeable sentence for the most important rule in the demo.
    The swap itself lives in `app/rules/catalog.py::english()`, which F4 shares; what is
    checked here is that a proposal built through this module comes out readable.
    """
    reply = {
        "rules": [
            {
                "type": "expect_column_values_to_be_between",
                "kwargs": {"column": "order_total", "min_value": 0},
            },
            {
                "type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "shipped_at", "mostly": 0.98},
            },
        ]
    }
    lower, tolerated = suggest.proposals(orders_profile(), reply)
    assert lower.statement == "Every order_total is at least 0", lower.statement
    assert (
        tolerated.statement == "Every shipped_at has a value, in at least 98% of rows"
    ), tolerated.statement
