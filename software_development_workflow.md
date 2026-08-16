# Workflow — Prompt Pack (v4)

Copy-paste prompts for building greenfield projects or modifying brownfield ones.
Fill in `<PLACEHOLDERS>`. Run roughly in order; don't run every tier every time.

**Two things this pack is built around — read once, then internalize:**

1. **Align, don't control.** A capable model's bottleneck is no longer its ability —
   it's how much of *your actual situation and intent* reaches it. Every prompt here
   transfers context and intent, then gets out of the way. You are not programming a
   machine with instructions; you are briefing a colleague who lacks your context.

2. **Keep the problem head-sized (Norvig).** You will not hold a large project in your
   head at full resolution — so don't try. Hold a compressed **map**; let the artifacts
   (SPEC, bead graph, provenance) hold the **territory** you can reload on demand. When
   something *won't compress*, that's not a comms failure — it's the design telling you
   it doesn't fit yet. Simplify before you build.

**Tiers:**
- **Scope** (0.25) = right after Sharpen, size the problem so the harness matches
  the constraint (Lightning / Assignment / Full) without bending the quality bar.
- **MVH** (minimum viable harness) = steps 0–6 + Sharpen. Most tasks stop here.
- **Judgment** (0.5, 1.5) = run for anything consequential. Cheap; catches the
  wrong thing built (0.5) and the timid thing built (1.5).
- **Evaluator** (7) and **Team** (8) = only when the task demands them.
- **Compounding** (9–10) = the layer that makes the *next* project faster.

> Reusable habit: prefix any big/ambiguous ask with **Sharpen** (0), then set
> **Scope** (0.25) so you build to the constraint, not past it. Prefix any
> *consequential* ask with **Challenge** (0.5). Once a plan feels done — before
> you lock it — run **Out-of-the-box** (1.5).

---

## 0 · SHARPEN (alignment handshake — your input layer)

```
I'm going to describe something in rough, possibly imperfect English.
This is ONLY an alignment handshake — not the spec, not the build.

Before doing ANY work:
1. Restate what you understand I want, in your own words.
2. List every assumption you'd have to make to proceed.
3. Ask about anything ambiguous or underspecified — one batch, only the
   non-obvious ones.
4. In one or two sentences: is what I'm asking for even the right thing to
   build? If you see a materially simpler path, say so now.

Then STOP. The output of this step is shared understanding, nothing more.
Do NOT start the spec or any code until I answer and explicitly choose the
next step.

My request: <ROUGH DUMP — type or dictate, don't worry about grammar>
```

---

## 0.25 · SCOPE (size the problem before you size the harness)

> Sharpen aligns on WHAT you want; this aligns on HOW MUCH harness that want
> deserves. The pack adapts its weight to the scope — but never its quality.
> Cutting scope is how you hit a deadline; cutting the gate is how you ship
> something broken. So bend the harness to the constraint and hold the quality
> bar fixed. Run this immediately after Sharpen, before Challenge.

```
Before we go further, classify the SCOPE of this build using AskUserQuestion,
then tell me which steps of this pack we'll run and which we'll compress or
skip — and why. The rule is fixed: harness weight bends to the constraint, the
QUALITY BAR DOES NOT. We cut scope, never the gate or the craft pass.

Ask me which mode this is:

- LIGHTNING (≤ ~1 hour, hard time box): one working thing, fast. Compress to
  Sharpen → spec-in-head (3 lines, not a full SPEC.md) → ONE-pass build →
  deterministic gate → quick craft pass. Ruthlessly cut FEATURES to fit the
  clock; do NOT cut the gate, the tests on what you DID build, or the craft
  pass. Tell me out loud what you're dropping, so the cut is a decision, not an
  accident.

- ASSIGNMENT (production approach, time-boxed showcase): the deliverable is
  proof of PRODUCTION JUDGMENT, not just working code. Lead with an HLD I can
  put in front of a reviewer FIRST — problem framing, architecture sketch, the
  key trade-offs AND the ones I rejected, data/flow, failure modes, and what I'd
  build next with more time. Get my sign-off on the HLD, THEN run a compressed
  real flow: SPEC-lite → small bead set with DoD → gate → build loop → craft
  pass. Quality is the thing being graded here — keep every gate.

- FULL (real production project, no hard clock): run the full pack in the normal
  order of operations.

After I pick: restate the tailored step list for this scope (which run, which
compress, which skip) in a few lines; give me a rough time budget per phase if
there's a clock; and for ASSIGNMENT, produce the HLD as the first artifact.
Then STOP and wait for me to confirm before any build.
```

