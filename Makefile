# The gate. `make check` is the only command anyone has to remember.
#
# Everything runs against the tools that are ALREADY installed on this machine
# (ruff 0.6.1, mypy 1.19.1, pytest 7.4.3, python playwright 1.57.0 with browsers
# cached). `make check` installs nothing, needs no network and needs no running
# app — it deselects the `ge` and `e2e` markers, which are the two layers that
# would otherwise break exactly those promises.
#
# There is no `check-ge` target on purpose: all three `ge` checks are still stubs,
# so a target would resolve great-expectations from the network in order to print
# three skips. The exact (verified) `uv run` command lives in VERIFICATION.md §1
# and comes back as a target the day one of those checks stops being a stub.

PY := python3

# `app` does not exist yet; $(wildcard) makes the gate tolerate that instead of
# erroring on a missing path. It starts being linted the moment it appears.
SRC := $(wildcard app) tests

.PHONY: check lint format typecheck test check-ui

check: lint format typecheck test

lint:
	ruff check $(SRC)

format:
	ruff format --check $(SRC)

typecheck:
	mypy $(SRC)

# The marker deselection IS the layer separation. Without it `make check`
# collects the browser and GE layers it claims to exclude.
test:
	$(PY) -m pytest -m "not ge and not e2e"

# Browser layer only. Needs a RUNNING app: the `app_url` fixture GETs APP_URL and
# FAILS (never skips) when nothing answers, so a green run means a real server.
check-ui:
	APP_URL=$(or $(APP_URL),http://localhost:3000) $(PY) -m pytest -m e2e
