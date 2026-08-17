"""F6 · the rule store: four states, append-only, and no door that skips the validator.

The four unit checks drive the store's PURE half — the `Revision` type and the two
folds over a ledger of revisions — so the whole of the workflow's meaning is
checkable in `make check`, with no network and no framework. The half only a real
database can answer is in `tests/test_rule_store_on_postgres.py` — including the
check that matters most, which reaches past this module with raw SQL and is
refused by the database itself.

Two things are asserted in two places on purpose, because they are the two facts
that would rot silently if either copy moved alone: the four state names (the
dataclass and the CHECK constraint in `app/rules/store.sql`) and the
rejection-carries-a-reason rule (same two). A state the type allows and the
database refuses is a defect nobody meets until a user clicks the button.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from typing import Any

import pytest

from conftest import REPO, source_files

STORE = REPO / "app/rules/store.py"
DDL = REPO / "app/rules/store.sql"

TABLE = "orders"

# A spec exactly as `validate()` returns it: ours, two keys, framework-normalised.
SPEC: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0},
}
OTHER_SPEC: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0, "max_value": 100000.0},
}

REJECTION = "cancelled orders use a fourth status not in this sample"

# The three writers, named here so a fourth cannot be added quietly. Every one of
# them appends; none of them updates. See `test_the_store_has_no_writer_that_skips
# _the_validator` for what this constant is used for and why it is a closed set.
WRITERS = {"propose", "amend", "set_status"}

# A string literal that IS a statement, rather than prose that mentions one — the
# module docstring says the words UPDATE and DELETE, and store.sql's comments say
# them at length. Anchored at the start for that reason.
STATEMENT = re.compile(r"^\s*(select|insert|update|delete|truncate|create|drop|with)\b", re.I)
SQL_TARGET = re.compile(
    r"\b(?:insert\s+into|delete\s+from|update|truncate|from|join)\s+([\w.{}]+)", re.I
)


def _store() -> Any:
    from app.rules import store  # noqa: PLC0415

    return store


def rev(
    rule_id: str,
    revision: int,
    status: str,
    reason: str | None = None,
    spec: dict[str, Any] | None = None,
) -> Any:
    return _store().Revision(
        rule_id=rule_id,
        revision=revision,
        table=TABLE,
        spec=SPEC if spec is None else spec,
        status=status,
        reason=reason,
    )


# --- The workflow, checkable without a database -------------------------------


def test_unknown_state_is_rejected() -> None:
    """Four states, closed, and closed in the database too.

    The second half is the one that is easy to leave out. `STATES` and the CHECK
    constraint in store.sql are two copies of the same decision, and the direction
    that hurts is silent: a fifth state the dataclass accepts is written by the
    app and refused by the database at the moment a user acts.
    """
    store = _store()
    assert store.STATES == ("proposed", "needs_review", "accepted", "rejected")

    for state in store.STATES:
        assert rev("r1", 1, state, reason=REJECTION).status == state

    for bogus in ("approved", "PROPOSED", "pending", "", "deleted"):
        with pytest.raises(ValueError) as exc:
            rev("r1", 1, bogus)
        assert all(s in str(exc.value) for s in store.STATES), (
            f"refusing {bogus!r} must name the four states that ARE allowed, since the caller's "
            f"next move is to pick one: {exc.value}"
        )

    declared = re.search(r"status in \(([^)]*)\)", DDL.read_text())
    assert declared, "store.sql no longer constrains `status`; the four states are code-only now"
    assert tuple(re.findall(r"'([a-z_]+)'", declared.group(1))) == store.STATES, (
        f"store.sql allows {declared.group(1)} and app/rules/store.py allows {store.STATES}. "
        "Two copies of the state set have drifted, and the database has the last word."
    )


def test_rejection_without_a_reason_is_refused() -> None:
    """A rejected rule with no reason gets proposed again next week.

    Asserted on both routes into the state — building one directly, and judging an
    existing rule into it — because the second is how it actually happens.
    """
    store = _store()

    for empty in (None, "", "   ", "\n"):
        with pytest.raises(ValueError) as exc:
            rev("r1", 1, store.REJECTED, reason=empty)
        assert "reason" in str(exc.value)

    with pytest.raises(ValueError):
        rev("r1", 2, store.ACCEPTED).judged(store.REJECTED)

    rejected = rev("r1", 2, store.ACCEPTED).judged(store.REJECTED, REJECTION)
    assert rejected.reason == REJECTION and rejected.status == store.REJECTED
    assert "a_rejection_carries_its_reason" in DDL.read_text(), (
        "the database no longer constrains a rejection to carry its reason. The type check "
        "above only covers rows this process wrote."
    )


def test_only_accepted_rules_count_toward_coverage() -> None:
    """Coverage counts the CURRENT revision, and only the accepted ones.

    The rule with a history is the point: `b` was accepted and later rejected, so
    a fold that asks "was this ever accepted" — or one that trusts row order rather
    than revision number — counts it and reports protection the table does not
    have. The ledger is shuffled for that reason.
    """
    store = _store()
    ledger = [
        rev("a", 1, store.PROPOSED),
        rev("a", 2, store.ACCEPTED),
        rev("b", 1, store.PROPOSED),
        rev("b", 2, store.ACCEPTED),
        rev("b", 3, store.REJECTED, REJECTION),
        rev("c", 1, store.NEEDS_REVIEW),
        rev("d", 1, store.PROPOSED),
    ]

    for order in (ledger, list(reversed(ledger)), [ledger[i] for i in (4, 0, 6, 2, 5, 1, 3)]):
        counted = store.accepted(order)
        assert [(r.rule_id, r.revision) for r in counted] == [("a", 2)], (
            f"coverage counted {[(r.rule_id, r.status) for r in counted]}. Only `a` is currently "
            "accepted: `b` was accepted and then rejected, and the current revision is the rule."
        )
        assert {r.rule_id for r in store.current(order)} == {"a", "b", "c", "d"}
        assert {(r.rule_id, r.revision) for r in store.current(order)} == {
            ("a", 2),
            ("b", 3),
            ("c", 1),
            ("d", 1),
        }


def test_amend_creates_a_revision_and_preserves_the_prior_one() -> None:
    """Amending is appending. The prior revision is untouched — by the type, not by care.

    And an amended rule lands in `needs_review`, never back in `accepted`: a change
    to what a rule CHECKS is judged by a person before it runs again, or the
    two-user workflow is decoration.
    """
    store = _store()
    prior = rev("a", 2, store.ACCEPTED)
    amended = prior.amended(OTHER_SPEC)

    assert (amended.rule_id, amended.revision) == ("a", 3)
    assert amended.spec == OTHER_SPEC
    assert amended.status == store.NEEDS_REVIEW, (
        f"an amended rule came back {amended.status!r}. Inheriting `accepted` is an edit in "
        "place wearing a revision number — the new spec would run before anyone judged it."
    )

    assert prior.spec == SPEC and prior.status == store.ACCEPTED and prior.revision == 2, (
        "amending mutated the revision it was called on; 'the previous one stays readable' "
        "is exactly what that breaks"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        prior.status = store.REJECTED

    ledger = [prior, amended]
    assert store.current(ledger) == (amended,)
    assert store.accepted(ledger) == (), (
        "the amended rule still counts toward coverage. Until someone accepts the new spec, "
        "the table is covered by a rule nobody agreed to."
    )
    assert prior in ledger, "history must still hold the revision that was superseded"


# --- No quiet edits, and no writer that skips the validator --------------------


def _functions(tree: ast.AST) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]


def _sql_literal(node: ast.AST) -> str:
    """A string literal's text, f-string or not — `{schema}` survives as itself."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_sql_literal(part) for part in node.values)
    return ""


