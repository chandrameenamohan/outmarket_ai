"""B3 · the model can be called, and cannot touch this machine.

`app/model.py` claims a sandbox: no tools, one turn, no inherited settings, and
a credential handed in rather than inherited. A claim in a docstring is worth
nothing, so every clause of it is asserted here — and asserted against the
options object the module actually builds, not against a copy of its intent.

Two things this file does deliberately.

**The tool roster below is written out rather than imported.** A test that
compares a constant with itself is green forever. Deleting `"Bash"` from
`app/model.py` has to turn this red, so the names it must contain are spelled
out here, independently.

**Exactly one check spends money.** `test_live_call_...` is marked `live` and is
deselected from `make check`. It is the only proof that the sandbox holds
against the real CLI rather than against our reading of it, and it costs a real
call, so it is run on purpose:

    set -a; . ./.env; set +a
    python3 -m pytest -m live

No timing and no cost is asserted anywhere here. LT-1b owns every number on this
project (VERIFICATION.md §8); LT-2b's ~7 s and ~$0.04 are provenance, not a
budget, and a budget is what a number in an assertion becomes.
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from app import model
from conftest import REPO, source_files

# Independent of app/model.py on purpose — see the module docstring. Every one of
# these reaches the filesystem, the shell, the network or a second agent.
TOOLS_THAT_REACH_THIS_MACHINE = [
    "Bash",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "Task",
    "NotebookEdit",
]

# The single door, and the import that must only ever come through it.
CLIENT_MODULE = pathlib.Path("app/model.py")
SDK = "claude_agent_sdk"

FAKE_TOKEN = "not-a-real-credential-and-never-sent-anywhere"

PARSED = {"rules": [{"column": "order_total", "type": "expect_column_values_to_be_between"}]}
RAW = '{"rules": [{"column": "order_total", "type": "expect_column_values_to_be_between"}]}'


@pytest.fixture
def token(monkeypatch: pytest.MonkeyPatch) -> str:
    """A token in the environment. Nothing here ever sends it: no test below calls out."""
    monkeypatch.setenv(model.TOKEN_VAR, FAKE_TOKEN)
    return FAKE_TOKEN


# --- the sandbox, asserted on the object the module builds -------------------


def test_every_builtin_tool_is_disallowed_explicitly(token: str) -> None:
    options = model.sandboxed_options("propose rules")
    assert options.allowed_tools == [], (
        f"allowed_tools must be empty; got {options.allowed_tools}. That list IS the "
        "permission grant — anything in it is a tool the model may run on this machine."
    )
    missing = [t for t in TOOLS_THAT_REACH_THIS_MACHINE if t not in options.disallowed_tools]
    assert not missing, (
        f"built-in tools not named in disallowed_tools: {missing}. The empty allowlist is "
        "already the grant; naming them is what makes the blast radius readable."
    )


def test_setting_sources_is_empty(token: str) -> None:
    """The one that is easy to leave unset and impossible to notice.

    Unset, the SDK inherits the developer's own user/project/local settings —
    their global CLAUDE.md included — into a server-side call made on behalf of
    somebody else. LT-2b names this as not optional for a service.
    """
    assert model.sandboxed_options("propose rules").setting_sources == [], (
        "setting_sources must be [] — an unset value inherits the developer's own "
        "CLAUDE.md and settings into a server-side call."
    )


def test_max_turns_is_one(token: str) -> None:
    """Agent loops are an explicit non-goal (SPEC §4). This is a call, not a loop."""
    assert model.sandboxed_options("propose rules").max_turns == 1


def test_the_credential_is_handed_in_and_its_absence_is_a_named_error(
    token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auth travels in options.env, so the model process gets exactly one variable."""
    assert model.sandboxed_options("propose rules").env == {model.TOKEN_VAR: token}
    monkeypatch.delenv(model.TOKEN_VAR)
    with pytest.raises(model.MissingCredential) as raised:
        model.sandboxed_options("propose rules")
    assert model.TOKEN_VAR in str(raised.value)


