# HANDOFF — AI-Powered Data Quality Assistant

**Read this first.** It exists so a fresh session can resume without re-deriving anything.

Last updated: 2026-08-18 · **after the live-deployment defect wave.** All fifteen SPEC features have
shipped, **47 of 52 beads are closed, all seven epics are closed**, and the product is
**deployed**:

| | |
|---|---|
| app | https://web-production-d242f.up.railway.app |
| api | https://api-production-3d8d9.up.railway.app |

Two Railway services from this repo, each with its own Dockerfile.

> ### THE LIVE URLS NOW CARRY THE DEFECT-WAVE FIXES. *(corrected 2026-08-19)*
> This box previously warned that the deployment was built from `ea9a179` and carried none of the
> four hostile-QA fixes. **That is no longer true — Railway has been redeployed from `2373888`**
> (`173609e` "Fix the four defects hostile QA found on the live deployment"). Re-measured against
> the live app on 2026-08-19, not argued:
>
> | probe | result |
> |---|---|
> | `GET /rules/not-a-uuid` | **404** — was a 502 naming `api.railway.internal:8000` |
> | `GET /tables/orders/rules` as **expert** | 42,361 b · `expect_column` **0** · `kwargs` **0** |
> | `GET /tables/orders/rules` as **engineer** | 47,666 b · `expect_column` 48 · `kwargs` 20 |
>
> The `/runs/<recordId>` leak (`dq-220`) is closed on live too, and the demo store was reseeded at
> `2026-08-18T12:53`, so the QA pass's writes are gone and the ERRORED/sampled demo states are back.
> **A reviewer opening the live URL today is looking at the fixed product.** What is still only in
> this working tree is the *newer* work — `dq-8zj`'s handle change and `dq-mc0` — not the defect wave.

**The gate, re-measured at close-out on 2026-08-18 (§2 has the block):** `make check` **201 passed,
0 skipped, exit 0**; `make check-ge` **33 passed, exit 0**; the browser layer **63 passed, 2 failed,
2 skipped**, and both failures are two visual baselines that the fixes below genuinely changed —
they need a person's eye, which is the one approval no agent may give.

**What is left is FIVE beads and it is not all human work any more.** One act needs the author, the
rest is engineering:

1. **Look at two PNGs and `git add` them.** All six baselines were approved by the author in
   `2781c1f`, so the visual layer now genuinely compares — four states pass. Two no longer match
   because the screens honestly changed: `tables-three-buckets` lost `lt1a_probe` (`dq-5da`) and
   `run-record-in-flight` lost the domain expert's `<details>` panels (`dq-220`). §9 has both.
   `dq-vix` and `dq-dkq` are held by nothing else. **No agent may do this one.**
2. **`dq-8zj`, and it is engineering rather than a decision.** It is the one thing keeping `dq-220`
   open: a proposal's checkbox carries its compiled `{type, kwargs}` into the domain expert's
   document, because an unsaved proposal has no id to be addressed by. Measured, not argued —
   `dq-220`'s notes have the byte counts.
3. **`dq-mc0` is done and proven** — SPEC §7's stack schema carries the pid, two §7 flows ~2 s apart
   are both green, and the sweep leaves no graveyard (§2, §4.7.3 of VERIFICATION). What is left of
   it is a commit and a close. P3, and it was the third instance of one shape (§2, §6).

**And one thing that is neither**: put `DEPLOYED_APP_URL` and `DEPLOYED_API_URL` in `.env`. The
deployment check passed against the live URLs when they were exported by hand (`dq-cyi.1`), and
pends by name on every run that has not been told where the deployment is.

**The AI-usage write-up — a quarter of the grade — is written and its bead is closed:
[`AI_USAGE.md`](./AI_USAGE.md) (`dq-803`).**

---

## 1. What this is, in three sentences

A take-home case study (`QAFD.pdf` in this directory) for an AI-powered data quality assistant. A
domain expert states an expectation in plain English; the system turns it into a Great Expectations
check it has already proven will run, executes it against a PostgreSQL table on Supabase, and reports
failures in the same language the expectation was written in. It is graded on four equally-weighted
axes — AI-first development, product thinking, technical implementation, and **how AI tools were used
to build it** — so the process is part of the deliverable, not just the code.

---

## 2. Where we are

Following the author's own workflow (`software_development_workflow.md`, "Prompt Pack v4"), **FULL**
tier, with one deliberate substitution: **the Ralph/autonomous loop is NOT used.** The deterministic
gate it depends on is kept; the loop driver is replaced by attended, one-task-at-a-time sessions.

