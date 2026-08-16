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

## Recommendation (pending author's decision — beads epic `dq-j15`)

**Run Ledger as the base direction** — top-2 in every lens, its "book of record"
metaphor encodes the render-from-record decision directly, and it is the cheapest
to build faithfully. Graft from the runners-up:

1. Default entry on the domain-expert view, "Accept — I vouch for this" copy and
   the queue time-budget indicator (from Reviewer).
2. Real per-role density filtering — eng-only columns/config (Ledger's one weakness).
3. Optionally, Diglot's English ⟷ GE facing panes on the F12 authoring card only.

Known mockup defects noted by the judges (fix in synthesis, not here): Workbench's
F10 files `customers` under "never run" while F13 holds a running record for it;
Reviewer's 15-item catalog does not map 1:1 to GE expectation types; Console is
deliberately single-theme.