def _calls(node: ast.AST) -> set[str]:
    names = set()
    for call in [n for n in ast.walk(node) if isinstance(n, ast.Call)]:
        func = call.func
        if isinstance(func, ast.Attribute):
            names.add(func.attr)
        elif isinstance(func, ast.Name):
            names.add(func.id)
    return names


def test_the_store_has_no_writer_that_skips_the_validator() -> None:
    """INV-2's other half: there is no back door into the table.

    The closed set is the load-bearing assertion. A new function that appends is not
    forbidden — it is required to be added to `WRITERS` here, in front of a failing
    check, where whoever adds it has to say whether it validates. That is the only
    version of this check that survives the codebase growing.

    `_append` is private by convention only, so the closed set is worth nothing if
    the scan stops at this file: `from app.rules.store import _append` from an API
    handler reaches the INSERT with a spec `validate()` never saw. The second scan
    closes the class rather than the instance, the same way INV-3's text scan does.

    What it does NOT prove: that `set_status` carries the prior spec forward
    unaltered. Nothing structural can prove that, so it is asserted dynamically in
    `test_a_rule_walks_the_workflow_and_every_revision_stays_readable`.
    """
    source = STORE.read_text()
    tree = ast.parse(source)
    functions = {f.name: f for f in _functions(tree)}

    assert source.lower().count("insert into") == 1, (
        "more than one INSERT statement exists in the store. One writer to the table, reached "
        "by every path, or 'nothing reaches the store without the validator' has as many "
        "proofs as there are call sites."
    )
    outside = [
        f"{p.relative_to(REPO)}:{i}"
        for p in source_files("app")
        if p != STORE
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if "_append(" in line
    ]
    assert not outside, (
        f"{outside} calls the store's private writer directly. `_append` is the INSERT; a "
        "caller that reaches it has skipped validate(), which is the one thing INV-2 forbids. "
        "Go through propose(), amend() or set_status()."
    )

    # One credential with rights over everything (SPEC §3.1's role split is bead
    # dq-5pb.2, unbuilt), so "the store never writes to the tables under analysis"
    # rests entirely on WHERE its statements point. That is checkable, so it is
    # checked rather than claimed: `or`/`on` are the trigger's event list
    # (`before update or delete or truncate on ...`), not object names.
    statements = [s for n in ast.walk(tree) if (s := _sql_literal(n)) and STATEMENT.match(s)]
    statements.append(re.sub(r"--[^\n]*", "", DDL.read_text()))
    targets = {m.group(1) for s in statements for m in SQL_TARGET.finditer(s)} - {"or", "on"}
    assert targets == {"{schema}.rules"}, (
        f"the store's SQL names {sorted(targets)}. Every statement in app/rules/store.py and "
        "store.sql addresses {schema}.rules and nothing else — that is what keeps a table "
        "under analysis unreachable from a connection that could write to it."
    )
    inserters = {
        name
        for name, fn in functions.items()
        if any(isinstance(n, ast.Name) and n.id == "_WRITE" for n in ast.walk(fn))
    }
    assert inserters == {"_append"}, f"the INSERT is issued from {sorted(inserters)}, not _append"

    writers = {name for name, fn in functions.items() if "_append" in _calls(fn)} - {"_append"}
    assert writers == WRITERS, (
        f"the functions that append are {sorted(writers)}; this check knows about "
        f"{sorted(WRITERS)}. A new writer is a decision: add it here and say whether it "
        "validates the spec it writes."
    )

    for name in ("propose", "amend"):
        assert "validate" in _calls(functions[name]), (
            f"{name}() writes a spec that came from its caller and never calls validate(). "
            "An invalid or hallucinated rule reaching the store is the one thing INV-2 forbids."
        )
    assert "validate" not in _calls(functions["set_status"]), (
        "set_status() validates, which means it can also refuse. A rule whose column was "
        "dropped must still be rejectable — rejecting it is the remedy."
    )