| Step | Stage | Status |
|---|---|---|
| 0 | Sharpen | ✅ |
| 0.25 | Scope — FULL pack, MVP feature ceiling | ✅ |
| 0.5 | Challenge | ✅ |
| 1 | SPEC | ✅ `SPEC.md` **Rev 0.4, FROZEN**. Rev 0.3 said out loud what O-2 had settled; Rev 0.4 amended exactly one acceptance clause, F12's, for the chosen UI direction — see §5. Every open item is now resolved |
| 1.5 | Out-of-the-box expansion | ✅ one candidate surfaced, argued against, declined |
| 2 | Learning tests | ✅ **4 of 4 executed** against real dependencies → `learning-tests/FINDINGS.md` |
| 3 | Tasks + DoD | ✅ 6 epics + 27 task beads (3 filed *during* the build, which is the point of a live tracker) → `bd list` |
| 4 & 6 | Verification gate | ✅ **built, green, and shown to block** — now with a real browser layer over a real app → `VERIFICATION.md` |
| 5 | Build (attended) | ✅ **three waves, all fifteen features.** Wave 1: the boundaries and the rule domain (E1 partial, E2). Wave 2: the privilege split, discovery, proposals, authoring, execution, results (E3, E4). Wave 3: the two front doors, the delivery stack and SPEC §7 end to end (E5, E6 partial) |
| 7.5 | Craft review | ✅ done inside wave 3 — it is why `VERIFICATION.md` says "after the craft pass" and why the eighth visual state was deleted rather than approved |
| 9 | Provenance | ✅ **`AI_USAGE.md`** — the fourth deliverable, written 2026-08-17 from the fourteen PR bodies, the four learning tests, the bead close reasons and `bd memories`. Bead `dq-803`. See §9 |

**Epics: all seven are CLOSED** — E1 `dq-5pb`, E2 `dq-yov`, E3 `dq-3bp`, E4 `dq-klv`, E5 `dq-rbf`,
the UX epic `dq-j15`, and **E6 `dq-cyi`, which closed at this close-out on its last child**:
`dq-cyi.1` stood up the two Railway services and
`test_deployed_url_serves_the_smoke_route` PASSED against the live URLs in 167.75 s — the first time
that check ran rather than pended. E6 being closed means the delivery promise is **kept**; it does
not mean the deployed build is **correct**, and its close reason says so at length.

### The gate, today

```
# 2026-08-18, close-out, after the four live-deployment defects were fixed
make check       201 passed, 0 skipped, 103 deselected, 6.61 s, exit 0
                 ruff → ruff format → mypy → pytest → eslint + tsc
make check-ge     33 passed, 269 deselected, 199.79 s, exit 0   (network + database)
browser layer     63 passed, 2 failed, 2 skipped, 237 deselected, 525.11 s, exit 1
                 real Chromium, two real processes, real Supabase, 6 real billed model calls
```

**304 checks collected**, and the arithmetic is worth keeping visible because it is what catches a
check that joined no layer: 201 default + 33 `ge` + 67 `e2e` + 6 `live` − 3 (`e2e` and `live` both)
= 304.

