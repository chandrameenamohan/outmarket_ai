"""INV-3's other half: the one GE-importing module hands out plain data only.

`tests/test_inv3_single_ge_import.py` polices the BOUNDARY with `ast` — who may
import the framework, and that the process-global context is built exactly once,
at module level. It cannot police what crosses that boundary, because it never
executes anything. This file does: it drives the real module against the real
framework and asserts the surface is dicts, strings and tuples the whole way out.

Why that is the check that matters. A module that imports the framework in one
file and returns its objects from every function has moved the `import` and
nothing else — the upgrade still touches every caller, the store still fills with
framework defaults, and INV-3 reads as satisfied on a grep. So:

  - the wire key is `type`, never the 0.x `expectation_type`;
  - the stored spec is OURS, two keys, none of the ten defaults `.dict()` leaks;
  - the context is handed out, never rebuilt.

Marked `ge` because the framework is not installed for `make check` — that gate
installs nothing and needs no network. No database is touched here (construction,
introspection and serialisation are all context-free per LT-2a); the marker is
the mechanism that keeps the offline gate offline, and this is the second check
to use it that way. Run it with the `uv run` line in VERIFICATION.md §1.
"""

from __future__ import annotations

from typing import Any

import pytest

# The keys `obj.dict()` leaks. Storing them would put framework policy inside our
# rules, so a spec carrying any of them means the wrong serialiser was used.
GE_DEFAULTS = (
    "result_format",
    "catch_exceptions",
    "severity",
    "row_condition",
    "condition_parser",
    "meta",
    "id",
    "windows",
    "batch_id",
    "rendered_content",
)

JSON_SCALARS = (str, int, float, bool, type(None), list, dict, tuple)


def _runtime() -> Any:
    from app.dq import ge_runtime  # noqa: PLC0415

    return ge_runtime


@pytest.mark.ge
def test_repeated_calls_return_the_same_context_object() -> None:
    """One context per PROCESS, handed out — never one per caller.

    The framework's `get_context()` installs a process-global project rather than
    returning an object, so a second one silently detaches the first's
    datasources and the error only lands later, at validate(), naming a
    datasource that is right there (LT-1b). The sibling `ast` check proves there
    is exactly one call and that it is at module level; this proves the accessor
    does not quietly build a second one on the way past.
    """
    ge = _runtime()
    first = ge.context()
    assert first is not None, "the runtime hands out no context at all"
    assert ge.context() is first, "context() built a second context — that is the LT-1b bug"


@pytest.mark.ge
def test_module_surface_returns_plain_dicts_only() -> None:
    """Nothing framework-shaped crosses the boundary, in either direction.

    Asserted on every public function rather than on the interesting one: the
    leak that actually happens is an `introspect`-style helper that returns the
    class, or a spec built from `.dict()` because it was one character shorter.
    """
    ge = _runtime()

    types = ge.registry()
    assert isinstance(types, tuple) and types, "registry() returned no types"
    assert all(isinstance(t, str) for t in types), "registry() leaked framework classes"

    etype = "expect_column_values_to_be_in_set"
    described = ge.describe(etype)
    assert type(described) is dict
    assert described["type"] == etype
    assert described["base"] == "ColumnMapExpectation"
    assert described["supports_mostly"] is True, "map expectations carry `mostly`; this one lost it"
    assert all(
        isinstance(v, JSON_SCALARS) for v in described.values()
    ), f"describe() leaked a framework object: {described}"

    spec = ge.construct(etype, {"column": "status", "value_set": ["shipped", "pending"]})
    assert type(spec) is dict
    assert set(spec) == {"type", "kwargs"}, (
        f"the stored spec is {sorted(spec)}; it is OURS and it is two keys. "
        "`obj.dict()` is the one-character shortcut that leaks ten framework defaults."
    )
    assert spec["type"] == etype
    assert "expectation_type" not in spec and "expectation_type" not in spec["kwargs"], (
        "`expectation_type` is the 0.x wire key. 1.x renamed it to `type` (LT-2a) and every "
        "pre-1.0 memory, blog post and model completion will try to put it back."
    )
    leaked = [k for k in GE_DEFAULTS if k in spec or k in spec["kwargs"]]
    assert not leaked, f"framework defaults leaked into the stored spec: {leaked}"

    assert ge.construct(spec["type"], spec["kwargs"]) == spec, (
        "construct() is also the deserialiser; a stored spec that does not survive being read "
        "back is a rule that will change meaning between the day it was authored and the run."
    )


@pytest.mark.ge
def test_the_registry_is_read_from_the_registry_and_not_from_the_module() -> None:
    """The catalog's denominator, pinned where an upgrade would move it.

    `dir()` of the expectations module answers with CLASSES and holds names the
    registry does not, so a surface built from it over-counts and the catalog's
    "15 of N" becomes a lie. The assertion is on the shape of the answer, not on
    56: a framework upgrade that adds a type is not a defect, one that starts
    answering with classes is.

    The `unexpected_rows_expectation` line is a correction to LT-2a, found by
    running this: that escape hatch is NOT merely a module export, it is
    registered, under a name that breaks the `expect_*` pattern every other entry
    follows. So the registry count is not the number of checks a domain expert
    could author, and the catalog excludes it on purpose (raw SQL, out of scope).
    """
    ge = _runtime()
    types = ge.registry()
    assert len(set(types)) == len(types), "registry() returned duplicates"
    assert list(types) == sorted(types), "registry() is unsorted; callers diff these lists"
    assert not [t for t in types if t[:1].isupper()], (
        f"registry() answered with class names: {[t for t in types if t[:1].isupper()]}. "
        "Those come from `dir()` of the expectations module, which is the wrong source."
    )
    assert [t for t in types if not t.startswith("expect_")] == ["unexpected_rows_expectation"], (
        "exactly one registered entry is not an `expect_` type — the raw-SQL escape hatch. "
        f"Got {[t for t in types if not t.startswith('expect_')]}. If that list grew, the "
        "catalog has a new candidate to consider or a new thing to exclude deliberately."
    )


@pytest.mark.ge
def test_a_refusal_carries_a_readable_reason_and_no_framework_type() -> None:
    """A caller must be able to `except` a refusal without importing the framework.

    Its own refusals are `ExpectationNotFoundError` and `pydantic.v1.ValidationError`.
    Letting either escape would put a framework name in a caller's `except` clause,
    which is INV-3 lost one import at a time — and would leak a pydantic traceback
    to an author who asked for a rule about their orders table.
    """
    ge = _runtime()
    with pytest.raises(ge.Rejected) as hallucinated:
        ge.construct("expect_column_values_to_be_vibey", {"column": "x"})
    assert "expect_column_values_to_be_vibey" in str(
        hallucinated.value
    ), "the refusal must name the type that was refused; the author typed it and can fix it"

    with pytest.raises(ge.Rejected) as typo:
        ge.construct("expect_column_values_to_be_between", {"column": "x", "min_valu": 0})
    assert "min_valu" in str(typo.value), (
        f"a misspelled kwarg must be named in the refusal, got {str(typo.value)!r}. This is the "
        "model-authored typo case and it is the one the framework catches for us."
    )
    assert "\n" not in str(typo.value), "the refusal is one line, not a pydantic report"

    for exc in (hallucinated, typo):
        assert type(exc.value) is ge.Rejected, (
            f"{type(exc.value).__name__} escaped the runtime module. Every refusal is "
            "Rejected, or the framework's exception classes become part of our API."
        )
