# How I build software

Extracted from my own repos: `chandrameenamohan/india-radar`
(`software_development_workflow.md` — "Prompt Pack v4" — and the working rig) and
`sennamind/next-fastest-car`. This is the short operating version; the full prompt
text lives in india-radar.

**The one line:** transfer intent so the model solves *my* problem; require
compression so the problem stays head-sized; keep judgment and scope for myself.
Execution is the model's job.

---

## The two rules underneath everything

1. **Align, don't control.** The model's bottleneck isn't ability, it's how much of
   my actual situation reaches it. Brief a colleague, don't program a machine.
2. **Keep the problem head-sized.** I hold a compressed *map*; SPEC.md, TASKS.md and
   the decision trail hold the *territory*. When something won't compress, that's
   the design telling me it doesn't fit yet — simplify before building.

---

## Order of operations

**New project:** Sharpen → Scope → Challenge → SPEC → Out-of-the-box → learning
tests → tasks with DoD → design the gate → build under the gate → (evaluator /
craft review if warranted). Provenance throughout, reload at every cold start.

**Brownfield change:** Sharpen → Challenge → read the real code → mini-spec → small
task set → build under the existing gate. No greenfield ceremony on a small change.

**Lightning (≤1h):** Sharpen → spec-in-head (3 lines) → build the one thing fully →
gate → craft pass. Cut *features* to hit the clock, never the gate.

### 0 · Sharpen
Dump the request in rough English. Model restates it, lists its assumptions, asks
only the non-obvious questions, says in one line whether this is even the right
thing to build — then **stops**. Output is shared understanding, nothing else.

### 0.25 · Scope
Classify Lightning / Assignment / Full, and get told which steps we're running.
Harness weight bends to the constraint; the quality bar does not.

### 0.5 · Challenge
"Argue against this. I want your judgment, not your compliance." What's the
simpler 80% path? Which assumption is load-bearing? What would you *not* build?
This is the step most setups lack — everything downstream is good at building the
plan well, nothing else asks whether the plan is right.

### 1 · SPEC
Deep interview (AskUserQuestion), product + high-level architecture only — no
granular implementation, a wrong low-level call cascades. Then the **ten-sentence
compression** before any spec gets written: core thing, keystone decision, the one
genuinely hard part. Can't compress it → too tangled to build. SPEC.md carries
numbered features with *observable* acceptance, explicit non-goals, a
"deliberately not building yet" note, and one end-to-end scenario.

### 1.5 · Out-of-the-box
Once the plan feels done: generate many radically different additions internally,
run them against each other, return only THE ONE + what it unlocks + the minimal
version + its own strongest objection. Anything it surfaces goes back through
Challenge before entering the spec.

### 2 · Learning tests
Every dependency I can't read (third-party API, SDK, CLI): a small script that hits
the **real** thing, logs actual output, then asserts what I believe. Findings
comment at the top, corrected when I'm wrong. Durable ones live in
`learning-tests/`, with `FINDINGS.md` as the file every future session reads before
touching an external API.

### 3 · Tasks with Definition of Done
Outcome-level, never implementation-prescriptive. Every task carries:
`Acceptance (observable)` / `Checks (cheapest deterministic first: lint → typecheck
→ unit → e2e)` / `Out of scope`, plus "do not weaken, delete, or skip these checks
to pass." A task isn't created until its checks are stated. If the tree sprawls
past a glance, the decomposition is too complex.

### 4+6 · The gate — the part that lets me walk away
Designed in plain text (`VERIFICATION.md`) *before* any feature code, then built:

- `make check` = lint → typecheck → unit → worker → e2e. **One** definition of green.
- `.claude/hooks/gate.sh` — the only place that runs it; everything else calls this.
- `.claude/hooks/stop-gate.sh` — Stop hook. Red → exit 2, Claude Code blocks the
  turn and feeds stderr back into context. Gated on `PW_LOOP=1` so it's a silent
  no-op in interactive sessions.
- pre-commit → `make check-fast` (a 20s pre-commit is one people `--no-verify`).
  The last commit is therefore always green — that's what makes recovery safe.
- `init.sh` boots the env and smoke-tests it; missing optional keys warn, not fail.

Push everything into deterministic checks — console-clean, Playwright/browse on the
running app, visual diffs, a11y, dead-code and duplication detection. Reserve an
LLM evaluator for the one thing none of those judge: "does this match the intent."

