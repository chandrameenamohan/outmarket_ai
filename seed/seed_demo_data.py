"""
SEED — bulk demo dataset with documented, deliberate defects.

WHY THIS EXISTS
    SPEC F15: "a single command creates orders, customers and payments in a
    fresh database and populates them with realistic data containing known
    quality problems ... so the demo's outcome is verifiable rather than
    anecdotal." A clean database makes a working product look broken.

    It is also the prerequisite for LT-1b (dq-e1d): GE latency cannot be
    measured against an empty table. 500K orders rows, not the 2.4M quoted in
    the SPEC narrative — the Supabase free tier is 500 MB and 500K is ample to
    measure latency behaviour.

    The manifest this prints is the ground truth that later proves the rule
    engine finds what is actually there. Committed as seed/MANIFEST.md so the
    counts are readable without running anything.

WHAT IT DOES
    1. DROPs and recreates customers / orders / payments  (this is the
       idempotency mechanism — see below).
    2. Generates every row from a fixed RNG seed, so the bytes are identical
       on every run.
    3. Bulk-loads with COPY ... FROM STDIN via psycopg's copy(), not INSERTs.
    4. Runs one verification query returning the observed count of each
       planted defect, and asserts it equals the manifest.
    5. Prints per-table sizes, total DB size vs the 500 MB free tier, and the
       wall-clock load time.

IDEMPOTENCY
    Re-running produces the same state, not doubled rows, because the script
    drops and rebuilds from a deterministic generator (SEED = 20260816). Proof
    is a content fingerprint: md5 over every row of each table, in primary-key
    order, computed server-side with the session timezone pinned to UTC.
    `--fingerprint` prints it without touching the data; two runs that print
    the same three hashes are byte-identical.

DELIBERATELY MISSING CONSTRAINTS
    orders.customer_id and payments.order_id are NOT foreign keys, and
    orders.order_reference / customers.email are NOT unique. A constraint
    would make the corresponding defect impossible to plant. That is the
    point: this is a dirty warehouse-style landing table, not an OLTP schema.

FINDINGS — run 2026-08-16, PostgreSQL 17.6, Supabase ap-southeast-1
    [x] 1,050,000 rows bulk-loaded in 23.3 s wall (39K orders rows/s) over
        COPY from a laptop to Singapore. Loading is not the bottleneck.
    [x] 121 MB total = 24.1% of the 500 MB free tier. Room to grow ~4x if a
        larger table is ever wanted for LT-1b.
    [x] All 13 planted defect counts verified against the manifest, twice.
    [x] Idempotent: two full runs produced identical per-table content
        fingerprints and identical row counts.
    [!] THE FINDING WORTH CARRYING FORWARD — only 8 of the 13 defect classes
        can be expressed at all by the v1 single-column curated catalog.
        Four are cross-column or cross-table (shipped-before-ordered, both
        orphan foreign keys, payment/order amount reconciliation) and one
        needs a row_condition. A demo that only runs single-column rules
        will show a "clean" table that has 1,280 known-bad rows in it. That
        is a product honesty problem, not just a scope note — SPEC's
        multi-column deferral needs to be visible in the UI.

RUN
    cp ../.env .env                   # needs SUPABASE_DB_URL_DIRECT
    uv run --with psycopg[binary] python seed/seed_demo_data.py
    # or, if psycopg is already importable:
    python3 seed/seed_demo_data.py
    python3 seed/seed_demo_data.py --verify-only    # re-check, do not reseed
    python3 seed/seed_demo_data.py --fingerprint    # idempotency hashes
    python3 seed/seed_demo_data.py --manifest       # regenerate MANIFEST.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import pathlib
import random
import sys
import time
from array import array

import psycopg

# --- env -------------------------------------------------------------------

for _line in pathlib.Path(".env").read_text().splitlines():
    if "=" in _line and not _line.strip().startswith("#"):
        _k, _, _v = _line.partition("=")
        os.environ.setdefault(_k.strip(), _v.strip())

DB_URL = os.environ.get("SUPABASE_DB_URL_DIRECT")
assert DB_URL, "SUPABASE_DB_URL_DIRECT not in .env"

# --- scale -----------------------------------------------------------------

SEED = 20260816
N_CUSTOMERS = 50_000
N_ORDERS = 500_000
N_PAYMENTS = 500_000  # exactly one per order, so "amount = order_total" is a clean invariant

UTC = dt.timezone.utc
ANCHOR = dt.datetime(2026, 8, 16, tzinfo=UTC)  # "today" for the generated history
HISTORY_START = dt.datetime(2024, 1, 1, tzinfo=UTC)
HISTORY_SECONDS = int((ANCHOR - HISTORY_START).total_seconds())

FREE_TIER_BYTES = 500 * 1024 * 1024

# --- domain vocabulary -----------------------------------------------------

VALID_ORDER_STATUS = ["pending", "paid", "shipped", "delivered", "cancelled", "returned"]
ORDER_STATUS_WEIGHTS = [6, 10, 18, 55, 7, 4]
BOGUS_ORDER_STATUS = ["shippd", "SHIPPED", "compelted", "in transit"]

VALID_PAYMENT_METHOD = ["card", "paypal", "bank_transfer", "apple_pay", "gift_card"]
PAYMENT_METHOD_WEIGHTS = [62, 18, 9, 8, 3]
BOGUS_PAYMENT_METHOD = ["cred_card", "PAYPAL", "chq", "Card "]

VALID_PAYMENT_STATUS = ["captured", "refunded", "failed", "pending"]

CURRENCIES = ["USD", "EUR", "GBP", "SGD", "INR"]
CHANNELS = ["web", "mobile_app", "marketplace", "phone"]
COUNTRIES = ["US", "GB", "DE", "FR", "IN", "SG", "AU", "CA", "JP", "BR"]
TIERS = ["bronze", "silver", "gold", "platinum"]

FIRST_NAMES = [
    "amara", "brian", "chloe", "diego", "elena", "farid", "grace", "hiro",
    "ines", "jonas", "kavya", "liam", "maya", "noah", "olga", "priya",
    "quentin", "rosa", "sanjay", "tara", "umar", "vera", "wei", "ximena",
    "yusuf", "zara", "adam", "bella", "cai", "dara",
]
LAST_NAMES = [
    "okafor", "nakamura", "silva", "kaur", "novak", "haddad", "petrov",
    "lindqvist", "moreau", "rossi", "gupta", "oconnor", "vargas", "ahmed",
    "kowalski", "santos", "muller", "tanaka", "bianchi", "dubois",
    "fernandez", "hansen", "iyer", "jensen", "kim", "lopez", "mbeki",
    "nguyen", "olsen", "park",
]
DOMAINS = ["example.com", "mailbox.test", "shopmail.co", "inbox.example.org"]

# --- the manifest: exactly what is planted, and how much of it -------------
#
# Each entry: id -> (table, human description, planted count, SQL predicate
# that counts it, and whether the v1 single-column catalog (SPEC O-1) can
# express it at all).
#
# The "reach" column is a finding in its own right: four of these thirteen
# defects are cross-column or cross-table and CANNOT be caught by a
# single-column expectation, which is the v1 scope in HANDOFF §5.

MULTI = "needs multi-column / cross-table (v2)"
SINGLE = "v1 single-column catalog"
COND = "needs a row_condition (not plain single-column)"

DEFECTS: dict[str, dict] = {
    "D1": dict(
        table="orders", count=150, reach=SINGLE,
        expectation="expect_column_values_to_be_between(order_total, min=0)",
        desc="negative order_total — a sale that took money back",
        sql="SELECT count(*) FROM orders WHERE order_total < 0",
    ),
    "D2": dict(
        table="orders", count=320, reach=MULTI,
        expectation="pairwise A<=B (no single-column form)",
        desc="shipped_at earlier than ordered_at — shipped before it was ordered",
        sql="SELECT count(*) FROM orders WHERE shipped_at IS NOT NULL AND shipped_at < ordered_at",
    ),
    "D3": dict(
        table="orders", count=240, reach=SINGLE,
        expectation="expect_column_values_to_be_in_set(status, VALID_ORDER_STATUS)",
        desc="status values outside the vocabulary — typos and casing drift "
             f"({', '.join(BOGUS_ORDER_STATUS)})",
        sql="SELECT count(*) FROM orders WHERE NOT (status = ANY(%(valid_order_status)s))",
    ),
    "D4": dict(
        table="orders", count=90, reach=MULTI,
        expectation="referential integrity (no single-column form)",
        desc="orphan customer_id — order points at a customer that does not exist",
        sql="SELECT count(*) FROM orders o LEFT JOIN customers c USING (customer_id) "
            "WHERE c.customer_id IS NULL",
    ),
    "D5": dict(
        table="orders", count=60, reach=SINGLE,
        expectation="expect_column_values_to_be_between(ordered_at, max=now)",
        desc="ordered_at in the future — clock skew / bad import",
        sql="SELECT count(*) FROM orders WHERE ordered_at > now()",
    ),
    "D6": dict(
        table="orders", count=150, reach=SINGLE,
        expectation="expect_column_values_to_be_unique(order_reference)",
        desc="duplicate order_reference — 75 references issued twice (150 rows)",
        sql="SELECT coalesce(sum(n), 0) FROM (SELECT count(*) AS n FROM orders "
            "GROUP BY order_reference HAVING count(*) > 1) d",
    ),
    "D7": dict(
        table="customers", count=1200, reach=SINGLE,
        expectation="expect_column_values_to_not_be_null(email)",
        desc="missing customer email — cannot be contacted",
        sql="SELECT count(*) FROM customers WHERE email IS NULL",
    ),
    "D8": dict(
        table="customers", count=430, reach=SINGLE,
        expectation="expect_column_values_to_match_regex(email, RFC-ish)",
        desc="malformed email — no @, no domain dot, trailing @, embedded space",
        sql=r"SELECT count(*) FROM customers WHERE email IS NOT NULL "
            r"AND email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]{2,}$'",
    ),
    "D9": dict(
        table="customers", count=260, reach=SINGLE,
        expectation="expect_column_values_to_be_unique(email)",
        desc="duplicate customer email — 130 addresses held by two accounts (260 rows)",
        sql="SELECT coalesce(sum(n), 0) FROM (SELECT count(*) AS n FROM customers "
            "WHERE email IS NOT NULL GROUP BY email HAVING count(*) > 1) d",
    ),
    "D10": dict(
        table="payments", count=410, reach=MULTI,
        expectation="cross-table amount reconciliation (no single-column form)",
        desc="payment amount does not match its order_total",
        sql="SELECT count(*) FROM payments p JOIN orders o USING (order_id) "
            "WHERE p.amount <> o.order_total",
    ),
    "D11": dict(
        table="payments", count=200, reach=MULTI,
        expectation="referential integrity (no single-column form)",
        desc="orphan order_id — payment for an order that does not exist",
        sql="SELECT count(*) FROM payments p LEFT JOIN orders o USING (order_id) "
            "WHERE o.order_id IS NULL",
    ),
    "D12": dict(
        table="payments", count=180, reach=SINGLE,
        expectation="expect_column_values_to_be_in_set(method, VALID_PAYMENT_METHOD)",
        desc="payment method outside the vocabulary "
             f"({', '.join(repr(m) for m in BOGUS_PAYMENT_METHOD)} — note the "
             "trailing space on the last one)",
        sql="SELECT count(*) FROM payments WHERE NOT (method = ANY(%(valid_payment_method)s))",
    ),
    "D13": dict(
        table="payments", count=260, reach=COND,
        expectation="expect_column_values_to_not_be_null(paid_at) WHERE status='captured'",
        desc="captured payment with no paid_at — money taken, no timestamp",
        sql="SELECT count(*) FROM payments WHERE status = 'captured' AND paid_at IS NULL",
    ),
}

SQL_PARAMS = {
    "valid_order_status": VALID_ORDER_STATUS,
    "valid_payment_method": VALID_PAYMENT_METHOD,
}

# --- DDL -------------------------------------------------------------------
# No FKs on orders.customer_id / payments.order_id and no UNIQUE on
# order_reference / email: each would make a planted defect impossible.
# Only primary keys are indexed — extra indexes would inflate the footprint
# and distort the LT-1b latency measurement.

DDL = """
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id   integer       PRIMARY KEY,
    full_name     text          NOT NULL,
    email         text,                       -- nullable + not unique: D7, D8, D9
    signup_date   date          NOT NULL,
    country       text          NOT NULL,
    loyalty_tier  text          NOT NULL
);

