"""F8 · which rules a run submits, and the two settings that decide what comes back.

The half of rule execution that does not depend on how a run is TRIGGERED. Three
facts, and each one is a silent wrong answer if it slips:

  WHICH RULES RUN     only `accepted` ones, and only their current revision. The
                      store is append-only, so a rule that was accepted and has
                      since been rejected is still sitting there at revision 1.
  THE ASSET KIND      a table asset, never a query asset. The query asset is the
                      framework's only row cap; it is a net loss at full size and
                      it leaves the two `type` expectations with no reflected table,
                      so they raise a bare `KeyError: 'type'` that `catch_exceptions`
                      renders as a red rule with no offending rows and no reason —
                      someone then hunts a data problem that does not exist (LT-1b).
  THE RESULT FORMAT   SUMMARY with `unexpected_index_column_names`. COMPLETE is
                      never emitted: it drops the LIMIT from the sample query and
                      materialises every offending row in this process AND in the
                      stored raw output, 500,031 values in the measured wide case
                      (LT-1a). Memory and storage, not latency — the measurement
                      does not support a latency claim.

The first is a pure fold and is checked directly. The other two live in
`app/dq/ge_runtime.py`, which imports the framework at module level and therefore
cannot be imported by `make check` at all — so they are read out of the source with
`ast`, which pins the literal that will run rather than the prose around it. The
`ge` check at the bottom then runs the whole path against the real seeded table and
grades it against `seed/MANIFEST.md`: 150 negative totals (D1), 240 statuses outside
the vocabulary (D3), 150 rows sharing a duplicated reference (D6).
"""

from __future__ import annotations

import ast
import json
import pathlib
from typing import Any

import pytest

from app.dq import normalise
from app.rules import store
from conftest import REPO, module_constant, source_files

GE_RUNTIME = pathlib.Path("app/dq/ge_runtime.py")

TABLE = "orders"

# seed/MANIFEST.md, keyed by the column each rule watches. D1 / D3 / D6. The
# manifest is the authority and is never adjusted to match the engine: a lower
# number is a gap in the engine, a higher one is drift in the seed.
PLANTED = {"order_total": 150, "status": 240, "order_reference": 150}

# The disclosure's denominator, and it is OURS (INV-5). The framework records
# nothing that distinguishes a capped run from an honest run over a smaller table,
# so the total cannot come from the thing being disclosed.
SEEDED_ROWS = 500_000

# Three accepted rules for one table, in the shape the store holds them.
NEGATIVE: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0},
}
IN_SET: dict[str, Any] = {
    "type": "expect_column_values_to_be_in_set",
    "kwargs": {
        "column": "status",
        "value_set": ["pending", "paid", "shipped", "delivered", "cancelled", "returned"],
    },
}
UNIQUE: dict[str, Any] = {
    "type": "expect_column_values_to_be_unique",
    "kwargs": {"column": "order_reference"},
}
SPECS: list[dict[str, Any]] = [NEGATIVE, IN_SET, UNIQUE]


def test_only_accepted_rules_are_executed() -> None:
    """A run submits the current revision of each `accepted` rule, and nothing else.

    Both directions matter and the second is the one that bites: `proposed` and
    `needs_review` rules must not run (nobody judged them), and a rule that WAS
    accepted and has since been rejected must stop running — which is only true if
    the fold reads the CURRENT revision rather than every row in an append-only
    table.
    """
    revisions = [
        store.Revision("r1", 1, TABLE, NEGATIVE, store.ACCEPTED),
        store.Revision("r2", 1, TABLE, IN_SET, store.PROPOSED),
        store.Revision("r3", 1, TABLE, UNIQUE, store.NEEDS_REVIEW),
        store.Revision("r4", 1, TABLE, IN_SET, store.REJECTED, reason="status list is stale"),
    ]
    assert normalise.executable(revisions) == (NEGATIVE,), (
        f"executed {normalise.executable(revisions)}; only the accepted rule runs. A proposed "
        "rule that executes reports on a rule nobody judged."
    )

    withdrawn = [*revisions, store.Revision("r1", 2, TABLE, NEGATIVE, store.REJECTED, reason="no")]
    assert normalise.executable(withdrawn) == (), (
        "a rejected rule kept running because the fold read every revision instead of the "
        "current one — the store is append-only, so revision 1 is still sitting there"
    )

    accepted_again = [*withdrawn, store.Revision("r1", 3, TABLE, NEGATIVE, store.ACCEPTED)]
    assert normalise.executable(accepted_again) == (NEGATIVE,)


def test_result_format_complete_is_never_emitted() -> None:
    """SUMMARY ships; COMPLETE is a trap, on memory and storage grounds (LT-1a).

    COMPLETE drops the LIMIT from the sample query and materialises every offending
    row — in this process and in the raw output F9 stores alongside every result —
    500,031 values in the measured wide case. Not a latency argument: the
    measurement does not support one.

    Read out of the source with `ast` rather than by importing: that module imports
    the framework at module level and `make check` has none. Reading the literal
    that will run is stronger than a text scan, which would also flag the comment
    explaining why the setting is what it is.
    """
    fmt = module_constant(str(GE_RUNTIME), "RESULT_FORMAT")
    assert fmt == {"result_format": "SUMMARY"}, (
        f"the shipping result format is {fmt}. SUMMARY carries the violating count and a "
        "bounded sample; anything else changes what every stored run costs."
    )

    run = _function(GE_RUNTIME, "run")
    assert "COMPLETE" not in _literals(run), (
        "`run` composes the string COMPLETE. The constant above is then decoration, and the "
        "LIMIT that keeps a run bounded is gone."
    )
    assert "result_format" in _keywords(run), (
        "`run` passes no result_format, so the framework's default stands and the constant "
        "above describes nothing that happens"
    )


