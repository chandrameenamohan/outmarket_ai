# VERIFICATION — the back-pressure harness

**Status:** designed and scaffolded · Step 4 of `software_development_workflow.md`
**Runs today:** `make check` exits 0 with **7 real assertions passing and 28 loud `PENDING` skips**
(52 deselected — 49 browser checks and 3 GE checks, which belong to the layers below).
**`make check-ui` runs those 49 against the booted app in 22 s: 3 hygiene checks over 7 routes
(21 cases) and 28 `PENDING`** — console-clean, layout stability and accessibility are real on all
seven routes (§4.2, §4.4, §4.5); everything waiting on rules, runs or results still pends by name.
**Nothing in this harness is blocked on a learning test any more.** LT-1b (bead `dq-e1d`) landed and
settled SPEC **O-2** and **O-3**; §9 records what it settled and what each settled thing now checks.

This document is the contract for what "done" means. The rule it exists to enforce is short:

> A check that passes without verifying anything is worse than no check. Every stub in this
> harness therefore **skips with a reason beginning `PENDING —`**, printed on every run by
> `pytest -ra`. There is exactly one helper that can produce a stub (`tests/conftest.py::pending`)
> and no other route to one — **enforced**, not asserted: `test_code_quality_thresholds.py` fails
> the gate on a `test_` body that neither asserts nor pends (async bodies included — an
> `AsyncFunctionDef` is not a `FunctionDef`, and missing that is how an empty async test slips
> through *and* gets skipped for want of a plugin), on any `pytest.skip` / `mark.skip` /
> `mark.skipif` / `mark.xfail` / `pytest.xfail` / `pytest.importorskip` outside `conftest.py`,
> on `from pytest import skip|xfail|importorskip` in any form, and on an `async def test_` at all.

---

## 1. One command

```bash
make check
```

Composes five layers, in the order that fails cheapest first:

| # | Layer | Invoked as | Tool | Installed today? |
|---|---|---|---|---|
| 1 | lint | `ruff check $(SRC)` | ruff 0.6.1 | yes |
| 2 | format | `ruff format --check $(SRC)` | ruff 0.6.1 | yes |
| 3 | typecheck | `mypy $(SRC)` | mypy 1.19.1 | yes |
| 4 | tests | `python3 -m pytest -m "not ge and not e2e"` | pytest 7.4.3 | yes |
| 5 | js lint + typecheck | `npm --prefix web run check` | eslint 9 + tsc 5 (`eslint-config-next` 16.3.1) | yes, in `web/node_modules` — `./init.sh` installs it |

`SRC = $(wildcard app) tests`. `app/` does not exist yet; `$(wildcard)` makes the gate tolerate
that rather than erroring on a missing path, and `app/` starts being linted the moment it
appears. **`make check` installs nothing, needs no network and needs no running app.**

**Where the two languages live.** `SRC` is the *Python* scope and stays exactly as written —
narrowing it is a regression (bead `dq-5pb.1`). The Next application therefore lives in **`web/`,
not `app/`**: `app/` is reserved for the Python package this whole document already names
(`app/dq/ge_runtime.py`, `app/rules/validator.py`, `app/rules/catalog.json` — §5), it is what
`pyproject.toml` declares as isort first-party, and `mypy app` on a directory holding only
TypeScript fails outright with *"there are no .py[i] files in directory"*. One directory per
toolchain means neither linter is ever pointed at a language it cannot read, and no one is ever
tempted to add an exclude to make the gate quiet.

Layer 5 is *inside* `make check` because it meets the bar the other four meet: **6 s, offline, no
running app.** It runs last because it is the slowest by two orders of magnitude and the ordering
rule here is cheapest-fails-first. Three details in `web/package.json` are load-bearing rather than
stylistic — and this is their one home, now that `web/package.json`'s prose `"//"` key restating
the same two facts has been deleted:

- **`eslint --max-warnings 0`.** eslint reports most findings — including
  `@typescript-eslint/no-unused-vars`, the dead-code signal ruff gives us for free on the Python
  side — as *warnings*, and exits 0. Without the flag the lint half of layer 5 can never go red.
  Verified by appending an unused `const` and watching `make check` fail (exit 2).
- **`next typegen && tsc --noEmit`, in that order.** `next-env.d.ts` `import`s
  `./.next/types/routes.d.ts`, so bare `tsc` fails on any checkout that has never been built.
  `typegen` generates those route types without a full build, which keeps the typecheck layer
  independent of the build layer.
- **`NEXT_TELEMETRY_DISABLED=1` on every `next` script.** Next phones home on build by default;
  the flag is what makes "needs no network" true rather than nearly true.

That last sentence is a promise, so the marker deselection in layer 4 *implements* it rather than
trusting it: `-m "not ge and not e2e"` is what keeps `make check` from collecting a layer that
would launch a browser or import a framework the base interpreter does not have. Two layers are
therefore deliberately *outside* it:

```bash
make check-ui     # APP_URL=http://localhost:3000 pytest -m e2e
                  # needs a RUNNING app. The app_url fixture GETs it and FAILS when nothing
                  # answers — this target may never report success against a dead server.

# The GE layer has no make target: all three `ge` checks are still `pending()` stubs, so a
# target would resolve ~40 packages from the network in order to print three skips. The
# command, last verified working on 2026-08-16 (2 skipped, 66 deselected — there were two
# `ge` checks then; the third arrived with LT-1b and the command has not been re-run since):
uv run --no-project --with pytest --with great-expectations --with 'sqlalchemy>=2' \
  --with psycopg2-binary python3 -m pytest -m ge
```

`--with pytest` and `--no-project` are both load-bearing: uv's ephemeral env does not inherit
site-packages (without the first it dies with `ModuleNotFoundError: No module named 'pytest'`),
and without the second uv runs in project mode and writes `.venv/` and an unwanted `uv.lock`
into the repo root. It goes back into the Makefile the day one of those three checks stops being
a stub.

`make check` staying installation-free and app-free is what makes it runnable on every save.
The heavier layers run before a commit and in the end-to-end scenario (SPEC §7).

### Boot ritual

```bash
./init.sh                 # credentials → database smoke → app install+build → make check
```

Idempotent, safe on every session start, and **no skip knobs** — a boot script whose last line
says `ready.` has to mean it. Four things it does that a friendlier script would not:

- **Fails loudly with the fix when `.env` is missing.** `.env` is gitignored and therefore absent
  from every fresh clone and every git worktree, which has already cost time on this project.
- **Requires a non-empty, non-placeholder `SUPABASE_DB_URL_DIRECT`** — the one key it and the gate
  actually read. `cp .env.example .env` produces a file that satisfies a bare `grep '^KEY='`, so
  the check is `grep -qE '^KEY=..'` plus a rejection of the `:PASSWORD@` / `.PROJECT.` literals.
  `SUPABASE_DB_URL_POOLED` and `CLAUDE_CODE_OAUTH_TOKEN` are documented in `.env.example` but not
  required here: nothing inside the gate reads them, and a boot gate that blocks on keys no code
  consumes is one people learn to bypass.
