"""The one module that constructs a Claude Agent SDK client.

SPEC §3 puts model access behind a single door and §5 says why: subscription
authentication is right for this deliverable and wrong for a product, so moving
to organisation credentials has to be a change to one reviewed file rather than
a search across the codebase. `tests/test_model_sandbox.py` enforces the "one
module" half; this file is the other half — the sandbox itself.

The sandbox is four settings, each of them proven against the real library by
LT-2b (`learning-tests/FINDINGS.md` § LT-2b, claude-agent-sdk 0.1.23):

    allowed_tools=[] + explicit disallowed_tools   no shell, no filesystem, no
                                                   network of the model's own
    max_turns=1                                    a call, not an agent loop
    setting_sources=[]                             the developer's own global
                                                   CLAUDE.md and settings do not
                                                   leak into a server-side call
    env={CLAUDE_CODE_OAUTH_TOKEN: ...}             auth is handed in explicitly,
                                                   not inherited from whatever
                                                   the server process happens to
                                                   have in its environment

Not one of the four is a default: every one of them is *off* unless it is set,
which is exactly why they are set once, here, instead of at each call site.

The reply is parsed tolerantly. LT-2b got clean JSON from instruction alone, but
once. The failure mode of a strict parse is the worst one available to this
product — an empty proposal list reads as "the model had no ideas" — so a reply
this module cannot parse raises `NotJson` and never returns an empty result.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

MODEL = "claude-opus-5"

TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"

# Claude Code 2.1.233's built-in tools. `allowed_tools=[]` is already the whole
# permission grant, so this list is belt to that braces — it names the tools out
# loud so that "what could the model have touched?" is answerable by reading one
# constant instead of by knowing how the CLI resolves an empty allowlist.
#
# ponytail: the roster is hand-maintained because the SDK exports no enumeration
# of built-in tool names (checked in 0.1.23). It is deliberately over-inclusive —
# an unknown name in --disallowedTools is inert, a missing one would not be.
# Upgrade path: if the SDK ever exports the roster, import it and delete this.
BUILTIN_TOOLS = [
    "Bash",
    "BashOutput",
    "KillShell",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "Task",
    "TodoWrite",
    "ExitPlanMode",
    "SlashCommand",
    "ListMcpResources",
    "ReadMcpResource",
]


class ModelError(Exception):
    """Base for everything this module refuses to do, so one `except` catches all of it."""


class MissingCredential(ModelError):
    """No subscription token to authenticate with."""


class NotJson(ModelError):
    """The model replied, but not with a JSON object. Never a silent empty result."""


@dataclass
class Reply:
    """One model answer, carrying the two facts that prove the sandbox held.

    `tools_used` and `num_turns` are part of the returned value rather than
    debug output because they are the evidence the gate asserts on: a sandbox
    nobody can observe is a sandbox nobody can check.
    """

    data: dict[str, Any]
    tools_used: list[str] = field(default_factory=list)
    num_turns: int = 0


def sandboxed_options(system_prompt: str) -> ClaudeAgentOptions:
    """Build the only options this application ever calls the model with.

    The system prompt is the whole of this function's surface. Every knob that
    could widen the blast radius — `allowed_tools`, `mcp_servers`, `max_turns`,
    `setting_sources`, `permission_mode` — is set here and is not a parameter,
    so a call site asking for one gets Python's own `TypeError` naming the kwarg
    it tried to pass. The model name is not a parameter either; SPEC §3 pins it.
    """
    token = os.environ.get(TOKEN_VAR)
    if not token:
        raise MissingCredential(
            f"{TOKEN_VAR} is not set. It is the only credential this module accepts; see "
            ".env.example. Load it into the environment (`set -a; . ./.env; set +a`)."
        )
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=system_prompt,
        allowed_tools=[],
        disallowed_tools=list(BUILTIN_TOOLS),
        max_turns=1,
        setting_sources=[],
        env={TOKEN_VAR: token},
    )


def extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a reply that may be fenced or wrapped in prose.

    Three tolerances, in order: a ```json fence, a preamble before the object,
    and trailing commentary after it. The last one is free — `raw_decode` stops
    at the end of the first complete value — and it is also why this does not
    count braces by hand: a brace inside a string ("status is one of {a, b}") is
    a plausible thing for this product's model to write, and a hand-rolled depth
    counter truncates on it.
    """
    body = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", body, re.S)
    if fenced:
        body = fenced.group(1).strip()
    start = body.find("{")
    if start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(body[start:])
        except json.JSONDecodeError:
            pass
        else:
            return dict(obj)
    raise NotJson(
        f"the model replied, but not with a JSON object: {text[:200]!r}. "
        "Surfaced as an error on purpose — an empty result here reads as 'no findings'."
    )


async def ask_json(prompt: str, system_prompt: str) -> Reply:
    """One sandboxed call. One turn in, one JSON object out."""
    text: list[str] = []
    tools: list[str] = []
    turns = 0
    async for message in query(prompt=prompt, options=sandboxed_options(system_prompt)):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tools.append(block.name)
        elif isinstance(message, ResultMessage):
            turns = message.num_turns
    return Reply(data=extract_json("".join(text)), tools_used=tools, num_turns=turns)


# ponytail: a tool invocation is reported, not raised on. The gate asserts
# `tools_used == []` against a prompt that actively asks for a file read, which
# is a stronger check than a runtime guard that can only fire if `allowed_tools=[]`
# has stopped meaning what LT-2b measured. Upgrade path: raise here the day a
# caller has to fail closed rather than report.
