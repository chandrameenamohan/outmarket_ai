# Learning test findings

One section per learning test, most recent first; add new sections at the top
and a row to the index below. Each section records what was verified against the
**really installed** library, what was measured, and what surprised us — because
a surprise is the only part of a learning test that changes the design.

The scripts themselves carry the same findings in their module docstrings; this
file is the index a reader hits first.

| Test | Subject | Status | Script |
|---|---|---|---|
| LT-1a | Great Expectations against real PostgreSQL — execution and result shape | passed | `lt1a_ge_postgres.py` |
| LT-1b | Great Expectations latency on Supabase — direct vs pooled | passed | `lt1b_ge_latency.py` |
| LT-2a | Great Expectations 1.x — object model and registry | passed | `lt2a_ge_registry.py` |
| LT-2b | Claude Agent SDK — auth, tool suppression, structured output | passed | `lt2b_agent_sdk.py` |

---

## LT-1b · Great Expectations latency on Supabase — direct vs pooled

**Bead** `dq-e1d` · **Run** 2026-08-16
**great-expectations 1.20.0**, SQLAlchemy 2.0.52,
psycopg2-binary, Python 3.12.5,
PostgreSQL 17.6 (Supabase, `ap-southeast-1` / Singapore)
**Feeds** SPEC **O-2** (row cap), **O-3** (synchronous vs background),
F8, F9, F13, INV-1, INV-5
**Run it:**

```bash
cp ../.env .env
uv run --with great-expectations --with 'sqlalchemy>=2' \
       --with psycopg2-binary --with 'psycopg[binary]' \
       python learning-tests/lt1b_ge_latency.py
```

Every cell is 1 discarded warm-up run plus **5 measured runs**;
tables report the median and the min–max spread. Nothing here writes to the
database — every statement issued is a `SELECT`. The tables are the seeded
demo set: `orders`, 500,000 rows, only the primary key indexed
(`seed/MANIFEST.md`). Counts were checked against the manifest before timing
started, so these are timings of real work: GE reported exactly the planted
150 negative totals, 240 bad statuses and 150 duplicate references.

### The verdict, in plain words

Thresholds were fixed **before** the numbers were read: ≤2 s reads
as instant, ≤5 s needs only a spinner, ≤10 s is
tolerable with visible progress, and beyond that a synchronous screen is
dishonest and the work belongs in a background job.

**A full-catalog run over the whole table does not clear that bar.** All
fifteen catalog rules over 500,000 rows on the direct connection take
**13.97 s**. The 10-rule suite in the configuration F8
will actually ship (`unexpected_index_column_names`, which F13 needs for
identifier-plus-value) takes **14.84 s** — past the bar — a blank spinner is not honest here.

Those two are within noise of each other rather than 5 rules apart in cost,
and that is not a mistake: the 10-rule curve suite substitutes two
*aggregate* expectations for the two *type* expectations the fifteen contains,
because the type ones cannot run on a capped batch at all (below). The cheap
rules are cheap and the dear one is dear; the count is not what sets the price.

But a bare pass/fail is not something F8 can be designed against, so here is
where the line actually falls:

| question | measured answer |
|---|---|
| largest suite that fits under 10 s at 500,000 rows | **3 rules** |
| largest row count that fits under 10 s with 10 rules | **100,000 rows** |
| marginal cost of one more rule at full size | **0.83 s** |
| single rule, whole table, shipping config | **2.28 s** |

So the honest statement is not "synchronous works" or "synchronous fails". It
is: **a run is watchable while the suite is small, and stops being watchable
somewhere between 3 and 8 rules on a table this size**, and
the growth is per-rule, not per-row. A product that lets a domain expert
accumulate rules will cross that line by design, not by accident.

**F8 should use `SUPABASE_DB_URL_DIRECT` (port 5432.)**
The transaction-mode pooler did not break GE, but it is slower for this workload:
17.94 s against 14.84 s for identical work
(+21%). A rule run is a handful of long
analytical statements on one connection, which is the shape a pooler helps
least and taxes most.

### Connect time, separated from run time

INV-1 is about what the user waits for *after* the page is open. A server
process registers its datasource once at boot and reuses it; connect is never
inside the number the user watches. It is reported apart and is never added in.

| | connect (`add_postgres`, eager) | `SELECT 1` round trip |
|---|---|---|
| direct (5432, `db.fzqjiudsvcromqsrlhqw.supabase.co:5432`) | 1.16 s [0.98–1.37] | 51 ms [47–164] |
| pooled (6543, `aws-0-ap-southeast-1.pooler.supabase.com:6543`) | 2.26 s [2.02–2.41] | 109 ms [94–187] |

The round trip to Singapore is the floor under every statement GE issues.
At 51 ms and 28
statements, roughly **10%** of a full run is network latency that
no amount of SQL tuning will remove.

### The row-count curve

10 rules, both result-format configurations, both URLs. `wall` is what
the user waits for; `db` is the summed server time of every statement GE
issued, measured from SQLAlchemy's cursor events; `ovh` is the remainder —
GE's own Python.

