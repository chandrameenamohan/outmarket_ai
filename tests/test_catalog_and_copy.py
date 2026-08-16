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

import pytest

from conftest import pending

CATALOG_SIZE = 15  # SPEC O-1, resolved by LT-2a: single-column + table-level, zero multi-column

# LT-1b: these two read the column type off the REFLECTED TABLE. Against a query
# asset — the only row cap GE 1.x offers — there is no reflected table and both
# raise a bare KeyError: 'type'. Because catch_exceptions defaults to True
# (LT-1a), that surfaces as two red rules with no offending rows and no reason,
# and the user goes hunting for a data problem that does not exist. The cap does
# not ship (SPEC O-2), so today this is a regression check, not a workaround.
BREAKS_ON_A_QUERY_ASSET = (
    "expect_column_values_to_be_of_type",
    "expect_column_values_to_be_in_type_list",
)


def test_catalog_has_exactly_fifteen_entries() -> None:
    pending("needs the canonical catalog file (app/rules/catalog.json)")


@pytest.mark.ge
def test_every_catalog_type_exists_in_the_framework_registry() -> None:
    """Guards against a curated entry that was renamed or removed by an upgrade.

    Goes through app/dq/ge_runtime.py (INV-3) — the test does not import the
    framework itself.
    """
    pending("needs app/dq/ge_runtime.py")


@pytest.mark.ge
def test_the_two_type_expectations_run_against_a_table_asset() -> None:
    """Pins the day someone reaches for a query asset again.

    Execute the whole catalog through app/dq/ge_runtime.py against a TABLE asset
    and assert these two produced a real verdict — `exception_info` shows nothing
    raised — rather than an errored rule wearing a failure's clothes. The
    assertion has to be on exception_info, not on success: an errored rule is
    `success: false` with `result: {}` and is otherwise indistinguishable from a
    genuine failure (LT-1a).

    Lives in the `ge` layer so `make check` never pays for a database round trip;
    it runs with the other `ge` check via the `uv run` line in VERIFICATION.md §1.
    """
    pending(
        "needs app/dq/ge_runtime.py with a table-asset execution path — "
        f"the two to pin are {', '.join(BREAKS_ON_A_QUERY_ASSET)}"
    )


def test_catalog_excludes_every_multi_column_expectation() -> None:
    """The six pair/multicolumn types are v2. This is what makes F4's rejection honest."""
    pending("needs the canonical catalog file")


def test_shared_copy_module_owns_the_constant_strings() -> None:
    """The F11 caveat sentence and the neutral compile token have exactly one home."""
    pending("needs the shared copy module")