---

## 0.5 · CHALLENGE (the judgment tier — run before any consequential build)

> This is the step most harnesses lack. Everything downstream drives toward
> building the plan *well*; nothing else asks whether the plan is *right*. A
> capable model will help you build the wrong thing flawlessly unless you make
> space for it to push back. This step is that space.

```
Before we spec this, argue against it. I want your judgment, not your
compliance.
- Is this the right thing to build at all? What problem is it really solving,
  and is there a more direct way to solve that problem?
- Is there a materially simpler approach that gets ~80% of the value for far
  less complexity? Describe it.
- What part of this plan is most likely to be WRONG, or most likely to be
  regretted in six months? Where's the load-bearing assumption?
- What would you NOT build here, and why?

Push back hard — I'd rather kill or shrink a bad idea now than build it
cleanly. Then stop; I'll decide whether to proceed, simplify, or rethink.
```

---

## 1 · PLAN → SPEC (the interview + the compression gate)

```
I want to build: <1–4 SENTENCE DESCRIPTION>.

Interview me in depth using the AskUserQuestion tool. Cover product scope,
users and their core jobs, UX, edge cases, failure modes, explicit non-goals,
and the key technical CONSTRAINTS — but stay at product + high-level architecture. Do NOT pin down
granular implementation details: a wrong low-level decision here cascades
downstream, so capture intent and constraints and leave the "how" to
implementation. Be ambitious about scope.

Ask only non-obvious questions, dig into the hard parts I haven't considered,
and keep interviewing until the picture is complete.

THEN — before writing the spec — give me a TEN-SENTENCE COMPRESSION: the core
thing being built, the keystone decision everything hangs on, and the one
genuinely hard part. If you cannot get it that small, say so — that means it's
too tangled to build well yet, and we simplify the design before proceeding.
Wait for me to confirm the compression is right.

Only then write SPEC.md with:
- product overview (lead with a one-line thesis)
- numbered feature list (each with an observable acceptance description:
  what a user or caller can observe when it works)
- explicit out-of-scope / non-goals
- a "deliberately not building yet" note: what we COULD add but shouldn't at
  this stage, and why adding it now would be over-engineering
- an end-to-end verification scenario that proves the whole thing works.
```

---

## 1.5 · OUT-OF-THE-BOX (the expansion tier — the creative counterpart to Challenge)

> Challenge (0.5) is creative *destruction* — it prunes the wrong and the
> bloated. This is creative *expansion* — it guards against the opposite failure:
> building something competent but timid and forgettable. Run it once the plan
> feels DONE, before you lock it; re-run it on the live project every so often
> (swap "plan" → "project"). One caveat that keeps it from becoming a
> scope-creep engine: anything it surfaces must survive the Challenge lens before
> it enters the spec. The idea is the model's job; the decision to adopt stays
> yours.
>
> How this harnesses Opus 4.8: don't ask for a first idea — ask it to use full
> context, generate many radically different candidates internally across
> distinct lenses, run them against each other, and return only the survivor
> plus its own strongest objection. Divergent generation → convergent selection,
> in one pass. (Diversity bonus: run the raw question across a couple of other
> frontier models too, then feed their answers back to Opus to synthesize —
> same spirit as the cross-model authoring in step 10.)