| conn | rows | mechanism | config | wall med (s) | min–max | db (s) | ovh (s) | stmts | rows pulled | per rule (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| direct | 1,000 | query asset, LIMIT | plain | 4.16 | 4.07–5.37 | 2.00 | 2.12 | 17 | 2,009 | 0.42 |
| direct | 1,000 | query asset, LIMIT | indexed | 5.53 | 5.37–6.04 | 2.97 | 2.57 | 25 | 2,011 | 0.55 |
| direct | 10,000 | query asset, LIMIT | plain | 5.04 | 4.76–7.62 | 2.90 | 2.27 | 17 | 20,010 | 0.50 |
| direct | 10,000 | query asset, LIMIT | indexed | 6.22 | 5.98–8.91 | 3.60 | 2.63 | 25 | 20,013 | 0.62 |
| direct | 100,000 | query asset, LIMIT | plain | 6.95 | 6.74–7.87 | 4.75 | 2.12 | 17 | 200,049 | 0.69 |
| direct | 100,000 | query asset, LIMIT | indexed | 9.31 | 8.96–10.61 | 6.91 | 2.77 | 25 | 200,091 | 0.93 |
| direct | 500,000 | table asset | plain | 10.53 | 10.35–11.87 | 8.38 | 2.13 | 20 | 96 | 1.05 |
| direct | 500,000 | table asset | indexed | 14.84 | 13.35–16.16 | 11.70 | 2.72 | 28 | 156 | 1.48 |
| pooled | 1,000 | query asset, LIMIT | plain | 7.59 | 7.52–8.58 | 3.88 | 3.83 | 17 | 2,009 | 0.76 |
| pooled | 1,000 | query asset, LIMIT | indexed | 9.81 | 9.52–10.27 | 5.48 | 4.38 | 25 | 2,011 | 0.98 |
| pooled | 10,000 | query asset, LIMIT | plain | 7.75 | 7.63–8.72 | 4.29 | 3.60 | 17 | 20,010 | 0.78 |
| pooled | 10,000 | query asset, LIMIT | indexed | 11.62 | 10.07–12.28 | 6.73 | 4.86 | 25 | 20,013 | 1.16 |
| pooled | 100,000 | query asset, LIMIT | plain | 10.95 | 10.17–22.62 | 7.10 | 3.85 | 17 | 200,049 | 1.09 |
| pooled | 100,000 | query asset, LIMIT | indexed | 15.39 | 12.99–16.27 | 10.19 | 5.39 | 25 | 200,091 | 1.54 |
| pooled | 500,000 | table asset | plain | 14.03 | 13.64–15.31 | 10.28 | 3.74 | 20 | 96 | 1.40 |
| pooled | 500,000 | table asset | indexed | 17.94 | 17.70–20.64 | 13.51 | 4.46 | 28 | 156 | 1.79 |

Read it as: **wall time is not linear in rows, it is dominated by a fixed
floor.** Going from 1,000 rows to 500,000 — a 500× increase — costs
2.7× the time. The scan itself scales; almost everything
else does not.

### Suite size — per run, or per rule?

Whole table, direct, shipping config, nested prefixes of the same catalog.

| rules | wall med (s) | min–max | db (s) | ovh (s) | stmts | per rule (s) |
|---|---|---|---|---|---|---|
| 1 | 2.28 | 2.15–2.84 | 0.94 | 1.34 | 9 | 2.28 |
| 3 | 3.39 | 3.31–3.91 | 1.82 | 1.55 | 15 | 1.13 |
| 8 | 11.94 | 11.84–13.42 | 9.78 | 2.30 | 27 | 1.49 |
| 10 | 12.14 | 11.75–16.06 | 9.59 | 2.49 | 27 | 1.21 |
| 15 | 13.97 | 13.60–15.17 | 11.19 | 2.82 | 30 | 0.93 |

Averaged over the range, that is **2.3 s of floor plus ~0.83 s
per additional rule** — but the average is the least useful number in the table.
The real shape is lumpy: 1 → 3 rules adds 1.1 s,
3 → 8 adds 8.6 s, and 8 → 15 adds only
2.0 s. **What a rule costs depends on which rule
it is, not on how many are already there** — and the per-rule table below says
which ones are expensive.

### Per-rule cost, cheapest to dearest

Each catalog type alone, whole table, direct, shipping config, 3 runs each.
These are **not additive** — every one of them pays the same per-run floor.
The point is the ranking.

| rule | wall med (s) | min–max | db (s) | stmts |
|---|---|---|---|---|
| `table_row_count_between` | 1.28 | 1.22–1.29 | 0.20 | 1 |
| `be_in_type_list(order_total)` | 1.59 | 1.45–1.69 | 0.47 | 5 |
| `column_to_exist(order_total)` | 1.68 | 1.51–1.72 | 0.56 | 5 |
| `be_of_type(order_id)` | 1.77 | 1.55–1.83 | 0.51 | 5 |
| `mean_between(order_total)` | 2.16 | 2.03–3.11 | 0.93 | 7 |
| `unique_value_count_between(status)` | 2.41 | 2.31–2.80 | 1.14 | 7 |
| `be_null(shipped_at)  [contrived]` | 2.46 | 2.45–3.15 | 1.15 | 9 |
| `be_in_set(status)` | 2.50 | 2.46–2.75 | 1.18 | 9 |
| `not_be_null(customer_id)` | 2.61 | 2.30–2.94 | 0.99 | 9 |
| `not_be_in_set(channel)` | 2.65 | 2.58–3.16 | 1.24 | 9 |
| `be_between(order_total >= 0)` | 3.01 | 2.50–3.14 | 1.30 | 9 |
| `value_lengths_between(currency)` | 3.14 | 3.11–3.16 | 1.70 | 10 |
| `not_match_regex(status)` | 3.45 | 3.19–3.73 | 1.96 | 9 |
| `match_regex(order_reference)` | 4.03 | 3.43–4.07 | 2.28 | 9 |
| `be_unique(order_reference)` | 6.59 | 6.47–6.65 | 5.12 | 10 |

Fourteen of the fifteen sit between 1.3 s and
4.0 s. One does not: **`be_unique(order_reference)` costs
6.59 s**, 2.7× the median rule. It is
a uniqueness check on an unindexed `text` column over 500,000 rows, so
PostgreSQL sorts. That single rule is most of the 3 → 8 jump in the table above.

The seed deliberately leaves everything but the primary keys unindexed
(`seed/MANIFEST.md`), precisely so a measurement is not flattered by an index
nobody would have. So this is the honest number for an unprepared table — and
it also says where the cheapest available win is, if one is ever wanted.

### `result_format="COMPLETE"` — priced, not just warned about

LT-1a called it a trap; this is what it costs. Whole table, direct.

| case | wall | rows over the wire | unexpected |
|---|---|---|---|
| narrow (150 offending) | 2.79 s | 201 | 150 |
| wide (~all rows offending) | 2.99 s | 500,031 | 500000 |
| SUMMARY narrow | 2.54 s | 71 | — |
| SUMMARY wide | 2.87 s | 51 | — |

**The mechanism is exactly as LT-1a described; the price is lower than the
warning implied.** `COMPLETE` does drop the `LIMIT` and stream every offending
row — 500,031 of them for a rule that matches the whole table — but over
this link, for one numeric column, that cost about the same wall clock as the
bounded `SUMMARY` run.

That is not a licence to use it. Three things the timing does not show: the
transfer scales with column width and with every column
`unexpected_index_column_names` adds; each of those rows is materialised as a
Python object in the API process; and F9 stores the raw framework output, so a
`COMPLETE` run writes 500,031 values into the cache. **Keep the
prohibition — but on memory and storage grounds, which are the grounds these
numbers support, not on latency grounds, which they do not.**

### What the row cap itself costs

GE 1.x has no sampler. The only row cap is our own SQL through
`add_query_asset` — and GE executes that query **verbatim, twice per validate**,
through psycopg2's default client-side cursor, so every capped row is fetched
into the client before a single expectation is evaluated. Twice, not once: the
`rows over the wire` column in the curve above reads 2,009 for a 1,000-row cap
and 200,049 for a 100,000-row cap.

| | wall med (s) | min–max | rows over the wire |
|---|---|---|---|
| capped   LIMIT 500000 (query asset) | 22.67 | 22.47–22.89 | 1,000,127 |
| uncapped whole table   (table asset) | 13.63 | 13.15–14.09 | 156 |

At full size the cap is a **net loss**: asking for `LIMIT 500000` costs
22.7 s and moves 1,000,127 rows across the network, against
13.6 s and 156 rows for the same suite with no cap at
all. The uncapped table asset is 9.0 s faster *and* the
honest answer.

### UNEXPECTED — the row cap breaks two of the fifteen catalog types

Running the catalog over a **query asset** — the only row cap GE 1.x offers —
does not merely cost more. Two types stop working outright:

```
expect_column_values_to_be_in_type_list
    exception_message: 'type'
expect_column_values_to_be_of_type
    exception_message: 'type'
```

`expect_column_values_to_be_of_type` and
`expect_column_values_to_be_in_type_list` raise a bare `KeyError: 'type'`
against a query asset and run fine against the same data as a table asset.
GE reads the column type from the reflected table; a query asset has no
reflected table to read it from.

By itself that would be a nuisance. Combined with LT-1a's finding that
`catch_exceptions` defaults to `True` and an errored rule is visually
identical to a failing one, it is worse than a nuisance: **a capped run would
show those two rules red, with no offending rows and no explanation, and the
user would go looking for a data problem that does not exist.**

The curve below is therefore measured with a 10-rule suite drawn from the
catalog *minus* those two, so that the capped and uncapped cells do identical
work and the comparison means something. All fifteen are still timed against
the table asset in the suite-size and per-rule tables.

### The pooler

- sequential validates on 6543 — OK
- four concurrent validates on 6543 — OK — 4 threads, wall 7.04 s, per-thread [6.32, 6.45, 6.7, 7.02]
- psycopg v3 (server-side prepared statements) on 6543 — OK — 8 sequential runs, walls [6.94, 7.01, 6.62, 6.59, 7.06, 6.73, 7.9, 7.34]

### UNEXPECTED — `gx.get_context()` is process-global

`gx.get_context()` does not merely return a context; it **installs it as a
process-global project**. A second, unrelated call silently orphans the first
context's datasources. The failure does not surface at `get_context()`. It
surfaces later, at `validate()`, as:

```
DatasourceError: Cannot initialize datasource direct, error: The given datasource could not be retrieved from the DataContext; please confirm that your configuration is accurate.
```

— a configuration error naming a datasource that is sitting right there in the
context object you are holding. This cost this script its first full run: §2
was measuring connect cost by creating a throwaway context per sample, which
detached every asset §5 onwards depended on.

`great_expectations.data_context.data_context.context_factory.project_manager
.set_project(ctx)` puts it back, and this script asserts that it does.

**Consequence for F8 and INV-3.** The one GE-importing module must create
exactly one context for the process and hand it out — never one per request.
A request handler that calls `gx.get_context()` breaks every other request in
flight, and the error it produces points at configuration rather than at
concurrency, so it would be debugged in the wrong place.

### Drift

Supabase's free tier is burstable, and this script scans a 61 MB table a few
hundred times. The §5 baseline cell was re-run at the end:
14.84 s at the start,
13.61 s at the end
(-8.3%).

### Recommended answers

**O-2 · row cap for rule execution** — **Do not add a row cap. It is the wrong lever, and the mechanism available for it is worse than the problem.**

Three measured reasons, not one:

1. The cap buys little. Capping at 100,000 rows — an 80% cut — saves
   5.5 s of 14.8 s (37%). Cutting all
   the way to 1,000 rows, a 500× reduction, still leaves 5.5 s on the
   clock, because the cost is a per-run and per-rule floor, not the scan.
2. The cap is not free, and at full size it is a **net loss**: the query asset
   is executed verbatim on every validate through psycopg2's client-side
   cursor, so `LIMIT 500000` pulls 500,000 rows to the client before a single
   expectation is evaluated (§ "What the row cap itself costs").
3. The cap **breaks two of the fifteen catalog types outright**, and breaks
   them in the shape LT-1a warned about: silently, as a red rule.

What must still ship is INV-5's disclosure mechanism, because a cap will be
needed the moment a table is an order of magnitude larger than this one. GE
does not record that it was capped (LT-1a), so the marker has to be carried
by us from the asset definition into the stored result — build it, and leave
the cap switched off at this scale.

**O-3 · synchronous vs background execution** —
**synchronous, but progressive** — the request stays synchronous and streams each rule's verdict as it lands. Not a background job queue: the measured cost is a sequence of independent statements, and a worker would return the same total later with a polling endpoint and a staleness problem added.

The worst case measured is 14.0 s, past the 10 s bar. But the shape of the cost decides what to do about it, and the shape is: a 2.3 s floor plus ~0.8 s per rule, paid as a sequence of independent statements. Nothing in that is improved by moving it to a worker — a job queue would return the same 14 s later, with a polling endpoint and a stale-result problem added. What it argues for is **a synchronous request that streams each rule's verdict as it lands**: the first result appears in about 2 s and the list fills. Combined with F9's cache — a reload renders the last result without re-executing — that keeps F8, F9 and F13 the synchronous screens the spec describes.

SPEC §8's contingency is therefore **partially triggered**: the feature does not change into a job system, but F8's acceptance needs a progressive-result clause and F13 needs to render a partially-complete run. That is a spec revision to make before implementation, not during, and it is the author's call — the measurement's job is to say that a blank spinner for 14 s is not an option.

### Follow-ups — noted, deliberately not done here

Optimising these numbers is out of scope for this bead. Three things are worth
their own issue:

- **Per-rule streaming.** The run is a sequence of independent statements;
  F13 could render each rule's verdict as it lands instead of after all of
  them. That converts a 14 s wait into a 2 s wait
  followed by a filling list, without making anything faster.
- **GE's own Python overhead** is 21% of the wall clock at full
  size — more than the network. It is metric-graph resolution, not database
  work, and it is not something SQL tuning reaches.
- **A cheaper row cap.** If a cap is ever needed, `add_query_asset` as
  measured here is the wrong mechanism. Whatever replaces it has to be
  measured the same way before it is trusted.

Raw measurements: `learning-tests/lt1b_results.json`.

---
## LT-1a · Great Expectations executes against PostgreSQL

**Bead** `dq-dww` · **Run** 2026-08-16
**great-expectations 1.20.0**, SQLAlchemy 2.0.52, psycopg2-binary 2.9.9,
Python 3.12.5, PostgreSQL 17.6 (Supabase, `SUPABASE_DB_URL_DIRECT`, port 5432)
**Feeds** F8 (rule execution), F9 (result normalisation), F13 (results
dashboard), SPEC O-2 (row cap), INV-5
**Run it:**

```bash
cp ../.env .env      # .env is gitignored and absent from a fresh worktree
uv run --with great-expectations --with 'sqlalchemy>=2' --with psycopg2-binary \
    python learning-tests/lt1a_ge_postgres.py
```

Scope was correctness, not latency — timing, direct-vs-pooled and volume belong
to LT-1b (`dq-e1d`). The script builds and drops its own 100-row
`public.lt1a_ge_probe` and never reads the 500K seeded demo tables.

### What was verified

- [x] A suite runs end to end against real PostgreSQL and the counts are exact.
      100 rows, 25 planted negative `order_total`, 7 planted NULL `email`,
      0 planted `status` violations. GE reported 25, 7 and 0 — measured against
      a plain-SQL ground-truth count, not against the generator's constants.
- [x] One passing expectation and two failing ones in the same suite;
      `result.success is False`, `statistics` 3 evaluated / 1 successful /
      2 unsuccessful.
- [x] **Pushdown**, proved three ways (below). This is the finding LT-1b depends on.
- [x] Real offending values are retrievable, with row identifiers, and the
      sample size is a configurable pushed-down `LIMIT`.
- [x] The execute path **requires** a DataContext; an ephemeral one is enough
      and writes nothing to disk.
- [x] Both `psycopg2` and `psycopg` v3 drivers work when named explicitly.

### Measured

| | |
|---|---|
| planted / reported — negative `order_total` | 25 / **25** |
| planted / reported — NULL `email` | 7 / **7** |
| planted / reported — bad `status` | 0 / **0** |
| default offending-sample size | **20** (of 25 violations) |
| rows crossing the wire, whole 3-rule run | **58** (table holds 100) |
| SQL round trips — 1 expectation | 3 |
| SQL round trips — 3 expectations | 6 |
| SQL round trips — 3 expectations *with row identifiers* | 10 |

### How GE 1.x is pointed at a SQL table

Four objects, no YAML, no `great_expectations.yml`, no Checkpoint. Everything
online describing `context.add_datasource(yaml)` or a checkpoint run is pre-1.0
and does not apply.

```python
import great_expectations as gx
import great_expectations.expectations as gxe

context = gx.get_context(mode="ephemeral")
data_source = context.data_sources.add_postgres(
    name="supabase", connection_string="postgresql+psycopg2://...")
asset = data_source.add_table_asset(
    name="orders", table_name="orders", schema_name="public")
batch_definition = asset.add_batch_definition_whole_table(name="whole_table")
batch = batch_definition.get_batch()

result = batch.validate(
    suite,                                  # or a single Expectation
    result_format={
        "result_format": "SUMMARY",
        "unexpected_index_column_names": ["order_id"],
        "partial_unexpected_count": 20,
    },
)
```

`add_postgres()` opens a connection eagerly (`test_connection()`), so a bad DSN
raises `TestConnectionError` at registration rather than halfway through a run —
useful, and worth surfacing as a config error rather than a rule failure.

**A DataContext is required here**, unlike the compile path LT-2a mapped.
`PostgresDatasource(...)` constructs and `add_table_asset` / `add_batch_definition`
both work with no context, but `batch_definition.get_batch()` raises
`MissingDataContextError`. `gx.get_context(mode="ephemeral")` satisfies it,
`root_directory is None`, and no `gx/` project directory appears in the repo —
so nothing new needs gitignoring and the one GE-importing module (INV-3) can
create a context per process without touching the filesystem.

**Driver.** A bare `postgresql://` URL resolves to psycopg2 in SQLAlchemy;
with only psycopg v3 installed it fails at `add_postgres()` with
`ModuleNotFoundError: No module named 'psycopg2'`. Both drivers work when named
(`postgresql+psycopg2://`, `postgresql+psycopg://`); psycopg2-binary is what
`great-expectations[postgresql]` itself pulls in, so that is the one to pin.
Watch the resolver too: `--with sqlalchemy` unpinned resolved to **1.4.0** and
built it from source; pin `sqlalchemy>=2`.

### Pushdown, and how it was determined

**GE compiles each expectation into aggregate SQL and lets PostgreSQL do the
counting.** Determined by tapping SQLAlchemy's `before_cursor_execute` /
`after_cursor_execute` events and reading the statements actually issued:

```sql
-- the violating count, computed server-side
SELECT sum(CASE WHEN (order_total IS NOT NULL AND order_total < 0)
                THEN 1 ELSE 0 END) AS "column_values.between.unexpected_count",
       sum(CASE WHEN (order_total IS NULL) THEN 1 ELSE 0 END)
                AS "column_values.nonnull.unexpected_count"
FROM (SELECT * FROM public.lt1a_ge_probe WHERE true) AS anon_1

-- the only row-returning statement, and it is bounded
SELECT order_total AS unexpected_values
FROM (SELECT * FROM public.lt1a_ge_probe WHERE true) AS anon_1
WHERE order_total IS NOT NULL AND order_total < 0
LIMIT 20
```

Three independent checks, all asserted in the script:

1. the aggregate statements exist and contain `sum(CASE WHEN ...)`;
2. **no** row-returning statement lacks a `LIMIT`, and every one of those
   limits resolves to the `partial_unexpected_count` bind parameter;
3. rows actually handed back to Python, counted off `cursor.rowcount`, were
   **58** across a whole 3-expectation run over a 100-row table.

**Consequence for LT-1b.** Wall time will be dominated by PostgreSQL scan time
and per-statement round trips to Singapore, *not* by transferring 500K rows.
LT-1b should therefore measure: statements per rule (~2 plain, ~3.3 with row
identifiers), whether those statements are sequential or overlapped, and how
scan time grows from 100 to 500K rows. It should **not** expect the result-set
size to matter — unless someone sets `result_format="COMPLETE"` (see below),
which is exactly the configuration that would invalidate the measurement.

Round trips grow sub-linearly: the `table.row_count` metric is computed once per
run and independent aggregates are merged into a single statement (1 expectation
-> 3 statements, 3 expectations -> 6). Asking for row identifiers costs one extra
bounded `SELECT` per expectation and stops `row_count` being shared (3
expectations -> 10). Both numbers are worth timing.

### The result shape F9 must normalise

`batch.validate(suite)` returns
`great_expectations.core.expectation_validation_result.ExpectationSuiteValidationResult`.

```
ExpectationSuiteValidationResult
  .success                  bool — the whole run
  .statistics               {evaluated_expectations, successful_expectations,
                             unsuccessful_expectations, success_percent}
  .results                  list[ExpectationValidationResult]  <- order NOT guaranteed
  .suite_name, .suite_parameters, .id
  .meta                     {great_expectations_version, batch_spec,
                             batch_markers, active_batch_definition}
  .meta["batch_spec"]       {type, data_asset_name, table_name, schema_name,
                             batch_identifiers}          <- the provenance to store
```

Per expectation:

| What F9 needs | Where it lives |
|---|---|
| pass/fail | `r["success"]` — **not** `unexpected_count == 0` |
| rule identity | `r["expectation_config"]["type"]` + `["kwargs"]` |
| rows scanned | `r["result"]["element_count"]` |
| **violating rows** | `r["result"]["unexpected_count"]` |
| proportion (of non-missing) | `r["result"]["unexpected_percent"]` — 0–100, not 0–1 |
| proportion (of `element_count`) | `r["result"]["unexpected_percent_total"]` |
| nulls excluded from the check | `r["result"]["missing_count"]` / `["missing_percent"]` |
| **sample offending values** | `r["result"]["partial_unexpected_list"]` |
| ... with frequencies | `r["result"]["partial_unexpected_counts"]` -> `[{"value":…, "count":…}]` |
| ... with row identity | `r["result"]["partial_unexpected_index_list"]` -> `[{"order_id":…, "order_total":…}]` |
| errored, as opposed to failed | `r["exception_info"]` — two shapes, see below |

Every one of these must be read with `.get()`; the key set varies (below).

**Storage** is `json.dumps(result.to_json_dict())` with **no custom encoder** —
4.4 KB for a 3-rule run, and `json.loads` round-trips it exactly. That is F9's
"raw framework output retained separately". `to_json_dict()` has already
flattened Decimal, the enums and the pydantic objects; `json.dumps` on the live
`.result` raises `TypeError: Object of type Decimal is not JSON serializable`.

### Offending sample values (F13)

Real values come back, not just a count. By default **20** of them, in
`partial_unexpected_list`. The cap is configurable and it is a genuine
pushed-down `LIMIT`: passing
`result_format={"result_format": "SUMMARY", "partial_unexpected_count": 25}`
changed the SQL to `LIMIT 25` and returned 25 values.

For F13's *"#88231 −450.00"* — the identifier as well as the value — pass
`unexpected_index_column_names: ["order_id"]` and read
`partial_unexpected_index_list`:

```json
[{"order_id": 1, "order_total": -3.5}, {"order_id": 2, "order_total": -7.0}]
```

Still bounded by `partial_unexpected_count`, so it stays cheap. **This is the
setting F8 should use.**

**`result_format="COMPLETE"` is a trap.** It drops the `LIMIT` from the sample
query entirely and streams every offending row to the client — on the 500K table
with a rule that matches widely, that is a full pull. It does produce
`unexpected_index_query`, the SQL string that would return the bad rows, which
is worth *showing* in F13's raw panel without executing it.

### Sampling / row cap — resolves the mechanism for SPEC O-2 (INV-5)

**GE 1.x has no sampler.** The 0.x splitter/sampler API is gone — `add_sampler`,
`add_splitter` and `sampling_method` are all absent from the asset.
`great_expectations.core.partitioners` offers only *partitioners*
(`ColumnPartitionerDaily/Monthly/Yearly`, `PartitionerColumnValue`,
`PartitionerModInteger`, `PartitionerDividedInteger`, ...) — every one of them
slices by a **column**, none is "first N rows".

The only row cap is our own SQL, through `add_query_asset`:

```python
asset = data_source.add_query_asset(
    name="orders_capped", query="SELECT * FROM public.orders LIMIT 100000")
```

Verified: a `LIMIT 10` query asset reported `element_count: 10` and
`unexpected_count: 10` where the whole table gave 25.

**And GE does not record that it was capped.** Nothing in `element_count`,
`unexpected_count` or `meta` distinguishes a capped run from an honest run over
a smaller table. INV-5's sampling marker therefore cannot be recovered from GE's
output — it has to be carried by us, from the asset definition into the stored
result, or the disclosure silently disappears.

### UNEXPECTED — four things, and each one changes F9

**1 · There is no single result shape.** GE returns three, by base class:

| Base class | `result` body |
|---|---|
| `ColumnMapExpectation` | `element_count`, `unexpected_count`, `unexpected_percent`, `partial_unexpected_list`, ... |
| `ColumnAggregateExpectation` | `{"observed_value": 461.125}` — **no count, no samples** |
| `BatchExpectation` (row count) | `{"observed_value": 100}` — **no count, no samples** |
| `expect_column_to_exist` | `{}` — **empty** |

Four of the fifteen catalog types LT-2a selected (`expect_column_mean_to_be_between`,
`expect_column_unique_value_count_to_be_between`,
`expect_table_row_count_to_be_between`, `expect_column_to_exist`) can never
carry a violating-row count or an offending value. F13's *"150 orders have a
negative total · 0.006% · #88231 −450.00"* is simply not renderable for them:
the dashboard needs a second presentation — observed value against expected
range — and F9's result model needs both variants.

**2 · The key set is not stable even within `ColumnMapExpectation`.** Two failing
map expectations on the same batch with the same `result_format` return
different fields:

```
failing not_be_null   element_count, unexpected_count, unexpected_percent,
                      partial_unexpected_list, partial_unexpected_counts
failing be_between    ...the same, PLUS missing_count, missing_percent,
                      unexpected_percent_total, unexpected_percent_nonmissing
```

For `not_be_null` the nulls *are* the unexpected values, so the
missing/unexpected split collapses and those four fields vanish. F9 cannot
compute "% of rows scanned" the same way for every rule, and every field must
be read with `.get()`.

Related, and easy to miss: the same value has two types one line apart. A
`numeric(10,2)` column arrives as `decimal.Decimal` on the live `.result` object
and as `float` through `to_json_dict()`. Normalise off `to_json_dict()` —
otherwise `json.dumps` raises and a reflexive `default=str` silently stores
`"-3.50"` as a string.

**3 · `success` is not `unexpected_count == 0`.** With `mostly=0.5` on a column
that is 25% bad, GE reports `success: true` **and** `unexpected_count: 25`.
Pass/fail and violating count are independent readings. F13 must show both, or a
green rule sitting next to 25 bad rows reads as a bug in our product rather than
as the tolerance the rule author asked for.

**4 · A rule that could not run is indistinguishable from one that failed.**
`catch_exceptions` defaults to `True`, so a rule against a non-existent column
does not abort the suite — it lands as `success: false` with `result: {}`,
identical in every visible way to a genuine failure. Only `exception_info`
separates them, and it has two shapes:

```python
# nothing raised
{"raised_exception": False, "exception_traceback": None, "exception_message": None}

# something raised — keyed by MetricConfigurationID string
{"MetricConfigurationID(metric_name='column_values.between.condition', ...)":
     {"raised_exception": True,
      "exception_message": 'Error: The column "no_such_column" in BatchData does not exist.',
      "exception_traceback": "..."}}
```

So: `flat = "raised_exception" in exception_info`, else iterate `.values()`.
Our result model needs a third state — **errored** — and it cannot be folded
into *failed*. A rule that did not run has a coverage meaning, not a
data-quality meaning; reporting it as a failure would tell a domain expert
that data is bad when what is actually bad is the rule.

**And a smaller trap:** the `results` list is not guaranteed to follow
declaration order. It held order for a clean run and **reordered the moment one
expectation errored** — the errored one came back first. Join results to rules
by `expectation_config`, never by index.

### What this settles, and what it does not

Settled: F8's execution path, F9's field-by-field normalisation contract, F13's
access to real offending values with row identifiers, and the mechanism (though
not the value) behind O-2. Together with LT-2a, the whole GE surface the one
GE-importing module needs is now written down.

Not settled: **wall-clock time**. Nothing here is a latency measurement, and the
100-row table says nothing about 500K. O-2's *value* and O-3 (synchronous vs
background) still belong to LT-1b — but LT-1b now knows what to measure, because
the work happens in PostgreSQL and not in our process.

