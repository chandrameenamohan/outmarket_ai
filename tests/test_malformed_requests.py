"""Bead dq-abs · what this server does with input nobody anticipated.

A hostile pass against the live deployment typed `GET /rules/not-a-uuid` and got a
**502**, and the page in front of it printed

    api.railway.internal:8000 did not answer: TypeError: fetch failed

Two defects, and the second is the one that matters. There was no 502 anywhere in this
codebase: the driver refused PostgreSQL's `::uuid` cast, the exception left `do_GET`,
`ThreadingHTTPServer` closed the connection with nothing written on it, and the PROXY in
front invented a status code and a sentence — naming the private host and port of the
internal service to whoever typed the bad URL (SPEC §3.1).

So the checks below are in three layers, and none of them is per-route:

  1. THE SHAPE OF AN ID is refused where every rule id in the product arrives —
     `app/rules/store.py::latest`, the same guard `app/dq/runs.py::find` has carried
     since F13. A malformed id is a 404 with a sentence, not a database error.
  2. NOTHING ESCAPES A VERB. `app/api/refuse.py::Refusing.guard` wraps both route
     chains, so an unexpected content type is a 422 and an exception nobody predicted
     is a 500 — a status code either way, never a dropped connection.
  3. NOTHING USER-VISIBLE NAMES A PRIVATE THING. Every body produced above is scanned
     for hostnames, ports, driver names and stack traces, and the one refusal `web/`
     writes for itself is read out of the source.

The server is driven over a REAL SOCKET with no database anywhere: every case here is
refused before the first statement would be issued, which is itself the claim — a
malformed id costs a round trip to Singapore only if the shape check is missing.
"""

from __future__ import annotations

import contextlib
import http.client
import pathlib
import re
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import psycopg2
import pytest

from app.api import refuse, server
from app.db import unreachable
from conftest import REPO

# The ids the hostile pass actually typed, plus the near-misses that make the check a
# check rather than a demonstration: a uuid one character short, a percent-encoded path
# traversal, and an embedded NUL. All of them are `GET /rules/<this>`.
MALFORMED_IDS = [
    "not-a-uuid",
    "abc",
    "123",
    "%20",
    "foo-bar",
    "00000000-0000-0000-0000-00000000000",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "a%00b",
    "1'%20or%20'1'='1",
]

# A well-formed uuid, so the revision route below is refused for the CONTENT TYPE and
# not for the id. Nothing is ever stored under it; the body never gets that far.
WELL_FORMED = "34d8eec2-0823-40ba-bf4c-4a6f8dbe603e"

# What a response a stranger can read may never contain. `railway.internal` and `8000`
# are the two the live defect leaked; the rest are the same class of fact one layer
# down, and they are here because the fix is "say nothing about the inside", not
# "remove that one string".
PRIVATE = [
    "railway.internal",
    "8000",
    "5432",
    "supabase",
    "psycopg2",
    "Traceback",
    'File "/',
]

# What psycopg2 actually writes when the pooler does not answer, down to the resolved
# addresses. Injected rather than provoked, because provoking it means a real DSN and a
# real timeout in `make check` — and the point is the SHAPE of the text, not that a
# socket can time out. Every one of these facts reached a browser (see the test below).
DRIVER_TEXT = (
    'connection to server at "aws-0-ap-southeast-1.pooler.supabase.com" '
    "(52.77.146.31), port 5432 failed: timeout expired\n"
    "connection to server at ... (54.255.219.82), port 5432 failed: Operation timed out\n"
    "\tIs the server running on that host and accepting TCP/IP connections?"
)

WEB_DOOR = pathlib.Path("web/app/api.ts")

# The one address in `web/`, and the only place a `fetch` to it may be written. Counted
# rather than merely found: two doors go out of that file and one of them had no `catch`.
API_ADDRESS = "fetch(BASE"


@contextlib.contextmanager
def _running() -> Iterator[int]:
    """The real handler on a real socket. No database is reachable and none is needed."""
    with ThreadingHTTPServer(("127.0.0.1", 0), server.Handler) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            yield int(httpd.server_address[1])
        finally:
            httpd.shutdown()


