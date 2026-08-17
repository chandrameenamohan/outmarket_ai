"""F9 · the framework's result, read as the three things a person can act on.

WHAT A RESULT IS HERE: the rule's plain-English statement, one of three verdicts,
the violating count, a sample of the offending values, the sampling marker, and
the framework's own output kept WHOLE and SEPARATE in `raw`. Separate because the
normalised fields are a lossy reading by design — four of the fifteen catalog
types carry no count and no samples at all — and F13's raw panel is what a person
falls back to when the reading is not enough (INV-4).

THREE THINGS IN HERE ARE NOT STYLE.

1 · `errored` IS A THIRD STATE, NOT A KIND OF FAILURE. `catch_exceptions` defaults
    to True (LT-1a), so a rule that could not run does not abort the suite: it
    lands as `success: false` with an empty `result`, byte-identical to a rule that
    ran and found bad data. Only `exception_info` separates them, and it has TWO
    shapes — flat when nothing raised, keyed by metric id when something did. So
    the read is `"raised_exception" in info`, else iterate `.values()`. Folding the
    two together tells a domain expert their data is bad when what is bad is the
    rule, and inflates the count of things this product claims to have checked —
    which is why `coverage()` lives here and excludes them.

2 · RESULTS ARE JOINED TO RULES BY CONFIGURATION, NEVER BY INDEX. The framework
    reorders `results` the moment one of them errors, and by index that silently
    prints one rule's verdict against another rule's sentence. `normalise()` takes
    the specs it submitted and pairs each one to the result whose
    `expectation_config` matches it — and refuses if a spec never reported, because
    a run record that quietly omits a rule is a coverage lie of the same family.

3 · THE SAMPLING MARKER COMES FROM THE ASSET DEFINITION (INV-5). Nothing in the
    framework's output distinguishes a capped run from an honest run over a smaller
    table (LT-1a), so `element_count` is not evidence and `Scan` is not derived from
    the report — it is what the last code that saw the asset says was scanned. No
    cap ships at this scale (SPEC O-2), so every `Scan` is uncapped today and every
    result says so; the mechanism is here because the day it is switched on the
    marker cannot be recovered after the fact.

WHAT THIS MODULE IS NOT: the thing that triggers a run (B14b), and not the cache.
F9's cache is the completed run record, which is B15's — `record()` is the shape it
will store, and the marker rides inside it as a rendered string rather than as
something a reader recomposes.

ponytail: `normalise()` is strict about a missing result, which reads like it would
block the progressive run SPEC O-3 requires. It does not: a progressive caller
normalises the specs that HAVE reported, one at a time, and a rule with no verdict
yet renders `status.UNSETTLED_ATOM` rather than an absent row. Ceiling: two
identical accepted rules on one table share a configuration and therefore share a
result — they are the same check written twice, and the store does not dedupe them.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.dq import status
from app.rules import catalog, store

# The framework's own provenance kwarg, added to every evaluated configuration. It
# names the datasource and asset the rule ran against, so it stays in `raw` — but it
# is not part of the rule, so it is dropped before anything is matched on identity.
PROVENANCE_KWARG = "batch_id"


@dataclass(frozen=True)
class Scan:
    """What the ASSET DEFINITION says a run saw. Never read back off the framework.

    `row_limit` is the cap the asset was built with — `None` for the whole-table
    asset that actually ships (`app/dq/ge_runtime.py::ROW_LIMIT`, SPEC O-2). It is
    carried rather than inferred because the framework records nothing that would
    let it be inferred: a capped run and an honest run over a smaller table produce
    identical output (LT-1a). `total_rows` is ours for the same reason — it is the
    denominator of the disclosure, and the denominator may not come from the thing
    being disclosed.
    """

    table: str
    total_rows: int
    row_limit: int | None = None

    @property
    def scanned_rows(self) -> int:
        return self.total_rows if self.row_limit is None else min(self.row_limit, self.total_rows)


@dataclass(frozen=True)
class Result:
    """One rule's verdict, in our words, with the framework's own output alongside.

    `unexpected_count` and `samples` are empty for the aggregate and table-level
    shapes rather than zero: the framework returns three different result bodies by
    base class (LT-1a), and a type that cannot carry a violating count has not
    reported zero violations — it has reported an `observed` value against the range
    the rule asked for. F13 needs both presentations, so both fields exist and
    neither is faked.
    """

    statement: str
    spec: Mapping[str, Any]
    verdict: status.Verdict
    unexpected_count: int | None
    samples: tuple[Any, ...]
    identified: tuple[Mapping[str, Any], ...]
    observed: Any
    detail: str | None
    scan: Scan
    raw: Mapping[str, Any]

    def reading(self) -> status.RuleResult:
        """The verdict and its coverage, in the one type that knows how to disclose."""
        return status.RuleResult(self.verdict, self.scan.scanned_rows, self.scan.total_rows)

    @property
    def atom(self) -> str:
        """The verdict as text — with the sampling clause welded in (INV-5)."""
        return status.status_atom(self.reading())

    @property
    def sampled(self) -> bool:
        return self.reading().sampled

    @property
    def magnitude(self) -> str | None:
        """The size of the failure as one string, from the single writer (INV-4).

        The count, the denominator it is a count OF, and the share, composed once
        (`app/dq/status.py`). There is deliberately no numeric `proportion` beside it:
        the share would be the same arithmetic reachable twice, and the two would
        DISAGREE by design — the writer substitutes `status.NEGLIGIBLE_SHARE` for a
        non-zero count whose share would round to zero, so a renderer picking the
        number over the sentence loses exactly the guarantee that token exists to
        provide. The day a renderer needs a number rather than a sentence, it comes
        off this denominator.

        `None` for the shapes that cannot carry a count: the four aggregate and
        table-level types, which report an observed value against the range the
        `statement` already names, and EVERY errored rule — a rule that could not run
        counted nothing, and "0 violating rows" beside it is exactly the confusion
        `catch_exceptions` creates.
        """
        if self.unexpected_count is None:
            return None
        return status.magnitude(self.unexpected_count, self.scan.scanned_rows)

    @property
    def evidence(self) -> tuple[str, ...]:
        """Real offending values, each with the row it came from: `#88231 -450.0`.

        SPEC F13's last clause, and the half of INV-4 a count cannot supply: an
        identifier is what turns "150 orders have a negative total" into a thing
        somebody can go and look at. The pairing is ours because the framework hands
        back a bare dict per row (`{"order_id": 88231, "order_total": -450.0}`) with
        nothing marking which key is the identifier — the answer is that the rule's
        own `column` is the value and everything else is the identity.

        Falls back to the bare values when a run asked for no identifier columns, so
        a table with no primary key still shows what a wrong row looks like.

        ponytail: `str(value)`. No locale, no currency, no precision — SPEC's
        illustration renders "−450.00" because that column is `numeric(10,2)`, and
        knowing that would mean carrying the column type here to format one string.
        Ceiling: the values read as Python renders them.
        """
        column = self.spec["kwargs"].get("column")
        if not self.identified:
            return tuple(str(value) for value in self.samples)
        return tuple(
            " ".join(
                [*(f"#{v}" for k, v in row.items() if k != column), _shown(row.get(column))]
            ).strip()
            for row in self.identified
        )

    @property
    def covers(self) -> bool:
        """Whether this rule actually checked the data. A rule that could not run did not."""
        return self.verdict != "errored"

    def record(self) -> dict[str, Any]:
        """The JSON the run record stores and the browser renders. Plain data, all the way.

        The rendered atom travels IN the payload rather than being recomposed by
        whoever reads it back, which is what makes a cached result safe: the
        disclosure survives the round trip as a string, and `web/` renders what it
        is given (`app/dq/status.py`).
        """
        return {
            "statement": self.statement,
            "spec": dict(self.spec),
            "verdict": self.verdict,
            "status": self.atom,
            "sampled": self.sampled,
            "scanned_rows": self.scan.scanned_rows,
            "total_rows": self.scan.total_rows,
            "unexpected_count": self.unexpected_count,
            "magnitude": self.magnitude,
            "evidence": list(self.evidence),
            "samples": list(self.samples),
            "identified": [dict(row) for row in self.identified],
            "observed": self.observed,
            "detail": self.detail,
            "raw": dict(self.raw),
        }


def executable(revisions: Iterable[store.Revision]) -> tuple[dict[str, Any], ...]:
    """The specs a run submits: the current revision of each rule, `accepted` and nothing else.

    A function rather than a filter each caller writes, for the same reason
    `store.accepted()` is one: a run that executed a `proposed` rule would report on
    a rule nobody judged, and one that skipped an `accepted` rule would report
    coverage the table does not have. Both questions have the same answer and it is
    written down once.
    """
    return tuple(dict(rev.spec) for rev in store.accepted(revisions))


def normalise(
    specs: Sequence[Mapping[str, Any]], report: Mapping[str, Any], scan: Scan
) -> tuple[Result, ...]:
    """Framework output in, our results out — in the order the specs were submitted.

    The join is by `expectation_config`, never by position: the framework reorders
    `results` the moment one errors, and an index join then attributes a verdict to
    the wrong sentence. A spec with no matching result raises, because the framework
    silently dropping a rule and the rule passing look the same downstream.
    """
    reported = {_identity(r["expectation_config"]): r for r in report["results"]}
    missing = [s for s in specs if _identity(s) not in reported]
    if missing:
        raise ValueError(
            f"{[s['type'] for s in missing]} were submitted and never reported. A rule the "
            "framework dropped is not a rule that passed, and a run record missing it claims "
            "coverage the table does not have."
        )
    return tuple(_one(spec, reported[_identity(spec)], scan) for spec in specs)


def coverage(results: Iterable[Result]) -> int:
    """How many rules actually checked the data — the roll-up F10's dashboard reads.

    An errored rule is excluded, and that is the whole point of the third state: it
    did not run, so counting it would report coverage that does not exist. Only
    `accepted` rules reach here at all (SPEC F6, `executable()` above), so this is
    the second and last place a rule can drop out of the number.
    """
    return sum(1 for r in results if r.covers)


def _one(spec: Mapping[str, Any], result: Mapping[str, Any], scan: Scan) -> Result:
    verdict, detail = _verdict(result)
    body = result.get("result") or {}
    return Result(
        statement=catalog.english(spec["type"], spec["kwargs"]),
        spec={"type": spec["type"], "kwargs": dict(spec["kwargs"])},
        verdict=verdict,
        unexpected_count=body.get("unexpected_count"),
        samples=tuple(body.get("partial_unexpected_list") or ()),
        identified=tuple(body.get("partial_unexpected_index_list") or ()),
        observed=body.get("observed_value"),
        detail=detail,
        scan=scan,
        raw=result,
    )


def _verdict(result: Mapping[str, Any]) -> tuple[status.Verdict, str | None]:
    """`success` is the source of truth for pass/fail; `exception_info` outranks it.

    `success` and not `unexpected_count == 0`: a rule carrying `mostly` can succeed
    with violations, and reading the count instead would print a red rule next to
    the tolerance its author deliberately asked for (LT-1a).
    """
    if raised := _raised(result.get("exception_info") or {}):
        return "errored", "; ".join(raised)
    return ("passed" if result["success"] else "failed"), None


def _raised(info: Mapping[str, Any]) -> list[str]:
    """The two shapes of `exception_info`, read as one answer: what raised, if anything.

    Flat (`{"raised_exception": False, ...}`) when nothing raised; keyed by metric
    id when something did, with one entry per failing metric. Reading only the flat
    shape makes every errored rule look like a failing one, which is the whole trap.
    """
    shapes = [info] if "raised_exception" in info else list(info.values())
    return [
        str(s.get("exception_message") or "the rule raised, with no message")
        for s in shapes
        if isinstance(s, Mapping) and s.get("raised_exception")
    ]


def _shown(value: Any) -> str:
    """A single offending value, as a person reads it.

    `None` is the one value that cannot be printed as itself: the rows that violate
    "Every email has a value" are exactly the rows whose value is null, and a list of
    `#4471 None` reads as a bug in this product rather than as the defect it found.
    """
    return "(empty)" if value is None else str(value)


def _identity(config: Mapping[str, Any]) -> str:
    """A rule's identity: its type and its kwargs, minus the framework's provenance.

    A string rather than a tuple because kwargs hold lists (`value_set`), which are
    not hashable; `sort_keys` makes the key independent of dict ordering on both
    sides of the join.
    """
    kwargs = {k: v for k, v in config["kwargs"].items() if k != PROVENANCE_KWARG}
    return json.dumps([config["type"], kwargs], sort_keys=True, default=str)