---

## LT-2a · Great Expectations 1.x object model and registry

**Bead** `dq-chf` · **Run** 2026-08-16 · **great-expectations 1.20.0**, Python 3.12.5
**Feeds** SPEC O-1 (catalog composition), F5 (curated catalog and validation),
F7 (compilation), INV-2, INV-3
**Run it:** `uv run --with great-expectations python learning-tests/lt2a_ge_registry.py`

### What was verified

- [x] Installed version is **1.20.0** — a genuine 1.x, so every pre-1.0 memory
      (`ExpectationConfiguration` as the primary object, `DataContext`
      everywhere, `expectation_type` as the wire key) had to be re-derived.
- [x] The registry holds **56** expectation types.
- [x] A **15-type catalog** was selected from that registry and every entry
      confirmed present, with zero multi-column types.
- [x] The object model is **pydantic v1** (`pydantic.v1.main.BaseModel`,
      vendored inside pydantic 2). Introspection is `__fields__` / `.schema()`,
      never `model_fields` / `model_json_schema()`.
- [x] Construction, serialisation, round-trip and suite assembly all work with
      **no `DataContext` at all**.
- [x] A hallucinated expectation type cannot be resolved — the floor under
      INV-2 holds.

### Measured

| | |
|---|---|
| registry types | 56 |
| — `ColumnMapExpectation` (per-row, single column) | 25 |
| — `ColumnAggregateExpectation` (whole-column statistic) | 15 |
| — `BatchExpectation` (table-level) | 10 |
| — `ColumnPairMapExpectation` + `MulticolumnMapExpectation` | 6 (excluded, v2) |
| curated catalog | 15 |
| invalid-rule probes | 25 — GE rejects 15, **accepts 10** |
| `import great_expectations` cold | ~3.2 s |

