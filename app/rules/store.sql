-- The rule store. One table, and three guarantees the DATABASE makes about it —
-- not app/rules/store.py, and not a code review.
--
-- The reason it is SQL in a file rather than strings in Python: these are the
-- guarantees a reviewer has to be able to read, and the check that says
-- app/rules/store.py contains no UPDATE and no DELETE anywhere is only precise
-- if the one statement that says the words "update" and "delete" lives here,
-- where it is the refusal rather than a route to one.
--
-- 1 · APPEND-ONLY, enforced by a trigger rather than by a role grant. The role
--     split in app/db/roles.sql is real now and still cannot do this job: the
--     connection that runs this file OWNS the table, and a REVOKE against an
--     owner is a no-op. Grants stop the store reaching `orders`; only the trigger
--     stops it rewriting its own history.
--     The trigger refuses UPDATE, DELETE and TRUNCATE from every
--     role including the one that owns the table, so "there is no way to edit a
--     rule quietly" is a fact about the database (F6). It is FOR EACH STATEMENT,
--     so a DELETE matching nothing is refused too — the refusal does not depend
--     on which rows happen to be there.
--
-- 2 · THE FOUR STATES ARE A CHECK CONSTRAINT. `app/rules/store.py::STATES` says
--     the same four; tests/test_rule_store.py fails the gate if the two lists
--     ever disagree, because a state the dataclass allows and the database
--     refuses is an error nobody sees until a user clicks the button.
--
-- 3 · A REJECTION CARRIES ITS REASON. Also a constraint, for the same reason: a
--     rejected rule with no reason is the one row in this table that would waste
--     the next person's afternoon.
--
-- What is NOT here: any Great Expectations configuration. The stored spec is ours
-- — `{"type": ..., "kwargs": {...}}` — and the suite is compiled on demand by
-- app/dq/ge_runtime.py (INV-3, F6). Nothing in this schema is written by the
-- framework or read back into it.
--
-- ponytail: `{schema}` is substituted by str.format, guarded by a name regex in
-- store.py rather than by psycopg2.sql.Identifier. Ceiling: the schema name has
-- to be a bare lowercase identifier. Upgrade path is Identifier composition per
-- statement, which is four lines of quoting to buy a quoted schema name nobody
-- has asked for. There is no migration tool either: this script is idempotent and
-- runs on connect, so a SHAPE change needs a hand-written ALTER here.

create schema if not exists {schema};

create table if not exists {schema}.rules (
    rule_id    uuid        not null,
    revision   integer     not null check (revision >= 1),
    table_name text        not null,
    spec       jsonb       not null,
    status     text        not null
               check (status in ('proposed', 'needs_review', 'accepted', 'rejected')),
    reason     text        check (reason is null or length(btrim(reason)) > 0),
    written_at timestamptz not null default now(),

    -- Identity is (rule, revision). It is also the concurrency control: two
    -- amendments racing on the same rule produce the same next revision number,
    -- and the database refuses the second instead of losing it.
    primary key (rule_id, revision),

    constraint a_rejection_carries_its_reason
        check (status <> 'rejected' or reason is not null)
);

create or replace function {schema}.refuse_quiet_edits() returns trigger
language plpgsql as $$
begin
    raise exception
        'the rule store is append-only: % refused. A rule is amended or judged by '
        'appending a new revision, and every earlier one stays readable (F6, INV-2).',
        tg_op;
end;
$$;

drop trigger if exists rules_are_append_only on {schema}.rules;

create trigger rules_are_append_only
    before update or delete or truncate on {schema}.rules
    for each statement execute function {schema}.refuse_quiet_edits();
