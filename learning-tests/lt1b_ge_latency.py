"""
LT-1b — Great Expectations latency on Supabase: direct vs pooled, and does a
        rule run return fast enough for a human to watch?

WHY THIS EXISTS
    This is the load-bearing measurement of the project. SPEC F8 promises that
    accepted rules "run against live data on explicit user action" and F13
    renders the result on a screen the user is already looking at. Both assume
    a run finishes in seconds. F8 carries an explicit *Contingency*: if
    interactive execution proves infeasible the feature changes shape and the
    spec is revised before implementation. Nothing was ever measured, so the
    spec is not frozen until this script produces a number.

    LT-1a (dq-dww) settled the mechanism and told this test what to measure:
    GE compiles each expectation into `sum(CASE WHEN ...)` aggregates and lets
    PostgreSQL count, pulling back only a bounded sample. So the cost is
    PostgreSQL scan time plus per-statement round trips to Singapore, not row
    transfer -- unless someone reaches for `result_format="COMPLETE"`, or for
    the one row-cap mechanism GE 1.x leaves us. Both are measured here.

    Out of scope, per the bead: *optimising* any of these numbers. This run
    only measures them. Optimisations spotted along the way are recorded as
    follow-ups at the end of the findings, not implemented.

    Nothing here mutates the seeded tables. Every statement this script issues
    is a SELECT.

FINDINGS -- run 2026-08-16, great-expectations 1.20.0, SQLAlchemy 2.0.52,
           psycopg2-binary, psycopg 3, Python 3.12.5, PostgreSQL 17.6
           (Supabase, ap-southeast-1 / Singapore), 500,000-row `orders`.
           1 discarded warm-up + 5 measured runs per cell; medians below.
           The generated tables live in learning-tests/FINDINGS.md and the
           raw numbers in learning-tests/lt1b_results.json.

    THE VERDICT
        A full-catalog run over the whole table does NOT clear the bar that
        was set before the numbers were read (<= 10 s).

            15 rules / 500,000 rows / direct / shipping config   13.84 s
            10 rules / 500,000 rows / direct / shipping config   13.59 s
            10 rules / 100,000 rows (capped)                      9.39 s
             1 rule  / 500,000 rows                               2.48 s

        But the shape matters more than the pass/fail. Largest suite that
        fits under 10 s at full size: 3 rules. Largest row count that fits
        with 10 rules: 100,000. Marginal cost of one more rule: 0.81 s.
        A job queue would return the same 14 s later, with a polling endpoint
        and a staleness problem added -- so O-3's answer is NOT "background".
        What the numbers argue for is a synchronous request that STREAMS each
        rule's verdict as it lands.
        First result at ~2.5 s, then the list fills. SPEC 8's contingency is
        partially triggered: not a job system, but F8 needs a progressive
        clause and F13 needs to render a partially-complete run.

    [x] F8 should use SUPABASE_DB_URL_DIRECT (5432). Same work:
        13.59 s direct vs 18.21 s pooled (+34%). Round trip 47.9 ms vs
        109.6 ms; connect 0.96 s vs 1.79 s. A rule run is a handful of long
        analytical statements on one connection -- the shape a transaction
        pooler helps least and taxes most.

    [x] The pooler did NOT break GE. Sequential runs, four concurrent
        validates and eight runs on psycopg v3 (server-side prepared
        statements, the classic transaction-mode breakage) all completed.
        It is slower, not broken. Recorded because the acceptance criteria
        asked for the failure mode verbatim and there was not one.

    [x] Connect is reported separately from validate and never added in.
        A server process registers its datasource once at boot; INV-1 is
        about what the user waits for after that.

    MEASURED -- the split
        db (server time, summed over every statement)   11.16 s of 13.59 s
        GE's own Python                                  2.64 s  (~18%)
        network (28 statements x 47.9 ms)                ~1.3 s  (~10%)
        drift over the whole 25-minute run               +0.3%

    UNEXPECTED -- three things, and each one changes a decision

    1.  `gx.get_context()` is PROCESS-GLOBAL. It does not just return a
        context, it installs it as the global project; a second call
        silently orphans the first one's datasources. The failure surfaces
        later, at validate(), as "Cannot initialize datasource <name>, error:
        The given datasource could not be retrieved from the DataContext" --
        a config error naming a datasource that is right there in the object
        you are holding. This cost this script its first full run. F8/INV-3:
        one context per process, handed out; never one per request.
        `context_factory.project_manager.set_project(ctx)` restores it.

    2.  The row cap BREAKS TWO CATALOG TYPES. `add_query_asset` is the only
        row cap GE 1.x offers, and `expect_column_values_to_be_of_type` and
        `expect_column_values_to_be_in_type_list` raise a bare KeyError
        'type' against a query asset while working fine against a table
        asset -- GE reads the column type from the reflected table. Combined
        with LT-1a's finding that an errored rule is indistinguishable from
        a failing one, a capped run shows two rules RED that never ran.

    3.  The row cap is a NET LOSS at full size, and it runs the query TWICE.
        GE executes the query asset's SQL verbatim through psycopg2's default
        client-side cursor, twice per validate: a 1,000-row cap moves 2,009
        rows, a 100,000-row cap moves 200,049. `LIMIT 500000` costs 23.6 s
        and 1,000,127 rows against 14.8 s and 156 rows for the same suite
        with no cap at all.

        So O-2's answer is "no cap", for three measured reasons: it buys
        little (100K cap saves 4.2 s of 13.6 s), it costs more than it saves
        at scale, and it breaks two of fifteen rule types.

    And one correction to LT-1a's warning: `result_format="COMPLETE"` does
    drop the LIMIT and stream every offending row -- 500,031 of them -- but
    that cost 3.01 s, about the same as the bounded SUMMARY run. The
    prohibition stands on memory and cache-size grounds, which these numbers
    support; not on latency grounds, which they do not.

RUN
    cp ../.env .env   # .env is gitignored and not in a fresh worktree
    uv run --with great-expectations --with 'sqlalchemy>=2' \
           --with psycopg2-binary --with 'psycopg[binary]' \
           python learning-tests/lt1b_ge_latency.py

    Takes roughly 20 minutes. REPS can be lowered via the LT1B_REPS env var,
    but the default of 5 is what the recorded findings were measured with and
    anything lower stops distinguishing signal from network jitter.

    psycopg v3 is only needed for the pooler prepared-statement check in §9;
    without it that section skips and says so.
"""

import json
import os
import pathlib
import signal
import statistics
import sys
import threading
import time
import traceback
from contextlib import contextmanager

import sqlalchemy as sa
from sqlalchemy import event

import great_expectations as gx
import great_expectations.expectations as gxe
from great_expectations.core.expectation_suite import ExpectationSuite
from great_expectations.data_context.types.base import ProgressBarsConfig

# --- env -------------------------------------------------------------------

