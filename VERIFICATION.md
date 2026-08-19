# VERIFICATION — the back-pressure harness

**Status:** **shipped, and driving a real application** · Step 4 of
`software_development_workflow.md`. The harness was designed before there was any code; every layer
it described now runs against the thing it was designed for. The browser layer is not a plan — it
launches Chromium against a real Next process in front of a real Python process against the real
seeded Supabase database, with console, network and axe recorders attached before first paint, and
it has been made to go red on a planted break or a dead endpoint on **five recorded occasions** and
restored every time — §4.2, §4.6 twice, §4.7 and §8.1.
**Runs today** (re-measured 2026-08-18 at close-out, after the four live-deployment defects — the
concurrent three-target block from 08:50 is at §4.7.2): `make check` exits 0 with
**201 passed, 0 skipped** in 5.79 s (103 deselected — the browser, GE and billed-model layers, which
belong below). The markers cover all **304** collected
checks: 201 default + 33 `ge` + 67 `e2e` + 6 `live` (201+33+67+6−3 = 304, and the arithmetic is
worth keeping visible: it is what catches a check that joined no layer). **They stopped being a partition with F12**
and the overlap is deliberate and exactly three: `tests/e2e/test_f12_translation_desk.py`'s two authoring checks carry `e2e` AND
`live`, because F4's refusal and its unsaved-until-accepted promise need a browser *and* a real
model call — and SPEC §7's scenario carries both for the same reason, three times over.
`make check` excludes them twice over; `make check-ui` selects them on purpose, which is what
makes it the one make target that spends money (about $0.24 a run).
**`make check-ge` runs the GE layer against the real seeded database — 0 `PENDING`, no stubs
left**, and it is **33 passed, 269 deselected, 199.79 s, exit 0** at close-out. INV-2's authoring
gate (`app/rules/validator.py`, bead `dq-yov.4`) is what turned 16 of
those skips into assertions: every shipped invalid-rule probe is now refused before persistence —
all 10 the framework alone accepts, plus one probe for each of the four rejection classes it does
catch.
**That target was BROKEN at close-out and the fix is one `--with`.** It died with
`ModuleNotFoundError: No module named 'claude_agent_sdk'` and `Interrupted: 7 errors during
collection` in 0.76 s — a red target that had verified nothing, which is the failure mode this
document exists to refuse. `-m ge` selects 33 checks and none of them asks a model, but **pytest
imports every module under `testpaths` before it applies a marker**, and seven of them reach
`app/model.py` through `suggest` / `authoring` / `app.api.server`. `--no-project` inherits no
site-packages, so the recipe now names `claude-agent-sdk==0.1.23` the same way §1's API-process line
already does. A layer's dependency list is not "what it runs", it is "what it can import".
**`make check-ui` runs the browser layer against the two booted processes.** Last run
2026-08-18 at close-out, on a freshly rebuilt `web/.next`: **63 passed, 2 skipped, 2 failed, 237
deselected, 525.11 s**. The two skips are the delivery targets nobody named. The two failures are
visual-regression states and neither is a code change: `tables-three-buckets` no longer carries
`lt1a_probe`, which is this wave's own fix landing in a picture taken before it, and
`run-record-in-flight` photographs a demo run record that has since been re-seeded (new id, new
timestamp, and the two failing rules now sort together). Both need the author's eye and a
`git add`, which is the one approval no agent may give — §4.3 and §9. 21 of the passes are 3 hygiene checks over
7 routes (console-clean, layout stability and accessibility, §4.2/§4.4/§4.5); the rest are F10's,
F11's, F12's, F13's and F14's own screens, plus **SPEC §7's end-to-end scenario, which is one check
and about 2 min 50 s of it** (bead `dq-cyi.2` — see §4.6).

**TWO THINGS THAT MAKE A BROWSER-LAYER NUMBER A LIE, both met at close-out and both cheap to
avoid.** First, **`web/.next` is stale until you rebuild it and it fails GREEN**: `npm run start`
serves the last build and says nothing about it, so a whole `-m e2e` pass was taken against code
that predated the fixes it was checking, and it passed. `find web/app -newer web/.next/BUILD_ID`
answers it in one line, and it also dissolved a phantom defect the stale build had invented.
Second, **two concurrent runs of this layer used to take each other red, and no longer do**: SPEC
§7's stack schema was the constant `dq_scenario` and the flow DROPS it on the way in, so a second
runner dropped it under the first. Seen as `AssertionError: the store holds 3 rule(s) for orders
after a screen of proposals` — an assertion that is exactly right and was not loosened — against a
`dq_scenario` holding 19 rule revisions written by the other process inside the same 100 seconds.
**Fixed by bead `dq-mc0`: the schema carries the pid** (`dq_scenario_<pid>`), so a runner is its own
writer. Two §7 flows launched ~2 s apart, on 2026-08-19, both green — **1 passed in 141.24 s** and
**1 passed in 133.35 s**, both exit 0 — and §4.7.3 has the schema listing that proves they were in
different stores. It was the third instance of the shape §4.7.2 records.

