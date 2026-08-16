"""
LT-1a — Great Expectations 1.x against real PostgreSQL: does it execute, does
        it count correctly, and what exactly does the Execution Engine have to
        normalise?

WHY THIS EXISTS
    LT-2a (dq-chf) pinned GE's *compile* path — construct, serialise, assemble a
    suite — and never touched a database. Everything downstream of that is still
    assumption. SPEC F8 promises "per-rule pass/fail, the count of violating
    rows, and a sample of the offending values"; F9 promises to normalise GE's
    output into our own result format; F13 promises to render *real offending
    values* to a human. None of those three can be designed until the actual
    shape of an `ExpectationSuiteValidationResult` from a SQL backend is on the
    table, and most material online describes the pre-1.0 `DataContext` /
    `checkpoint` API, which no longer exists in this form.

    The load-bearing unknown is **pushdown**. If GE computes the check inside
    PostgreSQL, LT-1b is measuring query planning and network latency and the
    product can stay synchronous. If GE pulls rows into the client and counts
    them in Python, LT-1b is measuring transfer of 500K rows over a link to
    Singapore and F8/F9/F13 all become a job system. This script answers that
    by watching the SQL actually issued and counting the rows actually returned.

    Scope: correctness only. Timing, direct-vs-pooled and volume are LT-1b's
    job (dq-e1d). This script creates and drops its own 100-row table and never
    reads the 500K seeded demo tables.

FINDINGS — run 2026-08-16, great-expectations 1.20.0, SQLAlchemy 2.0.52,
           psycopg2-binary 2.9.9, Python 3.12.5, PostgreSQL 17.6 (Supabase)

    [x] End to end works. 100-row table, 25 planted negative totals and 7
        planted NULL emails, all three counts reported by GE exactly.

    [x] PUSHDOWN CONFIRMED — this is the finding LT-1b depends on.
        GE compiles each expectation into an aggregate SQL statement and lets
        PostgreSQL do the counting:

            SELECT sum(CASE WHEN (order_total IS NOT NULL AND order_total < 0)
                            THEN 1 ELSE 0 END) AS "column_values.between.unexpected_count",
                   sum(CASE WHEN (order_total IS NULL) THEN 1 ELSE 0 END)
                            AS "column_values.nonnull.unexpected_count"
            FROM (SELECT * FROM public.lt1a_ge_probe WHERE true) AS anon_1

        The only row-returning statement is the sample fetch, and it carries a
        LIMIT equal to `partial_unexpected_count`:

            SELECT order_total AS unexpected_values FROM ... WHERE <predicate>
            LIMIT 20

        Proved two ways, both asserted below: (1) the SQL text is captured off
        SQLAlchemy's `before_cursor_execute` event and inspected; (2) rows
        actually handed to the client are counted off `after_cursor_execute` —
        a whole run over 100 rows returns well under 100 rows to Python.
        => LT-1b should measure round trips and PostgreSQL scan time, not
           transfer. Row count should affect it roughly as a seq scan does.

    [x] A DataContext IS required on the execute path — unlike the compile
        path, which LT-2a showed needs none. `PostgresDatasource(...)`
        constructs and `add_table_asset` works, but `batch_definition.get_batch()`
        raises `MissingDataContextError`. An **ephemeral** context is enough:
        `gx.get_context(mode="ephemeral")` writes nothing to disk
        (`root_directory is None`), so no `gx/` project directory appears in
        the repo and nothing needs to be gitignored.

    [x] The 1.x path to a SQL table is four objects, no YAML, no checkpoint:
            context.data_sources.add_postgres(name, connection_string)
              -> .add_table_asset(name, table_name, schema_name)
              -> .add_batch_definition_whole_table(name)
              -> .get_batch()
              -> .validate(suite | expectation, result_format=...)
        `add_postgres()` eagerly opens a connection (`test_connection()`), so a
        bad DSN fails at registration with `TestConnectionError`, not mid-run.

    [x] Offending sample values are really there: `partial_unexpected_list`,
        default **20** values, and the cap IS configurable — pass
        `result_format={"result_format": "SUMMARY", "partial_unexpected_count": N}`
        and the SQL LIMIT changes to N. `partial_unexpected_counts` gives the
        same values with frequencies.

    [x] For F13's "#88231 -450.00" — the identifier as well as the value —
        `unexpected_index_column_names: ["order_id"]` yields
        `partial_unexpected_index_list: [{"id": 1, "order_total": -3.5}, ...]`,
        still bounded by `partial_unexpected_count`. This is the setting F8
        should use.

    [x] `result_format="COMPLETE"` is a trap on a large table: it drops the
        LIMIT from the sample query entirely and streams every offending row to
        the client. Never use it in the product. It does give
        `unexpected_index_query` — the SQL string that would return the bad
        rows — which is worth surfacing in F13's raw panel without executing.

    [x] Storage for F9 is `json.dumps(result.to_json_dict())` with **no custom
        encoder** — 4.4 KB for a 3-rule run, and `json.loads` round-trips it
        exactly. `to_json_dict()` has already flattened Decimal, the enums and
        the pydantic objects to primitives; `json.dumps` on the live `.result`
        raises `TypeError: Object of type Decimal is not JSON serializable`.

    [x] Sampling / row cap: GE 1.x has **no sampler**. The 0.x
        splitter/sampler API is gone; `great_expectations.core.partitioners`
        offers only *partitioners* (year/month/day, column value, mod/divided
        integer), which slice by a column, not "first N rows". The only honest
        row cap is our own SQL through `data_source.add_query_asset(name, query)`
        — verified: a `SELECT * FROM ... LIMIT 10` asset reports
        `element_count: 10`. That is the knob SPEC O-2 must be written against,
        and because GE's result does NOT record that it was capped, INV-5's
        sampling marker has to be carried by us, from the asset definition.

    MEASURED
        planted negative order_total   25   GE unexpected_count           25
        planted NULL email              7   GE unexpected_count            7
        planted status violations       0   GE unexpected_count            0
        default sample values          20   (of 25 -- the cap is visible)
        rows crossing the wire, whole   58   against 100 rows in the table
          3-expectation run                 -- bounded samples, not the data
        SQL round trips, 1 expectation   3   (row_count, sample, aggregate)
        SQL round trips, 3 expectations  6   sub-linear: the table row_count
                                             metric is computed once per run and
                                             independent aggregates are merged
                                             into a single statement
        ... same 3 with row identifiers 10   unexpected_index_column_names costs
                                             one extra bounded SELECT per rule
                                             and stops row_count being shared

    UNEXPECTED — four things, and every one of them changes F9

    1.  There is no single result shape. GE returns three, by base class:
            ColumnMapExpectation      -> element_count, unexpected_count,
                                         unexpected_percent, partial_unexpected_list, ...
            ColumnAggregateExpectation-> {"observed_value": 461.125}   <- NO count
            BatchExpectation row count-> {"observed_value": 100}       <- NO count
            expect_column_to_exist    -> {}                            <- empty!
        Four of the fifteen catalog types (mean, unique_value_count,
        table_row_count, column_to_exist) can never produce a violating-row
        count or a sample value. F13's "150 orders have a negative total ...
        #88231 -450.00" is simply not renderable for them and the UI needs a
        second presentation: observed value vs expected range.

    2.  The key set is not stable even *within* ColumnMapExpectation. Two
        failing map expectations on the same batch with the same result_format
        return different fields: `expect_column_values_to_not_be_null` has no
        `missing_count`, no `missing_percent` and no
        `unexpected_percent_total` / `_nonmissing`, because for that rule the
        nulls *are* the unexpected values and the split collapses. So F9 cannot
        compute "% of rows scanned" the same way for every rule, and every
        field must be read with `.get()`, never `[...]`.

        Related: the same value has two types one line apart. A `numeric(10,2)`
        column arrives as `decimal.Decimal` on the live `result` object and as
        `float` through `to_json_dict()`. Normalise off `to_json_dict()` —
        otherwise `json.dumps` raises `TypeError` on the Decimal and a reflexive
        `default=str` silently stores `"-3.50"` as a string.

    3.  `success` is NOT `unexpected_count == 0`. With `mostly=0.5` on a column
        that is 25% bad, GE reports `success: true` *and*
        `unexpected_count: 25`. Pass/fail and violating count are independent
        readings and F13 must show both, or a green rule with 25 bad rows reads
        as a bug in our product.

    4.  `catch_exceptions` defaults to **True**, so a rule that cannot run at
        all — wrong column name, say — does not abort the suite. It lands as
        `success: false` with `result: {}`, indistinguishable from a genuine
        failure unless `exception_info` is read. And `exception_info` has two
        shapes: flat `{raised_exception, exception_traceback, exception_message}`
        when nothing raised, and a dict keyed by *MetricConfigurationID string*
        holding one such triple per failed metric when something did. A third
        state — "errored" — is therefore mandatory in our result model; it
        cannot be folded into "failed".

    And one smaller trap: the `results` list is not guaranteed to be in the
    order the expectations were declared in the suite — observed reordering
    the moment one of them errors (the errored one came back first). Join
    results back to rules by `expectation_config`, never by index.

RUN
    cp ../.env .env   # .env is gitignored and not in a fresh worktree
    uv run --with great-expectations --with 'sqlalchemy>=2' --with psycopg2-binary \
        python learning-tests/lt1a_ge_postgres.py

    The driver matters. `postgresql://` with no suffix resolves to psycopg2 —
    verified: with only psycopg v3 installed the datasource fails at
    registration with ModuleNotFoundError: No module named 'psycopg2'. Both
    drivers work when named explicitly (`postgresql+psycopg2://`,
    `postgresql+psycopg://`); this script normalises to psycopg2, which is what
    `great-expectations[postgresql]` itself pulls in.
"""

