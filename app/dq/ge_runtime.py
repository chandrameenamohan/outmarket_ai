"""The one module that speaks Great Expectations. INV-3, made mechanical.

Everything above this line trades in plain `{"type": ..., "kwargs": {...}}` dicts.
The framework appears in exactly one file — enforced, not agreed:
`tests/test_inv3_single_ge_import.py` walks every gate-scoped source file with
`ast` and fails on the second importer. That is what makes the framework's next
breaking release a one-file change instead of a rewrite.

TWO THINGS IN HERE ARE NOT STYLE.

1 · ONE CONTEXT, BUILT AT IMPORT. `gx.get_context()` does not merely return a
    context, it INSTALLS one as a process-global project. A second call silently
    orphans the first context's datasources, and the failure does not surface at
    `get_context()` — it surfaces later at `validate()`, as a `DatasourceError`
    naming a datasource that is sitting right there in the object you are
    holding, so it gets debugged as configuration instead of as concurrency.
    LT-1b lost a full run to exactly that. Hence: one call, at module level. A
    single call site inside a request handler is still one context per request,
    which is the same bug wearing a singleton's clothes — and the gate asserts
    the module-level half separately for that reason.

2 · WE SERIALISE OUR SPEC, NEVER THE FRAMEWORK'S. `obj.dict()` leaks ten
    framework defaults (`result_format`, `catch_exceptions`, `mostly`,
    `severity`, `row_condition`, ...) into whatever stores it, and the 1.x wire
    key is `type`, NOT `expectation_type` — the 0.x name is the single commonest
    thing a model, a memory, or a search result will hand you. Both are pinned
    by `tests/test_ge_runtime.py`.

WHAT THIS IS NOT: a validator. The constructor checks SHAPE and never SENSE —
LT-2a fed it 25 deliberately nonsense rules and it ACCEPTED 10 of them, including
inverted bounds, an uncompilable regex and an empty value set. `construct()` is
INV-2's *second* layer and is worthless on its own; the per-type sanity table in
`app/rules/validator.py` runs first and is the layer that makes INV-2 true.
`tests/test_inv2_authoring_rejection.py::test_framework_alone_would_let_ten_of_these_through`
re-asserts that hole through this module so it cannot rot into an assumption.

3 · THE SAMPLING MARKER ORIGINATES HERE, in `ROW_LIMIT`, because this module is
    the last code that sees the asset definition and the framework records nothing
    that distinguishes a capped run from an honest run over a smaller table. INV-5's
    marker therefore cannot be recovered downstream. The cap itself does not ship
    (SPEC O-2); the disclosure it feeds does, carried by `app/dq/normalise.py::Scan`.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import great_expectations as gx
from great_expectations.exceptions.exceptions import ExpectationNotFoundError
from great_expectations.expectations.registry import (
    get_expectation_impl,
    list_registered_expectation_implementations,
)
from pydantic.v1 import ValidationError

# The one context for this process. Module level is load-bearing — see above.
# `ephemeral` writes nothing to disk: no project directory appears, so there is
# no new state to gitignore and nothing to clean up between runs (LT-1a).
_CONTEXT = gx.get_context(mode="ephemeral")

# The connection rules execute against: a role that holds SELECT on the tables
# under analysis and no other privilege anywhere (SPEC §3.1, app/db/roles.sql). A
# rule is a read, so this path never needs more, and PostgreSQL now refuses it more
# rather than this module promising not to ask. Still the direct connection, port
# 5432 — the pooler is 21% slower on identical work (LT-1b).
DSN_VAR = "SUPABASE_DB_URL_ANALYSIS"

# One datasource, one batch definition per table, both for the life of the process
# — registering either twice raises, and they are pure configuration.
_SOURCE: Any = None
_BATCHES: dict[str, Any] = {}

# THE ASSET DEFINITION'S CAP, and INV-5's marker at its origin. `None` is the whole
# table: no cap ships at this scale (SPEC O-2, LT-1b). It is a named constant rather
# than an absence because the framework records NOTHING that distinguishes a capped
# run from an honest run over a smaller table (LT-1a) — so the marker cannot be
# recovered downstream, and `_batch()` below is the last code that knows. Switching
# a cap on is a value change here plus the query asset `_batch()` refuses to build.
ROW_LIMIT: int | None = None

# SUMMARY, and COMPLETE is never emitted. SUMMARY carries the violating count and a
# bounded sample of the offending values, which is what F13 renders; COMPLETE drops
# the LIMIT from the sample query and materialises every offending row in this
# process AND in the stored raw output — 500,031 values in the measured wide case
# (LT-1a). That is a memory and storage argument, not a latency one: the measurement
# does not support a latency claim. `unexpected_index_column_names` is added per call
# because the identifier column is a property of the table, not of this module.
RESULT_FORMAT: dict[str, Any] = {"result_format": "SUMMARY"}


class Rejected(ValueError):
    """The framework refused this expectation, with its reason flattened to one line.

    Its own refusals are a `pydantic.v1.ValidationError` or an
    `ExpectationNotFoundError`. Letting either escape would put a framework type
    in a caller's `except` clause, which is INV-3 lost one `import` at a time.
    """


class Unavailable(RuntimeError):
    """The database the rules run against could not be reached. Not a rule failure.

    Kept distinct from `Rejected` because the two have different audiences: a
    rejection is the author's problem and names their rule, this is the
    operator's problem and names the credential. The framework's own
    `TestConnectionError` subclasses the builtin `ConnectionError`, which is why
    catching it below needs no framework import.
    """


def context() -> Any:
    """The process's one DataContext. Ask for it; never build one."""
    return _CONTEXT


