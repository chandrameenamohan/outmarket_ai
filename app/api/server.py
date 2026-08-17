"""F8's front door: one action, one response, one line of JSON per verdict.

SPEC O-4 IS DECIDED HERE — **newline-delimited JSON over a single chunked POST
response**, read with `fetch` and a stream reader. The three candidates the spec
named, and why the other two lost:

  server-sent events   `EventSource` is GET-only and RECONNECTS BY ITSELF when the
                       stream closes. A run is not idempotent and costs real database
                       work, so the normal end of every run would re-trigger it — and
                       the fix is a sentinel event plus `es.close()` on the client,
                       which makes the transport safe only while the client remembers
                       to be careful. It also needs `data:` prefixing, blank-line
                       terminators and multi-line escaping to carry what
                       `json.dumps(event) + "\\n"` carries as it stands.
  one request per rule the client would drive N requests, so one run becomes N runs
                       that nothing can identify as one: N plans, N records, and no
                       terminal event to carry the id of the single record F9 stores.
                       It also puts the ordering — and therefore the coverage count —
                       in the client, which is where it may not live.
  chosen: NDJSON       a POST, because a run is an action; one line per event, framed
                       by `\\n`; no reconnect to defeat, no framing to parse.

THE CONSTRAINT THAT RULED OUT THE ARRANGEMENT NOBODY LISTED: a Next route handler
shelling out to `python -m ...` per request. `gx.get_context()` installs a
PROCESS-GLOBAL project (INV-3, LT-1b), so a process per request is one context per
request wearing a disguise — and it is measurably the wrong shape anyway: a cold
process pays the framework import plus a 1.16 s connect, measured at 6.43 s for its
first rule against 2.98 s warm. So this is a long-lived process, `connect()` is called
once before it serves, and the handler holds no framework state of its own.

WHY THE STANDARD LIBRARY. `ThreadingHTTPServer` streams by writing to a socket, which
is the entire requirement; a framework would add a dependency, a lockfile and an
ASGI worker model to a program with one route. `protocol_version` stays HTTP/1.0 so the
response is delimited by the close rather than by chunk framing we would have to write
ourselves. ponytail: no CORS headers and no static file serving — `web/` proxies this
through its own origin, which is one route handler there against a header here that
would be wrong the moment anything else is deployed. Ceiling: single process, no TLS,
no request limits. It is the demo's server, and B22 is what puts it behind compose.

WHAT THIS FILE IS NOT ALLOWED TO BECOME: a second place where rules are chosen, results
are read or verdicts are worded. Everything below the socket is `app/dq/run.py`.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

from app.dq import normalise, profile, run
from app.rules import schema as live
from app.rules import store

# The one route. A run is an action on a table, so the table is in the path and there
# is no body to parse; `POST` because running one is not a safe, repeatable read.
RUN_ROUTE = "/runs"

# Not `application/json`: the body is a SEQUENCE of JSON documents, and a client that
# waited to parse it as one object would wait for the whole run — which is the exact
# behaviour this endpoint exists to avoid.
NDJSON = "application/x-ndjson"

PORT_VAR = "DQ_API_PORT"
DEFAULT_PORT = 8000


def plan(table: str) -> tuple[normalise.Scan, tuple[dict[str, Any], ...], tuple[str, ...]]:
    """Everything a run needs, resolved BEFORE the first byte of the response is sent.

    Order matters. Resolving here means a table that does not exist, a table with no
    accepted rules, or an unreachable database is a status code with a sentence in it —
    not a 200 that streams a "started" event and then dies, which a caller has no
    honest way to render.

    `primary_key()` is also the SPEC §3.1 check: it reads the LIVE schema, so a table
    name that reached us from outside is proven real before it is composed into SQL by
    anything downstream. `ROW_LIMIT` is imported here rather than at the top of the file
    so that importing this module costs no framework import; it is INV-5's marker at its
    origin, and carrying it into the `Scan` is what makes the disclosure recoverable.

    ponytail: the disclosure's denominator is the CACHED profile's row count (F2, five
    minutes), because the denominator may not come from the thing being disclosed —
    `element_count` is the framework's, and a capped run and an honest small table
    produce identical output (LT-1a). The same number is ALSO INV-4's denominator, so
    `magnitude`'s "of 500,000 rows scanned · 0.03%" inherits the staleness: on a busy
    table the count and the share come from two different moments, up to five minutes
    apart. That is the price of a denominator the run can defend, and it is named here
    because this line is where both of them are decided. Ceiling: on a cold cache this
    pays the profiler's measured 7.98 s before the response starts, and the rules page
    a run is triggered from has already warmed it. The upgrade path is one `select
    count(*)`, which is a second statement in a module whose whole argument is that it
    issues one.
    """
    from app.dq import ge_runtime

    identifiers = live.primary_key(table)
    specs = normalise.executable(store.revisions(table=table))
    if not specs:
        raise ValueError(
            f"{table} has no accepted rules, so a run would report success without checking "
            "anything — the one result this product may never produce."
        )
    scan = normalise.Scan(table, profile.of(table).total_rows, ge_runtime.ROW_LIMIT)
    return scan, specs, identifiers


class Handler(BaseHTTPRequestHandler):
    """One verb, one route. Everything else answers 404 or 501 without being written.

    There is deliberately no `do_GET`: a polling endpoint is the thing O-3 rejected, so
    the absence is the design and `BaseHTTPRequestHandler`'s own 501 is a better refusal
    than one written here.
    """

    protocol_version = "HTTP/1.0"

    def do_POST(self) -> None:  # the base class names the verb; the case is not ours
        table = _table(self.path)
        if table is None:
            self._refuse(404, f"POST {RUN_ROUTE}/<table> is the only route this server has.")
            return
        try:
            scan, specs, identifiers = plan(table)
        except (LookupError, RuntimeError, ValueError) as exc:
            self._refuse(422, str(exc))
            return

        self.send_response(200)
        self.send_header("Content-Type", NDJSON)
        # No Content-Length, and never one: the length is not known until the run is
        # over, and a client that received one would wait for the whole body.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for event in run.stream(scan, specs, identifiers):
                self.wfile.write(json.dumps(event).encode() + b"\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # The caller walked away mid-run. The generator is abandoned here, so its
            # last line never runs and nothing is stored — an interrupted run leaves the
            # previous record as the most recent one (SPEC F9).
            return

    def _refuse(self, code: int, message: str) -> None:
        body = json.dumps({"event": "refused", "message": message}).encode() + b"\n"
        self.send_response(code)
        self.send_header("Content-Type", NDJSON)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(port: int | None = None) -> None:
    """Warm the datasource, then serve. Both halves at boot, in that order, once.

    The warm-up is not an optimisation: it is what keeps the 1.16 s connect out of the
    number a user watches, and it is where INV-3's one-context-per-process becomes a
    fact about the running program rather than about the source.
    """
    from app.dq import ge_runtime

    ge_runtime.connect()
    address = ("", port if port is not None else int(os.environ.get(PORT_VAR, DEFAULT_PORT)))
    with ThreadingHTTPServer(address, Handler) as httpd:
        httpd.serve_forever()


def _table(path: str) -> str | None:
    """`/runs/orders` -> `orders`. Anything else is not this route."""
    parts = urlparse(path).path.strip("/").split("/")
    if len(parts) == 2 and f"/{parts[0]}" == RUN_ROUTE and parts[1]:
        return unquote(parts[1])
    return None


if __name__ == "__main__":
    serve()
