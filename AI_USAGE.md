# AI_USAGE — how AI tools were actually used to build this

**Scope.** This is the fourth deliverable named in `QAFD.pdf` — *"How AI tools were leveraged during
development"* — one of four equally-weighted evaluation axes. It is the log of the process, not the
product. What the system does with a model at runtime is `SPEC.md` F3/F4 and the architecture
document; what follows is how the repository in front of you got written.

**The rule this document is written under.** Every claim below is traceable to something you can
open: a merged PR body, a commit, a test file, a bead close reason, a `bd` memory, or a measurement
in `learning-tests/FINDINGS.md`. Where the repository disagrees with itself, or where a thing was
attempted and abandoned, that is written here too. There is a verification appendix at the bottom
that names the command for each section. **Nothing in this file is an adjective standing in for a
number.**

Elapsed: **2026-08-16 14:08 → 2026-08-18 08:31**. Fourteen merged PRs, **41 closed beads and 5
open** (46 in the tracker), **6 of the 7 epics closed** — E1–E5 plus the UX epic `dq-j15`; E6
(`dq-cyi`, delivery) is the one still open. `app/` is 21 Python files / 5,130 lines; `web/app/` is
15 TypeScript files; `tests/` is 42 files and 283 collected checks.

Every number in this file is a number a command returns, and the appendix names the command. Where
one moved after this was written, the fix was to re-run the command, not to soften the sentence:
an earlier draft shipped `39 closed / 44 in the tracker / check-ui 52 passed, 9 skipped`, and the
first two things the appendix invites a reviewer to run were the first two that contradicted it.

---

## 0. The short version

| | |
|---|---|
| **Tooling** | Claude Code (Opus 5) as the agent; `bd` (beads, Dolt-backed) as the only task tracker; `gh` for PRs; Playwright for the browser layer; the Claude Agent SDK inside the product itself |
| **Process** | The author's own prompt pack, `software_development_workflow.md`, at **FULL** tier — with the Ralph/autonomous loop **deliberately omitted** and the deterministic gate it depends on **kept** |
| **The unit of delegation** | One bead, one branch, one PR — and one commit per bead for PRs #1–#11. **The three build waves suspended the commit half**: each is one attended session and one commit covering 8+ beads (§2). Agents ran **no state-changing git command**; the author branched, committed, pushed and merged all fourteen PRs. (The wave commits carry a `Co-Authored-By: Claude Opus 5` trailer — that is Claude Code's convention on a commit the author made, not an agent commit) |
| **What made delegation safe** | `make check` — offline, installation-free, **187 passed, 0 skipped, 2.75 s** — plus an anti-cheat pass that walks every test with `ast` and fails the gate on a test that asserts nothing. Documented as blocking on **thirteen** separate occasions, listed in §4 |
| **Learning tests** | Four, run against real dependencies **before the spec froze**. Every one of them falsified an assumption the spec was about to be built on. §3 |
| **Where the human was load-bearing** | The UI direction (overrode a three-judge panel, forcing a frozen spec to a documented Rev 0.4), every visual baseline (approval is a *mechanism*, not a convention — and the mechanism had a hole, §6.2), and every bead that `bd` refused to close. §6 |

---

## 1. The process was chosen, not defaulted

The workflow followed is `software_development_workflow.md` — the author's own prompt pack, written
before this project existed. At kickoff its Step 0.25 asks which tier to run; the answer was **FULL**
(`HANDOFF.md` §2), and the tier list was then modified in exactly one place.

**The Ralph/autonomous loop was omitted on purpose. The deterministic gate it depends on was kept.**

The pack's §6.5 describes a "Ralph rig": a `while` loop spawning a fresh headless Claude per
iteration, each reading `LOOP_PROMPT.md`, implementing one bead, and stopping, with a `Stop` hook
that refuses to let the model finish while `make check` is red. Its own §5 states the precondition:

> **Precondition for unattended looping:** do NOT run this loop in auto-permission mode until the
> deterministic gate (Step 6) exists AND has been shown to block on a real failure. An unattended
> loop is only as safe as the gate that stops it. The gate is the brake; never drive without it.

The reasoning recorded in PR #1, before any code existed, and repeated in `HANDOFF.md` §5:

> **The autonomous build loop is omitted by choice**, while the deterministic gate it depends on is
> kept. **The gate is the part that survives; the loop driver is what current models have outgrown.**

That is a claim about where the value in the rig actually sits. The loop driver exists to solve
context exhaustion and unattended restart — problems a current model with a large context and a
resumable session handles without a `while` loop around it. The brake solves a problem no model
version fixes: *the agent believing it is done.* So the project ran **attended, one bead at a time**,
and spent the effort on the brake instead.

What replaced the loop was three **build waves**, each an attended session ending in one PR: wave 1
(26 files, +3,926), wave 2 (40 files, +6,734), wave 3 (62 files, +10,349). The pack's other steps ran
as written: Challenge (0.5) before the spec, Out-of-the-box (1.5) after it — *"one candidate
surfaced, argued against, declined"* — learning tests (2) before the freeze, tasks with Definitions
of Done (3), the harness (4/6), craft review (7.5), and this document (9, provenance).

---

## 2. What was delegated, and what was not

