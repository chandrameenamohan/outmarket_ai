# DEMO — the run of show

Nine minutes, seven beats, one browser. It is `SPEC.md` §7 performed rather than asserted,
with one change: §7 starts from an empty store, and a live demo cannot afford three empty
screens in the first minute. So the demo runs on **two tables at once** — `orders` carries the
states the fixture already seeded, and `payments` is the one table the fixture deliberately
leaves ruleless (`seed/seed_demo_rules.py`), which is where the live arc happens.

---

## Before you press record

```bash
docker compose up --build          # ~2 min cold; http://localhost:3000
make demo-fixture                  # second terminal. NOT optional — see README "Run it"
```

Then, **once, the day before** — the only two beats that depend on a live model call and a live
run, so rehearse exactly these and nothing else:

- `/tables/payments/rules` → request suggestions. Confirm a proposal about `method` comes back.
- Accept it, run it. Confirm it **fails at 180 rows** (defect D12, `seed/MANIFEST.md`).

If either misses, fall back to the `orders` beats below and say so out loud. Do not re-shoot.

Two tabs open, nothing else: `http://localhost:3000` and `seed/MANIFEST.md` on screen 2 as the
ground truth you will hold the product against.

---

## The run of show

### 1 · The door — who is asking? (30 s)
**Route:** `/`

> "Two people use this. An engineer who can read a Great Expectations config, and a domain
> expert who can't and shouldn't have to. The product asks which one you are, and it means it —
> this isn't a theme, it's a different set of screens."

Pick **engineer**.

### 2 · Coverage, including the absence of it (45 s)
**Route:** `/tables`

Three buckets. Point at the bottom one.

> "`payments` has no rules at all. Most tools show you what you've checked; the loudest thing
> this screen says is what nobody has checked yet. That's the bucket we're going to empty."

### 3 · Proposals arrive with their evidence (90 s) — *live model call*
**Route:** `/tables/payments/rules` → request suggestions

Progress indicator runs ~6.6 s (measured, LT-2b). Talk over it:

> "One model call. It's reading the schema and a sample, not guessing from column names."

When they land:

> "Each proposal is in English, and each shows the evidence underneath it — the values it
> actually saw. Nothing here is active yet. A model does not get to write to the rule store."

Accept the `method` vocabulary proposal. Flag one you *can't* verify as **needs review**, copy
its URL.

> "That one encodes a business assumption I'm not qualified to confirm. So I don't accept it —
> I send it to someone who is."

### 4 · The second user, working independently (60 s)
Switch role to **domain expert** (or a second browser). **Route:** `/review`

> "They never see a table list. They see a queue."

The flagged rule is waiting. Paste the copied URL — same rule, direct link. Reject it:

> *"cancelled orders use a fourth status not in this sample"*

> "The reason is stored with the rule. Six months from now the question 'why isn't this
> checked?' has an answer written by the person who made the call."

### 5 · English becomes an executable check (75 s) — *live model call*
Still the expert. Type into the rule field:

> *"order total can never be negative"*

> "Notice what is **not** on this screen. The Great Expectations configuration isn't collapsed
> for them — it isn't rendered at all. The engineer sees both panes side by side; the expert
> sees the sentence they wrote."

Confirm to save.

### 6 · The refusal — the most important 40 seconds
Type:

> *"shipped date must be after order date"*

It is rejected, in words, naming the limitation.

> "This is a real defect in the data — 320 rows of it, and I can show you the count. The product
> still says no, because that rule compares two columns and this engine is single-column. The
> alternative is a plausible-looking rule that silently checks nothing, and that is worse than
> no rule. Nothing was stored. Coverage didn't move."

### 7 · Execution finds the planted defect (90 s) — *live run*
Back to **engineer**. Run the suite on `payments`.

> "Verdicts land one at a time, not behind a blank spinner."

The `method` rule fails.

> "180 rows. Here's the manifest I seeded the database from" — *screen 2* — "**D12, 180 rows.**
> The product found exactly what's there, and it's telling me in the language the rule was
> written in, with real offending values — `'cred_card'`, `'PAYPAL'`, a `'Card '` with a
> trailing space."

Reload. It renders instantly from cache. Then `/tables`:

> "`payments` has moved buckets. That's the loop closing."

---

## Close (30 s)

> "Four things I'd point at. The model never writes to the store — it proposes, a human accepts.
> The two users are genuinely different products, not one product with permissions. The system
> refuses rules it can't honestly run. And `AI_USAGE.md` is the fourth deliverable: how this was
> built, including the four things the gate caught me on."

---

## If it breaks

| Breaks | Do |
|---|---|
| Proposals don't return | `/tables/orders/rules` — the fixture's eight rules are already there. Narrate the states instead of minting one. |
| The live run hangs | `/runs/<record id>` from the fixture. Two run records exist and render instantly. |
| Screens look empty | `make demo-fixture` didn't run. Run it, reload. |
| Port taken | `DQ_WEB_HOST_PORT=3100 DQ_API_HOST_PORT=8100 docker compose up` |

## Do not claim

- **There is no deployed URL** (bead `dq-cyi.1`). Demo from `localhost` and say so.
- **1,280 known-bad rows are invisible to this rule set** (`seed/MANIFEST.md`) — four multi-column
  defect classes. Beat 6 is where you say that on purpose. Don't let beat 7 imply the table is clean.
- The run latency ceiling is ~14 s and holds for a handful of rules, not dozens (`SPEC.md` §5).
