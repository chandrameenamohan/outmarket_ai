#!/usr/bin/env bash
# Boot the dev environment and smoke test it: credentials → database → app build → gate.
# Idempotent and safe to run on every session start. It installs and builds the Next
# app, because that is the one thing a fresh clone cannot do for itself and the gate
# now depends on — `npm install` and `next build` are both no-op-shaped once warm.
#
#   ./init.sh
#
# There are no skip knobs. Every step below either matters or would not be here,
# and a boot script whose last line says "ready." must mean it.
set -euo pipefail
cd "$(dirname "$0")"   # every script here reads ./.env relative to CWD; do not remove

say() { printf '\n\033[1m── %s\033[0m\n' "$*"; }
ok()  { printf '   ok   %s\n' "$*"; }
die() { printf '\n\033[1;31mFAILED: %s\033[0m\n\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
say "credentials"
# ---------------------------------------------------------------------------
# .env is gitignored and therefore ABSENT from every fresh clone and every git
# worktree. That has already cost time, so fail here with the fix, not later
# with a FileNotFoundError from inside a script.
if [ ! -f .env ]; then
  die "no .env in $(pwd)

  .env is gitignored, so a fresh clone or a git worktree will not have one.
    from a worktree : cp ../../../.env .env      (adjust depth to reach the main checkout)
    from scratch    : cp .env.example .env       then fill in the real values
  Required keys are listed in .env.example."
fi

# The three DSNs this script and the app actually connect with. Each is checked for
# a NON-EMPTY value and for the .env.example placeholders, because a plain
# `grep '^KEY='` passes on the blank/placeholder file `cp .env.example .env` leaves.
#
# ANALYSIS and SYSTEM are the privilege split of SPEC §3.1 (app/db/roles.sql) and
# are as required as DIRECT: an .env carrying only DIRECT is a pre-split .env, and
# every application module would die on a missing key one confusing layer later.
for key in SUPABASE_DB_URL_DIRECT SUPABASE_DB_URL_ANALYSIS SUPABASE_DB_URL_SYSTEM; do
  grep -qE "^${key}=.." .env || die "$key missing or empty in .env  (see .env.example)

  ANALYSIS and SYSTEM are minted by app/db/roles.sql — read its header for the
  command that creates the roles and the grants each one gets."
  ! grep -qE "^${key}=.*(:PASSWORD@|\.PROJECT\.)" .env \
    || die "$key still contains the .env.example placeholders — fill in the real values"
  ok "$key present"
done

# ---------------------------------------------------------------------------
say "smoke: database"
# ---------------------------------------------------------------------------
# Sourcing beats reimplementing a .env parser in this script; all values here are
# shell-safe URLs. (The Python copies in learning-tests/ and seed/ stay as they
# are — those are Python scripts with no shell around them.)
set -a; . ./.env; set +a

python3 - <<'PY' || die "database smoke failed (see error above)"
import os

import psycopg

# seed/MANIFEST.md — the three tables everything downstream assumes exist.
TABLES = ("customers", "orders", "payments")

# Opened as the ANALYSIS role, not as the owner. A table `postgres` can see but
# `dq_analyst` cannot is invisible to the whole product, so this smoke test asks
# the role that will actually do the reading (SPEC §3.1, app/db/roles.sql).
with psycopg.connect(os.environ["SUPABASE_DB_URL_ANALYSIS"], connect_timeout=15) as c:
    ver = c.execute("select version()").fetchone()[0].split(",")[0]
    who = c.execute("select current_user").fetchone()[0]
    present = {
        r[0]
        for r in c.execute(
            "select table_name from information_schema.tables where table_schema='public'"
        ).fetchall()
    }

# One round trip, purely to prove the second credential is the one it claims to be.
# A SYSTEM DSN holding the owner's password would pass every check above and quietly
# undo the split.
with psycopg.connect(os.environ["SUPABASE_DB_URL_SYSTEM"], connect_timeout=15) as c:
    sysuser = c.execute("select current_user").fetchone()[0]

missing = [t for t in TABLES if t not in present]
if missing:
    raise SystemExit(
        f"   connected as {who}, but the seeded tables are missing: {missing}\n"
        f"   run: python3 seed/seed_demo_data.py"
    )
if (who, sysuser) != ("dq_analyst", "dq_system"):
    raise SystemExit(
        f"   the split DSNs connect as ({who}, {sysuser}), not (dq_analyst, dq_system).\n"
        f"   SUPABASE_DB_URL_ANALYSIS / _SYSTEM must carry the roles app/db/roles.sql creates."
    )
print(f"   ok   {ver}  ·  {', '.join(TABLES)} present  ·  as {who} / {sysuser}")
PY

# ---------------------------------------------------------------------------
say "build: app"
# ---------------------------------------------------------------------------
# The Next app is in web/, NOT app/. `app/` is the Python package the gate lints
# (Makefile SRC, VERIFICATION.md §3) — pointing mypy at a TypeScript tree would
# only teach people to narrow SRC. Both toolchains stay in their own language.
#
# Idempotent by npm's own design: with the committed package-lock.json and a warm
# node_modules this is a sub-second no-op, and on a fresh clone it is the install.
npm --prefix web install --no-audit --no-fund --silent \
  || die "npm install failed in web/ (see error above)"
ok "web/node_modules"

# The browser layer screenshots and diffs this app (VERIFICATION.md §4.3), so it
# drives the PRODUCTION build — a dev server paints a different page. Turbopack
# reuses web/.next/cache, so a rebuild with nothing changed is a few seconds.
#
# This script does NOT boot the app to prove it serves. That was 22 lines buying a
# fact already bought twice: `next build` prerenders all seven routes, so a page
# that throws fails one step earlier, right here; and conftest's `app_url` fixture
# FAILS — never skips — when APP_URL has nothing answering, at the only moment it
# matters. Worse, the version that reused whatever was already on the port proved
# liveness and not identity: a stale `next start` holding 3000 from an older build
# satisfied it, and the whole browser layer went green against an artifact no
# longer on disk. A boot script must not print `ok` for a process it cannot name.
npm --prefix web run build --silent \
  || die "next build failed (see error above)"
ok "web/.next"

# ---------------------------------------------------------------------------
say "gate"
# ---------------------------------------------------------------------------
# No toolchain preflight: `make check` reports a missing tool itself, two seconds
# from now, and it cannot drift out of date the way a hand-listed loop does.
make check

printf '\n\033[1mready.\033[0m  next: bd ready'
printf '\n         run the app: npm --prefix web run start   then: make check-ui\n\n'