**Prove the brake before trusting it.** In india-radar `gate.sh` once `cd`'d one
directory too high, reported "no rule to make target" and *still* exited non-zero —
it looked like a working brake and wasn't. Only proving it caught that.

### 5 · The Ralph loop
`ralph.sh` spawns a **fresh** headless `claude -p` per iteration; each reads
`LOOP_PROMPT.md`, does ONE task, stops. No memory between iterations — all state is
in `TASKS.md` + git. Each iteration:

1. **Recover first.** Any task `in-progress` = a previous iteration died; resume it.
   `git checkout -- . && git clean -fd` (safe: last commit is green). Run `init.sh`.
2. Orient: SPEC.md, VERIFICATION.md, `learning-tests/FINDINGS.md`, `git log`.
3. Claim the highest ready task, commit the status change immediately so a crash
   leaves a trace.
4. Implement **fully** — no stubs, no "simple version for now". Ponytail ladder
   applies (YAGNI → stdlib → native → existing dep → one line); deliberate
   shortcuts get a `ponytail:` comment naming the ceiling and the upgrade path.
5. `make check` with the **real output as evidence**. Never weaken a check to pass.
6. Craft pass on the diff (dead code, duplication, over-abstraction, reads like the
   surrounding code) → re-run fast checks. Craft is part of done.
7. Commit explaining *why*, mark done, append anything durable to FINDINGS.md.
8. Fixed VALIDATION SUMMARY block: task, what built, acceptance, gate result, the
   exact command I can run myself, decisions, needs-input.

Attended by default (`./ralph.sh` pauses per task); `--auto` only after the gate has
caught a real failure. Progress detection: an iteration that closes no task and
makes no commit is stuck — stop rather than spin.

**Two hard-won rules in the loop prompt:** never stop with uncommitted work (step 1
deletes it — iteration 15 silently lost 1,833 resolved websites that way), and never
report a background process as still running (it dies with the iteration).

**Attendance:** missing input → `blocked: NEEDS INPUT`, stop, never fabricate.
Taste/subjective acceptance → `needs-review`, don't self-approve. Third-party API
down → `blocked: NEEDS RETRY`, don't fake data or burn the iteration retrying.

### 5.5 · Reload
`bd prime` reloads the machine's state; this reloads mine. After a loop run or a few
days away: core idea in 3 sentences, done/in-flight/open, key decisions and why,
the one thing I've likely forgotten, and anywhere the code has drifted from SPEC.

### 7.5 · Craft review
Separate from correctness. The loop generates a lot of code with no continuous human
taste holding it coherent, so craft gets verified, not assumed: reuse (did it
reinvent something in the repo?), over-abstraction, dead scaffolding, consistency.
Behavior-preserving fixes applied; judgment calls flagged back to me.

### 9 · Provenance
Code records *what*; only I can record *why*. Intent, key decisions, rejected
alternatives — in the commit body and the durable notes, so a stranger (future me,
a future agent) can reconstruct why, not just what.

### 10 · Compound
Every couple of weeks: review my own sessions for prompt patterns that worked vs.
went in circles, turn repeated manual workflows into skills, refresh stale ones.
For expert subagents, lead with the repo-aware version (it has context a generic
draft lacks) and optionally seed with a cross-model draft for diversity.

---

## The four failure modes this guards against

1. **Building the wrong thing well** — the execution tiers are excellent at driving
   to done, which is exactly what makes them dangerous. Sharpen + Challenge.
2. **Building the timid thing well** — competent, safe, forgettable. Out-of-the-box.
3. **Losing the problem** — compression gates, reload ritual, provenance.
4. **Mismatching harness to scope** — drowning a one-hour task in ceremony, or
   ripping the gate out under deadline. Cut scope, never the gate or the craft pass.

---

## Minimum rig for a new repo

`SPEC.md` · `VERIFICATION.md` · `TASKS.md` · `Makefile` (check / check-fast) ·
`init.sh` · `.claude/hooks/gate.sh` · `.claude/hooks/stop-gate.sh` + Stop hook in
`.claude/settings.json` · `.git/hooks/pre-commit` · `LOOP_PROMPT.md` · `ralph.sh` ·
`learning-tests/FINDINGS.md`.

Source: https://github.com/chandrameenamohan/india-radar/blob/main/software_development_workflow.md