**THE EIGHT SKIPS, AND THE STATUS OF THE VISUAL BASELINES, STATED ONCE.** Six of the eight are
visual-regression states (§4.3) and two are the delivery targets nobody named (§8.1). **No visual
baseline is approved, `role-door` included, and an earlier draft of this section said the
opposite.** That correction is bead `dq-zyt` and it is the most instructive thing in this document,
so it is stated here rather than buried: `role-door` DID compare and pass on 2026-08-17 — against a
picture no human ever staged. `_approved()` asked `git ls-files` whether the PATH was tracked, the
re-shot PNG had overwritten a tracked path, and a baseline therefore self-approved by being written
over. The old picture and the new one differ by **31.36% of their pixels against a 0.20% budget**,
which is the best evidence in this repository that the visual layer discriminates on a real change —
and the check called it approved anyway. `_approved()` now also asks `git diff --quiet`, so a
tracked-but-MODIFIED baseline pends with the same sentence the untracked case gets, and `role-door`
is back among the six. They are all photographed against the **demo** store, a fixed fixture in a
schema this layer does not write to (`seed/seed_demo_rules.py`, `tests/fixtures_demo.py`, §4.3), and
each of them writes its baseline and pends for the one reason that must never become automatic —
**nobody has looked at the picture yet.** No agent may approve one; approval is a person's `git
add`, and that mechanism has now had both of its doors shut. **`pytest -m live`**
is 6 checks, 3 of which are also `e2e` and therefore inside `make check-ui`; the other 3 — the
sandbox proof, F3's suggestion call and F4's own — are in no make target and are run deliberately.
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
| 4 | tests | `python3 -m pytest -m "not ge and not e2e and not live"` | pytest 7.4.3 | yes |
| 5 | js lint + typecheck | `npm --prefix web run check` | eslint 9 + tsc 5 (`eslint-config-next` 16.3.1) | yes, in `web/node_modules` — `./init.sh` installs it |

`SRC = $(wildcard app) tests`. `$(wildcard)` was there so the gate tolerated a missing `app/`
rather than erroring on it; `app/` now exists and is linted, typechecked and size-checked like
everything else. **`make check` installs nothing, needs no network and needs no running app.**

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
trusting it: `-m "not ge and not e2e and not live"` is what keeps `make check` from collecting a
layer that would launch a browser, import a framework the base interpreter does not have, or spend
money. Three layers are therefore deliberately *outside* it:

```bash
make check-ui     # APP_URL=http://localhost:3000  DQ_API_URL=http://localhost:8000  pytest -m e2e
                  # needs TWO RUNNING processes. Both fixtures GET their URL and FAIL when
                  # nothing answers — this target may never report success against a dead server.
                  #
                  #   1. the Next app          npm --prefix web run start
                  #   2. the Python process    the uv line below, with DQ_SCHEMA=dq_check
                  #
                  # The second one arrived with F14 (bead dq-rbf.1): a permalink that renders a
                  # rule's English statement, evidence line and actions has to READ a rule, so
                  # the screen is only real if the process behind it is. DQ_SCHEMA=dq_check is
                  # the BROWSER LAYER'S OWN scratch schema, which tests/scratch.py pins from the
                  # markers pytest selected — the store is append-only, so a check that wrote to
                  # the demo's own schema could not clean up after itself, and one that shared a
                  # schema with `check-ge` would read counts that layer was moving (§4.7.2).
                  # A server started on any other schema fails this layer by name rather than
                  # quietly rendering somebody else's store: `scratch.agrees`.
                  #
                  # The TARGET also sources ./.env now (bead dq-rbf.2, F10). One check needs a
                  # run record in the "ran, but unverifiable" bucket, and the shipping
                  # configuration cannot produce one — the row cap is off (O-2) so no run is
                  # sampled, and no seeded table makes a catalog rule blow up. So the condition
                  # is written into the SCRATCH schema through runs.save() before the browser
                  # looks (tests/conftest.py::coverage_records), which needs the system DSN in
                  # THIS process too. Without it that fixture PENDS by name rather than failing:
                  # a layer nobody handed credentials to was not asked for.
                  #
                  # AND, AS OF F12 (bead dq-rbf.4), THIS IS THE ONE MAKE TARGET THAT SPENDS
                  # MONEY: three real model calls per run, about $0.12 and ~20 s (LT-2b),
                  # made by the SERVER process rather than by pytest. `?propose=1` once,
                  # shared by three checks through the five-minute memo in
                  # app/rules/suggest.py; then F4's refusal and its unsaved-until-accepted
                  # promise, which are the product's two headline claims and cannot be
                  # proven without asking a model. Those two carry `live` as well as `e2e`,
                  # so `make check` excludes them twice over and `-m e2e` selects them here
                  # on purpose. It also APPENDS to the scratch store every run — the store
                  # is append-only (F6), which is why F12's visual state is photographed
                  # against the DEMO store and never this one (§4.3, bead dq-vix).
                  #
                  # set -a; . ./.env; set +a
                  # DQ_SCHEMA=dq_check uv run --no-project --with great-expectations \
                  #   --with 'sqlalchemy>=2' --with psycopg2-binary \
                  #   --with claude-agent-sdk==0.1.23 python3 -m app.api.server
                  #   ^ the fourth --with is load-bearing: --no-project inherits no
                  #     site-packages and app/api/server.py reaches app/model.py through
                  #     desk -> authoring, so without it the process dies on import
                  #     before it binds a socket. tests/e2e/scenario_stack.py carries the
                  #     same line for the seven checks that boot their own stack.
                  # DQ_API_URL=http://localhost:8000 npm --prefix web run start
                  # last run 2026-08-17: 43 passed, 15 skipped, 216 deselected in 167.5 s

# The `live` layer is one check (tests/test_model_sandbox.py) and one real, billed model call.
# It is the only proof the sandbox holds against the CLI rather than against our reading of it,
# so it exists; it costs ~$0.04, so it is never inside a command anyone runs on save. It is the
# one layer with no make target — run it deliberately:
set -a; . ./.env; set +a          # the call authenticates from CLAUDE_CODE_OAUTH_TOKEN
python3 -m pytest -m live         # last run 2026-08-17: 1 passed, 156 deselected in 5.03 s

make check-ge     # the uv line below, on the condition this section used to state
```

The GE layer had no target while all three of its checks were `pending()` stubs — a target that
resolves ~40 packages from the network in order to print three skips is a trap, not a
convenience. `app/dq/ge_runtime.py` landed with bead `dq-yov.1` and `app/rules/catalog.json` with
`dq-yov.2`; every `ge` check is now real, so the command is a target:

```bash
make check-ge     # set -a; . ./.env; set +a  +  the uv line below
uv run --no-project --with pytest --with great-expectations --with 'sqlalchemy>=2' \
  --with psycopg2-binary --with 'psycopg[binary]' python3 -m pytest -m ge
