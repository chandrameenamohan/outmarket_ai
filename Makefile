# The gate. `make check` is the only command anyone has to remember.
#
# Everything runs against tools that are already on this machine (ruff 0.6.1,
# mypy 1.19.1, pytest 7.4.3, python playwright 1.57.0 with browsers cached) plus
# web/node_modules, which `./init.sh` installs. `make check` installs nothing,
# needs no network and needs no running app — it deselects the `ge`, `e2e` and
# `live` markers, which are the three layers that would otherwise break those
# promises. (`live` spends money on a real model call; that is a fourth promise.)
#
# `check-js` is inside `check` because it earns its place: 6 s, offline, no server.
# It runs LAST because it is the slowest layer by two orders of magnitude, and the
# rule here is cheapest-fails-first. It has no `$(wildcard)` escape hatch — a
# missing web/node_modules is a broken checkout, not a tolerable state, and the
# error npm prints says so better than a hand-written guard would.
#
# `check-ge` exists now, on the condition this comment used to state: the `ge` layer
# stopped being all stubs when app/dq/ge_runtime.py landed, so the target no longer
# resolves ~40 packages from the network in order to print skips. It stays OUT of
# `check` because it needs the network, and — once the executor lands — a database.

PY := python3

# `app` does not exist yet; $(wildcard) makes the gate tolerate that instead of
# erroring on a missing path. It starts being linted the moment it appears.
# This is the PYTHON scope and stays that way — the Next app lives in web/ so that
# ruff and mypy are never pointed at TypeScript, and `check-js` at TypeScript only.
SRC := $(wildcard app) tests

.PHONY: check lint format typecheck test check-js check-ui check-ge

check: lint format typecheck test check-js

lint:
	ruff check $(SRC)

format:
	ruff format --check $(SRC)

typecheck:
	mypy $(SRC)

# The marker deselection IS the layer separation. Without it `make check`
# collects the browser, GE and billed-model layers it claims to exclude.
# `make check` must stay free to run on every save; `live` is not free.
test:
	$(PY) -m pytest -m "not ge and not e2e and not live"

# Defined once in web/package.json so the same command works from an editor.
check-js:
	npm --prefix web run check

# Browser layer only. Needs TWO running processes, and the fixtures fail (never skip)
# when either is set and silent — so a green run means a real server, not a fixture:
#
#   1. the Next app on APP_URL, started by `npm --prefix web run start`
#   2. the Python process on DQ_API_URL, which the rule screens READ (bead dq-rbf.1)
#
# The second one arrived with F14. A permalink that renders a rule's English statement,
# evidence line and actions has to read a real rule, and a frontend that rendered a
# plausible one from a fixture file is the failure VERIFICATION §10 exists to prevent.
# It needs the framework and the database, so it is started with the same `uv run` line
# the `ge` layer uses — the command is in VERIFICATION.md §1.
#
# DQ_SCHEMA=dq_check on that process is not a detail: tests/conftest.py sets the same
# scratch schema for exactly the reason stated there — the store is append-only, so a
# check that wrote to the demo's own schema could not clean up after itself.
# The layer also SOURCES ./.env, which arrived with F10 (bead dq-rbf.2). One check needs
# a run record in the middle bucket — "ran, but unverifiable" — and the shipping
# configuration cannot produce one: the row cap is off (SPEC O-2) so no run is sampled,
# and no seeded table makes a catalog rule blow up. So the condition is written into the
# SCRATCH schema through the product's own writer before the browser looks at it
# (tests/conftest.py::coverage_records), and that needs the system DSN in this process
# as well as in the two servers. Same one-liner init.sh and check-ge use, for the same
# reason: sourcing beats reimplementing a .env parser. Without it the fixture PENDS by
# name rather than failing, because a layer nobody gave credentials to was not asked for.
#
# THIS LAYER SPENDS MONEY, as of F12 (bead dq-rbf.4), and it is the only make target that
# does. Three real model calls per run — about $0.12 and ~20 s (LT-2b) — in the SERVER
# process, not this one: `?propose=1` once, shared by three checks through the five-minute
# memo in app/rules/suggest.py, plus F4's refusal and its unsaved-until-accepted promise,
# which are the product's two headline claims and cannot be proven without asking a model.
# Both of those carry the `live` mark as well as `e2e`, so `make check` still excludes them
# twice over; `-m e2e` here selects them deliberately. A gate that skipped them would leave
# F12's centrepiece checked by nothing.
#
# SPEC §7's scenario (bead dq-cyi.2) DOUBLES that — three more calls, so about $0.24 and
# 6 min 16 s for the whole target. It also starts TWO MORE PROCESSES of its own, on free
# ports, against a store schema it drops first: §7 opens on "no rules exist" and the shared
# store is append-only, so the flow cannot run on the two servers above. It needs nothing
# from this recipe beyond ./.env and the ports below being alive — see VERIFICATION.md §4.6.
check-ui:
	set -a; [ -f ./.env ] && . ./.env; set +a; \
	APP_URL=$(or $(APP_URL),http://localhost:3000) \
	DQ_API_URL=$(or $(DQ_API_URL),http://localhost:8000) \
	  $(PY) -m pytest -m e2e

# Great Expectations layer. Needs the NETWORK (uv resolves an ephemeral env) and,
# as of the compiler (F7), a reachable database. `--with pytest` and `--no-project`
# are both load-bearing: uv's ephemeral env does not inherit site-packages, and
# without the second uv writes a `.venv/` and an unwanted `uv.lock` into the repo.
#
# `. ./.env` is the same one-liner init.sh uses, for the same reason: sourcing beats
# reimplementing a .env parser. Without it the layer's checks fail on a missing DSN
# — which is correct behaviour and a rotten way to greet someone running the target.
#
# `psycopg[binary]` is psycopg 3 and is NOT a duplicate of psycopg2-binary: the seed
# checks (F15) re-run seed/seed_demo_data.py itself, which imports psycopg 3, in a
# subprocess of THIS interpreter — and an ephemeral env inherits no site-packages.
#
# RUN THIS ALONE, NOT ALONGSIDE `check-ui`. Both layers pin DQ_SCHEMA=dq_check and both
# WRITE to it, and the store is append-only (F6) — so a check that counts rules before
# and after an action is reading a number the other layer is also moving. Running the two
# concurrently took BOTH red at close-out with nothing wrong with either; the numbers and
# the reasoning are in VERIFICATION.md 4.7.2, and bead dq-cyi.4 owns giving them a schema
# each. This is a comment rather than a lock because a lock in a Makefile is a second
# thing to get wrong, and the two targets are minutes long and run deliberately.
check-ge:
	set -a; . ./.env; set +a; \
	uv run --no-project --with pytest --with great-expectations --with 'sqlalchemy>=2' \
	  --with psycopg2-binary --with 'psycopg[binary]' $(PY) -m pytest -m ge