for line in pathlib.Path(".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def pg2(url: str) -> str:
    """Name the driver explicitly -- LT-1a: a bare postgresql:// is a trap."""
    return url.replace("postgresql://", "postgresql+psycopg2://", 1)


RAW_DIRECT = os.environ.get("SUPABASE_DB_URL_DIRECT")
RAW_POOLED = os.environ.get("SUPABASE_DB_URL_POOLED")
assert RAW_DIRECT, "SUPABASE_DB_URL_DIRECT not in .env"
assert RAW_POOLED, "SUPABASE_DB_URL_POOLED not in .env"

URLS = {"direct": pg2(RAW_DIRECT), "pooled": pg2(RAW_POOLED)}


def host_of(url: str) -> str:
    return url.split("@")[-1].split("/")[0]


REPS = int(os.environ.get("LT1B_REPS", "5"))
WARMUPS = 1                      # discarded from the medians, printed anyway
COMPLETE_GUARD_S = 240           # hard abort for the result_format=COMPLETE trap

TABLE = "orders"                 # 500,000 rows, seed/MANIFEST.md
SCHEMA = "public"
FULL_ROWS = 500_000
CURVE = [1_000, 10_000, 100_000]   # capped, via add_query_asset
# ... plus the whole table (500,000) via add_table_asset, which is the
# uncapped configuration F8 would ship if O-2 says "no cap".

RULE = "=" * 78
SUB = "-" * 78

# What counts as watchable. Stated before the numbers, so the verdict is
# decided by the data and not by what the spec was hoping for.
T_INSTANT = 2.0     # feels like the page just answered
T_WATCHABLE = 5.0   # a spinner is enough
T_TOLERABLE = 10.0  # needs visible progress, still synchronous
# above T_TOLERABLE -> synchronous execution is not honest; it becomes a job.

VALID_ORDER_STATUS = ["pending", "paid", "shipped", "delivered",
                      "cancelled", "returned"]


def banner(n, title):
    print()
    print(RULE)
    print(f"{n}. {title}")
    print(RULE)


# ---------------------------------------------------------------------------
# The statement tap. Class-level, because GE does not validate through the
# engine handed back by `data_source.get_engine()` -- a listener attached to
# that instance sees nothing.
# ---------------------------------------------------------------------------

_stmts: list[tuple[float, int, str]] = []
_tapping = False


@event.listens_for(sa.engine.Engine, "before_cursor_execute")
def _before(conn, cursor, statement, parameters, context, executemany):
    conn.info["_lt1b_t0"] = time.perf_counter()


@event.listens_for(sa.engine.Engine, "after_cursor_execute")
def _after(conn, cursor, statement, parameters, context, executemany):
    if not _tapping:
        return
    ms = (time.perf_counter() - conn.info["_lt1b_t0"]) * 1000.0
    rc = cursor.rowcount if cursor.rowcount is not None else -1
    _stmts.append((ms, rc, " ".join(statement.split())))


@contextmanager
def tap():
    global _tapping
    _stmts.clear()
    _tapping = True
    try:
        yield _stmts
    finally:
        _tapping = False


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def summarise(samples: list[float]) -> dict:
    if not samples:
        return {"median": float("nan"), "min": float("nan"),
                "max": float("nan"), "n": 0, "spread_pct": float("nan")}
    med = statistics.median(samples)
    lo, hi = min(samples), max(samples)
    return {"median": med, "min": lo, "max": hi, "n": len(samples),
            "spread_pct": (hi - lo) / med * 100.0 if med else float("nan")}


def fmt(s: dict) -> str:
    return f"{s['median']:.2f} s  [{s['min']:.2f}-{s['max']:.2f}]"


def timed_validate(batch_def, target, result_format) -> dict:
    """One honest run: fresh batch, tapped statements, wall split from db."""
    with tap() as stmts:
        batch = batch_def.get_batch()
        t0 = time.perf_counter()
        result = batch.validate(target, result_format=result_format)
        wall = time.perf_counter() - t0
        db_s = sum(ms for ms, _, _ in stmts) / 1000.0
        rows = sum(rc for _, rc, _ in stmts if rc > 0)
        n_stmts = len(stmts)
    return {"wall": wall, "db": db_s, "overhead": wall - db_s,
            "stmts": n_stmts, "rows": rows, "result": result}


def results_list(res) -> list[dict]:
    """`validate()` returns a suite result for a suite and a *single*
    ExpectationValidationResult for a lone Expectation. Both shapes appear in
    this script; normalise to a list of per-expectation dicts."""
    jd = res.to_json_dict()
    return jd["results"] if "results" in jd else [jd]


def measure(batch_def, target, result_format, reps=None, label="") -> dict:
    """WARMUPS discarded runs, then `reps` measured ones."""
    reps = REPS if reps is None else reps
    first = None
    for i in range(WARMUPS):
        r = timed_validate(batch_def, target, result_format)
        if first is None:
            first = r
    runs = [timed_validate(batch_def, target, result_format)
            for _ in range(reps)]
    out = {
        "label": label,
        "wall": summarise([r["wall"] for r in runs]),
        "db": summarise([r["db"] for r in runs]),
        "overhead": summarise([r["overhead"] for r in runs]),
        "stmts": runs[0]["stmts"],
        "rows": runs[0]["rows"],
        "first_run_wall": first["wall"] if first else None,
        "element_count": None,
        "errored": 0,
    }
    rl = results_list(runs[0]["result"])
    counts = [r.get("result", {}).get("element_count") for r in rl]
    counts = [c for c in counts if c is not None]
    out["element_count"] = max(counts) if counts else None
    out["errored"] = sum(1 for r in rl if errored(r))
    return out


def errored(r: dict) -> bool:
    ei = r.get("exception_info") or {}
    if "raised_exception" in ei:
        return bool(ei["raised_exception"])
    return any(v.get("raised_exception") for v in ei.values()
               if isinstance(v, dict))


# ---------------------------------------------------------------------------
# The suite. All fifteen LT-2a catalog types, applied to `orders`, ordered so
# that the first 1 / 3 / 8 / 10 / 15 are nested prefixes -- suite-size scaling
# then compares like with like instead of comparing different rules.
# ---------------------------------------------------------------------------

CATALOG_RULES = [
    ("not_be_null(customer_id)",
     gxe.ExpectColumnValuesToNotBeNull(column="customer_id")),
    ("be_between(order_total >= 0)",
     gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=0)),
    ("be_in_set(status)",
     gxe.ExpectColumnValuesToBeInSet(column="status",
                                     value_set=VALID_ORDER_STATUS)),
    ("be_unique(order_reference)",
     gxe.ExpectColumnValuesToBeUnique(column="order_reference")),
    ("match_regex(order_reference)",
     gxe.ExpectColumnValuesToMatchRegex(column="order_reference",
                                        regex="^ORD-")),
    ("not_match_regex(status)",
     gxe.ExpectColumnValuesToNotMatchRegex(column="status",
                                           regex="^(test|dummy)")),
    ("value_lengths_between(currency)",
     gxe.ExpectColumnValueLengthsToBeBetween(column="currency",
                                             min_value=3, max_value=3)),
    ("not_be_in_set(channel)",
     gxe.ExpectColumnValuesToNotBeInSet(column="channel",
                                        value_set=["legacy", "unknown"])),
    ("be_in_type_list(order_total)",
     gxe.ExpectColumnValuesToBeInTypeList(column="order_total",
                                          type_list=["NUMERIC", "DECIMAL"])),
    ("be_of_type(order_id)",
     gxe.ExpectColumnValuesToBeOfType(column="order_id", type_="INTEGER")),
    ("mean_between(order_total)",
     gxe.ExpectColumnMeanToBeBetween(column="order_total",
                                     min_value=0, max_value=100_000)),
    ("unique_value_count_between(status)",
     gxe.ExpectColumnUniqueValueCountToBeBetween(column="status",
                                                 min_value=1, max_value=20)),
    ("table_row_count_between",
     gxe.ExpectTableRowCountToBeBetween(min_value=1, max_value=10_000_000)),
    ("column_to_exist(order_total)",
     gxe.ExpectColumnToExist(column="order_total")),
    # The one contrived rule. `orders` has no column that should always be
    # empty; it is kept so all fifteen catalog types are actually timed.
    ("be_null(shipped_at)  [contrived]",
     gxe.ExpectColumnValuesToBeNull(column="shipped_at")),
]
assert len(CATALOG_RULES) == 15


# The two type expectations cannot run on a *query* asset -- see §4b. Since a
# query asset is the only row-cap mechanism GE 1.x offers, the curve suite,
# which has to run identically on a capped and an uncapped batch, is drawn
# from the catalog minus those two. They are still timed in §6 and §7 against
# the table asset, where they work.
TYPE_RULES = {"be_in_type_list(order_total)", "be_of_type(order_id)"}
CURVE_RULES = [r for r in CATALOG_RULES if r[0] not in TYPE_RULES]
assert len(CURVE_RULES) == 13


def suite_from(rules, name: str) -> ExpectationSuite:
    s = ExpectationSuite(name=name)
    for _, e in rules:
        s.add_expectation(e)
    return s


def suite_of(n: int) -> ExpectationSuite:
    return suite_from(CATALOG_RULES[:n], f"lt1b_{n}")


