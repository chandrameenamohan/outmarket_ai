"""F10 · the Table Explorer, asserted in the browser against the running app.

One screen, five checks, and each owns a different way the screen can be wrong:

  ORDER        the three buckets appear in the prescribed sequence in DOCUMENT order,
               and the rows inside them are the sequence the server handed over. This
               screen's whole argument is its ranking, and a component that re-sorted
               would leave every other check here green.
  DERIVATION   a table whose last run errored or was sampled is in the middle bucket
               and in neither of the others — including bucket one, which is the
               winning mockup's own defect (design/ux-variant-workbench.html files
               `customers` under "never run" while holding a run record for it).
  ABSENCE      the engineer's columns are not in the domain expert's DOM at all.
  SELECTION    selecting a table opens its RULES, not its results.

WHY THIS IS ITS OWN FILE. `test_ui_behaviour.py` is the route-and-role map across four
features; this is one screen asserted from five directions, and the same split already
happened for F11's queue and F13's dashboard.

WHAT IS NOT ASSERTED HERE, on purpose: which table SHOULD be in which bucket for a given
record shape. That is `tests/test_table_coverage.py`, which is pure, runs in `make check`
and can lay out the cases the demo's three tables cannot express — including the one a
status-only derivation gets wrong, a FAILED run with an errored rule inside it.
"""

from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

import pytest

from app.dq import status
from conftest import Driver, choose_role

pytestmark = pytest.mark.e2e

# What `seed/seed_demo_data.py` planted, as `seed/MANIFEST.md` records it. Written here
# rather than read from the schema, because reading the schema is the thing under test.
DEMO_TABLES = frozenset({"customers", "orders", "payments"})


def _path(driver: Driver) -> str:
    """Where the browser actually is, with the origin and any query stripped off."""
    return urlparse(driver.page.url).path


def _coverage(api_url: str) -> dict:
    """F10's payload straight from the server, as the source of truth for what should render.

    Read over HTTP for the reason every check here reads over HTTP: the screen is only
    real if the thing behind it is, and comparing the DOM against a payload composed by
    `app/dq/coverage.py` is what makes "the page renders what it was given" an assertion
    rather than a hope. Nothing in this file re-derives a bucket, an order or an atom.
    """
    with urllib.request.urlopen(f"{api_url.rstrip('/')}/tables", timeout=60) as body:
        return dict(json.load(body))


def _rows(driver: Driver, bucket: str) -> list[str]:
    """The table names rendered inside one bucket, in DOM order."""
    return [
        row.get_attribute("data-table") or ""
        for row in driver.page.query_selector_all(f"[data-bucket='{bucket}'] tbody [data-table]")
    ]


def test_tables_buckets_render_in_the_prescribed_dom_order(driver, api_url, coverage_records):
    """never run -> ran, but unverifiable -> verified, read off the DOM in document order.

    DOM order and not CSS order, because the ordering IS the feature: this screen argues
    that the least trustworthy table is the first thing you see, and a stylesheet that
    reordered it would leave every other check in this file green. `query_selector_all`
    returns document order, so the list below is what a screen reader and a `curl` both
    get — not what a viewport happens to show.

    All three buckets are asserted present, empty ones included. A page that rendered
    only its populated buckets could satisfy an ordering check by having one, and
    "nothing here is verified" is the loudest thing this screen can say.
    """
    choose_role(driver, "engineer")
    driver.goto("/tables")
    driver.page.wait_for_load_state("networkidle")

    rendered = [
        s.get_attribute("data-bucket") for s in driver.page.query_selector_all("[data-bucket]")
    ]
    assert rendered == list(status.BUCKET_IDS), (
        f"the buckets rendered as {rendered}. The prescribed order is {list(status.BUCKET_IDS)} — "
        "no evidence, then evidence that proves nothing, then a verdict — and the ordinal in "
        "each heading claims that order out loud."
    )
    headings = driver.page.inner_text("body")
    missing = [b["heading"] for b in _coverage(api_url)["buckets"] if b["heading"] not in headings]
    assert not missing, (
        f"the screen renders bucket sections with no headings on them: {missing}. The headings "
        "are written once in app/dq/status.py and travel in the payload; a section identified "
        "only by a data attribute is a ranking nobody reading the page can see."
    )


