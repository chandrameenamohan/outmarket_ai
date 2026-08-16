"""INV-5 · Any result derived from a sample says so, in the same breath as pass/fail.

Three layers, because disclosure can be lost at three different places:

  1. ORIGIN (data)   the executor has no framework-provided way to know a run was
                     capped — nothing in element_count, unexpected_count or meta
                     distinguishes a capped run over a big table from an honest
                     run over a small one. The marker is OURS, carried from the
                     asset definition into the stored record. So: it must be
                     impossible to construct a run record without it.
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

import pytest

from conftest import pending


def test_status_atom_formatter_is_the_only_writer() -> None:
    """One function emits 'FAILED · sampled 500K / 2.4M'. Nothing else formats a verdict."""
    pending("needs the shared status-atom formatter module (F9/F13 surface)")


def test_a_capped_run_record_cannot_be_built_without_the_sampling_marker() -> None:
    """Origin layer. Constructing a capped run record without the marker must raise."""
    pending("needs the run-record model — buildable today, blocked on nothing (VERIFICATION §9.4)")


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
        "needs app/dq/ge_runtime.py — the only module that sees the asset definition; "
        "the cap itself is OFF (LT-1b settled O-2), the marker is not"
    )
