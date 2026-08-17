"""F8 · the front door a run is triggered through, and the shape of what comes back.

SPEC O-4 is decided in `app/api/server.py` — newline-delimited JSON over one chunked
POST response — and these are the checks that make the decision load-bearing rather
than documented. Two of them read the module with `ast`, because the execution model
is visible in the code's shape: one verb, no 202, no header that tells a caller to
come back later. The other two drive a REAL SOCKET against the real handler with the
run generator faked out, so the transport is proven to stream without a database, a
framework or a browser anywhere in `make check`.

Nothing here asserts a clock. The streaming check holds the run open behind a latch
the TEST releases, so what is asserted is that two events could be read and parsed
while the third was still blocked — an ordering fact, not a timing one (VERIFICATION.md
§9.1).

The engine those events come from is checked next door in `tests/test_run_stream.py`.
"""

from __future__ import annotations

import ast
import http.client
import json
import pathlib
import threading
from http.server import ThreadingHTTPServer
from typing import Any

from app.api import server
from app.dq import normalise, run
from conftest import REPO, module_constant

TABLE = "orders"
SEEDED_ROWS = 500_000

SCAN = normalise.Scan(TABLE, SEEDED_ROWS)
SPECS: list[dict[str, Any]] = [
    {"type": "expect_column_values_to_be_between", "kwargs": {"column": "order_total"}}
]

SERVER = pathlib.Path("app/api/server.py")


def test_trigger_returns_a_stream_and_no_poll_route_exists() -> None:
    """The execution model, read off the transport: one action, one streaming response.

    A job queue leaves structural fingerprints — a 202 with a job id, a second verb to
    poll it with, a Retry-After telling the caller when to come back. The check is on
    the code rather than on the prose.

    **RE-AIMED, NOT RELAXED, BY F14 (bead dq-rbf.1).** This used to assert
    `handlers == {"do_POST"}` — the absence of `do_GET` was the mechanism. F14's
    permalink needs a read surface (`GET /rules/<id>`, so a pasted link renders a rule
    with no prior navigation), so the verb now exists and the absence can no longer
    carry the claim. What O-3 actually forbids is narrower and is what is asserted here
    instead: **no run is addressable by GET.** `do_GET` may not so much as mention
    `RUN_ROUTE`, which is a stronger statement than "this file has one verb" — it holds
    however many read routes get added later, and it is the sentence O-3 wrote. The
    socket half is next door: `GET /runs/orders` answers 404, not a run's status.
    """
    tree = ast.parse((REPO / SERVER).read_text())
    handlers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("do_")
    }
    assert handlers == {"do_GET", "do_POST"}, (
        f"{SERVER} answers {sorted(handlers)}. A run is triggered by one action and streams "
        "its own verdicts; the read surface answers GET and nothing else answers anything."
    )
    reader = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "do_GET"
    )
    named = {node.id for node in ast.walk(reader) if isinstance(node, ast.Name)}
    assert "RUN_ROUTE" not in named, (
        f"{SERVER}'s do_GET reaches for RUN_ROUTE. A run addressable by GET is the polling "
        "endpoint O-3 rejected, whatever the response body is called."
    )
    codes = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, int)
    }
    assert 202 not in codes, (
        f"{SERVER} can answer 202. Accepted-and-come-back-later IS the job queue: it returns "
        "the same 14 s later with a polling endpoint and a stale result added (SPEC O-3)."
    )
    headers = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "send_header"
        and isinstance(node.args[0], ast.Constant)
    }
    assert "Retry-After" not in headers and "Location" not in headers, (
        f"{SERVER} sends {sorted(str(header) for header in headers)}. Both of those tell a "
        "caller to come back for a result later, which is the model this one does not use."
    )
    assert server.NDJSON == "application/x-ndjson", (
        "the response is a sequence of JSON documents; declaring application/json invites a "
        "client to wait for the whole run before parsing anything"
    )