- **Asserts the seeded tables exist**, not merely that a connection opened. `customers`, `orders`
  and `payments` (seed/MANIFEST.md) must be present in `public`, or it dies naming the seeder. An
  empty database is not a working data layer.
- **Installs and builds the Next app**, because that is the one thing a fresh clone cannot do for
  itself and the gate now depends on: `npm --prefix web install` then `npm --prefix web run build`,
  both no-op-shaped once warm, both `die` loudly on failure. It deliberately does **not** boot a
  server to prove one serves. An earlier version did — 22 lines of background PID, EXIT trap and
  poll — and it bought a fact already bought twice: `next build` prerenders all seven routes, so a
  page that throws fails at the build one step earlier, and conftest's `app_url` fixture FAILS
  (never skips) when `APP_URL` has nothing answering, at the only moment it matters. Worse, its
  reuse branch printed `ok … already answering — reusing it` on **liveness, not identity**: a stale
  `next start` holding port 3000 from a previous build satisfied it, and the entire browser layer
  then went green against an artifact no longer on disk — which is exactly how a visual baseline
  gets approved against the wrong thing. Starting the server is one line the closing message
  prints; `APP_URL` remains the contract `make check-ui` and `app_url` read.

The header's original claim — *installs nothing, creates nothing* — was true only while there was
nothing to install. It is now false and has been rewritten rather than left to rot: a fresh clone
has no `web/node_modules` and no `web/.next`, and the alternative (dying with *"run npm install,
then run me again"*) turns one command into a three-round ritual for no gain. **Warm cost 12.0 s,
measured 2026-08-16**; cold adds the `npm install` and the first uncached `next build` on top.

There is no toolchain preflight loop — and that now includes `npm`, whose `command -v` guard was
deleted for the same reason the others were never written: `npm --prefix web install` reports its
own absence in the same second, `make check` reports a missing `ruff`/`mypy`/`pytest` two seconds
later by itself, and a hand-listed loop is one more thing to keep in sync. `init.sh` does `cd` to
its own directory, because every script here reads `./.env` relative to CWD.

---

## 2. Test layout

Everything lives under `tests/`: invariant and unit checks at the top level, browser checks in
`tests/e2e/`. Each file opens with a docstring saying what it covers and why it is shaped that
way — that is the index, and unlike a tree transcribed into this document it cannot go stale on
the first rename. `ls tests/**/*.py` is the listing.

---

## 3. Gate scope, stated so the exclusion is visible

The gate governs `app/` and `tests/` in Python (`SRC`) and `web/` in TypeScript (`check-js`, §1).
It **excludes `learning-tests/` and `seed/`**.

Those are one-shot empirical scripts whose findings live in their docstrings; they were written
before the gate existed and re-flowing them would destroy provenance the take-home is graded on.
The exclusion hides a known, counted quantity, recorded here so it is a decision rather than an
oversight. Measured 2026-08-16 with the gate's own rule selection and thresholds
(`ruff check --config 'extend-exclude=[]' learning-tests seed`): **23 ruff findings across 10
codes** —

| Count | Code | What |
|---|---|---|
| 5 | `E402` | module import not at top of file — deliberate, imports sit after a timed `t_import` marker |
| 5 | `UP031` | printf-style formatting |
| 3 | `F541` | f-string with no placeholders |
| 2 | `I001` | unsorted imports |
| 2 | `PLR0913` | too many arguments |
| 2 | `PLR0915` | too many statements |
| 1 | `C901` | complex structure |
| 1 | `B007` | unused loop control variable |
| 1 | `E501` | line too long |
| 1 | `UP017` | `datetime.timezone.utc` |

`C901` and `PLR0915` are in that list on purpose: they are the two signals §6 calls the gate's
thresholds, so hiding them silently would have defeated the point of counting at all. Plus
**3 mypy errors** (`seed/seed_demo_data.py:694,701` `str | None` sloppiness;
`learning-tests/lt1a_ge_postgres.py:690` an `except`-scope reassignment) and **`ruff format`
would reflow all 4 files**.

**Dependency model, Python:** per-script `uv run --with …`, no lockfile, dependencies declared in
each script's `RUN` docstring block. `pyproject.toml` exists only to configure the gate and
declares no dependencies and no build backend. *Ceiling:* adding a resolver and a lockfile before
there is an app to lock would be scaffolding for later. The trigger to formalise is the first time
two modules need the same non-stdlib import at runtime.

**Dependency model, JavaScript:** `web/package.json` with a committed `web/package-lock.json` —
Node has no equivalent of `uv run --with`, and a lockfile is how `npm install` is idempotent
enough for `./init.sh` to run it on every boot. Five runtime and dev dependency *lines*
(`next`, `react`, `react-dom`, `typescript`, `eslint` + `eslint-config-next` + three `@types`)
resolve to 345 packages, all of them the Next toolchain. Nothing else is added: the shell has no
UI library, no CSS framework, no state manager, no test runner of its own — the browser layer is
Python playwright, which was already installed.

**Stripped from `create-next-app`:** `next.config.ts` (empty), `page.module.css`, all five
`public/*.svg`, `app/favicon.ico`, the generated `README.md` / `AGENTS.md` / `CLAUDE.md`, the
`next/font/google` import in the root layout, `eslint.config.mjs`'s `globalIgnores([…])` block,
`tsconfig.json`'s `paths` and `**/*.mts`, and `web/.gitignore`. Three of those need a word. The
font import downloads Geist at *build* time, which would have made `npm run build`, and therefore
`./init.sh`, need the network. The favicon was 25 KB of the Vercel logo shipping as this product's
tab icon on a graded take-home; nothing referenced it, and a missing `/favicon.ico` is a 404 that
fires neither `requestfailed` nor a console error, so `test_console_is_clean` stayed 7/7 green
without it. The `globalIgnores` block restated `eslint-config-next`'s own defaults verbatim —
measured identical 11-file lint set with and without it — which is precisely what §6 says
`pyproject.toml` deliberately does not do. `paths` and `**/*.mts` had zero users (every import in
the tree is relative; no `.mts` file exists) and `next typegen` does not re-add them; the four
options that Next *does* rewrite back on every `make check-js` — `allowJs`, `incremental`,
`resolveJsonModule`, `.next/dev/types/**/*.ts` — are left alone on purpose, because deleting them
just makes the working tree go dirty on every gate run. Boilerplate nothing reads is exactly what
this project deletes.

---

## 4. Driving the running app — F10, F11, F12, F13, F14

**F13 joined this layer when LT-1b landed** (§9). Its checks are in
`tests/e2e/test_f13_results_dashboard.py`, and its two routes are in the hygiene and visual lists.

The mockups have no routing at all — all four are single-page `show(id)` tab switchers with
`#fXX` anchors. F14 was therefore 100% uninvented at design time and is invented here. Route
map the browser checks assert against:

| Route | Feature |
|---|---|
| `/` | role door — a *view*, remembered on device |
| `/tables` | F10 |
| `/tables/[table]/rules` | F12 |
| `/rules/[ruleId]` | F12 + **F14** permalink |
| `/review` (`?table=orders` scopes it) | F11 |
| `/runs`, `/runs/[recordId]` | F13 — page unbuilt, but no longer undesigned |

**Role is never a route segment.** No `/eng/tables`, or every F14 permalink forks in two. Role is
localStorage/cookie view state layered on one URL space. This is asserted, not documented.

**All seven routes resolve today** (`dq-5pb.1`). `web/app/` has a `page.tsx` for each, and each
renders a heading and one sentence naming the feature that owns it and saying it is not built.
That is the whole of the shell: B1 owns no SPEC feature, so a route rendering plausible-looking
tables, rules or run records would make `make check-ui` green against a lie — the one failure mode
§10 exists to prevent. `/eng/tables` and `/expert/review` return 404 because nothing claims them,
which is how that assertion will pass without a rule being written to make it pass.

**A cost the running app introduced, and the fix that landed with the first real browser check.**
`make check-ui` went from instant to **44 s** the moment a server existed: `app_url` used to
`pending()` first, so the `driver` fixture never ran; once it succeeded, every still-`pending()`
browser check paid a full chromium launch before its body said it had nothing to do. The second
half of `dq-5pb.1` made the launch session-scoped (`chromium` fixture) and left the **context**
per-test, which is the boundary that actually matters — cookies, storage, permissions, and F14's
"no prior navigation". **49 browser checks now run in 22 s** — 3 hygiene checks over 7 routes (21 real cases), the rest pending.

### 4.1 Behavioural (`tests/e2e/test_ui_behaviour.py`)

Playwright drives the running app: navigate → act → assert on the actual route, rendered state,
or fired request. Never the DOM in a vacuum, never a static mockup — the `app_url` fixture pends
when `APP_URL` is unset precisely so a browser check cannot be satisfied by a fixture file.

Every assertion below is deterministic. None needs an eye.

**F11** — `/` with no stored role renders the role door; clicking *Domain expert* lands on
`/review`, **not** `/tables`; reload keeps it. **Zero** elements matching a table-list selector
exist anywhere in the `/review` DOM (an absence assertion — the kind a screenshot cannot make).
The caveat sentence *"A rule can be true of every row here and still be wrong"* is present, and
is compared against the **shared copy module**, not a literal duplicated into the test. A
duplicated literal only tests that two copies of a typo agree.

**F10** — the three bucket headings appear in **DOM order**: *never run → ran, but unverifiable →
verified*. A table whose last record is errored or sampled is a descendant of bucket II and
**not** of bucket III. Zero-coverage tables sort first (SPEC F10).

**F12** — the catalog renders exactly as many entries as the canonical catalog **file** contains
(counted against the file, not a hardcoded 15). The GE-config `<details>` has **no `open`
attribute** on first paint — attribute presence is deterministic, "looks collapsed" is not. A
`needs_review` row contains **no `input[type=checkbox]` at all**, not a disabled one: a disabled
control still says *this is bulk-acceptable, just not right now*. Bulk cap: 0 selected → button
`disabled`; cap+1 selected → the extra is refused and the label still reads the cap. The
*"Compiled · shape OK"* token does **not** carry the pass-verdict class — class equality is
deterministic, colour is not, and the neutrality is the whole point (compiling proves a rule is
well-formed, never that it is right).

**F14** — `/rules/<id>` opened in a **fresh browser context** (no cookies, no prior navigation,
no login) returns 200 and renders the English statement, evidence line and Accept action. The
fresh context is the fixture default, so this is normal rather than special.

**F13** (`tests/e2e/test_f13_results_dashboard.py`) — the screen must be correct **halfway through
a run**, because O-3 settled on *synchronous, but progressive* (§9). Mid-flight, every accepted rule
has a row: unsettled rules render **pending — not absent** (a missing row makes the run look smaller
and more finished than it is) and **not passing** (an unfinished rule may not wear the pass class;
silence is not a green tick), while **at least one row has already settled** — which is the whole
claim of progressive. A fourth fact rides on the same snapshot: the *"n of m reported"* counter SPEC
F13 asks for must equal the settled and total row counts read off that same DOM, because a counter
that disagrees with the list above it is worse than no counter. All four are states present at one
moment, read off the DOM; no stopwatch is involved. A second check closes the loop: once the record settles, **zero** rows are still pending,
because a list that never clears its pending state is indistinguishable from a finished run in a
screenshot and from a hung one to a user.

**Network assertions — the ones a DOM check cannot make:**

- An inexpressible rule (*"shipped date must be after order date"*) renders *"Nothing was saved.
  Your coverage did not change."* **and fires zero POST/PUT to the rules endpoint.** Rejection
  must not write. This is the assertion, not the copy.
- A draft compile hits the compile endpoint and **no** persistence endpoint until *Save as
  accepted*. Unsaved-until-accepted is a network fact, not a label.
- Page load renders the cached last result **without** firing an execution request (SPEC F9).
- Run records are immutable: no `PATCH`/`PUT`/`DELETE` route resolves for one, and *Re-run*
  issues a **create** that yields a new record id (assert the id in the URL changed).

### 4.2 Console-clean (`tests/e2e/test_ui_hygiene.py`)

Parametrised over every route. Zero console errors, zero unhandled rejections, zero failed
network requests. The recorders (`console` / `pageerror` / `requestfailed`) are part of the
`Driver` fixture's contract rather than monkeypatched per test, so they cannot be forgotten.
Cheapest high-yield check in the harness — it is what catches "looks fine, secretly broken".

**The browser layer is proven to block (workflow Step 6, `dq-5pb.1`, 2026-08-16).** One line —
`<img src="/deliberately-missing.png" />` in `web/app/unbuilt.tsx`, the component every route
renders — was added, the app rebuilt and restarted, and `make check-ui` went red: **14 failed, 7
passed, 28 skipped**, `make: *** [check-ui] Error 1`. One break tripped *two independent* checks on
all seven routes, which is the point of parametrising them:

```
E  AssertionError: / logged console errors: ['Failed to load resource: the server responded with a status of 404 (Not Found)']
E  AssertionError: / axe violations: critical image-alt at ['img']
```

The line was then removed, rebuilt, and the layer returned to **21 passed, 28 skipped**. Two
adjacent contracts were exercised in the same session and hold: `APP_URL` pointed at a port with
nothing answering **errors 49 checks rather than skipping one** (`app_url` FAILs, never skips), and
a cold checkout with no `web/node_modules` and no `web/.next` boots through `./init.sh` in **23.6 s**
and serves the same 21 green.

### 4.3 Visual regression

Eight named states, screenshotted and diffed against `tests/e2e/__baselines__/<state>.png`.
First run **writes** the baseline and **fails loudly** (`BASELINE WRITTEN — a human must look at
it once and commit it`); thereafter a pixel diff over threshold fails. One human approval per
state is what keeps this deterministic instead of subjective. Baselines are committed; `.actual`
and `.diff` output is gitignored. Deliberately narrow: eight states, not every screen at every
breakpoint — each baseline is a maintenance cost and has to earn itself. The eighth,
`run-record-in-flight`, earns it because a half-finished progressive run is the state most likely
to look plausible and be wrong.

**Not claimed yet — and the check reads why off the running app, rather than asserting it.**
`tests/e2e/__baselines__/` is **empty today and that is the honest state**: every route still
renders `web/app/unbuilt.tsx`, so a file called `tables-three-buckets.png` would be a picture of a
paragraph saying F10 is not built — a baseline no human could meaningfully approve, and one that
would need re-approving the moment the state it is named after existed. So the check navigates,
looks for the shell placeholder in the body text, and `pending()`s **per state, naming the route
and which of the two it saw**. It pends on both branches deliberately: the day the placeholder
disappears the PENDING line changes to *"this state is REAL — write the baseline diff"* instead of
the check going quietly green over a screen nothing has ever compared.

**The diff itself was written, proven, and then deleted.** A Pillow implementation (per-channel
tolerance 8, fail over 0.1% of pixels, `.actual.png` / `.diff.png` beside the baseline) was
exercised end to end on 2026-08-16 against a temporary placeholder-free route: first run wrote the
file and failed with `BASELINE WRITTEN`; the second passed byte-stable; a 300×80 black rectangle
painted into the baseline failed with *"role-door moved: 2.3343% of pixels differ (budget 0.1%)"*.
It was then removed rather than committed, on two grounds. With all eight states pending, every
line of it sat after a `pending()` that always fires — code `make check-ui` cannot reach, so the
gate could not keep it honest. And its `from PIL import …` was a module-level import in a file
pytest collects during **`make check`** (deselection happens after collection), which made Pillow
an undeclared fifth dependency of the default gate — absent from §1's table, from the `Makefile`
header and from `init.sh`, so a fresh clone following the documented boot could not run the gate at
all. Proven by shadowing `PIL` on `PYTHONPATH`: collection error, zero tests run. The first bead
that ships a real screen has to approve a baseline anyway, and writes the diff back in the same
breath — against a state that exists.

### 4.4 Accessibility

axe-core injected into the page and run in-page; fail on serious/critical, **warn** on moderate and
minor. `warnings.warn`, not `print`: pytest captures stdout and replays it only for a *failing*
test, i.e. never on the run where the moderate list is the interesting part, so the original claim
that they were "printed" described an output nobody would ever see. The warnings summary prints on
green. **REAL as of `dq-5pb.1`, over all seven routes.** The bundle is vendored as one file,
`tests/e2e/axe.min.js` (axe-core 4.13.0, 568 KB, MPL-2.0 with its copyright banner intact as that
licence requires, taken from `npm pack axe-core` in a scratch directory). Vendored rather than
imported from `web/node_modules` even though that directory now exists: `tests/` is Python, and
reaching sideways into a sibling toolchain's install directory for a runtime asset is how a test
starts failing for reasons that have nothing to do with the app. The check now requests the
`driver` fixture — the note about it deliberately not doing so applied only while the missing
bundle was the blocker a human had to act on.

*Result on the shell* — **zero serious or critical violations on all seven routes**, alongside
zero console errors, zero failed requests and CLS 0. That is no longer a note: it appears in
`pytest -ra` as 3 hygiene checks over 7 routes — 21 passing cases, not 21 independent facts. The shell was built to make it pass: `lang="en"` and a
single `<main>` landmark in the root layout (so `region` is satisfied once rather than per
screen), and a `--muted` grey at 7.0:1 on white.

### 4.5 Layout stability

`window.__cls`, accumulated by a `PerformanceObserver` on `layout-shift`, registered as an **init
script** — before any navigation, because `buffered: true` only replays shifts inside a document
that already existed, so registering after `goto` would measure a page that had finished moving.
Budget 0.1, Google's published "good" bar, borrowed rather than invented. The shell measures 0 on
all seven routes. §8 listed this as unclaimed; it is claimed now because the shell paints, which
makes the number exist, and because nothing else in the harness would notice a late-mounting
banner or a font swap.

---

## 5. The three keystone invariant checks

### INV-3 · exactly one module imports Great Expectations — **ENFORCED TODAY**

`tests/test_inv3_single_ge_import.py`. This is the invariant that makes GE's next breaking
release a one-file change instead of a rewrite, so it is enforced by the gate, not by convention.
The designated module is a single constant, `GE_RUNTIME = app/dq/ge_runtime.py` (provisional path;
change the constant and the gate follows).

Two halves, catching different dodges. The **first** is the non-vacuous one today; the second has
nothing to scan until `app/` exists and therefore reports `PENDING` rather than passing over an
empty set — an empty scan that reports green is the exact failure this harness exists to refuse:

1. **`ast.parse`** over every gate-scoped `.py`, collecting `ast.Import` / `ast.ImportFrom` whose
   root module is `great_expectations`. Any file other than `GE_RUNTIME` is an offender. This is
   real and non-vacuous *today*: it fails the instant a second module reaches for GE, which is
   exactly when the invariant would otherwise erode silently.
2. **A raw text scan** over `app/` for the literal module name — because AST
   only sees real import statements and misses `importlib.import_module("great_expectations")`,
   `__import__`, and re-exports through a string. A dynamic import is still an import. `app/` does
   not exist yet, so this half `PENDING`s with that as its reason and becomes real on its own the
   moment the directory lands. Tests are
   exempt from the *text* scan (they name the framework in prose and in expected-exception
   strings) but not from the AST scan; a test needing GE for real calls it through `GE_RUNTIME`
   like everything else.

A third assertion — that `GE_RUNTIME` exists and does import GE — is `PENDING` until `app/` exists,
and pins the module's location the moment it does.

**Half C — one module, one call, one context.** LT-1b found that `gx.get_context()` does not return
a context, it **installs one as a process-global project**: a second call silently orphans the first
context's datasources, and the failure does not surface at `get_context()` but later at `validate()`,
as a `DatasourceError` naming a datasource that is sitting right there in the object you are holding.
A request handler that calls it therefore breaks every other request in flight and sends the debugger
to configuration instead of to concurrency. Two more checks, same file, same mechanism as half A:

1. **No module outside `GE_RUNTIME` calls `get_context()`** — `ast` again, matched on the callee name
   so `gx.get_context()`, `great_expectations.get_context()` and a bare imported `get_context()` all
   count. Real and non-vacuous today. *Ceiling:* an unrelated helper of that name is a false
   positive; worth it, because the alternative is resolving aliases.
2. **`GE_RUNTIME` calls it exactly once, and at module level.** The module-level half is the one that
   matters: a single call site inside a request handler is still one context per request, which is
   precisely the LT-1b bug. `PENDING` until `app/` exists. *Ceiling:* requiring the call at module
   level is stricter than LT-1b's finding, which is one context per **process**, never per request.
   A module-level singleton and a memoised accessor (`_ctx = None; def context(): global _ctx; …`)
   are both correct; only the first is cheap to assert with `ast`, so that is the one the gate
   demands.

**Both proven to block.** `app/api/_probe.py` containing `ctx = gx.get_context()` fails check 1
(alongside both halves of A); a `GE_RUNTIME` whose `def context(): return gx.get_context()` defers
the call into a function fails check 2:

```
AssertionError: app/dq/ge_runtime.py calls get_context() inside a function (lines [5]).
Build the context once at import and hand it out — one per request is the LT-1b bug.
```

**Proven to block.** Dropping a one-line `import great_expectations as gx` into `app/api/_probe.py`
fails both halves:

```
AssertionError: INV-3 violated: [PosixPath('app/api/_probe.py')] import great_expectations.
Only app/dq/ge_runtime.py may. Route it through that module's dict-in/dict-out surface.
```

### INV-2 · an invalid or hallucinated expectation cannot reach the rule store

`tests/test_inv2_authoring_rejection.py`. **Rejection at authoring time**, while the author is
still looking at the screen and can be told why — not an execution error. An expectation that
blows up during execution has already been stored, already counts toward coverage, and has
already lied about the table being protected.

The learning tests killed the obvious design. *"Instantiate it against GE"* is a **proven
insufficient** gate: of 25 deliberately invalid rule probes, **GE rejected 15 and accepted 10**.
So the validator is two layers and the order is load-bearing:

1. **our own per-type sanity table** — `min <= max`, non-empty `value_set`, `re.compile`-able
   regex, known SQL type name, at least one bound present, column exists in the live schema;
2. **construction against GE**, through `app/dq/ge_runtime.py`.

Layer 1 must run **first**, because layer 2 alone lets all ten of these through:

| Probe | Why it is nonsense |
|---|---|
| `values_to_be_between(column, min_value=100, max_value=1)` | inverted bounds |
| `match_regex(column, regex="[unclosed")` | regex does not compile |
| `match_regex(column)` | no regex at all |
| `in_type_list(column)` | no `type_list` at all |
| `table_row_count_to_be_between()` | no bounds at all |
| `mean_to_be_between(column)` | no bounds at all |
| `unique_value_count_to_be_between(column)` | no bounds at all |
| `values_to_be_in_set(column, value_set=[])` | empty set can never pass |
| `values_to_be_of_type(column, type_="NOT_A_TYPE")` | not a real SQL type |
| `values_to_be_unique(column="no_such_column")` | column absent from the live schema |

The asymmetries are per-expectation authoring drift inside GE, not policy we can lean on:
`not_match_regex` without a regex **raises** but `match_regex` without one does not;
`row_count_to_be_between` with min > max **raises** but `values_to_be_between` does not;
`values_to_be_between` with neither bound **raises** (root validator) but `mean_to_be_between`
does not. Required-ness lives in two incomplete places — `.schema()["required"]` and a root
validator — which is also why **the catalog cannot be generated from GE introspection**.

The other **fifteen** probes are rejected by GE, and the four rejection *classes* are asserted too,
so our validator surfaces a readable reason instead of leaking a framework traceback. Exact
exception types confirmed by LT-2a (GE 1.20.0, pydantic **v1** object model vendored inside
pydantic 2); the DSN row is LT-1a's, and it is a connection error rather than one of the 25 rule
probes:

| Bad input | GE raises |
|---|---|
| hallucinated type (`expect_column_values_to_be_vibey`) | `great_expectations.exceptions.ExpectationNotFoundError` |
| missing declared kwarg, wrong type, `mostly` outside 0..1 | `pydantic.v1.ValidationError` |
| misspelled kwarg (`min_valu=`) | `pydantic.v1.ValidationError`, *"extra fields not permitted"* |
| bad DSN at `add_postgres()` | `TestConnectionError` — **config error, not rule failure**; classify separately |

Trap to avoid: `ExpectationConfiguration(type="expect_column_values_to_be_vibey", …)` does **not**
raise — it constructs fine and only `.to_domain_obj()` raises. The validator must therefore
construct through `get_expectation_impl(type)(**kwargs)`, never through `ExpectationConfiguration`.

Second assertion, the half a unit test usually misses: **a rejected spec writes nothing** —
asserted on the store, not on the return value. A validator that raises and a store that already
wrote are both possible at once.

The `uv run … -m ge` line in §1 re-asserts that GE alone would still let those ten through. If a
GE upgrade starts rejecting them, that test fails and we get to **delete** sanity rules rather
than guess. The ten are enumerated once, in
`tests/test_inv2_authoring_rejection.py::FRAMEWORK_ACCEPTS_THESE_TEN`; the table above is a
transcription of that constant for the reader, and the constant is the source of truth.

### INV-5 · any result derived from a sample says so

`tests/test_inv5_sampling_disclosure.py`. Three layers, because disclosure can be lost in three
different places.

1. **Origin.** GE 1.x has **no sampler** — no `add_sampler`, no `add_splitter`, no
   `sampling_method`; `partitioners` slice by column, never "first N rows". The only row cap is
   our own SQL via `add_query_asset(query="SELECT * FROM public.orders LIMIT N")`. Critically,
   **GE does not record that a run was capped**: nothing in `element_count`, `unexpected_count`
   or `meta` distinguishes a capped run from an honest run over a smaller table. The marker is
   ours, carried from the asset definition into the stored record. Two checks: *constructing a
   capped run record without the marker must raise*, and *the marker is set from the asset
   definition, never inferred from `element_count`* — the second is what stands where a cap-value
   check would have gone, now that LT-1b has decided no cap ships (§9). It is asserted as a pair
   (uncapped → not-sampled, capped → sampled) so a normaliser that marks everything sampled cannot
   pass it.
2. **Transport.** The marker survives normalisation and caching (F9).
3. **Surface.** The verdict and the disclosure are **one text node**:

```python
el = page.locator("[data-status-atom]")
assert el.text_content() == status_atom(...)          # the shared formatter, not a literal
assert "sampled" in el.text_content()                 # INSIDE the same element
# and no sibling carries the sampling text
```

One formatter, one writer, emitting a single string of the form `FAILED · sampled <scanned> /
<total>` — illustrative, not a reading: at the demo set's 500,000 rows the cap is off (§9.2), so
the marker's value is `not sampled`. "Adjacent" survives nothing — a layout change, a responsive
breakpoint or a truncation separates two sibling elements. "Inside" survives all three.

> **SPEC agrees, as of Rev 0.2:** `SPEC.md` INV-5, F13 and §7 step 7 all now say sampling renders
> *inside* the status token. The mockup and the recon assertion still disagree on casing
> (`Failed · sampled …` vs `FAILED · …`) — the formatter module settles it and the test asserts
> against the module, so pick either.

---

## 6. Deterministic code-quality signals

Named only where the tool actually exists for this stack today.

| Signal | Tool | Status |
|---|---|---|
| dead code — unused imports, unused locals | ruff `F401`, `F841` | **on** |
| function complexity | ruff `C901`, `max-complexity = 10` | **on** |
| function size | ruff `PLR0915` (statements), `PLR0912` (branches), `PLR0913` (args) | **on** |
| import hygiene / sorting | ruff `I` | **on** |
| bug-prone patterns | ruff `B` (bugbear) | **on** |
| file size | stdlib in `tests/test_code_quality_thresholds.py`, threshold 400 lines — Python **and** `web/app/**/*.tsx` | **on** |
| js dead code — unused imports and locals | `@typescript-eslint/no-unused-vars`, red because of `--max-warnings 0` (§1) | **on** |
| js type errors | `tsc --noEmit` in `check-js` | **on** |
| **no vacuous test** | stdlib `ast`: a `test_` body must assert or `pending()` — `FunctionDef` **and** `AsyncFunctionDef` | **on** |
| **no silent skip** | stdlib `ast`: no `pytest.skip` / `mark.skip` / `mark.skipif` / `mark.xfail` / `pytest.xfail` / `pytest.importorskip` outside `conftest.py`, and no `from pytest import skip\|xfail\|importorskip` | **on** |
| **no async test** | stdlib `ast`: no async plugin is configured, so an `async def test_` can only skip | **on** |
| **no mistyped marker** | pytest `--strict-markers`: an unregistered marker is a collection error, not a warning — without it a one-letter typo (`e2ee`) runs inside `make check` | **on** |
| **INV-3 single-importer** | AST + text scan (§5) | **on** |
| duplication | `jscpd` (Node) — **NOT INSTALLED**; `web/package.json` now exists, see below | **off** |
| unused exports | `knip` / `ts-prune` — **NOT INSTALLED**; `web/package.json` now exists, see below | **off** |
| Python dead-code beyond ruff | `vulture` — **NOT INSTALLED** | **off** |

ruff has no file-size rule and no opinion about whether a test verifies anything, which is why
those three signals are hand-rolled tests rather than config. Everything else here is ruff's own
default threshold (complexity 10, branches 12, statements 50, args 5); `pyproject.toml`
deliberately does **not** restate them, because a config line that equals the default changes no
behaviour and rots when the default moves.

The file-size cap grew a second file type when `web/` landed. It is a *craft* threshold — "this
file is doing two jobs" — not a Python fact, and eslint has no file-size rule either, so a
900-line `page.tsx` would have walked past the only signal that catches it. `source_files()` briefly
grew a `pattern` argument for it and has been reverted: a shared helper widened for exactly one
caller is the wrong shape, and the caller now says what it means in place —
`source_files("app", "tests") + list((REPO / "web/app").rglob("*.tsx"))`. One line, one reader,
no keyword whose docstring has to admit it exists for one caller.

**Duplication and unused exports: the stated trigger fired, and the answer is still off.** §8 said
*trigger: the first `npm install`* — that has now happened (`dq-5pb.1`). The trigger was a proxy
for "there is frontend code worth scanning", and it turns out to be a bad proxy: the shell that
came with the `npm install` is 9 `.tsx` files totalling under 70 lines, none of which export
anything unused and none of which duplicates another. `knip` and `jscpd` would add two
dependencies and a config file in order to print zeroes. **Replacement trigger, stated so it
cannot be waved through twice:** the first bead that ships a real screen — `dq-rbf` / `dq-klv`,
F10–F13 — adds `knip` to `web/package.json` and `knip` to the `check` script in the same commit.

The **subjective** craft review — abstraction fit, naming, "reads like the codebase" — stays with
the human/reviewer in Step 7.5. It is not automatable and pretending otherwise produces a check
that is either noisy or vacuous.

---

## 7. Deterministic vs LLM evaluator

**Deterministic (everything above).** Routes, DOM order, element counts, attribute presence,
class equality, absence assertions, network logs, console output, pixel diffs against approved
baselines, axe violations, AST facts, exception types, exact counts from the seed manifest.

Most of what *feels* subjective about this UI is not. "Sampling is disclosed" is
`el.textContent`. "Compiled is neutral" is a class comparison. "The expert never sees a table
list" is a selector count of zero. "Rejection doesn't write" is a network log. "The proposal is
unsaved" is a network log. **Push everything into this column first.**

**Genuinely subjective — the LLM evaluator's entire remit (Step 7):**

- Does the built product match the *design intent* of the chosen variant (`ux-variant-ledger.html`,
  "Run Ledger" — the book-of-record metaphor), or has it drifted into a generic dashboard?
- Do the named grafts survive: Reviewer's *"Accept — I vouch for this"* voice, the queue
  time-budget indicator, real per-role density filtering (eng columns actually **hidden**, not
  relabelled)?
- Is a failure legible to someone who could judge whether it matters (INV-4)? A machine can check
  the English statement is present; only a reader can say it reads like English.
- Does INV-1 hold — can a domain expert act on a table's proposals in ≤ 5 minutes? Time is
  measurable, but "did they understand what they accepted" is not.

Everything else the evaluator might be tempted to judge already has a deterministic form above.

**A special case that is deterministic and looks subjective:** rule *correctness* is graded
numerically against `seed/MANIFEST.md`, which is exact ground truth — 13 defect classes, 3,950
defective rows, every defect on a **disjoint** set of primary keys, each class shipping its
verifying SQL. `unexpected_count` must equal the manifest count (D1 = 150, D3 = 240, D6 = 150,
D7 = 1,200, D8 = 430, D9 = 260, D12 = 180). Seeding is byte-reproducible (`SEED = 20260816`,
verified by per-table md5 fingerprints). **Coverage is a fixed number, not an opinion**: the v1
single-column catalog reaches 8 classes / 2,670 rows, and **1,280 known-bad rows are invisible to
any purely single-column rule set** — so "does the product disclose its blind spot" becomes an
equality assertion on 1,280, not a judgement.

> Time trap, recorded: **D5** (60 rows, `ordered_at > now()`) decays after ~30 days from the
> 2026-08-16 anchor. Any gate asserting D5 = 60 must re-seed first, or treat D5 as time-sensitive.

---

## 8. Deliberately NOT verified at this stage

Each of these is a decision, not an oversight. Adding it now would be over-engineering for where
we are: **there is no application code yet.**

| Not verified | Why not, and the trigger to add it |
|---|---|
| **Duplication and unused-export detection** | ~~Trigger: the first `npm install`.~~ **That trigger fired with `dq-5pb.1` and was re-set, once, with the reasoning written down in §6:** the shell it arrived with is 9 files / <70 lines, so `knip` and `jscpd` would print zeroes. New trigger: the first bead that ships a real screen (F10–F13). |
| **Coverage percentage thresholds** | A coverage number over 5 real tests measures nothing, and a threshold set now becomes a target to game. Trigger: after the first feature ships with real tests. |
| **Mutation testing** | Correct answer to "are the tests any good", wrong cost at 5 tests. |
| **Performance / latency budgets** | The measurement now exists (LT-1b) and the answer is still no — deliberately, see §9.1. The environment moves more than the budget would: the same 10-rule cell measured 14.84 s at the start of the run and 13.61 s at the end (−8.3%) on a burstable free tier, and the pooled 100,000-row cell spread 10.17–22.62 s across five runs. A threshold above that noise (say 25 s) passes for a product nobody would wait for; one at the median flakes weekly and teaches people to re-run a red gate. What replaces it is a **shape** assertion that cannot flake: F13's progressive check (§4.1) asserts states present at one moment, never elapsed time. Trigger: a dedicated non-burstable instance, or one real user complaint about speed — then the budget is set from a re-measurement on that instance, not from these numbers. |
| **Load and concurrency** | One env-configured connection, one user at a time. Non-goal. |
| **Cross-browser and mobile viewports** | Two named desktop users. Chromium only until someone asks. |
| **Security scanning (SAST, dependency audit)** | ~~Trigger: the first lockfile.~~ **Fired with `dq-5pb.1`** — `web/package-lock.json` exists. `npm audit` reports **0 vulnerabilities across 346 packages** (2026-08-16), so the finding is recorded rather than the check installed: `npm audit` queries the registry, and putting it inside `make check` would break the "needs no network" promise §1 makes about every layer. New trigger: the deploy bead (`dq-cyi.1` · B22), where a network-dependent audit belongs — beside the Dockerfile, not on every save. |
| **Contract tests between backend and frontend** | Both live in one repo and ship together; the e2e flow already crosses the seam. Trigger: the seam becoming a deployment boundary. |
| ~~**Cumulative layout shift**~~ | **CLAIMED with `dq-5pb.1`** — the shell paints, so the number exists. `test_no_layout_shift_on_first_paint`, budget 0.1, §4.5. |
| **A CI runner** | No `.github/`. `make check` is the contract; wiring it to a runner is 10 lines whenever a second machine needs it. |
| **Pre-commit / Stop hooks** | Step 6 of the workflow. The gate has to exist and be shown to block first — it now is (§5, INV-3). Wiring is the next step, not this one. |
| **`docker-compose` build verification** | SPEC §3 promises it; no `Dockerfile` exists yet, and `docker` is not even on PATH (Docker Desktop 27.4.0 is installed at `/Applications/Docker.app/Contents/Resources/bin/`). Trigger: writing the Dockerfile. |

---

## 9. SETTLED BY LT-1b (bead `dq-e1d`)

LT-1b measured GE latency against Supabase and **landed**. It was the last thing blocking this
harness, and it resolved SPEC **O-2** (row cap) and **O-3** (synchronous vs background). Both
answers are adopted. Full write-up: `learning-tests/FINDINGS.md` §LT-1b, raw numbers in
`learning-tests/lt1b_results.json`. Nothing in this document is waiting on a measurement any more.
One implementation choice is still open — SPEC **O-4**, the transport for progressive results — and
nothing here asserts it, deliberately; §9.1's settled table records why and what constrains it.

The numbers this section leans on, all direct connection, `orders` at 500,000 rows, only the
primary key indexed:

| | measured |
|---|---|
| 15 catalog rules, whole table, shipping config | **13.97 s** |
| the 10-rule shipping suite (`unexpected_index_column_names`, which F13 needs) | **14.84 s** direct · **17.94 s** pooled |
| single rule, whole table, shipping config | **2.28 s** |
| cost shape | **~2.3 s floor + ~0.83 s per additional rule** — lumpy, not linear in rows |
| 1,000 → 500,000 rows (500×) | **2.7×** the time |
| largest suite under 10 s at 500,000 rows | **3 rules** |
| largest row count under 10 s with 10 rules | **100,000** |
| connect, never inside the watched number | direct **1.16 s** · pooled **2.26 s** (RTT 51 ms / 109 ms) |
| GE's own Python, share of wall clock at full size | **21%** — more than the network |

### 9.1 O-3 · execution model — **synchronous, but progressive**

Not a job queue. The worst case measured is past the 10 s bar, but the cost is a floor plus a
per-rule increment paid as a sequence of independent statements, and nothing in that shape is
improved by a worker: a queue returns the same 14 s later and adds a polling endpoint and a
staleness problem. What the shape argues for is a request that **streams each rule's verdict as it
lands** — first result at about 2 s (one rule over the whole table measures 2.28 s), then a filling
list. A blank spinner for 14 s is not an
option, and that is the part the measurement is entitled to insist on.

**The ceiling is measured, not hypothetical:** only **3 rules** fit under 10 s at 500,000 rows, and
with 10 rules only **100,000 rows** do. Progressive rendering is what makes 14 s honest, not fast —
a product that lets rules accumulate crosses the watchable line by design (LT-1b), which is why
SPEC §5 now carries "what happens past the ceiling" as a deliberate deferral with a trigger rather
than treating O-3 as a decision with no expiry date.

**Connection:** F8 uses `SUPABASE_DB_URL_DIRECT` (port 5432). The transaction pooler is **21% slower**
for this workload — 17.94 s against 14.84 s on identical work — because a rule run is a handful of
long analytical statements on one connection, the shape a pooler helps least.

**And still no latency assertion in the gate — chosen, not deferred.** §8 listed "LT-1b owns every
wall-clock number" as the reason there was no budget; that reason has expired and the answer is the
same for a better one. The environment moves more than any budget would: the same 10-rule cell read
14.84 s at the start of LT-1b's run and 13.61 s at the end (−8.3%) on a burstable free tier, and the
pooled 100,000-row cell spread 10.17–22.62 s over five runs. A threshold set above that noise would
pass for a product nobody would wait for; one set at the median goes red on a busy afternoon and
teaches everyone that a red gate means *re-run it*, which costs more than the check is worth. A
budget that flakes is worse than none. What ships instead is the **shape** of the promise, which is
deterministic: F13's progressive check asserts states present at one moment (§4.1), and O-3's
per-rule streaming is what makes 14 s honest rather than fast. The trigger to add a real budget is a
non-burstable instance or a real complaint — and it gets re-measured there, not copied from here.

**SPEC's wall-clock numbers are context, not gate criteria.** SPEC F8 and F13 quote 2.28 s, 13.97 s
and the 1.28–6.59 s per-rule range inside their acceptance paragraphs, explicitly marked there as
measurement rather than criterion. Nothing in this harness asserts any of them, deliberately, for
the reason above — so a reader should not go looking for the missing check. What is asserted is the
shape: unfinished rules render pending, at least one row settles before the rest, and a settled
record has zero pending rows.

What that settles, and what now checks it:

| Settled | Checked by |
|---|---|
| F13 renders a **partially-complete** run: unfinished rules pending, not absent, not passing; at least one settled; and the *"n of m reported"* counter agrees with the list it sits above | `tests/e2e/test_f13_results_dashboard.py::test_a_run_in_flight_renders_unfinished_rules_as_pending` (§4.1) |
| A settled record has **zero** rows still pending | `…::test_a_settled_run_has_no_pending_rows_left` |
| F13's routes are ordinary routes | `/runs`, `/runs/[recordId]` joined `ROUTES` in `test_ui_hygiene.py`; `run-record-in-flight` joined the visual baselines |
| No cancel check, no poll-termination check, no staleness check | Deliberate: there is no job to cancel and no poll to terminate, and F9's cache is what a reload renders. These were listed as F13's likely checks while O-3 was open; the answer removed them. |
| F8's acceptance needs a progressive-result clause, and SPEC F13 needs to describe a half-finished run | **DONE** — SPEC F8 *Acceptance — progressive results* and SPEC F13 *Acceptance — partially-complete runs* (Rev 0.2). SPEC §8's contingency was only partially triggered: the feature did not become a job system. |
| **O-4 · transport** (SSE / chunked response / one request per rule) is **still open** | Nothing asserts the transport — deliberately. §4.1's F13 checks are transport-agnostic (DOM states at one moment), and §5's INV-3 half C is the only constraint on it: whatever is chosen must work against a single process-global GE context and must not create one per request. |

### 9.2 O-2 · row cap — **no cap ships**

The cap is the wrong lever, on three measured grounds, not one:

1. **It buys little.** Capping at 100,000 rows — an 80% cut of the data — saves 5.5 s of 14.84 s
   (37%), because the cost is a per-run and per-rule floor rather than the scan.
2. **At full size it is a net loss.** GE executes a query asset's SQL verbatim, twice per validate,
   through psycopg2's client-side cursor: `LIMIT 500000` costs **22.67 s** and moves **1,000,127
   rows** to the client, against **13.63 s** and **156 rows** for the same suite uncapped.
3. **It breaks two of the fifteen catalog types outright.** `expect_column_values_to_be_of_type` and
   `expect_column_values_to_be_in_type_list` raise a bare `KeyError: 'type'` against a query asset —
   GE reads the column type from the reflected table and a query asset has none.

**So there is no cap value, and therefore nothing for a cap-value check to assert.** The check that
was marked `blocked_lt1b` is gone, and so is the marker itself (a marker for a resolved blocker is a
place for a stub to hide). What ships in its place:

| Settled | Checked by |
|---|---|
| INV-5's disclosure **mechanism** ships with the cap switched **off** — because the day a table is an order of magnitude bigger the cap returns, and GE will still not record it | `tests/test_inv5_sampling_disclosure.py::test_the_sampling_marker_comes_from_the_asset_definition_not_from_ge_output` — the marker is set from the asset definition, never inferred from `element_count`, asserted as an uncapped/capped pair |
| The two type expectations must keep working — and the failure mode is **silent**, since `catch_exceptions` defaults to `True` and an errored rule is visually identical to a failing one (LT-1a) | `tests/test_catalog_and_copy.py::test_the_two_type_expectations_run_against_a_table_asset`, in the `ge` layer so `make check` pays no network cost. It asserts on `exception_info`, not on `success` — an errored rule is `success: false` with `result: {}`. |
| `errored` is a **third result state**, not a kind of failure | `tests/test_result_normalisation.py` (F9). A rule that did not run has a coverage meaning, not a data-quality meaning; reporting it as failed tells a domain expert the data is bad when the rule is. Both checks are `pending()` on `app/dq/normalise.py`. |

### 9.3 The process-global context — a consequence nobody asked for

LT-1b also found that `gx.get_context()` installs a process-global project, which makes "exactly one
module imports GE" insufficient on its own: that one module must also create exactly one context, at
import, and hand it out. This is now enforced (§5, INV-3 half C) and proven to block. It is the
hardest of the new checks because the failure it prevents surfaces somewhere else entirely — a
`DatasourceError` about configuration, raised by a request that did nothing wrong.

### 9.4 Still not blocked, and still worth building first

Unchanged by LT-1b, and the reason O-3 was never on the critical path:

- **The persisted run-record table with an explicit `status` field.** Progressive execution needs the
  same record a synchronous one does, plus per-rule states that settle.
- **The `/runs` and `/runs/[recordId]` deep-link target strings**, already asserted.
- **The single status-atom formatter** (INV-5 surface layer).
- **Write-resistance**: no UI mutation path for a stored rule or a run record; amendment drafts a new
  revision, re-run appends a new record.

### 9.5 The follow-ups LT-1b named and this harness does not check

Recorded so they are decisions rather than omissions. None of them is a gate check today: two are
optimisations with no user asking for them, and the third is a mechanism that does not exist.

- **GE's own Python overhead** — 21% of wall clock at full size, metric-graph resolution rather than
  database work. Nothing to assert until someone tries to reduce it.
- **`be_unique(order_reference)` costs 6.59 s**, 2.7× the median rule, because it sorts an unindexed
  `text` column over 500,000 rows. That is the honest number for an unprepared table (the seed leaves
  everything but primary keys unindexed on purpose) and it is also the cheapest available win, if one
  is ever wanted. An index would make it a different measurement, not a passing check.
- **A cheaper row cap.** If a cap is ever needed, `add_query_asset` is the wrong mechanism, and
  whatever replaces it has to be measured the same way before it is trusted.

---

## 10. What is done, and how a feature earns "done"

**There is no feature ledger file.** An earlier draft of this harness carried
`verification/features.json` — F1–F15 with `steps[]` and a `passes` boolean — plus a `summary.py`
that claimed to enforce its rules. It was deleted, for two reasons that are worth keeping written
down:

1. It was a **fourth** copy of the same verification intent (SPEC.md F1–F15, this document, the
   test docstrings, the ledger), and CLAUDE.md already says `bd` is the only task tracker. It had
   drifted on its first day — it named a test file that did not exist.
2. It **did not enforce what it advertised.** Gutting every `steps` entry, rewriting every
   `description` and flipping all 15 features to `passes: true, verified_by: "vibes"` exited 0 and
   printed `15/15`. A gate's own honesty mechanism that can be made to lie is worse than not
   having one.

What replaces it costs nothing and cannot drift, because both are generated from the checks:

- **`pytest -ra` is the ledger.** Every stub prints `PENDING — <what it is waiting on>` on every
  run. That list is the scope of what remains, written by the checks themselves.
- **`bd list` over the F1–F15 beads** is the per-feature roll-up (Step 3 of the workflow), in the
  tracker this repo already mandates.

The rule the ledger existed to state survives, and is the one thing a reviewer should hold us to:

> A feature counts as verified only when a check that **actually ran** proves it, and for any
> feature with a UI surface that means a **browser-driven** check — not a unit test and not
> `curl`. Both have passed on this class of feature while the feature was broken; LT-2a found GE
> accepting 10 of 25 nonsense rules while reporting success.

And one mechanical guard now backs the harness's central claim instead of merely asserting it:
`tests/test_code_quality_thresholds.py` walks every test file with `ast` and fails on a `test_`
function (sync or async) that contains neither an assertion nor a `pending()` call, on every
spelling of a silent skip outside `conftest.py` — `pytest.skip`, `mark.skip`, `mark.skipif`,
`mark.xfail`, `pytest.xfail`, `pytest.importorskip`, and `from pytest import skip|xfail|
importorskip`, which closes the bare-name hole at the import rather than by chasing aliases — and
on an `async def test_` at all, because nothing here runs one. `pending()` being the only route to
a stub was previously true by convention, and then true for five spellings out of nine; the entire
thesis of this harness is that convention does not hold, so the check now has to enumerate.
