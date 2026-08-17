# AI-Powered Data Quality Assistant

A domain expert states an expectation in plain English. The system turns it into a Great
Expectations check it has already proven will run, executes it against a PostgreSQL table,
and reports the failures in the same language the expectation was written in.

Two users, one URL. An **engineer** sees the tables, the coverage and the Great Expectations
configuration; a **domain expert** sees the same product with the framework removed and never
encounters a table list. Role is a view you choose on entry and the device remembers — not an
account, not a route.

- The spec, with observable acceptance for every feature: [`SPEC.md`](./SPEC.md)
- How it is checked, and what is deliberately not checked: [`VERIFICATION.md`](./VERIFICATION.md)
- What was measured before anything was built: [`learning-tests/FINDINGS.md`](./learning-tests/FINDINGS.md)
- The state of the work, for whoever picks it up next: [`HANDOFF.md`](./HANDOFF.md)

---

## Run it

SPEC §3 promises two ways in: a deployed URL and one command on your own machine. **Only the second
one exists today.** There is no deployed URL, and this file will not pretend there is: the check for
one is written and pends by name on every run (`DEPLOYED_APP_URL is unset — no deployment was
named`), and it fails rather than skips the moment that variable points at something silent. Bead
`dq-cyi.1` owns standing one up. So: the command below is the way in.

```bash
git clone <this repo> && cd outmarket_ai
cp .env.example .env          # then fill it in — see "Credentials", below
docker compose up --build     # first build ~2 min; then open http://localhost:3000
```

That is the whole ritual. There is no database to install: the stack talks to the PostgreSQL
instance your `.env` points at.

Stop it with `Ctrl-C`, or `docker compose down`.

**Requirements:** Docker with Compose v2 (`docker compose version` ≥ 2.20), and a reachable
PostgreSQL 17 database — see the two sections after the next one if yours is empty.

**Ports.** The stack publishes **3000** (the app) and **8000** (the Python process). If either
is taken on your machine, name a different one on the host side; nothing inside the containers
moves:

```bash
DQ_WEB_HOST_PORT=3100 DQ_API_HOST_PORT=8100 docker compose up --build
```

---

## Credentials

**Everything comes from the environment. Nothing is baked into an image, nothing is committed,
and nothing is ever typed into the UI** (SPEC §3.1). `.env` is gitignored *and* in
`.dockerignore`, so a `docker build` cannot capture one by accident; `docker-compose.yml` hands
the file to the running container instead, which is a different thing — an image layer travels
to whoever pulls it, a container environment does not.

Copy [`.env.example`](./.env.example) to `.env` and fill in **four** values. The first three are
required; the fourth is required for the two features that ask a model anything.

| Variable | What it is | Who reads it |
|---|---|---|
| `SUPABASE_DB_URL_DIRECT` | PostgreSQL as the **owner**, port 5432 | `seed/seed_demo_data.py`, `init.sh`'s smoke, `app/db/roles.sql`. **No application module reads it** — that is the point of the split |
| `SUPABASE_DB_URL_ANALYSIS` | the same database as **`dq_analyst`** | the analysis path: profiling, identifier validation, rule execution |
| `SUPABASE_DB_URL_SYSTEM` | the same database as **`dq_system`** | the rule store and the run records — and nothing else, anywhere |
| `CLAUDE_CODE_OAUTH_TOKEN` | a Claude subscription token (`claude setup-token`) | `app/model.py`, the one module that talks to a model |

Two more are optional and both have working defaults: `DQ_SCHEMA` (where the system's own rules
and run records live; defaults to `dq`) and `SUPABASE_DB_URL_POOLED` (kept for comparison runs
only — F8 does not use it).

### The two roles, and what to run if they do not exist

`dq_analyst` and `dq_system` are the SPEC §3.1 privilege split **as the database enforces it**,
not as our code promises it. `dq_analyst` holds `SELECT` on the tables under analysis and no
other privilege anywhere, so a write to `orders` is refused by PostgreSQL rather than by us.
`dq_system` owns the system schema and is granted nothing at all on `public`, so the rule store
is refused that write too.

They are minted by [`app/db/roles.sql`](./app/db/roles.sql), applied as the owner. If your
database does not have them yet, run it **inside the api image you already built** — no local
Python needed:

```bash
docker compose run --rm --entrypoint python3 api - <<'PY'
import os, pathlib, urllib.parse as u, psycopg2
pw = lambda k: u.urlsplit(os.environ[k]).password
conn = psycopg2.connect(os.environ["SUPABASE_DB_URL_DIRECT"]); conn.autocommit = True
conn.cursor().execute(
    pathlib.Path("app/db/roles.sql").read_text(),
    {"analyst_password": pw("SUPABASE_DB_URL_ANALYSIS"),
     "system_password": pw("SUPABASE_DB_URL_SYSTEM")},
)
print("roles minted")
PY
```

The passwords are read back out of the DSNs you already wrote, so the role and the connection
string cannot drift apart. The file is **not** idempotent from the top — a second run stops at
`role "dq_analyst" already exists`, which is the right failure for a script that hands out
rights; everything after the two `create role` lines is safe to re-run on its own.

### If the demo tables are missing