def _ask(port: int, method: str, path: str, body: str = "", ctype: str = "") -> tuple[int, str]:
    """One request, one (status, body). A closed connection with no status raises here."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        conn.request(method, path, body or None, {"Content-Type": ctype} if ctype else {})
        response = conn.getresponse()
        return response.status, response.read().decode(errors="replace")
    finally:
        conn.close()


def test_every_malformed_rule_id_is_refused_with_a_four_hundred_and_a_reason() -> None:
    """The table the bead asks for: nine bad ids, nine 4xx, no 502, no dead socket.

    404 rather than 400 is deliberate and is `app/dq/runs.py::find`'s answer, arrived at
    for F13 and now shared: "there is no rule with that id" and "that is not an id at
    all" are the same fact to the person who followed the link, and only one of them is
    a sentence they can act on. `web/app/rules/[ruleId]/page.tsx` already turns a 404
    into `notFound()`, so the shape check reaches the reader as a page rather than as a
    banner about a database.

    An unreachable socket is NOT a passing case here. `_ask` raises on a connection that
    closes with no status line, which is exactly the failure mode being fixed — a test
    that tolerated it would go green on the defect.
    """
    with _running() as port:
        answers = {rid: _ask(port, "GET", f"/rules/{rid}") for rid in MALFORMED_IDS}

    wrong = {rid: status for rid, (status, _) in answers.items() if status != 404}
    assert not wrong, (
        f"malformed rule ids answered {wrong}. A bad id is a 404 — a 5xx says the server "
        "broke, and a 502 says it never answered at all, which is how this reached a proxy."
    )
    silent = {rid: body for rid, (_, body) in answers.items() if "message" not in body}
    assert not silent, (
        f"these refusals carry no sentence: {sorted(silent)}. A status code with an empty "
        "body tells the reader nothing about what was wrong with what they typed (INV-4)."
    )


def test_an_unexpected_content_type_is_refused_where_the_body_is_parsed() -> None:
    """A form-encoded body to a JSON route: 422, and the same for every POST at once.

    This is the half of the bead that says the gap is "input we did not anticipate" and
    not "that one route". A JSON body to `POST /rules/<id>/revision` already 422'd, and
    a form-encoded one 502'd — because `request.body()` raises where the route chain
    calls it rather than inside `_read`'s try. The fix is not a branch in this route: it
    is that BOTH verbs run inside `guard()`, so anything the parse of a request raises
    is a status code. Two routes are checked because one would prove a branch.
    """
    form = "statement=every+order+has+a+total&status=accepted"
    with _running() as port:
        revision = _ask(
            port,
            "POST",
            f"/rules/{WELL_FORMED}/revision",
            form,
            "application/x-www-form-urlencoded",
        )
        draft = _ask(port, "POST", "/drafts/orders", form, "application/x-www-form-urlencoded")

    for name, (status, body) in {"revision": revision, "draft": draft}.items():
        assert status == 422, (
            f"the {name} route answered {status} to a form-encoded body. A body we cannot "
            "parse is the caller's mistake and is a 4xx; it was a dropped connection."
        )
        assert "not JSON" in body, (
            f"the {name} refusal does not say what was wrong with the body: {body!r}. The "
            "sentence is the difference between a refusal and a wall."
        )


def test_an_exception_nobody_predicted_is_a_status_code_and_says_nothing_about_us(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catch-all, driven with the driver error that caused the live 502.

    The shape guard above means this exact exception can no longer arise from a bad id —
    which is why it is INJECTED here rather than provoked. What is being checked is the
    net under every future one: a reader gets a status code and one incurious sentence,
    and the driver's own text — which carries the host, the port and the SQL — reaches
    the process log instead.
    """
    leak = psycopg2.DataError(
        'invalid input syntax for type uuid: "abc"\n'
        "connection to server at db.zzzzzzzz.supabase.co, port 5432 failed"
    )

    def explode(*_: object, **__: object) -> None:
        raise leak

    monkeypatch.setattr(server.view, "of", explode)
    with _running() as port:
        status, body = _ask(port, "GET", f"/rules/{WELL_FORMED}")

    assert status == 500, (
        f"an unhandled {type(leak).__name__} answered {status}. Whatever else it is, it has "
        "to be a response — a request that ends in silence is reported by whoever is in front."
    )
    assert refuse.UNANTICIPATED in body, (
        f"the 500 body is {body!r}, not the one sentence this side writes for a failure it "
        "did not anticipate. A refusal composed from the exception is how the topology got out."
    )
    assert "supabase" not in body and "5432" not in body and "uuid" not in body, (
        f"the driver's own words reached the reader: {body!r}. That text names the database "
        "host, its port and the statement — none of it is usable by the person who asked."
    )


