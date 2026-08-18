"""Every byte this server writes back, and the promise that it always writes some.

Split out of `server.py`, which is at its 400-line ceiling — but the seam is a real one
and it is bead dq-abs's. A request whose SHAPE we did not anticipate used to leave
`do_GET`/`do_POST` as an exception, and `ThreadingHTTPServer` answers that by dropping
the connection with no response on it at all. Two things follow, and the second is the
one that matters:

  * the caller gets no status code from us, so the proxy in front invents one — a 502,
    which says "the thing behind me is broken" about a request that was simply wrong;
  * the proxy's refusal is then written by the PROXY, about the proxy, and names the
    private address it failed to reach. `api.railway.internal:8000` is topology the
    reader has no use for and an attacker does (SPEC §3.1).

So the last catch lives here, once, wrapped around whatever the route chain did — not
per route, because the input nobody anticipated is by definition the one no route was
written for. A route may still refuse deliberately and precisely; what it may not do is
end the request by saying nothing.

WHAT A REFUSAL IS ALLOWED TO SAY. The sentence in a 4xx was written by the module that
refused, for the person reading it (INV-4), and travels verbatim. The sentence in a 500
is written HERE and is deliberately incurious: an unhandled exception's text carries
driver names, file paths, SQL and hostnames, and the person who typed a bad URL is not
its audience. The exception goes to the process log instead, which is where the operator
who can act on it reads it.

AND "VERBATIM" IS ONLY SAFE BECAUSE OF WHAT THE MODULES NOW WRITE. Six call sites used
to raise `Unavailable(f"{DSN_VAR} did not answer: {exc}")`, and that `exc` is psycopg2's,
carrying the pooler hostname, its resolved addresses and its port. It was a `RuntimeError`
and so it left here as a **422 the reader was shown** — the private topology of the
deployment, in a body, over the path every screen reads through. `app/db/unreachable.py`
is the fix: one neutral sentence for the reader, the driver's own words to the log, and a
class this file can give a status code of its own.

ponytail: one generic sentence for every unanticipated failure, with no error id to
quote. Ceiling: an operator correlates by timestamp and path. A request id threaded
through the log and the body is the upgrade, and it is a feature rather than a fix.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler

from app.db.unreachable import Unreachable

# What the store, the profiler and the schema reader raise when the thing asked for is
# not there. Caught as one set because the honest response to all of them is the same: a
# status code carrying the sentence they wrote, never a 200 with an empty screen behind
# it. `ValueError` is also every malformed body and every missing parameter, which is
# why an unexpected content type is a 422 here rather than a dropped connection.
#
# `Unreachable` IS UNDER `RuntimeError` AND IS NOT ONE OF THESE. A 4xx says the caller
# asked for something wrong, and a database that is not answering is not something the
# caller did — it is a 503 (`guard()` below), which is also the difference between a
# reader who should retry and a reader who should stop. It is caught FIRST there for the
# same reason it is mentioned here: nothing else in this tuple would leave it a 422 by
# accident twice.
REFUSALS = (LookupError, RuntimeError, ValueError)

# Not `application/json`: the run's body is a SEQUENCE of JSON documents, and a client
# that waited to parse it as one object would wait for the whole run. A refusal keeps
# the same framing — one object, then a newline — because the run's client reads this
# response with the same line reader it reads verdicts with, and the read surface's
# client parses one document either way.
NDJSON = "application/x-ndjson"

# The only sentence on this side that is not written by the module that knows what went
# wrong, because nothing knew. It says the three things a reader can act on: it is ours
# and not theirs, somebody who can fix it has been told, and nothing was written.
UNANTICIPATED = (
    "This request could not be handled, and the fault is on this side rather than in "
    "what you asked for. It has been recorded for whoever runs this service, and "
    "nothing was changed."
)


class Refusing(BaseHTTPRequestHandler):
    """The response half of the handler: what gets written, and that something does."""

    #: The `Server:` header, on every response including the stock ones this class never
    #: sees. `BaseHTTP/0.6 Python/3.12.5` is the runtime and its patch version, sent to
    #: anybody who connects — the same disclosure class as the private hostname above,
    #: and the one door `guard()` cannot cover, because an unsupported verb is answered
    #: by the base class before any handler of ours runs. Blanked rather than branded:
    #: the name of this service is no more use to a prober than the version was.
    server_version = "dq"
    sys_version = ""

    #: Has a status line gone out yet? A run streams, so by the time it can fail there
    #: may already be a 200 and half its verdicts on the wire — and appending a refusal
    #: to that would be a second response inside the first. Tracked on `send_response`
    #: rather than in each writer, so a route added later inherits it by writing bytes.
    answered = False

    def send_response(self, code: int, message: str | None = None) -> None:
        self.answered = True
        super().send_response(code, message)

    @contextlib.contextmanager
    def guard(self) -> Iterator[None]:
        """Wrap a verb's whole route chain, so nothing leaves it as a dead socket."""
        try:
            yield
        except REFUSALS as exc:
            self.refuse_raised(exc)
        except Exception as exc:  # noqa: BLE001 — the point is that it is every one
            self.log_error(
                "unhandled %s on %s %s: %s", type(exc).__name__, self.command, self.path, exc
            )
            self.refuse(500, UNANTICIPATED)

    def refuse_raised(self, exc: BaseException) -> None:
        """Answer with a refusal a module raised on purpose, under the right code.

        The one place the 4xx/5xx line is drawn, because the routes below catch the same
        tuple in three places and a rule split across four `except` clauses is a rule
        that will disagree with itself. A malformed body, an unknown state, a rule the
        catalog cannot express: the caller's, and a 422. A database that is not
        answering: ours, and a 503 — a reader told "you sent something wrong" about an
        outage retries the one thing that cannot help.
        """
        self.refuse(503 if isinstance(exc, Unreachable) else 422, str(exc))

    def refuse(self, code: int, message: str) -> None:
        """One refusal shape for both surfaces, or silence if we already answered."""
        if self.answered:
            return
        self.answer(code, json.dumps({"event": "refused", "message": message}).encode() + b"\n")

    def answer(self, code: int, body: bytes, content_type: str = NDJSON) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