The product expects `customers`, `orders` and `payments` in `public` —
[`seed/MANIFEST.md`](./seed/MANIFEST.md) describes the 500,000-row dataset and the defects
seeded into it on purpose. Same trick, same image:

```bash
docker compose run --rm --entrypoint python3 api seed/seed_demo_data.py
```

---

## The IPv6 trap

**Read this before concluding the stack is broken.** It cost this project real time and it will
bite anyone running the containers against a Supabase direct connection.

Supabase publishes `db.<project-ref>.supabase.co` with **AAAA records only** — there is no A
record. A host with no IPv6 route cannot reach it, and **Docker Desktop gives containers no IPv6
route by default**, so the symptom is confusing: `psql` works fine from your laptop and the api
container dies at boot.

**How to detect it.** Two commands, in order:

```bash
docker compose logs api | grep -i "network is unreachable"
docker run --rm alpine getent ahosts db.<project-ref>.supabase.co
```

The first prints the diagnosis verbatim if this is your problem —

```
psycopg2.OperationalError: connection to server at "db.<ref>.supabase.co"
(2406:da18:1691:a200::1a6e), port 5432 failed: Network is unreachable
```

— an IPv6 literal in the parentheses and nothing else. The second confirms the cause: a
container resolves the name to an IPv6 address it has no way to reach.

**What to do.** Point the three DSNs at Supabase's **session pooler**, which is IPv4 and, like
the direct connection, holds one server connection per client for the life of the session. In
the Supabase dashboard it is *Project Settings → Database → Connection string → Session pooler*.
Two things change and nothing else does:

| | direct | session pooler |
|---|---|---|
| host | `db.<ref>.supabase.co` | `aws-0-<region>.pooler.supabase.com` |
| user | `postgres` / `dq_analyst` / `dq_system` | `postgres.<ref>` / `dq_analyst.<ref>` / `dq_system.<ref>` |
| port | 5432 | **5432** |

```
SUPABASE_DB_URL_ANALYSIS=postgresql://dq_analyst.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

**Port 5432, not 6543.** 6543 is the *transaction* pooler, and LT-1b measured it **21% slower**
on identical work — 17.94 s against 14.84 s for the ten-rule suite — because a rule run is a few
long analytical statements on one connection, the shape a transaction pooler helps least.

**The code's default is unchanged, deliberately.** `SUPABASE_DB_URL_DIRECT` still means the
direct connection, and F8 still uses it, because LT-1b chose it on measurement
(`learning-tests/FINDINGS.md` § LT-1b). What moves is the value in *your* `.env`, on the hosts
that need it. If your Docker daemon does have working IPv6 egress, change nothing.

---

## Developing without Docker

The containers are the delivery path, not the development one. On a machine with Python 3.12,
Node 22 and the tools `make check` names:

```bash
./init.sh                        # credentials -> database smoke -> npm install + next build -> make check
make check                       # the gate: lint, format, typecheck, tests, eslint + tsc. ~6 s, offline, no server
```

Then two processes, which is what the browser layer drives:

```bash
set -a; . ./.env; set +a
DQ_SCHEMA=dq_check uv run --no-project --with great-expectations --with 'sqlalchemy>=2' \
  --with psycopg2-binary python3 -m app.api.server      # :8000
DQ_API_URL=http://localhost:8000 npm --prefix web run start   # :3000

make check-ui                    # the browser layer, against both of the above
```

`VERIFICATION.md` §1 is the authority on all of it, including the two layers that cost money or
need the network and are therefore outside `make check`.

### Checking a delivered stack

The two delivery paths are checked by the smoke that already exists rather than by a new one —
`tests/e2e/test_delivery.py` points `tests/e2e/test_ui_hygiene.py` at whichever stack you name.
Unset means "not asked for" and pends; named but silent is a failure, never a skip.

```bash
docker compose up --build -d
COMPOSE_APP_URL=http://localhost:3000 COMPOSE_API_URL=http://localhost:8000 make check-ui
DEPLOYED_APP_URL=https://... DEPLOYED_API_URL=https://... make check-ui
```

It needs a store holding at least one rule for `orders` — `conftest.rule_id` fails rather than
skips on an empty one, because a permalink check satisfied by an empty database would be a green
tick over nothing. Propose and accept a rule through the UI first, or point `DQ_SCHEMA` at a
schema that already has one.

---

## What the two images are

| | base | what it runs | why it is that size |
|---|---|---|---|
| `Dockerfile.api` | `python:3.12-slim` | `python3 -m app.api.server` — the one process holding the single Great Expectations context (INV-3) and streaming a run's verdicts as they land (F8) | Great Expectations brings pandas; `app/model.py` needs a Node runtime because the Claude Agent SDK *spawns* the `claude` binary rather than calling an API |
| `Dockerfile.web` | `node:22-slim` | `next start` — every screen is server-rendered, so the browser never talks to Python: no CORS, no second origin, no API URL in the bundle | `npm ci` from the committed lockfile, then `next build` |

Both build from a **clean checkout**: nothing copies this machine's `node_modules`, `.next`,
`.venv` or Playwright cache, and `.dockerignore` says so explicitly.

One `api` per stack, deliberately — `gx.get_context()` installs a process-global project
(INV-3), so `--scale api=2` is not a supported thing to do.