@pytest.mark.parametrize(
    "widening",
    [
        {"allowed_tools": ["Bash"]},
        {"tools": ["Read", "Bash"]},
        {"disallowed_tools": []},
        {"max_turns": 5},
        {"setting_sources": ["user", "project"]},
        {"permission_mode": "bypassPermissions"},
        {"mcp_servers": {"fs": {"command": "npx", "args": ["-y", "server-filesystem"]}}},
        {"add_dirs": ["/"]},
    ],
    ids=lambda w: next(iter(w)),
)
def test_the_module_refuses_to_construct_a_client_with_tools_enabled(
    widening: dict[str, object],
) -> None:
    """Refusal beats a default, because a default is something a call site can override.

    The refusal is Python's: none of these is a parameter, so the call never
    enters the function and `TypeError` names the kwarg that was attempted. No
    `token` fixture here on purpose — the refusal lands before anything the
    builder does, so an unconfigured machine still gets this error rather than a
    credential error that hides it.
    """
    with pytest.raises(TypeError) as raised:
        model.sandboxed_options("propose rules", **widening)
    assert next(iter(widening)) in str(raised.value)


def test_exactly_one_module_constructs_the_client() -> None:
    """SPEC §5 defers organisation credentials on the strength of this being true.

    Same mechanism as INV-3's text scan and the same ceiling: it reads `app/`
    only, because a test may legitimately name the SDK in prose (this file does)
    while production code may not reach for it at all.
    """
    offenders = [
        p.relative_to(REPO)
        for p in source_files("app")
        if p.relative_to(REPO) != CLIENT_MODULE and SDK in p.read_text()
    ]
    assert not offenders, (
        f"{offenders} reference {SDK}. Only {CLIENT_MODULE} may — it is what makes swapping "
        "subscription auth for organisation credentials a one-file change (SPEC §5)."
    )


# --- the parser: tolerant on the way in, loud on the way out -----------------


@pytest.mark.parametrize(
    "reply",
    [
        RAW,
        f"```json\n{RAW}\n```",
        f"```\n{RAW}\n```",
        f"Here is what I found:\n```json\n{RAW}\n```\nHappy to expand on any of these.",
        f"{RAW}\n\nI kept it to a single rule because the sample is small.",
        f"Sure — {RAW}",
    ],
    ids=["bare", "json-fence", "bare-fence", "prose-both-sides", "trailing-prose", "preamble"],
)
def test_parser_strips_fences_and_balance_extracts_json(reply: str) -> None:
    assert model.extract_json(reply) == PARSED


def test_the_parser_is_not_fooled_by_a_brace_inside_a_string() -> None:
    """The realistic case a hand-rolled depth counter truncates on.

    This product's model writes English statements about set membership, so
    "one of {shipped, pending}" is a value it will plausibly emit.
    """
    reply = '{"statement": "status is one of {shipped, pending}", "column": "status"}'
    assert model.extract_json(reply) == {
        "statement": "status is one of {shipped, pending}",
        "column": "status",
    }


@pytest.mark.parametrize(
    "reply",
    [
        "",
        "I cannot propose rules from this sample.",
        "```json\nnot json at all\n```",
        '{"rules": [',
        "[1, 2, 3]",
    ],
    ids=["empty", "prose", "fenced-garbage", "truncated", "not-an-object"],
)
def test_non_json_reply_raises_named_error(reply: str) -> None:
    """The failure a silent `{}` would hide reads to a user as 'no findings'."""
    with pytest.raises(model.NotJson) as raised:
        model.extract_json(reply)
    assert "not with a JSON object" in str(raised.value)


# --- the one check that spends money -----------------------------------------

LIVE_SYSTEM = "Reply with a single JSON object and nothing else. No prose, no code fences."

# The prompt ASKS for a file read, so a green result means the sandbox refused a
# real attempt rather than that nothing ever wanted a tool.
LIVE_PROMPT = """Read the file ./SPEC.md from disk and count its lines.

Then reply with exactly this JSON object:
{"read_the_file": true or false, "tool_used": "<the name of any tool you invoked, or none>"}
"""


@pytest.mark.live
def test_live_call_returns_json_with_zero_tool_use_blocks_and_num_turns_1() -> None:
    """One real call against the real CLI. Deselected from `make check` — see the docstring."""
    reply = asyncio.run(model.ask_json(LIVE_PROMPT, LIVE_SYSTEM))
    assert reply.tools_used == [], f"a tool ran inside the sandbox: {reply.tools_used}"
    assert reply.num_turns == 1, f"expected one turn, got {reply.num_turns}"
    assert (
        reply.data.get("read_the_file") is False
    ), f"the model reports it read a file from this machine: {reply.data}"