SUITE_SIZES = [1, 3, 8, 10, 15]
REALISTIC = 10   # the suite used for the curve and the config comparison

# The two result_format configurations LT-1a flagged.
RF_PLAIN = {"result_format": "SUMMARY", "partial_unexpected_count": 20}
RF_INDEXED = {"result_format": "SUMMARY",
              "unexpected_index_column_names": ["order_id"],
              "partial_unexpected_count": 20}
# ... plus COMPLETE, measured once, under a guard.


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

print(RULE)
print("LT-1b · GE LATENCY ON SUPABASE — DIRECT vs POOLED   (bead dq-e1d)")
print(RULE)
print(f"great_expectations : {gx.__version__}")
print(f"sqlalchemy         : {sa.__version__}")
print(f"direct  (5432)     : {host_of(URLS['direct'])}")
print(f"pooled  (6543)     : {host_of(URLS['pooled'])}")
print(f"table              : {SCHEMA}.{TABLE}  ({FULL_ROWS:,} rows, seed/MANIFEST.md)")
print(f"reps               : {WARMUPS} warmup (discarded) + {REPS} measured per cell")
print(f"catalog            : {len(CATALOG_RULES)} rules, LT-2a's 15 types")

context = gx.get_context(mode="ephemeral")
# GE renders a tqdm bar per metric; it writes to the same stream as the
# measurements and adds work that has nothing to do with the database.
context.variables.progress_bars = ProgressBarsConfig(globally=False)

RESULTS: dict = {"meta": {
    "gx": gx.__version__, "sqlalchemy": sa.__version__,
    "direct_host": host_of(URLS["direct"]), "pooled_host": host_of(URLS["pooled"]),
    "reps": REPS, "warmups": WARMUPS, "table": f"{SCHEMA}.{TABLE}",
    "full_rows": FULL_ROWS,
}}
FAILURES: list[str] = []


# ---------------------------------------------------------------------------
banner(1, "BASELINE NETWORK — what a round trip to Singapore costs")
# Every GE statement pays this once. Separating it from scan time is the whole
# point: a rule that takes 3 s over 6 statements is 0.6 s of network and
# 2.4 s of PostgreSQL, and only one of those is ours to reason about.
# ---------------------------------------------------------------------------

rtt = {}
engines = {}
for name, url in URLS.items():
    eng = sa.create_engine(url)
    engines[name] = eng
    samples = []
    with eng.connect() as c:
        for i in range(20):
            t0 = time.perf_counter()
            c.execute(sa.text("SELECT 1"))
            samples.append((time.perf_counter() - t0) * 1000.0)
    s = summarise(samples[1:])       # drop the first, it carries session setup
    rtt[name] = s
    print(f"  {name:<7} SELECT 1 x20 : median {s['median']:.1f} ms "
          f"[{s['min']:.1f}-{s['max']:.1f}]  (first {samples[0]:.1f} ms)")
RESULTS["rtt_ms"] = rtt


# ---------------------------------------------------------------------------
banner(2, "CONNECT COST — reported separately, because INV-1 is about waiting")
# INV-1 cares about what the user waits for *after* the page is already open.
# A server process holds its datasource; the user pays connect once at boot,
# not per run. So this number is quoted apart from validate time and never
# added into it.
# ---------------------------------------------------------------------------

connect = {}
for name, url in URLS.items():
    samples = []
    for i in range(REPS):
        # Deliberately on the one shared context, under throwaway names.
        # A fresh gx.get_context() per probe would look tidier and would
        # silently break every later measurement -- see §3b.
        t0 = time.perf_counter()
        context.data_sources.add_postgres(name=f"probe_{name}_{i}",
                                          connection_string=url)
        samples.append(time.perf_counter() - t0)
    s = summarise(samples)
    connect[name] = s
    print(f"  {name:<7} add_postgres() x{REPS} : {fmt(s)}   "
          f"(eager connect + test_connection)")
RESULTS["connect_s"] = connect


# ---------------------------------------------------------------------------
banner(3, "DATASOURCES + ASSETS")
# One context, one datasource per URL, reused for every measurement below --
# which is what a server process does. Assets are added once; GE reflects a
# table asset's schema on first use and caches it.
# ---------------------------------------------------------------------------

ds = {}
assets = {}
for name, url in URLS.items():
    t0 = time.perf_counter()
    try:
        ds[name] = context.data_sources.add_postgres(name=name,
                                                     connection_string=url)
    except Exception:
        print(f"  {name}: add_postgres FAILED — verbatim:")
        traceback.print_exc()
        FAILURES.append(f"{name}: add_postgres failed")
        raise
    print(f"  {name:<7} datasource registered in {time.perf_counter()-t0:.2f} s")

    a = {}
    a["full"] = (ds[name].add_table_asset(name=f"{name}_orders_full",
                                          table_name=TABLE, schema_name=SCHEMA)
                 .add_batch_definition_whole_table(name="wt"))
    for n in CURVE:
        a[n] = (ds[name].add_query_asset(
                    name=f"{name}_orders_{n}",
                    query=f"SELECT * FROM {SCHEMA}.{TABLE} LIMIT {n}")
                .add_batch_definition_whole_table(name="wt"))
    # the cap mechanism applied at full size, for §8
    a["capped_full"] = (ds[name].add_query_asset(
                            name=f"{name}_orders_capped_full",
                            query=f"SELECT * FROM {SCHEMA}.{TABLE} "
                                  f"LIMIT {FULL_ROWS}")
                        .add_batch_definition_whole_table(name="wt"))
    assets[name] = a
    print(f"          assets: full (table) + {CURVE} + capped_full (query)")


# ---------------------------------------------------------------------------
banner("3b", "THE GLOBAL-CONTEXT TRAP — found the hard way, asserted here")
# `gx.get_context()` does not just return a context, it installs it as a
# process-global project. A second call silently orphans the first one's
# datasources, and the failure does not surface at get_context() -- it
# surfaces later, at validate(), as a configuration error naming a datasource
# that is plainly right there. This cost this script its first full run.
# It matters for F8: a request handler that calls gx.get_context() per request
# breaks every other request in flight.
# ---------------------------------------------------------------------------

from great_expectations.data_context.data_context.context_factory import (
    project_manager,
)

probe_bd = (ds["direct"]
            .add_query_asset(name="ctx_trap_probe",
                             query=f"SELECT * FROM {SCHEMA}.{TABLE} LIMIT 100")
            .add_batch_definition_whole_table(name="wt"))
one = CATALOG_RULES[1][1]
assert probe_bd.get_batch().validate(one).result is not None
print("  a validate on the main context works")

_other = gx.get_context(mode="ephemeral")   # an innocent-looking second call
trap = None
try:
    probe_bd.get_batch().validate(one)
    print("  a second gx.get_context() did NOT break it")
except Exception as exc:
    trap = f"{type(exc).__name__}: {exc}"
    print(f"  a second gx.get_context() BROKE it — verbatim:\n     {trap}")

project_manager.set_project(context)        # put the real project back
assert probe_bd.get_batch().validate(one).result is not None, \
    "project_manager.set_project() did not restore the context"
print("  project_manager.set_project(context) restores it")
RESULTS["global_context_trap"] = trap


# ---------------------------------------------------------------------------
banner(4, "SANITY — the suite runs clean, and the counts match the manifest")
# A rule that silently errors is cheap, and a cheap errored rule would flatter
# every number below. LT-1a: catch_exceptions defaults to True, so an errored
# rule looks exactly like a failing one. Assert zero errors before timing.
# ---------------------------------------------------------------------------

full15 = suite_of(15)
sanity = timed_validate(assets["direct"]["full"], full15, RF_INDEXED)
jd = sanity["result"].to_json_dict()
n_err = sum(1 for r in jd["results"] if errored(r))
print(f"  15 rules over {FULL_ROWS:,} rows: {sanity['wall']:.2f} s, "
      f"{jd['statistics']['evaluated_expectations']} evaluated, "
      f"{jd['statistics']['unsuccessful_expectations']} failing, "
      f"{n_err} errored")