| Delegated to an agent | Kept by the human |
|---|---|
| Writing `SPEC.md`, `VERIFICATION.md`, `HANDOFF.md`, `README.md` from the brief | Choosing the tier, and choosing to drop the loop |
| Writing and running all four learning tests against real dependencies | Reading their findings and deciding what the spec should say |
| Generating four UX variants and running a three-judge scoring panel | **Overriding the panel** — picking the 23.0 over the 25.4 (§6) |
| All application code, all tests, all Dockerfiles | Every `git commit`, `git push`, `gh pr merge` — fourteen of them |
| Filing beads and writing Definitions of Done | Ratifying a DoD that an agent proposed to narrow (§5, B8) |
| Taking screenshots | **Approving screenshots** — enforced by `git ls-files`, not by policy (§6) |
| Proposing a PostgreSQL privilege split | Authorising the `CREATE ROLE`/`GRANT` that made it real (§5) |

**Git discipline, recorded in `HANDOFF.md` §4a:** never commit to `main`; one branch per unit of
work; one commit per bead with the bead ID in the subject; `gh pr create` and **do not merge** — the
author reviews and merges. The finding goes in the PR body, not only in the bead notes. That last
clause is why the fourteen PR bodies are the densest evidence in this repository, and why this
document could be written from them.

**One clause of it was suspended, and `git log --oneline` shows that in ten seconds, so it is stated
here first.** The *one commit per bead with the bead ID in the subject* rule held for PRs #1–#11 —
`LT-2b: verify Agent SDK auth, tool suppression, structured output (dq-uco)`,
`SEED: bulk demo dataset with documented deliberate defects (dq-e4s)`, and so on. **The three build
waves did not follow it.** Each wave was one attended session and shipped as one commit covering
eight or more beads, with no bead ID in the subject:

| PR | Commit | Beads | Size |
|---|---|---|---|
| #12 | `649636a` *Wave 1: the boundaries and the rule domain (E1 partial, E2)* | B2–B9 | 26 files, +3,926 |
| #13 | `257c108` *Wave 2: the privilege split, discovery, proposals, authoring, execution, results* | E3, E4 | 40 files, +6,734 |
| #14 | `23ee9e1` *Wave 3: the two front doors, the results screen, delivery, and SPEC §7 end to end* | E5, E6 partial | 62 files, +10,349 |

Across the whole repository that is **18 non-merge commits against 41 closed beads**. The reason is
the same one §1 gives for the waves themselves — an attended session ending in one reviewable PR —
and the cost is real and worth naming: a wave commit cannot be reverted per bead, and the per-bead
evidence lives in the bead close reasons and the PR body rather than in the history. Given again,
the branch would stay one per wave and the commits would still be one per bead.

---

## 3. Learning tests: four assumptions, four falsifications, zero code depending on them