def test_an_errored_or_sampled_table_lands_in_bucket_two(driver, api_url, coverage_records):
    """A result exists and a verdict does not — so the row is in bucket two, and nowhere else.

    The record behind it is seeded (see `conftest.coverage_records`): the shipped
    configuration cannot produce this bucket, because the row cap is off and no demo
    table makes a catalog rule blow up. Both halves are on one record — a rule that
    errored AND a partial scan — so this also proves the two independent routes into the
    middle bucket land in the same place.

    THE THIRD ASSERTION IS THE MOCKUP'S DEFECT. `design/ux-variant-workbench.html` files
    `customers` under "never run" while holding a run record for it; that is only
    possible where the bucket is typed rather than derived, so the check is that the same
    table cannot be in bucket one while a record for it exists.
    """
    seeded = "customers"
    record = coverage_records[seeded]
    assert record.status == "errored" and record.scanned_rows < record.total_rows, (
        f"the fixture did not produce the case under test: {record.status!r}, "
        f"{record.scanned_rows} of {record.total_rows} rows"
    )

    choose_role(driver, "engineer")
    driver.goto("/tables")
    driver.page.wait_for_load_state("networkidle")

    assert seeded in _rows(driver, "unverifiable"), (
        f"{seeded}'s last run errored on a partial scan and it is not in the middle bucket. "
        f"Rendered there: {_rows(driver, 'unverifiable')}"
    )
    assert seeded not in _rows(driver, "verified"), (
        f"{seeded} is filed under a real verdict. A rule that could not run left a hole, and a "
        "run with a hole in it has not verified the table — that is what the third state is for."
    )
    assert seeded not in _rows(driver, "never-run"), (
        f"{seeded} is filed under 'never run' while record {record.record_id} exists for it. "
        "That is the winning mockup's own defect, and the bucket must come from the record."
    )
    atom = driver.page.query_selector(f"[data-table='{seeded}'] [data-status-atom]")
    assert atom is not None and atom.inner_text() == record.atom, (
        f"the row's verdict reads {atom and atom.inner_text()!r}; the record says {record.atom!r}. "
        "The atom is composed once, server-side, and rendered — never recomposed here."
    )


def test_the_front_door_lists_the_demo_dataset_and_nothing_else(driver, api_url, coverage_records):
    """The engineer is invited to care about the seeded tables, and about nothing else.

    `lt1a_probe` — a 100-row leftover from learning test LT-1a — reached the deployed
    coverage screen as a fourth row (bead dq-5da). The demo dataset is a deliberate
    artefact (`seed/MANIFEST.md`, SPEC F15), and a probe wandering into it makes the
    whole thing read as somebody's scratch database rather than as a case study.

    ASSERTED ON THE DOM AND NOT ON THE PAYLOAD, which is the one thing this layer can
    add: `test_zero_coverage_tables_sort_first` already pins the screen to what the
    server sent, and `tests/test_schema_discovery.py` pins the server to the three
    seeded tables. This is the end of that chain — what a person actually sees — and
    it fails if the exclusion is lost at either end.

    An equality, so it fails on a missing table as loudly as on an extra one: a filter
    that hid the demo would otherwise be the quietest possible pass.
    """
    choose_role(driver, "engineer")
    driver.goto("/tables")
    driver.page.wait_for_load_state("networkidle")

    rendered = {name for bucket in status.BUCKET_IDS for name in _rows(driver, bucket)}
    assert rendered == DEMO_TABLES, (
        f"the front door lists {sorted(rendered)}; the seeded demo is {sorted(DEMO_TABLES)}. "
        "A table nobody planted is a table the engineer is being asked to vouch for by "
        "mistake — and a missing one is a coverage view with a hole in it."
    )


def test_zero_coverage_tables_sort_first(driver, api_url, coverage_records):
    """SPEC F10's default sort, asserted where it can actually be lost: in the component.

    The ORDER is decided in `app/dq/coverage.py::arrange` and pinned there by
    `tests/test_table_coverage.py::test_zero_coverage_tables_sort_first_inside_every_bucket`,
    which lays out a set where coverage and size disagree — the demo's three tables cannot
    express that case, so asserting it here would mean asserting it against data that does
    not contain it. What this check owns is the other half, and it is the half a screen
    breaks: that the page renders the sequence it was handed, table for table, and never
    re-sorts. A `.sort()` in the component is invisible to every other check in this file.
    """
    choose_role(driver, "engineer")
    driver.goto("/tables")
    driver.page.wait_for_load_state("networkidle")

    payload = _coverage(api_url)
    served = {b["id"]: [row["table"] for row in b["tables"]] for b in payload["buckets"]}
    rendered = {bucket: _rows(driver, bucket) for bucket in status.BUCKET_IDS}
    assert rendered == served, (
        f"the screen shows {rendered}; the server ordered {served}. The default sort is the "
        "whole argument of this screen, and a component that re-sorts is a second opinion "
        "about which table is least trustworthy."
    )
    assert any(served.values()), (
        "no table rendered at all, so the ordering was asserted against an empty page. The "
        "connected schema has tables; if it does not, this check is passing on nothing."
    )
    for bucket in status.BUCKET_IDS:
        listed = [
            (row["table"], row["accepted_rules"]) for row in _bucket(payload, bucket)["tables"]
        ]
        counts = [count for _, count in listed]
        assert counts == sorted(counts, key=lambda n: n > 0), (
            f"bucket {bucket} put a covered table above an uncovered one: {listed}. A table "
            "nobody has written a rule for is the least trustworthy thing on the screen."
        )


