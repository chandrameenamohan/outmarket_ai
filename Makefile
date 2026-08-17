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

# Browser layer only. Needs a RUNNING app: the `app_url` fixture GETs APP_URL and
# FAILS (never skips) when nothing answers, so a green run means a real server.
check-ui:
	APP_URL=$(or $(APP_URL),http://localhost:3000) $(PY) -m pytest -m e2e

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
check-ge:
	set -a; . ./.env; set +a; \
	uv run --no-project --with pytest --with great-expectations --with 'sqlalchemy>=2' \
	  --with psycopg2-binary --with 'psycopg[binary]' $(PY) -m pytest -m ge
