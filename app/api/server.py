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
are read or verdicts are worded. Everything below the socket is `app/dq/run.py` for the
run and `app/rules/view.py` for everything a screen reads.

THE READ SURFACE ARRIVED WITH F14 (bead dq-rbf.1) AND IS NOT THE POLLING ENDPOINT O-3
REJECTED. The distinction is worth stating because this file used to have no `do_GET` at
all and said so on purpose: what O-3 refused was a client asking "is the run finished
yet?", which is a second source of truth about a run that is already streaming down an
open socket. `GET /rules/<id>` answers a different question — what IS this rule — for a
reader who arrived from a pasted link with no run in flight, which is F14's whole
scenario. Nothing here polls anything, and there is still no way to ask about a run.

F13 (bead `dq-klv.4`) added the second read that could be mistaken for the same thing,
and it is not: `GET /records/<recordId>` answers with a run that is OVER. A record only
exists because a run finished and was written down, so there is no state it can report
that a client could wait on — which is the difference between reading a fact and polling
a job. The run route still answers no GET at all, on the socket and in the source
(`tests/test_run_endpoint.py`), and a run in flight remains addressable only by the
caller streaming it.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from app.api import refuse, request
from app.api.dualstack import DualStackServer
from app.api.refuse import NDJSON, REFUSALS
from app.dq import coverage, normalise, profile, run, runs
from app.rules import desk, store, view
from app.rules import schema as live

# A run is an action on a table, so the table is in the path and there is no body to
# parse; `POST` because running one is not a safe, repeatable read. A rule is a thing,
# so it is a noun with an id — and that id is what F14's permalink is made of.
RUN_ROUTE = "/runs"
RULE_ROUTE = "/rules"

# F13 · a written RECORD is a different noun from a run, and the difference is exactly
# the one O-3 settled. A run is an action that streams down the socket it was triggered
# on; there is no way to ask this server how one is getting on, and there never will be.
# A record is a fact that a completed run left behind — the thing F9's cache clause is
# about, the thing `/runs/[recordId]` addresses in the browser, and the only half of the
# pair a reload can render. So it answers GET, and the run does not: `GET /runs/orders`
# is still a 404, which is what `tests/test_run_endpoint.py` asserts on both the socket
# and the source. The browser route keeps the word "runs" because that is the word a
# person uses for what they are looking at; the API says which of the two nouns it means.
RECORD_ROUTE = "/records"

# F10's coverage dashboard takes no parameters at all: it is every table in the connected
# schema, ranked, and a `?bucket=` or `?sort=` would be the browsing controls SPEC F10
# lists as out of scope. The whole payload is one document because the ORDER is the
# product here — three buckets a client could fetch separately are three buckets a client
# could render in its own order, which is the one thing this screen may not allow.
TABLE_ROUTE = "/tables"

# F11's queue is its own noun and not a filter on `/rules`, because it is not one: it
# spans every table at once, it joins the rule store against the last COMPLETED run
# record, and it drops rules that are perfectly fine. `?table=` narrows it and is
# optional — the unscoped queue is the domain expert's front door, and an endpoint that
# demanded a table name would be the table list F11 forbids, wearing a query string.
REVIEW_ROUTE = "/review"

# F12's two BILLED doors, and they are POSTs for a reason that is not verb pedantry: each
# one costs a real model call (~$0.04, ~6.6 s — LT-2b), so neither may be reachable by a
# prefetch, a crawler or a back button, which is exactly what a GET invites. They are also
# two nouns rather than one endpoint with a mode, because they ask the model different
# questions from different inputs: a PROPOSAL is inferred from a table's statistics and
# arrives in a batch, a DRAFT is translated from one person's sentence and arrives alone
# or as a refusal. Neither of them writes anything — accepting is what writes (SPEC F12).
PROPOSAL_ROUTE = "/proposals"
DRAFT_ROUTE = "/drafts"

# The one query parameter that changes what a payload CONTAINS rather than which rows it
# selects: `?configuration=1` is SPEC F12's Rev 0.4 amendment on the wire. The engineer's
# screen asks for it and gets facing pages; the domain expert's screen does not, and the
# framework is then absent from the answer rather than hidden in it. See app/rules/view.py.
CONFIGURATION = "configuration"

# `NDJSON` is the RUN's content type and the refusal shape's; it and `REFUSALS` live in
# `app/api/refuse.py`, beside the one thing that writes with both. The read surface below
# answers with one document and says so.
JSON = "application/json"

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