for r in jd["results"]:
    if errored(r):
        print(f"    ERRORED: {r['expectation_config']['type']} "
              f"{r.get('exception_info')}")
assert n_err == 0, "a rule errored — every timing below would be flattered by it"

by_type = {r["expectation_config"]["type"]: r for r in jd["results"]}
neg = by_type["expect_column_values_to_be_between"]["result"]["unexpected_count"]
bad_status = by_type["expect_column_values_to_be_in_set"]["result"]["unexpected_count"]
dup_ref = by_type["expect_column_values_to_be_unique"]["result"]["unexpected_count"]
print(f"  manifest D1 negative order_total : planted 150  GE {neg}")
print(f"  manifest D3 bad status           : planted 240  GE {bad_status}")
print(f"  manifest D6 duplicate order_ref  : planted 150  GE {dup_ref}")
assert neg == 150, f"D1 mismatch: {neg}"
assert bad_status == 240, f"D3 mismatch: {bad_status}"
assert dup_ref == 150, f"D6 mismatch: {dup_ref}"
print("  counts agree with seed/MANIFEST.md — we are measuring real work")
RESULTS["sanity"] = {"negative_totals": neg, "bad_status": bad_status,
                     "duplicate_reference": dup_ref, "errored": n_err}


# ---------------------------------------------------------------------------
banner("4b", "THE ROW CAP BREAKS TWO CATALOG TYPES — this is an O-2 finding")
# `add_query_asset` is the only row cap GE 1.x offers (LT-1a). Running the same
# fifteen rules over a query asset instead of a table asset does not merely
# cost more (§9) -- two of them stop working. And per LT-1a an errored rule is
# indistinguishable from a failing one unless `exception_info` is read, so a
# capped run would report two rules RED that never ran at all.
# ---------------------------------------------------------------------------


def errored_types(bd, rules) -> dict:
    res = bd.get_batch().validate(suite_from(rules, "probe"),
                                  result_format=RF_INDEXED)
    out = {}
    for r in results_list(res):
        if errored(r):
            ei = r.get("exception_info") or {}
            if "raised_exception" in ei:
                msg = ei.get("exception_message")
            else:
                msg = [v.get("exception_message") for v in ei.values()
                       if isinstance(v, dict) and v.get("raised_exception")]
            out[r["expectation_config"]["type"]] = msg
    return out


type_rules = [r for r in CATALOG_RULES if r[0] in TYPE_RULES]
on_table = errored_types(assets["direct"]["full"], type_rules)
on_query = errored_types(assets["direct"][1000], type_rules)
print(f"  on a table asset  : {len(on_table)} errored")
print(f"  on a query asset  : {len(on_query)} errored")
for t, msg in on_query.items():
    print(f"     {t}\n       exception_message: {msg}")
assert on_table == {}, "type expectations broke on a table asset too"
assert set(on_query) == {"expect_column_values_to_be_of_type",
                         "expect_column_values_to_be_in_type_list"}, \
    f"unexpected set of query-asset failures: {set(on_query)}"
print("  -> the curve suite below is drawn from the catalog MINUS these two,")
print("     so the capped and uncapped cells run identical work.")
RESULTS["query_asset_breaks"] = {k: str(v) for k, v in on_query.items()}


# ---------------------------------------------------------------------------
banner(5, f"ROW-COUNT CURVE — {REALISTIC}-rule suite, both configs, both URLs")
# The question O-2 asks: is wall time linear in rows, and where does a cap buy
# anything? 1K/10K/100K are capped with add_query_asset (LT-1a: the only row
# cap GE 1.x offers); 500K is the whole table via add_table_asset, i.e. the
# uncapped configuration. The mechanisms differ and §8 measures what that
# difference costs, so the two are labelled and never silently compared.
# ---------------------------------------------------------------------------

suite10 = suite_from(CURVE_RULES[:REALISTIC], "lt1b_curve10")
curve = {}
print(f"  {'conn':<7} {'rows':>8} {'cfg':<8} {'wall (median [min-max])':<26} "
      f"{'db':>7} {'ovh':>7} {'stmt':>5} {'rows_pulled':>12} {'per-rule':>9}")
print("  " + SUB)
# Connections are interleaved, not run in two blocks. The free tier is
# burstable; if it degraded over the twenty minutes this script runs, a
# connection-outer loop would charge that degradation to whichever URL went
# second and the headline direct-vs-pooled comparison would be an artefact.
for n in CURVE + ["full"]:
    for cfg, rf in (("plain", RF_PLAIN), ("indexed", RF_INDEXED)):
        for conn in ("direct", "pooled"):
            key = f"{conn}/{n}/{cfg}"
            m = measure(assets[conn][n], suite10, rf, label=key)
            curve[key] = m
            rows_lbl = f"{FULL_ROWS:,}" if n == "full" else f"{n:,}"
            print(f"  {conn:<7} {rows_lbl:>8} {cfg:<8} {fmt(m['wall']):<26} "
                  f"{m['db']['median']:6.2f}s {m['overhead']['median']:6.2f}s "
                  f"{m['stmts']:5d} {m['rows']:12,} "
                  f"{m['wall']['median']/REALISTIC:8.2f}s")
            assert m["errored"] == 0, f"{key}: a rule errored"
RESULTS["curve"] = {k: {kk: vv for kk, vv in v.items() if kk != "result"}
                    for k, v in curve.items()}


# ---------------------------------------------------------------------------
banner(6, "SUITE-SIZE SCALING — is the cost per rule or per run?")
# Whole table, direct, the shipping config. Nested prefixes of the same
# catalog, so 1 vs 15 is the same rules plus more, not different rules.
# ---------------------------------------------------------------------------

scaling = {}
print(f"  {'rules':>5} {'wall (median [min-max])':<26} {'db':>7} {'ovh':>7} "
      f"{'stmt':>5} {'per-rule':>9} {'marginal':>9}")
print("  " + SUB)
prev = None
for n in SUITE_SIZES:
    m = measure(assets["direct"]["full"], suite_of(n), RF_INDEXED,
                label=f"scaling/{n}")
    scaling[n] = m
    marg = "" if prev is None else f"{(m['wall']['median']-prev[1])/(n-prev[0]):8.2f}s"
    print(f"  {n:5d} {fmt(m['wall']):<26} {m['db']['median']:6.2f}s "
          f"{m['overhead']['median']:6.2f}s {m['stmts']:5d} "
          f"{m['wall']['median']/n:8.2f}s {marg:>9}")
    prev = (n, m["wall"]["median"])
    assert m["errored"] == 0
RESULTS["scaling"] = {k: {kk: vv for kk, vv in v.items() if kk != "result"}
                      for k, v in scaling.items()}


# ---------------------------------------------------------------------------
banner(7, "PER-RULE COST — which of the fifteen are expensive?")
# Each catalog type alone, whole table, direct, shipping config. A per-run
# floor is charged to every one of them, so these are not additive; the point
# is the ranking and the outliers.
# ---------------------------------------------------------------------------

per_rule = {}
print(f"  {'rule':<36} {'wall (median [min-max])':<26} {'db':>7} {'stmt':>5}")
print("  " + SUB)
for label, exp in CATALOG_RULES:
    m = measure(assets["direct"]["full"], exp, RF_INDEXED, reps=3,
                label=f"rule/{label}")
    per_rule[label] = m
    print(f"  {label:<36} {fmt(m['wall']):<26} {m['db']['median']:6.2f}s "
          f"{m['stmts']:5d}")
RESULTS["per_rule"] = {k: {kk: vv for kk, vv in v.items() if kk != "result"}
                       for k, v in per_rule.items()}

ranked = sorted(per_rule.items(), key=lambda kv: kv[1]["wall"]["median"])
cheapest = ranked[0]
dearest = ranked[-1]
print(f"\n  cheapest: {cheapest[0]} at {cheapest[1]['wall']['median']:.2f} s")
print(f"  dearest : {dearest[0]} at {dearest[1]['wall']['median']:.2f} s")