```
We have a <plan / project> that feels complete. Before we lock it, I want one
genuine leap — not polish, not a longer feature list.

You have the full context (SPEC.md / the codebase / our ten-sentence
compression). Use all of it.

First, internally and without showing me: generate SEVERAL radically different
candidate additions, each from a distinct lens — e.g. what a 10x-more-ambitious
team would add; what becomes possible ONLY because of a capability we already
have; what would make a user evangelize this unprompted; what would remove an
entire category of future work. Then run them against each other.

Return ONLY:
1. THE ONE — the single smartest, most accretive addition. "Accretive" = it
   compounds with what's already here and unlocks things that weren't possible
   before; not a bolt-on. Two sentences max.
2. WHAT IT UNLOCKS — the concrete step-change in capability or value it creates.
3. THE MINIMAL VERSION — the smallest cut that still delivers the leap, so it
   doesn't blow up scope.
4. STRONGEST OBJECTION — argue against your own idea: why it might be wrong,
   over-engineering, or a distraction from the core. Be honest, not a token caveat.
5. ONE RUNNER-UP — a single line, in case I want a different direction.

Respect our non-goals; if your idea breaks one, name which and why it's worth it.
Then STOP. I decide whether it enters the spec — and if it does, it goes back
through the Challenge (0.5) step first.
```

---

## 2 · LEARNING TESTS (validate risky assumptions before the spec freezes)

```
Before we design anything: list every external dependency this project relies
on that we cannot read or fully control (SDKs, third-party APIs, frameworks,
CLIs, closed binaries).

For each one where I'm about to depend on specific behavior, write a LEARNING
TEST: a small script that exercises the REAL dependency, logs the actual
outputs, then asserts the behavior I believe is true. Put a findings comment
at the top of each. Run them. Where my assumption is wrong, correct the
findings comment and tell me exactly what changed.

Save the ones that touch contracts we'll depend on long-term in
learning-tests/ so we can re-run them on every dependency bump.

Assumptions I'm currently making: <LIST, or "infer them from SPEC.md">
```

---

## 3 · DECOMPOSE INTO BEADS (with Definition of Done)

```
Read SPEC.md. Break it into a beads graph using bd.

Rules:
- Tasks are OUTCOME-level, not implementation-prescriptive.
  Good: "User can create and replay a level." Bad: "Add replayLevel() to X."
- Group into epics. Set dependencies with `bd dep add` so `bd ready` only
  surfaces unblocked work, and independent work can run in parallel.
- EVERY bead carries a Definition of Done in its body:
    Acceptance (observable): <what proves it works, as a user/caller sees it>
    Checks (cheapest deterministic first):
      lint -> typecheck -> unit:<test names> -> integration/E2E:<named check>
    Out of scope: <explicit>
- A bead isn't finished being created until its checks are stated.
- Add to each bead: "Do not weaken, delete, or skip these checks to pass."

Show me the epic/bead tree and dependency edges FIRST. The tree should be
scannable — if it has sprawled past what I can hold in my head at a glance,
that's a signal the decomposition (or the design) is too complex; flag it and
propose a simpler cut. Wait for my approval, then create them with bd.
```

---

## 4 · DESIGN THE BACK-PRESSURE HARNESS (plain text, before code)