import json
import os
import pathlib

import sqlalchemy as sa

# --- env -------------------------------------------------------------------

for line in pathlib.Path(".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

RAW_URL = os.environ.get("SUPABASE_DB_URL_DIRECT")
assert RAW_URL, "SUPABASE_DB_URL_DIRECT not in .env"

# A bare postgresql:// URL means psycopg2 to SQLAlchemy. Say so out loud rather
# than depending on the default -- see the driver note in the docstring.
URL = RAW_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

TABLE = "lt1a_ge_probe"
SCHEMA = "public"

# --- the planted defects: ground truth, counted by us, not by GE -------------
# 100 rows. Every count below is exact and the defect classes are disjoint.

ROWS = 100
NEGATIVE_TOTALS = 25        # order_total < 0        -> failing rule, 25 rows
NULL_EMAILS = 7             # email IS NULL          -> failing rule, 7 rows
STATUS_VOCAB = ["shipped", "pending", "cancelled", "returned"]
# status is deliberately clean -> the passing rule.

RULE = "=" * 78


def banner(n, title):
    print()
    print(RULE)
    print(f"{n}. {title}")
    print(RULE)


def rows():
    out = []
    for i in range(1, ROWS + 1):
        total = -(i * 3.5) if i <= NEGATIVE_TOTALS else i * 10.0
        email = None if NEGATIVE_TOTALS < i <= NEGATIVE_TOTALS + NULL_EMAILS \
            else f"customer{i}@example.com"
        out.append({
            "order_id": i,
            "order_total": round(total, 2),
            "status": STATUS_VOCAB[i % len(STATUS_VOCAB)],
            "email": email,
        })
    return out


engine = sa.create_engine(URL)


def build_table():
    with engine.begin() as c:
        c.execute(sa.text(f"DROP TABLE IF EXISTS {SCHEMA}.{TABLE}"))
        c.execute(sa.text(f"""
            CREATE TABLE {SCHEMA}.{TABLE} (
                order_id    integer PRIMARY KEY,
                order_total numeric(10,2) NOT NULL,
                status      text NOT NULL,
                email       text
            )
        """))
        c.execute(
            sa.text(f"INSERT INTO {SCHEMA}.{TABLE} (order_id, order_total, status, email) "
                    f"VALUES (:order_id, :order_total, :status, :email)"),
            rows(),
        )


def drop_table():
    with engine.begin() as c:
        c.execute(sa.text(f"DROP TABLE IF EXISTS {SCHEMA}.{TABLE}"))


def ground_truth():
    """Count the defects with plain SQL. GE is then measured against this, not
    against the generator's constants -- otherwise the test only proves that
    two copies of the same number agree."""
    with engine.connect() as c:
        n_rows = c.execute(sa.text(f"SELECT count(*) FROM {SCHEMA}.{TABLE}")).scalar()
        n_neg = c.execute(sa.text(
            f"SELECT count(*) FROM {SCHEMA}.{TABLE} WHERE order_total < 0")).scalar()
        n_null = c.execute(sa.text(
            f"SELECT count(*) FROM {SCHEMA}.{TABLE} WHERE email IS NULL")).scalar()
        n_status = c.execute(sa.text(
            f"SELECT count(*) FROM {SCHEMA}.{TABLE} "
            f"WHERE NOT (status = ANY(:vocab))"), {"vocab": STATUS_VOCAB}).scalar()
        version = c.execute(sa.text("SELECT version()")).scalar()
    return n_rows, n_neg, n_null, n_status, version


# --- SQL tap: everything GE sends, and every row it gets back ---------------

SQL_LOG = []            # (statement, params)
ROWS_RETURNED = [0]     # rows actually handed to the client
_TAP_ON = [False]


@sa.event.listens_for(sa.engine.Engine, "before_cursor_execute")
def _before(conn, cursor, statement, parameters, context, executemany):
    if _TAP_ON[0] and "pg_catalog" not in statement:
        SQL_LOG.append((" ".join(statement.split()), parameters))


@sa.event.listens_for(sa.engine.Engine, "after_cursor_execute")
def _after(conn, cursor, statement, parameters, context, executemany):
    if _TAP_ON[0] and "pg_catalog" not in statement and cursor.rowcount and cursor.rowcount > 0:
        ROWS_RETURNED[0] += cursor.rowcount


def tap():
    """Start recording; forget whatever the previous section recorded."""
    SQL_LOG.clear()
    ROWS_RETURNED[0] = 0
    _TAP_ON[0] = True


def untap():
    """Stop recording, keep what was recorded."""
    _TAP_ON[0] = False


try:
    # -----------------------------------------------------------------------
    banner(1, "REAL POSTGRESQL, OUR OWN SMALL TABLE")
    # -----------------------------------------------------------------------

    build_table()
    n_rows, n_neg, n_null, n_status, version = ground_truth()
    print(version.split(" on ")[0])
    print(f"table {SCHEMA}.{TABLE} built: {n_rows} rows")
    print(f"  planted  order_total < 0        {n_neg}")
    print(f"  planted  email IS NULL          {n_null}")
    print(f"  planted  status outside vocab   {n_status}   (clean on purpose)")

    assert (n_rows, n_neg, n_null, n_status) == (ROWS, NEGATIVE_TOTALS, NULL_EMAILS, 0), \
        "the table on disk does not match the intended plant"

    # -----------------------------------------------------------------------
    banner(2, "HOW GE 1.x IS POINTED AT A SQL TABLE")
    # -----------------------------------------------------------------------

    import great_expectations as gx
    import great_expectations.expectations as gxe
    from great_expectations.data_context.types.base import ProgressBarsConfig
    from great_expectations.datasource.fluent import PostgresDatasource
    from great_expectations.exceptions.exceptions import MissingDataContextError

    print(f"great_expectations {gx.__version__} | SQLAlchemy {sa.__version__}")

    # Does the execute path need a DataContext? LT-2a proved the compile path
    # does not. Find out before assuming either way.
    ctxless_asset = PostgresDatasource(name="ctxless", connection_string=URL) \
        .add_table_asset(name="a", table_name=TABLE, schema_name=SCHEMA)
    ctxless_bd = ctxless_asset.add_batch_definition_whole_table(name="w")
    try:
        ctxless_bd.get_batch()
        raise AssertionError("get_batch() worked with no DataContext -- re-check §2")
    except MissingDataContextError as e:
        print(f"no-context get_batch() -> MissingDataContextError({e})")
    print("=> the EXECUTE path needs a DataContext; the compile path (LT-2a) does not.")

    context = gx.get_context(mode="ephemeral")
    context.variables.progress_bars = ProgressBarsConfig(globally=False)
    print(f"\ncontext          {type(context).__name__}  "
          f"root_directory={getattr(context, 'root_directory', None)}")
    assert getattr(context, "root_directory", None) is None, \
        "the ephemeral context grew a project directory -- it would need gitignoring"

    data_source = context.data_sources.add_postgres(name="supabase", connection_string=URL)
    asset = data_source.add_table_asset(name="probe", table_name=TABLE, schema_name=SCHEMA)
    batch_definition = asset.add_batch_definition_whole_table(name="whole_table")
    batch = batch_definition.get_batch()
    for label, obj in [("data_source", data_source), ("asset", asset),
                       ("batch_definition", batch_definition), ("batch", batch)]:
        print(f"{label:16} {type(obj).__name__}")
    print("\ncontext.data_sources.add_postgres(name, connection_string)"
          "\n  .add_table_asset(name, table_name, schema_name)"
          "\n  .add_batch_definition_whole_table(name)"
          "\n  .get_batch()  ->  .validate(suite, result_format=...)")
    print("No YAML, no great_expectations.yml, no Checkpoint. add_postgres() "
          "connects eagerly,\nso a bad DSN raises TestConnectionError here rather "
          "than mid-run.")

    # -----------------------------------------------------------------------
    banner(3, "A SUITE WITH ONE PASSING AND TWO FAILING EXPECTATIONS")
    # -----------------------------------------------------------------------

    passing = gxe.ExpectColumnValuesToBeInSet(column="status", value_set=STATUS_VOCAB)
    failing_total = gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=0)
    failing_email = gxe.ExpectColumnValuesToNotBeNull(column="email")

    suite = gx.ExpectationSuite(
        name=f"{TABLE}_suite",
        expectations=[passing, failing_total, failing_email],
    )

    tap()
    result = batch.validate(
        suite,
        result_format={
            "result_format": "SUMMARY",
            "unexpected_index_column_names": ["order_id"],
        },
    )
    untap()

    print(f"result object     {type(result).__module__}.{type(result).__name__}")
    print(f"result.success    {result.success}")
    print(f"result.statistics {result.statistics}")
    assert result.success is False, "the suite must fail -- two rules are violated"
    assert result.statistics["evaluated_expectations"] == 3
    assert result.statistics["successful_expectations"] == 1
    assert result.statistics["unsuccessful_expectations"] == 2

    # Declaration order is not guaranteed -- §8(d) shows it breaking. Index by
    # expectation_config, never by position.
    by_type = {r.expectation_config.type: r for r in result.results}
    declared = [e.expectation_type for e in suite.expectations]
    returned = [r.expectation_config.type for r in result.results]
    print("\ndeclared order:", declared)
    print("results  order:", returned,
          "  <- same here; NOT guaranteed, see §8(d)" if declared == returned else "  <- REORDERED")
    assert len(by_type) == 3

    r_status = by_type["expect_column_values_to_be_in_set"]
    r_total = by_type["expect_column_values_to_be_between"]
    r_email = by_type["expect_column_values_to_not_be_null"]

    print()
    for label, r in [("status in set   ", r_status),
                     ("order_total >= 0", r_total),
                     ("email not null  ", r_email)]:
        print(f"{label}  success={str(r.success):5}  "
              f"unexpected_count={r.result.get('unexpected_count')}")

    # (1) the run completed, (2) the counts match the plant EXACTLY.
    assert r_status.success is True, "the clean rule must pass"
    assert r_status.result["unexpected_count"] == 0

    assert r_total.success is False
    assert r_total.result["unexpected_count"] == n_neg == NEGATIVE_TOTALS, \
        f"GE says {r_total.result['unexpected_count']} negative totals, SQL says {n_neg}"

    assert r_email.success is False
    assert r_email.result["unexpected_count"] == n_null == NULL_EMAILS, \
        f"GE says {r_email.result['unexpected_count']} null emails, SQL says {n_null}"

    print(f"\n=> GE's counts equal the SQL ground truth exactly "
          f"({NEGATIVE_TOTALS} and {NULL_EMAILS}).")

    # -----------------------------------------------------------------------
    banner(4, "PUSHDOWN OR PULL? — the finding LT-1b depends on")
    # -----------------------------------------------------------------------

    aggregates = [s for s, _ in SQL_LOG if "sum(CASE WHEN" in s or "unexpected_count" in s]
    samples = [(s, p) for s, p in SQL_LOG if "AS unexpected_values" in s]
    row_counts = [s for s, _ in SQL_LOG if 'AS "table.row_count"' in s]

    print(f"statements issued for the 3-expectation run: {len(SQL_LOG)}")
    for s, p in SQL_LOG:
        print(f"  - {s[:120]}{'...' if len(s) > 120 else ''}")

    assert row_counts, "no count(*) issued -- element_count came from somewhere else"
    assert aggregates, "no aggregate SQL: GE may be counting in Python"
    print(f"\nrow_count statements {len(row_counts)}  "
          f"aggregate {len(aggregates)}  sample {len(samples)}")

    # Proof 1 — the counting happens in SQL.
    counted_in_sql = [s for s in aggregates if "sum(CASE WHEN" in s]
    assert counted_in_sql, "expected sum(CASE WHEN ...) aggregates"
    print("\nthe violating count is computed by PostgreSQL:")
    print("  " + counted_in_sql[0][:300])

    # Proof 2 — no statement selects rows without a bound.
    def limit_of(statement, params):
        """The bound value actually sent, resolved through the bind parameter."""
        marker = statement.upper().rfind("LIMIT ")
        if marker < 0:
            return None
        name = statement[marker + 6:].strip().strip("%()s ")
        return params.get(name)

    row_returning = [(s, p) for s, p in SQL_LOG if s.upper().startswith("SELECT")
                     and "sum(CASE WHEN" not in s and "count(*)" not in s]
    unbounded = [s for s, _ in row_returning if "LIMIT" not in s.upper()]
    assert not unbounded, f"an unbounded row fetch was issued: {unbounded}"
    print("\nevery row-returning statement carries a LIMIT:")
    for s, p in row_returning:
        print(f"  LIMIT {limit_of(s, p)}  <- {s[:105]}...")
    assert all(limit_of(s, p) == 20 for s, p in row_returning), \
        "the pushed-down LIMIT is no longer the default 20"

    # Proof 3 — count what actually crossed the wire.
    print(f"\nrows returned to the client across the whole run: {ROWS_RETURNED[0]}")
    print(f"rows in the table:                                 {n_rows}")
    assert ROWS_RETURNED[0] < n_rows, \
        "the client received as many rows as the table holds -- that is a pull, not pushdown"
    print("=> PUSHDOWN. GE sends aggregates to PostgreSQL and pulls back only a "
          "bounded sample.\n   LT-1b is measuring scan time and round trips, not "
          "row transfer.")

    # Round-trip growth, since that is what LT-1b will actually be timing.
    tap()
    batch.validate(gx.ExpectationSuite(name="one", expectations=[
        gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=0)]))
    n_one = len(SQL_LOG)
    tap()
    batch.validate(gx.ExpectationSuite(name="three", expectations=[
        gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=0),
        gxe.ExpectColumnValuesToNotBeNull(column="email"),
        gxe.ExpectColumnValuesToBeUnique(column="order_id")]))
    n_three = len(SQL_LOG)
    untap()
    n_three_indexed = len(row_returning) + len(aggregates) + len(row_counts)
    print(f"""
SQL round trips, plain SUMMARY:  1 expectation -> {n_one},  3 expectations -> {n_three}
  Sub-linear: the table row_count is computed once and independent aggregates
  are merged into one statement.
SQL round trips with unexpected_index_column_names: 3 expectations -> {n_three_indexed}
  Asking for row identifiers costs one extra bounded SELECT per expectation,
  and the row_count metric stops being shared. Worth it for F13, but LT-1b
  should time both -- it is the difference between ~2 and ~3.3 statements per
  rule, all of them against the same table.""")
    assert n_three < 3 * n_one, "round trips grow linearly -- LT-1b should say so"
    assert n_three_indexed > n_three, "the identity fetch is free now -- recheck"

    # -----------------------------------------------------------------------
    banner(5, "THE RESULT SHAPE F9 MUST NORMALISE")
    # -----------------------------------------------------------------------

    print("ExpectationSuiteValidationResult")
    print(f"  top-level keys      {sorted(result.to_json_dict().keys())}")
    print(f"  .success            bool  -> {result.success}")
    print(f"  .statistics         {sorted(result.statistics)}")
    print(f"  .results            list[ExpectationValidationResult], "
          f"{len(result.results)} entries, order NOT guaranteed")
    print(f"  .meta               {sorted(result.meta)}")
    print(f"  .meta['batch_spec'] {result.meta['batch_spec']}")

    one = r_total.to_json_dict()
    print("\nExpectationValidationResult (the failing order_total rule)")
    print(f"  keys                {sorted(one.keys())}")
    print(f"  ['success']         {one['success']}")
    print(f"  ['expectation_config']['type']   {one['expectation_config']['type']}")
    print(f"  ['expectation_config']['kwargs'] {one['expectation_config']['kwargs']}")
    print("  ['result'] =   (lists clipped to 3 for legibility)")
    clipped = {k: (v[:3] + ["...%d more" % (len(v) - 3)] if isinstance(v, list) and len(v) > 3 else v)
               for k, v in one["result"].items()}
    print(json.dumps(clipped, indent=4, default=str))

    # The field paths F9 depends on, asserted so they cannot drift silently.
    res = one["result"]
    assert res["element_count"] == n_rows                     # rows scanned
    assert res["unexpected_count"] == NEGATIVE_TOTALS         # violating rows
    assert res["unexpected_percent"] == 25.0                  # proportion, 0-100 not 0-1
    assert res["missing_count"] == 0                          # NULLs, excluded from the check
    assert "partial_unexpected_list" in res                   # the sample values
    assert "partial_unexpected_counts" in res                 # values + frequencies
    assert one["exception_info"]["raised_exception"] is False

    print("""
F9 reads, per expectation:
    pass/fail        r["success"]                      (NOT unexpected_count == 0 -- see §8)
    rule identity    r["expectation_config"]["type"] + ["kwargs"]
    rows scanned     r["result"]["element_count"]
    violating rows   r["result"]["unexpected_count"]
    proportion       r["result"]["unexpected_percent"]        0-100, of non-missing
                     r["result"]["unexpected_percent_total"]  0-100, of element_count
    nulls skipped    r["result"]["missing_count"] / ["missing_percent"]
    sample values    r["result"]["partial_unexpected_list"]          <= partial_unexpected_count
    with frequency   r["result"]["partial_unexpected_counts"]        [{"value":..,"count":..}]
    with identity    r["result"]["partial_unexpected_index_list"]    [{"order_id":..,"col":..}]
    errored?         r["exception_info"]                      (two shapes -- see §8)
and, per run:
    overall          result.success, result.statistics
    provenance       result.meta["batch_spec"], result.meta["great_expectations_version"]
Every one of these is read with .get() -- the key set varies (§8).""")

    # No encoder argument at all -- to_json_dict() has already flattened
    # Decimal, ResultFormat and the pydantic objects to JSON primitives.
    raw = json.dumps(result.to_json_dict())
    assert json.loads(raw)["suite_name"] == suite.name
    assert json.loads(raw) == result.to_json_dict(), "the round trip is not exact"
    print(f"\nstorage: json.dumps(result.to_json_dict()) -> {len(raw)} chars of plain "
          f"JSON,\n  with NO custom encoder -- to_json_dict() has already flattened "
          f"Decimal and the\n  pydantic objects to primitives, and json.loads round-trips "
          f"it exactly.\n  That is F9's 'raw framework output retained separately'. Note "
          f"json.dumps on the\n  live result object instead raises TypeError on the "
          f"Decimal -- see §8(b2).")
    try:
        json.dumps(r_total.result)
        raise AssertionError("the live result object is JSON-serialisable now")
    except TypeError as e:
        print(f"  json.dumps(r.result) -> TypeError: {e}")

    # -----------------------------------------------------------------------
    banner(6, "OFFENDING SAMPLE VALUES — how many, and can we get more?")
    # -----------------------------------------------------------------------

    default_sample = r_total.result["partial_unexpected_list"]
    print(f"default partial_unexpected_list: {len(default_sample)} of "
          f"{NEGATIVE_TOTALS} violating rows")
    print(f"  {default_sample}")
    assert len(default_sample) == 20, \
        f"the default sample cap is no longer 20, it is {len(default_sample)}"
    assert all(v < 0 for v in default_sample), "these are supposed to be the real bad values"
    assert set(default_sample) <= {round(-(i * 3.5), 2) for i in range(1, NEGATIVE_TOTALS + 1)}, \
        "the sampled values are not the values actually in the table"

    print(f"\npartial_unexpected_counts (value + frequency): "
          f"{r_total.result['partial_unexpected_counts'][:3]} ...")

    idx = r_total.result.get("partial_unexpected_index_list")
    print(f"\npartial_unexpected_index_list (F13's '#88231 -450.00'): {idx[:3]} ...")
    assert idx and idx[0] == {"order_id": 1, "order_total": -3.5}, \
        "unexpected_index_column_names no longer returns real row identifiers"
    print("  -> obtained by passing unexpected_index_column_names=['order_id'];"
          "\n     still bounded by partial_unexpected_count, so it stays cheap.")

    tap()
    wide = batch.validate(failing_total, result_format={
        "result_format": "SUMMARY", "partial_unexpected_count": 25})
    untap()
    limits = [list(p.values())[-1] for s, p in SQL_LOG if "AS unexpected_values" in s]
    print(f"\npartial_unexpected_count=25 -> {len(wide.result['partial_unexpected_list'])} "
          f"values, SQL LIMIT {limits}")
    assert len(wide.result["partial_unexpected_list"]) == NEGATIVE_TOTALS
    assert 25 in limits, "partial_unexpected_count no longer drives the SQL LIMIT"
    print("=> the cap is a real, pushed-down LIMIT. Configurable, and cheap to raise.")

    tap()
    complete = batch.validate(failing_total, result_format="COMPLETE")
    untap()
    unbounded = [s for s, _ in SQL_LOG
                 if "AS unexpected_values" in s and "LIMIT" not in s.upper()]
    print(f"\nresult_format='COMPLETE' -> unexpected_list has "
          f"{len(complete.result['unexpected_list'])} values (all of them)")
    assert unbounded, "COMPLETE now bounds the fetch -- re-check whether it is still a trap"
    print("  and the LIMIT is GONE from the SQL:")
    print("  " + unbounded[0][:150])
    print("  => COMPLETE streams every offending row to the client. On the 500K "
          "table that is\n     a pull, not a pushdown. Do not use it in the product.")
    print(f"\nCOMPLETE does give unexpected_index_query -- SQL we can show without running:"
          f"\n  {str(complete.result.get('unexpected_index_query'))[:160]}")

    # -----------------------------------------------------------------------
    banner(7, "SAMPLING / ROW CAP — what the knob actually is (SPEC O-2, INV-5)")
    # -----------------------------------------------------------------------

    import great_expectations.core.partitioners as partitioners
    available = [n for n in dir(partitioners) if n.startswith(("Partitioner", "Column"))]
    print(f"great_expectations.core.partitioners offers: {available}")
    print("All of these slice by a COLUMN (a date part, a value, a modulus). None "
          "of them is\n'first N rows'. The 0.x splitter/sampler API is gone:")
    for gone in ["add_sampler", "add_splitter", "sampling_method"]:
        assert not hasattr(asset, gone), f"{gone} exists after all -- re-check"
        print(f"  asset.{gone}  absent")

    capped = data_source.add_query_asset(
        name="capped", query=f"SELECT * FROM {SCHEMA}.{TABLE} LIMIT 10")
    capped_batch = capped.add_batch_definition_whole_table(name="w").get_batch()
    capped_result = capped_batch.validate(failing_total)
    print(f"\nadd_query_asset('SELECT * FROM {TABLE} LIMIT 10'):"
          f"\n  element_count    {capped_result.result['element_count']}"
          f"\n  unexpected_count {capped_result.result['unexpected_count']} "
          f"(vs {NEGATIVE_TOTALS} on the whole table)")
    assert capped_result.result["element_count"] == 10
    assert capped_result.result["unexpected_count"] == 10
    print("""
=> The only row cap is our own SQL, through add_query_asset. That is what SPEC
   O-2 must be written against. And note what the result does NOT say: nothing
   in element_count, unexpected_count or meta records that this batch was
   capped -- the capped run looks exactly like an honest run over a 10-row
   table. INV-5's sampling marker cannot be recovered from GE's output; it has
   to be carried by us, from the asset definition, into the stored result.""")

    # -----------------------------------------------------------------------
    banner(8, "THE FOUR THINGS THAT CHANGE F9")
    # -----------------------------------------------------------------------

    print("(a) three different result shapes, by expectation base class\n")
    shapes = [
        ("ColumnMap    values_to_be_between",
         gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=0)),
        ("ColumnAgg    mean_to_be_between",
         gxe.ExpectColumnMeanToBeBetween(column="order_total", min_value=0, max_value=10)),
        ("ColumnAgg    unique_value_count",
         gxe.ExpectColumnUniqueValueCountToBeBetween(column="status", min_value=1, max_value=2)),
        ("Batch        table_row_count",
         gxe.ExpectTableRowCountToBeBetween(min_value=1, max_value=5)),
        ("Batch        column_to_exist",
         gxe.ExpectColumnToExist(column="not_a_column")),
    ]
    for label, e in shapes:
        d = batch.validate(e).to_json_dict()
        print(f"  {label:36} success={str(d['success']):5} "
              f"result={json.dumps(d['result'], default=str)[:88]}")

    agg = batch.validate(
        gxe.ExpectColumnMeanToBeBetween(column="order_total", min_value=0, max_value=10))
    assert "unexpected_count" not in agg.result and "observed_value" in agg.result, \
        "aggregate expectations now report a violating count -- F9 can simplify"
    exists = batch.validate(gxe.ExpectColumnToExist(column="not_a_column"))
    assert exists.result == {}, "column_to_exist now returns a body"
    print("""
    4 of the 15 catalog types (mean, unique_value_count, table_row_count,
    column_to_exist) can never carry a violating-row count or a sample value.
    F13 needs a second rendering for them: observed value vs expected range.
""")

    print("(b) the key set is not stable even within ColumnMap\n")
    # Same batch, same default result_format, both failing -- only the type differs.
    failing_null = batch.validate(gxe.ExpectColumnValuesToNotBeNull(column="email"))
    failing_between = batch.validate(
        gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=0))
    print(f"  failing not_be_null   keys: {sorted(failing_null.result)}")
    print(f"  failing be_between    keys: {sorted(failing_between.result)}")
    missing_from_null = sorted(set(failing_between.result) - set(failing_null.result))
    print(f"  present on one, absent on the other: {missing_from_null}")
    assert missing_from_null == ["missing_count", "missing_percent",
                                 "unexpected_percent_nonmissing",
                                 "unexpected_percent_total"], \
        f"the key sets have shifted: {missing_from_null}"
    assert "unexpected_percent_total" not in failing_null.result
    print("""  -> both are ColumnMapExpectations, both failed, and they do not carry
     the same fields. not_be_null has no missing_count, no missing_percent and
     no unexpected_percent_total/_nonmissing -- for it, the nulls ARE the
     unexpected values, so the missing/unexpected split collapses. F9 therefore
     cannot compute "% of rows scanned" the same way for every rule, and every
     field must be read with .get().
""")

    print("(b2) the live object and to_json_dict() do not hold the same types\n")
    live_types = {type(v).__name__ for v in r_total.result["partial_unexpected_list"]}
    wire_types = {type(v).__name__
                  for v in r_total.to_json_dict()["result"]["partial_unexpected_list"]}
    print(f"  r.result['partial_unexpected_list']               -> {live_types}")
    print(f"  r.to_json_dict()['result'][...]                   -> {wire_types}")
    assert live_types == {"Decimal"}, f"numeric samples are now {live_types}"
    assert wire_types == {"float"}, f"to_json_dict now yields {wire_types}"
    print("""  -> a numeric(10,2) column arrives as decimal.Decimal on the live result
     object, and to_json_dict() coerces it to float. So F9 must normalise off
     to_json_dict(), not off .result -- otherwise json.dumps raises TypeError
     on a Decimal and default=str silently turns "-3.50" into a string in the
     stored output. Two different renderings of the same value, one line apart.
""")

    print("(c) success is NOT unexpected_count == 0\n")
    lenient = batch.validate(
        gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=0, mostly=0.5))
    print(f"  mostly=0.5 on a 25%-bad column -> success={lenient.success}, "
          f"unexpected_count={lenient.result['unexpected_count']}")
    assert lenient.success is True and lenient.result["unexpected_count"] == NEGATIVE_TOTALS
    print("  -> pass/fail and violating count are independent readings. F13 shows "
          "both, or a\n     green rule with 25 bad rows looks like our bug.\n")

    print("(d) a rule that cannot run is not distinguishable from one that failed\n")
    print(f"  catch_exceptions default: {failing_total.catch_exceptions}   "
          f"expectation result_format default: {failing_total.result_format}")
    broken_suite = gx.ExpectationSuite(name="broken", expectations=[
        gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=0),
        gxe.ExpectColumnValuesToBeBetween(column="no_such_column", min_value=0),
    ])
    broken = batch.validate(broken_suite)
    for r in broken.results:
        col = r.expectation_config.kwargs.get("column")
        info = r.exception_info
        flat = "raised_exception" in info
        raised = info["raised_exception"] if flat else any(
            v["raised_exception"] for v in info.values())
        msg = info["exception_message"] if flat else \
            next(iter(info.values()))["exception_message"]
        print(f"  column={col:16} success={str(r.success):5} "
              f"result={json.dumps(r.result, default=str)[:60]}... "
              f"exception_info={'flat' if flat else 'keyed by MetricConfigurationID'} "
              f"raised={raised}")
        if col == "no_such_column":
            assert r.success is False and r.result == {} and raised is True
            assert not flat, "exception_info is flat on a raise now -- one shape, good news"
            print(f"      message: {msg}")
        else:
            assert flat and raised is False
    print("""
    Both rows read success=false. Only exception_info separates "150 rows are
    bad" from "this rule never ran". Our result model needs a third state,
    errored, and it cannot be folded into failed -- a rule that did not run has
    a coverage meaning, not a data-quality meaning.
""")

    broken_declared = [e.column for e in broken_suite.expectations]
    broken_returned = [r.expectation_config.kwargs["column"] for r in broken.results]
    print(f"  and, in the same run:  declared {broken_declared}")
    print(f"                         returned {broken_returned}")
    assert broken_declared != broken_returned, \
        "the reorder did not happen this time -- the join-by-index trap may be gone"
    print("""  -> the errored expectation came back FIRST. The results list is not
     in declaration order. Join results to rules by expectation_config,
     never by index.""")

    # -----------------------------------------------------------------------
    banner(9, "DRIVERS")
    # -----------------------------------------------------------------------

    print(f"connection string given to GE: postgresql+psycopg2://... "
          f"(from SUPABASE_DB_URL_DIRECT, port 5432)")
    print(f"dialect actually in use:       "
          f"{batch.data.execution_engine.engine.dialect.driver}")
    try:
        import psycopg  # noqa: F401
        ds3 = context.data_sources.add_postgres(
            name="pg_v3",
            connection_string=RAW_URL.replace("postgresql://", "postgresql+psycopg://", 1))
        b3 = ds3.add_table_asset(name="p3", table_name=TABLE, schema_name=SCHEMA) \
                .add_batch_definition_whole_table(name="w").get_batch()
        r3 = b3.validate(failing_total)
        print(f"postgresql+psycopg:// (v3)     works, unexpected_count="
              f"{r3.result['unexpected_count']}")
        assert r3.result["unexpected_count"] == NEGATIVE_TOTALS
    except ImportError:
        print("postgresql+psycopg:// (v3)     not installed here; psycopg2 is the "
              "one great-expectations[postgresql] pulls in")
    print("A bare postgresql:// URL resolves to psycopg2 and fails at "
          "add_postgres() with\nModuleNotFoundError if only psycopg v3 is installed. "
          "Name the driver explicitly.")

    print()
    print(RULE)
    print("ALL ASSERTIONS PASSED")
    print(RULE)

finally:
    _TAP_ON[0] = False
    drop_table()
    engine.dispose()
    print(f"\ncleaned up: {SCHEMA}.{TABLE} dropped. The seeded orders/customers/"
          "payments tables were never touched.")
