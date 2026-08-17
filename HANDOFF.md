# HANDOFF — AI-Powered Data Quality Assistant

**Read this first.** It exists so a fresh session can resume without re-deriving anything.

Last updated: 2026-08-17 · after the third build wave. **The product is built.** All fifteen SPEC
features have shipped, five of the six epics are closed, and both halves of the gate run against
real processes: `make check` is **187 passed, 0 skipped**, and `make check-ui` drives a real
Chromium over a real Next process in front of a real Python process against the real seeded
Supabase database — **52 passed, 9 skipped**.

What is *not* done is short and is named in §9: no deployed URL, no approved visual baselines, and
**the AI-usage write-up, which is a quarter of the grade and is still unwritten.**

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
| 9 | Provenance | ⬜ **the AI-usage write-up is still unwritten.** See §9. It has been the top of this list since the first session and it is still the top |

**Epics:** E1 `dq-5pb`, E2 `dq-yov`, E3 `dq-3bp`, E4 `dq-klv`, E5 `dq-rbf` are **CLOSED**, each with
its children's evidence in the close reason. **E6 `dq-cyi` is open** on two children — see §4.

### The gate, today

```
make check       187 passed, 0 skipped, 97 deselected, 2.73 s, exit 0
                 ruff → ruff format → mypy (63 source files) → pytest → eslint + tsc
make check-ui     52 passed, 9 skipped, 223 deselected, 368.55 s, exit 0
                 real Chromium, two real processes, real Supabase, 3 real billed model calls
make check-ge     33 passed, 251 deselected, 104.14 s, exit 0   (network + database)
```

**Run `check-ge` and `check-ui` ONE AT A TIME.** They share `DQ_SCHEMA=dq_check`, both write to it,
and the store is append-only — so run together they take each other red with nothing wrong with
either. It happened at close-out; `VERIFICATION.md` §4.7.2 has the numbers and bead `dq-cyi.4` owns
the fix. `make check-ui` also needs its two processes already running — the command lines are in
`VERIFICATION.md` §1.

**Zero skips in `make check`.** That number used to be 28 and every one of them was a `PENDING —`
line naming what it waited for; they are all assertions now. The **nine** remaining skips are all in
the browser layer and all of them are honest: seven visual-regression states and two delivery
targets. §9 says what a human has to do about them.