`great_expectations.expectations` exports 58 capitalised names — the 56
registered types plus the `Expectation` base and `UnexpectedRowsExpectation`
(a raw-SQL escape hatch, out of scope). **Count from the registry, not the
module.**

### The curated catalog (resolves O-1)

Single-column and table-level only. Multi-column is deferred to v2 — the six
excluded types are `expect_column_pair_values_a_to_be_greater_than_b`,
`expect_column_pair_values_to_be_equal`, `expect_column_pair_values_to_be_in_set`,
`expect_compound_columns_to_be_unique`, `expect_multicolumn_sum_to_equal`,
`expect_select_column_values_to_be_unique_within_record`.

| # | Family | Type | Base | GE-required kwargs | `mostly` |
|---|---|---|---|---|---|
| 1 | nulls | `expect_column_values_to_not_be_null` | ColumnMap | `column` | yes |
| 2 | nulls | `expect_column_values_to_be_null` | ColumnMap | `column` | yes |
| 3 | uniqueness | `expect_column_values_to_be_unique` | ColumnMap | `column` | yes |
| 4 | uniqueness | `expect_column_unique_value_count_to_be_between` | ColumnAggregate | `column` | no |
| 5 | value sets | `expect_column_values_to_be_in_set` | ColumnMap | `column`, `value_set` | yes |
| 6 | value sets | `expect_column_values_to_not_be_in_set` | ColumnMap | `column`, `value_set` | yes |
| 7 | ranges | `expect_column_values_to_be_between` | ColumnMap | `column` | yes |
| 8 | ranges | `expect_column_mean_to_be_between` | ColumnAggregate | `column` | no |
| 9 | regex/format | `expect_column_values_to_match_regex` | ColumnMap | `column` | yes |
| 10 | regex/format | `expect_column_values_to_not_match_regex` | ColumnMap | `column`, `regex` | yes |
| 11 | regex/format | `expect_column_value_lengths_to_be_between` | ColumnMap | `column` | yes |
| 12 | type | `expect_column_values_to_be_of_type` | ColumnMap | `column`, `type_` | yes |
| 13 | type | `expect_column_values_to_be_in_type_list` | ColumnMap | `column` | yes |
| 14 | row count | `expect_table_row_count_to_be_between` | Batch | *(none)* | no |
| 15 | column existence | `expect_column_to_exist` | Batch | `column` | no |

