"""INV-2, made mechanical: the only door a rule can walk through on its way to the store.

A rule is refused HERE, while its author is still looking at the screen and can be
told why — never later, as a red rule in a run. An expectation that blows up during
execution has already been stored, already counts toward coverage, and has already
lied about the table being protected.

TWO LAYERS, AND THE ORDER IS LOAD-BEARING.

    1 · our own per-type sanity table, driven by `checks` in app/rules/catalog.json
    2 · construction against the framework, through app/dq/ge_runtime.py

Layer 2 is the obvious design and LT-2a proved it insufficient on its own: of 25
deliberately invalid rule probes the framework REJECTED 15 and ACCEPTED 10,
including inverted bounds, an uncompilable regex, an empty value set and a bogus
SQL type name. The asymmetries are per-expectation authoring drift inside the
framework rather than a policy we can lean on — `not_match_regex` without a regex
raises but `match_regex` without one does not; `row_count_to_be_between` with
min > max raises but `values_to_be_between` does not. So layer 1 runs FIRST and is
the layer that actually makes INV-2 true. Layer 2 still runs, because only the
framework knows what the framework will accept, and because it is the same
constructor that will build the rule at execution time.

WHY THE FRAMEWORK IS IMPORTED INSIDE THE FUNCTION AND NOT AT THE TOP OF THIS FILE.
Two reasons, both structural rather than stylistic. Layer 1 has to be runnable
where the framework is not installed — `make check`'s interpreter deliberately does
not have it, and the 25-probe check is a unit check, not a network one.
And a spec that fails layer 1 must never pay for a framework import that costs
~3.2 s and installs a process-global project (INV-3). Nothing here imports the
framework by name; the one door is still `app/dq/ge_runtime.py`, which is also why
the INV-3 text scan finds no mention of it anywhere in this file.

WHAT THIS MODULE DELIBERATELY CANNOT DO: persist anything. It has no filesystem
and no database in its import graph — it takes a spec and returns a spec, and the
caller stores what comes back. That is what makes "a rejected spec writes nothing"
a property of the shape of the code rather than a claim about its control flow,
and `tests/test_inv2_authoring_rejection.py::test_a_rejected_spec_writes_nothing`
asserts the import graph rather than trusting this paragraph.

IDENTIFIERS ARE NOT TRUSTED (SPEC §3.1). A column name that came from model output
is checked against the LIVE schema before anything is built from it. `columns` is
an argument rather than a lookup this module performs, so that validation stays a
pure function; `app/rules/schema.py` is the live reader, and omitting it FAILS
CLOSED — an unverified identifier is refused, never waved through.

WHAT THIS MODULE IS NOT: a judge of whether a well-formed rule is RIGHT. LT-2a and
LT-2b independently confirmed the tool can only ever say a rule is well-formed —
the framework accepts nonsense, and the model proposes rules that are true of every
sampled row and still business-naive. Meaning is the domain expert's job, which is
the whole reason F12 exists.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from typing import Any

from app.rules import catalog

# The allowed output set, BOUND rather than copied: `is` holds against
# catalog.TYPES, so a sixteenth check type cannot be offered to the model and
# refused here, or the reverse.
ALLOWED_TYPES = catalog.TYPES

_BY_TYPE: dict[str, dict[str, Any]] = {e["type"]: e for e in catalog.ENTRIES}

# The stable half of the refusal for a type outside the catalog. A constant
# because the gate asserts on it: string-matching our own prose is how a check
# ends up passing on a message that changed meaning.
NOT_IN_CATALOG = "is not one of the check types this product offers"

# ponytail: a written-down vocabulary of SQL type names, compared case-insensitively.
# Ceiling: a type the demo database does not use and this list does not name would be
# refused as a hallucination. The upgrade path is `pg_type`, one query in
# app/rules/schema.py — deliberately not taken, because it turns a pure check into a
# round trip to reject a string, and the framework's own comparison is against these
# reflected names anyway.
SQL_TYPES = frozenset(
    {
        "SMALLINT", "INTEGER", "BIGINT", "SERIAL", "BIGSERIAL",
        "NUMERIC", "DECIMAL", "REAL", "FLOAT", "DOUBLE_PRECISION", "MONEY",
        "CHAR", "VARCHAR", "TEXT", "BYTEA", "UUID", "XML",
        "JSON", "JSONB", "ARRAY", "ENUM", "BOOLEAN", "BIT",
        "DATE", "TIME", "TIMESTAMP", "TIMESTAMPTZ", "INTERVAL",
        "INET", "CIDR", "MACADDR", "TSVECTOR",
    }
)  # fmt: skip


class RuleRejected(ValueError):
    """This rule may not be stored, and the message says what was wrong with it.

    One exception type for both layers on purpose: the author does not care which
    of our checks or which of the framework's caught it, and a caller that had to
    know would end up branching on the difference.
    """


def validate(
    etype: str,
    kwargs: Mapping[str, Any],
    table: str,
    columns: Collection[str] | None = None,
) -> dict[str, Any]:
    """The one gate. Returns the storable spec, or raises `RuleRejected` with a reason.

    `columns` is the live column set of `table`, from `app/rules/schema.py`. Passing
    `None` is not "skip the check" — it is "no schema was supplied", and every rule
    naming a column is then refused, because an identifier nobody verified is exactly
    what SPEC §3.1 forbids interpolating.

    The return value is the framework's own normalisation of the rule
    (`min_value=0` comes back as `0.0`), which is what the store holds and what F7
    compiles: nothing can reach the store that did not come out of this function.
    """
    entry = _entry(etype)
    _known_kwargs(etype, entry, kwargs)
    _required_kwargs(etype, entry, kwargs)
    _mostly(etype, kwargs)
    for name in entry["checks"]:
        CHECKS[name](etype, kwargs)
    _identifiers(etype, kwargs, table, columns)
    return _construct(etype, kwargs)


def _entry(etype: str) -> dict[str, Any]:
    if etype not in _BY_TYPE:
        raise RuleRejected(
            f"{etype!r} {NOT_IN_CATALOG} — there are {len(ALLOWED_TYPES)}, and this is not one "
            "of them. A check type outside the catalog is a defect, not a request: it has no "
            "English form, no sanity rules and nothing has ever run it here."
        )
    return _BY_TYPE[etype]


def _known_kwargs(etype: str, entry: Mapping[str, Any], kwargs: Mapping[str, Any]) -> None:
    """Refuse a parameter this check does not take — the shape a misspelling arrives in."""
    allowed = set(entry["required"]) | set(entry["optional"])
    if unknown := sorted(set(kwargs) - allowed):
        raise RuleRejected(
            f"{etype}: {unknown} is not a parameter of this check. It takes "
            f"{sorted(allowed)}. A parameter name nobody recognises is a guess, and a guess "
            "that is silently ignored produces a rule that checks something else."
        )


def _required_kwargs(etype: str, entry: Mapping[str, Any], kwargs: Mapping[str, Any]) -> None:
    if missing := sorted(set(entry["required"]) - set(kwargs)):
        raise RuleRejected(
            f"{etype}: missing {missing}. The framework declares required-ness in two "
            "incomplete places (LT-2a), so this list is ours and is the one that counts."
        )


def _mostly(etype: str, kwargs: Mapping[str, Any]) -> None:
    """`mostly` is a tolerance, so it is a proportion — never a percentage, never a count."""
    if "mostly" not in kwargs:
        return
    value = kwargs["mostly"]
    if not isinstance(value, int | float) or isinstance(value, bool) or not 0 <= value <= 1:
        raise RuleRejected(
            f"{etype}: mostly={value!r} is not a proportion between 0 and 1. "
            '"at most 2% may be null" is mostly=0.98, not mostly=2 and not mostly=98.'
        )


def _at_least_one_bound(etype: str, kwargs: Mapping[str, Any]) -> None:
    if kwargs.get("min_value") is None and kwargs.get("max_value") is None:
        raise RuleRejected(
            f"{etype}: neither min_value nor max_value was given, so the rule is true of every "
            "row and checks nothing. A green rule that cannot fail is worse than no rule — it "
            "reports coverage this table does not have."
        )


def _ordered_bounds(etype: str, kwargs: Mapping[str, Any]) -> None:
    low, high = kwargs.get("min_value"), kwargs.get("max_value")
    if low is None or high is None:
        return
    try:
        inverted = low > high
    except TypeError:
        # Bounds of incomparable kinds are a TYPE fault, and the framework names it
        # precisely one layer down. Saying "min is above max" about a date and an
        # integer would be a worse message than the one layer 2 already writes.
        return
    if inverted:
        raise RuleRejected(
            f"{etype}: min_value={low!r} is above max_value={high!r}, so no value can satisfy "
            "both and every row fails. If the range is inverted the bounds are swapped."
        )


def _non_empty_set(etype: str, kwargs: Mapping[str, Any]) -> None:
    for key in ("value_set", "type_list"):
        if key in kwargs and not kwargs[key]:
            raise RuleRejected(
                f"{etype}: {key} is empty, so no value can ever be in it and every row fails. "
                "An empty set is the shape a truncated or half-parsed model reply arrives in."
            )


def _compilable_regex(etype: str, kwargs: Mapping[str, Any]) -> None:
    pattern: Any = kwargs.get("regex")
    try:
        re.compile(pattern)
    except (re.error, TypeError) as exc:
        raise RuleRejected(
            f"{etype}: regex {pattern!r} does not compile — {exc}. The framework accepts it and "
            "the failure surfaces mid-run as an errored rule with no offending rows."
        ) from exc


def _known_sql_type(etype: str, kwargs: Mapping[str, Any]) -> None:
    named = [kwargs["type_"]] if "type_" in kwargs else list(kwargs.get("type_list") or [])
    for name in named:
        if not isinstance(name, str) or name.upper() not in SQL_TYPES:
            raise RuleRejected(
                f"{etype}: {name!r} is not a SQL type name. A plausible-looking type is the "
                "commonest hallucination in this position, and the framework stores it happily."
            )


# The sanity vocabulary. This dict IS the vocabulary — an entry's `checks` in
# app/rules/catalog.json names a key of it, and the gate reads this dict rather than
# a second declaration of the same five names, so a rename here fails the catalog
# check instead of silently disabling a rule.
CHECKS: dict[str, Callable[[str, Mapping[str, Any]], None]] = {
    "at_least_one_bound": _at_least_one_bound,
    "ordered_bounds": _ordered_bounds,
    "non_empty_set": _non_empty_set,
    "compilable_regex": _compilable_regex,
    "known_sql_type": _known_sql_type,
}


def _identifiers(
    etype: str, kwargs: Mapping[str, Any], table: str, columns: Collection[str] | None
) -> None:
    """SPEC §3.1 — an identifier from model output is checked against the live schema.

    The column-existence check in the catalog is checked like every other rule, and
    that is deliberate: it guards against a column being DROPPED later, so it is only
    meaningful if the column is there when it is written. Authoring one against a
    column that has never existed is the hallucination, not the drift.
    """
    if "column" not in kwargs:
        return
    column = kwargs["column"]
    if columns is None:
        raise RuleRejected(
            f"{etype}: no live schema was supplied for {table!r}, so the column {column!r} "
            "could not be verified. An unverified identifier is refused rather than trusted — "
            "read the schema (app/rules/schema.py) and pass it in."
        )
    if column not in columns:
        raise RuleRejected(
            f"{etype}: {table!r} has no column {column!r}. Its columns are "
            f"{sorted(columns)}. A rule on a column that does not exist cannot fail honestly; "
            "it errors mid-run and reads as a broken product rather than as a bad rule."
        )


def _construct(etype: str, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Layer 2. The framework's own constructor, behind the one module allowed to call it."""
    from app.dq import ge_runtime  # noqa: PLC0415

    try:
        return ge_runtime.construct(etype, dict(kwargs))
    except ge_runtime.Rejected as exc:
        raise RuleRejected(str(exc)) from exc