class Handler(refuse.Refusing):
    """Every route the product has. Each verb dispatches in one short function and does
    no work itself.

    BOTH VERBS RUN INSIDE `self.guard()`, and that is bead dq-abs. The route chain below
    covers the requests we thought of; the guard covers the ones we did not, and turns
    them into a status code instead of a dropped connection a proxy reports as a 502 in
    its own words. It wraps `request.parse` too, because a path we cannot even split is
    the same class of problem as a body we cannot parse.

    `_ROUTES` is the whole route table as a sentence, and it is what a 404 says back —
    so a client that guesses wrong is told what this server actually has, which is the
    thing a hand-rolled HTTP handler loses first.

    ponytail: still an `if` chain. This file's earlier note put the ceiling at the fifth
    route and named the replacement — a dict keyed by `(verb, segment count)` — and the
    screens of E5 took it past that. The chain stays, because the replacement was
    written out against this and is not smaller: a dict entry plus a lookup plus a
    fallback is more code than an `elif` line that already reads as the route list.
    Ceiling restated where it belongs, on the reader rather than on a count: the chain
    goes the day `_ROUTES` stops being a sentence somebody can hold in their head.
    """

    protocol_version = "HTTP/1.0"

    def do_GET(self) -> None:  # the base class names the verb; the case is not ours
        with self.guard():
            segments, query = request.parse(self.path)
            if request.route(segments) == RULE_ROUTE and len(segments) == 1:
                self._read(
                    lambda: desk.workbench(
                        request.one(query, "table"), request.flag(query, CONFIGURATION)
                    )
                )
            elif request.route(segments) == RULE_ROUTE and len(segments) == 2:
                self._read(lambda: view.of(segments[1], request.flag(query, CONFIGURATION)))
            elif request.route(segments) == TABLE_ROUTE and len(segments) == 1:
                self._read(coverage.listing)
            elif request.route(segments) == REVIEW_ROUTE and len(segments) == 1:
                self._read(lambda: view.queue(request.optional(query, "table")))
            elif request.route(segments) == RECORD_ROUTE and len(segments) == 1:
                self._read(lambda: view.last_run(request.one(query, "table")))
            elif request.route(segments) == RECORD_ROUTE and len(segments) == 2:
                self._read(lambda: view.run_record(segments[1]))
            else:
                self.refuse(404, _ROUTES)

    def do_POST(self) -> None:
        with self.guard():
            segments, query = request.parse(self.path)
            configured = request.flag(query, CONFIGURATION)
            if request.route(segments) == RUN_ROUTE and len(segments) == 2:
                self._run(segments[1])
            elif request.route(segments) == RULE_ROUTE and len(segments) == 1:
                self._batch()
            elif request.route(segments) == RULE_ROUTE and len(segments) == 2:
                self._judge(segments[1])
            elif (
                request.route(segments) == RULE_ROUTE
                and len(segments) == 3
                and segments[2] == "revision"
            ):
                body = self._body()
                # `asyncio.run` on this request's own thread, here and on the two billed
                # routes below. F12's authoring path is `async` because the Agent SDK is,
                # and this server is threads rather than an event loop
                # (ThreadingHTTPServer; see the module docstring) — so each request makes
                # a loop, runs the one call and closes it. There is no loop to conflict
                # with and nothing shared between them, and the setup is microseconds
                # beside a call that spends 6.6 s on the network (LT-2b).
                self._read(lambda: asyncio.run(desk.revise(segments[1], *request.revision(body))))
            elif request.route(segments) == PROPOSAL_ROUTE and len(segments) == 2:
                self._read(lambda: asyncio.run(desk.proposals(segments[1], configured)))
            elif request.route(segments) == DRAFT_ROUTE and len(segments) == 2:
                asked = request.required(self._body(), "request")
                self._read(lambda: asyncio.run(desk.draft(asked, segments[1], configured)))
            else:
                self.refuse(404, _ROUTES)

    # --- the run: one action, one response, one line of JSON per verdict ----------

    def _run(self, table: str) -> None:
        try:
            scan, specs, identifiers = plan(table)
        except REFUSALS as exc:
            self.refuse_raised(exc)
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

    # --- the read surface, and the one judgment that writes ----------------------

    def _read(self, produce: Any) -> None:
        """Run a reader and answer with what it returned, or with why it could not.

        A thing that is not there is a 404, and everything else is
        `refuse_raised`'s call between 422 and 503 — which is the distinction a permalink
        actually needs: a pasted link to a rule, a run record or a table that does not
        exist is a different problem from a database that is not answering, and the
        screen renders them differently. All three misses are the same
        answer, so they are caught as one tuple rather than as three clauses that could
        drift — `UnknownTable` joined with F12's desk (dq-rbf.4), which reads the live
        schema before it composes anything from a name that arrived in a URL (SPEC §3.1).
        A typo in an address is not an empty table, and the two must not look alike.
        `Cache-Control: no-store` because a rule's state changes the moment somebody
        presses one of the buttons on the page reading it.
        """
        try:
            payload = produce()
        except (store.UnknownRule, runs.UnknownRun, live.UnknownTable) as exc:
            self.refuse(404, str(exc))
        except REFUSALS as exc:
            self.refuse_raised(exc)
        else:
            self.answer(200, json.dumps(payload).encode(), JSON)

    def _batch(self) -> None:
        """F12 · one act of judgment over a selection (SPEC F12, bead dq-rbf.4).

        The body carries unsaved proposals (`specs`), stored rules (`rule_ids`), or both,
        and `store.judge_batch()` does everything: the cap, the empty selection, the
        reason requirement, the validator on every spec, and the two revisions each fresh
        rule gets. Nothing is decided here — a cap re-checked in this handler would be a
        second opinion, and the one that matters is the one nearest the table.
        """
        self._read(
            lambda: {
                "rules": [
                    {"rule_id": rev.rule_id, "revision": rev.revision, "status": rev.status}
                    for rev in request.batched(self._body())
                ]
            }
        )

    def _judge(self, rule_id: str) -> None:
        """Accept / reject / ask business, as one appended revision (F6, F12).

        The status and the reason are handed straight to `store.set_status()`, which
        validates both: an unknown state and a rejection with no reason are refused by
        the store's own `Revision`, so there is nothing to check here that would not be
        a second, weaker copy of that check.
        """
        try:
            body = self._body()
            reason = (body.get("reason") or "").strip() or None
            store.set_status(rule_id, str(body.get("status")), reason)
        except store.UnknownRule as exc:
            self.refuse(404, str(exc))
            return
        except REFUSALS as exc:
            self.refuse_raised(exc)
            return
        self._read(lambda: view.of(rule_id))

    def _body(self) -> dict[str, Any]:
        """The bytes off the socket, parsed. The only part of a body this class touches.

        Reading is HTTP and belongs here; deciding what the object means is
        `app/api/request.py`, which every POST route below asks. Content-Length is the
        frame — `protocol_version` is HTTP/1.0, so there is no chunked request body to
        reassemble.
        """
        return request.body(self.rfile.read(int(self.headers.get("Content-Length") or 0)))


