"""The check-type catalog, read from the one file that holds it.

SPEC O-1, resolved by LT-2a: fifteen of the 56 types in the Great Expectations
1.20.0 registry — single-column and table-level only. The six pair/multicolumn
types are v2, and F4's refusal of *"shipped_date must be after order_date"* is
only honest because they are genuinely absent here.

WHY A FILE AND NOT A LIST IN CODE. Four consumers need this list: the model's
menu (F3/F4), the validator's allowed output set (F5), the catalog screen (F12),
and the gate. A design review already caught one mockup shipping fifteen catalog
entries that did not map 1:1 onto real expectation types — the drift is not
hypothetical. So there is one file, and **no module anywhere declares how long it
is**: the count is `len(ENTRIES)`, everywhere, and
`tests/test_catalog_and_copy.py::test_catalog_length_is_read_from_one_source`
fails the gate on a second copy of the list or a hard-coded count.

WHY IT IS HAND-WRITTEN RATHER THAN GENERATED FROM THE FRAMEWORK. LT-2a found
required-ness living in two incomplete places: `.schema()["required"]` lists only
`['column']` for `expect_column_values_to_be_between`, yet a root validator
rejects both-bounds-`None`; `match_regex` without a `regex` is accepted while
`not_match_regex` without one raises. There is no coherent policy to introspect.
So `required` here is OURS and is a superset of the framework's — a rule that
satisfies this file can still be refused by the framework, never the reverse —
and `checks` is the sanity table GE has no equivalent of at all (it accepted 10
of 25 deliberately nonsense rules). Generating this file would import that
incoherence; the file is written down and *tested against* the registry instead.

`checks` names functions in `app/rules/validator.py::CHECKS`, which is the one
vocabulary — this module declares no second copy of it to be diffed against, and
the gate reads the implementation directly. A name here with no implementation
fails `tests/test_catalog_and_copy.py`, so a typo cannot quietly disable one.

TWO FIELDS ARE COPIES OF FRAMEWORK FACTS, and both are pinned rather than
trusted, by `test_the_catalog_agrees_with_the_framework_about_base_and_required_kwargs`
in the `ge` layer:

  `base`      what the type inherits from. It is the exclusion mechanism — the six
              multi-column types are out by BASE CLASS, not by matching "pair" in
              a name — and it is also how F9 knows which of the three result
              shapes to expect, since a ColumnAggregate/Batch result carries an
              `observed_value` and no violating-row count at all (LT-1b).
  `required`  see above; the pin asserts ours is a superset of the framework's.

THE `type` FAMILY IS THE ONE THAT CANNOT RUN AGAINST A ROW CAP, and the constraint
is enforced where a cap would be built — see `app/dq/ge_runtime.py::_batch`.

ponytail: one English template per type, `{placeholder}` substituted verbatim, no
grammar. `expect_column_values_to_be_between` with only a lower bound therefore
reads "... is between 0 and None". The ceiling is deliberate — the phrasing of a
half-bounded rule is F3/F4's problem, where the evidence line and the bounds are
both in hand; upgrade path is a formatter there, not a second template here.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

CATALOG_FILE = pathlib.Path(__file__).with_name("catalog.json")

ENTRIES: tuple[dict[str, Any], ...] = tuple(json.loads(CATALOG_FILE.read_text()))

# The allowed output set, for the generator and the validator. Same list, same
# order, same length — derived, never re-typed.
TYPES: tuple[str, ...] = tuple(e["type"] for e in ENTRIES)
