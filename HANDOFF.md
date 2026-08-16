# HANDOFF — AI-Powered Data Quality Assistant

**Read this first.** It exists so a fresh session can resume without re-deriving anything.

Last updated: 2026-08-16 · after Step 2 began (first learning test passed)

---

## 1. What this is, in three sentences

A take-home case study (`QAFD.pdf` in this directory) for an AI-powered data quality assistant. A domain expert states an expectation in plain English; the system turns it into a Great Expectations check it has already proven will run, executes it against a PostgreSQL table on Supabase, and reports failures in the same language the expectation was written in. It is graded on four equally-weighted axes — AI-first development, product thinking, technical implementation, and **how AI tools were used to build it** — so the process is part of the deliverable, not just the code.

---

## 2. Where we are

Following the author's own workflow (`software_development_workflow.md`, "Prompt Pack v4"), **FULL** tier, with one deliberate substitution: **the Ralph/autonomous loop is NOT used.** The deterministic gate it depends on is kept; the loop driver is replaced by attended, one-task-at-a-time sessions.

| Step | Stage | Status |
|---|---|---|
| 0 | Sharpen | ✅ |
| 0.25 | Scope — FULL pack, MVP feature ceiling | ✅ |
| 0.5 | Challenge | ✅ |
| 1 | SPEC | ✅ → `SPEC.md` |
| 1.5 | Out-of-the-box expansion | ✅ → one candidate surfaced, argued against, declined |
| **2** | **Learning tests** | **◐ IN PROGRESS — 1 of 4 done** |
| 3 | Tasks + DoD | ⬜ beads exist for learning tests only |
| 4 & 6 | Verification gate | ⬜ |
| 5 | Build (attended) | ⬜ |
| 7.5 | Craft review | ⬜ |
| 9 | Provenance | continuous |

---

## 3. Artifacts

| What | Where |
|---|---|
| The brief | `QAFD.pdf` |
| **Architecture design doc** | https://claude.ai/code/artifact/97a3df0c-7ae3-4e8a-94fe-6e23e8b6f0f9 — republish by editing the source file and calling Artifact with the same path |
| Design doc source | `/private/tmp/claude-501/.../scratchpad/dq-architecture.html` — **session-scoped; if it is gone, fetch the artifact URL with WebFetch and re-create it before editing** |
| **SPEC** | `SPEC.md` — 15 features with observable acceptance, non-goals, end-to-end scenario |
| Learning tests | `learning-tests/` |
| Task tracker | beads, prefix `dq` — `bd ready`, `bd list` |
| Credentials | `.env` (gitignored) |
| The author's workflow | `software_development_workflow.md`, `HOW_I_BUILD.md` |

---

## 4. Do next

```
bd ready
```

Currently two unblocked:

### `dq-chf` — LT-2a · Great Expectations 1.x object model and registry  (P0)
Confirm the installed GE version's real object model and enumerate its actual expectation-type registry. Most material online describes the pre-1.0 API, so nothing here may be assumed. **The output picks the ~15-type curated catalog** (SPEC O-1) and defines the compiler's shape (F5, F7).

Acceptance: prints GE version, count of available types, the ~15 catalog candidates; instantiates one valid and one deliberately invalid expectation and asserts the invalid one raises; records the real API shape in `learning-tests/FINDINGS.md`.

### `dq-e4s` — SEED · Bulk demo dataset generator  (P1)
Seed `orders` / `customers` / `payments` in Supabase with **documented** deliberate defects. Prerequisite for LT-1b (latency needs volume) and delivers SPEC F15.

Use **~500K orders rows, not 2.4M** — the Supabase free tier is 500MB and 500K is ample to measure latency behaviour.

### Then, blocked until the above:
- `dq-dww` — LT-1a · GE executes against PostgreSQL (needs LT-2a)
- `dq-e1d` — **LT-1b · GE latency on Supabase, direct vs pooled** (needs LT-1a + SEED)

**LT-1b is the load-bearing one.** The entire interaction model assumes a rule run returns fast enough to watch. If GE against Supabase takes minutes rather than seconds, the product becomes a background-job system and F8/F9/F13 all change shape. The spec is not frozen until this number exists.

---

## 4a. Commit discipline — one bead, one commit

**Each completed bead gets its own commit. Never batch several beads into one.**

Close the bead and commit in the same step, with the bead ID in the subject:

```
LT-2a: confirm GE 1.x object model and expectation registry (dq-chf)
```

Work that is not a bead — setup, docs, spec revisions — still gets its own focused commit
rather than being folded into a bead's. A commit spanning several beads cannot be reverted
without taking unrelated work with it.

---

## 5. Decisions already made — do not re-litigate