```
Before writing ANY implementation code, design the verification harness in
plain text. Do not implement features yet.

Produce VERIFICATION.md describing:
- The single command that runs the full gate (e.g. `make check` =
  lint + typecheck + unit + e2e) and how each layer is invoked.
- For UI/frontend features: how we drive the RUNNING app, not just unit tests.
  Push as much as possible into DETERMINISTIC checks before reaching for an
  evaluator — most of what feels "subjective" about a UI isn't:
    * console-clean: drive the page, assert ZERO console errors, unhandled
      rejections, or failed network requests (catches "looks fine, secretly
      broken").
    * behavioral: Playwright drives the running app (navigate -> act -> assert
      on actual rendered state, route, fired request), not the DOM in a vacuum.
    * visual regression: screenshot key states, diff against committed
      baselines (first run establishes baselines, a human approves them once).
    * accessibility: run axe / a11y snapshot, fail on violations.
  Reserve the LLM evaluator (Step 7) for the ONE thing none of these can judge:
  "does this match the design intent / feel right."
- Deterministic CODE-QUALITY signals, folded into the gate where the toolchain
  supports them: unused-export / dead-code detection, duplication detection, and
  a file/function size or complexity threshold. These keep craft enforceable
  without a human; reserve the subjective craft review (abstraction-fit, naming,
  "reads like the codebase") for the reviewer in Step 7.5.
- init.sh: boots the dev environment and runs a basic smoke test.
- Which checks are deterministic (preferred) vs. which genuinely need an LLM
  evaluator (UX / subjective quality only).
- What we are deliberately NOT verifying at this stage, and why adding it now
  would be over-engineering for where we are.

Then create init.sh and the empty check scaffolding so `make check` runs today
(even while most checks are still pending/stubbed to fail).
```

---

## 5 · BUILD LOOP (session-start ritual + ONE bead)

Use as the per-session prompt, or as the body of `LOOP_PROMPT.md` for a Ralph
loop: `while :; do cat LOOP_PROMPT.md | claude -p --permission-mode auto ; done`

> **Precondition for unattended looping:** do NOT run this loop in auto-permission
> mode until the deterministic gate (Step 6) exists AND has been shown to block on
> a real failure. An unattended loop is only as safe as the gate that stops it.
> The gate is the brake; never drive without it.

```
Get your bearings, then implement exactly ONE bead:

1. Run init.sh and the smoke test. If the app is broken, FIX THAT FIRST —
   never start new work on a broken base.
2. Run `bd prime`; read recent progress and `git log`.
3. Run `bd ready`, pick the highest-priority unblocked bead,
   `bd update <id> --claim`.
4. Implement it FULLY. No placeholders, no stubs, no "simple version for now."
   Before assuming something isn't implemented, search the codebase with a
   subagent.
5. Run THIS bead's checks (lint -> typecheck -> unit -> e2e). Show the ACTUAL
   output as evidence; do not claim success without it.
6. LEAVE IT CLEANER: before committing, run a quick craft pass on what you just
   wrote — dead code removed, no duplicated logic, no over-abstraction, names and
   structure that READ LIKE the surrounding code (e.g. the /simplify skill). Then
   re-run THIS bead's checks so the cleanup is still green. Craft is part of done,
   not a later sweep.
   (Keep it cheap: this is a quick pass on the DIFF, not the codebase; re-run only
   the fast checks (lint/typecheck/unit) here and leave the full gate for commit.
   SKIP it entirely for throwaway spikes — match the effort to the code's lifespan.
   The deep craft review is on-demand in Step 7.5, not every bead.)
7. When green: commit with a descriptive message, `bd close <id>`, and
   `bd remember "<durable learning for future loops>"`.

Work on ONE bead only, then stop.
```

---

## 5.5 · RELOAD (run at the start of any session where the problem has left your head)

> `bd prime` reloads the *machine's* state. This reloads *yours*. After an
> unattended loop or a few days away, the problem is no longer in your head —
> rehydrate the map before you make decisions, instead of re-reading the diff.

```
Reload my mental model of this project. Keep it whiteboard-sized — small enough
that I could redraw it from memory:
- The core idea in 2–3 sentences.
- What's done, what's in progress, what's still open.
- The key decisions made and WHY (pull from bd remember / commit trails).
- The one or two things I'm most likely to have forgotten that would bite me.
- Anywhere the actual implementation has DRIFTED from SPEC.md or the original
  intent — I want the map to still match the territory.
```

---

## 6 · DETERMINISTIC GATE (the part that lets you walk away)

**Option A — `/goal` (drives the whole build to done):**
```
/goal All beads are closed (`bd ready` returns empty) AND `make check` exits 0
with lint, typecheck, unit, and e2e all passing. Show the passing output as
evidence. Do not modify or weaken any check to satisfy this condition.
```