**Re-measured 2026-08-19 on the combined tree** (`dq-8zj`'s handle change plus `dq-mc0`): `make
check` **207 passed, 103 deselected, 0 skipped, exit 0**. The deselected count is unchanged, so the
six new checks are all default-layer and the arithmetic still closes: 207 + 103 = **310 collected**.

**The two browser-layer failures are the honest kind and neither is a code fault.**
`tables-three-buckets` and `run-record-in-flight` are visual baselines photographed before this
wave's fixes; the screens they photograph genuinely changed. **The layer is red until a person looks
at two PNGs**, which is exactly what that check is for. §9 has both.

**`make check-ge` was broken at close-out and is fixed.** As written it died with
`ModuleNotFoundError: No module named 'claude_agent_sdk'` and `Interrupted: 7 errors during
collection` in 0.76 s — a red target that had verified nothing. `-m ge` selects 33 checks, none of
which asks a model, but pytest **imports every module under `testpaths` before it applies a
marker**, and seven of them reach `app/model.py` through `suggest` / `authoring` / `app.api.server`.
The recipe now carries `--with claude-agent-sdk==0.1.23`, the same `--with` `VERIFICATION.md` §1
already calls load-bearing on the API process's line. With it: 33 passed, 199.79 s, exit 0.

**`check-ge` and `check-ui` may be run AT THE SAME TIME** (bead `dq-cyi.4`). They used to share
`DQ_SCHEMA=dq_check` and take each other red with nothing wrong with either; they now have a scratch
schema each — `dq_check_ge` and `dq_check` — derived from the markers pytest selected, so it is not a
value a shell or a `.env` can get wrong, and a process that collected both layers is refused before it
writes a row. Neither ever writes to the demo store `dq`. `VERIFICATION.md` §4.7.2 has both failures,
both guards and the green concurrent run. `make reset-scratch [ARGS=dq_check_ge]` drops them.
`make check-ui` also needs its two processes already running — the command lines are in
`VERIFICATION.md` §1, and the API one must carry `DQ_SCHEMA=dq_check` or the layer fails by name.

**A THIRD SHARED-SCHEMA COLLISION, and it is FIXED in this tree** (`dq-mc0`, P3, filed at close-out
on 2026-08-18, fixed 2026-08-19). `tests/e2e/scenario_stack.py::SCENARIO_SCHEMA` was the literal
`dq_scenario` and SPEC §7 **drops it on the way in**, because §7 opens on "no rules exist" — right
for one runner, wrong for two. Seen at close-out as `AssertionError: the store holds 3 rule(s) for
orders after a screen of proposals`, an assertion that is exactly right and was not loosened, while
`dq_scenario` showed 19 rule revisions and 2 run records written by the *other* process inside the
same 100 seconds. A marker cannot tell two processes apart, which is why `dq-cyi.4`'s fix did not
reach this one; **the schema now carries the pid** — `dq_scenario_<pid>` — and the way-in drop
sweeps the ones whose process is gone, never one a live run owns. **Shown, two §7 flows launched
~2 s apart:**

```
run A   pytest -m e2e tests/e2e/test_spec_section_7.py   1 passed in 141.24s   exit 0
run B   pytest -m e2e tests/e2e/test_spec_section_7.py   1 passed in 133.35s   exit 0
information_schema afterwards:
['dq', 'dq_check', 'dq_check_ge', 'dq_hostile', 'dq_scenario_33664', 'dq_scenario_33964']
```

Two distinct per-pid stores and no `dq_scenario`. `VERIFICATION.md` §4.7.3 has the whole account,
the `ponytail:` ceiling on the sweep, and the unit check that catches a regression without paying
for an e2e run (`tests/test_scenario_schema_isolation.py`). **Two whole `make check-ui` runs at once
are still not green** — the rest of that layer shares `dq_check` through one API process and three
checks there count rules before and after an action. Same shape a fourth time, out of `dq-mc0`'s
scope by the bead's own words, and worth its own bead.

**Zero skips in `make check`.** That number used to be 28 and every one of them was a `PENDING —`
line naming what it waited for; they are all assertions now. The **two** remaining skips are both in
the browser layer and both honest, and they are now the *same* skip twice: nobody has named a
deployed URL. `COMPOSE_APP_URL` and `DEPLOYED_APP_URL` are unset — and the second of those is a live
Railway service that exists. §9.

**A BUILT `web/.next` IS A SILENT LIAR, and it cost a full browser-layer run at close-out.**
`npm --prefix web run start` serves whatever was last built; it does not notice that
`web/app/api.ts` is newer than `web/.next/BUILD_ID`. A whole `-m e2e` pass was taken against a build
that predated the fixes it was checking, and it went *green*, which is worse than red. It also
produced a phantom defect — the not-found page appeared to offer the engineer's door to a domain
expert — that vanished on a rebuild. **Rebuild before you believe a browser-layer result:**
`find web/app -newer web/.next/BUILD_ID` answers the question in one line.

**Working tree, at close-out 2026-08-18.** Everything through wave 4 is **merged to `origin/main`**
— PRs #12–#15 — `main` is up to date with its remote, and **`ea9a179` is what Railway is serving.**
What is uncommitted is **this wave: the four live-deployment defects.** Nine new files
(`app/api/refuse.py`, `app/db/unreachable.py`, `web/app/framework.ts`, `web/app/not-found.tsx`,
`DEMO.md`, and four test files) and edits to twenty-eight more, including eight `web/app/` files and
nine test files. Two of them are worth naming here because they cut the other way from the rest:
`tests/test_code_quality_thresholds.py` was **strengthened** (its web scan globbed `*.tsx` alone, so
no `.ts` file was ever measured and `web/app/api.ts` reached **451 lines** while the size check
reported green), and `Makefile` gained the `--with` that makes `check-ge` collect at all.
**Branching, committing and the PR are the author's, not an agent's** (§4a).

The six baseline PNGs are **committed** (`2781c1f`) and therefore approved. Two of them no longer
match and are the author's next look (§9).

---

## 3. Artifacts

| What | Where |
|---|---|
| The brief | `QAFD.pdf` |
| **SPEC (frozen, Rev 0.4)** | `SPEC.md` — 15 features with observable acceptance, 6 invariants, non-goals, §7 end-to-end scenario, §9 open items |
| **Verification harness** | `VERIFICATION.md` (the design) + `Makefile` + `tests/` + `init.sh` |
| **How to run it** | `README.md` — docker compose, credentials, and "The IPv6 trap" |
| Learning-test findings | `learning-tests/FINDINGS.md`, raw numbers in `lt1b_results.json` |
| **AI-usage deliverable (the fourth graded axis)** | `AI_USAGE.md` — what was delegated, what was refused, what the gate caught, what it misses. This is what the design doc's Appendix D pointed at |
| Demo dataset | `seed/MANIFEST.md`, `seed/seed_demo_data.py` — loaded in Supabase |
| **Demo RULE fixture** (bead `dq-vix`) | `seed/seed_demo_rules.py`, run by `make demo-fixture` — eight rules and two run records in the demo store `dq`. It is what the six visual baselines photograph, and **a reviewer needs it or the product looks broken while working perfectly** (`README.md`, "Run it") |
| UX variants + judge scores | `design/README.md`, four self-contained HTML files; **the chosen one is `design/ux-variant-workbench.html`** |
| **Architecture design doc** | https://claude.ai/code/artifact/97a3df0c-7ae3-4e8a-94fe-6e23e8b6f0f9 — problem framing, designs not chosen, risk register, Appendix D (AI-usage log — **should now point at `AI_USAGE.md`**; the artefact is hosted, so only the author can edit it) |
| **The live deployment** | app https://web-production-d242f.up.railway.app · api https://api-production-3d8d9.up.railway.app — two Railway services, one Dockerfile each, built from `ea9a179`. **It does not carry this tree's fixes** (§9) |
| Demo run of show | `DEMO.md` — nine minutes, seven beats, one browser; SPEC §7 performed rather than asserted, on `orders` and `payments` |
| Task tracker | beads, prefix `dq` — `bd ready`, `bd list`, `bd show <id>` |
| Credentials | `.env` (gitignored); shape documented in `.env.example` |
| The author's workflow | `software_development_workflow.md`, `HOW_I_BUILD.md` |

### The map of the code, so nobody re-reads it to find out

| Module | Feature | What it owns |
|---|---|---|
| `app/db/system.py` | — | the one system-role connection; hands out a **cursor**, never a connection, because the API threads |
| `app/rules/schema.py` | — | the one door to the **analysis** role, which cannot write anywhere |
| `app/db/tables.py` | F1 | every table with shape, estimated size and **accepted**-rule coverage |
| `app/dq/profile.py` | F2 | one statistics query per table, cached |
| `app/rules/suggest.py` | F3 | proposals with evidence, unsaved, catalog-only |
| `app/rules/authoring.py` | F4 | English in, a validated rule or an honest refusal out |
| `app/rules/catalog.json` | F5 | the 15 expectation types, as data, counted by everyone from this file |
| `app/rules/store.py` | F6 | four states: proposed / needs_review / accepted / rejected, append-only revisions |
| `app/dq/ge_runtime.py` | F7 | **the only module that imports Great Expectations** (INV-3), one context per process |
| `app/rules/validator.py` | INV-2 | nothing invalid reaches the store — validate *before* persist |
| `app/dq/run.py` | F8 | the run as a **generator**, one validate per rule |
| `app/api/server.py::_run` | F8 | that generator as **NDJSON over one chunked POST** (O-4) |
| `app/dq/normalise.py` | F9 | the result model; `errored` is a **third** state, not a kind of failure |
| `app/dq/runs.py` | F9 | immutable run records; only a COMPLETED run enters the cache |
| `app/dq/status.py` | all | **THE ONE WRITER** of verdicts, refusals, evidence lines and every load-bearing sentence |
| `web/app/role.ts` | F11/F14 | role as a **cookie**, never a route segment |
| `web/app/run/route.ts` | F13 | the one address the browser itself calls; a pass-through, never a poll |
| `web/app/api.ts` | — | **the only file that knows the API's address.** Two doors out, `call()` and `stream()`, and one `fetch` between them, so neither can be the one without a `catch` |
| `web/app/framework.ts` | F12 | **may this reader see the framework** — asked once, for every screen, by both doors above; and the redaction that makes the answer stick (`dq-220`) |
| `web/app/not-found.tsx` | — | the one page whose job is to be somewhere to leave from. Reached by a mistyped id, not only a mistyped path |
| `app/api/refuse.py` | — | every byte this server writes back, and the promise that it always writes some. 4xx caller / 503 database / 500 incurious (`dq-abs`) |
| `app/db/unreachable.py` | — | what every module says when a database does not answer — the driver's words to the log, one neutral sentence to the reader |

---

## 4. Do next

```bash
./init.sh     # credentials → database smoke → app install+build → make check
bd ready
```

**Five beads are open and three of them are agent-shaped.** Nothing below was closed around, and
nothing was `--force`d. **Also set `DEPLOYED_APP_URL` and `DEPLOYED_API_URL` in `.env`** — not a
bead, but it is why two checks still pend on every browser-layer run against a deployment that
exists.

- **`dq-8zj` · P2 — the one piece of engineering left, and it is what holds `dq-220` open.**
  A machine proposal has no row in the store (F3), so the checkbox that accepts one carries its
  whole compiled spec as its value (`web/app/tables/[table]/rules/token.ts`). Measured off the
  socket at close-out: `/tables/orders/rules?propose=1` as `dq-role=expert` is **562,768 bytes with
  35 occurrences of `expect_column` and 35 of `kwargs`.** The door cannot strip it — taking
  `type`/`kwargs` out would leave the domain expert a checkbox that accepts nothing. It needs a
  **handle instead of a spec**, which is a change to the accept path. When it lands, add a
  `?propose=1` entry to `tests/e2e/test_framework_absence.py`'s `QUERIES` so the propose screen
  joins the raw-response check by mechanism rather than by memory.
- **`dq-220` · P1 — open on `dq-8zj` and on nothing else.** Its own defect is fixed and proven: the
  two `/runs` routes are clean, the stream door is clean, and the decision moved into one door
  (`web/app/framework.ts`). Its acceptance is written in absolute terms — *no `expect_column`, no
  `kwargs`, on any route* — and the numbers above say that is still false on one address, so it
  stays open rather than closing around it. Full before/after byte table in its notes.
- **`dq-vix` · B25 and `dq-dkq` · B28 — both held by the same two PNGs.** The engineering under
  both is done and proven, and the approval they were waiting for has **happened**: all six
  baselines are committed (`2781c1f`), four of the six compare and pass. Two do not, because this
  wave's fixes changed the screens they photograph — `tables-three-buckets` and
  `run-record-in-flight`, §9. Look at those two, `git add` them, re-run, and both beads close on
  that output.
- **`dq-mc0` · P3 — fixed in this tree and proven, open only until it is committed and closed.**
  Two concurrent §7 runs collided on the constant schema `dq_scenario`; it now carries the pid, and
  the same way-in drop sweeps the schemas whose process is gone. Two §7 flows ~2 s apart are green
  (141.24 s and 133.35 s, both exit 0) and left two distinct per-pid schemas behind. §2 has the
  evidence, `VERIFICATION.md` §4.7.3 the account. It was the third instance of one shape — and the
  fourth is already visible: two whole `make check-ui` runs still share `dq_check`.

**Read `bd show <id>` before starting anything** — each bead carries its own acceptance, its check
order (cheapest deterministic first), and an explicit out-of-scope list.

---

## 4a. Git discipline — branch, one commit per bead, PR

**Never commit to `main`.** Every unit of work gets its own branch, named for what it is. Each
completed bead gets its own commit with the bead ID in the subject; work that is not a bead — setup,
docs, spec revisions — still gets its own focused commit. Then push and open a PR with `gh pr create`
and **do not merge it**: the author reviews and merges. Put the finding in the PR body, not only in
the bead notes.

Agents run **no state-changing git command** on this project. PRs #1–#12 are merged; wave 2 is pushed
on `build/wave2-engine`; wave 3 is uncommitted.

---

## 5. Decisions already made — do not re-litigate

The wave-3 decisions are first, because they are the ones a fresh reader is most likely to try to
reopen.

| Decision | Why |
|---|---|
| **The UI direction is `design/ux-variant-workbench.html` — "Diglot Workbench"** | The author's call, overriding the judge panel's preference for Run Ledger (23.0 against 25.4). Its idea is a **bilingual split**: plain English and the GE configuration as facing pages, warm paper tint for English, cool for the framework |
| **SPEC amended to Rev 0.4 for it, rather than absorbed silently** | Workbench's facing panes are incompatible with F12's original *"collapsed by default"*. A frozen spec that quietly swallows an acceptance edit is worth less than no freeze, so the clause took a revision |
| **The GE configuration is ABSENT for the domain expert, not collapsed** | The stronger form of the original intent. It is not `display: none` and not a disclosure control: the payload is not even asked for, so view-source, a screen reader and a text browser all agree. A component deciding not to print a field it was handed is one refactor away from printing it. **Amended by `dq-220`:** asking is only half. The decision moved off the four pages that each made it — one of which forgot — into `web/app/framework.ts`, and the door STRIPS as well as not-asks, because `/records` sends the framework unasked and no query parameter would have protected the run screens |
| **The time-budget indicator is grafted in from the Reviewer variant** | The judges scored Workbench 6.5/10 on expert usability, second-lowest of four, and proposed this graft themselves. It is what keeps INV-1's five minutes honest **on screen**, and its arithmetic has four unit checks. The other half of the graft is Reviewer's "Accept — I vouch for this" copy, which lives in `app/dq/status.py` |
| **O-4 RESOLVED: NDJSON over one chunked POST** | One line of JSON per verdict, no Content-Length ever, `web/app/run/route.ts` passing the body through byte for byte. Not SSE (a GET-shaped protocol with reconnect semantics for a thing that must never be restarted) and not one request per rule (N connects to Singapore at 1.16 s each). **There is no address anywhere that answers "how is the run getting on"** — the only account of a run in flight is the response the caller is already reading, and a check fails the gate on a GET that reaches the run route |
| **The first stream event is the whole rule list, before any rule runs** | That is the *mechanism* that makes a blank spinner impossible rather than merely discouraged, and it is what F13's progressive clause rests on. Measured: one validate of three rules costs 7.94 s and shows nothing until 7.94 s; three validates cost 12.64 s and the first verdict lands at 2.98 s. Progressive costs ~1.6× the total and buys the first verdict 2.7× sooner |
| **The privilege split is in the database, not in the code** | Two roles: `analysis` cannot write anywhere (`app/db/roles.sql`), `system` writes only our own two tables. A code path that *cannot* write is worth more than one that promises not to |
| **Role is a COOKIE, not localStorage** | It decides what the **server** renders, so a value only the browser can read would mean rendering every page twice and moving it under the reader, against a 0.1 CLS budget. A cold request carrying no cookie gets the **domain expert's** view — the conservative direction, because a permalink arriving in someone's chat must not confront its reader with the framework |
| **No Ralph/autonomous loop**, but keep the gate | The gate is the part that survives; the loop driver is what current models have outgrown |
| **No row cap ships** (O-2, from LT-1b) | Capping to 100,000 rows (an 80% data loss) saves only 37%; at full size it is a *net loss*, because GE runs a query asset verbatim through a client-side cursor; and it breaks two catalog types outright with `KeyError: 'type'`. **INV-5's disclosure mechanism still ships**, carried by us from the asset definition into the stored result, with the cap switched **off** |
| **Execution is synchronous, but progressive** (O-3, from LT-1b) | Not a job queue. A worker returns the same total later plus a polling endpoint and a staleness problem |
| **F8 uses `SUPABASE_DB_URL_DIRECT` (5432)** | The transaction pooler is 21% slower on identical work — 17.94 s vs 14.84 s |
| **Exactly one GE context per process** (INV-3) | `gx.get_context()` is *process-global*: a second call silently orphans the first context's datasources, and the failure surfaces later at `validate()` naming a datasource that is sitting right there |
| **Curated catalog of 15 GE expectation types**, not the full registry | Smaller menu → better model output, less validation code, renderable UI |
| **Validate before persist** | Makes an invalid rule structurally impossible to save. The keystone decision |
| **One SQL stat query**, not a profiling module | Start minimal; deepen only the dimension that proves weak |
| **GE is a runtime, not the domain model** — exactly one module imports it | Survives GE's next breaking release; enforced in the gate, not by convention |
| **Two primary users**, not primary + secondary | Engineer owns coverage; domain expert owns whether a rule *means* the right thing |
| **Single-column and table-level rules only** | Multi-column deferred to v2 — the most common rejection, and the first thing to add next |
| **Inexpressible NL rules are rejected with a reason, never stored** | A stored `unsupported` rule implies coverage that does not exist |
| **Claude Agent SDK, all built-in tools disabled, `setting_sources=[]`, single call** | Subscription-token auth; `setting_sources=[]` stops the developer's global `CLAUDE.md` leaking into a server-side call |
| **Delivery: live URL *and* docker-compose** | "Working MVP" must not depend on the reviewer's machine. Half done — see §9 |
| **No feature-ledger file** | An earlier `verification/features.json` + `summary.py` was deleted: a fourth copy of the same intent, and it could be made to print `15/15 passes: true, verified_by: "vibes"` and exit 0. `pytest -ra`'s PENDING list and `bd list` replace it (`VERIFICATION.md` §10) |

Two things are **never** simplified away, at any scope: a suggestion always carries its evidence, and
any result derived from a sample says so — **inside** the same text node as the pass/fail state, not
adjacent to it.

---

## 6. Findings so far

**Full write-ups are in `learning-tests/FINDINGS.md`.** Read the LT-1b section in full before
touching F8, F9 or F13. Summary:

- **LT-1b · latency (`dq-e1d`).** The 10-rule shipping suite over 500,000 rows: **14.84 s** direct /
  17.94 s pooled; one rule alone 2.28 s. Cost is a ~2.3 s floor plus ~0.83 s per rule — lumpy per
  *rule*, not linear in *rows*. Only **3 rules** fit under 10 s at full size. GE's own Python is 21%
  of wall clock — more than the network.
- **LT-1a · GE on PostgreSQL (`dq-dww`).** `catch_exceptions` defaults to `True`, so an **ERRORED
  rule is visually identical to a FAILING one** — hence `errored` is a third result state.
- **LT-2a · object model and registry (`dq-chf`).** GE accepted **10 of 25 nonsense rules while
  reporting success**: compiling is not sense. That is why F12 renders `Compiled · shape OK` as a
  neutral token with no passing-verdict class, and why the validator has to enumerate.
- **LT-2b · Agent SDK (`dq-uco`).** 6.6 s and $0.041 per call. **The finding that matters:** every
  rule the model proposed was statistically true and business-naive — it did *not* propose
  `order_total >= 0`, the actual invariant. The meaning is not in the sample. Evidence lines and
  unsaved-proposal status are load-bearing, not decorative.

**Found during the build, and worth as much as the learning tests:**

- **Progressive costs 1.6× the total and buys the first verdict 2.7× sooner** (§5). Measured on the
  live table, not reasoned about.
- **A screenshot of a screen this layer writes to is a photograph of a database.** The review-queue
  baseline came out 1280×12430 and 1.3 MB, thirty-eight cards, most of them the same rule duplicated
  by earlier runs into an append-only store. That is what put five states in `DATA_DEPENDENT` —
  a list that no longer exists, because bead `dq-vix` removed the cause instead of the symptom.
- **Two visual states can be the same photograph.** `tables-bucket-two-errored` and
  `tables-three-buckets` produced byte-identical PNGs (same md5, two independent runs). The eighth
  state was deleted rather than approved.
- **`networkidle` is not a write barrier.** A click on a server action that redirects can leave the
  page "idle" again before the request has left, so a read taken straight after it arrives before the
  write. This cost one red `make check-ui` (bead `dq-cyi.3`) after the repository had already learned
  it twice elsewhere.
- **Two check layers sharing one append-only schema take each other red.** `make check-ge` and
  `make check-ui` both pinned `DQ_SCHEMA=dq_check` and both write to it, so a check counting rules
  before and after an action read a number the other layer was moving. Both went red when run
  together and both were green alone. The lesson is not "make the count tolerant" — that assertion
  is the one that catches a stored non-rule — it is "one writer per schema", and that is what bead
  `dq-cyi.4` shipped: a schema per layer, derived from the markers rather than exported, plus a
  refusal for a process that collected both. The two run together green now (VERIFICATION §4.7.2).
  **It has now happened a THIRD time, in the same shape every time: one schema name, two writers,
  and an append-only store that cannot forgive it** (§2 counts them). The third was SPEC §7's own
  stack schema, across two *processes* of one layer (`dq-mc0`): `dq_scenario` was a literal and the
  flow DROPS it on the way in, so a second `make check-ui` took the first one's store away and wrote
  into it, and the first then failed its own §7 assertion — *"the store holds 3 rules"* — on the
  other run's rules. **The pattern, now that there are three of it:** the discriminator has to come
  from something the colliding parties cannot share, and each instance needs one finer than the
  last. A marker names a layer and cannot tell two processes of it apart, so `dq-mc0` puts the
  **pid** in the name — `dq_scenario_<pid>` in `tests/e2e/scenario_stack.py` — and the way-in drop
  sweeps the scenario schemas whose process is gone, never one a live run owns, since sweeping those
  would be the same bug with an extra step. Two §7 flows ~2 s apart are green (141.24 s and
  133.35 s, both exit 0) and left two distinct per-pid schemas behind — `VERIFICATION.md` §4.7.3 has
  the run lines and the schema listing. `tests/test_scenario_schema_isolation.py` holds both halves
  as unit checks, so the next regression costs no e2e run to catch. **Read a fourth occurrence as a
  shared-name problem before reading it as a product bug** — and there is one waiting: two whole
  `make check-ui` runs still share `dq_check`.

**Found by a hostile QA pass against the LIVE deployment, 2026-08-18 — the four defects of this
wave, and each one is a different way for a rule to be carried by convention:**

- **An invariant carried by convention across four page types will be forgotten on the fourth**
  (`dq-220`). SPEC F12 Rev 0.4 says the framework is ABSENT from the domain expert's document.
  Three screens each read the role for themselves and asked for `?configuration=1` only for the
  engineer; `/runs` and `/runs/<recordId>`, written later by someone who had read none of the other
  three, did not — and served **both roles byte-identical HTML** with nine expectation
  configurations folded into a `<details>`, the exact disclosure control Rev 0.4 deleted. The bead
  named one leaking route; there were **two**. Three things the fix had to be: **one door**
  (`web/app/framework.ts`, asked by both exits of `web/app/api.ts`, so a page cannot forget because
  it is never asked); **stripping and not just not-asking**, because `/records` sends the framework
  UNASKED and no query parameter would ever have protected the run screens; and **the stream is a
  second door**, so redacting the page load alone would have left the record clean until somebody
  pressed Run. The check reads `web/app/**/page.tsx` off the filesystem and asserts on the RAW
  response, so a page written tomorrow is in it by existing.
- **A refusal must not destroy the work it was protecting** (`dq-ee0`). Reject-with-no-reason gave
  the *correct* refusal and took ten unsaved proposals — a ~25 s billed call — off the screen with
  it. That is the tax that teaches people to fill the reason box with a full stop. The fix is not
  persistence (F3 keeps proposals unsaved on purpose); it is one query parameter carried back, off
  a five-minute memo. Reading the fix found the same loss on the **success** path and on **amend**.
- **A private hostname reaches the reader through the gap where nothing answered** (`dq-abs`).
  There was no 502 anywhere in this codebase: an exception left the handler, `ThreadingHTTPServer`
  closed the connection with nothing written, and the **proxy** invented both the status and the
  sentence — naming `api.railway.internal:8000`. Two structural fixes, neither per-route. And the
  grep that looks for leaked hostnames **was blind**: every refusal is produced before a connection
  is opened, so it only ever read bodies with no hostname available to leak.
- **A number in UI copy can be an ARGUMENT, not a preference** (`dq-5da`). "Up to 8 at a time, so
  every evidence line is on screen when you press it" is the reason bulk accept is *safe*; the
  proposer held its own constant of ten. The cap now lives with the module that refuses a selection
  past it and is passed as an argument, and the check is on the **call site**, because a check that
  counted the output would go green on a literal `8` typed in beside the constant.

---

## 7. Environment — verified working

- `.env` (gitignored) holds `SUPABASE_DB_URL_DIRECT` (5432), `SUPABASE_DB_URL_POOLED` (6543),
  `SUPABASE_DB_PASSWORD`, `CLAUDE_CODE_OAUTH_TOKEN`. `.env.example` documents them.
- Supabase PostgreSQL 17.6, region `ap-southeast-1`. `customers`, `orders` (500,000 rows) and
  `payments` are live; `init.sh` asserts they exist, not merely that a connection opened.
- Installed and used by the gate: ruff 0.6.1, mypy 1.19.1, pytest 7.4.3, Python 3.12.5, playwright
  1.57.0 with browsers cached, Node with `web/node_modules`. Also `claude-agent-sdk`, `psycopg`,
  `uv`, `bd`. Great Expectations is **not** in the base interpreter, on purpose — the `ge` layer runs
  through `uv run --no-project --with …` (`VERIFICATION.md` §1).
- Docker Desktop is at `/Applications/Docker.app/Contents/Resources/bin/` and is **not on `PATH`**.

### Gotchas that already cost time
- **`gx.get_context()` is process-global.** One context per process, handed out — never one per
  request.
- **`catch_exceptions` defaults to `True`** — assert on `exception_info`, not on `success`.
- **`networkidle` is not a write barrier** (§6). Poll the thing you are about to assert on, bounded,
  and keep the same assertion at the end.
- **The IPv6 trap.** `db.<ref>.supabase.co` publishes AAAA records only and Docker Desktop gives
  containers no IPv6 route, so *"psql works from my laptop"* proves nothing about the container. The
  compose stack was verified against the **session** pooler (IPv4, 5432). The code's default is
  unchanged. `README.md` has the detection and the fix. **It bites the make targets too:** both
  `check-ge` and `check-ui` re-source `./.env` *inside* the recipe, so a pooler override exported in
  your shell is overwritten and you get
  `could not translate host name "db.<ref>.supabase.co" to address` from 24 checks at once. Source
  the override where the recipe cannot reach it, or point `.env` at the pooler.
- **`web/.next` is stale until you rebuild it, and it fails GREEN.** `npm --prefix web run start`
  serves the last build and says nothing about it. `find web/app -newer web/.next/BUILD_ID` before
  trusting any browser-layer result (§2).
- **The `ge` layer's ephemeral env inherits no site-packages, and pytest imports before it filters.**
  `-m ge` selects nothing that asks a model, but collection imports every module under `testpaths`
  and seven reach `app/model.py`. That is why the `check-ge` recipe carries
  `--with claude-agent-sdk==0.1.23`; without it the target dies at collection in under a second.
- **`.claude/worktrees/` and the local `worktree-agent-*` branches belong to other sessions.** Never
  commit them, never `git add -A` blindly.
- **A worktree or fresh clone has no `.env`** — `init.sh` fails loudly with the fix rather than
  skipping; do not add a skip knob.
- `make check` must stay installation-free, network-free and app-free. The marker deselection
  `-m "not ge and not e2e and not live"` implements that promise; `--strict-markers` stops one
  mistyped marker from smuggling a network check inside it.
- Supabase free tier is burstable: treat single timings as ±10%, not as constants.

---

## 8. Open items

| ID | Item | Status |
|---|---|---|
| O-1 | Composition of the catalog | **RESOLVED** (LT-2a) — 15 types, single-column and table-level only |
| O-2 | Row cap for rule execution | **RESOLVED — no cap ships** (LT-1b); the disclosure mechanism ships, switched off |
| O-3 | Synchronous vs background execution | **RESOLVED — synchronous, progressive, direct connection** (LT-1b) |
| O-4 | Transport for progressive results | **RESOLVED — NDJSON over one chunked POST**, decided while building B14b/B16 (§5) |
| UX | Which variant is the base direction | **RESOLVED — Diglot Workbench**, with the Reviewer graft, by the author's decision. SPEC Rev 0.4 records it |

Nothing in the spec is open. What is left is delivery and provenance, and both are in §9.

---

## 9. The thing most likely to be forgotten

**DONE, 2026-08-17 — this entry is kept as a record rather than deleted.** The AI-usage deliverable
is a quarter of the grade and it is now written: **[`AI_USAGE.md`](./AI_USAGE.md)**, bead `dq-803`.
It was assembled from the fourteen merged PR bodies, `learning-tests/FINDINGS.md`, the bead close
reasons, `bd memories` and `VERIFICATION.md` §4.7/§8/§10 — every claim in it traceable to one of
those, with a verification appendix naming the command for each section. It covers the tier choice
and the deliberately omitted loop, the four falsifications, the **thirteen** documented occasions the gate
was shown to block, the honest failures (the refused privilege grant, the forgeable feature ledger
that was deleted, the stale export, the IPv6 outage, the two red-with-nothing-broken runs), and the
three places a human stayed load-bearing. **The design doc's Appendix D should now point at it.**

What made it writable at all was not documentation discipline at the end — it was §4a's rule that
every finding goes in the **PR body**, not only in the bead notes. Without that it would have been
reconstruction, and it would have shown.

Three runners-up remain. The first two are **five minutes of a human's attention each**; the third
is the one that changes what the world sees.

1. **Two visual baselines to look at — not six, and not for the reason §9 used to give.** All six
   were approved by the author in `2781c1f`, so the visual layer genuinely compares now and **four
   of the six pass**. Two do not, and neither is a defect: the screens changed, on purpose, in this
   wave.

   | File under `tests/e2e/__baselines__/` | Route | Moved | Why |
   |---|---|---|---|
   | `tables-three-buckets.png` | `/tables` | over budget | `lt1a_probe` is no longer listed (`dq-5da`) |
   | `run-record-in-flight.png` | `/runs/<demo record id>` | **4.46%** vs a **0.20%** budget | the domain expert's `<details>` panels are gone (`dq-220`), and the demo record was re-seeded |

   The fresh shot is written beside each as `<state>.actual.png`. Open it, decide whether that is
   the screen you meant, `git add` the baseline, and re-run — `dq-vix` and `dq-dkq` close on that
   output:

   ```bash
   # the two processes from VERIFICATION.md §1 must be up
   APP_URL=http://localhost:3000 DQ_API_URL=http://localhost:8000 \
     python3 -m pytest -m e2e -k visual_regression -ra
   ```

   **No agent may approve one**, and the door that used to let one through is shut and shown shut:
   `_approved()` asks `git ls-files` **and** `git diff --quiet`, and at close-out that was driven by
   hand — a committed baseline with one byte appended pends with the same sentence the untracked
   case gets, and restores clean. `VERIFICATION.md` §4.3 and `AI_USAGE.md` §6.2 carry the correction
   and the 31.36%-against-0.20% number that made it worth writing down. Bead `dq-zyt`, **closed**.

2. **Name the deployment the checks are already asking for.** `dq-cyi.1` is closed —
   `test_deployed_url_serves_the_smoke_route` PASSED against the live URLs in 167.75 s, the first
   time it ran rather than pended — but that was with the variables exported **by hand for one
   session**. `DEPLOYED_APP_URL` and `DEPLOYED_API_URL` are not in `.env`, so every browser-layer
   run since prints `PENDING — DEPLOYED_APP_URL is unset — no deployment was named`. The check
   **fails rather than skips** the moment the variable points at something silent, so putting them
   in `.env` is what turns a one-session proof into part of every run.

3. **THE FIXES IN THIS TREE ARE NOT DEPLOYED.** Railway is serving `ea9a179`. Until the lead
   redeploys, the live app still: serves the Great Expectations configuration to a domain expert on
   both `/runs` screens; answers a mistyped rule id with a **502 naming `api.railway.internal:8000`**;
   destroys ten unsaved proposals when a rejection is refused; returns **10** proposals under copy
   that promises 8; and lists `lt1a_probe` on the coverage screen. **A reviewer opening the live URL
   is looking at the defects, not at the repository.** After the redeploy, re-run the hostile checks
   against the deployment rather than assuming — the four beads' close reasons carry the exact
   `curl` measurements to compare against.

And one standing caution that has not expired: **the 14 s ceiling is not a decision with no expiry
date.** O-3 is settled, but LT-1b's verdict was *not* "synchronous works" — a run stops being
watchable somewhere between 3 and 8 rules on a 500,000-row table, and a product that lets a domain
expert accumulate rules crosses that line by design. `SPEC.md` §5 carries the deferral and its
trigger.