def test_the_executor_builds_a_table_asset_and_never_a_query_asset() -> None:
    """The asset kind is the whole of SPEC O-2, and it is one method name.

    A query asset is the only row cap the framework offers; it is a net loss at
    full size, and it leaves the two `type` expectations with no reflected table to
    read a column type from, so they raise a bare `KeyError: 'type'` that
    `catch_exceptions` renders as a red rule with no offending rows and no reason —
    sending someone hunting a data problem that does not exist (LT-1b).

    The behavioural half of this runs in the `ge` layer already
    (`tests/test_catalog_and_copy.py::test_the_two_type_expectations_run_against_a_table_asset`).
    This is the structural half, and it also pins that no SECOND module builds an
    asset — the invariant is one door, not one polite caller.
    """
    called = {
        node.func.attr
        for node in ast.walk(_tree(GE_RUNTIME))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert (
        "add_table_asset" in called and "add_batch_definition_whole_table" in called
    ), f"{GE_RUNTIME} builds no whole-table batch definition; it called {sorted(called)}"
    assert "add_query_asset" not in called

    elsewhere = [
        p.relative_to(REPO)
        for p in source_files("app")
        if p.relative_to(REPO) != GE_RUNTIME
        and any(name in p.read_text() for name in ("add_table_asset", "add_query_asset"))
    ]
    assert not elsewhere, (
        f"{elsewhere} build a batch asset. One module builds one kind of asset, or the row cap "
        "and INV-5's marker have two origins and only one of them is checked."
    )


@pytest.mark.ge
def test_run_against_seeded_orders_reports_the_planted_defect_counts() -> None:
    """The acceptance, against the live 500,000-row table, graded on the manifest.

    Everything the bead promises in one pass: the three rules execute, `success` is
    the source of truth for the verdict, the violating counts match what
    `seed/MANIFEST.md` documents as planted, real offending values come back with
    the row identifier F13 needs, nothing errored, coverage counts all three — and
    the sampling marker travels from the asset definition rather than from anything
    the framework said.
    """
    from app.dq import ge_runtime  # noqa: PLC0415
    from app.rules import schema as live  # noqa: PLC0415

    identifiers = live.primary_key(TABLE)
    assert identifiers == ("order_id",), f"{TABLE} reports its key as {identifiers}"

    specs = [ge_runtime.construct(s["type"], s["kwargs"]) for s in SPECS]
    report = ge_runtime.run(TABLE, specs, table=TABLE, identifiers=identifiers)
    scan = normalise.Scan(TABLE, SEEDED_ROWS, ge_runtime.ROW_LIMIT)
    results = normalise.normalise(specs, report, scan)

    found = {r.spec["kwargs"]["column"]: r.unexpected_count for r in results}
    assert found == PLANTED, (
        f"the run reported {found}; seed/MANIFEST.md plants {PLANTED} (D1, D3, D6). The "
        "manifest is the ground truth and is never adjusted to match the engine."
    )
    assert [r.verdict for r in results] == ["failed"] * 3, (
        f"got {[(r.spec['kwargs']['column'], r.verdict, r.detail) for r in results]}. Every one "
        "of these rules is aimed at a planted defect, and an errored one would look identical "
        "in the framework's own output."
    )
    assert normalise.coverage(results) == 3

    for r in results:
        assert r.samples, f"{r.statement} reported {r.unexpected_count} violations and no values"
        assert r.identified and "order_id" in r.identified[0], (
            f"{r.statement} carries values without the row they came from: {r.identified[:1]}. "
            "F13 renders '#88231 −450.00' — the identifier is half of it."
        )
        assert "unexpected_index_query" not in r.raw["result"], (
            "the raw result carries unexpected_index_query, which only COMPLETE emits — the "
            "sample query has lost its LIMIT and every offending row is now in memory"
        )

    assert results[0].statement == "Every order_total is at least 0"
    assert results[0].magnitude == (
        f"{PLANTED['order_total']:,} violating rows · of {SEEDED_ROWS:,} rows scanned · 0.03%"
    ), (
        f"the live run reads {results[0].magnitude!r}. SPEC F13's own illustration is D1 against "
        "the seeded table, so this is the sentence the product actually produces, not a fixture."
    )
    assert results[0].evidence[0].startswith("#"), (
        f"the offending rows read {results[0].evidence[:2]} — F13 renders '#88231 −450.00', and "
        "an identifier is what lets someone open the order and judge it (INV-4)"
    )
    assert not any(r.sampled for r in results), "no cap ships at this scale (SPEC O-2)"
    assert {r.atom for r in results} == {"FAILED"}, f"{[r.atom for r in results]}"
    assert json.loads(json.dumps([r.record() for r in results]))[0]["raw"]["expectation_config"], (
        "the framework's own output must survive being stored next to the reading of it — it "
        "is the collapsed panel a person opens when the reading is not enough (INV-4)"
    )


def _tree(relative: pathlib.Path) -> ast.AST:
    return ast.parse((REPO / relative).read_text(), filename=str(relative))


def _function(relative: pathlib.Path, name: str) -> ast.FunctionDef:
    found = [
        n for n in ast.walk(_tree(relative)) if isinstance(n, ast.FunctionDef) and n.name == name
    ]
    assert len(found) == 1, f"{relative} defines {len(found)} functions called {name}"
    return found[0]


def _literals(fn: ast.FunctionDef) -> set[str]:
    """Every string literal in a function BODY, past its docstring."""
    return {
        n.value
        for stmt in fn.body[1:]
        for n in ast.walk(stmt)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def _keywords(fn: ast.FunctionDef) -> set[str]:
    return {
        kw.arg
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        for kw in n.keywords
        if kw.arg is not None
    }
