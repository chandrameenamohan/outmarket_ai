# HANDOFF — AI-Powered Data Quality Assistant

**Read this first.** It exists so a fresh session can resume without re-deriving anything.

Last updated: 2026-08-16 · after the SPEC was frozen, the verification harness was built, and the
spec was decomposed into beads. **No application code exists yet** — `app/` is not there.

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
| 1 | SPEC | ✅ `SPEC.md` Rev 0.2 **FROZEN** 2026-08-16 — nothing waits on a measurement; only O-4 (progressive transport) is open, and it changes no acceptance text |
| 1.5 | Out-of-the-box expansion | ✅ one candidate surfaced, argued against, declined |
| 2 | Learning tests | ✅ **4 of 4 executed** against real dependencies → `learning-tests/FINDINGS.md` (PRs #2, #4, #5, #7) |
| 3 | Tasks + DoD | ✅ **6 epics + 25 task beads**, all open, none claimed → `bd list` |
| 4 & 6 | Verification gate | ✅ **built and green** → `VERIFICATION.md`, `Makefile`, `init.sh`, `pyproject.toml`, `tests/` |
| 5 | Build (attended) | ⬜ **not started — this is where the next session works** |
| 7.5 | Craft review | ⬜ |
| 9 | Provenance | ⬜ the AI-usage write-up is still unwritten — see §9 |

Also landed outside the step ladder: the 500,000-row demo dataset (PR #3, `seed/MANIFEST.md`, live in
Supabase) and four UX design variants with judge scores (PR #6, `design/`).

**`make check` today:** exit 0 — 6 passed, 28 skipped, 46 deselected. Every skip prints a loud
`PENDING — <what it is waiting on>`. That skip list *is* the ledger of remaining work; there is no
feature-ledger file, deliberately (`VERIFICATION.md` §10).

**Uncommitted on `main` right now** (`git status`): the SPEC freeze edit plus the whole harness —
`VERIFICATION.md`, `Makefile`, `init.sh`, `pyproject.toml`, `.env.example`, `tests/`,
`UX_HARNESS_FINDINGS.md`, and the `CLAUDE.md` / `AGENTS.md` / `.gitignore` updates. It is real, it
runs, and it is not yet on a branch. See §4 and §4a.

---

## 3. Artifacts

| What | Where |
|---|---|
| The brief | `QAFD.pdf` |
| **SPEC (frozen)** | `SPEC.md` — 15 features with observable acceptance, 6 invariants, non-goals, §7 end-to-end scenario, §9 open items |
| **Verification harness** | `VERIFICATION.md` (the design) + `Makefile` (`make check`, `make check-ui`) + `tests/` + `init.sh` |
| Learning-test findings | `learning-tests/FINDINGS.md`, raw numbers in `learning-tests/lt1b_results.json` |
| Demo dataset | `seed/MANIFEST.md`, `seed/seed_demo_data.py` — already loaded in Supabase |
| UX variants + judge scores | `design/README.md`, four self-contained HTML files; constraints derived in `UX_HARNESS_FINDINGS.md` |
| **Architecture design doc** | https://claude.ai/code/artifact/97a3df0c-7ae3-4e8a-94fe-6e23e8b6f0f9 — problem framing, designs not chosen, risk register, Appendix D (AI-usage log) |
| Design doc source | scratchpad HTML, **session-scoped**; if gone, WebFetch the artifact URL and re-create before editing, then republish to the same path |
| Task tracker | beads, prefix `dq` — `bd ready`, `bd list`, `bd show <id>` |
| Credentials | `.env` (gitignored); shape documented in `.env.example` |
| The author's workflow | `software_development_workflow.md`, `HOW_I_BUILD.md` |

---

## 4. Do next

```bash
./init.sh     # credentials → database smoke → make check
bd ready
```

`bd ready` returns 8 rows, 6 of which are epics. **Two real tasks are ready:**

- **`dq-5pb.6` · B24 — freeze the documents against what was measured.** Mostly *done in the working
  tree already*: `SPEC.md` is frozen and its §9 records O-1/O-2/O-3 resolved, `VERIFICATION.md` §9 is
  written as "SETTLED BY LT-1b", and this rewrite is the HANDOFF half of it. What remains is
  verifying its checks and getting it onto a branch and into a PR. Documents only, no app code.
- **`dq-5pb.1` · B1 — the gate reaches the browser layer, and is shown once to go red.** This is the
  first build task: a Node/Next app that boots from `./init.sh`, answers on `APP_URL`, and lets
  `make check-ui` run `tests/e2e/` against something real instead of skipping. Then break one check
  on purpose, watch the gate go red, restore it (workflow Step 6).

After B1, E1's remaining P0s (`dq-5pb.2`, `.3`, `.4`) and then epic E2 (`dq-yov`, the GE door +
catalog + store) are the spine. `VERIFICATION.md` §9.4 lists what is buildable immediately regardless
of O-4: the persisted run record with an explicit `status`, the `/runs` and `/runs/[recordId]` route
strings, the single status-atom formatter, and write-resistance.

**Read `bd show <id>` before starting anything** — each bead carries its own acceptance, its check
order (cheapest deterministic first), and an explicit out-of-scope list.

---

## 4a. Git discipline — branch, one commit per bead, PR

**Never commit to `main`.** Every unit of work gets its own branch, named for what it is
(`learning-tests/lt2a-ge-registry`, `seed/demo-dataset`). Branch off the last commit on
`origin/main`, not off other local work, so PRs stay independent and mergeable in any order.

**Each completed bead gets its own commit. Never batch several beads into one.** Close the bead and
commit in the same step, with the bead ID in the subject:

```
LT-2a: confirm GE 1.x object model and expectation registry (dq-chf)
```

Work that is not a bead — setup, docs, spec revisions — still gets its own focused commit. Then push
and open a PR with `gh pr create`. **Do not merge it** — the author reviews and merges. Put the
finding in the PR body, not only in the bead notes.

PRs #1–#7 are all merged; that is the whole history so far.

---

## 5. Decisions already made — do not re-litigate

| Decision | Why |
|---|---|
| **No Ralph/autonomous loop**, but keep the gate | The gate is the part that survives; the loop driver is what current models have outgrown |
| **No row cap ships** (O-2, from LT-1b) | Wrong lever, three measured reasons: capping to 100,000 rows (an 80% data loss) saves only 37%; at full size it is a *net loss* because GE runs a query asset verbatim through a client-side cursor (`LIMIT 500000` → 22.67 s and 1,000,127 rows pulled, vs 13.63 s and 156 rows uncapped); and it breaks `expect_column_values_to_be_of_type` and `expect_column_values_to_be_in_type_list` outright with `KeyError: 'type'`. **INV-5's disclosure mechanism still ships**, carried by us from the asset definition into the stored result — GE does not record that it was capped — with the cap switched **off** at this scale |
| **Execution is synchronous, but progressive** (O-3, from LT-1b) | Not a job queue. Worst case is 14.84 s for the ten-rule shipping suite, past the 10 s bar — but the cost is a ~2.3 s floor plus ~0.83 s per rule, paid as independent statements, so a worker returns the same total later plus a polling endpoint and a staleness problem. Streaming each verdict as it lands turns a 14 s blank spinner into a first result at ~2 s and a filling list. F8's acceptance carries the progressive clause; F13 must render a partially-complete run |
| **F8 uses `SUPABASE_DB_URL_DIRECT` (5432)** | The transaction pooler is 21% slower on identical work — 17.94 s vs 14.84 s. A rule run is a few long analytical statements on one connection: the shape a pooler helps least |
| **Exactly one GE context per process** (INV-3, from LT-1b) | `gx.get_context()` is *process-global*: a second call silently orphans the first context's datasources, and the failure surfaces later at `validate()` as a `DatasourceError` naming a datasource that is sitting right there. The single GE-importing module creates one context and hands it out — **never one per request** |
| **Curated catalog of 15 GE expectation types**, not the full registry | Smaller menu → better model output, less validation code, renderable UI. The 15 are listed in `FINDINGS.md` § LT-2a |
| **Validate before persist** — instantiate against GE before storing | Makes an invalid rule structurally impossible to save. This is the keystone decision |
| **One SQL stat query**, not a profiling module | Start minimal; deepen only the dimension that proves weak |
| **GE is a runtime, not the domain model** — exactly one module imports it | Survives GE's next breaking release; enforced in the gate, not by convention |
| **Two primary users**, not primary + secondary | Engineer owns coverage; domain expert owns whether a rule *means* the right thing |
| **Role is a selected view, not an account** | One env-configured DB; auth would add realism, not capability |
| **Single-column and table-level rules only** | Multi-column deferred to v2 — the most common rejection, and the first thing to add next |
| **Inexpressible NL rules are rejected with a reason, never stored** | A stored `unsupported` rule implies coverage that does not exist |
| **Claude Agent SDK, all built-in tools disabled, `setting_sources=[]`, single call** | Subscription-token auth (no API purchase), reduced to the one call the task needs; `setting_sources=[]` stops the developer's global `CLAUDE.md` leaking into a server-side call |
| **Delivery: live URL *and* docker-compose** | "Working MVP" must not depend on the reviewer's machine (bead `dq-cyi.1` · B22) |
| **E-commerce demo dataset** | Rules are self-explanatory without domain briefing |
| **No feature-ledger file** | An earlier `verification/features.json` + `summary.py` was deleted: a fourth copy of the same intent, and it could be made to print `15/15 passes: true, verified_by: "vibes"` and exit 0. `pytest -ra`'s PENDING list and `bd list` replace it (`VERIFICATION.md` §10) |

Two things are **never** simplified away, at any scope: a suggestion always carries its evidence, and
any result derived from a sample says so — **inside** the same text node as the pass/fail state, not
adjacent to it.

---

## 6. Findings so far

**Full write-ups are in `learning-tests/FINDINGS.md`**, one section per test, with raw numbers in
`lt1b_results.json`. Read the LT-1b section in full before touching F8, F9 or F13. Summary:

- **LT-1b · latency (`dq-e1d`).** 15 catalog rules over the whole 500,000-row table on the direct
  connection: **13.97 s**; the 10-rule shipping suite (with `unexpected_index_column_names`, which
  F13 needs): **14.84 s** direct / **17.94 s** pooled; one rule alone: **2.28 s**. Cost shape is a
  ~2.3 s floor plus ~0.83 s per additional rule — lumpy per *rule*, not linear in *rows*: 1,000 →
  500,000 rows (500×) costs only 2.7× the time. The line: only **3 rules** fit under 10 s at 500,000
  rows, and with 10 rules only **100,000 rows** do. Connect is measured apart and never inside the
  watched number (direct 1.16 s, pooled 2.26 s; RTT 51 ms / 109 ms). GE's own Python is **21%** of
  wall clock at full size — more than the network. This settled O-2, O-3 and the connection choice
  (§5) and produced the process-global-context trap (§7).
- **LT-1a · GE on PostgreSQL (`dq-dww`).** Confirmed execution and captured the exact result shape F9
  must normalise. `catch_exceptions` defaults to `True`, so an **ERRORED rule is visually identical
  to a FAILING one** — hence `errored` is a third result state in F9, not a kind of failure.
- **LT-2a · object model and registry (`dq-chf`).** 15 types chosen from the 56 in GE 1.20.0. The
  catalog cannot be generated from GE introspection alone — `.schema()["required"]` is incomplete —
  so each entry carries our own required-parameter and sanity constraints. GE accepted **10 of 25
  nonsense rules while reporting success**: compiling is not sense, which is why F12 must never
  render "Compiled OK" as a success state.
- **LT-2b · Agent SDK (`dq-uco`).** Auth from `CLAUDE_CODE_OAUTH_TOKEN`, tools fully suppressed,
  `max_turns=1`, structured JSON by instruction alone; 6.6 s and $0.041 per call. **The finding that
  matters:** every rule the model proposed was statistically true and business-naive — `status IN
  {observed values}`, `order_total BETWEEN 0 AND 89,400`, `order_total IS NOT NULL`. It did *not*
  propose `order_total >= 0`, the actual invariant. The meaning is not in the sample. Evidence lines
  and unsaved-proposal status are load-bearing, not decorative.

---

## 7. Environment — verified working

- `.env` (gitignored) holds `SUPABASE_DB_URL_DIRECT` (5432), `SUPABASE_DB_URL_POOLED` (6543),
  `SUPABASE_DB_PASSWORD`, `CLAUDE_CODE_OAUTH_TOKEN`. `.env.example` documents all four.
- Supabase PostgreSQL 17.6, region `ap-southeast-1` (Singapore). The seeded tables `customers`,
  `orders` (500,000 rows) and `payments` are live; `init.sh` asserts they exist, not merely that a
  connection opened.
- Installed and used by the gate: ruff 0.6.1, mypy 1.19.1, pytest 7.4.3, Python 3.12.5, playwright
  1.57.0 with browsers cached. Also `claude-agent-sdk` 0.1.23, `psycopg`, `uv`, `bd`. **`ant` CLI is
  not installed and is not needed.**
- Great Expectations is **not** installed in the base interpreter, on purpose. The `ge` layer runs
  only via the `uv run --no-project --with …` line in `VERIFICATION.md` §1.

### Gotchas that already cost time
- **`gx.get_context()` is process-global.** A second call orphans the first context's datasources and
  the error appears later at `validate()`, naming a datasource that exists. One context per process,
  handed out — never one per request. (`project_manager.set_project(ctx)` restores it.)
- **`catch_exceptions` defaults to `True`** — a rule that crashed looks exactly like a rule that
  failed (`success: false`, `result: {}`). Assert on `exception_info`, not on `success`.
- **`.claude/worktrees/` and the local `worktree-agent-*` branches belong to other sessions.** Never
  commit them, never `git add -A` blindly; the `.gitignore` entry that excludes them is itself still
  uncommitted.
- **A worktree or fresh clone has no `.env`** — it is gitignored. `init.sh` fails loudly with the fix
  rather than skipping; do not add a skip knob.
- `make check` must stay installation-free, network-free and app-free. The marker deselection
  `-m "not ge and not e2e"` is what implements that promise, and `--strict-markers` is what stops one
  mistyped marker from smuggling a network check inside it.
- Supabase's UI shows `[YOUR-PASSWORD]` as a literal placeholder; it never displays the real
  password. Reset it from Settings → Database if lost. A password containing `@ : / # ? % &` must be
  URL-encoded in the URI.
- Supabase free tier is burstable: the LT-1b baseline drifted −8.3% across one script run. Treat
  single timings as ±10%, not as constants.

---

## 8. Open items

| ID | Item | Status |
|---|---|---|
| O-1 | Composition of the catalog | **RESOLVED** (LT-2a) — 15 types, single-column and table-level only |
| O-2 | Row cap for rule execution | **RESOLVED — no cap ships** (LT-1b); the disclosure mechanism still ships, switched off |
| O-3 | Synchronous vs background execution | **RESOLVED — synchronous, progressive, direct connection** (LT-1b) |
| O-4 | Transport for progressive results | **OPEN** — SSE, chunked response, or one request per rule. Changes no acceptance text; decided when B14b/B16 are built, constrained only by the single process-global GE context |
| UX | Which variant is the base direction | **Recommendation pending the author's decision** — `design/README.md` proposes *Run Ledger* (25.4/30) with named grafts from Reviewer and Diglot. Do not silently pick a different one |

---

## 9. The thing most likely to be forgotten

**The AI-usage deliverable is a quarter of the grade and nobody has written it.** The brief grades
"how AI tools were leveraged during development" on equal footing with the code. The evidence is
being generated right now — seven PRs whose bodies carry the findings, four learning tests that each
falsified something, a gate that says PENDING out loud, a design doc whose Appendix D is still marked
*Pending* — but nothing has been assembled into the artefact a reviewer reads. It cannot be
reconstructed convincingly at the end, and the build phase starting now is the part that will
generate the most material. Capture it as the work happens.

Two runners-up:

1. **The 14 s ceiling is not a decision with no expiry date.** O-3 is settled, but LT-1b's verdict was
   *not* "synchronous works" — a run stops being watchable somewhere between 3 and 8 rules on a
   500,000-row table. A product that lets a domain expert accumulate rules crosses that line by
   design. `SPEC.md` §5 carries the deferral and its trigger.
2. **A shipped harness is not a shipped app.** `make check` is green over 28 PENDING skips and zero
   application code. Every one of those skips names its blocker; none of them will turn green by
   accident, and a bead's acceptance is the check, not the description of it. Do not weaken, delete,
   or skip a check to make the gate pass.
