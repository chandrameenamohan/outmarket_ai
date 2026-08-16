"""The single writer for a verdict and for the sentences the product's honesty rests on.

INV-5 says a result derived from a sample must say so *inside* the same text node
as the pass/fail state. That is a property of a STRING, not of a layout, so it can
only be guaranteed where the string is built. Hence one module, one writer:
`status_atom()` is the only place a verdict is ever turned into display text, and
the sampling clause is welded into the same return value. A caller cannot render a
verdict and forget the disclosure, because it has no way to render a verdict at all
except by asking for the whole atom.

The same argument, one level out, covers the handful of load-bearing sentences —
the review-queue caveat, the neutral compile token and its companion, the refusal
line. They each exist here once. A second copy is not a style problem: it is two
truths that drift apart silently, and nobody finds out until a user reads both.
`tests/test_inv5_sampling_disclosure.py::test_status_atom_formatter_is_the_only_writer`
fails the gate on any second copy in `app/` or `web/app/`, the same way INV-3's
import boundary is enforced rather than agreed.

WHAT THIS MODULE DELIBERATELY IS NOT: a templating system, an i18n layer, or a
component library. It is a handful of pure functions over a small frozen dataclass.

HOW THE SAME STRINGS REACH THE FRONTEND WITHOUT A SECOND COPY: they are payload,
not frontend constants. `status_atom()` runs server-side and the rendered atom
travels in the run record's JSON; the constant sentences ride along in the response
of the endpoint whose screen shows them. `web/` renders what it is given and never
composes a verdict, which is exactly what the single-writer check asserts.

There is NO `running` verdict. Execution is synchronous but progressive (SPEC O-3),
so a rule either has settled into one of three states or has not reported yet — and
a rule that has not reported is not a verdict, it is the absence of one. It renders
`UNSETTLED_ATOM`. The formatter refuses anything else rather than inventing a
fourth state at the surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

# The whole verdict vocabulary. `errored` is a third state, never a kind of
# failure: a rule that could not run has a coverage meaning, not a data-quality
# one, and Great Expectations makes the two byte-identical (LT-1a).
Verdict = Literal["passed", "failed", "errored"]
VERDICTS: tuple[str, ...] = get_args(Verdict)

SEPARATOR = " · "

# --- The load-bearing sentences. One home each. -------------------------------

# F11 · the review queue header. The UI expression of LT-2b: the model proposed
# rules that were true of every sampled row and still business-naive.
REVIEW_CAVEAT = (
    "Evidence is drawn from a sample of this table. "
    "A rule can be true of every row here and still be wrong."
)

# F12 · compiling is shape, never sense. Great Expectations accepted 10 of 25
# nonsense rules while reporting success (LT-2a), so this token is neutral and
# is never styled as a pass verdict.
COMPILED_TOKEN = "Compiled · shape OK"
COMPILED_CAVEAT = "Compiling proves the rule is well-formed — never that it is right."

# F4/F12 · an inexpressible rule is refused, and the refusal says what did not happen.
NOTHING_SAVED = "Nothing was saved. Your coverage did not change."

# F13 · a rule that has not reported yet. Not a verdict; see the module docstring.
UNSETTLED_ATOM = "PENDING · not yet reported"

# F13 · an errored rule, in words, because ERRORED alone reads as a louder FAILED.
ERRORED_DETAIL = "rule could not run"


@dataclass(frozen=True)
class RuleResult:
    """A settled verdict plus how much of the table it actually saw.

    The two counts are what a caller states; `sampled` is derived from them, so a
    record that saw fewer rows than the table holds cannot fail to disclose it —
    the contradiction is not caught, it is unrepresentable. Great Expectations
    records nothing that distinguishes a capped run from an honest run over a
    smaller table (LT-1a), so both counts are OURS, carried from the asset
    definition by the last code that knows.

    ponytail: rows are the only sampling dimension, because the only cap Great
    Expectations 1.x offers is a row-limited query asset. A column- or
    partition-sampled run would need a different disclosure, and would be a new
    field here rather than a new writer elsewhere.
    """

    verdict: Verdict
    scanned_rows: int
    total_rows: int

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(
                f"{self.verdict!r} is not a verdict; the set is {VERDICTS}. "
                "A rule that has not reported yet is not a verdict — render UNSETTLED_ATOM."
            )
        if self.scanned_rows < 0 or self.total_rows < 0:
            raise ValueError("row counts cannot be negative")
        if self.scanned_rows > self.total_rows:
            raise ValueError(
                f"scanned {self.scanned_rows:,} of a {self.total_rows:,}-row table; "
                "the scanned count is a subset of the total, not a separate measurement"
            )

    @property
    def sampled(self) -> bool:
        """INV-5's marker. A partial scan IS a sample; there is no way to say otherwise."""
        return self.scanned_rows < self.total_rows


def status_atom(result: RuleResult) -> str:
    """The one string that carries a verdict — with its sampling clause welded in.

    Shapes, settled here because VERIFICATION.md §5 left the casing to this module
    (the mockups disagreed with each other):

        PASSED
        FAILED · sampled 100,000 / 512,400
        ERRORED · rule could not run

    Full digits rather than `500K / 2.4M`: rounding a disclosure is a small lie,
    and this is the one sentence that exists to not tell them.
    """
    parts = [result.verdict.upper()]
    if result.verdict == "errored":
        parts.append(ERRORED_DETAIL)
    if result.sampled:
        parts.append(f"sampled {result.scanned_rows:,} / {result.total_rows:,}")
    return SEPARATOR.join(parts)