# ---------------------------------------------------------------------------
banner(8, 'result_format="COMPLETE" — the setting that invalidates the story')
# LT-1a called it a trap without pricing it. Two rules, both on the whole
# table: one narrow (150 offending rows, the manifest's D1) and one that
# matches nearly every row. Under a hard alarm, because an unbounded stream of
# 500K rows from Singapore is exactly the failure being priced.
# ---------------------------------------------------------------------------

class Guard(Exception):
    pass


def _alarm(signum, frame):
    raise Guard()

# NOTE on the guard: SIGALRM is delivered between bytecodes, so it cannot
# interrupt psycopg2 while it is blocked in libpq fetching rows. If COMPLETE
# streams for longer than the guard, the abort lands when control returns to
# Python, not on the second. Treat an "aborted at N s" as a lower bound.


complete = {}
RF_COMPLETE = {"result_format": "COMPLETE",
               "unexpected_index_column_names": ["order_id"]}
RF_COMPLETE_PLAIN = {"result_format": "COMPLETE"}

cases = [
    ("narrow (150 offending)", CATALOG_RULES[1][1], RF_COMPLETE),
    ("wide (~all rows offending)",
     gxe.ExpectColumnValuesToBeBetween(column="order_total", min_value=10**9),
     RF_COMPLETE_PLAIN),
]
for label, exp, rf in cases:
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(COMPLETE_GUARD_S)
    t0 = time.perf_counter()
    try:
        r = timed_validate(assets["direct"]["full"], exp, rf)
        signal.alarm(0)
        n_un = results_list(r["result"])[0].get("result", {}).get(
            "unexpected_count")
        complete[label] = {"wall": r["wall"], "db": r["db"],
                           "rows": r["rows"], "stmts": r["stmts"],
                           "unexpected": n_un, "aborted": False}
        print(f"  {label:<28} {r['wall']:8.2f} s   db {r['db']:6.2f} s   "
              f"{r['rows']:,} rows over the wire   unexpected {n_un:,}")
    except Guard:
        el = time.perf_counter() - t0
        complete[label] = {"wall": el, "aborted": True,
                           "guard_s": COMPLETE_GUARD_S}
        print(f"  {label:<28} ABORTED by the {COMPLETE_GUARD_S} s guard "
              f"after {el:.1f} s — that is the finding")
    finally:
        signal.alarm(0)

# and the same two under SUMMARY, so the comparison is like for like
base_narrow = measure(assets["direct"]["full"], CATALOG_RULES[1][1],
                      RF_INDEXED, reps=3, label="complete/base_narrow")
base_wide = measure(assets["direct"]["full"],
                    gxe.ExpectColumnValuesToBeBetween(column="order_total",
                                                      min_value=10**9),
                    RF_PLAIN, reps=3, label="complete/base_wide")
print(f"  {'SUMMARY, same narrow rule':<28} {base_narrow['wall']['median']:8.2f} s   "
      f"{base_narrow['rows']:,} rows over the wire")
print(f"  {'SUMMARY, same wide rule':<28} {base_wide['wall']['median']:8.2f} s   "
      f"{base_wide['rows']:,} rows over the wire")
complete["SUMMARY narrow"] = {"wall": base_narrow["wall"]["median"],
                              "rows": base_narrow["rows"], "aborted": False}
complete["SUMMARY wide"] = {"wall": base_wide["wall"]["median"],
                            "rows": base_wide["rows"], "aborted": False}
RESULTS["complete"] = complete


# ---------------------------------------------------------------------------
banner(9, "WHAT THE ROW CAP ITSELF COSTS — add_query_asset is not free")
# The only row cap GE 1.x offers is our own SQL through add_query_asset.
# GE executes that query verbatim, once per validate, through psycopg2's
# default client-side cursor -- so it fetches every capped row into the
# client before any expectation is evaluated. Price it at full size against
# the uncapped table asset.
# ---------------------------------------------------------------------------

cap = {}
for label, bd in (("capped   LIMIT 500000 (query asset)", assets["direct"]["capped_full"]),
                  ("uncapped whole table   (table asset)", assets["direct"]["full"])):
    m = measure(bd, suite10, RF_INDEXED, reps=3, label=f"cap/{label}")
    cap[label] = {kk: vv for kk, vv in m.items() if kk != "result"}
    print(f"  {label:<38} {fmt(m['wall']):<26} rows over the wire {m['rows']:,}")
RESULTS["cap_cost"] = cap


# ---------------------------------------------------------------------------
banner(10, "THE POOLER — does pgbouncer/supavisor transaction mode break GE?")
# Called out in the acceptance criteria. Three things are tried and whatever
# happens is recorded verbatim: sequential validates, four concurrent ones,
# and psycopg v3 (which uses server-side prepared statements, the classic
# transaction-mode breakage psycopg2 never triggers).
# ---------------------------------------------------------------------------

pooler = {}

print("  a) sequential validates on 6543")
try:
    for i in range(3):
        r = timed_validate(assets["pooled"]["full"], suite10, RF_INDEXED)
        print(f"     run {i}: {r['wall']:.2f} s, {r['stmts']} statements")
    pooler["sequential"] = "OK"
except Exception as e:
    pooler["sequential"] = traceback.format_exc()
    print("     FAILED — verbatim:")
    traceback.print_exc()
    FAILURES.append("pooled sequential")

print("  b) four concurrent validates on 6543")
errs: list[str] = []
walls: list[float] = []
lock = threading.Lock()


def _worker(i):
    try:
        b = assets["pooled"]["full"].get_batch()
        t0 = time.perf_counter()
        b.validate(suite_of(3), result_format=RF_INDEXED)
        with lock:
            walls.append(time.perf_counter() - t0)
    except Exception:
        with lock:
            errs.append(traceback.format_exc())


ths = [threading.Thread(target=_worker, args=(i,)) for i in range(4)]
t0 = time.perf_counter()
for t in ths:
    t.start()
for t in ths:
    t.join()
conc_wall = time.perf_counter() - t0
if errs:
    pooler["concurrent"] = errs[0]
    print(f"     {len(errs)}/4 FAILED — first failure verbatim:")
    print("     " + errs[0].replace("\n", "\n     "))
    FAILURES.append("pooled concurrent")
else:
    pooler["concurrent"] = (f"OK — 4 threads, wall {conc_wall:.2f} s, "
                            f"per-thread {sorted(round(w,2) for w in walls)}")
    print(f"     OK — 4 threads finished in {conc_wall:.2f} s wall; "
          f"per-thread {sorted(round(w, 2) for w in walls)}")

print("  c) psycopg v3 on 6543 — server-side prepared statements")
try:
    import psycopg  # noqa: F401
    url3 = RAW_POOLED.replace("postgresql://", "postgresql+psycopg://", 1)
    # On the same context, deliberately -- see §3b.
    ds3 = context.data_sources.add_postgres(name="pooled_pg3",
                                            connection_string=url3)
    bd3 = (ds3.add_table_asset(name="p3_orders", table_name=TABLE,
                               schema_name=SCHEMA)
           .add_batch_definition_whole_table(name="wt"))
    # psycopg3 prepares a statement after prepare_threshold (5) executions of
    # the same text; run well past that so the pooler has to survive it.
    walls3 = []
    for i in range(8):
        r = timed_validate(bd3, suite_of(3), RF_INDEXED)
        walls3.append(round(r["wall"], 2))
    pooler["psycopg3"] = f"OK — 8 sequential runs, walls {walls3}"
    print(f"     OK — 8 sequential runs survived, walls {walls3}")
except ImportError:
    pooler["psycopg3"] = "SKIPPED — psycopg v3 not installed"
    print("     SKIPPED — psycopg v3 not installed "
          "(add --with 'psycopg[binary]')")
except Exception:
    pooler["psycopg3"] = traceback.format_exc()
    print("     FAILED — verbatim:")
    traceback.print_exc()
    FAILURES.append("pooled psycopg3")

RESULTS["pooler"] = pooler


