"""INV-5 · Any result derived from a sample says so, in the same breath as pass/fail.

Three layers, because disclosure can be lost at three different places:

  1. ORIGIN (data)   the executor has no framework-provided way to know a run was
                     capped — nothing in element_count, unexpected_count or meta
                     distinguishes a capped run over a big table from an honest run
                     over a small one. The counts are OURS, carried from the asset
                     definition into the stored record, and the marker is DERIVED from
                     them, so a record that lies about its coverage cannot be written.
  2. TRANSPORT (api) the marker survives normalisation and caching.
  3. SURFACE (ui)    the verdict and the sampling disclosure are ONE text node — and
                     that layer drives a browser, so it lives in the browser layer:
                     `tests/e2e/test_inv5_surface.py`, which this file's checks are the
                     other two thirds of.

Layer 3 is the mechanical form of the invariant and the reason there is a single
status-atom formatter. "Adjacent" survives nothing — a layout change, a responsive
breakpoint or a truncation can separate two sibling elements — and "inside" survives all
three. SPEC agrees as of Rev 0.2: INV-5, F13 and §7 step 7 all say *inside* the status
token, where they said *adjacent to* until the harness findings superseded it.

WHAT LT-1b SETTLED HERE (SPEC O-2): no row cap ships, so there is no cap VALUE for a
check to assert — asserting one would pin a thing that does not exist. The cap is the
wrong lever three ways: it saves 37% (5.5 s of 14.84 s) for an 80% cut of the data; at
full size it is a NET LOSS, because GE runs a query asset's SQL verbatim through a
client-side cursor and pulls every LIMITed row to the client (22.67 s / 1,000,127 rows
capped, against 13.63 s / 156 uncapped); and it BREAKS the two type expectations outright
(KeyError 'type' — a query asset has no reflected table to read a column type from),
pinned in tests/test_catalog_and_copy.py.

What still ships is this file: the disclosure MECHANISM, built with the cap switched off
at this scale, because the day a table is an order of magnitude larger the cap comes back
and the disclosure has to already exist.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import pytest

from app.dq import normalise, status
from conftest import REPO, module_constant, source_files

# The one writer. Same shape as INV-3's GE_RUNTIME constant: one place to change
# if the module moves, and the gate follows.
STATUS_MODULE = pathlib.Path("app/dq/status.py")

# The module that builds the asset, and therefore the module that owns the row cap
# the marker is derived from. It imports the framework, so the offline gate reads
# its literals rather than importing it.
GE_RUNTIME = pathlib.Path("app/dq/ge_runtime.py")

# One rule, one framework result, in the shape `to_json_dict()` produces (LT-1a).
# The transport checks below vary the ASSET and hold this constant.
SPEC: dict[str, Any] = {
    "type": "expect_column_values_to_be_between",
    "kwargs": {"column": "order_total", "min_value": 0.0},
}

# Production code only, both languages. Tests are allowed to NAME these sentences in
# prose — this file does, in its own docstring — the same exemption INV-3's text scan
# grants, for the same reason: a check that bans its own explanation is unreadable.
#
# THE TYPESCRIPT ROOT IS `web`, NOT `web/app`. It was the route tree, on the argument
# that the route tree holds no node_modules — which is an argument for excluding the
# generated directories, not for a narrower root: a component moved to `web/components/`
# or `web/lib/` would leave the scan silently, and the anti-vacuity guard below would
# still pass on the route files left behind. So the whole of `web` is walked and the
# three generated things are named.
GENERATED = ("node_modules", ".next")
TEXT_SCANNED = [p for p in source_files("app") if p.relative_to(REPO) != STATUS_MODULE]
TEXT_SCANNED += sorted(
    p
    for suffix in ("*.tsx", "*.ts")
    for p in (REPO / "web").rglob(suffix)
    if not set(p.parts) & set(GENERATED) and p.name != "next-env.d.ts"
)

# The composed shapes, which no constant can pin because they carry live numbers.
# `sampled\s+[\d,]+\s*/` matches the rendered clause and NOT a `sampled` field on a
# record — the field is how the marker travels, and banning it would ban the
# mechanism instead of the second copy.
#
# The third is INV-4's headline sentence, `status.magnitude()`: "150 violating rows ·
# of 500,000 rows scanned · 0.03%". It is PAIRED rather than matched on either half,
# and both halves are load-bearing. A bare `violating rows` false-positives on
# `app/dq/normalise.py`, which quotes "0 violating rows" in a docstring explaining why
# an errored rule renders none; a bare `rows scanned` false-positives on
# `app/rules/suggest.py`, which composes F3's evidence line — a different sentence
# with a different writer. Only the two together are this sentence.
COMPOSED = (
    re.compile(r"\b(" + "|".join(v.upper() for v in status.VERDICTS) + r")\b"),
    re.compile(r"sampled\s+[\d,]+\s*/"),
    re.compile(r"violating rows.{0,40}rows scanned"),
    # INV-1's budget line: the one a component would rebuild from numbers it already has.
    re.compile(r"Decision\s+\d+\s+of\s+\d+"),
)


# The reserved copy, enumerated. DERIVING it from the writer's module-level strings was
# tried and reverted: that also picks up `NEVER RUN` and `NO RULES`, which
# `app/dq/coverage.py` and `app/rules/view.py` QUOTE IN PROSE while explaining the slot
# they occupy. Which copy is load-bearing stays a judgement made in front of this list —
# `STATE_LABELS` is deliberately NOT on it (see that constant). `BULK_ACTION_TEMPLATE` is
# reserved for its wording; its `{n}` slot is the only part a component may move.
OWNED = (
    "REVIEW_CAVEAT COMPILED_TOKEN COMPILED_CAVEAT NOTHING_SAVED UNSETTLED_ATOM "
    "ERRORED_DETAIL NEGLIGIBLE_SHARE BUDGET_LAST MULTI_COLUMN_LIMIT UNCLEAR_REQUEST "
    "ACCEPT_ACTION REJECT_ACTION ASK_ACTION REASON_LABEL UNSAVED_NOTE RESTATE_LABEL "
    "RECONFIGURE_LABEL AMENDED_NOTE BULK_EXCLUDED BULK_ACTION_TEMPLATE"
).split()


def _normalised(scan: normalise.Scan, element_count: int = 500_000) -> normalise.Result:
    """`SPEC` failing on 150 rows, read through F9 against the given asset definition."""
    report = {
        "success": False,
        "results": [
            {
                "success": False,
                "expectation_config": {
                    "type": SPEC["type"],
                    "kwargs": {**SPEC["kwargs"], "batch_id": "postgres-orders"},
                },
                "result": {
                    "element_count": element_count,
                    "unexpected_count": 150,
                    "partial_unexpected_list": [-450.0],
                },
                "exception_info": {"raised_exception": False, "exception_message": None},
            }
        ],
    }
    return normalise.normalise([SPEC], report, scan)[0]


def atom_for(verdict: str) -> str:
    """A settled, unsampled result for `verdict` — the shortest legal atom there is."""
    return status.status_atom(status.RuleResult(verdict, 10, 10))  # type: ignore[arg-type]


def test_status_atom_formatter_is_the_only_writer() -> None:
    """One function emits 'FAILED · sampled 100,000 / 512,400'. Nothing else formats a verdict.

    The same holds for the handful of load-bearing sentences beside it, INV-4's
    magnitude line included — "150 violating rows · of 500,000 rows scanned · 0.03%"
    is what SPEC F13 states verbatim, and F13's dashboard is exactly where somebody
    retypes it in TSX because reaching for the payload felt like more work.

    Enforced in the style of INV-3's import boundary: the reserved text is read OUT of
    the module rather than duplicated into the test, so the check tracks the copy instead
    of pinning a second copy of it.

    ponytail: a raw text scan. It catches the literal second copy, which is the failure
    that actually happens; it does not catch `verdict.toUpperCase()` assembled at runtime,
    and the upgrade path for that is the browser check already in this file.
    """
    assert (REPO / STATUS_MODULE).exists(), f"{STATUS_MODULE} is the designated writer and is gone"
    assert any(p.suffix == ".tsx" for p in TEXT_SCANNED) and len(TEXT_SCANNED) > 5, (
        f"the scan collected {len(TEXT_SCANNED)} files. It covers app/ AND all of web/; if "
        "either side stops being collected this check goes green on a second copy."
    )
    # By NAME, so a constant that is renamed or deleted fails here loudly rather than
    # quietly stopping being guarded.
    owned = [getattr(status, name) for name in OWNED]
    offenders = []
    for path in TEXT_SCANNED:
        text = path.read_text()
        rel = path.relative_to(REPO)
        offenders += [f"{rel}: {s!r}" for s in owned if s in text]
        offenders += [
            f"{rel}: /{p.pattern}/ -> {m.group(0)!r}" for p in COMPOSED if (m := p.search(text))
        ]
    assert not offenders, (
        f"a second writer for the load-bearing copy: {offenders}. Only {STATUS_MODULE} composes "
        "these. Server-side, call status_atom(); in web/, render what the payload carries — a "
        "verdict typed by hand is a verdict that can lose its sampling clause."
    )


def test_the_formatter_is_never_asked_to_render_a_running_verdict() -> None:
    """The verdict set is passed / failed / errored. There is no fourth value.

    Execution is synchronous but progressive (SPEC O-3), so a rule has either settled or
    not reported yet — and 'not reported yet' is the ABSENCE of a verdict, rendered as
    UNSETTLED_ATOM. If `running` were a verdict, every consumer downstream would have to
    special-case a state that can never carry a count or a sampling disclosure.
    """
    assert set(status.VERDICTS) == {"passed", "failed", "errored"}
    for absent in ("running", "pending", "queued", ""):
        with pytest.raises(ValueError):
            status.RuleResult(absent, 10, 10)  # type: ignore[arg-type]
    settled = {atom_for(v) for v in status.VERDICTS}
    assert status.UNSETTLED_ATOM not in settled
    assert not any(v.upper() in status.UNSETTLED_ATOM for v in status.VERDICTS), (
        f"{status.UNSETTLED_ATOM!r} reads as a verdict. A rule that has not reported must be "
        "distinguishable at a glance from one that has — F13 renders it in the same column."
    )


def test_a_capped_run_record_cannot_be_built_without_the_sampling_marker() -> None:
    """Origin layer. A capped run record has no way to claim it saw the whole table.

    `sampled` is derived from the two counts rather than stated alongside them, so
    there is no contradiction to catch: a record that scanned 100,000 of 500,000
    rows discloses it, and no argument exists that could say otherwise. Asserted in
    both directions, because "always sampled" would pass a one-sided check.

    The one thing the counts CAN disagree about is still refused: a scan is a subset
    of the table, never a second measurement of it.
    """
    capped = status.RuleResult("failed", 100_000, 500_000)
    assert capped.sampled and "sampled 100,000 / 500,000" in status.status_atom(capped)
    assert not status.RuleResult("failed", 500_000, 500_000).sampled

    with pytest.raises(ValueError):
        status.RuleResult("passed", 600_000, 500_000)  # saw more rows than exist


def test_uncapped_run_renders_no_sampling_substring() -> None:
    """The other half of the disclosure: it must not cry wolf.

    A sentence that appears on every result stops being read. At the demo set's
    500,000 rows no cap engages (SPEC O-2), so the shipping atom is the bare
    verdict — and that is what makes the sampled one worth noticing.
    """
    full = status.RuleResult("failed", 500_000, 500_000)
    assert status.status_atom(full) == "FAILED"
    assert "sampled" not in status.status_atom(full)
    assert "sampled" not in status.status_atom(status.RuleResult("passed", 0, 0))


def test_no_shipping_code_path_constructs_a_capped_asset() -> None:
    """'The cap is off' is a checked fact, not a claim in a document.

    `add_query_asset` is the only row cap Great Expectations 1.x offers, and LT-1b
    measured it as a net loss that also breaks two catalog types outright. The
    disclosure mechanism above stays built and exercised; the cap does not ship.

    ponytail: greps for the one API that can create one. It would not notice a cap
    smuggled in as raw SQL through some future asset factory — but there is no
    such factory, and the day there is, this check is where it gets caught.
    """
    offenders = [
        f"{p.relative_to(REPO)}:{i}"
        for p in source_files("app")
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if "add_query_asset" in line
    ]
    assert not offenders, (
        f"a capped batch asset is constructed at {offenders}. SPEC O-2: no cap ships — it saves "
        "37% for an 80% data loss, is a net loss at full size, and breaks the two type "
        "expectations with a bare KeyError 'type' that catch_exceptions renders as a red rule."
    )


def test_sampling_marker_survives_normalisation_and_cache() -> None:
    """Transport layer. The rendered atom travels IN the payload; nobody recomposes it.

    A cache is where a disclosure goes to get lost: the marker is derived, the payload is
    JSON, and a reader that stores the verdict and reconstructs the sentence has one code
    path where the sampling clause is optional. So the whole atom is a field, it survives
    `json.dumps`/`json.loads` unchanged, and the counts ride alongside it.

    ponytail: the cache exercised here is the serialisation, which is what a cache stores.
    The run record that holds it stores exactly this dict.
    """
    result = _normalised(normalise.Scan("orders", 500_000, 100_000))
    assert result.sampled
    assert "sampled 100,000 / 500,000" in result.atom

    cached = json.loads(json.dumps(result.record()))
    assert cached["status"] == result.atom, "the atom did not survive the round trip intact"
    assert "sampled 100,000 / 500,000" in cached["status"], (
        f"the cached verdict reads {cached['status']!r}. INV-5: the disclosure is INSIDE the "
        "status token, so it has to be inside the string that is stored, not next to it."
    )
    counts = (cached["sampled"], cached["scanned_rows"], cached["total_rows"])
    assert counts == (True, 100_000, 500_000), f"the counts behind the clause arrived as {counts}"


def test_the_sampling_marker_comes_from_the_asset_definition_not_from_ge_output() -> None:
    """The mechanism, in place of the cap value that LT-1b decided will never exist.

    GE reports nothing that distinguishes a capped run from an honest run over a
    smaller table, so the marker cannot be recovered downstream — whoever builds
    the asset is the last code that knows. This is the check: the executor's
    result carries `sampled` iff the asset it ran against was capped, and it is
    set from the asset definition, never inferred from element_count.

    With the cap off at this scale the honest assertion is the pair: an uncapped
    asset yields a result marked not-sampled, and a capped one (the mechanism
    exercised, not shipped) yields one marked sampled with the cap it used.

    The decoupling is asserted by holding the framework's output CONSTANT and
    changing only the asset definition: one report, two scans, opposite markers. No
    reading of `element_count` can produce that, which is the property under test.
    The origin itself is the row limit declared in the module that builds the asset,
    read out of the source because that module cannot be imported offline; the `ge`
    layer runs the same constant against the real table
    (`tests/test_result_normalisation.py::test_run_against_seeded_orders_reports_the_planted_defect_counts`).
    """
    assert module_constant(str(GE_RUNTIME), "ROW_LIMIT") is None, (
        "the shipping asset declares a row cap. SPEC O-2: none ships at this scale — and the "
        "day one does, this is the value every disclosure downstream is derived from."
    )

    capped = _normalised(normalise.Scan("orders", 500_000, 100_000))
    whole = _normalised(normalise.Scan("orders", 500_000))
    assert capped.raw["result"]["element_count"] == whole.raw["result"]["element_count"], (
        "the two readings must share one framework output, or this check proves nothing about "
        "where the marker came from"
    )
    assert capped.sampled and not whole.sampled, (
        "identical framework output produced identical markers, so the marker is being read "
        "off the framework — which cannot distinguish a capped run from a small table (LT-1a)"
    )
    assert "sampled 100,000 / 500,000" in capped.atom
    assert "sampled" not in whole.atom

    small = _normalised(normalise.Scan("orders", 500_000), element_count=10)
    assert not small.sampled, (
        "a report whose element_count is 10 was marked sampled against an uncapped asset — "
        "inferred from the framework's count rather than carried from the asset definition"
    )
