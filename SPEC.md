# SPEC — AI-Powered Data Quality Assistant

**Status:** Rev 0.2 · **FROZEN** 2026-08-16 · pre-implementation
**Companion:** [Architecture design document](https://claude.ai/code/artifact/97a3df0c-7ae3-4e8a-94fe-6e23e8b6f0f9) — problem framing, designs not chosen, risk register
**Frozen on:** All four learning tests (LT-1a, LT-1b, LT-2a, LT-2b) have been executed against real dependencies and recorded in `learning-tests/FINDINGS.md` — see §8. Nothing in this spec is waiting on a measurement. One implementation choice remains open — **O-4**, the transport for progressive results — which changes no acceptance text and is decided when F8 and F13 are built.

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
| **INV-3** | Great Expectations is a runtime, not the domain model. Exactly one module imports it, and that module holds exactly one GE context per process. |
| **INV-4** | Every failure is readable by someone who can judge whether it matters. |
| **INV-5** | Any result derived from a sample says so, **inside** the same text node as the pass/fail state. |
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

*Acceptance:* Requesting suggestions for `orders` returns a set of proposals. Each names a column, states the rule in plain English, cites its supporting evidence (`500,000 rows scanned · 0 nulls · min observed 0.00`), and arrives in `proposed` status. No proposal is stored as an active rule and none is executed.

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

*Constraint — one context per process:* `gx.get_context()` does not merely return a context, it installs it as a process-global project, so a second call silently orphans the first context's datasources and the failure surfaces much later at `validate()` as a `DatasourceError` naming a datasource that is sitting right there in the context object being held (LT-1b). This module therefore creates **exactly one context for the process**, once, and hands it out — never one per request. This is a correctness constraint, not a style note: a request handler that calls `gx.get_context()` breaks every other request in flight and produces an error that points at configuration rather than at concurrency, so it would be debugged in the wrong place. *(INV-3)*

---

**F8 · Rule execution**

Accepted rules run against live data on explicit user action.

*Execution model — decided by LT-1b:* **Synchronous, but progressive.** The request stays synchronous and streams each rule's verdict as it lands. It is not a background job queue: the measured cost is a sequence of independent statements, so a worker would return the same total later with a polling endpoint and a stale-result problem added. Execution uses the **direct** connection, `SUPABASE_DB_URL_DIRECT` (port 5432) — the transaction pooler is 21% slower for this workload, 17.94 s against 14.84 s on identical work. **No row cap ships at this scale** (O-2).

*The ceiling is measured, not hypothetical:* only **3 rules** fit under 10 s at 500,000 rows, and with 10 rules only **100,000 rows** do. Progressive rendering is what makes 14 s honest, not fast — a product that lets rules accumulate crosses the watchable line by design (LT-1b). See §5 for what happens past it.

*Acceptance:* Triggering a run for `orders` executes every accepted rule against the live table and returns per-rule pass/fail, the count of violating rows, and a sample of the offending values. A rule that could not run is reported as **errored**, never as failing — the two are visually identical in Great Expectations' own output (LT-1a) and mean different things.

*Acceptance — progressive results:* Verdicts arrive **one at a time**, each renderable by the caller as it lands, and **no rendering may be a blank spinner for the duration of the run** — the user sees the list filling from the first verdict onward. That is the whole of the acceptance: it is observable at any moment and needs no stopwatch (VERIFICATION §9.1 deliberately ships no latency budget).

*Note — the measured cost, which is context and not a criterion:* against the seeded 500,000-row `orders` table on the direct connection, one rule over the whole table costs 2.28 s and the full fifteen-rule catalog 13.97 s. Averaged over that range the shape is a ~2.3 s floor plus ~0.83 s per rule, **but the average is not an acceptance-grade number** — the real cost is per-rule and lumpy: a single rule measures anywhere from 1.28 s to 6.59 s, and `be_unique` on an unindexed `text` column alone costs 6.59 s. That is why the ten-rule suite F13 actually needs — `unexpected_index_column_names`, for identifier-plus-value display — costs **more** (14.84 s) than the fifteen-rule catalog (13.97 s): fewer rules costing more is not a typo, because the ten-rule suite substitutes two aggregate expectations for the two type expectations, and one dear rule sets the price. Rule count is not what sets the cost, and neither is row count. It also means the first verdict's timing depends on which rule lands first.

*Acceptance — sampling disclosure:* If a row cap engages, the run is marked as sampled and every result derived from it carries that marker through to the UI. Great Expectations does not record that a batch was capped (LT-1a), so the marker is carried by us, from the asset definition into the stored result. The mechanism ships; at this scale the cap itself is switched off. *(INV-5)*

---

**F9 · Result normalisation and caching**

Great Expectations output is translated into the system's own result format and cached.

*Acceptance:* A result carries the rule's plain-English statement, pass/fail, violating count, sample violations, the sampling marker, and the raw framework output retained separately. The most recent result per table is cached and rendered on load without re-execution; re-running is an explicit action.

*Acceptance — cache and progressive runs:* Only a **completed** run enters the cache. A run still streaming verdicts (F8) is never stored as if it were complete, and a reload during a run shows the last completed run rather than a half-filled one. The cached path is what makes a reload instant; an interrupted or abandoned run leaves it untouched.

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

*Acceptance:* A failure displays as the rule's English statement, the count and proportion of violating rows, and real offending values — for example, *"150 orders have a negative total · of 500,000 rows scanned · 0.03% · #88231 −450.00 …"* (0.03% = 150 / 500,000, the D1 defect count in `seed/MANIFEST.md`; `FINDINGS.md` §LT-1a quotes the same illustration as 0.006%, which is a slip in that document). Raw framework output is available in a collapsed panel. Sampling disclosure renders **inside** the pass/fail status token, not beside it and not in a footnote. A re-run control is present. *(INV-4, INV-5)*

*Acceptance — partially-complete runs:* The dashboard renders a run that is still executing (F8). Rules that have not yet returned a verdict are shown as **visibly pending** — present in the list, distinguishable at a glance from a pass, and never rendered as passing by their absence of failures. The screen states how many of how many rules have reported — a count read off the same list, so it can be checked against the DOM at one moment — and each verdict replaces its pending row as it lands. *(Measured, as context rather than as a criterion: 2.28 s for one rule, 13.97 s for the fifteen-rule catalog; individual rules range 1.28–6.59 s, so which rule lands first is what sets when the first row resolves.)*

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
| Database | PostgreSQL 17.6 on Supabase — both the analysis target and the system's own store, in separate schemas. Rule execution connects direct on port 5432, not through the transaction pooler (F8, LT-1b) |
| DQ engine | Great Expectations **1.20.0** — confirmed by LT-2a and exercised end to end by LT-1a / LT-1b |
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

Five smaller items in the same category:

- **What happens past the watchable ceiling.** LT-1b's verdict is not "synchronous works": *a run is watchable while the suite is small, and stops being watchable somewhere between 3 and 8 rules on a table this size.* Only **3 rules** fit under 10 s at 500,000 rows, and with 10 rules only **100,000 rows** do. Progressive rendering (F8, O-3) is what makes fourteen seconds honest, not fast, and a product that lets a domain expert accumulate rules crosses that line **by design, not by accident**. This revision does not build what happens next — partial suites, a run split across requests, or a background worker. Trigger: a table's accepted suite passing roughly eight rules, or a target table an order of magnitude larger than the demo set. Then the number gets re-measured on the machine that will run it, and O-3 is reopened with data rather than reasoned about with these.
- **Making Great Expectations itself faster.** GE's own Python is 21% of wall clock at full size — more than the network. It is metric-graph resolution, not database work, so no SQL tuning reaches it (LT-1b). Trigger: the per-run and per-rule floor, rather than the scan, being what a user complains about. Until then the answer is progressive rendering (F8), which costs nothing and removes the wait the user actually feels.
- **A cheaper row cap.** `add_query_asset` is the only cap GE 1.x offers and it is the wrong mechanism — at full size it is a net loss, and it breaks two catalog types outright (O-2). Whatever replaces it has to be measured the same way before it is trusted. Trigger: a target table an order of magnitude larger than the 500,000-row demo set. INV-5's disclosure mechanism ships now (F8), so switching a cap on later is a value change, not a new feature.
- **A deeper profiler.** Pattern detection and distribution analysis would likely produce better suggestions. Building it before observing which suggestions are weak means building for an imagined deficiency. Trigger: suggestion quality proving weak on a specific dimension — then deepen that dimension only. *(INV-6)*
- **Organisation-level credentials.** Subscription authentication is correct for this deliverable and wrong for a product. Since exactly one module constructs the client, this is a contained change when it is actually needed.

---

## 6. Assumptions

1. This is an evaluated case study; the deliverable is proof of judgment as much as working code.
2. One target database, configured from the environment.
3. Execution is synchronous and progressive — confirmed by LT-1b against the seeded 500,000-row `orders` table on Supabase: 2.28 s for one rule, 13.97 s for the full fifteen-rule catalog, streamed per rule rather than waited on as a block. Averaged over that range the shape is a ~2.3 s floor plus ~0.83 s per additional rule, but the real cost is per-rule and lumpy (1.28–6.59 s for a single rule), which is why the ten-rule shipping suite costs 14.84 s — more than all fifteen.
4. Great Expectations **1.20.0** — confirmed by LT-2a (56 registered types, a pydantic v1 object model, no `DataContext` needed to construct or compile) and executed against PostgreSQL 17.6 by LT-1a and LT-1b on SQLAlchemy 2.0.52, psycopg2-binary and Python 3.12.5.
5. A Claude subscription token authenticates the Agent SDK in a server process — confirmed by LT-2b with `claude-agent-sdk` 0.1.23 and model `claude-opus-5`: `CLAUDE_CODE_OAUTH_TOKEN` works with no API purchase, built-in tools are fully suppressed, `max_turns=1` is enforced, and `setting_sources=[]` keeps the developer's own `CLAUDE.md` out of a server-side call. Measured 6.6 s and $0.041 per call.

---

## 7. End-to-end verification scenario

**One scenario that proves the whole system works.** If this passes, the product does what it claims.

> **Setup.** A fresh Supabase database seeded by F15. The `orders` table contains 500,000 rows, among them a known set with negative `order_total`. No rules exist.
>
> **1 — Coverage is visible.** The engineer opens the Table Explorer. `orders` appears at the top of the list with a rule count of zero.
>
> **2 — Proposals arrive with evidence.** They select `orders` and request suggestions. Proposals appear after a single model call — measured at 6.6 s by LT-2b, inside the ≤ 10 s band that needs visible progress rather than the ≤ 5 s band a bare spinner covers, so the screen shows progress. Each states a rule in English and shows the evidence behind it. Among them is a proposal that `order_total` is never negative. Every proposal is in `proposed` status; none is active.
>
> **3 — Review splits by confidence.** The engineer bulk-accepts the unambiguous proposals. They mark the proposal constraining `status` to observed values as `needs_review`, because it encodes a business assumption they cannot verify, and copy its URL.
>
> **4 — The second user acts independently.** The domain expert opens the product, selects their role, and finds the flagged rule waiting in their queue — without seeing a table list. They also open the copied URL directly and land on the same rule. They reject it with the reason *"cancelled orders use a fourth status not in this sample"*. The reason is stored.
>
> **5 — English becomes an executable rule.** The domain expert types *"order total can never be negative"* into the rule field. The system returns a validated rule, shows the Great Expectations configuration it compiles to (collapsed), and saves it on confirmation.
>
> **6 — An impossible rule fails honestly.** They then type *"shipped date must be after order date"*. The system rejects it with an explanation naming the limitation. Nothing is stored, and coverage does not change.
>
> **7 — Execution finds the planted defect.** The engineer runs the suite. The first verdict appears well before the last and the rest fill in one by one — never a blank spinner — rules not yet reported showing as pending throughout. The `order_total` rule fails, reporting exactly the number of negative-total rows the seed script planted, with real offending order IDs and values shown in business language. If sampling was applied, the result says so **inside** the status token.
>
> **8 — The loop closes.** The result is cached and renders immediately on reload. Re-running produces the same outcome. The Table Explorer now shows `orders` with a non-zero rule count and a failing last run.

**This scenario is the acceptance test for the system as a whole** and is automated as the single end-to-end flow in the verification gate.

---

## 8. Learning tests — EXECUTED

All four ran against real dependencies, and their findings are recorded in `learning-tests/FINDINGS.md` before any implementation depends on them. This section is what unblocks the freeze: nothing here is waiting on a measurement. One implementation choice remains open — **O-4**, the transport for progressive results — which changes no acceptance text and is decided when F8 and F13 are built.

**LT-1 · Great Expectations against real PostgreSQL, and its latency on Supabase** — *fed F8, F9, F13, INV-5* — **EXECUTED**
- **LT-1a** (`FINDINGS.md` § "LT-1a · Great Expectations executes against PostgreSQL") — a suite runs end to end against real PostgreSQL with exact counts, the work is pushed down to the database, offending values come back with row identifiers, and GE returns three different result shapes plus an errored state that is indistinguishable from a failure unless `exception_info` is read. F9's normalisation contract is written down there field by field.
- **LT-1b** (`FINDINGS.md` § "LT-1b · Great Expectations latency on Supabase — direct vs pooled") — over the seeded 500,000-row table on the direct connection, one rule costs 2.28 s, the full fifteen-rule catalog 13.97 s, and the ten-rule suite that actually ships 14.84 s. The cost is a floor plus a per-rule increment, not a function of row count — and the increment is lumpy (1.28–6.59 s for a single rule), so an average per rule is descriptive and not predictive. Synchronous execution survives, but only as a progressive one, and only up to a measured ceiling (O-3); the row cap is a net loss that breaks two catalog types (O-2).

**LT-2 · Great Expectations API and Claude Agent SDK surface** — *fed F3, F5, F7, INV-2, INV-3* — **EXECUTED**
- **LT-2a** (`FINDINGS.md` § "LT-2a · Great Expectations 1.x object model and registry") — 1.20.0, 56 registered types, from which the fifteen-type catalog is drawn (O-1); the object model is pydantic v1 and needs no `DataContext` to construct or compile. Crucially, GE's constructor check is necessary but not sufficient — it accepts contradictory bounds, uncompilable regexes and missing parameters — so F5 carries its own sanity table.
- **LT-2b** (`FINDINGS.md` § "LT-2b · Claude Agent SDK — auth, tool suppression, structured output") — a subscription token authenticates `claude-agent-sdk` 0.1.23 in a server process with every built-in tool off, one turn, and structured JSON by instruction; 6.6 s and $0.041 per call. The rules it proposes are statistically true and business-naive, which is why F3 proposes and never activates.

---

## 9. Open items

| ID | Item | Status | Resolution, and the number behind it |
|---|---|---|---|
| **O-1** | Exact composition of the ~15-type catalog | **RESOLVED** (LT-2a) | Fifteen types selected from the 56 in the GE 1.20.0 registry — single-column and table-level only, the six multi-column types excluded because F4 already rejects multi-column rules as v2. The catalog is listed in full in `FINDINGS.md` § LT-2a. It cannot be generated from GE introspection alone: `.schema()["required"]` is incomplete, so each entry also carries our own required-parameter and sanity constraints (F5). |
| **O-2** | Row cap for F8 | **RESOLVED — no cap** (LT-1b) | The cap is the wrong lever, for three measured reasons. It buys little: capping to 100,000 rows — an 80% cut — saves 5.5 s of 14.8 s (37%), because the cost is a per-run and per-rule floor and not the scan. It is a net loss at full size: GE runs a query asset verbatim through a client-side cursor, so `LIMIT 500000` costs 22.67 s and moves 1,000,127 rows to the client against 13.63 s and 156 rows uncapped. And it breaks two of the fifteen catalog types outright — `expect_column_values_to_be_of_type` and `expect_column_values_to_be_in_type_list` raise `KeyError: 'type'` on a query asset, and with `catch_exceptions` defaulting to `True` (LT-1a) they would surface as two silently red rules with no offending rows. What still ships is INV-5's disclosure mechanism, carried by us from the asset definition into the result, with the cap switched off at this scale (F8). |
| **O-3** | Synchronous vs background execution | **RESOLVED — synchronous, progressive** (LT-1b) | Worst case measured in the shipping configuration is **14.84 s** for the ten-rule suite `unexpected_index_column_names` requires (the full fifteen-rule catalog measures 13.97 s — fewer rules cost more because the two type expectations were substituted for two aggregates), past the 10 s bar. But the cost is a floor plus a lumpy per-rule increment, paid as a sequence of independent statements. A job queue improves none of that: it returns the same total later, with a polling endpoint and a staleness problem added. Streaming each verdict as it lands turns a 14 s wait into a first verdict followed by a filling list, at no cost in total time. F8 and F13 carry the clauses. **The ceiling is measured, not hypothetical:** only **3 rules** fit under 10 s at 500,000 rows, and with 10 rules only **100,000 rows** do. Progressive rendering is what makes 14 s honest, not fast — a product that lets rules accumulate crosses the watchable line by design (§5). Execution uses the direct connection: the pooler is 21% slower on identical work, 17.94 s against 14.84 s. |
| **O-4** | Transport for progressive results | **OPEN** (new, from LT-1b) | O-3 settled that the run must stream; it did not choose how each verdict reaches the browser — server-sent events, a chunked response, or one request per rule driven by the client. Resolution path: decided when F8 and F13 are implemented, constrained by F7 — whatever is chosen must work with a single process-global GE context and must not create one per request. |