| Decision | Why |
|---|---|
| **No Ralph/autonomous loop**, but keep the gate | The gate is the part that survives; the loop driver is what current models have outgrown |
| **Curated catalog of ~15 GE expectation types**, not the full registry | Smaller menu → better model output, less validation code, renderable UI |
| **Validate before persist** — instantiate against GE before storing | Makes an invalid rule structurally impossible to save. This is the keystone decision |
| **One SQL stat query**, not a profiling module | Start minimal; deepen only the dimension that proves weak |
| **GE is a runtime, not the domain model** — exactly one module imports it | Survives GE's next breaking release; enforce in the gate, not by convention |
| **Two primary users**, not primary + secondary | Engineer owns coverage; domain expert owns whether a rule *means* the right thing. Both enter the same product at different doors |
| **Role is a selected view, not an account** | One env-configured DB; auth would add realism, not capability |
| **Single-column and table-level rules only** | Multi-column deferred to v2 — it is the most common rejection, and the first thing to add next |
| **Inexpressible NL rules are rejected with a reason, never stored** | A stored `unsupported` rule implies coverage that does not exist |
| **Claude Agent SDK, all built-in tools disabled, single call** | Chosen for its auth model (subscription token, no API purchase), reduced to the one call the task needs |
| **Delivery: live URL *and* docker-compose** | "Working MVP" must not depend on the reviewer's machine |
| **E-commerce demo dataset** | Rules are self-explanatory without domain briefing |

Two things are **never** simplified away, at any scope: a suggestion always carries its evidence, and any result derived from a sample says so.

---

## 6. Findings so far

### `dq-uco` — LT-2b · Agent SDK ✅ CLOSED, all assertions passed

Verified against `claude-agent-sdk` 0.1.23, model `claude-opus-5`:

- Auth works from `CLAUDE_CODE_OAUTH_TOKEN` passed via `ClaudeAgentOptions.env`. **No `ant` CLI, no `ANTHROPIC_API_KEY`, no separate API purchase.**
- Tools fully suppressed with `allowed_tools=[]` + explicit `disallowed_tools`. Zero invocations.
- `max_turns=1` enforced (`ResultMessage.num_turns == 1`).
- Structured JSON obtained **by instruction alone** — the `output_format` option was not needed. Keep the tolerant parser regardless.
- **`setting_sources=[]` is required**, otherwise the developer's own global `CLAUDE.md` leaks into a server-side call. Not optional for a service.
- Measured: **6.6 s wall, $0.041 per call**.

### The finding that matters

Every rule the model returned was **statistically true and business-naive**:

```
status IN {shipped, pending, cancelled, returned}   ← only the values observed
order_total BETWEEN 0 AND 89,400                    ← overfits the observed max
order_total IS NOT NULL                             ← trivially true
```

It did **not** propose `order_total >= 0` — the actual business invariant.

The model can only infer from the sample; the *meaning* is not in the sample. This is empirical confirmation of risk **R-2** on the first test, and of why the domain expert is a first-class user rather than a reviewer of last resort. **Evidence lines and unsaved-proposal status are load-bearing, not decorative** — without them these three rules get silently accepted.

---

## 7. Environment — verified working

- `.env` (gitignored) holds `SUPABASE_DB_URL_DIRECT` (5432), `SUPABASE_DB_URL_POOLED` (6543), `SUPABASE_DB_PASSWORD`, `CLAUDE_CODE_OAUTH_TOKEN`.
- **Both Supabase connections tested OK** — PostgreSQL 17.6, ~680 ms / ~1030 ms connect. Region is Singapore (`ap-southeast-1`), so a little network time is included in any measurement; note it, don't chase it.
- Installed already: `claude-agent-sdk` 0.1.23, `anthropic` 0.40.0, `psycopg`, `uv`, `bd` 1.2.2. **`ant` CLI is not installed and is not needed.**
- Python 3.12.5.

### Gotchas that already cost time
- The `.env` var is spelled `SUPBASE_DB_PASSWORD` (missing A) in one place — harmless, but do not "fix" it into a broken state.
- Supabase's UI shows `[YOUR-PASSWORD]` as a literal placeholder in connection strings; it never displays the real password. Reset it from Settings → Database if lost.
- A password containing `@ : / # ? % &` must be URL-encoded in the URI.

---

## 8. Open items

| ID | Item | Resolved by |
|---|---|---|
| O-1 | Exact composition of the ~15-type catalog | LT-2a (`dq-chf`) |
| O-2 | Row cap for rule execution | LT-1b (`dq-e1d`) |
| O-3 | Synchronous vs background execution | LT-1b (`dq-e1d`) |

---

## 9. The thing most likely to be forgotten

**The spec is not frozen.** `SPEC.md` §8 lists LT-1 and LT-2 as blocking. Do not start building features F8, F9 or F13 before LT-1b produces a number — that measurement decides whether they are synchronous screens or a job system, and building first means building twice.

Second: the brief grades **"how AI tools were leveraged during development"** as its own deliverable. Appendix D of the design doc tracks it, and it is still marked *Pending*. Capture it as the work happens; it cannot be reconstructed convincingly at the end.
