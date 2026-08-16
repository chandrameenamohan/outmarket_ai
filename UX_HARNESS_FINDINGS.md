# UX findings from the long-running-agent harness approach

**Source:** [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — Anthropic Engineering, 26 Nov 2025.
Read 2026-08-16 via a read-only subagent, three fetch passes, two independent extractions in agreement. No truncation.

**Read this caveat first.** The article contains **no UI content and no discussion of human review or intervention**. It is an agent-engineering piece. Nothing below is UX guidance the article gives; everything is a *structural* claim from the article plus our inference about what it implies for our screens. The two are kept separate throughout, because we are making design decisions from this.

---

## 1. What the approach actually is

The article's framing is a handoff problem:

> *"Imagine a software project staffed by engineers working in shifts, where each new engineer arrives with no memory of what happened on the previous shift."*

The harness exists so a fresh agent with zero memory can reconstruct state and continue. Its mechanism is a set of **durable artifacts**, not a running process:

| Artifact | Role |
|---|---|
| `init.sh` | boots the environment |
| `claude-progress.txt` | narrative log of what happened |
| initial git commit | known-good base |
| **feature-list JSON** (~200 entries: `category`, `description`, `steps[]`, `passes`) | the scope and status of the whole job |

Every feature starts `passes: false`, deliberately, *"to outline the full functionality scope."* Agents *"edit this file only by changing the status of a `passes` field."* JSON was chosen over Markdown **because the model is less likely to modify JSON inappropriately**.

Each session re-orients before doing new work: `pwd`, read git log and progress file, pick the highest-priority incomplete feature, run `init.sh`, run a basic end-to-end test.

### The two named failure modes

1. **One-shotting.** *"the agent tended to try to do too much at once—essentially to attempt to one-shot the app"*, leaving *"the next session to start with a feature half-implemented and undocumented."*
2. **Declaring done from surface evidence.** *"a later agent instance would look around, see that progress had been made, and declare the job done."*

### The cheap check that lied

> *"Claude tended to make code changes, and even do testing with unit tests or `curl` commands against a development server, but would fail recognize that the feature didn't work end-to-end."*

The fix was end-to-end verification driven *as a human user would* (browser automation, screenshots). And marking done was gated on it: *"Self-verify all features. Only mark features as 'passing' after careful testing."*

Notably, the article **names its own residual blindness** rather than implying full coverage — vision limits, and browser-native alert modals it simply cannot see.

---

## 2. Why this rhymes with what our learning tests already measured

The article's failure modes are not new to us. We hit the same shapes empirically, in a different domain:

| Article | Our learning test |
|---|---|
| *"see that progress had been made, and declare the job done"* — surface state read as completion | **LT-2b**: the model proposed `order_total BETWEEN 0 AND 89,400` (overfit to the observed max) and never `order_total >= 0`. The sample looked complete. **Meaning is not in the sample.** |
| Unit tests and `curl` passed while the feature was broken | **LT-2a**: GE validates shape, never sense — of 25 invalid-rule probes it silently accepted 10 (min>max, unclosed regex, empty value set). **Construction succeeding is not the rule being right.** |
| Residual blindness stated explicitly | **LT-1a**: GE does not record that a run was row-capped. A sampled run is byte-identical to an honest full run — so the disclosure has to come from us. |

The consistent lesson across both bodies of evidence: **a tool confirms well-formedness, never meaning.** That is the thing our domain expert exists to supply, and the reason evidence lines and unsaved-proposal status are load-bearing rather than decorative.

---

## 3. The one conclusion that changes our plan

**Render results from a persisted run record with an explicit status field — never from the request.**

*Article claim it rests on:* the shift-handoff design. State lives in durable artifacts (progress file, git history, feature list) precisely so a reader with no memory of the run can reconstruct it. The record is the source of truth, not the process that produced it.

*What it does for us:* a synchronous run becomes just a record that happened to complete while the user was watching. A background run adds a `running` value and a poll. Nothing else about the screen changes.

**This takes O-3 (synchronous vs background execution) off the critical path for F13's design.** LT-1b's number stops being a screen-shape decision and becomes a latency decision. F13 can be designed now, before that number lands — provided it is built against the record from day one.

---

## 4. Per-screen recommendations

Each is tied to a specific claim in the article.

**F12 · Rule Management — cap bulk-accept and make it a verification act, not a dismissal.**
Require every selected proposal's evidence line to be visible on screen at the moment of the click — a short scannable list, not a collapsed count — and exclude anything in `needs_review` from bulk selection entirely.
*Claim:* one-shotting is the article's first named enemy, and its fix was one feature at a time. Bulk-accept does at scale exactly what failure mode 2 describes: converting "looks fine" into "done".

**F12 · "Compiled OK" must never render as a success state.**
*Claim:* unit tests and `curl` passing on a broken feature. Our equivalent is GE accepting 10 of 25 nonsense rules. A rule that compiles has cleared shape, not sense.

**F13 · Results Dashboard — fold sampling and error state *into* the status token, not beside it.**
Render one atom of the form `FAILED · sampled <scanned> / <total>`, `ERRORED · rule could not run`
(the `500K / 2.4M` shape in the mockup is illustrative — LT-1b later settled that no row cap ships
at the demo set's 500,000 rows, so the marker's real value there is `not sampled`).
*Claim:* `passes` works because it is one narrow, single-writer field that is hard to write casually. INV-5 fails the moment sampling is a separate adjacent element, because any layout change can separate it. "Inside" survives what "adjacent" does not.

**F13 · Render from the run record.** See §3.

**F10 · Table Explorer — sort by *unverified*, not by *uncovered*.**
Three buckets, in order: never run · ran but unverifiable (errored or sampled) · verified.
*Claim:* everything in the feature list starts `passes: false` so the full scope of unfinished work is visible from session one. A table whose last run errored or was row-capped is also not yet vouched for, and belongs above the fold alongside zero-coverage tables — not filed under "has coverage".

**F11 · Review queue — state what the evidence cannot tell you, in one static header line.**
e.g. *"Evidence is drawn from a sample of this table. A rule can be true of every row here and still be wrong."*
*Claim:* the article names its own residual blindness explicitly rather than implying full coverage. This is the UI expression of the LT-2b finding, and it costs the ≤5-minute budget (INV-1) exactly one sentence.

---

## 5. What the article argues against

Design instincts we are likely to have, that this evidence contradicts:

- **Don't let one action complete many things.** One-shotting is failure mode 1.
- **Don't trust the cheap check.** It passed while the thing was broken.
- **Don't make the machine-authored record freely editable.** JSON was chosen over Markdown for write-resistance. Our analogue: the stored rule and its run record should not be casually mutable from the UI.

## 6. Where the article gave us nothing

Stated plainly so no one mines it twice: it has **no** guidance on progress display, latency thresholds, confidence representation, three-state modelling, or human checkpoints. Our product makes the opposite bet to the article on that last one — it solves "nobody is watching" by having the agent self-verify, whereas our entire design rests on a human judging whether a rule *means* the right thing.