CREATE TABLE orders (
    order_id        integer       PRIMARY KEY,
    order_reference text          NOT NULL,   -- deliberately NOT unique: D6
    customer_id     integer       NOT NULL,   -- deliberately NOT a foreign key: D4
    ordered_at      timestamptz   NOT NULL,
    shipped_at      timestamptz,
    status          text          NOT NULL,
    order_total     numeric(10,2) NOT NULL,
    currency        text          NOT NULL,
    channel         text          NOT NULL,
    ship_country    text          NOT NULL
);

CREATE TABLE payments (
    payment_id  integer       PRIMARY KEY,
    order_id    integer       NOT NULL,       -- deliberately NOT a foreign key: D11
    method      text          NOT NULL,
    amount      numeric(10,2) NOT NULL,
    status      text          NOT NULL,
    paid_at     timestamptz
);
"""

# --- generation ------------------------------------------------------------


def _pool(rng: random.Random, universe: int, sizes: list[int]) -> list[list[int]]:
    """Disjoint id sets, so every defect count is independently exact."""
    picked = rng.sample(range(1, universe + 1), sum(sizes))
    out, at = [], 0
    for size in sizes:
        out.append(picked[at : at + size])
        at += size
    return out


def gen_customers(rng: random.Random):
    d7, d8, d9 = _pool(rng, N_CUSTOMERS, [DEFECTS["D7"]["count"],
                                          DEFECTS["D8"]["count"],
                                          DEFECTS["D9"]["count"]])
    null_email = set(d7)
    bad_email = set(d8)
    # 130 pairs: the second account reuses the first account's address.
    dup_src = {d9[i + 1]: d9[i] for i in range(0, len(d9), 2)}

    def address(cid: int) -> str:
        first = FIRST_NAMES[cid % len(FIRST_NAMES)]
        last = LAST_NAMES[(cid // len(FIRST_NAMES)) % len(LAST_NAMES)]
        return f"{first}.{last}{cid}@{DOMAINS[cid % len(DOMAINS)]}"

    def malformed(cid: int) -> str:
        """Five ways an address can be wrong. Each stays unique, so a malformed
        address never accidentally lands in the duplicate-email count."""
        first = FIRST_NAMES[cid % len(FIRST_NAMES)]
        last = LAST_NAMES[(cid // len(FIRST_NAMES)) % len(LAST_NAMES)]
        local = f"{first}.{last}{cid}"
        return [
            local,                                  # no @ at all
            f"{local}@",                            # trailing @, no domain
            f"{local}@localhost{cid}",              # no dot in the domain
            f"{first} {last}{cid}@example.com",     # embedded space
            f"@{local}.example.com",                # no local part
        ][cid % 5]

    for cid in range(1, N_CUSTOMERS + 1):
        first = FIRST_NAMES[cid % len(FIRST_NAMES)]
        last = LAST_NAMES[(cid // len(FIRST_NAMES)) % len(LAST_NAMES)]
        if cid in null_email:
            email = None
        elif cid in bad_email:
            email = malformed(cid)
        elif cid in dup_src:
            email = address(dup_src[cid])
        else:
            email = address(cid)
        signup = dt.date(2022, 1, 1) + dt.timedelta(days=rng.randrange(0, 1642))
        yield (
            cid,
            f"{first.capitalize()} {last.capitalize()}",
            email,
            signup,
            COUNTRIES[rng.randrange(len(COUNTRIES))],
            TIERS[rng.randrange(len(TIERS))],
        )


def gen_orders(rng: random.Random, totals: array, ordered_epoch: array,
               status_ix: bytearray):
    sizes = [DEFECTS[k]["count"] for k in ("D1", "D2", "D3", "D4", "D5", "D6")]
    d1, d2, d3, d4, d5, d6 = _pool(rng, N_ORDERS, sizes)
    neg = set(d1)
    time_travel = set(d2)
    bad_status = set(d3)
    orphan = set(d4)
    future = set(d5)
    dup_ref = {d6[i + 1]: d6[i] for i in range(0, len(d6), 2)}  # 75 pairs

    for oid in range(1, N_ORDERS + 1):
        status = rng.choices(VALID_ORDER_STATUS, ORDER_STATUS_WEIGHTS)[0]
        ordered = HISTORY_START + dt.timedelta(seconds=rng.randrange(HISTORY_SECONDS))
        total = round(min(5000.0, max(5.0, math.exp(rng.gauss(3.6, 0.9)))), 2)
        customer_id = rng.randrange(1, N_CUSTOMERS + 1)
        reference = f"ORD-{oid:07d}"

        if status in ("shipped", "delivered", "returned"):
            shipped = ordered + dt.timedelta(seconds=rng.randrange(3600, 7 * 86400))
        else:
            shipped = None

        if oid in neg:
            total = -total
        if oid in bad_status:
            status = BOGUS_ORDER_STATUS[oid % len(BOGUS_ORDER_STATUS)]
        if oid in orphan:
            customer_id = N_CUSTOMERS + 1000 + (oid % 977)  # no such customer
        if oid in future:
            ordered = ANCHOR + dt.timedelta(days=30 + rng.randrange(370))
            shipped = None
        if oid in time_travel:
            # shipped before ordered: force a shipment, then reverse the arrow
            shipped = ordered - dt.timedelta(seconds=rng.randrange(3600, 20 * 86400))
        if oid in dup_ref:
            reference = f"ORD-{dup_ref[oid]:07d}"

        totals[oid - 1] = total
        ordered_epoch[oid - 1] = ordered.timestamp()
        status_ix[oid - 1] = (VALID_ORDER_STATUS.index(status)
                              if status in VALID_ORDER_STATUS else 255)

        yield (
            oid, reference, customer_id, ordered, shipped, status, total,
            CURRENCIES[rng.randrange(len(CURRENCIES))],
            CHANNELS[rng.randrange(len(CHANNELS))],
            COUNTRIES[rng.randrange(len(COUNTRIES))],
        )


def gen_payments(rng: random.Random, totals: array, ordered_epoch: array,
                 status_ix: bytearray):
    sizes = [DEFECTS[k]["count"] for k in ("D10", "D11", "D12", "D13")]
    d10, d11, d12, d13 = _pool(rng, N_PAYMENTS, sizes)
    mismatch = set(d10)
    orphan = set(d11)
    bad_method = set(d12)
    no_paid_at = set(d13)

    # Payment status follows the order's fate, so the data reads as coherent.
    by_order_status = {
        "pending": "pending", "paid": "captured", "shipped": "captured",
        "delivered": "captured", "cancelled": "failed", "returned": "refunded",
    }

    for pid in range(1, N_PAYMENTS + 1):
        order_id = pid
        amount = totals[pid - 1]
        ix = status_ix[pid - 1]
        order_status = VALID_ORDER_STATUS[ix] if ix != 255 else "delivered"
        status = by_order_status[order_status]
        method = rng.choices(VALID_PAYMENT_METHOD, PAYMENT_METHOD_WEIGHTS)[0]

        if status in ("captured", "refunded"):
            paid_at = dt.datetime.fromtimestamp(
                ordered_epoch[pid - 1] + rng.randrange(60, 3 * 86400), UTC
            )
        else:
            paid_at = None

        if pid in mismatch:
            # off by a plausible amount — a partial capture never reconciled
            amount = round(amount * rng.choice([0.5, 0.9, 1.1, 2.0]) + 0.01, 2)
            if amount == totals[pid - 1]:
                amount = round(amount + 1.13, 2)
        if pid in orphan:
            order_id = N_ORDERS + 1000 + (pid % 991)  # no such order
        if pid in bad_method:
            method = BOGUS_PAYMENT_METHOD[pid % len(BOGUS_PAYMENT_METHOD)]
        if pid in no_paid_at:
            status, paid_at = "captured", None

        yield (pid, order_id, method, amount, status, paid_at)


# --- load ------------------------------------------------------------------


def bulk_load(conn, table: str, columns: list[str], rows, expected: int) -> float:
    started = time.perf_counter()
    cols = ", ".join(columns)
    written = 0
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
                written += 1
                if written % 100_000 == 0:
                    print(f"    {table}: {written:,} rows "
                          f"({time.perf_counter() - started:.1f}s)", flush=True)
    conn.commit()
    elapsed = time.perf_counter() - started
    assert written == expected, f"{table}: generated {written}, expected {expected}"
    print(f"    {table}: {written:,} rows in {elapsed:.1f}s "
          f"({written / elapsed:,.0f} rows/s)")
    return elapsed


# --- verification ----------------------------------------------------------


def verify(conn) -> tuple[list[tuple], bool]:
    rows, ok = [], True
    with conn.cursor() as cur:
        for did, spec in DEFECTS.items():
            params = SQL_PARAMS if "%(" in spec["sql"] else None
            cur.execute(spec["sql"], params)
            observed = int(cur.fetchone()[0])
            match = observed == spec["count"]
            ok = ok and match
            rows.append((did, spec["table"], spec["desc"], spec["count"],
                         observed, match, spec["reach"], spec["expectation"]))
    return rows, ok


def fingerprint(conn) -> dict[str, str]:
    """Content hash per table. Two runs agreeing = byte-identical state."""
    out = {}
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")  # t::text must not depend on session tz
        for table, pk in (("customers", "customer_id"), ("orders", "order_id"),
                          ("payments", "payment_id")):
            cur.execute(
                f"SELECT md5(string_agg(md5(t::text), '' ORDER BY {pk})) FROM {table} t"
            )
            out[table] = cur.fetchone()[0]
    return out


def report_sizes(conn) -> None:
    with conn.cursor() as cur:
        print("\n  TABLE SIZES")
        for table in ("customers", "orders", "payments"):
            cur.execute(f"SELECT count(*) FROM {table}")
            n = cur.fetchone()[0]
            cur.execute("SELECT pg_size_pretty(pg_total_relation_size(%s)), "
                        "pg_total_relation_size(%s)", (table, table))
            pretty, raw = cur.fetchone()
            print(f"    {table:<10} {n:>9,} rows   {pretty:>10}  ({raw:,} bytes)")
        cur.execute("SELECT pg_database_size(current_database())")
        total = cur.fetchone()[0]
        pct = 100.0 * total / FREE_TIER_BYTES
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        print(f"    {'DATABASE':<10} {'':>9}        {cur.fetchone()[0]:>10}  "
              f"({total:,} bytes) = {pct:.1f}% of the 500 MB free tier")


# --- manifest --------------------------------------------------------------
#
# seed/MANIFEST.md is generated from the constants above by `--manifest`, so
# the committed ground truth cannot drift from what the script actually plants.

MEASURED = """\
| Measurement | Value |
|---|---|
| Bulk load, 1,050,000 rows | **23.3 s** wall (run 1), 23.8 s (run 2) |
| customers, 50,000 rows | 1.6 s — 30,322 rows/s |
| orders, 500,000 rows | 12.7 s — 39,407 rows/s |
| payments, 500,000 rows | 9.0 s — 55,708 rows/s |
| `ANALYZE` all three | 1.2 s |
| Verification, 13 queries | 3.7 s |
| Content fingerprint, 1.05M rows | 4.9 s |
| Connect (direct, 5432) | 0.78 s |
| **Total database size** | **121 MB — 24.1% of the 500 MB free tier** |
| customers / orders / payments | 6.0 MB / 61 MB / 44 MB (incl. PK indexes) |

