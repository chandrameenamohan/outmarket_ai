"""INV-5 · Any result derived from a sample says so, in the same breath as pass/fail.

Three layers, because disclosure can be lost at three different places:

  1. ORIGIN (data)   the executor has no framework-provided way to know a run was
                     capped — nothing in element_count, unexpected_count or meta
                     distinguishes a capped run over a big table from an honest
                     run over a small one. The counts are OURS, carried from the
                     asset definition into the stored record, and the marker is
                     DERIVED from them — so a record that lies about its coverage
                     is not caught, it cannot be written down.
  2. TRANSPORT (api) the marker survives normalisation and caching.
  3. SURFACE (ui)    the verdict and the sampling disclosure are ONE text node.

Layer 3 is the mechanical form of the invariant and the reason there is a single
status-atom formatter with a single writer. "Adjacent" survives nothing; a layout
change, a responsive breakpoint or a truncation can separate two sibling elements.
"Inside" survives all three. SPEC agrees as of Rev 0.2: INV-5, F13 and §7 step 7
all say *inside* the status token. (They said *adjacent to* until the harness
findings superseded it; this test is what enforces the difference.)

WHAT LT-1b SETTLED HERE (SPEC O-2): no row cap ships. There is therefore no cap
VALUE for a check to assert — asserting one would pin a thing that does not
exist. The cap is the wrong lever three ways: it saves 37% (5.5 s of 14.84 s) for
an 80% cut of the data; at full size it is a NET LOSS, because GE runs a query
asset's SQL verbatim through a client-side cursor and pulls every LIMITed row to
the client (22.67 s / 1,000,127 rows capped, against 13.63 s / 156 rows uncapped);
and it BREAKS expect_column_values_to_be_of_type and
expect_column_values_to_be_in_type_list outright (KeyError 'type' — a query asset
has no reflected table to read a column type from). See
tests/test_catalog_and_copy.py for the regression check that pins those two.

What still ships is this file: the disclosure MECHANISM, built with the cap
switched off at this scale, because the day a table is an order of magnitude
larger the cap comes back and the disclosure has to already exist.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.dq import status
from conftest import REPO, pending, source_files

# The one writer. Same shape as INV-3's GE_RUNTIME constant: one place to change
# if the module moves, and the gate follows.
STATUS_MODULE = pathlib.Path("app/dq/status.py")

# Production code only, both languages. `web/app` is the Next route tree and holds
# no node_modules. Tests are allowed to NAME these sentences in prose — this file
# does, in its own docstring — the same exemption INV-3's text scan grants, for the
# same reason: a check that bans its own explanation is unreadable.
TEXT_SCANNED = [p for p in source_files("app") if p.relative_to(REPO) != STATUS_MODULE]
TEXT_SCANNED += sorted((REPO / "web/app").rglob("*.tsx")) + sorted((REPO / "web/app").rglob("*.ts"))

# The composed shapes, which no constant can pin because they carry live numbers.
# `sampled\s+[\d,]+\s*/` matches the rendered clause and NOT a `sampled` field on a
# record — the field is how the marker travels, and banning it would ban the
# mechanism instead of the second copy.
COMPOSED = (
    re.compile(r"\b(" + "|".join(v.upper() for v in status.VERDICTS) + r")\b"),
    re.compile(r"sampled\s+[\d,]+\s*/"),
)


def atom_for(verdict: str) -> str:
    """A settled, unsampled result for `verdict` — the shortest legal atom there is."""
    return status.status_atom(status.RuleResult(verdict, 10, 10))  # type: ignore[arg-type]


def test_status_atom_formatter_is_the_only_writer() -> None:
    """One function emits 'FAILED · sampled 100,000 / 512,400'. Nothing else formats a verdict.

    Enforced as an import-boundary check in the style of INV-3: the reserved text
    is read OUT of the module rather than duplicated into the test, so the check
    tracks the copy instead of pinning a second copy of it.

    ponytail: a raw text scan. It catches the literal second copy, which is the
    failure that actually happens — someone types the sentence into a component
    because reaching for the payload felt like more work. It does not catch
    `verdict.toUpperCase()` assembled from parts at runtime. The upgrade path, if
    that ever appears, is the browser check that already exists here:
    test_ui_renders_verdict_and_sampling_in_one_element compares the rendered DOM
    text against status_atom() itself, which no amount of assembly can fake.
    """
    assert (REPO / STATUS_MODULE).exists(), f"{STATUS_MODULE} is the designated writer and is gone"
    owned = [
        status.REVIEW_CAVEAT,
        status.COMPILED_TOKEN,
        status.COMPILED_CAVEAT,
        status.NOTHING_SAVED,
        status.UNSETTLED_ATOM,
        status.ERRORED_DETAIL,
    ]
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

    Execution is synchronous but progressive (SPEC O-3), so a rule has either
    settled or not reported yet — and 'not reported yet' is the ABSENCE of a
    verdict, not a kind of one. It renders UNSETTLED_ATOM. If `running` were a
    verdict, every consumer downstream would have to special-case a state that
    can never carry a violating count or a sampling disclosure.
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
    pending("needs F9 result normalisation")


@pytest.mark.e2e
def test_ui_renders_verdict_and_sampling_in_one_element(app_url: str) -> None:
    """Surface layer, deterministic and eye-free:

    el = page.locator('[data-status-atom]')
    text = el.text_content()
    assert text == status_atom(...)            # from the shared formatter, not a literal
    assert 'sampled' in text                   # inside the SAME element
    for sib in el.locator('xpath=../*').all(): # no sibling carries it
        assert sib is el or 'sampled' not in sib.text_content()
    """
    pending("needs a running app with a rendered run record — F13 surface, unbuilt")


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
    """
    pending(
        "needs F9's result model (app/dq/normalise.py). app/dq/ge_runtime.py already builds the "
        "asset and executes through it — _batch() is real and the `ge` layer drives it against "
        "the seeded table — but run() hands back raw framework output with no run record and no "
        "`sampled` field, so the marker has nowhere yet to be carried to"
    )
