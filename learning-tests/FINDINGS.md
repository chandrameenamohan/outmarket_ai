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
| LT-2a | Great Expectations 1.x — object model and registry | passed | `lt2a_ge_registry.py` |
| LT-2b | Claude Agent SDK — auth, tool suppression, structured output | passed | `lt2b_agent_sdk.py` |

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
