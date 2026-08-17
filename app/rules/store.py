"""F6 · rules persist in OUR format, with the two-user workflow in their state.

Three claims live here, and each one is a mechanism rather than a convention.

ONE · THE WORKFLOW IS THE STATE. A rule is in exactly one of four states, and the
set is closed in two places that are checked against each other — `STATES` below
and a CHECK constraint in `store.sql`. Only `accepted` rules execute and only
`accepted` rules count toward coverage, which is why `accepted()` is a function
here and not a filter each caller writes for itself: a screen that counted
`proposed` rules would report coverage the table does not have.

TWO · THERE IS NO QUIET EDIT. The table is APPEND-ONLY and the database is what
says so — a trigger refuses UPDATE, DELETE and TRUNCATE from every role, so
amending a rule appends a revision and the previous one stays readable. Nothing
in this module issues an UPDATE; the point is that it would not matter if it did.
`tests/test_rule_store_on_postgres.py::test_reaching_past_the_store_with_raw_sql_is_refused`
reaches past this module with raw SQL and is refused, which is worth more than a
check that goes through the front door and passes.

THREE · NOTHING REACHES THE TABLE WITHOUT THE VALIDATOR (INV-2). A spec enters
through `propose()` or `amend()`, and both hand it to `app/rules/validator.py`
first — with the live column set, so an identifier from model output is checked
against the schema it will run against. `set_status()` writes no spec at all: it
carries the prior revision's forward untouched, which is why judging a rule cannot
be a back door into changing what it checks. The three writers are a closed set
and the gate asserts it, so a fourth one is a decision someone has to make in
front of a failing test. `judge_batch()` is not one: it appends nothing itself
and reaches the table only through `propose()` and `set_status()`, which is what
makes F12's bulk accept incapable of skipping the validator however many rules a
person selected.

WHAT IS NEVER STORED: the Great Expectations configuration. The stored spec is
`{"type": ..., "kwargs": {...}}` — ours, and the same shape `compile_suite()`
takes — and the suite shown in the UI is compiled on demand (INV-3). A stored
suite would be a second source of truth that drifts silently from the rule.

WHAT THIS MODULE IS NOT: a query layer. Reading is one statement with two optional
filters, and the folds over what comes back (`current`, `accepted`) are pure
functions of a list of revisions, so the workflow's rules are checkable without a
database. That split is deliberate — the four unit checks in `tests/test_rule_store.py`
drive the folds directly and run in `make check`, which has no network.

FOUR · IT CANNOT REACH THE TABLES UNDER ANALYSIS. The write path connects through
`app/db/system.py` as `dq_system` (`SUPABASE_DB_URL_SYSTEM`), a role granted nothing
at all on `public` — see `app/db/roles.sql`. Every statement in this module and in
`store.sql` names `{schema}.rules` and nothing else, and
`tests/test_rule_store.py::test_the_store_has_no_writer_that_skips_the_validator`
asserts that target set exhaustively; but that is a fact about THIS CODE, and a
future bug would sail past it. The grants are what make it a fact about the
CONNECTION — `tests/test_db_privilege_split.py` writes to `orders` on this very
connection and shows PostgreSQL refusing it.
"""

from __future__ import annotations

import dataclasses
import pathlib
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from psycopg2.extras import Json

from app.db import system
from app.rules import schema as live
from app.rules import validator

DDL = pathlib.Path(__file__).with_name("store.sql").read_text()

# The four states, in the order a rule normally walks them. `store.sql` repeats
# them in a CHECK constraint and the gate fails if the two ever disagree.
PROPOSED, NEEDS_REVIEW, ACCEPTED, REJECTED = "proposed", "needs_review", "accepted", "rejected"
STATES: tuple[str, ...] = (PROPOSED, NEEDS_REVIEW, ACCEPTED, REJECTED)

_COLUMNS = "rule_id, revision, table_name, spec, status, reason, written_at"

_READ = f"""
    select {_COLUMNS}
      from {{schema}}.rules
     where (%(table)s::text is null or table_name = %(table)s::text)
       and (%(rule)s::uuid is null or rule_id = %(rule)s::uuid)
     order by table_name, rule_id, revision
"""

# `written_at` is the database's to set, so it is read back rather than sent.
_WRITE = """
    insert into {schema}.rules (rule_id, revision, table_name, spec, status, reason)
    values (%s, %s, %s, %s, %s, %s)
    returning written_at
"""


# F12 · how many rules one bulk accept may carry. It is a REVIEW limit rather than a
# transaction limit, and the sentence that explains it is
# `app/dq/status.py::bulk_note()` — the number lives here because this is the module
# that refuses one past it, and a cap a client applies is a cap anybody can post past.
#
# Eight is what fits on a screen alongside its evidence lines, which is the whole
# requirement (UX_HARNESS_FINDINGS §4): a bulk accept that hides what it is accepting
# is how forty business-naive rules (LT-2b) enter at once.
BULK_CAP = 8


