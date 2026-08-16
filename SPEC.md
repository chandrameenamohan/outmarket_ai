# SPEC — AI-Powered Data Quality Assistant

**Status:** Draft, pre-implementation · Rev 0.1
**Companion:** [Architecture design document](https://claude.ai/code/artifact/97a3df0c-7ae3-4e8a-94fe-6e23e8b6f0f9) — problem framing, designs not chosen, risk register
**Blocked on:** Learning tests LT-1 and LT-2 (§8) before this spec is frozen

---

## 1. Product overview

> **A domain expert states an expectation in plain English; the system turns it into a Great Expectations check it has already proven will run, executes it against live data, and reports failures in the same language the expectation was written in.**

Data quality rules encode business knowledge, but expressing them requires engineering skill — and those two things live in different people. The result is that the most valuable rules never get written, and data stays silently wrong. This service closes that gap for one PostgreSQL database: it shows where coverage is missing, proposes rules with the evidence behind them, accepts rules stated in English, and runs them on demand.

### 1.1 Users

Two users, both first-class, entering at different points.

| | Data engineer | Domain expert |
|---|---|---|
| **Owns** | Coverage and execution | Whether a rule *means* the right thing |
| **Enters at** | Table Explorer — where is coverage missing | Review queue — what needs my judgment |
| **Time budget** | Ongoing | ≤ 5 minutes per table |

Role is a view the user selects, not an account they log into. See F11 and §6.

### 1.2 Invariants

These hold from the first commit and are not traded away for scope. Each maps to a design goal in the architecture document.

| ID | Invariant |
|---|---|
| **INV-1** | A domain expert can act on a table's proposals in ≤ 5 minutes. |
| **INV-2** | An invalid or non-existent expectation can never reach the rule store. |
| **INV-3** | Great Expectations is a runtime, not the domain model. Exactly one module imports it. |
| **INV-4** | Every failure is readable by someone who can judge whether it matters. |
| **INV-5** | Any result derived from a sample says so, adjacent to the pass/fail state. |
| **INV-6** | Start minimal; deepen only where evidence shows weakness. Does not apply to INV-1, INV-2, INV-5. |

---

## 2. Features

Each feature states **observable acceptance** — what a user or caller can see when it works. Grouped in the brief's own order so the mapping stays legible.

### Backend — AI Rule Generator

---

**F1 · Schema discovery**

The system enumerates the tables in the connected database with their columns, types, row counts, and current rule coverage.

*Acceptance:* A caller requests the table list and receives every table in the target schema, each with column names and types, an approximate row count, and a count of accepted rules. A table with no rules reports zero rather than being omitted.

---

**F2 · Table profiling**

For a selected table, the system derives descriptive statistics per column plus a bounded sample of rows.

*Acceptance:* Profiling `orders` returns, for each column: total rows, non-null count, distinct count, min and max where the type is ordered, and the distinct values themselves when cardinality is low. Twenty sample rows accompany the block. The result is cached and a repeat request within the cache window does not re-query the database.

*Note:* Implemented as one parameterised statistics query per table, not a profiling subsystem. Per INV-6, deepen only the specific dimension that proves weak — see the "deliberately not building yet" note in §5.

---

**F3 · Rule suggestion from profile**

The system proposes candidate rules for a table, derived from its profile, each carrying the evidence that justifies it.

*Acceptance:* Requesting suggestions for `orders` returns a set of proposals. Each names a column, states the rule in plain English, cites its supporting evidence (`2,400,000 rows scanned · 0 nulls · min observed 0.00`), and arrives in `proposed` status. No proposal is stored as an active rule and none is executed.

*Constraint:* The generator may only select from the curated catalog (F5). A proposal referencing an expectation type outside the catalog is a defect, not a feature request.

---

**F4 · Natural-language rule authoring**

A user states a rule in English and receives a validated rule, or a clear explanation of why it cannot be expressed.

*Acceptance:*
- *"order total can never be negative"* → a rule on `orders.order_total` with a lower bound of zero, shown for confirmation before saving.
- *"shipped_date must be after order_date"* → rejected with: *"Not supported yet — this rule compares two columns, and the current rule set covers single-column and table-level checks only."* Nothing is stored.
- Ambiguous or unparseable input → an explanation, never a silent failure and never a guess.

---

**F5 · Curated catalog and validation**

Every generated rule is checked against Great Expectations before it is written anywhere.

*Acceptance:* The generator is restricted to a fixed catalog of roughly fifteen expectation types. Each generated rule is instantiated as a real Great Expectations expectation object before persistence; one that fails to construct is rejected at authoring time with the reason surfaced to the author. A hallucinated type or malformed parameter set cannot reach the rule store. *(INV-2)*

*Verification:* A test that feeds a deliberately invalid rule spec through the validator and asserts it is rejected — not that it errors at execution time.

---

**F6 · Rule storage and lifecycle**

Rules persist in the system's own specification format with a status that carries the two-user workflow.

*Acceptance:* A rule occupies exactly one of four states — `proposed`, `needs_review`, `accepted`, `rejected`. Only `accepted` rules execute and only `accepted` rules count toward coverage. A rejection stores the reason alongside it. The stored representation is the system's own; the Great Expectations configuration shown in the UI is produced on demand by compiling it. *(INV-3)*

---

### Backend — Data Quality Engine

---

**F7 · Great Expectations compilation**

Stored rule specs compile into an executable Great Expectations suite at run time.

*Acceptance:* Given a table's accepted rules, the compiler produces a suite that Great Expectations executes without further transformation. This module is the only one in the codebase that imports Great Expectations — enforced by a check in the gate, not by convention. *(INV-3)*

---

**F8 · Rule execution**

Accepted rules run against live data on explicit user action.

*Acceptance:* Triggering a run for `orders` executes every accepted rule against the live table and returns per-rule pass/fail, the count of violating rows, and a sample of the offending values. If a row cap engages, the run is marked as sampled and every result derived from it carries that marker through to the UI. *(INV-5)*

*Contingency:* The synchronous model depends on the LT-1 measurement (§8). If interactive execution proves infeasible, this feature changes shape and the spec is revised before implementation, not during.

---

**F9 · Result normalisation and caching**

Great Expectations output is translated into the system's own result format and cached.

*Acceptance:* A result carries the rule's plain-English statement, pass/fail, violating count, sample violations, the sampling marker, and the raw framework output retained separately. The most recent result per table is cached and rendered on load without re-execution; re-running is an explicit action.

---

### Frontend

---

**F10 · Table Explorer**

The engineer's entry point: a coverage dashboard, not a database browser.

*Acceptance:* The screen lists tables with row count, rule count, and last-run summary. Default sort places zero-coverage tables first. Selecting a table opens its rules.

---

**F11 · Review queue**

The domain expert's entry point: everything awaiting their judgment, with no schema knowledge required.

*Acceptance:* The screen shows rules in `needs_review` and currently failing rules, each stated in business language. Table names appear as context, never as navigation. A user reaching this screen never encounters a table list. Selecting the role is a one-click choice on entry and is remembered.

---

**F12 · Rule Management interface**

Where rules are reviewed, authored, inspected, and edited — used by both users.

*Acceptance:*
- Proposals render with their English statement, evidence line, and Accept / Reject / Ask business actions. Unambiguous proposals can be accepted in bulk.
- A single text field accepts a natural-language rule (F4).
- The generated Great Expectations configuration is present and editable, **collapsed by default**.
- The engineer edits the configuration; the domain expert edits the English statement and the system recompiles.
- Rejecting captures a reason.

---

**F13 · Results Dashboard**

Execution results, rendered for someone deciding whether a failure matters.

*Acceptance:* A failure displays as the rule's English statement, the count and proportion of violating rows, and real offending values — for example, *"150 orders have a negative total · of 2,400,000 rows scanned · 0.006% · #88231 −450.00 …"*. Raw framework output is available in a collapsed panel. Sampling disclosure renders adjacent to the pass/fail state, not in a footnote. A re-run control is present. *(INV-4, INV-5)*

---

**F14 · Stable URLs**

Every rule and every failure is addressable and renders standalone.

*Acceptance:* Opening a rule's URL directly shows that rule, its evidence, and its actions, with no prior navigation and no login. Pasting the URL into a chat client and following it lands on the item in question.

---

### Supporting

---

**F15 · Demo dataset**

A seeded database with deliberate, discoverable defects.

*Acceptance:* A single command creates `orders`, `customers`, and `payments` in a fresh database and populates them with realistic data containing known quality problems — negative order totals, shipped dates preceding order dates, status values absent from a small sample, and missing customer emails. The seed script documents which defects it plants, so the demo's outcome is verifiable rather than anecdotal.

*Reasoning:* A clean database makes a working product look broken. The defects are part of the deliverable.

---

## 3. Technical constraints

| Layer | Decision |
|---|---|
| Backend | Python |
| Frontend | React / Next.js |
| Database | PostgreSQL on Supabase — both the analysis target and the system's own store, in separate schemas |
| DQ engine | Great Expectations (version confirmed by LT-2) |
| Model access | Claude Agent SDK on a subscription token, `claude-opus-5`, **all built-in tools disabled**, single structured call, no agent loop |
| Delivery | Deployed URL *and* `docker-compose` |

### 3.1 Security

- Read-only database role against the tables under analysis; a separate write-capable role scoped to the system schema.
- The model receives aggregate statistics and a bounded sample — never full table contents.
- Credentials from environment configuration only; never entered through the UI, never stored in application tables.
- Identifiers derived from model output are validated against the live schema before interpolation. Generated SQL is parameterised.
- Every Agent SDK built-in tool is off: no shell, no filesystem, no network from the model's side.

---

## 4. Non-goals

Explicitly out of scope for this revision.

| Excluded | Reasoning |
|---|---|
| Scheduling / recurring runs | Requires a scheduler and changes the deployment story |
| Run history and trends | High long-run value; not required for the core path |
| Authentication and accounts | Role is a selected view; one env-configured connection means auth adds realism, not capability |
| Alerting | Belongs with scheduling; meaningless while runs are manual |
| Severity, muting, staleness detection | The alert-fatigue countermeasures — see §5 |
| Multi-column rules | The most common rejection under F4; the first capability to add next |
| Arbitrary database connection UI | One connection from environment configuration |
| GE Data Docs | Would expose the exact abstraction the product exists to hide |
| Conversational rule authoring | Authoring a rule is filling a field, not holding a conversation |
| Non-GE execution fallback | The first step toward reimplementing Great Expectations |

---

## 5. Deliberately not building yet

Everything above is a scope decision. This section is the one that is a *judgment* — the thing we can see coming and are choosing not to solve.

**The alert-fatigue problem is real, and this revision does not address it.**

Making rule authoring cheap solves day one. Day thirty looks different: forty rules run, twelve report failures, the team stops looking because red has become the normal state, and a genuine defect fires correctly into a pile nobody reads. The cause is that three distinct situations render identically — a wrong rule, a correct rule whose violation doesn't matter, and a correct rule whose violation matters a great deal. The middle category is the most common and cannot be removed by fixing the rule.

The countermeasures are known: severity, muting with a reason, and trend over time. **Building them now would be over-engineering**, because none of them can be designed well before there is a running system producing real failures to triage. Severity levels chosen in advance encode a guess about which rules matter; muting built before anyone has wanted to mute something is a feature with no user. These are second-version features precisely because the first version generates the evidence needed to design them.

What this revision owes the problem is honesty about it, not a partial implementation of it.

Two smaller items in the same category:

- **A deeper profiler.** Pattern detection and distribution analysis would likely produce better suggestions. Building it before observing which suggestions are weak means building for an imagined deficiency. Trigger: suggestion quality proving weak on a specific dimension — then deepen that dimension only. *(INV-6)*
- **Organisation-level credentials.** Subscription authentication is correct for this deliverable and wrong for a product. Since exactly one module constructs the client, this is a contained change when it is actually needed.

---

## 6. Assumptions

1. This is an evaluated case study; the deliverable is proof of judgment as much as working code.
2. One target database, configured from the environment.
3. Execution is synchronous — pending LT-1.
4. Great Expectations 1.x — pending LT-2.
5. A Claude subscription token authenticates the Agent SDK in a server process — pending LT-2.

---

## 7. End-to-end verification scenario

**One scenario that proves the whole system works.** If this passes, the product does what it claims.

> **Setup.** A fresh Supabase database seeded by F15. The `orders` table contains 2.4M rows, among them a known set with negative `order_total`. No rules exist.
>
> **1 — Coverage is visible.** The engineer opens the Table Explorer. `orders` appears at the top of the list with a rule count of zero.
>
> **2 — Proposals arrive with evidence.** They select `orders` and request suggestions. Within the interactive latency budget, proposals appear. Each states a rule in English and shows the evidence behind it. Among them is a proposal that `order_total` is never negative. Every proposal is in `proposed` status; none is active.
>
> **3 — Review splits by confidence.** The engineer bulk-accepts the unambiguous proposals. They mark the proposal constraining `status` to observed values as `needs_review`, because it encodes a business assumption they cannot verify, and copy its URL.
>
> **4 — The second user acts independently.** The domain expert opens the product, selects their role, and finds the flagged rule waiting in their queue — without seeing a table list. They also open the copied URL directly and land on the same rule. They reject it with the reason *"cancelled orders use a fourth status not in this sample"*. The reason is stored.
>
> **5 — English becomes an executable rule.** The domain expert types *"order total can never be negative"* into the rule field. The system returns a validated rule, shows the Great Expectations configuration it compiles to (collapsed), and saves it on confirmation.
>
> **6 — An impossible rule fails honestly.** They then type *"shipped date must be after order date"*. The system rejects it with an explanation naming the limitation. Nothing is stored, and coverage does not change.
>
> **7 — Execution finds the planted defect.** The engineer runs the suite. Results return with per-rule pass/fail. The `order_total` rule fails, reporting exactly the number of negative-total rows the seed script planted, with real offending order IDs and values shown in business language. If sampling was applied, the result says so beside the state.
>
> **8 — The loop closes.** The result is cached and renders immediately on reload. Re-running produces the same outcome. The Table Explorer now shows `orders` with a non-zero rule count and a failing last run.

**This scenario is the acceptance test for the system as a whole** and is automated as the single end-to-end flow in the verification gate.

---

## 8. Learning tests — required before this spec is frozen

Both are executed against real dependencies, with findings recorded before any implementation depends on them.

**LT-1 · Great Expectations latency on Supabase** — *blocks F8*
Run several expectations against a real multi-million-row table on a real Supabase instance and measure wall-clock time. The entire interaction model assumes results return fast enough to watch. If they do not, the product becomes a background-job system and F8, F9, F13 all change shape. Roughly one hour of work that determines the shape of the user experience.

**LT-2 · Great Expectations API and Claude Agent SDK surface** — *blocks F5, F7, F3*
Confirm the Great Expectations object model against the installed version — most available material describes the pre-1.0 API — and the real expectation-type registry that F5's catalog is drawn from. Separately, confirm that a subscription token authenticates the Agent SDK in a server process and establish how structured output is requested and read back.

---

## 9. Open items

| ID | Item | Resolution path |
|---|---|---|
| **O-1** | Exact composition of the ~15-type catalog | From the confirmed registry (LT-2) plus observed coverage of realistic rules |
| **O-2** | Row cap value for F8 | From the LT-1 measurement |
| **O-3** | Synchronous vs background execution | LT-1 |