Why each earns its slot is recorded inline in `lt2a_ge_registry.py`. The
weakest slot is **#2 `expect_column_values_to_be_null`** — genuine e-commerce
use is rare. If a 16th type is ever wanted, drop it for
`expect_column_proportion_of_non_null_values_to_be_between`, which states a null
budget as a first-class threshold rather than via `mostly=`.

Note the `mostly` column: it exists only on map expectations. "At most 2% of
emails may be null" is expressible; "the mean is mostly in range" is not.

### UNEXPECTED — this is the finding that changes the design

**"Instantiate it against GE before persisting" is a weaker gate than INV-2
assumes.** GE's constructor validation is real, but it is *inconsistent between
expectation types*, and it checks shape, never sense.

GE **accepts** all of the following. Every one is a bad rule:

| Constructed without error | Why it is wrong |
|---|---|
| `values_to_be_between(column="x", min_value=100, max_value=1)` | contradictory bounds |
| `match_regex(column="e", regex="[unclosed")` | regex does not compile |
| `match_regex(column="e")` | no `regex` at all |
| `in_type_list(column="e")` | no `type_list` at all |
| `table_row_count_to_be_between()` | no bounds — vacuously true |
| `mean_to_be_between(column="x")` | no bounds — vacuously true |
| `unique_value_count_to_be_between(column="x")` | no bounds — vacuously true |
| `values_to_be_in_set(column="s", value_set=[])` | can never pass |
| `values_to_be_of_type(column="x", type_="NOT_A_TYPE")` | bogus SQL type name |