class UnknownRule(LookupError):
    """No rule with that id has ever been written here."""


def judgeable(status: str, reason: str | None) -> None:
    """Is this a judgment the store will accept? Raises `ValueError` naming what is wrong.

    Split out of `Revision.__post_init__` — which is still its only unconditional
    caller, so nothing can be stored without passing it — because `judge_batch()`
    below has to ask the question BEFORE it writes anything. That is a sequencing
    problem and not a duplication one: an unsaved proposal is persisted by `propose()`
    and judged by `set_status()`, so a reasonless rejection discovered at the second
    step would leave revision 1 sitting in an append-only table, proposed by a machine
    and judged by nobody, with no way to take it back out.

    One function, two callers, one copy of the rule.
    """
    if status not in STATES:
        raise ValueError(
            f"{status!r} is not a rule state; the four are {STATES}. A fifth state "
            "would have to mean something to both users, and the two questions this "
            "product asks — is it worth reviewing, is it worth running — have four answers."
        )
    if status == REJECTED and not (reason or "").strip():
        raise ValueError(
            "a rejected rule must carry the reason it was rejected. A rule that vanishes "
            "with no reason gets proposed again next week, and the person who rejected it "
            "is the only one who knows why it should not be."
        )


@dataclasses.dataclass(frozen=True)
class Revision:
    """One revision of one rule — the unit this store holds, and never edits.

    Frozen because the amendment model depends on it: `judged()` and `amended()`
    return a NEW revision and cannot touch the one they were called on, so "the
    previous one stays readable" is a property of the type and not of the care
    taken by each caller.

    `spec` is exactly what `app/rules/validator.py::validate()` returned — the
    framework's own normalisation of the rule, and the shape `compile_suite()`
    consumes. Two keys, checked here, because that check is what stops a compiled
    suite or a framework result being stuffed into this column later.

    `written_at` is None until the row exists. That is the honest reading of an
    in-memory revision: the database owns the clock, so a revision that has not
    been written has no time.
    """

    rule_id: str
    revision: int
    table: str
    spec: Mapping[str, Any]
    status: str
    reason: str | None = None
    written_at: datetime | None = None

    def __post_init__(self) -> None:
        judgeable(self.status, self.reason)
        if set(self.spec) != {"type", "kwargs"}:
            raise ValueError(
                f"a stored spec is {{'type', 'kwargs'}}, ours, as validate() returned it; got "
                f"{sorted(self.spec)}. The Great Expectations configuration is compiled on "
                "demand and is never stored (F6, INV-3)."
            )
        if self.revision < 1:
            raise ValueError(f"revision {self.revision} — revisions start at 1 and only rise")

    def judged(self, status: str, reason: str | None = None) -> Revision:
        """The same rule, one revision on, in a new state. The spec is carried, never re-typed."""
        return dataclasses.replace(
            self, revision=self.revision + 1, status=status, reason=reason, written_at=None
        )

    def amended(self, spec: Mapping[str, Any]) -> Revision:
        """A new revision with a new spec — and it lands in `needs_review`, always.

        An amended rule may not inherit `accepted`: that would be an edit in place
        wearing a revision number, and the whole point of the two-user workflow is
        that a change to what a rule CHECKS is judged by a person before it runs.
        """
        return dataclasses.replace(
            self,
            revision=self.revision + 1,
            spec=spec,
            status=NEEDS_REVIEW,
            reason=None,
            written_at=None,
        )


# --- The three writers. A fourth is a decision, not an addition. ---------------


def propose(table: str, etype: str, kwargs: Mapping[str, Any]) -> Revision:
    """Validate a brand-new rule and write revision 1 of it, always as `proposed`.

    The state is not a parameter. A caller that could ask for `accepted` here would
    be writing a rule into the set that executes and counts toward coverage without
    anyone having judged it — the two-user workflow made optional at its one
    entrance. `accepted` is reachable only through `set_status()`.
    """
    spec = validator.validate(etype, kwargs, table, live.columns(table))
    return _append(
        Revision(rule_id=str(uuid.uuid4()), revision=1, table=table, spec=spec, status=PROPOSED)
    )


def amend(rule_id: str, etype: str, kwargs: Mapping[str, Any]) -> Revision:
    """Validate a replacement spec and append it as the next revision of an existing rule."""
    prior = latest(rule_id)
    spec = validator.validate(etype, kwargs, prior.table, live.columns(prior.table))
    return _append(prior.amended(spec))