def test_expert_view_omits_engineer_columns_from_the_dom(driver, api_url, coverage_records):
    """F11 · the domain expert's document does not contain the table list. At all.

    Not restyled, not collapsed, not `display: none` — absent, which is the amendment
    SPEC 0.4 made to F12 applied to the screen next door. The winning mockup hid its
    configuration pane with a stylesheet, and a stylesheet is a promise the DOM can
    break: view-source, a screen reader and a text browser all see through it.

    The second half is what stops this passing on a page that renders nothing at all:
    the same address, in the engineer's view, must carry every one of the things asserted
    absent above. An absence check with no matching presence check is green on a 500.

    The expert is CHOSEN here rather than assumed: since bead dq-1rp a cold context is
    the engineer's view (the demo opens open), so the conservative document this check
    walks is the one a device gets after saying so in the header.
    """
    choose_role(driver, "expert")
    driver.goto("/tables")
    driver.page.wait_for_load_state("networkidle")
    assert _path(driver) == "/tables", (
        f"the domain expert was redirected to {_path(driver)}. One address renders differently "
        "for the two views; it does not send them to different places, or a pasted link "
        "carries the sender's role to the receiver (F14)."
    )

    engineer_only = "[data-bucket], [data-table], [data-status-atom], table.explorer"
    assert driver.page.query_selector_all(engineer_only) == [], (
        "the engineer's coverage columns are in the domain expert's document. F11: a domain "
        "expert never encounters a table list, and table names are context rather than navigation."
    )
    body = driver.page.inner_text("body")
    named = [row["table"] for b in _coverage(api_url)["buckets"] for row in b["tables"]]
    assert named and not [t for t in named if t in body], (
        f"table names reached the page anyway: {[t for t in named if t in body]}. This view does "
        "not call the coverage endpoint, so a name on it came from somewhere it should not have."
    )

    choose_role(driver, "engineer")
    driver.goto("/tables")
    driver.page.wait_for_load_state("networkidle")
    assert driver.page.query_selector_all(engineer_only), (
        "the same URL renders no coverage columns for the engineer either, so the check above "
        "proved nothing. The two views differ; they are not both empty."
    )


def test_selecting_a_table_navigates_to_its_rules(driver, api_url, coverage_records):
    """SPEC F10's one interaction: 'Selecting a table opens its rules.'

    Not its run record, and not a detail panel. The engineer's next move on a row is to
    change what is checked, so the table name is a link to F12 — the run record is a
    separate column with its own address, and a screen where the name led to results
    would make the coverage dashboard a results browser.
    """
    choose_role(driver, "engineer")
    driver.goto("/tables")
    driver.page.wait_for_load_state("networkidle")

    row = driver.page.query_selector("[data-table]")
    assert row is not None, "no table row to select; the dashboard rendered nothing to click"
    table = row.get_attribute("data-table")
    driver.page.click(f"[data-table='{table}'] a")

    # `wait_for_url` and not `wait_for_load_state`: a `next/link` transition never loads a
    # document, so "the network went quiet" is already true one millisecond after the
    # click and would have this check reading the address of the page it just left. The
    # timeout is the assertion — a click that goes nowhere spends it and then says so.
    from playwright.sync_api import TimeoutError as Timeout  # noqa: PLC0415 — see tests/conftest.py

    try:
        driver.page.wait_for_url(f"**/tables/{table}/rules", timeout=15_000)
    except Timeout:
        pass
    assert _path(driver) == f"/tables/{table}/rules", (
        f"selecting {table} landed on {_path(driver)}. F10 opens the table's RULES; anything "
        "else makes this screen a database browser, which is the thing it is defined against."
    )


def _bucket(payload: dict, bucket: str) -> dict:
    return next(b for b in payload["buckets"] if b["id"] == bucket)
