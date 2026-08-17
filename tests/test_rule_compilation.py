"""F7 · a stored rule spec becomes a runnable suite, and the framework runs it as-is.

Three checks, cheapest first, and the third is the one that matters: the whole
feature is the claim that *the framework executes what we compiled, without
anything in between touching it*, and that claim is only checkable by executing.
So the last check runs the compiled suite against the real seeded 500,000-row
`orders` table and asserts it finds exactly the defects `seed/MANIFEST.md`
documents as planted — 150 negative totals (D1), 240 statuses outside the
vocabulary (D3), 150 rows sharing a duplicated `order_reference` (D6).

**The manifest is the authority, not the engine.** Those three numbers are
written out below rather than derived from a query, because a check that counts
the bad rows itself and then asserts the engine agrees with the count is two
readings of the same table agreeing with each other. If a run reports fewer, the
engine has a gap; the numbers do not move to meet it (`seed/MANIFEST.md`).

Why all three are marked `ge` even though two of them touch no database: they
compile, and compiling is the framework's job. `make check` installs nothing and
its interpreter has no `great_expectations`, so a compile check inside it would
be an ImportError, not a signal. They run with the rest of the layer through
`make check-ge`, which needs the network and — as of this file — a reachable
database and a loaded `.env`.

Nothing here imports the framework (INV-3). Every call goes through
`app/dq/ge_runtime.py`, including the execution, which is why the run helper
lives in that module rather than in a sibling that would have had to import
`great_expectations` to hold a suite object.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# The accepted rules for one table, in the shape the store holds them: three of the
# planted defect classes the v1 single-column catalog can actually reach.
ORDERS_RULES = [
    ("expect_column_values_to_be_between", {"column": "order_total", "min_value": 0}),
    (
        "expect_column_values_to_be_in_set",
        {
            "column": "status",
            "value_set": ["pending", "paid", "shipped", "delivered", "cancelled", "returned"],
        },
    ),
    ("expect_column_values_to_be_unique", {"column": "order_reference"}),
]

# seed/MANIFEST.md, keyed by the column each rule watches. D1 / D3 / D6.
PLANTED = {"order_total": 150, "status": 240, "order_reference": 150}

TABLE = "orders"


def _runtime() -> Any:
    from app.dq import ge_runtime  # noqa: PLC0415

    return ge_runtime


def _stored_specs(ge: Any) -> list[dict[str, Any]]:
    """What the store holds: every rule already round-tripped through the framework.

    Built with `construct()` rather than written out as literals on purpose — the
    compiler's input is post-`construct` data by definition (nothing else can
    reach the store, INV-2), and `construct` normalises: `min_value=0` comes back
    as `0.0`. Literals here would make the round-trip check assert that our typing
    of a zero survived, which is not the property under test.
    """
    return [ge.construct(etype, kwargs) for etype, kwargs in ORDERS_RULES]


@pytest.mark.ge
def test_accepted_specs_compile_to_a_suite() -> None:
    """A table's accepted rules become one named suite, described back as plain data.

    The suite object stays behind the door; what a caller gets is data it can
    store, diff and render — which is what F6 shows the author under "the
    configuration this compiles to". So the assertion is on the shape of that
    data, and specifically on the two framework defaults that ride along on the
    framework's own suite JSON: `severity` and `meta` are its policy about our
    rule, and letting them out here would put them in front of a domain expert
    and into whatever stores this next.
    """
    ge = _runtime()
    specs = _stored_specs(ge)

    compiled = ge.compile_suite(TABLE, specs)
    assert type(compiled) is dict
    assert set(compiled) == {"name", "expectations"}, (
        f"a compiled suite is a name and its expectations; got {sorted(compiled)}. "
        "Every extra key is a framework detail a caller now has to know about."
    )
    assert compiled["name"] == TABLE
    assert len(compiled["expectations"]) == len(specs)

    for e in compiled["expectations"]:
        assert set(e) == {"type", "kwargs"}, (
            f"expectation {e.get('type')} came back as {sorted(e)}. `severity` and `meta` are on "
            "the framework's suite JSON — they are its policy, and they are not our rule."
        )

    # Plain data all the way down, asserted the only way that is not a guess.
    assert json.loads(json.dumps(compiled)) == compiled

    with pytest.raises(ge.Rejected) as empty:
        ge.compile_suite(TABLE, [])
    assert TABLE in str(empty.value), "the refusal must name the table whose suite was empty"

    hallucinated = {"type": "expect_column_values_to_be_vibey", "kwargs": {}}
    with pytest.raises(ge.Rejected) as stale:
        ge.compile_suite(TABLE, [*specs, hallucinated])
    assert "expect_column_values_to_be_vibey" in str(stale.value), (
        "compilation re-validates every spec, so a stored rule that stopped being expressible "
        "fails here, by name — not at the next run as a red rule with no offending rows."
    )


@pytest.mark.ge
def test_spec_round_trips_through_compile_unchanged() -> None:
    """Compiling changes no rule's meaning, and compiling twice changes nothing at all.

    This is the property that lets the suite be produced on demand and never
    stored (SPEC F6): if compilation were lossy, the stored spec and the thing
    that ran would drift, and the configuration shown to the author would be
    describing a rule other than the one executed.
    """
    ge = _runtime()
    specs = _stored_specs(ge)

    compiled = ge.compile_suite(TABLE, specs)
    assert compiled["expectations"] == specs, (
        "the specs did not survive compilation unchanged.\n"
        f"  in  : {specs}\n  out : {compiled['expectations']}\n"
        "Order matters too: a suite that reorders rules makes a progressive run report "
        "verdicts against the wrong lines."
    )
    assert ge.compile_suite(TABLE, compiled["expectations"]) == compiled, (
        "compiling the read-back specs produced a different suite; compilation is not idempotent "
        "and the second run of an unedited rule set would not be the same run"
    )


@pytest.mark.ge
def test_compiled_suite_is_accepted_by_the_framework() -> None:
    """The acceptance: the framework runs the compiled suite as-is and finds the plants.

    Two things are asserted, and the first is what makes the second mean
    something. The result carries, per rule, the configuration the framework
    actually evaluated — so comparing that against what `compile_suite` described
    proves the executed suite is the compiled suite, with nothing transformed in
    between. Then the counts prove it ran against the real table rather than
    against a plausible-looking mock of one.

    Compared as a mapping rather than as a list: LT-1a found `.results` order is
    not guaranteed, and asserting on it would produce a flake that reads as a
    compilation bug.

    `batch_id` is the one kwarg the framework adds on the way through, and it is
    lifted out rather than ignored: it names the datasource and asset the rule was
    evaluated against, it is identical across the three rules — one batch, one
    table, one scan — and it is the provenance F9 stores. Ignoring it would also
    have meant this check could not tell "ran against `orders`" from "ran".
    """
    ge = _runtime()
    specs = _stored_specs(ge)
    compiled = ge.compile_suite(TABLE, specs)

    report = ge.run(TABLE, specs, table=TABLE)

    assert report["suite_name"] == TABLE
    assert report["statistics"]["evaluated_expectations"] == len(specs), (
        f"{report['statistics']['evaluated_expectations']} of {len(specs)} rules were evaluated; "
        "a suite the framework silently drops rules from is not the suite that was compiled"
    )

    evaluated = [
        (r["expectation_config"]["type"], dict(r["expectation_config"]["kwargs"]))
        for r in report["results"]
    ]
    batches = {kwargs.pop("batch_id", None) for _, kwargs in evaluated}
    ran = dict(evaluated)
    assert ran == {e["type"]: e["kwargs"] for e in compiled["expectations"]}, (
        f"the framework evaluated {ran}, the compiler produced {compiled['expectations']}. "
        "'no further transformation' means these are the same rules, kwarg for kwarg."
    )
    assert len(batches) == 1 and TABLE in str(batches.pop()), (
        f"the three rules were evaluated against {batches}; one compiled suite is one batch "
        f"against {TABLE}, and a differing batch_id means they did not share the scan"
    )

    found = {
        r["expectation_config"]["kwargs"]["column"]: r["result"].get("unexpected_count")
        for r in report["results"]
    }
    assert found == PLANTED, (
        f"the run reported {found}; seed/MANIFEST.md plants {PLANTED} (D1, D3, D6). "
        "The manifest is the ground truth and is never adjusted to match the engine — a lower "
        "number here is a gap in the engine, and a higher one means the seed drifted."
    )

    errored = {
        r["expectation_config"]["type"]: r["exception_info"]
        for r in report["results"]
        if (r.get("exception_info") or {}).get("raised_exception")
    }
    assert not errored, (
        f"{sorted(errored)} raised rather than ran: {errored}. `catch_exceptions` is on by "
        "default, so an errored rule is `success: false` with an empty result — visually "
        "identical to a genuine failure, and it would have been read as one."
    )
    assert report["success"] is False, (
        "every one of these three rules is aimed at a planted defect, so the run cannot succeed; "
        "a green run here means the suite executed against something other than the seeded table"
    )