# last run 2026-08-17 at close-out: 33 passed, 251 deselected in 104.14 s, exit 0
# (it was 18 checks in 38 s before waves 2 and 3; the layer grew with the code it checks)
#
# RUNNING IT ALONGSIDE `check-ui` IS SAFE, as of bead dq-cyi.4 (B27). It used to take
# both layers red: they shared DQ_SCHEMA=dq_check, both WRITE, and the store is
# append-only (F6), so a check counting rules before and after an action was reading a
# number the other layer was moving. They have a schema each now — this layer writes
# `dq_check_ge` — derived from the markers pytest selected rather than exported by a
# target, so it cannot be got wrong by a shell or a .env. See §4.7.2 for both failures,
# both guards, and the concurrent run that is green. `make reset-scratch` drops them.
```

`--with pytest` and `--no-project` are both load-bearing: uv's ephemeral env does not inherit
site-packages (without the first it dies with `ModuleNotFoundError: No module named 'pytest'`),
and without the second uv runs in project mode and writes `.venv/` and an unwanted `uv.lock`
into the repo root. **The target now sources `.env` first** — as of the compiler (`dq-yov.3`)
this layer runs the compiled suite against the real seeded `orders` table, so the marker's
"AND a reachable database" clause finally bites; without the DSN the layer fails, which is
correct and a rotten way to greet someone running the target. `psycopg2-binary` and `sqlalchemy`
are in the line because that path has landed, not in anticipation of it.

The layer went from 3 s to 38 s as it started executing, and that is the price of the thing
being checked rather than overhead: the three-rule `orders` suite includes
`expect_column_values_to_be_unique` over an unindexed `text` column at 500,000 rows, the dearest
rule LT-1b priced (6.59 s alone), and the store's own integration checks write and read real rows
over the same link. A GE layer that runs in 3 s is a GE layer that never ran a rule.

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
| `/runs`, `/runs/[recordId]` | F13 — `?table=` moves, `/runs/[recordId]` is fixed for ever |

**Role is never a route segment.** No `/eng/tables`, or every F14 permalink forks in two. Role is
cookie view state layered on one URL space. This is asserted, not documented.

**And whether a document contains the framework is decided in ONE place, which is bead `dq-220`.**
It used to be decided on each page — three of them appended `?configuration=1` for the engineer,
and the two `/runs` screens, written later, did not: both roles received byte-identical HTML with
nine expectation configurations in it, folded into a `<details>`, which is exactly the disclosure
pattern Rev 0.4 replaced. The decision now lives in `web/app/api.ts`, the one door every screen
reads through, and it is enforced from two sides: `tests/test_f12_framework_boundary.py` (default
layer, offline) fails on any file under `web/` that knows the API's address or composes the
parameter itself, and `tests/e2e/test_framework_absence.py` derives the route list from
`web/app/**/page.tsx` and fetches every page as both readers, asserting on the RAW RESPONSE that
the domain expert's carries none of the framework's vocabulary. A page added later joins that check
by existing rather than by somebody remembering; a page with a segment it cannot fill goes red
naming it. The run stream is checked the same way, from one real run read twice — the expert's
NDJSON must be clean while the record that run stored must not be, or the check has proved nothing.

**Built with F14 (bead `dq-rbf.1`), and this is what the mechanism turned out to be.** The role is
a **cookie**, not localStorage, and the reason is a property of this stack rather than a
preference: the role decides what the SERVER renders — the Great Expectations pane is not hidden
from the domain expert with a stylesheet, it is never put in the markup — so a value only the
browser can read would mean rendering every page twice and moving it under the reader, against a
0.1 CLS budget. `web/app/role.ts` is the whole of it: two roles, each naming the door it opens
(`/tables`, `/review`), one cookie, one server action. `/` is the door; a device that has already
chosen is redirected past it. **The default for a request carrying no cookie at all is the DOMAIN
EXPERT's view**, which is the conservative direction — a cold permalink from someone else's chat
message must not confront its reader with the framework (SPEC F12, Rev 0.4), and an engineer
un-defaults with one click that is then remembered.

**All seven routes now render a real screen**, as of `dq-rbf.4`, and `web/app/unbuilt.tsx` was
deleted with its last caller. Until then each unbuilt route said which feature owned it and that
the feature did not exist, on purpose: a route rendering plausible-looking tables, rules or run
records would make `make check-ui` green against a lie — the one failure mode §10 exists to
prevent. `/eng/tables`, `/engineer/tables`, `/expert/review` and `/expert/rules/<id>` all return
404 because nothing claims them, and the check asserts the other direction too: walking through
the door produces `/tables`, an address with no role in it.

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
`/review`, **not** `/tables`; returning to `/` keeps it. **REAL as of `dq-rbf.1`** — both halves
in one check, because neither is worth anything alone: a door that routes correctly but forgets
asks the question on every visit, and a remembered choice that routed to the wrong screen is worse
than no memory at all. The click targets the DOOR's own button rather than the switch in the
header; both set the same cookie, and a check that clicked the wrong one would pass without ever
proving the door works. Still pending: **zero** elements matching a table-list selector anywhere in
the `/review` DOM (an absence assertion — the kind a screenshot cannot make), and the caveat
sentence *"A rule can be true of every row here and still be wrong"*, compared against the
**shared copy module** rather than a literal duplicated into the test. A duplicated literal only
tests that two copies of a typo agree. Both wait on B19.

**F10** — the three bucket headings appear in **DOM order**: *never run → ran, but unverifiable →
verified*. A table whose last record is errored or sampled is a descendant of bucket II and
**not** of bucket III. Zero-coverage tables sort first (SPEC F10).

**F12** — the catalog renders exactly as many entries as the canonical catalog **file** contains
(counted against the file, not a hardcoded 15). The GE configuration is a facing pane and there is
no disclosure control on that screen at all, which is Rev 0.4 (the check asserts
`query_selector_all("details") == []` for the engineer, and no `ge-pane` and no `expect_column_values`
anywhere in the domain expert's document). The raw panel that IS a `<details>` is F13's, on the run
record, and it belongs to the engineer — asserted on the absence of the `open` attribute, because
attribute presence is deterministic and "looks collapsed" is not. A
`needs_review` row contains **no `input[type=checkbox]` at all**, not a disabled one: a disabled
control still says *this is bulk-acceptable, just not right now*. Bulk cap: 0 selected → button
`disabled`; cap+1 selected → the extra is refused and the label still reads the cap. The
*"Compiled · shape OK"* token does **not** carry the pass-verdict class — class equality is
deterministic, colour is not, and the neutrality is the whole point (compiling proves a rule is
well-formed, never that it is right).

**F14** — **REAL as of `dq-rbf.1`.** `/rules/<id>` opened in a **fresh browser context** (no
cookies, no prior navigation, no login) returns 200 and renders the English statement, evidence
line and the actions. The fresh context is the fixture default, so this is normal rather than
special, and the check asserts the context arrived empty before it navigates.

**Nothing in that check is a literal.** The statement, the evidence line and every button label
are read out of the payload the server composed (`GET /rules/<id>`) and compared against the
rendered DOM, so what is asserted is that the page *renders what it was given*. A copy of the
sentence typed into the test would pass on a page that had quietly started composing its own —
which is the failure `app/dq/status.py`'s single-writer rule exists to prevent, and the one a test
full of literals cannot see. It also asserts there is no `input[type=password]` anywhere on the
page: there is nothing to log into, and SPEC's non-goals settled why.

**The run-record link contract** is fixed in the same bead and asserted separately: `/runs` and
`/runs/<recordId>` both answer 200 to a cold request, and **two different record ids reach two
different pages** — otherwise `/runs/<id>` is one screen wearing many URLs and a link to a
specific run is not a link. The page behind it is B16's; only the contract is fixed here.

**Shown once to go red (2026-08-17, `dq-rbf.1`).** A single file — `web/app/expert/review/page.tsx`,
the per-role URL space this bead exists to forbid — was added, the app rebuilt and restarted, and
`test_role_is_never_a_route_segment` failed with

```
E  AssertionError: ['/expert/review'] resolve. A per-role URL space means a pasted permalink
   carries the sender's role to the receiver, which is exactly what F11 forbids.