**Working tree.** Waves 1 and 2 are committed on branch `build/wave2-engine` (Wave 1 is merged to
`origin/main` as PR #12). **Wave 3 — the whole UI, the docker stack, SPEC §7's flow — is
uncommitted**, 61 paths in `git status`. Branching, committing and the PR are the author's, not an
agent's (§4a).

---

## 3. Artifacts

| What | Where |
|---|---|
| The brief | `QAFD.pdf` |
| **SPEC (frozen, Rev 0.4)** | `SPEC.md` — 15 features with observable acceptance, 6 invariants, non-goals, §7 end-to-end scenario, §9 open items |
| **Verification harness** | `VERIFICATION.md` (the design) + `Makefile` + `tests/` + `init.sh` |
| **How to run it** | `README.md` — docker compose, credentials, and "The IPv6 trap" |
| Learning-test findings | `learning-tests/FINDINGS.md`, raw numbers in `lt1b_results.json` |
| Demo dataset | `seed/MANIFEST.md`, `seed/seed_demo_data.py` — loaded in Supabase |
| UX variants + judge scores | `design/README.md`, four self-contained HTML files; **the chosen one is `design/ux-variant-workbench.html`** |
| **Architecture design doc** | https://claude.ai/code/artifact/97a3df0c-7ae3-4e8a-94fe-6e23e8b6f0f9 — problem framing, designs not chosen, risk register, Appendix D (AI-usage log, still *Pending*) |
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

---

## 4. Do next

```bash
./init.sh     # credentials → database smoke → app install+build → make check
bd ready
```

Three beads are open, and they are the whole remaining ledger:

- **`dq-cyi.1` · B22 — a reviewer runs the product without our machine.** One criterion of three
  is unmet: **no deployed URL exists.** The docker half is proven and recorded with its numbers in
  `VERIFICATION.md` §8.1 (both images build clean in 1 m 52 s, the compose stack answers the same 21
  hygiene cases, no credential is baked into either image). What remains is standing up both
  processes somewhere and setting `DEPLOYED_APP_URL` **and** `DEPLOYED_API_URL` — the second is a
  real cost of the topology, because `web/app/api.ts` reaches Python **server-side**, which is what
  buys this product no CORS and no API base URL in the browser bundle. Read `README.md`,
  "The IPv6 trap", before blaming the stack.
- **`dq-cyi.4` · B27 — `make check-ge` and `make check-ui` share one scratch schema.** Also found at
  close-out, by running them together: both went red, neither was broken. Run them one at a time
  until this lands.
- **`dq-vix` · B25 — a fixed demo fixture makes the six data-dependent screens photographable.**
  This is the bead that unblocks six of the seven visual baselines. `VERIFICATION.md` §4.3 had
  promised they would clear "with B23's fixed demo data"; B23 builds and **drops its own schema** by
  design, so that promise had no owner until this bead.

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
| **The GE configuration is ABSENT for the domain expert, not collapsed** | The stronger form of the original intent. It is not `display: none` and not a disclosure control: the payload is not even asked for (`?configuration=1` is added only in the engineer's render), so view-source, a screen reader and a text browser all agree. A component deciding not to print a field it was handed is one refactor away from printing it |
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
  by earlier runs into an append-only store. That is what put six states in `DATA_DEPENDENT`.
- **Two visual states can be the same photograph.** `tables-bucket-two-errored` and
  `tables-three-buckets` produced byte-identical PNGs (same md5, two independent runs). The eighth
  state was deleted rather than approved.
- **`networkidle` is not a write barrier.** A click on a server action that redirects can leave the
  page "idle" again before the request has left, so a read taken straight after it arrives before the
  write. This cost one red `make check-ui` (bead `dq-cyi.3`) after the repository had already learned
  it twice elsewhere.
- **Two check layers sharing one append-only schema take each other red.** `make check-ge` and
  `make check-ui` both pin `DQ_SCHEMA=dq_check` and both write to it, so a check counting rules
  before and after an action reads a number the other layer is moving. Both went red when run
  together and both are green alone (bead `dq-cyi.4`). The lesson is not "make the count tolerant" —
  that assertion is the one that catches a stored non-rule — it is "one writer per schema".

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
  unchanged. `README.md` has the detection and the fix.
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

**It is still the same thing, and it is now the only large one left: the AI-usage deliverable is a
quarter of the grade and nobody has written it.** The brief grades "how AI tools were leveraged
during development" on equal footing with the code. The evidence exists and is unusually good —
twelve PRs whose bodies carry the findings, four learning tests that each *falsified* something a
reasonable person would have assumed, a gate that says `PENDING —` out loud and was shown to go red
five separate times, bead close reasons that walk a DoD criterion by criterion with pasted output,
`HOW_I_BUILD.md`, and a design doc whose Appendix D is still marked *Pending*. **None of it has been
assembled into the artefact a reviewer reads.** It cannot be reconstructed convincingly after the
fact, and the build phase that generated the most material is now over. This is the single highest
-value hour left in the project.

Two runners-up, both of which need a **human**, not a session:

1. **Seven visual baselines, and only one of them has a picture.** `tests/e2e/__baselines__/role-door.png`
   is written and **unapproved** — it is untracked, and *being tracked by git is what approval means
   here*, because a person staging a file is the only signal available that a person looked at it.
   **Open it and decide whether that is the screen you meant.** The other six pend on `dq-vix` (B25)
   for a fixed demo fixture, because today they would photograph a database rather than a screen. No
   agent may approve any of them; a machine approving its own photograph is the one habit that check
   exists to prevent.
2. **There is no deployed URL** (`dq-cyi.1`). The docker path is proven and the smoke check for a
   deployment already exists and pends by name — it fails rather than skips the moment
   `DEPLOYED_APP_URL` points at something silent. Until someone stands one up, SPEC §3's promise is
   half kept, and nothing in this repository should be read as saying otherwise.

And one standing caution that has not expired: **the 14 s ceiling is not a decision with no expiry
date.** O-3 is settled, but LT-1b's verdict was *not* "synchronous works" — a run stops being
watchable somewhere between 3 and 8 rules on a 500,000-row table, and a product that lets a domain
expert accumulate rules crosses that line by design. `SPEC.md` §5 carries the deferral and its
trigger.