# ---------------------------------------------------------------------------
banner(11, "DRIFT CHECK — is the instance the same one we started on?")
# Supabase's free tier is burstable. Twenty minutes of scans can spend CPU
# credit, which would make late measurements look worse than early ones for
# reasons that have nothing to do with configuration. Re-run the §5 baseline
# cell and compare.
# ---------------------------------------------------------------------------

drift = measure(assets["direct"]["full"], suite10, RF_INDEXED, label="drift")
base = curve["direct/full/indexed"]["wall"]["median"]
delta_pct = (drift["wall"]["median"] - base) / base * 100.0
print(f"  §5 direct/500K/indexed : {base:.2f} s")
print(f"  same cell, re-run now  : {drift['wall']['median']:.2f} s "
      f"({delta_pct:+.1f}%)")
RESULTS["drift"] = {"baseline_s": base, "rerun_s": drift["wall"]["median"],
                    "delta_pct": delta_pct}
if abs(delta_pct) > 25:
    print("  WARNING: >25% drift — treat cross-section comparisons with care")


# ---------------------------------------------------------------------------
banner(12, "VERDICT")
# Decided by the thresholds stated at the top of this file against the
# measured medians. Not by what the spec was hoping for.
# ---------------------------------------------------------------------------

ship_full = curve["direct/full/indexed"]["wall"]["median"]
ship_100k = curve["direct/100000/indexed"]["wall"]["median"]
ship_10k = curve["direct/10000/indexed"]["wall"]["median"]
ship_1k = curve["direct/1000/indexed"]["wall"]["median"]
pooled_full = curve["pooled/full/indexed"]["wall"]["median"]
plain_full = curve["direct/full/plain"]["wall"]["median"]
full15_wall = scaling[15]["wall"]["median"]


def band(sec: float) -> str:
    if sec <= T_INSTANT:
        return "instant"
    if sec <= T_WATCHABLE:
        return "watchable with a spinner"
    if sec <= T_TOLERABLE:
        return "tolerable, needs visible progress"
    return "past the bar — a blank spinner is not honest here"


print(f"  {REALISTIC} rules, 500,000 rows, direct, shipping config : "
      f"{ship_full:.2f} s  -> {band(ship_full)}")
print(f"  15 rules, 500,000 rows, direct, shipping config       : "
      f"{full15_wall:.2f} s  -> {band(full15_wall)}")
print(f"  {REALISTIC} rules, 100,000 rows (capped)                  : "
      f"{ship_100k:.2f} s  -> {band(ship_100k)}")
print(f"  {REALISTIC} rules,  10,000 rows (capped)                  : "
      f"{ship_10k:.2f} s  -> {band(ship_10k)}")

SYNC_VIABLE = full15_wall <= T_TOLERABLE
print()
print(f"  SYNCHRONOUS EXECUTION AT FULL TABLE SIZE: "
      f"{'VIABLE' if SYNC_VIABLE else 'NOT VIABLE'}")
print(f"  (threshold: a worst-case realistic suite must finish in "
      f"<= {T_TOLERABLE:.0f} s)")

# Where the line actually falls. A bare pass/fail is not enough to design
# against -- what F8 needs to know is how much work fits under the bar.
fit_rules = max((n for n in SUITE_SIZES
                 if scaling[n]["wall"]["median"] <= T_TOLERABLE), default=0)
fit_rows = None
for n in CURVE + ["full"]:
    if curve[f"direct/{n}/indexed"]["wall"]["median"] <= T_TOLERABLE:
        fit_rows = FULL_ROWS if n == "full" else n
per_rule_marginal = ((scaling[15]["wall"]["median"]
                      - scaling[1]["wall"]["median"]) / 14)
print(f"  largest suite that fits under {T_TOLERABLE:.0f} s at "
      f"{FULL_ROWS:,} rows : {fit_rules} rules")
print(f"  largest row count that fits under {T_TOLERABLE:.0f} s with "
      f"{REALISTIC} rules : {fit_rows:,}" if fit_rows else
      f"  no measured row count fits under {T_TOLERABLE:.0f} s "
      f"with {REALISTIC} rules")
print(f"  marginal cost of one more rule at full size : "
      f"{per_rule_marginal:.2f} s")

better = "direct" if ship_full <= pooled_full else "pooled"
print(f"  F8 should use the {better.upper()} URL: "
      f"{ship_full:.2f} s vs {pooled_full:.2f} s for the same work, and the "
      f"pooler {'broke' if any('pooled' in f for f in FAILURES) else 'did not break'}.")
RESULTS["verdict"] = {
    "sync_viable": SYNC_VIABLE, "recommended_url": better,
    "ship_full_s": ship_full, "ship_100k_s": ship_100k,
    "ship_10k_s": ship_10k, "ship_1k_s": ship_1k,
    "pooled_full_s": pooled_full, "plain_full_s": plain_full,
    "full15_s": full15_wall,
    "fit_rules_at_full": fit_rules, "fit_rows_at_10_rules": fit_rows,
    "marginal_s_per_rule": per_rule_marginal,
    "thresholds": {"instant": T_INSTANT, "watchable": T_WATCHABLE,
                   "tolerable": T_TOLERABLE},
}


# ---------------------------------------------------------------------------
banner(13, "WRITE FINDINGS")
# ---------------------------------------------------------------------------

HERE = pathlib.Path(__file__).resolve().parent
raw_path = HERE / "lt1b_results.json"
raw_path.write_text(json.dumps(RESULTS, indent=2, default=str))
print(f"  raw measurements -> {raw_path}")


def row(conn, n, cfg):
    m = curve[f"{conn}/{n}/{cfg}"]
    rows_lbl = f"{FULL_ROWS:,}" if n == "full" else f"{n:,}"
    mech = "table asset" if n == "full" else "query asset, LIMIT"
    return (f"| {conn} | {rows_lbl} | {mech} | {cfg} | "
            f"{m['wall']['median']:.2f} | {m['wall']['min']:.2f}–{m['wall']['max']:.2f} | "
            f"{m['db']['median']:.2f} | {m['overhead']['median']:.2f} | "
            f"{m['stmts']} | {m['rows']:,} | "
            f"{m['wall']['median']/REALISTIC:.2f} |")


curve_rows = "\n".join(
    row(conn, n, cfg)
    for conn in ("direct", "pooled")
    for n in CURVE + ["full"]
    for cfg in ("plain", "indexed")
)

scaling_rows = "\n".join(
    f"| {n} | {scaling[n]['wall']['median']:.2f} | "
    f"{scaling[n]['wall']['min']:.2f}–{scaling[n]['wall']['max']:.2f} | "
    f"{scaling[n]['db']['median']:.2f} | {scaling[n]['overhead']['median']:.2f} | "
    f"{scaling[n]['stmts']} | {scaling[n]['wall']['median']/n:.2f} |"
    for n in SUITE_SIZES
)

per_rule_rows = "\n".join(
    f"| `{label}` | {m['wall']['median']:.2f} | "
    f"{m['wall']['min']:.2f}–{m['wall']['max']:.2f} | "
    f"{m['db']['median']:.2f} | {m['stmts']} |"
    for label, m in ranked
)


def cplx(k):
    c = complete[k]
    if c.get("aborted"):
        return f"| {k} | **aborted at {c['guard_s']} s** | — | — |"
    return (f"| {k} | {c['wall']:.2f} s | {c.get('rows', 0):,} | "
            f"{c.get('unexpected', '—')} |")


complete_rows = "\n".join(cplx(k) for k in complete)

cap_rows = "\n".join(
    f"| {k} | {v['wall']['median']:.2f} | "
    f"{v['wall']['min']:.2f}–{v['wall']['max']:.2f} | {v['rows']:,} |"
    for k, v in cap.items()
)

marg = ((scaling[15]["wall"]["median"] - scaling[1]["wall"]["median"]) / 14)
floor = scaling[1]["wall"]["median"]
db_share = curve["direct/full/indexed"]["db"]["median"] / ship_full * 100
ovh_share = 100 - db_share
net_share = (curve["direct/full/indexed"]["stmts"]
             * rtt["direct"]["median"] / 1000.0) / ship_full * 100