```

The file was deleted, rebuilt, and the layer returned to **25 passed, 24 skipped**. That is the
whole value of the check: nothing else in the harness notices a second URL space appearing, and it
is the kind of thing that gets added by someone being helpful.

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

**The recorders are cleared after the role dance, and only then** (bead `dq-rbf.4`). Engineer-facing
routes call `choose_role` first, which posts a server action to `/` and redirects; the browser
records the superseded request as a failure, *intermittently*, and reported it against whichever
engineer route lost the race. `/` has its own entry in `ROUTES` and its own console check, so
starting clean at the moment the navigation under test begins loses nothing and stops the check
crying wolf — which is the one habit that gets a check deleted.

**The browser layer is proven to block (workflow Step 6, `dq-5pb.1`, 2026-08-16).** One line —
`<img src="/deliberately-missing.png" />` in `web/app/unbuilt.tsx`, the component every route
rendered at the time — was added, the app rebuilt and restarted, and `make check-ui` went red: **14 failed, 7
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

**Six** named states, screenshotted and diffed against `tests/e2e/__baselines__/<state>.png`.
Deliberately narrow: six, not every screen at every breakpoint — each baseline is a maintenance
cost and has to earn itself.

**It was eight, and two were deleted rather than approved, for the same reason. Here is the
first; the second is below, and it is the more instructive one because it recurred after this
was fixed once.** `tables-bucket-two-errored` and `tables-three-buckets` both mapped to `/tables`, and `_settled()` only navigates — so the two
states were the same full-page photograph by construction, and the two written PNGs were
byte-identical (md5 `251d2012bccdbdc52ebb0341b5fbbd54`, on two independent runs). A baseline that
cannot fail while its neighbour passes asserts nothing its neighbour does not, and approving both
would have put a human signature on a duplicate. Scoping the second shot to the bucket element was
the alternative and was not taken: it would still be a strict subset of the first image — the same
maintenance cost for the same information. The middle bucket is checked where it is derived
(`tests/test_table_coverage.py`) and where its atom is rendered (INV-5's browser walk).

**REAL as of bead `dq-rbf.1`, the first bead that renders a screen rather than a placeholder.**
The diff is back — Pillow, imported *inside* the test function, per-channel tolerance 12 and a
budget of 0.2% of pixels. Both numbers are deliberate: a screenshot that must match bit for bit
fails on a Chromium point release, and a check that cries wolf gets deleted. The comparison is a
per-pixel maximum across channels (`ImageChops.lighter` twice) and then a histogram, which is
exact and avoids `getdata()` — deprecated in Pillow 12, and a removal warning in the gate's output
is noise in a place whose whole value is that green means green.

**A BASELINE IS NEVER SELF-APPROVED, AND THAT IS A MECHANISM, NOT A CONVENTION.** The first time a
state renders something real the check writes the PNG and PENDS — and it *keeps* pending until the
file is **tracked by git and unmodified since**, because a person staging a file is the only signal
available that a person looked at it. Without that gate the run would photograph whatever it
rendered and pass against its own photograph from the next run on: a green check over an image
nobody has ever seen, which is exactly the failure §10 exists to prevent. Writing is automatic;
approving is a human act with a name on it. A checkout with no git answers "not approved" and the
state keeps pending, which is the right way round — the unapproved case must never be the silent one.

**AND IT HAD A SECOND DOOR, WHICH WAS FOUND BY WALKING THROUGH IT — bead `dq-zyt`.** The mechanism
above was implemented as one question, `git ls-files --error-unmatch <baseline>`, i.e. *is this PATH
tracked*. That is the whole story the first time a state is photographed and stops being the whole
story the moment the screen changes: the check itself overwrites the baseline, and overwriting an
already-tracked path leaves it tracked. So a re-shot baseline compared against **itself** and went
green over a picture nobody had looked at — the exact habit the paragraph above says it exists to
prevent, arriving through the door nobody had checked.

It is not hypothetical and it is not a story about somebody else. It happened here, on 2026-08-17,
while re-shooting `role-door.png` for the door polish (bead `dq-dkq`). The committed picture is md5
`d81dd5bab5f32f7f6a5df6088b03fd48`; the re-shot one is `1bb3f3224d34c4fd435b2f07f28e8b36`; they
differ by **31.36% of their pixels against a 0.20% budget** — 156x over, i.e. the loudest red this
check can produce. The check called it approved and passed. Two things follow, and the second is the
one worth keeping:

1. **The fix is one line and the same tool.** `_approved()` now asks `git diff --quiet -- <baseline>`
   as well, i.e. *is the CONTENT the staged content*. A tracked-but-modified baseline pends with the
   same sentence the untracked case gets, and a re-approval costs a person the same look the first
   approval did. The failure message no longer reads like an instruction to walk through the door
   either — "replace the baseline with it and `git add` that as the approval" is now true, because a
   replaced baseline PENDS until somebody does.
2. **The 31.36% is the evidence, not the embarrassment.** Before this, the strongest thing that could
   be said about the visual layer was that a synthetic 60x60 block moved 0.404% of a picture. What
   actually happened is that a real, intended layout change moved a third of the screen and the diff
   caught it exactly. The check discriminates. What failed was the approval gate around it.

   Re-derived 2026-08-18 with the check's own three expressions, against
   `git show HEAD:tests/e2e/__baselines__/role-door.png` and the working tree:
   `sizes (1280, 720) (1280, 720)` · `moved 289019 px = 31.36%`. The re-shot PNG is also
   byte-stable across every run since — same md5 `1bb3f322…` after the pend path rewrites it —
   so the 31.36% is a property of the change, not of the renderer.

**WHAT THE FIVE DATA-DEPENDENT STATES PENDED FOR, AND WHY THEY DO NOT ANY MORE — bead `dq-vix`.**
Every one of them
said the same thing in a different dress: *the screen behind it is built and green behaviourally,
and what it RENDERS is not a function of the code alone.* `tables-three-buckets` printed a rule
count this layer moves and a record id a fixture mints per session. `review-queue-with-caveat` was
the loudest — 1280x12430, 1.3 MB, thirty-eight cards, most of them the same rule left by earlier
runs into an append-only store (F6) **that this very layer writes to**; the queue's own time-budget
indicator honestly read *"about 16 minutes left — past the five minutes this is supposed to take"*.
`rule-permalink-standalone` photographed whichever rule the store handed over first.
`rules-facing-panes` photographed a desk that `fixtures_f12.held_rule` and
`test_draft_compile_does_not_persist_until_accept` add a rule to on every run, by design.
`run-record-in-flight` photographed a record id and a finish time minted by the run that wrote it.

**The fix is not a tolerance, a mask or a crop — it is a different database.** The photographs are
now taken against the DEMO store `dq`:

- **`seed/seed_demo_rules.py`** seeds it, in one idempotent command (`make demo-fixture`). Eight
  rules over three tables, one per STORED state these screens render:
  accepted-and-passing, accepted-and-failing (D1 and D6 from `seed/MANIFEST.md`, 150 rows each),
  one `needs_review` — SPEC §7 step 3's flagged rule verbatim, the vocabulary of `orders.status` —
  one `rejected` **carrying its reason**, and one reading that is `errored` rather than failed,
  which is the distinction LT-1a bought and which nothing could show without an instance.
  `payments` deliberately gets nothing, because a table nobody has written a rule for is F10's
  first bucket. **Every rule walks `store.propose()` and therefore the validator (INV-2)** — a
  fixture that INSERTed would be the one back door the keystone invariant exists to close.
- **Idempotent against a store that cannot be edited.** Both tables refuse UPDATE, DELETE and
  TRUNCATE by trigger, from every role including the owner, so "run it twice, get the same store"
  is done by asking per rule whether the store already holds that exact validated spec and
  appending only what is missing — and by keeping the run records a table already has, because a
  record is immutable and a second one would move every id on screen. Proven: two consecutive runs
  of the seeder, the second printing `held` on all ten lines and writing nothing.
- **`tests/fixtures_demo.py`** boots the product on it — its own Python and Next processes on free
  ports, the same machinery SPEC §7 uses (`scenario_stack`, which grew two arguments for this).
  The one difference is the whole point: `reset=False`, because §7 needs a store nobody has written
  to *yet* and this needs one nobody will write to *again*. **Every navigation these states make is a
  GET.** Measured across three runs of the browser layer on 2026-08-17: `dq_check` went from 261
  rules / 253 records to **267 / 261**, while `dq` stayed at **16 rows and 2 records** with its
  last write still the seeder's.

**Result, measured 2026-08-17 across three independent runs — two of `pytest -m e2e -k visual`
and one of the whole browser layer: every baseline came out BYTE-IDENTICAL** (same md5, three times
over) — a stronger property than the 0.2% budget the check enforces. Zero states now skip for data
dependence, and all six pend with the one sentence that was always the honest one: *the baseline
was WRITTEN and is NOT approved.*

**THE DUPLICATE-PHOTOGRAPH DEFECT RECURRED, AND WAS SETTLED THE WAY THE FIRST ONE WAS.**
`rules-facing-panes` and `rules-proposal-needs-review-held` mapped to the same route and `_settled()`
only navigates, so they were the same photograph — md5 `ed9a0d4cef028e8996b5aedf8cc9ffcf`, on all
three runs. That is verbatim the case the eighth state was deleted for, above, recurring after being
fixed once, which is a better piece of evidence than the clean version would have been. This
document's first draft named it and deferred it to a human. It is now **deleted**, on the argument
the eighth state already established and on one more that is specific to it: the state could not
render what it is named for at all. A proposal is a model call (F3) and is unsaved by definition
(F4), so the demo fixture cannot mint one — the pane in the shipped PNG read *"Accept 0 — I vouch
for each of these · 0 / 8"* over an empty list. Giving it a step that produced a real proposal was
the alternative and was refused: a billed, non-deterministic call is the one thing a photograph may
not depend on. The proposal pane is checked where it is real, in
`tests/e2e/test_f12_translation_desk.py`. **Handing a person two identical PNGs to sign was the
thing to avoid, and asking them to settle it counts as handing.**

**One thing a person still has to settle.** `run-record-in-flight` is now a photograph of a
*settled* record, because a fixed record is by definition one that finished — the name outlived what
it names. Renaming a baseline is a scope decision with a human's name on it, and unlike the
duplicate above it costs nothing to leave standing: the state asserts exactly what it should, under
a name that reads wrong.

**The diff was proven to go both ways on 2026-08-17**, against the real `role-door.png` at
1280×720: an identical image moves 0 pixels (green); a 20×20 black block moves 441 pixels, 0.048%
(green, under budget); a 60×60 block moves 3,721 pixels, 0.404% (**red**, over the 0.2% budget).
Same three expressions the check runs.

**And on 2026-08-17 it ran for real — against a picture nobody had staged.** `role-door` compared
and passed inside the browser layer, which is the first actual comparison this harness has ever
made, and it should not have happened: the baseline it compared against was one the check had
written over a tracked path minutes earlier. That is bead `dq-zyt` and it is told in full above.
What survives is the measurement — 31.36% of the screen moved and the diff reported 31.36% — and
what is fixed is the gate around it.

**Why the earlier implementation was deleted, and what changed.** A first Pillow version was
exercised end to end on 2026-08-16 and then removed on two grounds. With every state pending,
every line of it sat after a `pending()` that always fires — code `make check-ui` could not reach,
so the gate could not keep it honest. And its `from PIL import …` was a module-level import in a
file pytest collects during **`make check`** (deselection happens after collection), which made
Pillow an undeclared fifth dependency of the default gate — proven by shadowing `PIL` on
`PYTHONPATH`: collection error, zero tests run. Both are addressed rather than forgotten: one
state now reaches the diff, and the import is inside the function, below the `e2e` marker's reach.

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

### 4.6 SPEC §7 · the whole system, once (`tests/e2e/test_spec_section_7.py`)

One check, eight steps, **2 min 23 s and about $0.12** — the scenario SPEC §7 calls "the acceptance
test for the system as a whole" and says is "automated as the single end-to-end flow in the
verification gate". It is the one check in this harness whose entire value is that **nothing in it
is faked**: three real model calls, two real runs of `orders`, real Chromium, real Supabase. Marked
`e2e` and `live`, so `make check` excludes it twice over and `make check-ui` selects it.

**It boots its own stack.** §7 opens on *"No rules exist"*, the store is append-only (F6), and
`DQ_SCHEMA` is read from the process environment — so the flow drops and recreates a schema of its
own (`dq_scenario_<pid>`), starts an API process on it and a Next process in front of that, on two
free ports. `tests/e2e/scenario_stack.py` argues it at length. **The reset is idempotent rather than
self-cleaning:** a second run is never polluted by a first, and what the flow wrote survives so a
red one can be read. `DROP SCHEMA ... CASCADE` is also the only reset available — both stores refuse
DELETE and TRUNCATE by trigger, from the owner included.

**The pid in that name is bead `dq-mc0`** and it is what makes two of these flows runnable at once:
the name was the literal `dq_scenario`, which is one schema for however many runners there are, and
the way-in drop then took the first runner's store away (§4.7.3). The same way-in drop is the
cleanup — it sweeps the `dq_scenario_*` schemas whose process is gone, and never one a live run
owns, since that would be the same collision with an extra step.

Four files, because 400 lines is the file ceiling: the flow (`test_spec_section_7.py`, which asserts
only the SEAM between steps), the stack, steps 1–6 (`scenario_steps.py`) and the run
(`scenario_run.py`). It borrows the session browser rather than launching one — `sync_playwright()`
cannot be entered twice in a process, and the isolation boundary a browser check needs is the
context anyway.

**Shown to go red, twice, on 2026-08-17.** An off-by-one planted into
`app/dq/normalise.py::_one`'s `unexpected_count` produced

> `AssertionError: the order_total rule reads 'failed' over 149 rows; seed/MANIFEST.md plants
> exactly 150 negative-total rows in orders, and the manifest is not adjusted to match.`

and a `"verdict": "passed"` planted into `app/dq/run.py`'s opening event — a rule rendered as
passing before it had run, which is the one misreading F13 forbids — took the run screen red as
well. Both were restored and both files `diff` clean against their pre-break copies.

The numbers it grades against come from `seed/MANIFEST.md` and never from §7's prose, which still
quotes 2.4M rows the demo dataset does not have.

### 4.7 The three ways this gate has gone red without anything being broken

The first two were found at close-out on 2026-08-17 and the third at close-out on 2026-08-18; all
three are recorded here rather than in a commit message, and they matter for the same reason: **a
gate that is green two runs in three is not green.** An intermittent red teaches people to re-run
rather than to read, which is the one habit the rest of this harness exists to prevent.

**Two of the three are one shape** — one schema name, two writers, an append-only store — and that
is the most reusable thing in this section. The discriminator has to come from something the
colliding parties cannot share, and each instance needed one finer than the last: a marker names a
LAYER (§4.7.2) and a pid names a PROCESS (§4.7.3).

#### 4.7.1 A read that raced a write (bead `dq-cyi.3`)

**`make check-ui` went red once at close-out, on 2026-08-17 — 1 failed, 51 passed, 9 skipped in
279.29 s** — on §7's scenario, at step 4:

> `AssertionError: the store holds 'needs_review' with reason None; the reason is kept with the
> rule forever, which is the point of asking for it.`

**The same check then passed alone (1 passed in 133.07 s) and the same full target passed on the
next run (52 passed, 9 skipped, 384.05 s, exit 0).** Nothing in `app/` or `web/` was wrong.

**The mechanism.** Judging a rule is a Next **server action that redirects**. `networkidle` can
therefore be true *again* between the click and the request leaving, so a read taken straight after
it can arrive before the write. This repository had already learned that twice —
`tests/e2e/scenario_steps.py::_settle` polls the store and says so in its docstring, and
`tests/conftest.py::choose_role` waits for the header's own `aria-pressed` rather than for the
network — and step 4's rejection was the one place left with the old shape.

**The fix is a bounded poll on the thing being asserted, and the assertion is unchanged.** That
distinction is the whole of it: a poll that ends in `pass` would be a weakening, and one that ends
in the same `(status, reason) == ("rejected", REJECTION)` equality is not. **Proven, not assumed:**
filling the reason field with `""` instead — the store refuses a rejection carrying no reason — the
poll still exhausts its 60 attempts and reports the identical sentence above, at 1 failed in
122.35 s. The break was then reverted and `scenario_steps.py` `diff`s clean against its pre-break
copy.

#### 4.7.2 Two layers writing into one scratch schema (bead `dq-cyi.4`)

**Running `make check-ge` and `make check-ui` at the same time on one machine took BOTH of them red,
and neither had anything wrong with it.** Measured at close-out:

```
make check-ge   1 failed, 32 passed, 251 deselected, 112.55 s
                test_concurrent_writers_share_one_connection_without_corrupting_each_other
