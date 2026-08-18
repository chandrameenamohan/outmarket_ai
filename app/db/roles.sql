-- SPEC §3.1's privilege split, as the DATABASE sees it (bead dq-5pb.2).
--
-- Until this ran, "the analysis path never writes to the tables under analysis"
-- was a property of OUR CODE: every statement in app/rules/store.py names
-- `{schema}.rules`, and tests/test_rule_store.py asserts that target set
-- exhaustively. A test like that proves our code does not try. It cannot prove a
-- future bug would fail if it did. These grants make the guarantee a property of
-- the CONNECTION, so PostgreSQL refuses the write whether or not we meant it.
--
-- Two login roles, and neither can do the other's job:
--
--   dq_analyst  the ANALYSIS path — app/dq/ge_runtime.py (rule execution) and
--               app/rules/schema.py (identifier validation). SELECT on the tables
--               under analysis and NOTHING else, anywhere. No INSERT, no UPDATE,
--               no DELETE, no CREATE.
--
--   dq_system   the RULE STORE — app/rules/store.py. Owns its own schema and may
--               write there. Granted nothing at all on `public`, so it is refused
--               a write to `orders` too: the store never had a reason to hold that
--               power, and "the store is well behaved" was the only thing stopping
--               it before.
--
-- WHAT THIS IS NOT: the append-only guarantee. That is store.sql's trigger, and it
-- stays a trigger precisely because it must bind the table's OWNER — dq_system —
-- for whom a REVOKE would be a no-op. Grants and the trigger answer two different
-- questions and neither substitutes for the other.
--
-- HOW TO RUN IT. There is no psql on the development machine, so the recipe is the
-- same psycopg2 the product uses. The passwords are read back out of the DSNs in
-- .env rather than typed twice, so the role and the connection string cannot drift:
--
--     set -a; . ./.env; set +a
--     python3 - <<'PY'
--     import os, pathlib, urllib.parse as u, psycopg2
--     pw = lambda k: u.urlsplit(os.environ[k]).password
--     conn = psycopg2.connect(os.environ["SUPABASE_DB_URL_DIRECT"]); conn.autocommit = True
--     conn.cursor().execute(
--         pathlib.Path("app/db/roles.sql").read_text(),
--         {"analyst_password": pw("SUPABASE_DB_URL_ANALYSIS"),
--          "system_password": pw("SUPABASE_DB_URL_SYSTEM")},
--     )
--     PY
--
-- It is applied as `postgres` — the account that owns the demo tables and holds
-- CREATEROLE — and that account's own credentials are unchanged by this file.
--
-- ponytail: `create role` is not wrapped in a DO block, so a second run stops at
-- `role "dq_analyst" already exists`. Ceiling: not idempotent from the top. That is
-- the right failure for a script that mints credentials — the guard would have to
-- quote a password into a plpgsql string literal, which is a new place for a bug in
-- the one file that hands out rights. Everything AFTER the two `create role` lines
-- is safe to re-run on its own.

-- PostgreSQL 16 narrowed what CREATEROLE hands back: the creator is granted the
-- new role WITH ADMIN OPTION but with neither SET nor INHERIT, and section 3's
-- `alter schema ... owner to dq_system` requires being able to SET ROLE to the new
-- owner. Without this line the file dies at `must be able to SET ROLE "dq_system"`
-- (observed, PostgreSQL 17.6). `set`, not `set, inherit`: `postgres` needs to hand
-- the schemas over, not to acquire the rights it is handing over.
set createrole_self_grant = 'set';

-- --------------------------------------------------------------------------
-- 1 · The analysis role. Read, and only read.
-- --------------------------------------------------------------------------
-- CONNECT and TEMP arrive from the database's grant to PUBLIC; USAGE on `public`
-- from the schema's. Neither carries a single table privilege, so a new role
-- starts with no way to read a row and no way to write one — everything this role
-- can do is on the next two lines.
create role dq_analyst login password %(analyst_password)s;

grant usage on schema public to dq_analyst;
grant select on all tables in schema public to dq_analyst;

-- `grant ... on all tables` is a snapshot, not a rule: it covers what exists now
-- and nothing seeded afterwards. F15 re-seeds as `postgres`, so the default
-- privilege is attached to `postgres` and a re-seeded `orders` is readable again
-- without anyone remembering to re-run this file.
alter default privileges for role postgres in schema public
    grant select on tables to dq_analyst;

-- --------------------------------------------------------------------------
-- 2 · The system role. Writes to its own schema and to nowhere else.
-- --------------------------------------------------------------------------
create role dq_system login password %(system_password)s;

-- CREATE on the DATABASE rather than on `public`, and this is the only grant here
-- wider than one schema. app/rules/store.py runs `create schema if not exists
-- {schema}` on connect and DQ_SCHEMA is configurable — tests/conftest.py points it
-- at a scratch schema so an append-only store never accumulates junk rules in the
-- one the demo reads. Ceiling: dq_system can create SCHEMAS of its own. It still
-- holds no privilege on any table in `public`, which is the guarantee that matters.
grant create on database postgres to dq_system;

-- That grant is what makes the SECOND scratch schema free (bead dq-cyi.4): the GE layer
-- writes `dq_check_ge` and the browser layer keeps `dq_check`, so the two can run at the
-- same time without moving each other's rule counts. `dq_check_ge` is deliberately NOT
-- created below — dq_system creates it on first connect and therefore OWNS it, which is
-- exactly the property section 3 has to hand-fix for the schemas that predate this file.
-- `make reset-scratch` drops both of them on the SYSTEM DSN for the same reason: an owner
-- does not need the owner's credentials to drop what it made.

-- Deliberately absent: any grant to dq_system on `public`. It is not a read-only
-- role there, it is a no-access role there.

-- --------------------------------------------------------------------------
-- 3 · Hand the system schemas over.
-- --------------------------------------------------------------------------
-- On a fresh database the `create` lines do the work and the `alter`s are no-ops.
-- On this one it is the other way round: `dq_check` already existed, created by
-- `postgres` before the split did, and store.sql's `create or replace function` and
-- `create trigger` both require OWNERSHIP. Both spellings are here so the file runs
-- on either, and every line below is safe to re-run.
create schema if not exists dq;
create schema if not exists dq_check;

alter schema dq       owner to dq_system;
alter schema dq_check owner to dq_system;

alter table if exists dq.rules       owner to dq_system;
alter table if exists dq_check.rules owner to dq_system;

-- The append-only trigger and its function are recreated by store.sql on the next
-- connect, then owned by dq_system. Dropping the `postgres`-owned copies is what
-- makes room for that. This drops a FUNCTION and a TRIGGER; it touches no row, and
-- the store is append-only again the moment anything connects to it.
--
-- `cascade` off the FUNCTION, not a `drop trigger` of its own: a trigger depends on
-- the function, so one line removes both — and `drop trigger if exists ... on
-- dq.rules` still raises `relation "dq.rules" does not exist` when the table is
-- absent, which is every fresh database (observed, PostgreSQL 17.6). Dropping a
-- function that is not there is a genuine no-op.
drop function if exists dq.refuse_quiet_edits() cascade;
drop function if exists dq_check.refuse_quiet_edits() cascade;