Step 2 of the pack says: before freezing a spec, take every assumption the spec rests on that you
have not personally verified in *this* version of *this* dependency, and write a script that finds
out. The scripts are in `learning-tests/`; the write-ups are `learning-tests/FINDINGS.md`; each is a
merged PR (#2, #4, #5, #7). `SPEC.md` §8 named two of them as **blocking the freeze**, and the freeze
did not happen until they landed (PR #8).

**All four confirmed most of what they tested and falsified something load-bearing in every case** —
which is what the practice is for. LT-2b's write-up carries five `[x]` confirmations (auth from
`CLAUDE_CODE_OAUTH_TOKEN`, tools fully suppressed, `max_turns=1` enforced, structured JSON by
instruction alone, `setting_sources=[]`) before its one UNEXPECTED; LT-1a confirmed pushdown three
ways and the exact counts 25/25, 7/7, 0/0 before its four surprises; LT-2a confirmed version,
registry size, object model and round-trip. The falsification in each row below is the thing the
spec would otherwise have been built on.

| Test | The assumption | What actually happened | What it changed, before any code depended on it |
|---|---|---|---|
| **LT-2b** · Agent SDK | A model shown a data sample proposes sensible rules | Every rule was **statistically true and business-naive**: `status IN {shipped, pending, cancelled, returned}` (only the observed values), `order_total BETWEEN 0 AND 89,400` (overfits the observed max). It **never proposed `order_total >= 0`** — the actual invariant | Evidence lines and unsaved-proposal status became **load-bearing, not decorative**. A domain expert became a first-class user rather than a reviewer of last resort. Also found: `setting_sources=[]` is *required*, or the developer's own global `CLAUDE.md` leaks into a server-side call. 6.6 s, $0.041/call |
| **LT-2a** · GE object model | "Instantiate it against GE before persisting" is a sufficient validity gate (SPEC INV-2) | Of **25 invalid-rule probes, GE accepted 10** while reporting success — `min=100, max=1`; `regex="[unclosed"`; empty `value_set`; `type_="NOT_A_TYPE"`; `row_count_to_be_between()` with no bounds. And `ExpectationConfiguration(type="expect_column_values_to_be_vibey")` **constructs without error** | INV-2 needed our own per-type sanity table *before* GE sees the kwargs. F12 renders `Compiled · shape OK` as a **neutral** token with no passing-verdict class. The catalog cannot be generated from GE introspection |
| **LT-1a** · GE on PostgreSQL | A rule either passes or fails | `catch_exceptions` defaults to `True`, so a rule that **could not run** lands as `success: false, result: {}` — **visually identical to a failing rule**. Also: no single result shape (four of fifteen types can never carry a violating count); `success` is not `unexpected_count == 0`; the results list **reorders** the moment an expectation errors | `errored` became a **third result state**, never folded into failed. "A rule that did not run has a coverage meaning, not a data-quality meaning" |
| **LT-1b** · Latency | The interaction model assumes a run returns fast enough to watch | **14.84 s** for the ten-rule suite over 500,000 rows. Only **3 rules** fit under 10 s. Cost is a **~2.3 s floor + ~0.83 s per rule** — lumpy per *rule*, not linear in *rows*. A row cap is a **net loss** at full size (22.67 s / 1,000,127 rows moved, against 13.63 s / 156 rows uncapped) and **breaks two of the fifteen catalog types** with `KeyError: 'type'`. GE's own Python is 21% of wall clock — more than the network | Resolved SPEC **O-2** (*no cap ships*) and **O-3** (*synchronous, but progressive — not a job queue*). Unblocked the freeze. Also found `gx.get_context()` is **process-global**, which became the second half of INV-3 |

**Why this matters for an AI-first process specifically.** Three of the four findings are about a
tool confirming *well-formedness* while saying nothing about *meaning* — the model's rules compile
and are wrong; GE's constructor accepts and is wrong; a capped run is byte-identical to an honest
one. An AI process that had not tested its dependencies would have shipped LT-2b's three rules
silently, and a reviewer would have had no way to see it. `UX_HARNESS_FINDINGS.md` §2 lines these up
against the failure modes Anthropic's own long-running-agent article names, and they are the same
shape: *surface state read as completion.*

The tests also paid for themselves in avoided work. O-3's answer determined whether F8 and F13 were
built as a streaming request or as a job queue with a polling endpoint. Building the affected screens
first would have meant building them twice — which is exactly what PR #1 said, before the numbers
existed:

> Whether rule execution is synchronous or a background-job system depends on a measurement that does
> not exist yet — building the affected screens first means building them twice.

---

## 4. The gate: what made delegation safe

`make check` is offline, installation-free, app-free, and runs in under four seconds. Real output,
**2026-08-18 08:50:29 IST**, from the run that produced every number in this section:

```
ruff check app tests seed
All checks passed!
ruff format --check app tests seed
66 files already formatted
mypy app tests seed
Success: no issues found in 66 source files
python3 -m pytest -m "not ge and not e2e and not live"
collected 283 items / 96 deselected / 187 selected
================ 187 passed, 96 deselected, 1 warning in 2.88s =================
npm --prefix web run check
> eslint --max-warnings 0
> next typegen && tsc --noEmit
```

The file count is 66 rather than the 63 an earlier draft quoted, and the difference is the point of
stamping it: `seed/` was outside `SRC` until the craft pass, so `seed/seed_demo_rules.py` — 329 lines
importing `app.api.server`, `app.dq.run` and `app.rules.store` — was 329 lines the green gate had
never read. The one script deliberately frozen in there is excluded by name in `pyproject.toml` with
the reason, rather than by leaving the directory out.

Two further layers cost money or need the network and therefore sit outside it, behind markers.
Both were launched from the same shell at the same moment as the block above — concurrency that used
to take both of them red and does not any more (§5.4):

```
# 2026-08-18 08:50:29 IST — all three targets launched from one shell, at once, on one machine
make check      187 passed, 96 deselected, 1 warning in 2.88s                        CHECK_RC=0
make check-ge    33 passed, 250 deselected, 1 warning in 103.64s (0:01:43)              GE_RC=0
make check-ui    52 passed, 8 skipped, 223 deselected, 1 warning in 368.17s (0:06:08)   UI_RC=0
```

`check-ge` is 33 checks against the real seeded Supabase database; `check-ui` is a real Chromium over
a real Next process in front of a real Python process, including six real billed model calls (three
for F12, three more for SPEC §7's flow). Its eight skips are the two delivery targets nobody named
and the **six visual baselines, all written and none approved** — §6.2. `--strict-markers` is on, so
one mistyped marker is a collection error rather than a network check smuggled silently into the
fast gate.

### 4.1 The one rule the whole harness rests on

**`pending()` in `tests/conftest.py` is the only sanctioned way to produce a stub**, and it skips
*loudly*, printing `PENDING — <what it is waiting on>` on every run. That was true by convention
first, then true for five spellings out of nine, and is now enumerated —
`tests/test_code_quality_thresholds.py` walks every test file with stdlib `ast` and fails the gate
on:

- a `test_` function (sync **or** async) containing neither an assertion nor a `pending()` call;
- every spelling of a silent skip outside `conftest.py`: `pytest.skip`, `mark.skip`, `mark.skipif`,
  `mark.xfail`, `pytest.xfail`, `pytest.importorskip`, and `from pytest import skip|xfail|
  importorskip` — the import is banned rather than the alias chased.

Why it enumerates rather than trusting the convention is stated in `VERIFICATION.md` §10:

> the entire thesis of this harness is that convention does not hold, so the check now has to
> enumerate.

The check's own comments carry the reasoning for each half — *"resolve aliases, ban the import —
which catches renames-on-import for free"*, and *"`AsyncFunctionDef` is NOT a subclass of
`FunctionDef`. Omitting it makes every `async def test_...` invisible to the vacuity check below."*

This is the mechanism that makes a green gate mean something when an agent wrote both the code and
the tests. A stub that quietly passes does not merely fail to catch a bug — it poisons every
downstream decision made on the strength of the green.

### 4.2 The gate was proven to block, on the record, thirteen times

Step 6 of the pack is explicit that a gate is not to be trusted until it has been *shown* to go red
on a real break. These are the documented occasions, each with the break, the red, and the restore.

| # | What was broken | The red | Source |
|---|---|---|---|
| 1 | A deliberately dishonest test that asserts nothing | `AssertionError: test functions that assert nothing and declare no PENDING: ['tests/test_zz_anticheat_probe.py:6 test_this_asserts_nothing']` · `1 failed, 187 passed, 96 deselected in 2.70s` · `make: *** [test] Error 1`. Probe deleted, gate green again | PR #9; re-proven 2026-08-18 |
| 2 | A skip-dodge probe | Caught by **ruff at the lint layer, before pytest ran at all** — cheapest-fails-first ordering working as designed | PR #11 |
| 3 | One line — `<img src="/deliberately-missing.png" />` — in the component every route rendered | **14 failed, 7 passed, 28 skipped**, `make: *** [check-ui] Error 1`. One break tripped **two independent checks across all seven routes**: console-clean saw the 404, axe saw `critical image-alt`. Restored → **21 passed** | VERIFICATION §4.2 |
| 4 | `APP_URL` pointed at a port with nothing answering | **49 errors, zero skips.** The browser layer may not skip its way past a dead server | PR #11 |
| 5 | `APP_URL` unset | 49 skipped, 0 passed — `make check` leaves the layer out rather than pretending it ran | PR #11 |
| 6 | A single file, `web/app/expert/review/page.tsx` — a per-role URL space | `AssertionError: ['/expert/review'] resolve. A per-role URL space means a pasted permalink carries the sender's role to the receiver, which is exactly what F11 forbids.` Deleted, rebuilt → **25 passed, 24 skipped** | VERIFICATION §4.1 |
| 7 | A rejection reason planted as `""` (the store refuses a rejection with no reason) | The bounded poll still exhausted its 60 attempts and reported the identical sentence — **1 failed in 122.35 s**. This is what proves the race fix in §5.4 was a *fix* and not a *weakening* | VERIFICATION §4.7.1 |
| 8 | `COMPOSE_APP_URL` at a dead port | Fails in **0.20 s** with *"a named stack that is not running is a broken delivery, not an absent one"* — it does not skip | VERIFICATION §8.1 |
| 9 | The delivery check's own first draft — both test functions delegated their assertion to a helper | `test_no_test_function_is_vacuous` failed the gate on them **by name** until the verdict was returned and asserted at the call site. The anti-cheat caught a check written by the same session that wrote the anti-cheat's neighbours | VERIFICATION §8.1 |
| 10 | `SPEC.md` quoting a row count the seed manifest does not | The one cross-document check that survived B24 (three others were dropped as prose-policing) — proven to block, and it fires if the seed is ever re-scaled and SPEC does not follow | PR #11 |
| 11 | An off-by-one planted into `app/dq/normalise.py::_one`'s `unexpected_count` | SPEC §7's own flow went red: `AssertionError: the order_total rule reads 'failed' over 149 rows; seed/MANIFEST.md plants exactly 150 negative-total rows in orders, and the manifest is not adjusted to match.` Restored, file diffs clean | VERIFICATION §4.6 |
| 12 | `"verdict": "passed"` planted into `app/dq/run.py`'s opening event — a rule rendered as passing before it had run, the one misreading F13 forbids | Took the run screen red as well. Restored, file diffs clean | VERIFICATION §4.6 |
| 13 | The role door's layout, changed for real by bead `dq-dkq` | `role-door` moved **31.36% of its pixels against a 0.20% budget** — 156x over, and the loudest thing the visual layer can say. The check discriminated exactly as designed; the *approval* gate around it did not, which is §6.2 | VERIFICATION §4.3, bead `dq-zyt` |

**The break in #3 was chosen, not stumbled into.** From the `bd` memory recorded that day:

> WHY the break-red demo was done with a missing image rather than a broken assertion: it is the
> cheapest break that is (a) one line, (b) restorable byte-for-byte, and (c) tripwires two
> independent checks at once … which is the evidence that parametrising the hygiene checks over
> ROUTES actually buys something.
>
> REJECTED alternative: killing the server to make the layer red. It proves the `app_url` fixture,
> not the checks.

Both were exercised anyway — that is #4.

### 4.3 What the gate caught that a review would not have

Two of these are worth naming because they are the failure modes an AI-heavy process actually
produces, as opposed to the ones people worry about:

- **A route quietly forking the URL space.** Nothing else in the harness notices a second URL space
  appearing, and — per VERIFICATION §4.1 — *"it is the kind of thing that gets added by someone being
  helpful."* An agent adding `/expert/review` is being helpful. It also breaks every permalink.
- **Green over an empty set.** INV-3's second half reports `PENDING` rather than passing when there
  is nothing to scan: *"an empty scan that reports green is the exact failure this harness exists to
  refuse."*

---

## 5. The honest failures

Nothing here is hypothetical; each item has a PR, a bead, or a memory behind it.

### 5.1 An agent proposed a database privilege change and it was refused — correctly

Wave 1 shipped without B2, the read-only role. From PR #12:

> **B2 (`dq-5pb.2`, the read-only role) is unbuilt.** Creating PostgreSQL roles and privilege grants
> on the live database was refused as an unauthorised privilege change — which is the right call, it
> was never specifically asked for.
>
> So today *"we never write to a table under analysis"* is a property of **our code** … B2 would make
> it a property of the **connection**. SPEC §3.1's split is still aspirational and this PR does not
> pretend otherwise.

The refusal is half of it. The other half is that the PR **states what the product does not yet
guarantee** rather than describing the code-level assertion as if it were the database-level one. B2
landed in wave 2 once authorised, and PR #13 shows PostgreSQL doing the refusing in its own words
(`permission denied for table orders`) — including for the store's own connection, which never should
have had `SELECT` on `orders` either.

### 5.2 A feature ledger was built, found forgeable, and deleted

An earlier draft of the harness carried `verification/features.json` — F1–F15 with `steps[]` and a
`passes` boolean — plus a `summary.py` that claimed to enforce its rules. It is gone. Both reasons
are recorded in `VERIFICATION.md` §10:

1. It was a **fourth** copy of the same verification intent (SPEC F1–F15, VERIFICATION, the test
   docstrings, the ledger). **It drifted on its first day** — it named a test file that did not exist.
2. **It did not enforce what it advertised.** Gutting every `steps` entry, rewriting every
   `description` and flipping all fifteen features to `passes: true, verified_by: "vibes"` **exited 0
   and printed `15/15`**.

> A gate's own honesty mechanism that can be made to lie is worse than not having one.

This one is uncomfortable to include because the ledger was copied, in good faith, from the pattern
in Anthropic's own long-running-agent article (`UX_HARNESS_FINDINGS.md` §1). It works there because a
human never reads it as evidence. Here it was going to be read as evidence, which is exactly the
condition under which a forgeable artefact is worse than none. What replaced it costs nothing and
cannot drift, because both are generated by the checks: **`pytest -ra` is the ledger** (every stub
prints what it is waiting on, on every run), and **`bd list` is the per-feature roll-up**.

### 5.3 A stale export contradicted the live tracker, and was believed

`.beads/issues.jsonl` is a passive export of the Dolt-backed tracker, stale the moment the database
moves. It was untracked, un-ignored, and being read. PR #10:

> It was already contradicting the tracker (listing `dq-e1d` as `in_progress` and `dq-j15` as `open`,
> both closed in the live DB).

It is still there and still wrong — it lists **9 issues** where the live tracker holds **46**, with
those same two statuses stale. It is now gitignored, and `AGENTS.md` carries the line
*"`.beads/issues.jsonl` is a passive export, not the wire protocol."* The general lesson is
uncomfortable and worth writing down: **an agent reading a file that looks authoritative will not ask
whether it is current.** The fix is not diligence, it is removing the file from the places an agent
looks.

PR #10 was in fact three fixes with one cause — *"the files a fresh agent reads first were lying
about this project."* The other two: `CLAUDE.md` still carried the `_Add your ..._` placeholders from
`bd init`, and `AGENTS.md` had a 91-line auto-injected block instructing agents to use a tool (`br`)
that **is not installed on this machine** and that contradicts `CLAUDE.md`'s mandate to use `bd`.

### 5.4 Two ways the gate went red with nothing broken

Both found at close-out on 2026-08-17, both recorded in `VERIFICATION.md` §4.7, because *"a gate that
is green two runs in three is not green."*

**A read that raced a write (bead `dq-cyi.3`).** `make check-ui` went red on **about one run in
three** — the bead is titled for exactly that, and the `bd` memory says *"made `make check-ui` red
about one run in three"* — on SPEC §7 step 4. The instance with the numbers is **1 failed, 51
passed, 9 skipped in 279.29 s**. Nothing in `app/` or `web/` was wrong. Judging a
rule is a Next **server action that redirects**, so `networkidle` can be true *again* between the
click and the request leaving; a read taken straight after arrives before the write. This repository
had **already learned that twice** (`scenario_steps._settle` polls the store; `conftest.choose_role`
waits for `aria-pressed`) and step 4 was the one place left with the old shape. The fix is a bounded
poll **on the thing being asserted, with the assertion byte-identical** — and that distinction was
*proven*, not asserted, by break #7 in §4.2.

**Two layers writing into one scratch schema (bead `dq-cyi.4`).** Running `make check-ge` and
`make check-ui` at the same time took **both** red, with nothing wrong with either:

```
make check-ge   1 failed, 32 passed, 251 deselected, 112.55 s
make check-ui   1 failed, 51 passed, 9 skipped, 367.69 s
                AssertionError: the store went from 89 rules to 91 on a refusal.
```

Both pin `DQ_SCHEMA=dq_check`, both write, and the rule store is append-only. The tempting fix — make
the count tolerant — was refused explicitly:

> that assertion is precisely the one that catches a stored non-rule, and loosening it deletes the
> check while leaving it green.

So the constraint was documented and the bead owned the real fix — **which then shipped, without
touching either assertion**: one scratch schema per layer, `dq_check_ge` and `dq_check`, derived from
the markers pytest selected rather than exported by a target, so the isolation is structural instead
of a convention someone remembers. A process that collects both layers is refused before it writes a
row, and the browser layer asks its API process for a record it just wrote rather than trusting that
the two share a schema. Run together on one machine, both are green (VERIFICATION §4.7.2).

### 5.5 An outage killed a run mid-flight, and the workaround was not allowed to become the fix

During wave-2 close-out, `make check-ge` failed **24 of 33** checks with
`could not translate host name "db.<ref>.supabase.co" to address`. It was neither a code regression
nor a credential problem: Supabase's direct host publishes **AAAA records only**, and IPv6 egress had
disappeared (a VPN had taken the default IPv6 route). The tell is that `/usr/bin/host` resolved the
name happily while Python's `getaddrinfo` raised.

The work resumed by exporting the **session** pooler DSNs (IPv4, port 5432) for one run: **24 failed
/ 9 passed became 33 passed**. And then the memory recorded, in capitals:

> **DO NOT 'FIX' THIS IN `.env` OR IN THE CODE.** SPEC and LT-1b chose the direct connection
> deliberately — the *transaction* pooler is 21% slower on this workload … The session pooler is a
> diagnostic fallback for a machine with no IPv6, not the shipping connection.

That restraint is the point. The cheapest resolution — edit `.env`, go green, move on — would have
silently overturned a decision made on measurement, on the strength of one machine's networking. The
same trap later cost the first `docker compose up` its boot, and it is now `README.md`'s "The IPv6
trap" with the detection commands and the fix.

### 5.6 Two screenshots turned out to be the same photograph — and then two more did

The visual layer was **eight** states until the craft pass. `tables-bucket-two-errored` and
`tables-three-buckets` both mapped to `/tables`, and the helper only navigates — so the two states
were the same full-page photograph by construction, and the two written PNGs were **byte-identical**
(md5 `251d2012bccdbdc52ebb0341b5fbbd54`, on two independent runs). The eighth state was **deleted
rather than approved**. A baseline that cannot fail independently of its neighbour is a maintenance
cost with no signal.

**Then it happened again, which is the more interesting half.** `rules-facing-panes` and
`rules-proposal-needs-review-held` both mapped to `/tables/orders/rules`, and came out
byte-identical too — md5 `ed9a0d4cef028e8996b5aedf8cc9ffcf`, on three independent runs. The same
defect, recurring in the same file after being fixed once, because the fix had been *this instance*
rather than *this shape*. The second one was worse: it could not render what it was named for at
all. A proposal is a model call (SPEC F3) and is unsaved by definition (F4), so the demo fixture
cannot mint one — the pane in its shipped PNG read *"Accept 0 — I vouch for each of these · 0 / 8"*
over an empty list. It is now deleted too, and the argument is written into the code beside `STATES`
so a third occurrence has something to hit. Giving it a step that produced a real proposal was the
alternative and was refused: a billed, non-deterministic call is the one thing a photograph may not
depend on. One related item is still open and named rather than fixed: `run-record-in-flight` now
photographs a *settled* record, because a fixed record is by definition one that finished — the name
outlived what it names, and renaming a baseline is a human's call (VERIFICATION §4.3).

**A related discovery, from `HANDOFF.md` §6: a screenshot of a screen this layer writes to is a
photograph of a database.** The review-queue baseline came out 1280×12430 and 1.3 MB — thirty-eight
cards, most of them the same rule duplicated into an append-only store by earlier runs. The fix was
not a tolerance, a mask or a crop — it was **a different database** (bead `dq-vix`, shipped):
`seed/seed_demo_rules.py` seeds a fixed demo store in one idempotent command, `make demo-fixture`,
and `tests/fixtures_demo.py` boots the product on it on its own ports. Two things about it answer
the question a grader of an AI-built system should be asking, *how do you know the agent-written
fixture is not cheating*:

- **The fixture goes through the same validator the product does.** Every rule in it walks
  `store.propose()` and therefore INV-2 — *"a fixture that INSERTed would be the one back door the
  keystone invariant exists to close"* (VERIFICATION §4.3).
- **The photograph layer was measured not to write to the store it photographs.** Across three runs
  of the browser layer, the scratch schema `dq_check` went from 261 rules / 253 records to 267 / 261
  while the demo schema `dq` **stayed at 16 rows and 2 records with its last write still the
  seeder's**, and every baseline came out byte-identical on all three.

Zero states pend for data dependence now. What all six pend for is the one thing no machine can
supply — and §6.2 is the hour in which the mechanism guarding *that* turned out to have a hole.

### 5.7 The visual diff was written, proven, deleted, and rebuilt

The first Pillow implementation was exercised end to end on 2026-08-16 and then removed, on two
grounds recorded in `VERIFICATION.md` §4.3. With every state pending, every line of it sat after a
`pending()` that always fires — **code `make check-ui` could not reach**, so the gate could not keep
it honest. And its `from PIL import …` was a module-level import in a file pytest collects during
`make check` (deselection happens after collection), which made Pillow **an undeclared fifth
dependency of the default gate** — proven rather than argued, by shadowing `PIL` on `PYTHONPATH`:
collection error, zero tests run. Both were addressed rather than forgotten when it came back: the
import is inside the function, with a `ponytail:` comment naming why.

### 5.8 The shipped system contradicts a clause of its own frozen spec, and the number is recorded

The only item in this repository where the built product fails the wording of `SPEC.md` rather than
the other way round. From the `bd` memory `f8-progressive-streaming-has-a-measured-total-cost`
(bead `dq-klv.2`):

> F8 progressive streaming has a measured TOTAL cost, and SPEC's *"at no cost in total time"* is not
> literally true. … ONE validate of all three = **7.94 s** with nothing visible until 7.94 s; THREE
> validates of one rule each = **12.64 s** total with the first verdict at **2.98 s**. So progressive
> costs ~1.6x the total and buys the first verdict ~2.7x sooner. The trade is taken because the total
> was already past the 10 s bar … B24 may want SPEC F8 to say *"the wait"* rather than *"the total"*.

Measured on the live 500,000-row table at the time, with the amendment it implies named in the same
memory. The clause has not been amended — which is the honest state to report, not a defect to hide:
`SPEC.md` was frozen, an amendment costs a revision (§6.1 is what one looks like), and nobody has
spent it.

### 5.9 A Definition of Done that could not be satisfied in its own bead's order

B4 (`dq-5pb.4`) named seven checks; five were green, and the two that were not were INV-5's
*transport* layer, which waits on `app/dq/normalise.py` — a module owned by two beads **downstream**
of B4. The agent did not resolve it:

> DECISION: left open, discrepancy recorded, not resolved by me. Two exits, and the author picks: (a)
> leave B4 open and close it as the last act of B14a; (b) rescope B4 to INV-5's ORIGIN and SURFACE
> layers only … **(b) reads cleaner but it is an edit to a Definition of Done.**

The same shape appeared at B8, where the INV-2 probe table shipped at **14** cases rather than the
**25** its DoD named — the 10 nonsense rules GE actually accepts, plus one representative of each of
the four classes GE does catch. Also not waved through:

> WHY it was not just waved through: it narrows a written Definition of Done, and **a DoD edited by
> whoever is closing the bead is not a DoD.**

---

## 6. Where the human stayed in the loop, and where it mattered

Three places. In each, the mechanism matters more than the decision.

### 6.1 The UI direction — a three-judge panel was overruled, and the frozen spec was amended rather than bent

Four UX variants were generated independently and scored by a three-judge panel across three lenses
(PR #6, `design/README.md`):

| Variant | Compliance | Expert usability | Product/buildability | **Total /30** |
|---|---|---|---|---|
| Run Ledger | 9.0 | 8.0 | 8.4 | **25.4** ← judges' recommendation |
| Vouch Reviewer | 8.2 | 9.0 | 7.7 | 24.9 |
| **Diglot Workbench** | 8.5 | **6.5** | 8.0 | **23.0** ← author's choice |
| Vouch Console | 9.5 | 5.0 | 6.8 | 21.3 |

The author took the 23.0. The reasoning is on the record (2026-08-16, `design/README.md` and a `bd`
memory): Workbench's central idea — the same rule as plain English and as compiled Great Expectations
side by side — *is* the product's thesis, and it is the only variant whose **layout** makes INV-2 and
INV-3 visible rather than asserting them in copy. The judges independently wanted that same idea
grafted onto F12 while recommending Ledger, which is corroboration rather than contradiction.

**And the price was paid explicitly, not absorbed.** Workbench's 6.5 on expert usability lands
directly on INV-1 (a domain expert acts in ≤ 5 minutes), so the mitigation the judges themselves
prescribed was built: the Reviewer variant's queue **time-budget indicator** (which puts the
five-minute promise on screen) and its **"Accept — I vouch for this"** copy, which names what
accepting actually is — staking judgment, not approving a config.

**Then the spec moved.** Workbench's facing panes are incompatible with F12's original *"collapsed by
default"*, and `SPEC.md` was **FROZEN**. It took a revision:

> **Changed in 0.4 (2026-08-17, author's decision):** one acceptance clause, F12's … Recorded rather
> than absorbed silently, because F12 was frozen. No other feature, invariant or non-goal changed.

And PR #14: *"A freeze that silently swallows acceptance edits is worth less than no freeze."* The
built version is stronger than the mockup it came from — for the domain expert the GE configuration
is not `display: none` and not a disclosure control; **the payload is never asked for**, so
view-source, a screen reader and a text browser all agree.

### 6.2 Visual baselines — approval is a mechanism, and the mechanism had a hole

A screenshot is the one artefact in this harness that the run produces itself, so it is the one place
where a machine could certify its own work. The check
(`tests/e2e/test_ui_hygiene.py::test_visual_regression_against_committed_baseline`) writes the PNG
automatically, then pends until a person stages it, because staging a file is the only available
machine-readable signal that a person looked at it. The docstring:

> **A BASELINE IS NEVER SELF-APPROVED, AND THAT IS A MECHANISM.** … Writing is automatic; approving
> is not. Without that gate the run would photograph whatever it rendered and pass against its own
> photograph from the next run on.

**An earlier draft of this section said "no agent has ever approved a screenshot on this project, and
no agent *can*." That was false when it was written, and the repository's own open bug says so.**
Bead `dq-zyt`, filed 2026-08-17 while re-shooting `role-door.png` for the door polish (`dq-dkq`):

> `_approved()` runs `git ls-files --error-unmatch <baseline>` and returns true when the PATH is
> tracked. … overwriting an already-tracked baseline leaves the path tracked, so the very next run
> compares the new shot against itself and goes GREEN over a picture nobody has looked at. That is
> the habit the check's own docstring says it exists to prevent, arriving through the second door.
> **It is not hypothetical: it happened in this bead.** The old baseline failed at 31.36% moved …,
> the new shot replaced it, and the re-run passed with no human in the loop.

So the mechanism holds for a state's **first** baseline and had a second door for every one after it.
Three things about that are worth more than the absolute claim was:

1. **The one-line fix is the same tool.** `_approved()` now asks `git diff --quiet -- <baseline>` as
   well as `git ls-files`, i.e. *is the CONTENT the staged content* and not merely *is the path
   tracked*. A re-shot baseline pends with the same sentence the untracked case gets, and a
   re-approval costs a person the same look the first approval did.
2. **The 31.36% is the best evidence in this document that the visual layer works.** A real layout
   change moved a third of the screen against a 0.20% budget and the diff reported it exactly (§4.2,
   row 13). What failed was the gate around the diff, not the diff.
3. **Finding the hole in your own approval mechanism and filing it beats claiming there is no hole.**

**Current state, checkable rather than inferred.** `tests/e2e/__baselines__/role-door.png` is tracked
— added in `23ee9e1`, which is the wave-3 commit whose own message declares *"One baseline image is
written and deliberately untracked: tests/e2e/__baselines__/role-door.png"*. The file was therefore
staged inside the very commit that says it was not, which reads more like `git add -A` than a
decision. It is also **modified** in the working tree, which under the fixed check means it pends.
`VERIFICATION.md` §4.3 records the one comparison that did run, and records that it should not have
counted. **The score today: six baselines written, zero approved.**

### 6.3 Beads were left open rather than forced closed

At the wave-1/wave-2 close-out, **six beads had every DoD criterion met and green** and `bd` refused
to close all six, because they depend on `dq-5pb.1`, which was open on a question only a human could
answer — whether deferring the visual baselines to the first real-screen bead was accepted. `--force`
was available. From PR #12 and the memory:

> ALTERNATIVE REJECTED: forcing past the dependency guard, on the argument that the guard is tracker
> ordering rather than a DoD criterion. Rejected because **the guard exists precisely because a human
> has not answered yet, and routing around it is self-approval wearing a different hat.**
>
> CONSEQUENCE, stated so it is not a surprise: `bd ready` and `bd list` currently understate real
> progress by six delivered beads.

That is the general principle this project used for every human-in-the-loop question: **a guard
standing on an unanswered human question may not be routed around, and the cost of leaving it
standing is stated rather than hidden.** The same principle produced §5.9's two unresolved DoDs and
§5.1's refused privilege grant.

---

## 7. What the harness still misses

`VERIFICATION.md` §8 is a table of things deliberately not verified, each with the **trigger** that
would add it. It was re-read row by row at close-out rather than left to inherit an argument it had
outlived. Today:

- **Duplication and unused-export detection: the trigger has fired twice and this is not done.**
  Recorded as an open gap rather than deferred a third time, because *"re-setting a trigger twice is
  how a deliberate omission becomes an undiscovered one."* Neither `knip` nor `jscpd` has ever run on
  this repository.
- **No deployed URL** (bead `dq-cyi.1`). The docker half is proven with numbers; SPEC §3's promise is
  half kept, and `README.md` was **corrected** in wave 3 because it had claimed otherwise. The check
  exists, pends by name, and *fails rather than skips* the moment `DEPLOYED_APP_URL` points at
  something silent.
- **No latency budget in the gate — chosen, not deferred.** LT-1b owns real numbers now, and the
  answer is still no: the free tier moved 8.3% inside a single run, so a threshold above the noise
  passes for a product nobody would wait for and one at the median teaches everyone that red means
  *re-run*. What ships instead is a **shape** assertion that cannot flake.
- **All six visual states assert nothing yet.** They are photographs of a fixed store now, so the
  only thing between them and asserting is a person opening each PNG and staging it.
- **`dq-zyt` is open** (§6.2). The check is fixed; what is not done is the human's eye on the
  re-shot `role-door` baseline, which is the bead's last criterion and the one a machine may not
  satisfy.

The `PENDING —` lines say all of this out loud on every single run. That is the point of them.

---

## 8. What I would do differently

Five things, all of them traceable to something above.

1. **A fifth learning test, on the front-end write barrier.** The `networkidle`-is-not-a-write-barrier
   lesson was learned **three times** — twice absorbed quietly into helpers, once as a red gate a
   third of runs (§5.4). Four learning tests were run against the *back-end* dependencies (GE, the
   SDK, PostgreSQL latency) and none against Next server actions, which turned out to have exactly
   the same character: a documented behaviour that does not mean what a reasonable person assumes.
   The pattern generalises — **run a learning test against every dependency whose failure would be
   silent, not just the ones that look risky.**
2. **One writer per schema from the first check that writes.** `dq-cyi.4` is a design defect that
   cost two red runs and an entry in the README, and it was avoidable at zero cost on the day the
   second writing layer was created.
3. **Deploy on day one, not at the end.** `dq-cyi.1` is the one open criterion that needs a human
   with an account and cannot be delegated at all — so it was the worst possible thing to leave last.
   Everything else in SPEC §3's promise is proven; the half that is missing is the half a reviewer
   meets first.
4. **Write the Definitions of Done after the dependency graph, not before it.** B4 and B8 (§5.9) both
   named criteria that could not be satisfied in their own bead's position in the order. Both were
   correctly escalated instead of quietly edited, but the escalation cost a human decision that
   better sequencing would have made unnecessary.
5. **Write this document incrementally.** It was the top of `HANDOFF.md`'s "most likely to be
   forgotten" list from the first session to the last, and every session correctly deprioritised it
   in favour of shipping. It survived only because the PR bodies, bead close reasons and `bd`
   memories were written *at the time*, with numbers in them. **The discipline that saved it was not
   documentation discipline — it was the rule that every finding goes in the PR body, not just in the
   bead notes.** Had that rule not existed, this file would have been reconstruction, and it would
   have shown.

---

## Appendix · verify any of this yourself

Everything above is checkable. The commands:

| Claim | Command |
|---|---|
| The gate is green, offline, and fast | `make check` |
| Every finding in §3 and §5 | `gh pr list --state all` then `gh pr view <n>` — the bodies are the evidence |
| The learning tests, with raw numbers | `learning-tests/FINDINGS.md`, `learning-tests/lt1b_results.json`; re-run each script with the command in its PR |
| Beads, with per-criterion close reasons | `bd list --status closed`, `bd show <id>` |
| The durable "why" behind the decisions | `bd memories`, `bd recall <key>` |
| The anti-cheat that makes green mean something | `tests/test_code_quality_thresholds.py`, `tests/conftest.py::pending` |
| Every occasion the gate was shown to block | `VERIFICATION.md` §4.1, §4.2, §4.3, §4.6, §4.7, §8.1; PRs #9, #11, #14 |
| Baseline approval is a mechanism | `tests/e2e/test_ui_hygiene.py::_approved` — and `git ls-files tests/e2e/__baselines__/` then `git status tests/e2e/__baselines__/` |
| The hole in that mechanism, and its fix | `bd show dq-zyt`; `VERIFICATION.md` §4.3 |
| The stale export, still stale | `wc -l .beads/issues.jsonl` → **9**, against a live tracker holding **46** (`bd list --status closed` → 41, `bd list` → 5 open) |
| The spec amendment | `SPEC.md` header, *Changed in 0.4* |
| The workflow this followed | `software_development_workflow.md` §5 (the loop precondition), §6.5 (the rig that was not built) |

---

*Companion documents: [`SPEC.md`](./SPEC.md) · [`VERIFICATION.md`](./VERIFICATION.md) ·
[`learning-tests/FINDINGS.md`](./learning-tests/FINDINGS.md) · [`HANDOFF.md`](./HANDOFF.md) ·
[`HOW_I_BUILD.md`](./HOW_I_BUILD.md) (the author's general workflow, of which this project is one
application).*