def test_no_request_handler_prepares_a_run_after_the_response_has_begun() -> None:
    """Everything that can fail is resolved before the first byte. INV-3's half, one level up.

    `tests/test_inv3_single_ge_import.py` already fails the gate on any module outside
    the runtime calling `get_context()`, which covers this handler — so what is left to
    check is the arrangement that makes one context per PROCESS achievable: the plan is
    built, and the datasource warmed at boot, before anything is written to the socket.
    A handler that planned mid-stream could only report a failure by hanging up.

    **Widened by F14 (bead dq-rbf.1), which is why it no longer names `do_POST`.** The
    run moved out of `do_POST` into its own method when the rule routes arrived, so a
    check pinned to one function name would have gone green on a file where the run had
    simply moved somewhere unwatched. It now finds whichever method calls `plan`,
    asserts there is exactly one, and asserts the ordering inside it — which is the
    sentence the test's own name has always made.
    """
    tree = ast.parse((REPO / SERVER).read_text())
    planners = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "plan"
            for call in ast.walk(node)
        )
    ]
    assert len(planners) == 1, (
        f"{SERVER} plans a run in {[p.name for p in planners]}. Exactly one function may — "
        "two of them is two answers to 'what does this run check', one of them stale."
    )
    handler = planners[0]
    plan_line = next(
        node.lineno
        for node in ast.walk(handler)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "plan"
    )
    sent = [
        node.lineno
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "end_headers"
    ]
    assert sent, f"{SERVER}::{handler.name} plans a run and never sends headers"
    assert plan_line < min(sent), (
        f"{SERVER} plans the run at line {plan_line}, after headers went out at {min(sent)}. "
        "A table that does not exist must be a status code, not a 200 that dies mid-stream."
    )

    boot = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "serve"
    )
    warmed = {
        node.func.attr
        for node in ast.walk(boot)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "connect" in warmed, (
        f"{SERVER}::serve does not warm the datasource. The 1.16 s connect (LT-1b) then lands "
        "inside the first run a user watches — measured at 6.43 s cold against 2.98 s warm."
    )


def test_the_run_path_reads_the_direct_url_setting_and_never_the_pooled_one() -> None:
    """The connection choice, checked where it is made rather than where it is described.

    The transaction pooler is 21% slower on this workload — 17.94 s against 14.84 s on
    identical work (LT-1b) — so the analysis credential is a port-5432 URL and no module
    under `app/` may reach for the pooled one. Both halves are asserted: the DSN the
    runtime reads, and the port `.env.example` documents behind that name.
    """
    dsn_var = module_constant("app/dq/ge_runtime.py", "DSN_VAR")
    assert dsn_var == "SUPABASE_DB_URL_ANALYSIS", (
        f"the run path reads {dsn_var}. Read out of the source rather than imported: that "
        "module imports the framework, which `make check` deliberately does not have."
    )

    documented = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in (REPO / ".env.example").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    }
    assert ":5432/" in documented[dsn_var], (
        f"{dsn_var} is documented as {documented[dsn_var]!r}, which is not the direct "
        "connection. The pooler costs 21% on identical work (LT-1b)."
    )
    assert ":6543/" in documented["SUPABASE_DB_URL_POOLED"], (
        ".env.example no longer documents the pooled URL on 6543, so the check above is "
        "comparing the direct port against nothing"
    )

    offenders = [
        path.relative_to(REPO)
        for path in (REPO / "app").rglob("*.py")
        if "SUPABASE_DB_URL_POOLED" in path.read_text()
    ]
    assert not offenders, f"{offenders} reach for the pooled connection; F8 runs direct."


def test_the_endpoint_streams_one_json_line_per_verdict_as_it_lands(monkeypatch) -> None:
    """The transport, over a real socket, with no database and no framework anywhere.

    A run whose second verdict is held behind a latch: the client must be able to read
    and parse the first two lines while the third is still blocked. That is O-4's whole
    claim — a caller renders each verdict as it arrives — and it is asserted as reads
    that complete rather than as elapsed time. The latch is released from the test, so
    nothing here depends on how fast anything is.
    """
    latch = threading.Event()

    def held(*_: Any, **__: Any):
        yield {"event": run.STARTED, "table": TABLE, "total": 2, "reported": 0, "rules": []}
        yield {"event": run.VERDICT, "index": 0, "total": 2, "reported": 1, "result": {}}
        assert latch.wait(timeout=10), "the test never released the latch"
        yield {"event": run.COMPLETED, "record_id": "record-1", "total": 2, "reported": 2}

    monkeypatch.setattr(server, "plan", lambda table: (SCAN, SPECS, ()))
    monkeypatch.setattr(server.run, "stream", held)

    with ThreadingHTTPServer(("127.0.0.1", 0), server.Handler) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=15)
        conn.request("POST", f"{server.RUN_ROUTE}/{TABLE}")
        response = conn.getresponse()

        assert response.status == 200
        assert response.getheader("Content-Type") == server.NDJSON
        assert response.getheader("Content-Length") is None, (
            "a Content-Length means the body was known before the run finished, which it "
            "cannot be — and a client that trusts it waits for the whole run"
        )

        started = json.loads(response.readline())
        verdict = json.loads(response.readline())
        assert (started["event"], verdict["event"]) == (run.STARTED, run.VERDICT), (
            "two events were readable while the run was still blocked, but they are not the "
            "rule list and the first verdict"
        )

        latch.set()
        rest = [json.loads(line) for line in response]
        assert [e["event"] for e in rest] == [run.COMPLETED]
        conn.close()
        httpd.shutdown()


def test_an_unknown_route_is_refused_before_a_run_is_planned(monkeypatch) -> None:
    """A miss costs no database round trip, and the run route still answers no GET.

    The GET half changed shape with F14 (bead dq-rbf.1) and not meaning. This used to
    assert **501**, produced by `BaseHTTPRequestHandler` because the server had no
    `do_GET` at all; the read surface F14 needs gave it one, so the same request is now
    refused **404** by the route table instead of by the absence of a verb. What is
    asserted is unchanged and is the thing O-3 settled: there is no way to ASK this
    server about a run. Verdicts arrive on the socket the run is streaming down, and
    nothing anywhere answers "is it finished yet".
    """
    planned: list[str] = []
    monkeypatch.setattr(server, "plan", lambda table: planned.append(table))
    with ThreadingHTTPServer(("127.0.0.1", 0), server.Handler) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=15)
        conn.request("POST", "/runs")
        assert conn.getresponse().status == 404

        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=15)
        conn.request("GET", f"{server.RUN_ROUTE}/{TABLE}")
        assert (
            conn.getresponse().status == 404
        ), "a GET answered here would be the polling endpoint the execution model rejected"
        conn.close()
        httpd.shutdown()
    assert planned == [], f"a run was planned for {planned} before the route was checked"
