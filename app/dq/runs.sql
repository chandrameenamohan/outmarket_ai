-- The run record store: F9's cache, and the reason a reload costs nothing.
--
-- One row per COMPLETED run. It is written once and never touched again, so the
-- three guarantees below are the DATABASE's rather than app/dq/runs.py's.
--
-- 1 · APPEND-ONLY, by trigger, exactly as {schema}.rules is. Re-running a table
--     appends a new record under a new id and every earlier one stays readable;
--     there is no UPDATE anywhere that could turn a stored run into a different
--     run after the fact. Same argument as the rule store (app/rules/store.sql):
--     the connection that runs this file OWNS the table, and a REVOKE against an
--     owner is a no-op, so privilege cannot do this job. The trigger is FOR EACH
--     STATEMENT, so a DELETE matching nothing is refused too.
--     This file and app/rules/store.sql are the only two under app/ that say the
--     words UPDATE, DELETE and TRUNCATE, and both say them as a refusal — which is
--     what makes the scan in tests/test_rule_store.py precise.
--
-- 2 · THE STATUS SET IS TERMINAL, as a CHECK constraint. The three values are the
--     verdict vocabulary of app/dq/status.py, rolled up over the run's rules.
--     There is deliberately no `running` value: execution is synchronous and
--     progressive (SPEC O-3), so a run in flight lives in the caller and only a
--     completed run is written down. A row here is a finished fact.
--     app/dq/runs.py::RUN_STATUSES says the same three, and
--     tests/test_run_records.py fails the gate if the two ever disagree.
--
-- 3 · THE SAMPLING MARKER IS A PAIR OF COLUMNS, NOT AN INFERENCE (INV-5).
--     `scanned_rows` and `total_rows` come from the ASSET DEFINITION, carried by
--     app/dq/normalise.py::Scan from the module that built the batch. Great
--     Expectations records nothing that distinguishes a capped run from an honest
--     run over a smaller table (LT-1a), so a record that lost them could never get
--     them back. Both are NOT NULL and the constraint says a scan is a subset of
--     the table rather than a second measurement of it — so a run cannot be
--     recorded without saying what it saw. No cap ships at this scale (SPEC O-2),
--     so the two are equal today: switching a cap on changes a value, not a shape.
--
-- What is NOT here: any Great Expectations configuration, and any per-rule column.
-- `results` is the normalised list app/dq/normalise.py::Result.record() produces,
-- rendered atom and raw framework output included, stored as one jsonb document
-- because it is read whole, by one screen, and never queried across. The columns
-- beside it are exactly app/dq/run.py::completed()'s payload keys, so a record
-- neither drops anything the run said nor recomputes anything on the way back.
--
-- ponytail: no retention policy and no index but the one below. Records accumulate
-- and only the newest per table is ever read. Ceiling: the day run history becomes
-- a feature (an explicit non-goal today) this table already holds it; the day it
-- becomes too big to keep, pruning it needs a change to the trigger above, which
-- is exactly the conversation deleting a run record should require.

create schema if not exists {schema};

create table if not exists {schema}.runs (
    record_id   uuid        primary key,
    table_name  text        not null,
    status      text        not null
                check (status in ('passed', 'failed', 'errored')),

    -- INV-5's two numbers, carried from the asset definition (see 3 above).
    scanned_rows bigint     not null check (scanned_rows >= 0),
    total_rows   bigint     not null check (total_rows >= scanned_rows),

    -- How many of the run's rules actually checked the data. An errored rule is
    -- excluded (app/dq/normalise.py::coverage), so this is a smaller number than
    -- the length of `results` whenever a rule could not run — and it is stored
    -- rather than recounted on read, because a reader recomputing it would have to
    -- know that rule about the third state too.
    coverage     integer    not null check (coverage >= 0),

    results     jsonb       not null check (jsonb_array_length(results) > 0),

    -- The database owns the clock, as it does for a rule revision: a record's time
    -- is when the row landed, never what the process that built it believed.
    finished_at timestamptz not null default now()
);

-- The only shape of query this table serves: the most recent record per table —
-- for one table (_READ) or for all of them at once (_READ_ALL, bead dq-z4k).
create index if not exists runs_newest_per_table
    on {schema}.runs (table_name, finished_at desc);

create or replace function {schema}.refuse_run_edits() returns trigger
language plpgsql as $$
begin
    raise exception
        'a run record is a record of what happened: % refused. Re-running a table appends a '
        'new record with a new id, and every earlier one stays readable (F9).',
        tg_op;
end;
$$;

drop trigger if exists runs_are_append_only on {schema}.runs;

create trigger runs_are_append_only
    before update or delete or truncate on {schema}.runs
    for each statement execute function {schema}.refuse_run_edits();