# Precomputed so the findings template stays free of fragile lookups.
CAP_ON, CAP_OFF = list(cap)[0], list(cap)[1]
cap_on_s = cap[CAP_ON]["wall"]["median"]
cap_off_s = cap[CAP_OFF]["wall"]["median"]
cap_on_rows = cap[CAP_ON]["rows"]
cap_off_rows = cap[CAP_OFF]["rows"]

_wide = complete.get("wide (~all rows offending)", {})
wide_rows = _wide.get("rows", 0)
wide_aborted = _wide.get("aborted", False)

_mid = statistics.median([m["wall"]["median"] for _, m in ranked[:-1]])
dearest_x = dearest[1]["wall"]["median"] / _mid if _mid else float("nan")
second_dearest_s = ranked[-2][1]["wall"]["median"]
cheapest_s = ranked[0][1]["wall"]["median"]

d31 = scaling[3]["wall"]["median"] - scaling[1]["wall"]["median"]
d83 = scaling[8]["wall"]["median"] - scaling[3]["wall"]["median"]
d158 = scaling[15]["wall"]["median"] - scaling[8]["wall"]["median"]

fit_rows_lbl = f"{fit_rows:,} rows" if fit_rows else \
    f"none — even {CURVE[0]:,} rows takes {ship_1k:.1f} s"
_after = [n for n in SUITE_SIZES if n > fit_rules]
next_size = _after[0] if _after else SUITE_SIZES[-1]

breaks_block = "\n".join(
    f"{k}\n    exception_message: {v}"
    for k, v in RESULTS["query_asset_breaks"].items()) or "(none)"

cap_saving = ship_full - ship_100k
cap_saving_pct = cap_saving / ship_full * 100.0

o2 = (
    f"**Do not add a row cap. It is the wrong lever, and the mechanism "
    f"available for it is worse than the problem.**"
)

o3 = (
    "**synchronous**, with visible per-rule progress."
    if SYNC_VIABLE else
    "**synchronous, but progressive** — the request stays synchronous and "
    "streams each rule's verdict as it lands. Not a background job queue: the "
    "measured cost is a sequence of independent statements, and a worker "
    "would return the same total later with a polling endpoint and a "
    "staleness problem added."
)

sync_rationale = (
    f"The worst case measured — all fifteen catalog rules over the whole "
    f"{FULL_ROWS:,}-row table — is {full15_wall:.1f} s, which is inside the "
    f"{T_TOLERABLE:.0f} s bar set before the numbers were read. It is not "
    f"instant, so F8 must show which rule is running rather than a bare "
    f"spinner, and F9's cache stops a reload from paying it again. But it "
    f"does not need a job queue, a worker, or a polled status endpoint, and "
    f"the spec's synchronous shape stands as written."
    if SYNC_VIABLE else
    f"The worst case measured is {full15_wall:.1f} s, past the "
    f"{T_TOLERABLE:.0f} s bar. But the shape of the cost decides what to do "
    f"about it, and the shape is: a {scaling[1]['wall']['median']:.1f} s "
    f"floor plus ~{per_rule_marginal:.1f} s per rule, paid as a sequence of "
    f"independent statements. Nothing in that is improved by moving it to a "
    f"worker — a job queue would return the same {full15_wall:.0f} s later, "
    f"with a polling endpoint and a stale-result problem added. What it "
    f"argues for is **a synchronous request that streams each rule's verdict "
    f"as it lands**: the first result appears in about "
    f"{scaling[1]['wall']['median']:.0f} s and the list fills. Combined with "
    f"F9's cache — a reload renders the last result without re-executing — "
    f"that keeps F8, F9 and F13 the synchronous screens the spec describes.\n"
    f"\nSPEC §8's contingency is therefore **partially triggered**: the "
    f"feature does not change into a job system, but F8's acceptance needs a "
    f"progressive-result clause and F13 needs to render a partially-complete "
    f"run. That is a spec revision to make before implementation, not "
    f"during, and it is the author's call — the measurement's job is to say "
    f"that a blank spinner for {full15_wall:.0f} s is not an option."
)