def test_no_mutation_route_exists_for_a_stored_rule_or_run_record() -> None:
    """Write-resistance, on both surfaces a mutation could arrive through.

    The SQL surface: no statement anywhere in `app/` updates, deletes or truncates
    anything. The only files that say those words are `store.sql` and
    `app/dq/runs.sql`, where they name what each trigger REFUSES.

    The HTTP surface: no route handler answers PUT, PATCH or DELETE, and nothing
    in the route tree sends one. A run record inherits this for free (B15) — the
    check is over the whole tree, not over a rule screen — which is why it is
    written once, here.
    """
    mutations = re.compile(
        r"\bdelete\s+from\b|\bupdate\s+[\w.{}]+\s+set\b|\btruncate\s+(table\s+)?[\w.{}]+\s*;",
        re.IGNORECASE,
    )
    offenders = [
        f"{p.relative_to(REPO)}: {m.group(0).strip()}"
        for p in source_files("app")
        for m in mutations.finditer(p.read_text())
    ]
    assert not offenders, (
        f"SQL that edits or removes a stored row: {offenders}. The store is append-only — a "
        "rule is amended by appending a revision and a run by appending a record."
    )

    ddl = DDL.read_text()
    assert "before update or delete or truncate" in ddl and "for each statement" in ddl, (
        "store.sql no longer refuses UPDATE/DELETE/TRUNCATE at the database. Everything above "
        "this line is then a promise about our own code rather than a property of the store."
    )

    verbs = re.compile(
        r"export\s+(async\s+function|function|const)\s+(PUT|PATCH|DELETE)\b"
        r"|method:\s*['\"](PUT|PATCH|DELETE)"
    )
    routes = [
        f"{p.relative_to(REPO)}: {m.group(0)}"
        for p in (REPO / "web/app").rglob("*")
        if p.suffix in {".ts", ".tsx"}
        for m in verbs.finditer(p.read_text())
    ]
    assert not routes, (
        f"a mutation route exists: {routes}. Amending a rule POSTs a new revision and re-running "
        "POSTs a new record; there is nothing for PUT, PATCH or DELETE to address."
    )