The asymmetries are the tell — this is not a coherent validation policy, it is
per-expectation authoring drift:

| | |
|---|---|
| `not_match_regex` without `regex` | **raises** |
| `match_regex` without `regex` | accepted |
| `row_count_to_be_between` with min > max | **raises** |
| `values_to_be_between` with min > max | accepted |
| `values_to_be_between` with neither bound | **raises** (root validator) |
| `mean_to_be_between` with neither bound | accepted |

And `.schema()["required"]` is **not** the source of truth either: it lists only
`['column']` for `values_to_be_between`, yet a root validator rejects
both-bounds-`None`. Required-ness lives in two places and neither is complete —
so the catalog cannot be generated purely from GE introspection.

**Second surprise:**
`ExpectationConfiguration(type="expect_column_values_to_be_vibey", kwargs={...})`
**constructs without error.** A hallucinated type passes straight through the
configuration object; it only raises at `.to_domain_obj()`. If the compiler ever
persists an `ExpectationConfiguration`, INV-2 does not hold at all.

What GE *does* reliably reject, and what we get for free: unknown types (through
the concrete class), missing required kwargs where they are declared,
wrong-typed kwargs, `mostly` outside 0..1, and — usefully for an LLM-authored
rule — **misspelled kwargs** (`min_valu=` → `extra fields not permitted`; the
constructor is strict, so typos cannot slip through as ignored extras).

