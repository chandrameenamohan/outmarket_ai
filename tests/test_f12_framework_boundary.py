"""SPEC F12 Rev 0.4 · ONE door decides whether a reader may see the framework.

The behavioural half of this claim is `tests/e2e/test_framework_absence.py`, which reads
the finished bytes of every page as both readers. This is the structural half, and it is
here rather than there because it costs nothing and runs offline: it fails on a screen
that has started fetching for itself, BEFORE that screen has grown anything to leak.

WHAT WENT WRONG (bead dq-220). `?configuration=1` was composed by the pages: three of
them appended it on the engineer's behalf, and the domain expert's payload came back
without the framework in it. `/runs` and `/runs/<recordId>` were written later and did
neither — they did not need to append anything, because `/records` sends the framework's
own output unasked, so the omission that protected the other three was simply absent and
nothing said so. Four copies of a rule is not an enforced rule; it is four chances.

So `web/app/api.ts` asks the question now, once, for every screen — and the two things
below are what keep it the only one asking: nobody else knows the address of the product,
and nobody else composes the parameter. A page that wanted its own answer would have to
break one of them, and breaking either is red.

ponytail: a raw text scan, the same instrument and the same ceiling as INV-3's dynamic
import check (`tests/test_inv3_single_ge_import.py`). It catches the copy somebody
writes; it does not catch a URL assembled from three variables at runtime. The check
that does is the one that reads the response. It also cannot tell code from prose, so
the parameter is spelled out in one file and described in words everywhere else — which
is the same trade INV-5's scan makes, and it leaves the literal string greppable to
exactly the one module entitled to compose it.
"""

from __future__ import annotations

import pathlib

from conftest import REPO

# The one module allowed to know either of these.
DOOR = pathlib.Path("web/app/api.ts")

# The product's address, and the wire parameter that asks for the configuration. Both are
# scanned as literal text: what is banned is a second file KNOWING them.
ADDRESS = "DQ_API_URL"
PARAMETER = "configuration=1"

GENERATED = {"node_modules", ".next"}

# The mechanism inside the door, named so that deleting it fails here rather than only in
# the browser layer twenty minutes later. The question is ASKED once per door — the page
# load and the run stream — and `await` is in the constant so that the definition of the
# function does not count as one of its callers.
ASKED = "await frameworkVisible()"
REDACTOR = "withoutFramework"
DOORS = 2


def _web_sources() -> list[pathlib.Path]:
    return sorted(
        p
        for suffix in ("*.ts", "*.tsx")
        for p in (REPO / "web").rglob(suffix)
        if not set(p.parts) & GENERATED and p.name != "next-env.d.ts"
    )


def test_only_one_module_knows_where_the_product_answers() -> None:
    """Every screen's data comes through the door, so the door can decide things.

    This is the load-bearing half. The redaction below is worth nothing if a page can
    fetch the Python process itself — and a page that did would look perfectly ordinary
    in review, which is exactly how the run screens came to serve the framework to
    everybody.
    """
    files = _web_sources()
    assert len(files) > 5 and (REPO / DOOR) in files, (
        f"the scan collected {len(files)} files under web/, and {DOOR} was "
        f"{'among' if (REPO / DOOR) in files else 'NOT among'} them. A scan that lost its "
        "subject reports the same green as a clean tree."
    )
    offenders = [
        str(p.relative_to(REPO))
        for p in files
        if p.relative_to(REPO) != DOOR and ADDRESS in p.read_text()
    ]
    assert not offenders, (
        f"{offenders} name {ADDRESS}. Only {DOOR} may — every screen reads through it, which "
        "is what lets one place decide what a domain expert's document contains (SPEC F12 "
        "Rev 0.4). A component with the API's address is a component that can bypass that."
    )


def test_no_screen_asks_for_the_configuration_on_its_own_behalf() -> None:
    """The convention that failed, banned rather than re-agreed.

    A page composing `?configuration=1` is a page holding its own copy of the role rule —
    correct in the three that had it, absent in the two that did not, and unenforceable
    either way. The door asks now; a screen that asks again fails here.
    """
    offenders = [
        str(p.relative_to(REPO))
        for p in _web_sources()
        if p.relative_to(REPO) != DOOR and PARAMETER in p.read_text()
    ]
    assert not offenders, (
        f"{offenders} compose {PARAMETER!r}. That decision belongs to {DOOR}, which asks "
        f"`{ASKED}` on every screen's behalf, and to nothing else — bead dq-220 is what four "
        "copies of it cost. Ask `read()` for the thing and render what arrives."
    )


def test_the_door_still_takes_the_framework_out_for_everyone_else() -> None:
    """Asking is half of it; the other half is what comes back unasked.

    `/records` carries the framework's own output whether or not anybody asked, so the
    parameter alone never protected the run screens. The door strips it — on the page
    load and on the run stream, which is why the redactor has to appear on both.
    """
    source = (REPO / DOOR).read_text()
    assert REDACTOR in source, (
        f"{DOOR} no longer strips anything. The framework arrives unasked on `/records`, so "
        "the wire parameter alone leaves the run screens exactly as they were before dq-220."
    )
    asked = source.count(ASKED)
    assert asked == DOORS, (
        f"{DOOR} asks {ASKED} {asked} time(s); there are {DOORS} doors out of this file — the "
        "read path and the run stream — and each has to ask. A screen that is clean until "
        "somebody presses Run is not clean, and a third door that does not ask is dq-220 again."
    )