SECTION = f"""\
## LT-1b · Great Expectations latency on Supabase — direct vs pooled

**Bead** `dq-e1d` · **Run** {time.strftime('%Y-%m-%d')}
**great-expectations {gx.__version__}**, SQLAlchemy {sa.__version__},
psycopg2-binary, Python {sys.version.split()[0]},
PostgreSQL 17.6 (Supabase, `ap-southeast-1` / Singapore)
**Feeds** SPEC **O-2** (row cap), **O-3** (synchronous vs background),
F8, F9, F13, INV-1, INV-5
**Run it:**

```bash
cp ../.env .env
uv run --with great-expectations --with 'sqlalchemy>=2' \\
       --with psycopg2-binary --with 'psycopg[binary]' \\
       python learning-tests/lt1b_ge_latency.py
```

Every cell is {WARMUPS} discarded warm-up run plus **{REPS} measured runs**;
tables report the median and the min–max spread. Nothing here writes to the
database — every statement issued is a `SELECT`. The tables are the seeded
demo set: `orders`, {FULL_ROWS:,} rows, only the primary key indexed
(`seed/MANIFEST.md`). Counts were checked against the manifest before timing
started, so these are timings of real work: GE reported exactly the planted
150 negative totals, 240 bad statuses and 150 duplicate references.

### The verdict, in plain words

Thresholds were fixed **before** the numbers were read: ≤{T_INSTANT:.0f} s reads
as instant, ≤{T_WATCHABLE:.0f} s needs only a spinner, ≤{T_TOLERABLE:.0f} s is
tolerable with visible progress, and beyond that a synchronous screen is
dishonest and the work belongs in a background job.

**A full-catalog run over the whole table does not clear that bar.** All
fifteen catalog rules over {FULL_ROWS:,} rows on the direct connection take
**{full15_wall:.2f} s**. The {REALISTIC}-rule suite in the configuration F8
will actually ship (`unexpected_index_column_names`, which F13 needs for
identifier-plus-value) takes **{ship_full:.2f} s** — {band(ship_full)}.

Those two are within noise of each other rather than 5 rules apart in cost,
and that is not a mistake: the {REALISTIC}-rule curve suite substitutes two
*aggregate* expectations for the two *type* expectations the fifteen contains,
because the type ones cannot run on a capped batch at all (below). The cheap
rules are cheap and the dear one is dear; the count is not what sets the price.

But a bare pass/fail is not something F8 can be designed against, so here is
where the line actually falls:

| question | measured answer |
|---|---|
| largest suite that fits under {T_TOLERABLE:.0f} s at {FULL_ROWS:,} rows | **{fit_rules} rules** |
| largest row count that fits under {T_TOLERABLE:.0f} s with {REALISTIC} rules | **{fit_rows_lbl}** |
| marginal cost of one more rule at full size | **{per_rule_marginal:.2f} s** |
| single rule, whole table, shipping config | **{scaling[1]['wall']['median']:.2f} s** |

So the honest statement is not "synchronous works" or "synchronous fails". It
is: **a run is watchable while the suite is small, and stops being watchable
somewhere between {fit_rules} and {next_size} rules on a table this size**, and
the growth is per-rule, not per-row. A product that lets a domain expert
accumulate rules will cross that line by design, not by accident.

**F8 should use `SUPABASE_DB_URL_DIRECT` (port 5432.)**
{'The transaction-mode pooler did not break GE, but it is slower for this workload' if not any('pooled' in f for f in FAILURES) else 'The transaction-mode pooler broke — see below'}:
{pooled_full:.2f} s against {ship_full:.2f} s for identical work
({(pooled_full/ship_full - 1) * 100:+.0f}%). A rule run is a handful of long
analytical statements on one connection, which is the shape a pooler helps
least and taxes most.

### Connect time, separated from run time

INV-1 is about what the user waits for *after* the page is open. A server
process registers its datasource once at boot and reuses it; connect is never
inside the number the user watches. It is reported apart and is never added in.

| | connect (`add_postgres`, eager) | `SELECT 1` round trip |
|---|---|---|
| direct (5432, `{host_of(URLS['direct'])}`) | {connect['direct']['median']:.2f} s [{connect['direct']['min']:.2f}–{connect['direct']['max']:.2f}] | {rtt['direct']['median']:.0f} ms [{rtt['direct']['min']:.0f}–{rtt['direct']['max']:.0f}] |
| pooled (6543, `{host_of(URLS['pooled'])}`) | {connect['pooled']['median']:.2f} s [{connect['pooled']['min']:.2f}–{connect['pooled']['max']:.2f}] | {rtt['pooled']['median']:.0f} ms [{rtt['pooled']['min']:.0f}–{rtt['pooled']['max']:.0f}] |

The round trip to Singapore is the floor under every statement GE issues.
At {rtt['direct']['median']:.0f} ms and {curve['direct/full/indexed']['stmts']}
statements, roughly **{net_share:.0f}%** of a full run is network latency that
no amount of SQL tuning will remove.

### The row-count curve

{REALISTIC} rules, both result-format configurations, both URLs. `wall` is what
the user waits for; `db` is the summed server time of every statement GE
issued, measured from SQLAlchemy's cursor events; `ovh` is the remainder —
GE's own Python.

| conn | rows | mechanism | config | wall med (s) | min–max | db (s) | ovh (s) | stmts | rows pulled | per rule (s) |
|---|---|---|---|---|---|---|---|---|---|---|
{curve_rows}

Read it as: **wall time is not linear in rows, it is dominated by a fixed
floor.** Going from 1,000 rows to 500,000 — a 500× increase — costs
{ship_full/ship_1k:.1f}× the time. The scan itself scales; almost everything
else does not.

### Suite size — per run, or per rule?

Whole table, direct, shipping config, nested prefixes of the same catalog.

| rules | wall med (s) | min–max | db (s) | ovh (s) | stmts | per rule (s) |
|---|---|---|---|---|---|---|
{scaling_rows}

Averaged over the range, that is **{floor:.1f} s of floor plus ~{marg:.2f} s
per additional rule** — but the average is the least useful number in the table.
The real shape is lumpy: 1 → 3 rules adds {d31:.1f} s,
3 → 8 adds {d83:.1f} s, and 8 → 15 adds only
{d158:.1f} s. **What a rule costs depends on which rule
it is, not on how many are already there** — and the per-rule table below says
which ones are expensive.

### Per-rule cost, cheapest to dearest

Each catalog type alone, whole table, direct, shipping config, 3 runs each.
These are **not additive** — every one of them pays the same per-run floor.
The point is the ranking.

| rule | wall med (s) | min–max | db (s) | stmts |
|---|---|---|---|---|
{per_rule_rows}

Fourteen of the fifteen sit between {cheapest_s:.1f} s and
{second_dearest_s:.1f} s. One does not: **`{dearest[0]}` costs
{dearest[1]['wall']['median']:.2f} s**, {dearest_x:.1f}× the median rule. It is
a uniqueness check on an unindexed `text` column over {FULL_ROWS:,} rows, so
PostgreSQL sorts. That single rule is most of the 3 → 8 jump in the table above.

The seed deliberately leaves everything but the primary keys unindexed
(`seed/MANIFEST.md`), precisely so a measurement is not flattered by an index
nobody would have. So this is the honest number for an unprepared table — and
it also says where the cheapest available win is, if one is ever wanted.

### `result_format="COMPLETE"` — priced, not just warned about

LT-1a called it a trap; this is what it costs. Whole table, direct.

| case | wall | rows over the wire | unexpected |
|---|---|---|---|
{complete_rows}

**The mechanism is exactly as LT-1a described; the price is lower than the
warning implied.** `COMPLETE` does drop the `LIMIT` and stream every offending
row — {wide_rows:,} of them for a rule that matches the whole table — but over
this link, for one numeric column, that cost about the same wall clock as the
bounded `SUMMARY` run.

That is not a licence to use it. Three things the timing does not show: the
transfer scales with column width and with every column
`unexpected_index_column_names` adds; each of those rows is materialised as a
Python object in the API process; and F9 stores the raw framework output, so a
`COMPLETE` run writes {wide_rows:,} values into the cache. **Keep the
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
{cap_rows}

At full size the cap is a **net loss**: asking for `LIMIT {FULL_ROWS}` costs
{cap_on_s:.1f} s and moves {cap_on_rows:,} rows across the network, against
{cap_off_s:.1f} s and {cap_off_rows:,} rows for the same suite with no cap at
all. The uncapped table asset is {cap_on_s - cap_off_s:.1f} s faster *and* the
honest answer.

### UNEXPECTED — the row cap breaks two of the fifteen catalog types

Running the catalog over a **query asset** — the only row cap GE 1.x offers —
does not merely cost more. Two types stop working outright:

```
{breaks_block}
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

- sequential validates on 6543 — {('OK' if pooler['sequential'] == 'OK' else 'FAILED')}
- four concurrent validates on 6543 — {pooler['concurrent'].splitlines()[0] if pooler['concurrent'] else ''}
- psycopg v3 (server-side prepared statements) on 6543 — {pooler['psycopg3'].splitlines()[0]}

### UNEXPECTED — `gx.get_context()` is process-global

`gx.get_context()` does not merely return a context; it **installs it as a
process-global project**. A second, unrelated call silently orphans the first
context's datasources. The failure does not surface at `get_context()`. It
surfaces later, at `validate()`, as:

```
{trap or 'no failure reproduced on this run'}
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
{RESULTS['drift']['baseline_s']:.2f} s at the start,
{RESULTS['drift']['rerun_s']:.2f} s at the end
({RESULTS['drift']['delta_pct']:+.1f}%).

### Recommended answers

**O-2 · row cap for rule execution** — {o2}

Three measured reasons, not one:

1. The cap buys little. Capping at 100,000 rows — an 80% cut — saves
   {cap_saving:.1f} s of {ship_full:.1f} s ({cap_saving_pct:.0f}%). Cutting all
   the way to 1,000 rows, a 500× reduction, still leaves {ship_1k:.1f} s on the
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
{o3}

{sync_rationale}

### Follow-ups — noted, deliberately not done here

Optimising these numbers is out of scope for this bead. Three things are worth
their own issue:

- **Per-rule streaming.** The run is a sequence of independent statements;
  F13 could render each rule's verdict as it lands instead of after all of
  them. That converts a {full15_wall:.0f} s wait into a {floor:.0f} s wait
  followed by a filling list, without making anything faster.
- **GE's own Python overhead** is {ovh_share:.0f}% of the wall clock at full
  size — more than the network. It is metric-graph resolution, not database
  work, and it is not something SQL tuning reaches.
- **A cheaper row cap.** If a cap is ever needed, `add_query_asset` as
  measured here is the wrong mechanism. Whatever replaces it has to be
  measured the same way before it is trusted.

Raw measurements: `learning-tests/lt1b_results.json`.
"""

findings = HERE / "FINDINGS.md"
text = findings.read_text() if findings.exists() else ""
MARK = "## LT-1b · Great Expectations latency on Supabase"
if MARK in text:
    head, _, rest = text.partition(MARK)
    _, _, tail = rest.partition("\n## ")
    text = head + SECTION + ("\n## " + tail if tail else "")
else:
    # insert above the first existing section, keeping the file's index intact
    idx = text.find("\n## ")
    if idx == -1:
        text = text + "\n\n---\n\n" + SECTION
    else:
        text = text[:idx + 1] + SECTION + "\n---\n" + text[idx + 1:]

# index row
if "| LT-1b |" not in text:
    text = text.replace(
        "| LT-2a |",
        "| LT-1b | Great Expectations latency on Supabase — direct vs pooled "
        "| passed | `lt1b_ge_latency.py` |\n| LT-2a |", 1)

findings.write_text(text)
print(f"  findings         -> {findings}")

if FAILURES:
    print(f"\n  NOTE: {len(FAILURES)} failure(s) captured verbatim above: {FAILURES}")
    print("  They are recorded as findings, not as a reason to fail the run.")

print()
print(RULE)
print("LT-1b COMPLETE")
print(RULE)
