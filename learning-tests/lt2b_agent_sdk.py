"""
LT-2b — Claude Agent SDK: auth, tool suppression, and structured output.

WHY THIS EXISTS
    SPEC F3/F4 assume the Agent SDK can be used as a plain "prompt in, structured
    rule out" call: authenticated by a long-lived token, with every built-in tool
    disabled, in a single turn. None of that was verified — only assumed. This
    script checks it against the real library.

FINDINGS — run 2026-08-16, claude-agent-sdk 0.1.23, model claude-opus-5
    [x] Auth works from CLAUDE_CODE_OAUTH_TOKEN passed via options.env.
        No `ant` CLI, no ANTHROPIC_API_KEY, no separate API purchase.
    [x] Tools fully suppressed: allowed_tools=[] + explicit disallowed_tools.
        Zero tool invocations observed. The security posture in §7.6 holds.
    [x] Single turn enforced by max_turns=1 (ResultMessage.num_turns == 1).
    [x] Structured JSON obtained by instruction alone — the `output_format`
        option was NOT needed. Response was clean JSON, no code fence.
        Keep the tolerant parser anyway; one clean run is not a guarantee.
    [x] setting_sources=[] stops the developer's own CLAUDE.md/settings from
        leaking into a server-side call. Not optional for a service.

    MEASURED
        latency  6.6 s wall / 4.7 s reported for one generation call
        cost     $0.041 per call at opus-5

    UNEXPECTED — this is the important one
        Every rule returned was statistically true and business-naive:
          - status IN {the 4 values observed}      <- R-2 exactly
          - order_total BETWEEN 0 AND 89,400       <- overfits the observed max
          - order_total IS NOT NULL                <- trivially true
        It did NOT propose "order_total >= 0", the actual business invariant.
        The model can only infer from the sample; the *meaning* is not in the
        sample. This is empirical confirmation of R-2 and, more importantly,
        of why the domain expert is a first-class user rather than a reviewer
        of last resort. Evidence lines and unsaved-proposal status are
        load-bearing, not decorative.

RUN
    uv run --with claude-agent-sdk python learning-tests/lt2b_agent_sdk.py
"""

import anyio
import json
import os
import pathlib
import re
import time

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

# --- env -------------------------------------------------------------------

for line in pathlib.Path(".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"), "CLAUDE_CODE_OAUTH_TOKEN not in .env"

# --- the prompt the real Rule Generator would send -------------------------
# A realistic stat block from `orders`, exactly the shape F2 produces.

STAT_BLOCK = """\
Table: orders

order_total   2,400,000 rows | 0 nulls | min 0.00 | max 89,400.00 | 45,102 distinct
status        2,400,000 rows | 0 nulls | 4 distinct: shipped, pending, cancelled, returned
email         2,400,000 rows | 1,204 nulls | 2,398,796 distinct
"""

CATALOG = [
    "expect_column_values_to_not_be_null",
    "expect_column_values_to_be_unique",
    "expect_column_values_to_be_between",
    "expect_column_values_to_be_in_set",
    "expect_column_values_to_match_regex",
]

SYSTEM = (
    "You propose data quality rules. You may only use expectation types from the "
    "provided catalog. Reply with JSON only, no prose, no code fences."
)

PROMPT = f"""{STAT_BLOCK}

Allowed expectation types: {", ".join(CATALOG)}

Propose up to 3 rules. Reply with a JSON object of this exact shape:
{{"rules": [{{"column": str, "type": str, "params": object, "statement": str, "evidence": str}}]}}
"""


def extract_json(text: str):
    """Tolerant parse — we are learning what actually comes back, not enforcing."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        depth += (ch == "{") - (ch == "}")
        if depth == 0:
            try:
                return json.loads(text[start : i + 1])
            except json.JSONDecodeError:
                return None
    return None


async def main() -> None:
    options = ClaudeAgentOptions(
        model="claude-opus-5",
        system_prompt=SYSTEM,
        # Every built-in tool off — this is the security posture in §7.6.
        allowed_tools=[],
        disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep",
                          "WebSearch", "WebFetch", "Task", "NotebookEdit"],
        # One turn. This is a call, not an agent loop.
        max_turns=1,
        # Do NOT inherit the developer's own CLAUDE.md / settings into a server call.
        setting_sources=[],
        env={"CLAUDE_CODE_OAUTH_TOKEN": os.environ["CLAUDE_CODE_OAUTH_TOKEN"]},
    )

    text_parts: list[str] = []
    tool_uses: list[str] = []
    result: ResultMessage | None = None

    t0 = time.perf_counter()
    async for msg in query(prompt=PROMPT, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_uses.append(block.name)
        elif isinstance(msg, ResultMessage):
            result = msg
    elapsed = time.perf_counter() - t0

    text = "".join(text_parts)

    print("=" * 68)
    print(f"elapsed        : {elapsed:.1f} s")
    if result is not None:
        for attr in ("num_turns", "total_cost_usd", "is_error", "duration_ms"):
            if hasattr(result, attr):
                print(f"{attr:15}: {getattr(result, attr)}")
    print(f"tools invoked  : {tool_uses or 'none'}")
    print("=" * 68)
    print(text)
    print("=" * 68)

    parsed = extract_json(text)
    print("parsed as JSON :", "yes" if parsed else "NO")
    if parsed:
        rules = parsed.get("rules", [])
        print(f"rules returned : {len(rules)}")
        for r in rules:
            in_catalog = r.get("type") in CATALOG
            print(f"  [{'ok ' if in_catalog else 'OUT'}] {r.get('type')} "
                  f"on {r.get('column')} -> {r.get('statement')}")

    # --- assertions: what we believe is true -------------------------------
    assert text.strip(), "no text returned — auth or transport failure"
    assert not tool_uses, f"a tool ran despite being disabled: {tool_uses}"
    assert parsed is not None, "response was not parseable as JSON"
    assert parsed.get("rules"), "no rules in response"
    outside = [r["type"] for r in parsed["rules"] if r.get("type") not in CATALOG]
    assert not outside, f"proposed types outside the catalog: {outside}"
    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    anyio.run(main)