**Option B — Stop hook (deterministic, can't be argued with):**
```
Write a Claude Code Stop hook in .claude/settings.json that runs `make check`
whenever you think you're done, blocks the turn from ending until it exits 0,
and injects any failure output back into context. Also add a pre-commit hook
that runs the same gate. Show me that it actually blocks on a real failure
before I rely on it.
```

---

## 6.5 · THE RALPH RIG (the concrete loop-under-a-gate setup)

> Steps 5 + 6 in practice. "Ralph" (after Geoff Huntley) = a `while` loop that
> spawns a FRESH headless Claude each iteration; each reads `LOOP_PROMPT.md`,
> implements ONE bead, and stops. All memory lives in **beads + git**, never in
> the model's head — so iterations are stateless and resumable, and the **Stop
> hook gate is the only thing that lets you walk away.** Build it as four files.

```
Set up a Ralph rig for this project, matching this pattern:

1. .claude/hooks/gate.sh — the gate in ONE place: runs `make check` from the
   project root, exits with its code. Everything else calls this.

2. .claude/hooks/stop-gate.sh + register it as a "Stop" hook in
   .claude/settings.json. CRITICAL: gate it on an env flag (e.g. PW_LOOP=1) so
   it enforces ONLY during the loop and is a silent no-op in my normal
   interactive sessions. When active and the gate is RED: exit 2 (Claude Code
   blocks the stop and feeds stderr back into context); when GREEN: exit 0.

3. .git/hooks/pre-commit — also runs gate.sh, so the LAST COMMIT IS ALWAYS
   GREEN. This is what makes recovery safe: an interrupted iteration can always
   discard partial work back to a known-good base.

4. LOOP_PROMPT.md — the body of one iteration, in this order:
   - Recovery FIRST: check `bd list --status in_progress` (bd ready hides these);
     if a bead is mid-flight, resume it; discard untrusted uncommitted work
     (`git checkout -- . && git clean -fd`) since the last commit is green.
   - Orient (SPEC.md, VERIFICATION.md — the invariants a single DoD doesn't repeat).
   - `bd ready` → claim highest-priority bead → implement FULLY (no stubs) →
     `make check` with REAL output as evidence → CRAFT PASS (simplify: dead-code,
     dup, over-abstraction — re-run the gate after) → commit → `bd close` →
     `bd remember` the WHY (provenance, Step 9).
   - Attendance rules: MISSING INPUT = mark `blocked --notes "NEEDS INPUT: …"` and
     STOP, never fabricate. SUBJECTIVE/TASTE acceptance a deterministic gate can't
     judge (e.g. "does this match the source faithfully?") = mark
     `blocked --notes "NEEDS REVIEW: …"` for the human, don't self-close.
   - End with a fixed VALIDATION SUMMARY block (bead, what built, acceptance,
     how to verify yourself, decisions, needs-validation).

5. ralph.sh — the driver. ATTENDED by default (pause for my validation after
   each bead); `--auto` for unattended. Export the PW_LOOP flag so the Stop hook
   activates. Tee output to logs/. Add PROGRESS DETECTION: if an iteration closes
   no bead and defers none, it's stuck — in --auto, STOP rather than spin forever.
   Stop when `bd ready` is empty.

Then PROVE the brake before I rely on it: with the gate RED, show the Stop hook
exits 2 and blocks WITH PW_LOOP=1, and is a silent no-op WITHOUT it.
Run:  ./ralph.sh          (attended)
      ./ralph.sh --auto   (unattended — only after the brake is proven)
```

> Two driver flavors, both valid: **attended** (`ralph.sh` pauses per bead — best
> for the first beads and anything risky) and **unattended** (`--auto` / a
> `MAX_ITERS` cap + a completion sentinel like `LOOP-COMPLETE`). Always run
> attended until the gate has caught at least one real failure.

---

## 7 · SKEPTICAL EVALUATOR (add only when the task exceeds reliable solo capability)

**Create the agent:**
```
Create a subagent "evaluator": a hostile QA engineer that assumes every feature
is broken until proven otherwise. Given a bead's Definition of Done, it drives
the RUNNING app via Playwright (clicking, hitting endpoints, checking DB state)
and, for each acceptance criterion, returns PASS/FAIL with concrete evidence
(exact file/line/condition on failures). Report ONLY gaps that affect
correctness or the stated requirements — not style, not speculative edge cases.
Read this repo's architecture first and tailor checks to our actual stack.
Tools: Read, Grep, Bash, Playwright MCP. Save to .claude/agents/evaluator.md.
```

**Invoke (only AFTER the deterministic gate passes):**
```
Use the evaluator subagent to verify bead <id> against its Definition of Done.
Return failures as a specific bug list for the builder, then re-review after
fixes.
```

**Tune it (do this a few times — it's a poor QA agent out of the box):**
```
Read the evaluator's last few runs. Find where its judgment diverged from mine
(approved something broken, or flagged non-issues). Rewrite the evaluator
prompt to fix those specific divergences. Show me the diff.
```

---

## 7.5 · CODE QUALITY (the craft reviewer — works ≠ well-built)

> Correctness and craft are different reviews. The gate (6) proves it WORKS; the
> evaluator (7) hunts BUGS — neither catches a codebase that passes every test
> while rotting: duplicated logic, dead scaffolding, over-abstraction, drift from
> the local conventions. The Ralph loop makes this acute — it generates a lot of
> code with no continuous human taste holding it coherent, so craft has to be
> verified, not assumed. The per-bead pass (Step 5, item 6) is the continuous
> defense; this is the on-demand deep pass for consequential beads, before a
> release, or periodically on the live project.

```
Review the code changed for <bead / branch / the recent loop iterations> for
CRAFT, not correctness:
- Reuse: did this reinvent something that already exists in the repo? Search
  before assuming it's new.
- Unnecessary complexity / over-abstraction: indirection that earns nothing,
  premature generalization, cleverness over clarity.
- Dead code: unused exports, stubs, scaffolding left behind.
- Consistency: does it READ LIKE the surrounding code — naming, structure,
  idioms?

Apply the fixes that PRESERVE behavior (e.g. the /simplify skill); for judgment
calls that change behavior or trade off real design, flag them for me rather
than guessing. Re-run `make check` so everything stays green after.

This is NOT a bug hunt — that's the evaluator (Step 7). It is NOT scope creep
or "should we build this" — that's Challenge (Step 0.5). Hand those back to
their owners. (For the bug + convention-compliance complement, /code-review.)
```

---

## 8 · PARALLELIZE BY DEPENDENCY (the Team tier)

```
Look at `bd ready`. Identify the beads that are GENUINELY independent — no
shared files, no ordering dependency. Only those are safe to parallelize.
Start each in its own worktree (or agent-team member); each claims one bead
with `bd update --claim` so they don't collide. Do NOT parallelize beads that
touch the same modules — let dependency order serialize those.
Report the parallel set and the serial remainder before starting.
```

---

## 9 · CAPTURE PROVENANCE (the scarce complement — keep the "why")

> Code records WHAT. It cannot record WHY. The "why" is what lets you (or a
> teammate, or a future agent) reload a region of the problem in seconds instead
> of re-deriving it. This is how "keep the problem in your head" survives across
> time — you don't hold it continuously, you rehydrate it on demand.

```
For this bead, alongside the code, record the decision trail: the intent that
drove it, the key decisions and WHY, and any alternative you rejected and why.
Store it with the bead via `bd remember` and reference it in the commit body.
Goal: someone with zero context (future me, a teammate, a future agent) can
reconstruct WHY this was built this way, not just WHAT changed.
```

---

## 10 · COMPOUND YOUR TOOLING (run every ~2 weeks)

**Regenerate skills from your own history:**
```
Review my Claude sessions across all my projects from the last month.
Identify (a) the prompt patterns that led to clean outcomes vs. the ones that
sent you in circles, and (b) recurring workflows I do manually that should be
skills. Propose a refreshed set of skills/commands and update the stale ones.
Show me the diff before writing anything.
```

**Build an expert agent (lead repo-aware; seed cross-model for diversity):**

Opus can usually author its own — it has repo context a generic draft lacks. So
lead with the repo-aware version. But a second model sees the domain
differently, and that diversity is worth harvesting — so seed with a cross-model
draft when the domain is non-trivial.

```
[Step 1 — optional, in another model, e.g. ChatGPT/Gemini]
Write a Claude Code subagent prompt for an expert in <DOMAIN>, using current
best practices as of <DATE>. Output only the subagent prompt.

[Step 2 — in Claude, with or without the draft above]
Draft a Claude Code subagent for an expert in <DOMAIN>, using current best
practices. Read THIS repo's architecture FIRST and tailor the expertise to our
actual stack and conventions — you have repo context a generic draft wouldn't.
If I paste an external draft below, treat it as raw input to harvest ideas
from, not as authority — lead with your own repo-aware version.
External draft (optional): <PASTE or "none">
Save to .claude/agents/<name>.md.
```

---

## Order of operations

**Brand-new project:**
0. Sharpen → 0.25. Scope (Lightning / Assignment / Full) →
0.5. Challenge (is this even right?) → 1. Plan→SPEC (compress first)
→ 1.5. Out-of-the-box (one leap, then back through Challenge) →
2. Learning tests → 3. Beads+DoD → 4. Design harness → 6. Gate →
5. Build loop under the gate → (7. Evaluator if needed) →
(7.5. Craft reviewer on consequential beads) →
(8. Parallelize if independent work exists). 9. Capture provenance throughout;
5.5. Reload at every cold start; 10. Compound tooling between projects.

**Brownfield change:** Sharpen → Challenge → (skip to) read the real code and
write a focused mini-spec for the change → small bead set with DoD → build under
the existing gate → provenance. Don't impose the full greenfield ceremony on a
small change; match the harness weight to the actual risk.

**Lightning (≤1 hour):** Sharpen → Scope (Lightning) → spec-in-head (3 lines) →
lightweight deterministic gate → build the ONE thing fully → craft pass. Cut
features to the clock; keep the gate and the craft pass. That's the whole flow.

**Assignment (production showcase):** Sharpen → Scope (Assignment) → HLD as the
first artifact (get sign-off) → SPEC-lite → small beads + DoD → gate → build
loop → craft pass → provenance on the key decisions. The HLD plus a green gate
are what demonstrate production judgment — neither is optional.

---

## The four failure modes this pack guards against

1. **Building the wrong thing well.** The execution tiers (1–8) are excellent at
   driving to "done," which makes them dangerous if the goal is wrong. Steps 0
   and 0.5 are the guard — never skip the Challenge step on a consequential build
   just because the harness is good at executing.

2. **Building the timid thing well.** The same drive-to-done makes it easy to ship
   something competent, safe, and forgettable. Step 1.5 is the guard — once the
   plan is sound, ask for the one leap that makes it matter, then re-prune it
   through Challenge so ambition doesn't become bloat.

3. **Losing the problem.** As the project grows past one head, the compression
   gates (1, 3), the reload ritual (5.5), and provenance (9) are what keep it
   re-loadable. If the model can't compress it and you can't hold the map, the
   design is too complex — that's signal, act on it before you build more.

4. **Mismatching harness to scope.** The pack is heavy by design, which makes it
   easy to drown a one-hour task in ceremony — or, under deadline, to ship with
   the gate ripped out. Step 0.25 is the guard: size the problem first, then bend
   the harness weight to the constraint while holding the quality bar fixed. Cut
   scope to hit the clock; never cut the gate or the craft pass.

> The whole pack in one line: **transfer intent so the model solves YOUR problem;
> require compression so the problem stays head-sized; reserve judgment and scope
> for yourself.** Execution is the model's job — alignment and the decision to
> proceed are yours.