def connect() -> None:
    """Register the datasource NOW, so no request ever pays for it. Called at boot.

    `_source()` is lazy, so without this the FIRST run of a process pays the connect
    inside the number a user is watching. Measured on the live table: the first rule
    of a cold process costs 6.43 s against 2.98 s for the same rule warm. A server
    calls this once before it starts serving (`app/api/server.py`), which is also the
    only arrangement that keeps INV-3 true — one context and one datasource for the
    process, handed out, never built inside a request handler.
    """
    _source()


def registry() -> tuple[str, ...]:
    """Every expectation type the INSTALLED framework registers, sorted.

    Read off the registry, never off `dir()` of the expectations module: that
    module exports two names the registry does not hold (the `Expectation` base
    and a raw-SQL escape hatch), so counting the module over-counts by two.
    """
    return tuple(sorted(list_registered_expectation_implementations()))


def describe(etype: str) -> dict[str, Any]:
    """What the framework knows about one type, as plain data.

    `base` is how multi-column types are excluded from the catalog; `mostly` is
    how "at most 2% of emails may be null" is expressible for map expectations
    and not for aggregate ones.

    `required` is the framework's DECLARED requirement and is INCOMPLETE on
    purpose-of-record: root validators reject kwarg combinations that never
    appear in it (LT-2a). It is a hint for authoring, never a source of truth —
    which is why the catalog is curated data rather than generated from here.
    """
    cls = _impl(etype)
    return {
        "type": cls.expectation_type,
        "base": cls.__mro__[1].__name__,
        "required": sorted(cls.schema().get("required", [])),
        "supports_mostly": "mostly" in cls.__fields__,
    }


