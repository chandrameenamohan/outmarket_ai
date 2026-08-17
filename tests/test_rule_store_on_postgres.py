"""F6 · the rule store against the real PostgreSQL it ships on.

The half of `tests/test_rule_store.py` that no amount of pure Python can answer,
and the reason it is a separate file: these three need the network, a database
and the framework, and they WRITE.

The one that matters most is `test_reaching_past_the_store_with_raw_sql_is_refused`
— it issues UPDATE, DELETE and TRUNCATE against the store's own table on the
store's own connection and is refused by the database. A check that goes through
the front door and passes proves the front door works; that one proves there is
no other door.

They cannot clean up after themselves — the table is append-only, which is the
whole point — so they write to a scratch schema (`conftest.SCRATCH_SCHEMA`) and
never to the store the demo reads from. An accepted junk rule there would not
merely be untidy: it would execute and count toward coverage.

Marked `ge` with the rest of the layer that needs a live database, and run by
`make check-ge`. `make check` installs nothing and reaches no network, so these
would be an ImportError there rather than a signal.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg2
import pytest

TABLE = "orders"

SPEC: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0},
}
OTHER_SPEC: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0, "max_value": 100000.0},
}

REJECTION = "cancelled orders use a fourth status not in this sample"

# The envelope of a Great Expectations SUITE. Never these keys, anywhere in our
# schema. Note what is NOT on this list: `type` and `kwargs`. A rule's identity IS
# its check type, and we store that; what is never stored is the compiled suite,
# because it is derivable and a second copy of a rule drifts from the rule.
GE_CONFIGURATION_KEYS = (
    "expectation_suite_name",
    "expectations",
    "data_asset_type",
    "ge_cloud_id",
    "batch_id",
    "result_format",
    "catch_exceptions",
    "severity",
    "meta",
)


def _store() -> Any:
    from app.rules import store  # noqa: PLC0415

    return store


@pytest.mark.ge
def test_a_rule_walks_the_workflow_and_every_revision_stays_readable() -> None:
    """The positive path, against the real store — the check that stops "refuse everything".

    Everything above proves things are refused, and a store that wrote nothing at
    all would pass all of it. This one walks a rule through proposal, review,
    acceptance and amendment, and asserts the two facts the workflow rests on:
    judging a rule cannot change what it checks, and every earlier revision is
    still readable afterwards.
    """
    store = _store()
    kwargs = {"column": "order_total", "min_value": 0}

    proposed = store.propose(TABLE, "expect_column_values_to_be_between", kwargs)
    assert (proposed.revision, proposed.status) == (1, store.PROPOSED)
    assert proposed.written_at is not None, "the database owns the clock; a written row has a time"
    assert proposed.spec == SPEC, (
        f"the store holds {proposed.spec}; the spec is validate()'s own return value, "
        "framework-normalised (min_value=0 -> 0.0), and nothing else can reach the table."
    )

    store.set_status(proposed.rule_id, store.NEEDS_REVIEW)
    accepted = store.set_status(proposed.rule_id, store.ACCEPTED)
    assert accepted.spec == proposed.spec, (
        "judging a rule changed what it checks. `set_status` carries the prior revision's spec "
        "forward; if it can rewrite one, acceptance is an unvalidated write."
    )
    assert proposed.rule_id in {r.rule_id for r in store.accepted(store.revisions(table=TABLE))}

    amended = store.amend(
        proposed.rule_id,
        "expect_column_values_to_be_between",
        {"column": "order_total", "min_value": 0, "max_value": 100000},
    )
    assert (amended.revision, amended.status) == (4, store.NEEDS_REVIEW)
    assert amended.spec == OTHER_SPEC
    assert proposed.rule_id not in {
        r.rule_id for r in store.accepted(store.revisions(table=TABLE))
    }, "an amended rule still counts toward coverage before anyone has judged the new spec"

    store.set_status(proposed.rule_id, store.REJECTED, REJECTION)
    ledger = store.revisions(rule_id=proposed.rule_id)
    assert [(r.revision, r.status) for r in ledger] == [
        (1, store.PROPOSED),
        (2, store.NEEDS_REVIEW),
        (3, store.ACCEPTED),
        (4, store.NEEDS_REVIEW),
        (5, store.REJECTED),
    ]
    assert ledger[0].spec == SPEC, "revision 1 is no longer readable as it was written"
    assert ledger[-1].reason == REJECTION
    assert store.accepted(ledger) == ()

    with pytest.raises(ValueError):
        store.set_status(proposed.rule_id, store.REJECTED)
    with pytest.raises(store.UnknownRule):
        store.latest("00000000-0000-0000-0000-000000000000")


@pytest.mark.ge
def test_reaching_past_the_store_with_raw_sql_is_refused() -> None:
    """The check worth more than all the front-door ones: there IS no other door.

    Raw SQL on the store's own connection, as the role that owns the table —
    which is the strongest attacker this deliberate single-credential deployment
    has (SPEC §3.1's role split is bead dq-5pb.2). A grant would not stop it; the
    trigger does, and so do the two constraints, so "no way to edit them quietly"
    is a property of the database rather than of this codebase's manners.
    """
    store = _store()
    schema = store._schema()  # reaching past the front door is the whole point of this check
    conn = store._connection()
    store.propose(TABLE, "expect_column_values_to_be_unique", {"column": "order_reference"})

    refusals = {
        f"update {schema}.rules set status = 'accepted'": "append-only",
        f"delete from {schema}.rules": "append-only",
        f"truncate {schema}.rules": "append-only",
        # A row that never went through validate() is not stoppable by SQL — but a
        # row in a state nobody defined, or a rejection with no reason, is.
        f"insert into {schema}.rules (rule_id, revision, table_name, spec, status) "
        f"values (gen_random_uuid(), 1, '{TABLE}', '{{}}'::jsonb, 'approved')": "status",
        f"insert into {schema}.rules (rule_id, revision, table_name, spec, status) "
        f"values (gen_random_uuid(), 1, '{TABLE}', '{{}}'::jsonb, 'rejected')": "reason",
    }

    for sql, expected in refusals.items():
        with pytest.raises(psycopg2.Error) as exc, conn, conn.cursor() as cur:
            cur.execute(sql)
        assert expected in str(exc.value).lower(), (
            f"`{sql}` was answered with {exc.value!r} rather than a refusal naming {expected!r}. "
            "Every one of these is a way to edit a rule without leaving a revision behind."
        )


@pytest.mark.ge
def test_no_stored_ge_configuration_exists_anywhere_in_the_schema() -> None:
    """F6/INV-3: the framework's configuration is compiled on demand, never stored.

    Two halves. The negative one reads the live schema and every stored spec and
    finds no trace of a suite. The positive one compiles the accepted rules and
    shows the configuration comes back identical to what was compiled from the
    stored specs — which is what makes storing it pointless rather than merely
    forbidden.
    """
    from app.dq import ge_runtime  # noqa: PLC0415

    store = _store()
    schema = store._schema()
    conn = store._connection()

    written = store.propose(
        TABLE, "expect_column_values_to_be_between", {"column": "order_total", "min_value": 0}
    )
    store.set_status(written.rule_id, store.ACCEPTED)

    with conn, conn.cursor() as cur:
        cur.execute(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = %s",
            (schema,),
        )
        columns = cur.fetchall()
        cur.execute(f"select spec::text from {schema}.rules")
        specs = [row[0] for row in cur.fetchall()]

    assert columns, f"schema {schema!r} holds no columns; the store did not create its table"
    named = [f"{t}.{c}" for t, c in columns for k in GE_CONFIGURATION_KEYS if k in c]
    assert not named, f"columns named for a framework configuration: {named}"

    leaked = [(k, s) for s in specs for k in GE_CONFIGURATION_KEYS if f'"{k}"' in s]
    assert not leaked, (
        f"stored specs carry framework configuration keys: {leaked}. A stored suite is a second "
        "copy of a rule, and it drifts from the rule silently."
    )
    assert all(set(json.loads(s)) == {"type", "kwargs"} for s in specs), (
        "a stored spec is ours: a check type and its kwargs. Anything else came from the "
        "framework and belongs to the compiler. Read off the raw jsonb rather than off "
        "Revision, whose constructor refuses any other shape before an assert could see it."
    )

    compiled = ge_runtime.compile_suite(TABLE, [written.spec])
    assert compiled["expectations"] == [written.spec], (
        "compiling the stored specs did not reproduce them, so the configuration shown to an "
        "author would describe a rule other than the one that runs"
    )


@pytest.mark.ge
def test_a_rejected_spec_writes_no_row() -> None:
    """INV-2 from the other end: the store's own row count, before and after every probe.

    The companion to
    `tests/test_inv2_authoring_rejection.py::test_a_rejected_spec_writes_nothing`,
    which asserts the validator's import graph. This one goes through the FRONT
    DOOR — `store.propose()`, the way a rule is actually authored — so it covers
    the thing that COMPOSES the validator with the store, which is where the bug
    would actually live. The probe list is imported rather than restated: two
    copies of it would agree on the day they were written and never again.
    """
    from test_inv2_authoring_rejection import ALL_PROBES  # noqa: PLC0415

    from app.rules import validator  # noqa: PLC0415

    store = _store()
    before = len(store.revisions())

    for etype, kwargs, _ in ALL_PROBES:
        with pytest.raises(validator.RuleRejected):
            store.propose("orders", etype, kwargs)

    assert len(store.revisions()) == before, (
        f"{len(store.revisions()) - before} row(s) appeared while {len(ALL_PROBES)} invalid "
        "rules were refused. A validator that raises and a store that already wrote are both "
        "possible at once, and this is the half that catches it."
    )