def set_status(rule_id: str, status: str, reason: str | None = None) -> Revision:
    """Move a rule through the workflow. Carries the spec forward; cannot change it."""
    return _append(latest(rule_id).judged(status, reason))


# --- F12's one act of judgment, over a selection that may be either kind ------


def judge_batch(
    table: str,
    specs: Sequence[Mapping[str, Any]],
    rule_ids: Sequence[str],
    status: str,
    reason: str | None = None,
) -> tuple[Revision, ...]:
    """Judge a selection in one act — unsaved proposals, stored rules, or both.

    NOT A FOURTH WRITER, and the check in `tests/test_rule_store.py` is what says so:
    nothing here appends. Each unsaved spec walks `propose()`, which hands it to
    `validate()` exactly as though a person had typed it — so a proposal that reached
    the browser as JSON and came back edited is still refused by INV-2's own door — and
    every rule, fresh or stored, is then moved by `set_status()`. The history records
    both steps, which is the honest account: the rule was proposed, and then somebody
    judged it.

    **ACCEPTING IS THE FIRST MOMENT ANYTHING IS PERSISTED** (SPEC F12). A `Proposal` has
    no id and no row; it is a line on a screen with a button under it, and this is the
    function that button reaches. Nothing upstream of here can write.

    THE TWO REFUSALS, BOTH BEFORE THE FIRST WRITE:

      the empty selection   the screen disables the control at zero, so an empty batch
                            arriving here means something got past it. Answering "fine,
                            nothing happened" would make that invisible.
      past the cap          `BULK_CAP` exists so every selected evidence line is on
                            screen at the moment of the click. Enforced here rather
                            than in the component, because a limit a client applies is
                            a limit anybody can post past.

    `judgeable()` runs before either write for the reason its own docstring gives: a
    rejection with no reason must not persist revision 1 of anything on its way to
    being refused.
    """
    selected = len(specs) + len(rule_ids)
    if not selected:
        raise ValueError(
            "a judgment with nothing selected. The control is disabled at zero on the "
            "screen, so an empty selection here is something that got past it — and "
            "answering as though it had succeeded is how that stays invisible."
        )
    if selected > BULK_CAP:
        raise ValueError(
            f"{selected} rules in one act, and the cap is {BULK_CAP}. The cap is what keeps "
            "every evidence line on screen at the moment of the click; accepting more than "
            "can be read is the one-shotting a bulk control exists to be prevented from."
        )
    judgeable(status, reason)
    fresh = [propose(table, str(spec["type"]), spec.get("kwargs") or {}).rule_id for spec in specs]
    return tuple(set_status(rule_id, status, reason) for rule_id in [*fresh, *rule_ids])


# --- Reading, and the two folds that decide what a state MEANS -----------------


def revisions(table: str | None = None, rule_id: str | None = None) -> tuple[Revision, ...]:
    """Every revision ever written, oldest first within each rule."""
    with system.cursor(DDL) as cur:
        cur.execute(system.sql(_READ), {"table": table, "rule": rule_id})
        return tuple(Revision(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in cur.fetchall())


def current(revs: Iterable[Revision]) -> tuple[Revision, ...]:
    """The newest revision of each rule — pure, so the workflow is checkable offline.

    This is where "no update in place" stops being a storage detail and becomes the
    read model: history is the whole table, the RULE is its last revision, and a
    caller that renders every row would show a rejected rule as still proposed.
    """
    newest: dict[str, Revision] = {}
    for rev in revs:
        if rev.revision >= newest.get(rev.rule_id, rev).revision:
            newest[rev.rule_id] = rev
    return tuple(newest.values())


def accepted(revs: Iterable[Revision]) -> tuple[Revision, ...]:
    """What executes, and what counts toward coverage. The same answer to both questions.

    One function for both on purpose: coverage that counts a rule which does not run
    is the specific lie this product exists to not tell.
    """
    return tuple(rev for rev in current(revs) if rev.status == ACCEPTED)


def latest(rule_id: str) -> Revision:
    """The current revision of one rule, read back from the store."""
    found = current(revisions(rule_id=rule_id))
    if not found:
        raise UnknownRule(f"no rule {rule_id!r} has ever been written to this store")
    return found[0]


# --- The one door to the table ------------------------------------------------


def _append(rev: Revision) -> Revision:
    """The only INSERT in the product. Every writer above arrives here."""
    with system.cursor(DDL) as cur:
        cur.execute(
            system.sql(_WRITE),
            (rev.rule_id, rev.revision, rev.table, Json(dict(rev.spec)), rev.status, rev.reason),
        )
        (written_at,) = cur.fetchone()
    return dataclasses.replace(rev, written_at=written_at)