def construct(etype: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Build the expectation against the framework; hand back OUR storable spec.

    Also the deserialiser: `construct(spec["type"], spec["kwargs"]) == spec` is an
    exact round trip, so reading a stored rule back re-validates it and a rule
    that stopped being expressible after an upgrade fails loudly at read time
    instead of at the next run.
    """
    conf = _build(etype, kwargs).configuration.to_json_dict()
    return {"type": conf["type"], "kwargs": conf["kwargs"]}


def compile_suite(name: str, specs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Stored specs in, a runnable suite out — described back to the caller as data.

    F7. The suite object itself never crosses this boundary: `run()` below is the
    only thing that needs one and it is in here, so what a caller gets is the
    compiled suite's own account of itself — read back off the framework object
    that will be executed, not echoed from the input. That distinction is the
    point. If the framework normalises a kwarg on the way in (`min_value=0`
    becomes `0.0`), the caller is told the value that will actually be checked.

    Compilation re-validates every spec through the same door `construct()` uses,
    so a stored rule that stopped being expressible after an upgrade fails HERE,
    by name, instead of at the next run as a red rule with no offending rows.

    `severity` and `meta` are dropped: they are on the framework's suite JSON and
    they are its policy, not our rule. Same two keys as a stored spec, so what F6
    shows the author collapsed under "the configuration this compiles to" is the
    same shape the store holds.
    """
    suite = _suite(name, specs)
    return {
        "name": suite.name,
        "expectations": [
            {"type": e["type"], "kwargs": e["kwargs"]} for e in suite.to_json_dict()["expectations"]
        ],
    }


def run(
    name: str, specs: Sequence[dict[str, Any]], table: str, identifiers: Sequence[str] = ()
) -> Any:
    """Compile and execute against the real table. Raw framework output, as plain JSON.

    Compiling and running in one call is what makes "GE executes the produced
    suite with no further transformation" structural rather than a promise: there
    is no seam between them for a transformation to live in. The framework adds
    one kwarg of its own on the way through — `batch_id`, on every evaluated
    config — which is provenance rather than a change to the rule, and it is what
    `test_compiled_suite_is_accepted_by_the_framework` pins the difference to.

    `table` is a PRECONDITION, not a parameter this function validates: it reaches
    `add_table_asset` and is composed into SQL by the framework, so a caller passes
    a name it has already resolved through `app/rules/schema.py::columns()` — which
    is the SPEC §3.1 check, and which the caller needs the column set from anyway.

    `identifiers` are the columns that name an offending ROW rather than describe
    it — the primary key, from `app/rules/schema.py::primary_key()`. They turn
    F13's sample from *"−450.00"* into *"#88231 −450.00"*, at the cost of one extra
    bounded SELECT per rule (LT-1a). They are a caller's to supply for the same
    reason `table` is: this module does not read `information_schema`, and the
    caller has already resolved the table it is running against.

    The return value stays raw on purpose — `app/dq/normalise.py` is what turns it
    into F9's three states, and it needs the whole thing to keep alongside them
    (INV-4). `to_json_dict()` has already flattened Decimal and the enums, so it is
    `json.dumps`-able as it stands.
    """
    result_format = dict(RESULT_FORMAT)
    if identifiers:
        result_format["unexpected_index_column_names"] = list(identifiers)
    return _batch(table).validate(_suite(name, specs), result_format=result_format).to_json_dict()


def _suite(name: str, specs: Sequence[dict[str, Any]]) -> Any:
    if not specs:
        raise Rejected(
            f"{name}: a suite with no expectations reports success without checking anything, "
            "which is the one result this product may never produce"
        )
    return gx.ExpectationSuite(
        name=name, expectations=[_build(s["type"], s["kwargs"]) for s in specs]
    )


def _batch(table: str) -> Any:
    """A whole-table batch. Table asset, never a query asset — SPEC O-2, LT-1b.

    A query asset is the only row cap the framework offers and it gives the two
    `type` expectations no reflected table to read a column type from, so they
    raise a bare `KeyError: 'type'` that `catch_exceptions` renders as a red rule
    with no reason. No cap ships; this is why.

    ponytail: no schema argument. `schema_name=` is deprecated in 1.20.0 — it
    warns and tells you to put the schema in the connection string — and the
    demo database has one schema. Ceiling: a table outside the search path is
    unreachable; upgrade path is the connection string, which is a second
    datasource, not a second parameter here.

    The refusal below is what welds `ROW_LIMIT` to the asset it claims to describe.
    Without it the constant and this function are coupled by comment only, and
    setting it to a number would make every disclosure downstream state a sample
    that was never taken — a false INV-5 marker AND a wrong INV-4 denominator from a
    one-token edit, with nothing between the edit and a user reading it.
    """
    if ROW_LIMIT is not None:
        raise NotImplementedError(
            f"ROW_LIMIT={ROW_LIMIT} but this builds a WHOLE-TABLE asset, so the cap would be "
            "disclosed and never applied. A row cap needs a query asset, which LT-1b measured "
            "as a net loss and which breaks the two type expectations outright (SPEC O-2)."
        )
    if table not in _BATCHES:
        asset = _source().add_table_asset(name=table, table_name=table)
        _BATCHES[table] = asset.add_batch_definition_whole_table(name="whole_table")
    return _BATCHES[table].get_batch()


def _source() -> Any:
    """The datasource, built once for the process. Its connection test runs eagerly (LT-1a)."""
    global _SOURCE
    dsn = os.environ.get(DSN_VAR, "")
    if not dsn:
        raise Unavailable(
            f"{DSN_VAR} is not set; rules have nothing to run against. Load the environment "
            "(`set -a; . ./.env; set +a`) — see .env.example."
        )
    if _SOURCE is None:
        # `postgresql://` resolves to psycopg2 implicitly; naming it makes that
        # visible. With only psycopg v3 installed the implicit form dies at
        # datasource registration with `ModuleNotFoundError: No module named
        # 'psycopg2'` (LT-1a) — which reads as a broken install rather than as a
        # URL that named no driver.
        try:
            _SOURCE = _CONTEXT.data_sources.add_postgres(
                name="postgres",
                connection_string=dsn.replace("postgresql://", "postgresql+psycopg2://", 1),
            )
        except ConnectionError as exc:
            raise Unavailable(f"{DSN_VAR} did not answer: {exc}") from exc
    return _SOURCE


def _build(etype: str, kwargs: dict[str, Any]) -> Any:
    try:
        return _impl(etype)(**kwargs)
    except ValidationError as exc:
        raise Rejected(f"{etype}: {'; '.join(_reasons(exc))}") from exc


def _impl(etype: str) -> Any:
    try:
        return get_expectation_impl(etype)
    except ExpectationNotFoundError as exc:
        raise Rejected(f"{etype!r} is not a check type this framework knows about") from exc


def _reasons(exc: ValidationError) -> list[str]:
    """pydantic's multi-line report, flattened to something an author can read.

    ponytail: one line per error, no field renaming. It is already better than a
    traceback; making it *good* is the validator's job, because only the validator
    knows the type and can say "min must be at most max" instead of "__root__".
    """
    return [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
