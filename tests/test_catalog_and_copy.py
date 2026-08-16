"""One catalog, one copy module — so the UI and the compiler cannot drift.

Design review caught one mockup shipping 15 catalog entries that did not map 1:1
onto real expectation types. A single data file makes that class of drift
impossible and gives the browser checks something exact to count.

Same argument for constant strings: the review-queue caveat sentence and the
neutral "Compiled · shape OK" copy live in one module, and the browser check
asserts against that module rather than a literal duplicated into the test.
A duplicated literal tests that two copies of a typo agree.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import pytest

from app.dq import status
from app.rules import catalog, validator
from conftest import REPO, source_files

CATALOG_SIZE = 15  # SPEC O-1, resolved by LT-2a: single-column + table-level, zero multi-column

# What SPEC.md said the `orders` table held before the seed settled at 500,000.
RETIRED_ROW_COUNT = "2,400,000"

# The two bases every excluded type inherits from. Exclusion is BY BASE CLASS: a
# name scan for "pair" or "multicolumn" would miss
# expect_select_column_values_to_be_unique_within_record, which is neither.
MULTI_COLUMN_BASES = ("ColumnPairMapExpectation", "MulticolumnMapExpectation")

# LT-1b: the `type` family reads the column type off the REFLECTED TABLE. Against
# a query asset — the only row cap GE 1.x offers — there is no reflected table and
# both raise a bare KeyError: 'type'. Because catch_exceptions defaults to True
# (LT-1a), that surfaces as two red rules with no offending rows and no reason,
# and the user goes hunting for a data problem that does not exist. The cap does
# not ship (SPEC O-2), so today this is a regression check, not a workaround.
#
# Read OFF THE CATALOG, not typed here: a sixteenth entry in this family needs a
# probe added below, and this is what makes that fail rather than pass quietly.
READS_A_REFLECTED_TABLE = tuple(e["type"] for e in catalog.ENTRIES if e["family"] == "type")

# The catalog's own module is exempt from the second-copy scans below, the same
# way app/dq/ge_runtime.py is exempt from INV-3's import scan and app/dq/status.py
# from INV-5's text scan: it is the designated home, and a check that bans its own
# subject's docstring is a check nobody can explain.
CATALOG_MODULE = pathlib.Path("app/rules/catalog.py")

# Production code, both languages. `web/app` is the Next route tree; it holds no
# node_modules. Tests are not scanned — this file names two types in a comment.
SCANNED = [p for p in source_files("app") if p.relative_to(REPO) != CATALOG_MODULE]
SCANNED += sorted((REPO / "web/app").rglob("*.tsx")) + sorted((REPO / "web/app").rglob("*.ts"))

A_TYPE_NAME = re.compile(r"\bexpect_[a-z_]+\b")
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _runtime() -> Any:
    """The GE door, imported lazily — same shape as tests/test_ge_runtime.py.

    A module-level import would make the framework a prerequisite for COLLECTING
    this file, and `make check` installs nothing. The `ge` marker deselects the
    checks below; it cannot deselect an import.
    """
    from app.dq import ge_runtime  # noqa: PLC0415

    return ge_runtime


def test_catalog_has_exactly_fifteen_entries() -> None:
    """SPEC O-1's number, pinned once, in the one place a literal 15 belongs.

    Production code never states the count — `test_catalog_length_is_read_from_one
    _source` fails the gate on one. This is the single check that ties the file to
    what the SPEC says was decided, so growing the catalog is a deliberate edit in
    two places rather than a drift in one.
    """
    assert len(catalog.ENTRIES) == CATALOG_SIZE, (
        f"the catalog holds {len(catalog.ENTRIES)} entries; SPEC O-1 settled on {CATALOG_SIZE}. "
        "Changing it means changing SPEC O-1 too."
    )
    assert len(set(catalog.TYPES)) == len(catalog.TYPES), (
        f"duplicate types in the catalog: "
        f"{sorted({t for t in catalog.TYPES if catalog.TYPES.count(t) > 1})}"
    )


def test_catalog_length_is_read_from_one_source() -> None:
    """The bug this bead exists to prevent: a second copy of the list, or of its length.

    Two dodges, because there are two ways to grow a second source of truth — the
    UI hardcoding `15` next to a heading, and the model prompt or validator
    carrying its own list of type strings. Either one drifts silently the first
    time the catalog changes; neither is caught by any other check here.

    ponytail: a text scan, like INV-3's and INV-5's. It catches the literal second
    copy, which is the failure that actually happens — someone types the number
    into a component because reaching for the payload felt like more work. It does
    not catch a count assembled at runtime. The upgrade path is the browser check
    in B20, which counts rendered rows against this file.
    """
    count = re.compile(rf"\b{len(catalog.ENTRIES)}\b")
    offenders = []
    for path in SCANNED:
        rel = path.relative_to(REPO)
        for i, line in enumerate(path.read_text().splitlines(), 1):
            named = [t for t in A_TYPE_NAME.findall(line) if t in catalog.TYPES]
            if named:
                offenders.append(f"{rel}:{i} names {named}")
            if "catalog" in line.lower() and count.search(line):
                offenders.append(f"{rel}:{i} hard-codes the catalog length: {line.strip()!r}")
    assert not offenders, (
        f"a second source for the catalog: {offenders}. {catalog.CATALOG_FILE.name} is the one "
        f"list and `len(ENTRIES)` is the one count — read {CATALOG_MODULE}, or in web/ render "
        "what the payload carries."
    )


def test_every_entry_has_an_english_template() -> None:
    """A catalog entry nobody can read is a menu item nobody can choose.

    Every type states itself in business language (F3's proposals, F12's screen,
    F4's confirmation), and the template's placeholders have to be parameters the
    rule actually carries — otherwise the rendered sentence either silently drops
    a `{brace}` into the UI or omits the value the rule turns on.
    """
    bad = []
    for e in catalog.ENTRIES:
        params = set(e["required"]) | set(e["optional"])
        placeholders = set(PLACEHOLDER.findall(e["english"]))
        if not e["english"].strip():
            bad.append(f"{e['type']}: no English template")
        if unknown := placeholders - params:
            bad.append(f"{e['type']}: template names {sorted(unknown)}, which are not parameters")
        if missing := set(e["required"]) - placeholders:
            bad.append(f"{e['type']}: template never mentions required {sorted(missing)}")
    assert not bad, bad
    templates = [e["english"] for e in catalog.ENTRIES]
    assert len(set(templates)) == len(templates), (
        "two catalog entries state themselves identically; a user choosing between them "
        f"cannot tell them apart: {sorted({t for t in templates if templates.count(t) > 1})}"
    )


def test_every_entry_carries_its_own_parameter_rules() -> None:
    """INV-2's real layer, as data. LT-2a: the framework checks shape, never sense.

    It accepted contradictory bounds, an uncompilable regex, an empty value set and
    a bogus SQL type name — 10 of 25 nonsense rules — so each entry names the sanity
    constraints that run BEFORE the framework ever sees the kwargs. The vocabulary
    is `validator.CHECKS` itself — the implementations, not a second declaration of
    their names — so a check named here that nothing implements is caught as a typo
    rather than surfacing later as a KeyError inside validate().

    The last assertion is the identifier seam: `validator._identifiers` verifies the
    kwarg named `column` and nothing else, which is complete for these fifteen and is
    a coincidence of the data rather than a checked property. A sixteenth entry
    taking `column_list` or `column_set` — both real GE 1.x kwargs — would receive no
    schema validation at all and every other check here would still pass.
    """
    bad = []
    for e in catalog.ENTRIES:
        if unknown := set(e["checks"]) - set(validator.CHECKS):
            bad.append(f"{e['type']}: unknown sanity check(s) {sorted(unknown)}")
        if both := set(e["required"]) & set(e["optional"]):
            bad.append(f"{e['type']}: {sorted(both)} declared both required and optional")
        if len(e["checks"]) != len(set(e["checks"])):
            bad.append(f"{e['type']}: repeats a sanity check")
    assert not bad, f"{bad}. The vocabulary is {sorted(validator.CHECKS)}."
    used = {c for e in catalog.ENTRIES for c in e["checks"]}
    assert not (dead := set(validator.CHECKS) - used), (
        f"{sorted(dead)} is implemented in the sanity vocabulary and no entry uses it. That is "
        "a constraint that can never fire."
    )

    identifiers = {k for e in catalog.ENTRIES for k in (*e["required"], *e["optional"])}
    assert {k for k in identifiers if k.startswith("column")} == {"column"}, (
        f"the catalog names identifier-valued kwargs {sorted(identifiers)}; "
        "app/rules/validator.py::_identifiers verifies `column` and only `column` against the "
        "live schema. Teach it the new one before the entry ships, or the identifier reaches "
        "the framework unverified (SPEC §3.1)."
    )


@pytest.mark.ge
def test_every_catalog_type_exists_in_the_framework_registry() -> None:
    """Guards against a curated entry that was renamed or removed by an upgrade.

    Goes through app/dq/ge_runtime.py (INV-3) — the test does not import the
    framework itself.
    """
    ge = _runtime()
    missing = sorted(set(catalog.TYPES) - set(ge.registry()))
    assert not missing, (
        f"{missing} are in the catalog and not in the installed framework's registry. Curated "
        "data goes stale on an upgrade; that is what this check is for."
    )


@pytest.mark.ge
def test_the_two_type_expectations_run_against_a_table_asset() -> None:
    """Pins the day someone reaches for a query asset again.

    Runs the two flagged types through app/dq/ge_runtime.py against a TABLE asset
    and asserts they produced a real verdict — `exception_info` shows nothing
    raised — rather than an errored rule wearing a failure's clothes. The
    assertion has to be on exception_info, not on success: an errored rule is
    `success: false` with `result: {}` and is otherwise indistinguishable from a
    genuine failure (LT-1a). Against a query asset both raise `KeyError: 'type'`,
    so this check is what would go red if the asset kind ever changed.

    Two rules, not the whole catalog: the other thirteen need no reflected table,
    so running them here would buy nothing and cost a scan each (LT-1b).

    Lives in the `ge` layer so `make check` never pays for a database round trip;
    it runs with the rest of the layer through `make check-ge`.
    """
    ge = _runtime()
    specs = [
        ge.construct("expect_column_values_to_be_of_type", {"column": "status", "type_": "TEXT"}),
        ge.construct(
            "expect_column_values_to_be_in_type_list",
            {"column": "status", "type_list": ["TEXT", "VARCHAR"]},
        ),
    ]
    assert sorted(s["type"] for s in specs) == sorted(READS_A_REFLECTED_TABLE), (
        f"this check must exercise exactly {sorted(READS_A_REFLECTED_TABLE)}; the family is "
        "read off the catalog, so an entry added there needs a probe added here"
    )

    report = ge.run("orders", specs, table="orders")
    raised = {
        r["expectation_config"]["type"]: r["exception_info"]
        for r in report["results"]
        if (r.get("exception_info") or {}).get("raised_exception")
    }
    assert not raised, (
        f"{sorted(raised)} raised against a TABLE asset: {raised}. These two read the column type "
        "off the reflected table; a bare KeyError: 'type' here is the query-asset failure LT-1b "
        "measured, rendered by catch_exceptions as a red rule with no reason."
    )
    observed = {
        r["expectation_config"]["type"]: r["result"].get("observed_value")
        for r in report["results"]
    }
    assert all(observed.values()), (
        f"the two type rules reported {observed}; a real verdict carries the observed column "
        "type, and an empty result is what an errored rule looks like"
    )


def test_catalog_excludes_every_multi_column_expectation() -> None:
    """The six pair/multicolumn types are v2. This is what makes F4's rejection honest.

    Offline half: no entry DECLARES a multi-column base. The declaration is a copy
    of a framework fact, so the copy is pinned next door in the `ge` layer — but
    the exclusion itself is checkable without the network, and `make check` is
    where it belongs: F4's refusal of "shipped_date must be after order_date" is
    a promise the cheapest layer should keep.
    """
    offenders = [e["type"] for e in catalog.ENTRIES if e["base"] in MULTI_COLUMN_BASES]
    assert not offenders, (
        f"{offenders} are multi-column expectations. Multi-column is v2 (SPEC F4): the refusal "
        "is only honest while these are genuinely absent from the catalog."
    )


@pytest.mark.ge
def test_the_catalog_agrees_with_the_framework_about_base_class_and_required_kwargs() -> None:
    """Two curated fields are copies of framework facts. Copies drift, so they are pinned.

    `base` is the exclusion mechanism the check above runs on, and F9's signal for
    which of the three result shapes to expect — an aggregate or table-level
    result carries an `observed_value` and no violating-row count at all (LT-1b).
    A stale `base` would break both silently.

    `required` is OURS and deliberately larger than the framework's: LT-2a found
    required-ness split across `.schema()["required"]` and root validators, with
    neither complete (`match_regex` without a `regex` is accepted; `not_match_regex`
    without one raises). Superset is the only safe direction — a rule this file
    accepts may still be refused by the framework, never the reverse. Declaring
    LESS would let the validator wave through kwargs the framework then rejects at
    construction, which is INV-2's rejection arriving one layer too late.

    The sweep at the end is the same claim from the other side: every registry type
    whose REAL base is multi-column is absent. Six of them, by base class, never by
    matching a name.
    """
    ge = _runtime()
    wrong = []
    for e in catalog.ENTRIES:
        actual = ge.describe(e["type"])
        if actual["base"] != e["base"]:
            wrong.append(f"{e['type']}: catalog says {e['base']}, framework says {actual['base']}")
        if short := set(actual["required"]) - set(e["required"]):
            wrong.append(f"{e['type']}: framework requires {sorted(short)}, catalog does not")
    assert not wrong, wrong

    excluded = [t for t in ge.registry() if ge.describe(t)["base"] in MULTI_COLUMN_BASES]
    assert len(excluded) == 6, (
        f"expected the 6 multi-column types LT-2a counted, found "
        f"{len(excluded)}: {sorted(excluded)}"
    )
    assert not (leaked := sorted(set(excluded) & set(catalog.TYPES))), f"{leaked} slipped in"


def test_shared_copy_module_owns_the_constant_strings() -> None:
    """The F11 caveat sentence and the neutral compile token have exactly one home.

    That there is no SECOND home is asserted next door, by
    tests/test_inv5_sampling_disclosure.py::test_status_atom_formatter_is_the_only_writer,
    which scans app/ and web/app for a duplicate. This check owns the other half:
    the home exists, it is populated, and the compile token is neutral where it
    matters — LT-2a found the framework accepting 10 of 25 nonsense rules while
    reporting success, so a token that reads as a pass is a lie about 40% of them.

    Nothing here re-types the sentences. A test that asserts
    `REVIEW_CAVEAT == "Evidence is drawn from ..."` only proves two copies of a
    typo agree, which is the exact failure this module exists to prevent.
    """
    named = {
        "REVIEW_CAVEAT": status.REVIEW_CAVEAT,
        "COMPILED_TOKEN": status.COMPILED_TOKEN,
        "COMPILED_CAVEAT": status.COMPILED_CAVEAT,
        "NOTHING_SAVED": status.NOTHING_SAVED,
    }
    empty = [k for k, v in named.items() if not v.strip()]
    assert not empty, f"the shared copy module declares {empty} but says nothing in them"
    assert len(set(named.values())) == len(named), f"two of {list(named)} are the same sentence"

    verdict_words = {v.upper() for v in status.VERDICTS} | {v.title() for v in status.VERDICTS}
    leaked = [w for w in verdict_words if w in status.COMPILED_TOKEN]
    assert not leaked, (
        f"{status.COMPILED_TOKEN!r} contains the verdict word(s) {leaked}. Compiling clears "
        "shape, never sense; a token that reads as a verdict claims a run that never happened."
    )


def test_spec_quotes_the_seeded_row_count_and_not_the_retired_one() -> None:
    """Same drift argument, one layer up: SPEC's row count is a second copy of the seed's.

    `seed/MANIFEST.md` is generated from the seeder's own constants, so it is the
    fact; every row count in SPEC.md is a hand-copied duplicate of it. SPEC quoted
    2,400,000 until the seed settled at 500,000 — a factual error, not a wording
    preference, and the kind that comes back the next time an old paragraph is
    pasted forward. This is the only prose check in the harness on purpose: the
    other three B24 proposed police wording ("inside" vs "adjacent"), which the
    tests themselves already assert behaviourally, and VERIFICATION §10 is about
    what a fourth copy of the verification intent costs.

    Both halves are asserted, and the second is the one the name promises: the
    retired number has to be GONE, not merely outvoted by the right one. Presence
    alone passes on a SPEC that quotes both.

    ponytail: greps two documents, and names the one retired number rather than
    hunting every comma-grouped integer in the SPEC — 20,000 customers and 800,000
    payments are also in there, so "any other big number is drift" is false.
    2,400,000 is the number that was actually wrong; a second retirement adds a
    second line here.
    """
    manifest = (REPO / "seed" / "MANIFEST.md").read_text()
    spec = (REPO / "SPEC.md").read_text()

    seeded = re.search(r"\|\s*`orders`\s*\|\s*([\d,]+)\s*\|", manifest)
    assert seeded, "seed/MANIFEST.md no longer states an `orders` row count in its scale table"
    rows = seeded.group(1)

    assert rows in spec, f"seed plants {rows} `orders` rows; SPEC.md quotes that number nowhere"
    assert RETIRED_ROW_COUNT not in spec, (
        f"SPEC.md still quotes {RETIRED_ROW_COUNT} `orders` rows. The seed settled at {rows}; "
        "the old figure comes back whenever an old paragraph is pasted forward, which is the "
        "regression this check exists to catch."
    )
