# UX design variants — F10–F13

Four independently generated design directions for the assistant's four screens
(F10 Table Explorer, F11 Review Queue, F12 Rule Management, F13 Results Dashboard),
produced by a 4-generator + 3-judge workflow on 2026-08-16. Every variant satisfies
the hard constraints derived in `../UX_HARNESS_FINDINGS.md` §3–§5: status as one
atom (`FAILED · sampled 500K / 2.4M`), render-from-persisted-run-record, buckets
sorted by *unverified*, evidence-visible capped bulk-accept, neutral "Compiled OK",
reject-with-reason for inexpressible rules.

Each file is fully self-contained — open it in a browser, switch screens via the
tab bar, and flip the engineer / domain-expert role toggle.

| File | Variant | Philosophy |
|---|---|---|
| `ux-variant-ledger.html` | **Run Ledger** | Record-centric: runs as immutable ledger entries, rules as numbered clauses, stamped statuses |
| `ux-variant-reviewer.html` | **Vouch Reviewer** | Domain-expert-first guided queue: one decision at a time, "Accept — I vouch for this" |
| `ux-variant-workbench.html` | **Diglot Workbench** | Bilingual split-pane: plain English ⟷ GE config as facing pages |
| `ux-variant-console.html` | **Vouch Console** | Engineer-first dense dark ops console, keyboard-driven |

## Judge scores (0–10 per lens)

| Variant | Compliance | Expert usability | Product/buildability | Total /30 |
|---|---|---|---|---|
| Run Ledger | 9.0 | 8.0 | 8.4 | **25.4** |
| Vouch Reviewer | 8.2 | 9.0 | 7.7 | 24.9 |
| Diglot Workbench | 8.5 | 6.5 | 8.0 | 23.0 |
| Vouch Console | 9.5 | 5.0 | 6.8 | 21.3 |

## DECISION — Diglot Workbench is the base direction (2026-08-16, beads epic `dq-j15`)

**The author has chosen `ux-variant-workbench.html` (Diglot Workbench) as the base
direction, overriding the judge panel.** The judges recommended Run Ledger (25.4)
over Workbench (23.0); the author took the lower-scored variant deliberately. The
score table above stands as measured — this section does not re-score it, it records
that the decision went the other way and what that costs.

The judged case for Ledger was that it is top-2 in every lens and cheapest to build
faithfully. The author's case for Workbench is that its central idea — the same rule
shown as plain English and as compiled Great Expectations, side by side, each user
working from their own side — *is* the product's thesis. INV-2 (an invalid or
hallucinated expectation can never reach the rule store) and INV-3 (GE is a runtime,
not the domain model) are both statements about keeping those two languages distinct
and in sync. Workbench is the only variant whose layout makes that visible rather
than asserting it in copy.

### The known cost, and what we do about it

Workbench's measured weakness is **expert usability: 6.5 — the second-lowest of the
four**, and lower than Ledger's 8.0 and Reviewer's 9.0. This matters directly to
**INV-1** (a domain expert can act on a table's proposals in ≤ 5 minutes), so it is
not a taste disagreement we can absorb.

Mitigation, in build order:

1. **Take the Reviewer's expert ergonomics wholesale, not as polish.** The domain
   expert's F11 gets Reviewer's one-decision-at-a-time queue, its **"Accept — I vouch
   for this"** primary-action copy (which names what the human is actually doing —
   staking their judgment — where "Accept" names only a click), and its **queue
   time-budget indicator** ("about 2 minutes left"). The budget indicator is the
   cheapest instrument we have for INV-1: it puts the five-minute promise on screen
   where a user can see it being kept or broken.
2. **Keep Workbench's role split absolute, not cosmetic.** Workbench already routes
   each role to its own door (`show(expert ? 'f11' : 'f10')`) and makes the tables
   rail non-navigable for the expert. That is what buys back expert usability; it
   must survive synthesis intact rather than degrading into a density toggle.
3. **Re-measure rather than assume.** The 6.5 was scored against the mockup, not
   against the built screens with grafts 1–2 in place. Treat it as a debt with a
   test, not a fact: INV-1 is checked by the harness, and that check is the arbiter.

### Grafts from the runners-up that still apply

- **From Reviewer:** "Accept — I vouch for this" copy, and the queue time-budget
  indicator. (Both above — listed again here because they are the two we keep even
  if graft 1's full queue shape is cut for scope.)
- **From Diglot itself, per the judges:** the judges' own recommendation for Ledger
  included grafting *Diglot's English ⟷ GE facing panes onto the F12 authoring card*.
  That graft is now the base rather than an add-on — the panel independently rated
  the idea worth importing, which is corroboration for this decision rather than a
  contradiction of it.
- **From Ledger:** the "book of record" framing for F13 — render-from-persisted-run-
  record, runs as immutable entries. Workbench's F13 already does this (its running
  row says "this row is the record, refreshed — 'running' is just another status
  value"); Ledger's stamped, numbered presentation is the reference if Workbench's
  F13 proves thin in build.

### ⚠ The one real conflict: F12 and the collapsed configuration

**SPEC F12 is FROZEN and says:** *"The generated Great Expectations configuration is
present and editable, **collapsed by default**."* Workbench's core idea is that it is
**not** collapsed — it is a permanently-open facing page, `.en-pane` beside `.ge-pane`
in a two-column `.spread`. This is a genuine conflict with a frozen SPEC clause, not a
detail to be smoothed over in synthesis.

Workbench does not ignore the clause's *intent* — it resolves it differently, by role:

```css
body.expert .ge-pane   { display: none; }        /* expert never sees the config */
body.expert .spread    { grid-template-columns: 1fr; }
body.expert .ge-note   { display: flex; }        /* "compiled GE available … [show]" */
```

For the **domain expert**, the GE pane is not collapsed — it is *absent*, replaced by
a one-line `.ge-note` reading "compiled GE available — secondary in this view · show".
That is stricter than the SPEC: collapsed-by-default still puts a GE disclosure
triangle in front of a user who should never need to know GE exists (the same reason
GE Data Docs is a non-goal). For the **engineer**, the pane is open and facing,
because for that user a collapsed config is a click tax on the thing they came for.

**Recommended amendment, so both stay honest:**

> **F12:** the generated Great Expectations configuration is **hidden entirely for the
> domain expert** (an unobtrusive "compiled GE available" affordance only, no config
> in the default view) **and a facing pane for the engineer** — present and editable
> in both cases, never collapsed-by-default for either.

**Amending a frozen SPEC is the author's call, and that call has not been made.**
SPEC.md is unchanged and remains Rev 0.3 FROZEN. Until it is amended, F12 as written
still governs, and bead `dq-rbf.4` (B20) still carries the shipped e2e check
`test_generated_config_is_collapsed_on_first_paint`. Do not resolve this by editing
the test, and do not resolve it by editing SPEC.md — either is a decision, and this
one belongs to the author.

### Known mockup defects — do not build these by accident

- **Workbench (the chosen base) contradicts itself on `customers`.** F10 files
  `customers` under bucket "1 · Never run" with a `NEVER RUN` status atom (line ~470),
  while F13 Record 4 holds `run_0493 · customers · RUNNING · STARTED 14:35:10 UTC`
  (line ~889). A table cannot be both. This is a mockup slip, and it is exactly the
  class of bug the render-from-persisted-run-record decision exists to make
  impossible: both screens must read the same run record, so "never run" is the
  *absence* of a record and never a hardcoded state. Fix in synthesis.
- Reviewer's 15-item catalog does not map 1:1 to GE expectation types — the catalog
  renders from the one canonical file (B6).
- Console is deliberately single-theme.
