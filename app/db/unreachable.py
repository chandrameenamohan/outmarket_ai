"""What every module says when a database does not answer — and what it does not say.

BEAD dq-abs, SECOND HALF. The first half stopped a request ending as a dropped
connection. This is the leak that survived it: six call sites raised

    Unavailable(f"{DSN_VAR} did not answer: {exc}")

and `exc` is the DRIVER'S text. psycopg2 writes the pooler hostname, every IP address
it resolved to, the port and "Is the server running on that host" into that string.
`Unavailable` is a `RuntimeError`, so `app/api/refuse.py::REFUSALS` caught it and put
the whole thing in a 422 body — and `web/app/api.ts::call()` renders `payload.message`
verbatim. A stranger who loaded any screen while the database was down was handed the
topology (SPEC §3.1), by the same shape of bug the bead was filed for.

So the driver's words go to the log, where the operator who can act on them reads them,
and the reader gets ONE sentence written here. It is the register of
`app/api/refuse.py::UNANTICIPATED` and for the same reason: nothing about the inside is
usable by the person who asked, and all of it is usable by somebody probing.

IT ALSO CARRIES THE STATUS CODE, by being one class. An unreachable database is not the
caller's mistake, so `guard()` answers 503 for anything under `Unreachable` and 422 for
the rest of `REFUSALS`. Three modules keep their own `Unavailable` — the system store,
the analysis schema and the framework runtime fail for different reasons and their
callers still catch them apart — and all three inherit from here, so the one thing that
had to be shared is, and nothing else is.

ponytail: `logging` with no configuration, so this lands on stderr beside the server's
own `log_error` lines. Ceiling: no request id ties a log line to the refusal a reader
saw, which is the same ceiling `refuse.py` names and the same upgrade closes both.
"""

from __future__ import annotations

import logging

# The whole of what a reader is told. No variable name, no host, no port, no driver:
# `SUPABASE_DB_URL_ANALYSIS` alone tells a prober which managed database this is.
NOT_ANSWERING = (
    "The database behind this did not answer, so nothing could be read and nothing was "
    "written. The fault is on this side rather than in what you asked for; it has been "
    "recorded for whoever runs this service. Try again in a moment."
)


class Unreachable(RuntimeError):
    """A database this process needs did not answer. The operator's problem, not a reader's."""

    @classmethod
    def not_answering(cls, dsn_var: str, exc: BaseException) -> Unreachable:
        """The driver's own words to the log; the neutral sentence to whoever asked.

        A constructor rather than a free function so the raising module keeps its own
        subclass — `raise live.Unavailable.not_answering(DSN_VAR, exc) from exc` reads
        as one line and there is no f-string in it for anybody to grow.
        """
        logging.getLogger(__name__).error("%s did not answer: %s", dsn_var, exc)
        return cls(NOT_ANSWERING)