Measured 2026-08-16 against PostgreSQL 17.6 on Supabase `ap-southeast-1`
(Singapore) from a laptop. Round-trip network time is included in every
number above and is expected; it is not worth chasing.
"""


def render_manifest() -> str:
    lines: list[str] = []
    w = lines.append
    w("# Demo dataset — defect manifest")
    w("")
    w("Ground truth for the seeded demo database. Generated by")
    w("`python3 seed/seed_demo_data.py --manifest` from the same constants the")
    w("seeder uses, so this file cannot silently drift from what is planted.")
    w("")
    w("This doubles as the ground truth that later proves the rule engine finds")
    w("what is actually there. If a rule run reports fewer than the counts below,")
    w("the engine has a gap — the manifest is not adjusted to match it.")
    w("")
    w("## Scale")
    w("")
    w("| Table | Rows |")
    w("|---|---|")
    w(f"| `customers` | {N_CUSTOMERS:,} |")
    w(f"| `orders` | {N_ORDERS:,} |")
    w(f"| `payments` | {N_PAYMENTS:,} (exactly one per order) |")
    w(f"| **total** | **{N_CUSTOMERS + N_ORDERS + N_PAYMENTS:,}** |")
    w("")
    w("500K orders, not the 2.4M quoted in the SPEC narrative: the Supabase free")
    w("tier is 500 MB and 500K is ample to measure GE latency behaviour (LT-1b).")
    w("")
    w("## Planted defects")
    w("")
    total = sum(s["count"] for s in DEFECTS.values())
    w(f"{len(DEFECTS)} defect classes, {total:,} defective rows in total.")
    w("Every defect occupies a disjoint set of primary keys, so each count is")
    w("independently exact — no row carries two defects.")
    w("")
    w("| ID | Table | Rows | Defect | Verified by |")
    w("|---|---|---|---|---|")
    for did, s in DEFECTS.items():
        sql = " ".join(s["sql"].split()).replace("|", r"\|")
        w(f"| **{did}** | `{s['table']}` | {s['count']:,} | {s['desc']} "
          f"| `{sql}` |")
    w("")
    w("## Can the v1 rule engine actually catch these?")
    w("")
    w("HANDOFF §5: v1 is single-column and table-level rules only; multi-column")
    w("is deferred to v2. Against that scope:")
    w("")
    w("| Reach | Count | Defects |")
    w("|---|---|---|")
    for reach in (SINGLE, COND, MULTI):
        ids = [d for d, s in DEFECTS.items() if s["reach"] == reach]
        rows = sum(DEFECTS[d]["count"] for d in ids)
        plural = "class" if len(ids) == 1 else "classes"
        w(f"| {reach} | {len(ids)} {plural} / {rows:,} rows | {', '.join(ids)} |")
    w("")
    missed = sum(s["count"] for s in DEFECTS.values() if s["reach"] != SINGLE)
    w(f"**{missed:,} known-bad rows are invisible to a purely single-column rule")
    w("set.** A demo that runs only v1 rules will call these tables cleaner than")
    w("they are. That is an argument for surfacing the multi-column gap in the")
    w("product, not for quietly dropping the defects.")
    w("")
    w("Mapping to the curated catalog (SPEC O-1, finalised by LT-2a):")
    w("")
    w("| ID | Expectation that would catch it |")
    w("|---|---|")
    for did, s in DEFECTS.items():
        w(f"| {did} | `{s['expectation']}` |")
    w("")
    w("## Vocabularies")
    w("")
    w(f"- Valid `orders.status`: {', '.join('`%s`' % v for v in VALID_ORDER_STATUS)}")
    w(f"- Planted invalid: {', '.join('`%s`' % v for v in BOGUS_ORDER_STATUS)}")
    w(f"- Valid `payments.method`: {', '.join('`%s`' % v for v in VALID_PAYMENT_METHOD)}")
    w(f"- Planted invalid: {', '.join('`%s`' % v for v in BOGUS_PAYMENT_METHOD)}")
    w(f"- Valid `payments.status`: {', '.join('`%s`' % v for v in VALID_PAYMENT_STATUS)}")
    w("")
    w("## Schema")
    w("")
    w("Note what is deliberately absent. `orders.customer_id` and")
    w("`payments.order_id` are not foreign keys; `orders.order_reference` and")
    w("`customers.email` are not unique. Each of those constraints would make a")
    w("planted defect impossible. Only primary keys are indexed — extra indexes")
    w("would inflate the footprint and distort the LT-1b latency measurement.")
    w("")
    w("```sql")
    w(DDL.strip())
    w("```")
    w("")
    w("## Measured")
    w("")
    w(MEASURED.strip())
    w("")
    w("## Idempotency")
    w("")
    w(f"The seeder drops and rebuilds all three tables from a fixed RNG seed")
    w(f"(`SEED = {SEED}`), so re-running produces the same bytes rather than")
    w("doubled rows. Proof is a per-table content fingerprint — md5 over every")
    w("row in primary-key order, session timezone pinned to UTC:")
    w("")
    w("```")
    w("customers  256cf549478c02a7192474eac6e70b99")
    w("orders     7b2f20d842bd4a4908d8ec8a625ea791")
    w("payments   100abbc4b03e55792ea1d2019d9827b4")
    w("```")
    w("")
    w("Two consecutive full runs on 2026-08-16 produced exactly these three")
    w("hashes and identical row counts. Reproduce with:")
    w("")
    w("```bash")
    w("python3 seed/seed_demo_data.py              # seed + verify")
    w("python3 seed/seed_demo_data.py --fingerprint")
    w("```")
    w("")
    w("Reported table sizes can wobble by a few kB between runs (6008 kB vs")
    w("6016 kB for `customers`) — that is page/free-space-map bookkeeping after")
    w("a drop-and-recreate, not a difference in the data. The fingerprints are")
    w("the authority.")
    w("")
    w("## Time-sensitive defect")
    w("")
    w("**D5** plants `ordered_at` between 30 and 400 days after the 2026-08-16")
    w("anchor, and is verified with `ordered_at > now()`. Its count decays if")
    w("the data is left in place for more than ~30 days. Re-seed before a demo.")
    w("")
    return "\n".join(lines)


# --- main ------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-only", action="store_true",
                    help="run the verification query against existing data")
    ap.add_argument("--fingerprint", action="store_true",
                    help="print per-table content hashes and exit")
    ap.add_argument("--manifest", action="store_true",
                    help="regenerate seed/MANIFEST.md from the constants and exit")
    args = ap.parse_args()

    if args.manifest:
        out = pathlib.Path(__file__).with_name("MANIFEST.md")
        out.write_text(render_manifest())
        print(f"wrote {out}")
        return 0

    print("=" * 78)
    print("SEED · demo dataset with deliberate defects")
    print(f"  target   : {DB_URL.split('@')[-1].split('/')[0]}")
    print(f"  scale    : {N_CUSTOMERS:,} customers · {N_ORDERS:,} orders · "
          f"{N_PAYMENTS:,} payments")
    print(f"  rng seed : {SEED} (deterministic — re-running rebuilds the same bytes)")
    print("=" * 78)

    connect_started = time.perf_counter()
    with psycopg.connect(DB_URL) as conn:
        print(f"connected in {time.perf_counter() - connect_started:.2f}s "
              f"(Supabase ap-southeast-1 — network latency is expected)")
        conn.execute("SET TIME ZONE 'UTC'")

        if args.fingerprint:
            for table, h in fingerprint(conn).items():
                print(f"  {table:<10} {h}")
            return 0

        load_total = 0.0
        if not args.verify_only:
            rng = random.Random(SEED)
            print("\n  DDL — dropping and recreating three tables")
            conn.execute(DDL)
            conn.commit()

            print("\n  BULK LOAD (COPY ... FROM STDIN)")
            load_total += bulk_load(
                conn, "customers",
                ["customer_id", "full_name", "email", "signup_date", "country",
                 "loyalty_tier"],
                gen_customers(rng), N_CUSTOMERS,
            )

            totals = array("d", bytes(8 * N_ORDERS))
            ordered_epoch = array("d", bytes(8 * N_ORDERS))
            status_ix = bytearray(N_ORDERS)
            load_total += bulk_load(
                conn, "orders",
                ["order_id", "order_reference", "customer_id", "ordered_at",
                 "shipped_at", "status", "order_total", "currency", "channel",
                 "ship_country"],
                gen_orders(rng, totals, ordered_epoch, status_ix), N_ORDERS,
            )
            load_total += bulk_load(
                conn, "payments",
                ["payment_id", "order_id", "method", "amount", "status", "paid_at"],
                gen_payments(rng, totals, ordered_epoch, status_ix), N_PAYMENTS,
            )
            print(f"    TOTAL LOAD: {load_total:.1f}s wall for "
                  f"{N_CUSTOMERS + N_ORDERS + N_PAYMENTS:,} rows")

            started = time.perf_counter()
            conn.execute("ANALYZE customers; ANALYZE orders; ANALYZE payments;")
            conn.commit()
            print(f"    ANALYZE: {time.perf_counter() - started:.1f}s")

        print("\n  VERIFICATION — planted vs observed")
        started = time.perf_counter()
        rows, ok = verify(conn)
        print(f"    (13 defect queries in {time.perf_counter() - started:.1f}s)\n")
        print(f"    {'ID':<5}{'TABLE':<11}{'PLANTED':>8}{'OBSERVED':>10}  {'':<4}"
              f"DEFECT")
        print("    " + "-" * 92)
        for did, table, desc, planted, observed, match, _reach, _exp in rows:
            print(f"    {did:<5}{table:<11}{planted:>8,}{observed:>10,}  "
                  f"{'ok' if match else 'FAIL':<4}{desc}")
        print("    " + "-" * 92)
        total_planted = sum(r[3] for r in rows)
        total_observed = sum(r[4] for r in rows)
        print(f"    {'':5}{'TOTAL':<11}{total_planted:>8,}{total_observed:>10,}")

        by_reach: dict[str, int] = {}
        for r in rows:
            by_reach[r[6]] = by_reach.get(r[6], 0) + 1
        print("\n  CATCHABLE BY THE v1 CURATED CATALOG?")
        for reach, n in sorted(by_reach.items()):
            print(f"    {n:>2} defect classes — {reach}")

        report_sizes(conn)

        print("\n  IDEMPOTENCY FINGERPRINT (rerun and compare)")
        started = time.perf_counter()
        for table, h in fingerprint(conn).items():
            print(f"    {table:<10} {h}")
        print(f"    (computed in {time.perf_counter() - started:.1f}s)")

        print("\n" + "=" * 78)
        if not ok:
            print("VERIFICATION FAILED — observed defect counts disagree with the "
                  "manifest.\nThat disagreement IS the finding. Do not relax the "
                  "manifest to make it pass.")
            return 1
        print("ALL 13 PLANTED DEFECT COUNTS MATCH THE MANIFEST")
        print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
