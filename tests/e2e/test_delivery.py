"""SPEC §3's delivery promise, checked instead of asserted in a README.

SPEC §3 says the product is delivered as a **deployed URL and `docker-compose`**.
Both are the same claim — *someone who is not us can run this* — so both are checked
the same way and by the same means: point the browser hygiene smoke that already
exists at the stack in question and require it to come back green.

**NOTHING HERE RE-IMPLEMENTS A CHECK.** `tests/e2e/test_ui_hygiene.py` is the smoke;
these two tests are a subprocess call to it with `APP_URL` and `DQ_API_URL` pointing
somewhere else. A second copy of "is the console clean" that drifted from the first
would be worse than no check at all, and the point of the exercise is precisely that
the deployed thing passes the checks the local thing passes — which is only true if
they are the same checks.

**WHY A SUBPROCESS AND NOT A FIXTURE.** `app_url` and `api_url` are session-scoped
and read the environment once, which is the right design for a layer that drives one
app: it makes "the browser layer ran against a real server" a session-level fact. A
per-test override would have to reach inside that and would leave the parametrised
hygiene cases addressing two different servers in one session. A subprocess gets a
clean session with a clean environment — and its exit code is NOT the whole result,
because pytest exits 0 on a run in which everything skipped. See `_smoke`.

**Unset -> PENDING, set but dead -> FAIL.** The same contract `conftest.app_url`
states and for the same reason: `make check-ui` is the only authority for "the UI
works", so it may never report success against a stack nobody started. A stack that
is not running was not asked for; a stack that was named and does not answer is a
failure, not an absence.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

from conftest import REPO, pending

pytestmark = pytest.mark.e2e

HYGIENE = pathlib.Path(__file__).with_name("test_ui_hygiene.py")

# The three hygiene checks over the seven routes: console-clean, layout stability,
# accessibility. 21 cases, and every one of them is a fact about the DELIVERY —
# did the server render, did it render without errors, is what it rendered usable.
#
# Visual regression is deliberately NOT in the smoke, and the reason is the same one
# that keeps six of its seven states pending: what those screens render is a function of
# the store behind them, not of the code. Exactly ONE baseline is written today
# (`role-door.png`) and it is not approved either — nobody has staged it, so the check
# pends rather than compares. A diff run against a stack serving a different store would
# report on the contents of a DATABASE while wearing the costume of a check about
# deployment. That store is B23's subject, not this one's.
SMOKE = "console or layout_shift or accessibility"


def _answers(url: str, what: str) -> None:
    """Any HTTP response counts as alive; an OSError does not. Fail, never skip."""
    try:
        urllib.request.urlopen(url, timeout=15).close()
    except urllib.error.HTTPError:
        pass
    except OSError as exc:
        pytest.fail(
            f"{what}={url} does not answer ({exc}). A named stack that is not running is a "
            "broken delivery, not an absent one — start it, or unset the variable."
        )


def _smoke(app_url: str, api_url: str) -> str:
    """Run the hygiene smoke against this pair of URLs. Empty string means it passed.

    The verdict is RETURNED rather than asserted here, and that is the harness's rule
    rather than a preference: `tests/test_code_quality_thresholds.py` fails the gate on
    a test function whose own body neither asserts nor pends, precisely so that a check
    cannot delegate its judgement to a helper and become unreadable at the call site.
    So the helper reports and the test decides.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(HYGIENE),
            "-m",
            "e2e",
            "-k",
            SMOKE,
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO,
        env={**os.environ, "APP_URL": app_url, "DQ_API_URL": api_url},
        capture_output=True,
        text=True,
        check=False,
    )
    # EXIT 0 IS NOT THE WHOLE RESULT, and this is the one check where that matters most:
    # pytest also exits 0 when every selected test SKIPS, and this is the layer aimed at a
    # stack nobody in this session started — the place a fixture is most likely to pend.
    # "the delivered stack is green" may not be reported on the strength of 21 PENDINGs,
    # so the summary line has to say things passed and must not say anything skipped.
    if proc.returncode == 0 and " passed" in proc.stdout and "skipped" not in proc.stdout:
        return ""
    return (
        f"the hygiene smoke did not come back green against APP_URL={app_url} / "
        f"DQ_API_URL={api_url} (exit {proc.returncode}). A skip counts as a failure here: "
        "a check that cannot run against a delivered stack has not checked it.\n"
        f"{proc.stdout[-6000:]}\n{proc.stderr[-2000:]}"
    )


def _pair(prefix: str, how: str) -> tuple[str, str]:
    """Both URLs or neither. A half-configured target pends with the half it is missing."""
    app, api = os.environ.get(f"{prefix}_APP_URL"), os.environ.get(f"{prefix}_API_URL")
    if not app and not api:
        pending(f"{prefix}_APP_URL is unset — {how}")
    if not app or not api:
        missing = f"{prefix}_APP_URL" if not app else f"{prefix}_API_URL"
        pending(
            f"{missing} is unset. The smoke needs BOTH: the browser drives the Next app, and "
            "the rule permalink and run-record checks read the Python process behind it "
            "(conftest.rule_id / conftest.record). One without the other cannot run."
        )
    _answers(app, f"{prefix}_APP_URL")
    _answers(f"{api.rstrip('/')}/rules", f"{prefix}_API_URL")
    return app, api


def test_compose_stack_serves_the_smoke_route() -> None:
    """`docker compose up` on a clean clone with only `.env` serves the same green smoke.

    Run it by naming the ports compose published:

        docker compose up --build -d
        COMPOSE_APP_URL=http://localhost:3000 COMPOSE_API_URL=http://localhost:8000 \\
          make check-ui

    Two preconditions that are the stack's, not this check's, and both fail loudly
    rather than quietly passing:

      - **The store must hold at least one rule for `orders`.** `conftest.rule_id`
        reads one over HTTP and FAILS on an empty store, because F14's permalink
        check cannot be satisfied by a database with nothing in it. A stack pointed
        at a virgin `DQ_SCHEMA` has none yet — propose and accept one through the UI
        first, or point the stack at a schema that already has one.
      - **The database must be reachable FROM THE CONTAINER.** That is not the same
        question as "from this laptop": `db.<ref>.supabase.co` publishes AAAA records
        only, and Docker Desktop gives containers no IPv6 route, so the api service
        dies at boot with `Network is unreachable` while `psql` on the host is fine.
        README, "The IPv6 trap", has the detection and the fix.
    """
    failure = _smoke(*_pair("COMPOSE", "the local docker compose stack was not asked for"))
    assert not failure, failure


def test_deployed_url_serves_the_smoke_route() -> None:
    """The other half of SPEC §3: the URL a grader clicks answers the same smoke.

        DEPLOYED_APP_URL=https://... DEPLOYED_API_URL=https://... make check-ui

    `DEPLOYED_API_URL` is a genuine cost of checking a deployment this way and is
    worth naming rather than hiding: in the shipped topology the Python process is
    NOT public — `web/app/api.ts` reaches it server-side, which is what gives this
    product no CORS configuration and no API URL in the browser bundle. So a deployed
    stack has to expose it to be smoked, or this check pends. Pending is the honest
    outcome; a deployment check that quietly dropped the half it could not reach would
    report "deployed and green" on the strength of seven pages that render.
    """
    failure = _smoke(*_pair("DEPLOYED", "no deployment was named"))
    assert not failure, failure