def test_a_database_that_does_not_answer_is_ours_to_own_and_not_the_callers_mistake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect the grep below could not see, and the reason it could not.

    Every other case in this file is refused BEFORE the database is touched, so the one
    class of body that could carry a hostname was the one class never produced. It read

        422 {"message": "SUPABASE_DB_URL_ANALYSIS did not answer: connection to server
        at \\"aws-0-ap-southeast-1.pooler.supabase.com\\" (52.77.146.31), port 9999 …"}

    — the driver's own text interpolated into an `Unavailable`, which is a `RuntimeError`
    and therefore landed in `REFUSALS`. `web/app/api.ts::call()` renders `message`
    verbatim, so the pooler host, three of its addresses and its port reached the browser
    of whoever loaded a screen during an outage. Two facts are asserted, because the
    original was wrong twice: the sentence says nothing about the inside, and the STATUS
    IS A 503 — an unreachable database is not the caller's mistake, and a reader told
    "what you sent was wrong" about an outage retries the one thing that cannot help.
    """

    def dead(*_: object, **__: object) -> None:
        raise psycopg2.OperationalError(DRIVER_TEXT)

    monkeypatch.setattr(server.live, "connect", dead)
    with _running() as port:
        status, body = _ask(port, "GET", "/tables")

    assert status == 503, (
        f"an unreachable database answered {status}. 4xx is 'your request was wrong' and "
        "the request was fine — the database was not there, which is ours to own."
    )
    assert unreachable.NOT_ANSWERING in body, (
        f"the refusal is {body!r}, not the one sentence written for a database that did not "
        "answer. A message composed from the driver's exception is how the topology got out."
    )
    for secret in ("pooler", "52.77.146.31", "TCP/IP", "OperationalError"):
        assert secret not in body, (
            f"the driver's own words reached the reader: {secret!r} in {body!r}. That text "
            "names the host, its addresses and its port; none of it is theirs to act on."
        )


def test_no_response_a_stranger_can_read_names_an_internal_host_or_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The grep the bead asks for, run over every refusal this file can produce.

    One check rather than an assertion bolted onto each of the three above, because the
    claim is about the SET of things this server says, not about any one route: a body
    added tomorrow that quotes an address is caught here even if its own check passes.

    THE LAST BODY IS THE ONE THIS CHECK USED TO BE BLIND TO. The five above it are all
    refused before a connection is opened, so the grep only ever read bodies that had no
    hostname available to leak — green on the one shape it was written to stop. The
    database is made to fail with the driver's real text so that a body of that class is
    in the set too.
    """

    def dead(*_: object, **__: object) -> None:
        raise psycopg2.OperationalError(DRIVER_TEXT)

    with _running() as port:
        bodies = [_ask(port, "GET", f"/rules/{rid}")[1] for rid in MALFORMED_IDS]
        bodies.append(_ask(port, "GET", "/no-such-route")[1])
        bodies.append(_ask(port, "POST", "/rules/x/y/z/w")[1])
        bodies.append(_ask(port, "GET", "/records/not-a-uuid")[1])
        bodies.append(_ask(port, "POST", f"/rules/{WELL_FORMED}/revision", "x=1", "text/plain")[1])
        monkeypatch.setattr(server.live, "connect", dead)
        bodies.append(_ask(port, "GET", "/tables")[1])

    leaked = [(secret, body) for body in bodies for secret in PRIVATE if secret in body]
    assert not leaked, (
        f"a user-visible response names something private: {leaked}. SPEC §3.1 — a reader "
        "has no use for the internal address and a prober has every use for it."
    )


def test_the_web_refusal_banner_quotes_no_address_of_its_own() -> None:
    """`web/` writes exactly one refusal itself, and this is the line that leaked.

    It read ``refused: `${BASE} did not answer: ${error}` `` — `BASE` being
    `http://api.railway.internal:8000` in the deployment, and `error` being the
    JavaScript error class. The banner is the only sentence on that side not composed by
    the module that refused, so it is the only one that can name something the server's
    own refusals never do; a source check is what keeps it that way, since no fixture can
    reproduce a private hostname that is only private in production.
    """
    text = (REPO / WEB_DOOR).read_text()
    banners = re.findall(r"refused:\s*(`[^`]*`|[A-Za-z_][A-Za-z0-9_]*)", text)
    assert (
        banners
    ), f"{WEB_DOOR} composes no refusal at all any more; this check has lost its subject"
    quoted = [b for b in banners if "${BASE}" in b or "railway" in b or ":8000" in b]
    assert not quoted, (
        f"{WEB_DOOR} puts the API's address in a refusal a reader sees: {quoted}. It belongs "
        "in console.error, which lands in the service log where somebody can act on it."
    )
    assert "console.error" in text, (
        f"{WEB_DOOR} no longer logs the cause anywhere. Taking the address off the page is "
        "only half of it — an operator who cannot see why the call failed is worse off."
    )


def test_the_second_web_door_cannot_be_the_one_that_forgot_the_catch() -> None:
    """One `fetch` to the API in `web/`, so there is one place it can fail.

    `call()` had the try/catch and `stream()` did not, so with the Python process down
    `POST /run?table=orders` answered **500 with a zero-byte body** — nothing for
    `panel.tsx`'s line reader to parse, and a status code shown to a domain expert. It
    leaked no address, so it was never an acceptance failure; it was the same class of
    gap on the door that got the redaction and not the refusal.

    Counting the occurrences is what makes this a check rather than a demonstration: a
    third door added tomorrow either goes through the one guarded call or fails here. It
    is a text scan with the ceiling every text scan in this repo has (see
    `tests/test_f12_framework_boundary.py`) — it catches the `fetch` somebody writes, not
    one assembled at runtime.
    """
    text = (REPO / WEB_DOOR).read_text()
    uses = text.count(API_ADDRESS)
    assert uses == 1, (
        f"{WEB_DOOR} writes {API_ADDRESS!r} {uses} time(s). Exactly one is right: every door "
        "out of this file goes through the call that wraps it, so none of them can be the "
        "one without a catch. Route the new one through `ask()` instead of fetching again."
    )


def test_no_response_advertises_the_runtime_this_server_is_written_in() -> None:
    """The `Server:` header, which `guard()` cannot reach and every response carries.

    `BaseHTTPRequestHandler` defaults to `BaseHTTP/0.6 Python/3.12.5` — the runtime and
    its patch version, handed to anybody who connects, including on the stock 501 the
    base class writes for a verb no handler exists for. Same disclosure class as the
    private hostname (SPEC §3.1), on the one door the guard is not in front of, so it is
    fixed with two class attributes rather than with a handler per verb.
    """
    with _running() as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
        try:
            conn.request("GET", "/no-such-route")
            refusal = conn.getresponse()
            refusal.read()
            banner = refusal.getheader("Server") or ""
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
            conn.request("PUT", "/rules")
            stock = conn.getresponse()
            stock.read()
            unguarded = stock.getheader("Server") or ""
        finally:
            conn.close()

    for where, header in {"a refusal": banner, "an unsupported verb": unguarded}.items():
        assert "Python" not in header and "BaseHTTP" not in header, (
            f"{where} advertises the runtime: {header!r}. A version number is what a prober "
            "matches against a CVE list, and it is no use at all to the person who asked."
        )
