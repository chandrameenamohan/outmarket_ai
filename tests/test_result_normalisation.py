"""F9 · the normalised result — and the third state the framework hides.

`catch_exceptions` defaults to `True` (LT-1a), so a rule that could not run does
not abort the suite. It lands as `success: false` with `result: {}`, which is
identical in every visible way to a rule that ran and found bad data. Only
`exception_info` separates them, and it has two shapes: flat when nothing raised
(`{"raised_exception": False, ...}`) and keyed by MetricConfigurationID string
when something did. So the read is `"raised_exception" in exception_info`, else
iterate `.values()`.

Why this is an invariant and not a nicety: a rule that did not run has a COVERAGE
meaning, not a data-quality meaning. Folding errored into failed tells a domain
expert their data is bad when what is actually bad is the rule — and it inflates
the count of things the product claims to have checked.

LT-1b made it sharper. The two type expectations break on a query asset with a
bare KeyError 'type', which under the default `catch_exceptions` renders as two
red rules with no offending rows and no explanation. The cap that would have
caused that does not ship (SPEC O-2), but the failure mode is generic: any rule
whose column is dropped or renamed errors exactly the same silent way.
"""

from __future__ import annotations

from conftest import pending


def test_an_errored_rule_is_a_third_state_not_a_failure() -> None:
    """Feed the normaliser both shapes of exception_info and assert they diverge.

    A rule with `raised_exception: True` normalises to `errored` and carries the
    exception message; a genuine `success: false` with no exception normalises to
    `failed` and carries the violating count. The assertion is that the two are
    not equal — asserting only that the errored one says "errored" would pass on a
    normaliser that labels everything errored.
    """
    pending("needs app/dq/normalise.py — F9's result model, with `errored` as its third state")


def test_an_errored_rule_never_counts_as_coverage() -> None:
    """The consequence of the state, asserted where it actually matters.

    Only `accepted` rules count toward coverage (SPEC F6); a rule that errored did
    not check anything, so a table whose only rule errored is not covered. Assert
    the coverage number, not the badge.
    """
    pending("needs app/dq/normalise.py plus the coverage roll-up F10 reads")