make check-ui   1 failed, 51 passed, 9 skipped, 367.69 s
                test_inexpressible_rule_is_rejected_and_writes_nothing
                AssertionError: the store went from 89 rules to 91 on a refusal.
```

Alone, both are green — `check-ge` 33 passed in 104.14 s, and F12's eight checks green in every solo
run of the day. **The cause is one value.** Both layers pin `DQ_SCHEMA=dq_check`, both *write* to
it, and the store is append-only (F6) — so a check that counts rules before and after an action is
reading a number a second process is also moving.

**The F12 check is right and its sentence is right**, which is the part worth being clear about: *"a
stored non-rule reports coverage the table does not have"* is exactly the assertion that has to stay
exact, and making it tolerant of a moving count would delete the check while leaving it green. What
was wrong was running two writers into one append-only schema at once.

**Fixed by `dq-cyi.4`, and neither assertion was touched.** The two layers now have a scratch schema
each — `dq_check_ge` for the GE layer, `dq_check` for the browser layer and the API process it
drives — and the name is derived from the MARKERS pytest selected rather than exported by a target,
so it is not a value a shell, a `.env` or a copied command line can get wrong (`tests/scratch.py`).
Neither layer writes to the demo store `dq` and the derivation refuses to be pointed there.

**Two guards, because there are two ways into the wrong schema and neither may be silent:**

- **One process is one schema.** `pytest_collection_modifyitems` refuses a run that selected both
  layers, before it writes a row. Bare `pytest` (which collects everything) now exits 4 with
  `ERROR: this run collected the e2e and ge layers together, and they write to different scratch
  schemas (dq_check, dq_check_ge)` rather than half-running a browser layer into the GE layer's
  store.
- **The browser layer is two processes on one store.** Its writes are split between pytest
  (`conftest.coverage_records`) and an API process a person starts by hand, and only a matching
  `DQ_SCHEMA` makes those the same store — so the fixture asks the server for a run record it has
  just written and fails by name if the server cannot see it (`scratch.agrees`). Without that, a
  server on the wrong schema is not an error anywhere: it is F10's middle bucket coming up empty
  and a check blaming the product. **Shown to go red**, by starting a second API process on
  `DQ_SCHEMA=dq_check_ge` and pointing one F10 check at it:

  > `Failed: the API process on http://localhost:8123 cannot see run record
  > 319d19e5-92ad-4096-8b20-2000503001b6, which this process just wrote to dq_check (HTTP Error
  > 404: Not Found), so the two are on different schemas. Start it with DQ_SCHEMA=dq_check …`

**Shown, not asserted — the two targets run at the same time on one machine, both green:**

```
# 2026-08-18 08:50:29 IST — all three targets launched from one shell, at once, on one machine
make check      187 passed, 96 deselected, 1 warning in 2.88s                        CHECK_RC=0
make check-ge    33 passed, 250 deselected, 1 warning in 103.64s (0:01:43)              GE_RC=0
make check-ui    52 passed, 8 skipped, 223 deselected, 1 warning in 368.17s (0:06:08)   UI_RC=0
```

The 2026-08-17 measurement, kept because it is the one the bead closed on: `check-ge` 33 passed in
104.35 s, `check-ui` 53 passed / 8 skipped in 382.15 s. The pass count moved from 53 to 52 because
one visual state was deleted for being a duplicate photograph (§4.3) and another stopped
self-approving (`dq-zyt`) — the skip count is unchanged at eight because those two cancel.

Those are the same numbers each target posts alone, and the eight skips are the two unnamed delivery
targets and the six unapproved visual baselines — none of them new. The GE run is also the stronger case: `make
reset-scratch ARGS=dq_check_ge` had dropped its schema minutes earlier, so it built its store from
nothing while the browser layer was writing to `dq_check` beside it.

**Resetting them.** `make reset-scratch` drops both scratch schemas; `make reset-scratch
ARGS=dq_check_ge` drops one, which is the common case. `DROP SCHEMA … CASCADE` is the only reset an
append-only store has, and it runs as `dq_system` — which owns these schemas because
`app/rules/store.py` created them — so it needs the system DSN and never the owner's. Any name
outside `tests/scratch.py` is refused, which is what makes `ARGS=dq` an error. Reset ahead of a full
run of a layer rather than of one check: `make check-ui` rebuilds what it needs in file order, and
`conftest.rule_id` fails on an empty store by design.

#### 4.7.3 Two PROCESSES of one layer writing into one scratch schema (bead `dq-mc0`)

**The same shape as §4.7.2, one level finer, and it survived that fix.** SPEC §7's stack schema was
the constant `dq_scenario` and the flow DROPS it on the way in, because §7 opens on *"No rules
exist"* (SPEC §7.1). That is exactly right for one runner and wrong for two: a second `make
check-ui` dropped the schema underneath the first and started writing into it. Found at close-out on
2026-08-18 by running `-m e2e` while another process was doing the same:

```
FAILED tests/e2e/test_spec_section_7.py::test_spec_section_7_end_to_end_scenario
AssertionError: the store holds 3 rule(s) for orders after a screen of proposals.
Nothing is persisted until somebody accepts it (SPEC F12).
```

**That assertion is right and was not loosened** — it is F3's whole promise, that a machine proposal
is not a stored rule. What was wrong was two writers in one schema, and reading `dq_scenario`
straight afterwards said so: 19 rule revisions and 2 run records written between 12:10:59Z and
12:12:48Z, a complete §7 lifecycle (proposed → accepted, needs_review, rejected), while this
process's §7 had aborted at step 2 at ~12:11:00Z. One run cannot produce both. **And it passed
alone, which is the tell:** `pytest -m e2e tests/e2e/test_spec_section_7.py` → 1 passed in 170.18 s.

**Why `dq-cyi.4`'s fix does not reach it.** That one derives the schema from the markers pytest
COLLECTED, which is a fact about the layer. Two processes of the same layer collect the same
markers, so a marker cannot tell them apart. The discriminator has to be a property of the process,
and the cheapest one that already exists is its pid: `SCENARIO_SCHEMA` is now
`f"dq_scenario_{os.getpid()}"` (`tests/e2e/scenario_stack.py`). The alternative the bead allowed —
refusing the second runner by name — was rejected for costing more machinery (a connection held open
for the whole run to hold a lock) while taking away the concurrency §4.7.2 had just bought.

**The graveyard is swept by the drop that was already there**, so there is no second mechanism and
no teardown: `_reset_schema` also drops the `dq_scenario_*` schemas whose pid is no longer a live
process, plus the pre-fix literal `dq_scenario`. It never takes one a live run owns — that would be
this same bug with an extra step, which is what `_stale_scenario_schemas` exists to refuse.
**Ceiling, marked `ponytail:` in that function:** liveness is asked LOCALLY against a schema list
that lives on a shared Supabase, so a run on another machine whose pid happens to be free here could
be swept. One developer, one laptop today; the upgrade path is a session advisory lock per schema
(`pg_try_advisory_lock`, held for the run), where a free lock means nobody is using it anywhere.

**Shown, not asserted — two §7 flows launched within ~2 s of each other on 2026-08-19, overlapping
windows, both green:**

```
run A   pytest -m e2e tests/e2e/test_spec_section_7.py   1 passed in 141.24s   exit 0
run B   pytest -m e2e tests/e2e/test_spec_section_7.py   1 passed in 133.35s   exit 0
```

The schemas afterwards, read straight off `information_schema`, are the other half of the evidence —
two distinct per-pid stores, and no `dq_scenario`:

```
['dq', 'dq_check', 'dq_check_ge', 'dq_hostile', 'dq_scenario_33664', 'dq_scenario_33964']
```

Both survive their own run, which is the documented idempotent-not-self-cleaning behaviour, and the
next §7 run sweeps them because those two pids are now dead.

**The cheap half is a unit check, so the next regression costs no e2e run to catch.**
`tests/test_scenario_schema_isolation.py` asserts that the schema is derived from this process
(`prefix + os.getpid()`, never a literal) and that the sweep returns only the dead-pid schema and
the legacy literal — leaving this process's own, a live sibling's, `dq_check` and `dq` alone. It
needs no database and no marker, so it rides in `make check`.

**Still one writer per schema, one level up: two whole `make check-ui` runs at once are NOT green.**
§7 no longer collides, but the rest of the browser layer shares `dq_check` through one API process,
and three checks there count rules before and after an action
(`tests/e2e/test_f12_translation_desk.py`, `test_f12_refused_judgment.py`). That is the same shape a
fourth time and it is out of `dq-mc0`'s scope by the bead's own words; the acceptance above is
therefore two §7 flows, which is what the bead asks for.

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

`tests/test_inv5_sampling_disclosure.py` for the first two layers and
`tests/e2e/test_inv5_surface.py` for the third, which needs a browser and therefore belongs in
the browser layer. Three layers, because disclosure can be lost in three different places.

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

**The same walk runs on BOTH screens that render an atom**, as of the craft pass: `/tables`,
where the atom sits in a table cell, and `/runs/[recordId]`, where a component takes a reading
apart into status, magnitude and evidence — the screen SPEC F13 names for this token, and the one
where losing the clause is easiest. It covered `/tables` alone until then, and widening it
immediately caught a real hole: `tests/conftest.py::completed_run` was composing its records'
per-result status as `verdict.upper()`, a SECOND WRITER, so a seeded run that scanned 10,000 of
50,000 rows rendered a bare `ERRORED` on F13 with the disclosure nowhere on the row. The fixture
now composes through `status_atom()` like a real run does.

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

Each of these is a decision, not an oversight. The sentence that used to close this line —
*"there is no application code yet"* — is no longer true, so the rows were re-read one by one at
close-out rather than left to inherit an argument they had outlived. Two rows have been CLAIMED
(layout shift, docker-compose), one has fired twice and been recorded rather than installed
(security scanning), **one has fired and is NOT done — duplication detection, which is stated as an
open gap below rather than quietly re-deferred** — and the rest still hold for the reason each
states. A
"not verified" table nobody re-reads after the code arrives is how a deliberate gap turns into an
undiscovered one.

| Not verified | Why not, and the trigger to add it |
|---|---|
| **Duplication and unused-export detection** | ~~Trigger: the first `npm install`.~~ ~~New trigger: the first bead that ships a real screen (F10–F13).~~ **BOTH TRIGGERS HAVE NOW FIRED AND THIS IS NOT DONE.** F10–F13 shipped in wave 3; `web/` is 15 TypeScript files rather than 9 near-empty ones, so `knip` and `jscpd` would no longer print zeroes and the argument that re-set the trigger has expired. It is recorded here as an **open gap**, not re-deferred a third time: re-setting a trigger twice is how a deliberate omission becomes an undiscovered one. The partial substitutes that do exist are named so nobody overestimates them — `eslint --max-warnings 0` catches unused *locals* (not unused exports), ruff catches the Python half, and §6's own size thresholds cap files and functions. Neither tool has ever been run on this repository. |
| **Coverage percentage thresholds** | A coverage number over 5 real tests measures nothing, and a threshold set now becomes a target to game. Trigger: after the first feature ships with real tests. |
| **Mutation testing** | Correct answer to "are the tests any good", wrong cost at 5 tests. |
| **Performance / latency budgets** | The measurement now exists (LT-1b) and the answer is still no — deliberately, see §9.1. The environment moves more than the budget would: the same 10-rule cell measured 14.84 s at the start of the run and 13.61 s at the end (−8.3%) on a burstable free tier, and the pooled 100,000-row cell spread 10.17–22.62 s across five runs. A threshold above that noise (say 25 s) passes for a product nobody would wait for; one at the median flakes weekly and teaches people to re-run a red gate. What replaces it is a **shape** assertion that cannot flake: F13's progressive check (§4.1) asserts states present at one moment, never elapsed time. Trigger: a dedicated non-burstable instance, or one real user complaint about speed — then the budget is set from a re-measurement on that instance, not from these numbers. |
| **Load and concurrency** | One env-configured connection, one user at a time. Non-goal. |
| **Cross-browser and mobile viewports** | Two named desktop users. Chromium only until someone asks. |
| **Security scanning (SAST, dependency audit)** | ~~Trigger: the first lockfile.~~ **Fired with `dq-5pb.1`** — `web/package-lock.json` exists. `npm audit` reports **0 vulnerabilities across 346 packages** (2026-08-16), so the finding is recorded rather than the check installed: `npm audit` queries the registry, and putting it inside `make check` would break the "needs no network" promise §1 makes about every layer. ~~New trigger: the deploy bead (`dq-cyi.1` · B22), where a network-dependent audit belongs — beside the Dockerfile, not on every save.~~ **That trigger fired too.** Re-run beside the Dockerfile on 2026-08-17: `npm audit` **0 vulnerabilities across 347 packages**, and `npm audit --omit=dev` **0** — so the two images ship nothing with a known advisory. Recorded, still not installed in `make check`, for the same network reason. Next trigger: a dependency change, i.e. a diff to `web/package-lock.json` or to the pinned `pip install` line in `Dockerfile.api`. |
| **Contract tests between backend and frontend** | Both live in one repo and ship together; the e2e flow already crosses the seam. Trigger: the seam becoming a deployment boundary. |
| ~~**Cumulative layout shift**~~ | **CLAIMED with `dq-5pb.1`** — the shell paints, so the number exists. `test_no_layout_shift_on_first_paint`, budget 0.1, §4.5. |
| **A CI runner** | No `.github/`. `make check` is the contract; wiring it to a runner is 10 lines whenever a second machine needs it. |
| **Pre-commit / Stop hooks** | Step 6 of the workflow. The gate has to exist and be shown to block first — it now is (§5, INV-3). Wiring is the next step, not this one. |
| ~~**`docker-compose` build verification**~~ | **CLAIMED with `dq-cyi.1` (B22)** — the trigger this row named was "writing the Dockerfile", and `Dockerfile.api`, `Dockerfile.web` and `docker-compose.yml` now exist. It is not verified by a build-succeeds assertion: `tests/e2e/test_delivery.py::test_compose_stack_serves_the_smoke_route` points the existing hygiene smoke at the running stack and requires the same 21 green cases, because an image that builds and serves a broken page is not a delivery. See §8.1. |

---

### 8.1 What B22 actually proved, and the one half it did not

**Proved, on this machine, 2026-08-17.** `docker compose build` produced both images from a
clean context in 1 m 52 s — `.dockerignore` excludes `web/node_modules`, `web/.next`, `.venv` and
every cache, so `npm ci` and `next build` ran inside the image from the committed lockfile rather
than copying darwin/arm64 artefacts. `docker compose up -d` brought `api` to *healthy* and `web`
up behind it, and `APP_URL`/`DQ_API_URL` pointed at the published ports returned **21 passed, 8
deselected in 75.00 s** — the same three hygiene checks over the same seven routes that
`make check-ui` runs locally. `POST /proposals/payments` answered with real model proposals in
9.9 s, which is the one fact a page render cannot establish: the Claude Code CLI is installed in
the api image and authenticates from the environment, so F3 and F4 are alive in the container and
not merely importable. Neither image contains a `.env` or any credential string (`find / -name
.env` empty, `grep -rl 'sk-ant-oat01\|supabase.co' /srv` empty).

**Shown to block, the same way §4.2 shows the browser layer blocking.** `COMPOSE_APP_URL` at a
dead port fails in 0.20 s with *"a named stack that is not running is a broken delivery, not an
absent one"* — it does not skip. And the harness's own rule caught the first draft of this check:
both test functions delegated their assertion to a helper, and
`test_no_test_function_is_vacuous` failed the gate on them by name until the verdict was returned
and asserted at the call site.

**NOT proved: the deployed URL.** `test_deployed_url_serves_the_smoke_route` exists, reuses the
same smoke, and **pends** — no deployment has been stood up, and nothing here should be read as
saying one has. It fails rather than skips the moment `DEPLOYED_APP_URL` names something silent.
It also needs `DEPLOYED_API_URL`, which is a real cost of the shipped topology rather than an
oversight: the Python process is not public, because `web/app/api.ts` reaches it server-side —
which is exactly what gives this product no CORS configuration and no API base URL in the
browser bundle.

**The environment trap, documented rather than hidden.** `db.<ref>.supabase.co` publishes AAAA
records only, and Docker Desktop gives containers no IPv6 route, so the first `docker compose up`
died at `psycopg2.OperationalError: ... (2406:da18:1691:a200::1a6e), port 5432 failed: Network is
unreachable` while `psql` from the host was fine. The stack above was verified against Supabase's
**session pooler** (IPv4, port 5432, user `<role>.<ref>`) — *not* the transaction pooler on 6543
that LT-1b measured 21% slower. **The code's default is unchanged**: F8 still reads
`SUPABASE_DB_URL_DIRECT` and LT-1b's choice stands; what moves is the value in a `.env` on a host
without IPv6. Detection and fix are in README, "The IPv6 trap".

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

**What is done, at close-out on 2026-08-17.** All fifteen features have shipped and every one with a
UI surface is checked by a browser-driven check, which is what the rule at the bottom of this section
demands. Five of six epics are closed with per-criterion evidence in their close reasons —
`dq-5pb`, `dq-yov`, `dq-3bp`, `dq-klv`, `dq-rbf`. **What is not done is three things and they are
named, not implied:** no deployed URL answers the smoke (`dq-cyi.1`, §8.1); **no visual baseline has
ever been approved by a human**, so the visual layer asserts nothing yet — and for two hours on
2026-08-17 this document said otherwise, because a re-shot baseline had self-approved through a hole
in `_approved()` (`dq-zyt`, §4.3); and
duplication/unused-export detection has had its trigger fire and has not been run (§8). The
`PENDING —` lines in a real run say all three out loud on every invocation, which is the point.

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