### Consequences for F5 / F7

1. The validation gate is `get_expectation_impl(type)(**kwargs)` — the concrete
   class — **never** `ExpectationConfiguration`.
2. GE construction is **necessary but not sufficient**. The catalog must carry
   our own per-type required-parameter and sanity table — `min <= max`,
   non-empty `value_set`, `re.compile`-able regex, known SQL type name, at least
   one bound present — and run it *before* handing kwargs to GE. That table is a
   small amount of code and it is the part that actually makes INV-2 true. It is
   also what lets a rejection carry a reason a domain expert can read, which
   pydantic's `ValidationError` text does not.
3. This is the same shape as the LT-2b finding: **the tool confirms the rule is
   well-formed, never that it is meaningful.** LT-2b showed the model produces
   statistically true, business-naive rules; LT-2a shows GE will happily accept
   a rule that is not even statistically meaningful. Two independent
   confirmations that the human review step is load-bearing.

### The API contract for the one module that imports GE (INV-3)

```python
# --- construct -------------------------------------------------------------
from great_expectations.expectations.registry import get_expectation_impl
obj = get_expectation_impl(type_str)(**kwargs)
#   unknown type   -> great_expectations.exceptions.ExpectationNotFoundError
#   bad kwargs     -> pydantic.v1.ValidationError
#   unknown kwarg  -> ValidationError "extra fields not permitted"
# statically, the same classes live at:
import great_expectations.expectations as gxe
gxe.ExpectColumnValuesToBeInSet(column="status", value_set=[...])

# --- introspect ------------------------------------------------------------
cls = get_expectation_impl(type_str)
cls.expectation_type            # -> "expect_column_values_to_be_in_set"
cls.schema()["required"]        # -> declared required kwargs (INCOMPLETE, see above)
cls.__fields__                  # -> pydantic v1 FieldInfo map: .required, .outer_type_
"mostly" in cls.__fields__      # -> True only for map expectations
cls.__mro__[1].__name__         # -> ColumnMapExpectation | ColumnAggregateExpectation
                                #    | BatchExpectation | ColumnPairMapExpectation
                                #    | MulticolumnMapExpectation
                                #    (this is how multi-column is excluded)

# --- serialise -------------------------------------------------------------
obj.configuration.to_json_dict()
# -> {"type": str, "kwargs": {...}, "meta": {}, "severity": "critical"}
# The wire key is "type", NOT "expectation_type" — that is the 1.x rename.
# The instance itself has no .to_json_dict() and no .type attribute.
# obj.dict() works but leaks 10 GE defaults (result_format, catch_exceptions,
# mostly, severity, row_condition, ...). Store OUR spec, not this.

# --- deserialise -----------------------------------------------------------
obj = get_expectation_impl(d["type"])(**d["kwargs"])     # exact round trip
# or ExpectationConfiguration(**d).to_domain_obj()  <- validates only here

# --- suite (F7) ------------------------------------------------------------
import great_expectations as gx
suite = gx.ExpectationSuite(name="orders_suite", expectations=[obj, ...])
suite.to_json_dict()
# Context-free. suite.add_expectation(obj) instead demands an active context
# and raises DataContextRequiredError — do not use it in the compiler.
```

Everything above stays behind that one module: its public surface takes and
returns our own `{type, kwargs}` dicts, so `great_expectations` appears in
exactly one file, as INV-3 requires.

### Out of scope here

Executing a suite against PostgreSQL — that is LT-1a (`dq-dww`), which this
unblocks. Nothing in this test touched a database.

---

## LT-2b · Claude Agent SDK — auth, tool suppression, structured output

**Bead** `dq-uco` · **Run** 2026-08-16 · **claude-agent-sdk 0.1.23**, model `claude-opus-5`

Full findings live in the docstring of `lt2b_agent_sdk.py`. In brief: auth works
from `CLAUDE_CODE_OAUTH_TOKEN` with no API purchase; tools fully suppressed;
`max_turns=1` enforced; structured JSON obtained by instruction alone;
`setting_sources=[]` is required so the developer's own `CLAUDE.md` cannot leak
into a server-side call. Measured 6.6 s wall and $0.041 per call.

The finding that matters: every rule the model proposed was statistically true
and business-naive — it overfit the observed max instead of proposing the actual
business invariant `order_total >= 0`. The meaning is not in the sample.