def serve(port: int | None = None) -> None:
    """Warm the datasource, then serve. Both halves at boot, in that order, once.

    The warm-up is not an optimisation: it is what keeps the 1.16 s connect out of the
    number a user watches, and it is where INV-3's one-context-per-process becomes a
    fact about the running program rather than about the source.
    """
    from app.dq import ge_runtime

    ge_runtime.connect()
    address = ("", port if port is not None else int(os.environ.get(PORT_VAR, DEFAULT_PORT)))
    with DualStackServer(address, Handler) as httpd:
        httpd.serve_forever()


# The route table, as the sentence a 404 answers with. Written once, next to the four
# handlers above, because a server whose refusal does not say what it serves makes the
# caller read this file to find out.
_ROUTES = (
    f"this server has GET {RULE_ROUTE}?table=<table>[&{CONFIGURATION}=1], "
    f"GET {RULE_ROUTE}/<ruleId>[?{CONFIGURATION}=1], "
    f"GET {REVIEW_ROUTE}[?table=<table>], GET {TABLE_ROUTE}, "
    f"GET {RECORD_ROUTE}?table=<table>, GET {RECORD_ROUTE}/<recordId>, "
    f"POST {RULE_ROUTE}, POST {RULE_ROUTE}/<ruleId>, POST {RULE_ROUTE}/<ruleId>/revision, "
    f"POST {PROPOSAL_ROUTE}/<table>, POST {DRAFT_ROUTE}/<table> "
    f"and POST {RUN_ROUTE}/<table>."
)


if __name__ == "__main__":
    serve()
