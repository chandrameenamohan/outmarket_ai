"""The single writer for a verdict and for the sentences the product's honesty rests on.

INV-5 says a result derived from a sample must say so *inside* the same text node as
the pass/fail state. That is a property of a STRING, not of a layout, so it can only be
guaranteed where the string is built. Hence one module, one writer: `status_atom()` is
the only place a verdict becomes display text, and the sampling clause is welded into
the same return value — a caller cannot render a verdict and forget the disclosure,
because it has no way to render a verdict at all except by asking for the whole atom.

The same argument, one level out, covers the load-bearing sentences beside it: INV-4's
magnitude line, the review-queue caveat, INV-1's time-budget line, the compile token, the
refusal line, the state labels. A second copy of one is not a style problem — it is two
truths that drift apart silently, and nobody finds out until a user reads both.
`tests/test_inv5_sampling_disclosure.py` fails the gate on one anywhere in `app/` or
`web/`, the same way INV-3's import boundary is enforced rather than agreed.

THEY REACH THE FRONTEND AS PAYLOAD, never as frontend constants: this runs server-side
and the strings travel in the response of the endpoint whose screen shows them. `web/`
renders what it is given and never composes a verdict. WHAT THIS DELIBERATELY IS NOT: a
templating system, an i18n layer, or a component library — a handful of pure functions
over a small frozen dataclass.

There is NO `running` verdict. Execution is synchronous but progressive (SPEC O-3), so a
rule either has settled into one of three states or has not reported yet — and one that
has not reported is the ABSENCE of a verdict, rendered as `UNSETTLED_ATOM`. The
formatter refuses anything else rather than inventing a fourth state at the surface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, get_args

# The whole verdict vocabulary. `errored` is a third state, never a kind of
# failure: a rule that could not run has a coverage meaning, not a data-quality
# one, and Great Expectations makes the two byte-identical (LT-1a).
Verdict = Literal["passed", "failed", "errored"]
VERDICTS: tuple[str, ...] = get_args(Verdict)

SEPARATOR = " · "

# --- The load-bearing sentences. One home each. -------------------------------

# F11 · the review queue header. The UI expression of LT-2b: the model proposed rules
# that were true of every row it saw and still business-naive.
#
# IT DOES NOT MENTION A SAMPLE, AND THAT IS THE POINT. It used to open "Evidence is drawn
# from a sample of this table" — unconditionally, while SPEC O-2 ships no cap at this
# scale, two lines above an evidence line reading "500,000 rows scanned" on a 500,000-row
# table. There is no conditional version either: a sampling disclosure belongs INSIDE the
# verdict it qualifies (INV-5, `status_atom`), never in a page-level banner a layout can
# separate from the number it is about.
REVIEW_CAVEAT = (
    "Every rule here was inferred from this table's own numbers. "
    "A rule can be true of every row in it and still be wrong about the business."
)

# F11 / INV-1 · the five minutes a domain expert is promised for one table's queue. The
# number is INV-1's — "a domain expert can act on a table's proposals in <= 5 minutes" —
# and it is the PROMISE, not the arithmetic; see `budget()` for why those differ now.
#
# The indicator is the Reviewer variant's, grafted deliberately (design/README.md; three
# judges scored the Workbench direction 6.5/10 on expert usability, and this screen is
# where that showed). Its job is that INV-1 is otherwise a claim nobody in the product
# can see, because timing a human is not a gate check.
BUDGET_MINUTES = 5

# What one decision costs: read the sentence, read the evidence line, press one of three
# buttons. Fifteen of those fill the five minutes, which is where 20 s comes from — the
# budget over the queue length INV-1 was written for, fixed rather than recomputed.
DECISION_SECONDS = 20

# What the indicator says when the queue is longer than the promise covers. It exists
# because `budget()` used to DIVIDE the five minutes by the queue length, so it was
# bounded above by five and read the same in front of thirty-seven decisions as in front
# of five — a needle painted on the dial (design/README.md: "kept OR BROKEN").
OVER_BUDGET = "past the five minutes this is supposed to take"

# What the tail says on the last decision. Separate from the minutes because "about 0
# minutes left" reads as a stopwatch that ran out rather than as a queue nearly done.
BUDGET_LAST = "the last one"

# F12 · compiling is shape, never sense. Great Expectations accepted 10 of 25 nonsense
# rules while reporting success (LT-2a), so this token is neutral and never a pass.
COMPILED_TOKEN = "Compiled · shape OK"
COMPILED_CAVEAT = "Compiling proves the rule is well-formed — never that it is right."

# F12 · the moment before anything is written down. F4 returns a draft that went through
# the validator and nothing else, and the claim a reader cannot check from the screen is
# that it is not already in the store — so it is stated, like "Nothing was saved" below.
UNSAVED_NOTE = "Nothing is stored until you press it. This draft exists only on this screen."

# F12 · the two doors into a new revision, one per user. Each is a claim about what the
# system does with what you typed — the expert's sentence is COMPILED AGAIN, the
# engineer's configuration VALIDATED AGAIN — and a label that stopped saying so would
# leave the bilingual split decorative. AMENDED_NOTE is the half nobody expects: an
# amended rule lands in `needs_review`, so editing a rule is not a way of accepting it.
RESTATE_LABEL = "Say it another way — your sentence is compiled again"
RECONFIGURE_LABEL = "Edit the configuration — it is validated again before anything is saved"
AMENDED_NOTE = (
    "An amended rule goes back for review. Changing what a rule checks is not a way "
    "of agreeing with it, so the new revision runs only once somebody accepts it."
)

# F12 · why a rule already flagged for review carries no checkbox AT ALL rather than a
# disabled one: a disabled control still says "bulk-acceptable, just not right now", and
# this population is the opposite — somebody looked and could not settle it.
BULK_EXCLUDED = "Held for review — this one is a judgment, not a formality."

# F12 · the one label composed in the BROWSER, and the mechanism that keeps this module
# its only writer anyway: the count changes on every checkbox click, which is not worth a
# round trip, so the sentence lives here and travels with one slot for the number. The
# wording is ACCEPT_ACTION's in the plural, deliberately — this is the control that can
# do LT-2b's damage at scale, so it may not read milder.
BULK_ACTION_TEMPLATE = "Accept {n} — I vouch for each of these"

# F4/F12 · an inexpressible rule is refused, and the refusal says what did not happen.
NOTHING_SAVED = "Nothing was saved. Your coverage did not change."

# F4 · the two refusals authoring has to be able to say out loud. They are what make "we
# refused" mean something other than "it did not work", and a second copy of either would
# drift from the catalog it describes. The first is SPEC F4's own acceptance text, word
# for word: a refusal a user cannot act on is one they will work around, so it names the
# limitation AND its boundary, and the reader learns what the product does cover.
MULTI_COLUMN_LIMIT = (
    "Not supported yet — this rule compares two columns, and the current rule set "
    "covers single-column and table-level checks only."
)
UNCLEAR_REQUEST = (
    "This could not be read as a check on one column or on the table as a whole. "
    "Name the column and say what would make a row wrong."
)

# F12/F14 · the three judgments one person makes about one rule. A permalink is the one
# screen a stranger reaches with no context, so the button that changes what the product
# will execute has to say what pressing it means.
#
# ACCEPT_ACTION is the Reviewer variant's copy, grafted deliberately (design/README.md,
# SPEC 0.4's known-risk note): "Accept" alone reads as dismissing a notification, and
# LT-2b is why it must not — every rule the model proposed was true of the rows it saw
# and wrong about the business. The person pressing this is the only check on that.
ACCEPT_ACTION = "Accept — I vouch for this"
REJECT_ACTION = "Reject…"
# SPEC F12's own third action. It is not a rejection: it parks the rule where a rule
# nobody can yet judge belongs, which is the `needs_review` state F6 already has.
ASK_ACTION = "Ask business"

# F11/F12/F14 · the four store states, in the language of the person deciding.
#
# `app/rules/store.py` owns the states; this owns what a READER is shown, because
# `needs_review` in a monospace chip is the schema leaking onto screens F11 promises need
# no schema knowledge. Both users get the English one (the mockup's chips were English on
# both sides of the spread), and the raw name still travels beside it as the styling hook
# and the `data-row` attribute the browser checks read. Keys pinned to the store's four
# in `tests/test_review_queue.py`.
#
# ponytail: NOT in the single-writer scan's reserved list, unlike every sentence above —
# that list is disclosure copy, and banning "Rejected" under `web/` would ban prose.
STATE_LABELS: dict[str, str] = {
    "proposed": "Unsaved proposal",
    "needs_review": "Held for review",
    "accepted": "In use",
    "rejected": "Rejected",
}

# F4/F12 · a refusal is an OUTCOME and wears the same chip every other outcome does.
# Prose with a coloured border reads as the system telling you something; this reads as
# the system recording a decision, and the decision it recorded is that nothing was.
REFUSED_TOKEN = "REFUSED · nothing stored"

# The one place the reason field is named: F12 requires a rejection to capture WHY, and
# app/rules/store.py refuses a rejected revision that carries none — so the label says
# which of the three buttons needs it.
REASON_LABEL = "Why — required to reject, kept with the rule forever"

# F10 · the three verification buckets, in the order they appear on the screen — a
# heading and the sentence under it, so they live here with the rest of the copy.
#
# THE ORDER IS THE FEATURE, which is why the ordinal is IN the heading rather than
# supplied by a list marker: a heading that read the same in any position would let a
# stylesheet reorder the argument without reordering the screen.
#
# The ids are DOM identifiers rather than copy, and are here anyway because the
# derivation (`app/dq/coverage.py::bucket`) and the headings must name one set of three.
BUCKET_IDS: tuple[str, str, str] = ("never-run", "unverifiable", "verified")

BUCKETS: tuple[dict[str, str], ...] = (
    {
        "id": BUCKET_IDS[0],
        "heading": "1 · Never run",
        "why": "no evidence at all — top of the pile",
    },
    {
        "id": BUCKET_IDS[1],
        "heading": "2 · Ran, but unverifiable",
        "why": "errored or sampled — a result exists, a verdict does not",
    },
    {
        "id": BUCKET_IDS[2],
        "heading": "3 · Verified",
        "why": "full scan completed — pass or fail, the verdict is real",
    },
)

# F10 · why the screen is in the order it is in, said once at the top. A ranking nobody
# explains reads as an arbitrary list, and this is what stops the middle bucket being
# read as a milder version of the third.
SORT_NOTE = (
    "Sorted by what is unverified — a table whose last run errored or was sampled is "
    "not vouched for, and never files under coverage that can be trusted."
)


def bulk_note(cap: int) -> str:
    """F12 · what the cap on a bulk accept is FOR, said where the control is.

        Up to 8 at a time, so every evidence line is on screen when you press it.

    UX_HARNESS_FINDINGS §4 is the argument: a bulk control that hides what it is
    accepting turns "looks fine" into "done" at scale, and LT-2b is what makes that
    expensive. So the sentence states the REASON for the limit rather than the limit, and
    the number arrives as an argument because it belongs to the thing that enforces it
    (`app/rules/store.py::BULK_CAP`): our words, somebody else's numbers.
    """
    return (
        f"Up to {cap} at a time, so every evidence line is on screen when you press it. "
        "Accepting is vouching, not dismissing — read each line. Anything already "
        "flagged for review is not offered here at all."
    )


def refusal(explanation: str) -> str:
    """The one shape a refusal takes: what could not be done, then what did not happen.

    The second half is never optional and never a caller's to compose. "Nothing was
    saved" is the claim a user has no way to verify from the screen, so it is welded to
    every refusal for the same reason the sampling clause is welded to every verdict.
    `explanation` is one of the two constants above or a validator's own reason; either
    way the sentence ends the same.
    """
    return f"{explanation} {NOTHING_SAVED}"


UNSETTLED_ATOM = "PENDING · not yet reported"  # not a verdict; see the module docstring

# F10 · what stands in the verdict column for a table with no run record at all. It is
# here rather than in the screen because it occupies the same slot as a verdict, and a
# second writer for that slot is the one place a sampling clause could go missing by
# being replaced with something else. NEVER RUN is deliberately not a verdict — there is
# nothing to have a verdict about — and NO_RULES is appended rather than shown instead
# because a table with nothing to check it with is a different job for the engineer
# reading the row (write rules, rather than press Run).
NEVER_RUN_ATOM = "NEVER RUN"
NO_RULES_CLAUSE = "NO RULES"

ERRORED_DETAIL = "rule could not run"  # ERRORED alone reads as a louder FAILED

# F13 · the share a failure is too small to state honestly: a non-zero count whose share
# rounds to "0.00%" reads as nothing happened, which is the one thing it is not.
NEGLIGIBLE_SHARE = "<0.01%"


def magnitude(unexpected_count: int, scanned_rows: int) -> str:
    """How big a failure is: the count, the denominator it is a count OF, and the share.

        150 violating rows · of 500,000 rows scanned · 0.03%

    SPEC F13's sentence, minus the rule's own English statement (which
    `app/rules/catalog.py::english()` renders, and no second module composes either). A
    count on its own is unjudgeable — 150 is a catastrophe in a 500-row table and a
    rounding error in 500,000 — so INV-4 needs the denominator and the share, and they
    travel in one string for the reason the sampling clause travels with the verdict:
    three numbers a caller can pick apart are three a caller can render two of.

    THE DENOMINATOR IS `scanned_rows`, NEVER THE TABLE'S TOTAL. A share of rows nobody
    looked at is a number the run cannot support, and it would disagree with the atom
    beside it, which discloses the same denominator.

    Full digits, like `status_atom`: rounding a number here is rounding the truth. The
    one number that IS rounded never rounds down to zero while the count is non-zero.
    """
    share = 100 * unexpected_count / scanned_rows if scanned_rows else 0.0
    rendered = f"{share:.2f}%" if share == 0 or round(share, 2) else NEGLIGIBLE_SHARE
    return SEPARATOR.join(
        (f"{unexpected_count:,} violating rows", f"of {scanned_rows:,} rows scanned", rendered)
    )


def budget(position: int, total: int, table: str) -> str:
    """INV-1 made visible: where this decision sits, and how long the rest will take.

        Decision 3 of 5 for orders · about 1 minute left
        Decision 5 of 5 for orders · the last one
        Decision 1 of 37 for orders · about 12 minutes left — past the five minutes …

    THE TABLE NAME IS CONTEXT AND NOT NAVIGATION (F11): the budget is a per-table
    promise and a position with no subject is unreadable, but it arrives as a word in a
    string, which is the one shape it cannot be clicked in.

    IT COUNTS AT A FIXED PACE RATHER THAN DIVIDING THE PROMISE, which is the difference
    between an instrument and a decoration — dividing `BUDGET_MINUTES` by the queue
    length is bounded above by five by construction, so it could only ever report INV-1
    being KEPT. `ceil`, never `round`: the tail counts decisions still ahead.

    ponytail: no elapsed time, no timer, no measurement — the pace is a constant, so this
    is a pure function of the queue and the same on every reload. Ceiling: it says how
    long what is LEFT should take, never how long you have spent. INV-1 is owned here BY
    PROXY for that reason.
    """
    if not 1 <= position <= total:
        raise ValueError(
            f"decision {position} of {total} is not a position in the queue. Positions are "
            "1-based and no larger than the queue they index; a budget line that indexes "
            "past the end is a promise about decisions nobody is being asked to make."
        )
    left = math.ceil((total - position) * DECISION_SECONDS / 60)
    if not left:
        tail = BUDGET_LAST
    else:
        tail = f"about {left} minute{'' if left == 1 else 's'} left"
        if left > BUDGET_MINUTES:
            tail = f"{tail} — {OVER_BUDGET}"
    return SEPARATOR.join((f"Decision {position} of {total} for {table}", tail))


@dataclass(frozen=True)
class RuleResult:
    """A settled verdict plus how much of the table it actually saw.

    The two counts are what a caller states; `sampled` is DERIVED from them, so a record
    that saw fewer rows than the table holds cannot fail to disclose it — the
    contradiction is not caught, it is unrepresentable. Great Expectations records
    nothing that distinguishes a capped run from an honest run over a smaller table
    (LT-1a), so both counts are OURS, carried from the asset definition.

    ponytail: rows are the only sampling dimension, because the only cap GE 1.x offers is
    a row-limited query asset. A column-sampled run would be a new field here rather than
    a new writer elsewhere.
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

        PASSED
        FAILED · sampled 100,000 / 512,400
        ERRORED · rule could not run

    Casing settled here because VERIFICATION.md §5 left it to this module (the mockups
    disagreed). Full digits rather than `500K / 2.4M`: rounding a disclosure is a small
    lie, and this is the one sentence that exists to not tell them.
    """
    parts = [result.verdict.upper()]
    if result.verdict == "errored":
        parts.append(ERRORED_DETAIL)
    if result.sampled:
        parts.append(f"sampled {result.scanned_rows:,} / {result.total_rows:,}")
    return SEPARATOR.join(parts)


def coverage_atom(accepted_rules: int) -> str:
    """F10 · the same slot as `status_atom`, for a table that has never been run.

        NEVER RUN
        NEVER RUN · NO RULES

    Two facts, one string, for the third time in this module: a table showing NEVER RUN
    has rules waiting to be executed, one showing NEVER RUN · NO RULES has nothing that
    could ever produce a verdict, and rendering them identically is how "no coverage"
    gets mistaken for "not run yet".

    There is no sampling clause here and never will be — nothing was scanned, so there is
    no sample to disclose. That is the honest asymmetry rather than a hole in INV-5.
    """
    parts = [NEVER_RUN_ATOM] + ([] if accepted_rules else [NO_RULES_CLAUSE])
    return SEPARATOR.join(parts)
