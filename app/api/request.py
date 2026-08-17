"""One request's path and body, turned into the arguments a module below takes.

`app/api/server.py` says out loud what it may not become — a second place where rules
are chosen, results are read or verdicts are worded — and the way that stays true is
that its handlers are one line each. This is where the line's arguments come from.

Everything here is a PURE FUNCTION OF A DICT, with one deliberate exception
(`batched`, which hands a parsed body to the store's own door and refuses nothing
itself). That purity is the point: a route's argument handling is checkable without a
socket, and `tests/test_run_endpoint.py` drives the real handler for the parts that are
about HTTP rather than about arguments.

WHAT IS DELIBERATELY NOT HERE: any decision. A missing parameter raises with a sentence
naming it, and every other refusal — the bulk cap, the four states, the reason a
rejection needs, the validator — belongs to the module that owns the thing being
refused. A check re-made here would be the second opinion that drifts.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.rules import store


def parse(path: str) -> tuple[tuple[str, ...], dict[str, list[str]]]:
    """`/rules/abc?table=orders` -> `('rules', 'abc')`, `{'table': ['orders']}`.

    Empty segments are dropped, so `/rules/` and `/rules` are the same route — a
    trailing slash is a typo, never a different resource. `unquote` runs here and
    nowhere else, which is what stops a percent-encoded id being matched raw in one
    place and decoded in another.
    """
    parsed = urlparse(path)
    segments = tuple(unquote(p) for p in parsed.path.split("/") if p)
    return segments, parse_qs(parsed.query)


def route(segments: tuple[str, ...]) -> str:
    """The first segment back as a path, so the server's constants stay the strings a
    client would type: `('rules', 'abc')` -> `/rules`, `()` -> `/`."""
    return "/" + (segments[0] if segments else "")


def one(query: dict[str, list[str]], name: str) -> str:
    """The single value of a required query parameter, or a refusal naming it."""
    values = query.get(name) or []
    if len(values) != 1 or not values[0].strip():
        raise ValueError(f"?{name}= is required here and takes exactly one value; got {values}")
    return values[0]


def optional(query: dict[str, list[str]], name: str) -> str | None:
    """The same, for a parameter whose ABSENCE is a legitimate request.

    `/review` with no `?table=` is the domain expert's front door and the commonest
    request this server serves, so a missing value is not a refusal — it is the whole
    queue. An empty or repeated value still is: `?table=` with nothing after it is a
    caller that meant to say something, and answering the unscoped queue would silently
    ignore them.
    """
    return None if name not in query else one(query, name)


def flag(query: dict[str, list[str]], name: str) -> bool:
    """Is this switch on? Present with any value at all means yes, absent means no.

    Deliberately not `== "1"`. The only caller is `?configuration=`, whose answer changes
    what a payload CONTAINS rather than how much of it there is (SPEC F12, Rev 0.4), and
    a spelling that silently meant "no" — `?configuration=true`, `?configuration=yes` —
    would show a domain expert's screen to an engineer with no error anywhere. Present is
    yes, and the conservative answer is the one you get by not asking.
    """
    return name in query


def body(raw: bytes) -> dict[str, Any]:
    """The request body as an object, or a `ValueError` the refusal path already catches.

    `ValueError` rather than `json.JSONDecodeError` handled at each call site: a
    malformed body is exactly what the server's `REFUSALS` set exists for — a 422 with
    the parser's own complaint in it — and one handler per POST route was four copies of
    the same lines waiting to disagree.
    """
    try:
        parsed = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"the request body is not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"the request body is a {type(parsed).__name__}, not an object")
    return parsed


def required(parsed: dict[str, Any], name: str) -> str:
    """One non-empty string out of a body, or a refusal naming the field."""
    value = parsed.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{name}` is required in this body and must be a non-empty string")
    return value


def batched(parsed: dict[str, Any]) -> tuple[store.Revision, ...]:
    """F12's bulk judgment: a read body, handed to the store's own door.

    EVERY REFUSAL BELOW THIS LINE BELONGS TO THE STORE — the cap, the empty selection,
    the reason a rejection needs, the validator on each spec. What happens here is only
    shape: a `specs` that is not a list is a caller error and says so, rather than
    reaching `judge_batch` as an empty selection and being refused for the wrong reason.
    """
    specs = parsed.get("specs") or []
    rule_ids = parsed.get("rule_ids") or []
    if not isinstance(specs, list) or not isinstance(rule_ids, list):
        raise ValueError(
            "a batch judgment carries `specs` (unsaved proposals) and `rule_ids` (stored "
            f"rules), each a list; got {type(specs).__name__} and {type(rule_ids).__name__}"
        )
    return store.judge_batch(
        required(parsed, "table"),
        specs,
        [str(rule_id) for rule_id in rule_ids],
        str(parsed.get("status")),
        (parsed.get("reason") or "").strip() or None,
    )


def revision(parsed: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """The two shapes a new revision arrives in, kept apart: a configuration, or a sentence.

    Both are optional here, and `app/rules/desk.py::revise` refuses a body carrying
    neither — the refusal belongs there because that is the function that knows there is
    no third way to change what a rule checks.
    """
    spec = parsed.get("type") and {"type": parsed["type"], "kwargs": parsed.get("kwargs") or {}}
    statement = parsed.get("statement")
    return (spec or None), (str(statement) if isinstance(statement, str) else None)
