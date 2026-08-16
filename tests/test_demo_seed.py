"""F15 · the demo dataset can be re-established and verified without a human.

The generator itself is already delivered (`seed/seed_demo_data.py`, `seed/MANIFEST.md`).
This file is the residual the bead asks for: the gate RUNS the seeder's own read-only
modes and asserts the result, so "the demo's outcome is verifiable rather than
anecdotal" is a check rather than a sentence. If the seed drifts from its manifest —
in the constants, in the committed markdown, or in the database — one of these fails.

Three facts, each checked where it is cheapest:

  offline  the committed manifest still states the counts the seeder plants
           (parsed out of the source with `ast`, because importing the seeder opens
           a database connection at import time and reads `.env` from the cwd)
  offline  the manifest's time-sensitive flag and this file's exclusion set agree
  live     the three per-table md5 fingerprints and all 13 planted defect counts

A checkout with no repo-root `.env` is named rather than left as a bare
FileNotFoundError — that is `_missing_env` below, and its message is read by
whoever hits a real failure, which is the only reader a message has.

The live pair is marked `ge` — the marker whose job is keeping `make check` offline —
and runs under `make check-ge`. It needs a database and psycopg, not the framework.

**The manifest is the authority.** A mismatch is a finding about the seed or the
database, never a reason to move a number here to make the check pass.

D5 is the one exception, and it is deliberate: it plants `ordered_at` 30–400 days past
the 2026-08-16 anchor and is counted with `ordered_at > now()`, so its observed count
DECAYS as the calendar moves. Asserting D5 == 60 against a database nobody re-seeded
would turn a stale demo into a red gate for a reason that has nothing to do with the
code. It is asserted in the only direction time can move it, and the failure message
says "re-seed" rather than "the engine has a gap".
"""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

import pytest

from conftest import REPO

SEEDER = REPO / "seed" / "seed_demo_data.py"
MANIFEST = REPO / "seed" / "MANIFEST.md"

# Defects whose count is a function of the clock, not of the seed. Cross-checked below
# against the manifest's own "Time-sensitive" section, so this set cannot fall behind it.
TIME_SENSITIVE = {"D5"}

# `| **D1** | `orders` | 150 | ... |` — the manifest's planted-defect table.
MANIFEST_ROW = re.compile(r"^\|\s*\*\*(D\d+)\*\*\s*\|\s*`(\w+)`\s*\|\s*([\d,]+)\s*\|", re.M)

# `    D1   orders          150       150  ok  negative order_total ...` — verify output.
VERIFY_ROW = re.compile(r"^\s+(D\d+)\s+(\w+)\s+([\d,]+)\s+([\d,]+)\s+(ok|FAIL)\b", re.M)

# `customers  256cf549478c02a7192474eac6e70b99` — printed by `--fingerprint`, and
# quoted in the manifest's idempotency block in exactly the same shape.
FINGERPRINT = re.compile(r"^\s*(customers|orders|payments)\s+([0-9a-f]{32})\s*$", re.M)


def _n(text: str) -> int:
    return int(text.replace(",", ""))


def _missing_env(root: pathlib.Path) -> str:
    """'' when the seeder can run from `root`; otherwise the reason, by name.

    `seed_demo_data.py` reads `.env` by RELATIVE path at import time, so from a
    checkout without one it dies with a bare `FileNotFoundError: '.env'` — five frames
    of psycopg-free traceback that name neither the file's role nor the fix. `.env` is
    gitignored, which means every git worktree and every fresh CI checkout is exactly
    that case.
    """
    if (root / ".env").exists():
        return ""
    return (
        f"no .env in {root}, so seed/seed_demo_data.py cannot read SUPABASE_DB_URL_DIRECT. "
        "It reads `.env` by relative path at import time and would otherwise die with a bare "
        "FileNotFoundError('.env'). .env is gitignored, so a git worktree or a fresh CI "
        f"checkout never has one: copy the repo-root .env to {root}/.env"
    )


def _seed(*args: str) -> str:
    """Run the seeder in a read-only mode and return its stdout.

    cwd is pinned to the repo root for the same reason `_missing_env` exists: the
    seeder resolves `.env` against the cwd, so a check that inherited pytest's cwd
    would pass from the repo root and fail from anywhere else.
    """
    if reason := _missing_env(REPO):
        pytest.fail(reason)
    proc = subprocess.run(
        [sys.executable, str(SEEDER), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.stdout, f"`{SEEDER.name} {' '.join(args)}` printed nothing.\n{proc.stderr}"
    return proc.stdout


def _seed_constants() -> dict[str, tuple[str, int]]:
    """`{'D1': ('orders', 150), ...}` read out of the seeder's DEFECTS literal.

    Read with `ast`, never imported: `import seed_demo_data` executes a module-level
    `.env` read and a psycopg connect, which would make an offline check need a
    database to confirm a fact about two text files.

    Undefensive about the seeder's shape on purpose. It is a landed deliverable that
    is not changing, and if it ever does, the AttributeError names the node type as
    usefully as a hand-written message would. The one isinstance left is what lets
    mypy see the keys and values at all.
    """
    tree = ast.parse(SEEDER.read_text(), filename=str(SEEDER))
    literal = next(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "DEFECTS"
    )
    assert isinstance(literal, ast.Dict), "seed DEFECTS is no longer a dict literal"
    planted = [{k.arg: k.value for k in call.keywords} for call in literal.values]  # type: ignore[attr-defined]
    return {
        ast.literal_eval(key): (  # type: ignore[arg-type]
            ast.literal_eval(fields["table"]),
            ast.literal_eval(fields["count"]),
        )
        for key, fields in zip(literal.keys, planted, strict=True)
    }


def _manifest_counts() -> dict[str, tuple[str, int]]:
    return {m[1]: (m[2], _n(m[3])) for m in MANIFEST_ROW.finditer(MANIFEST.read_text())}


def test_manifest_counts_match_seed_constants() -> None:
    """The committed ground truth still says what the generator actually plants.

    `--manifest` regenerates MANIFEST.md from these constants, so the two agree the
    moment it is run — and silently diverge from any later edit to either one. Everything
    downstream (SPEC's coverage numbers, the rule-engine correctness checks in
    test_rule_compilation.py) reads the markdown, not the code.
    """
    assert _manifest_counts() == _seed_constants(), (
        "seed/MANIFEST.md disagrees with the DEFECTS constants in seed/seed_demo_data.py. "
        "Regenerate it: python3 seed/seed_demo_data.py --manifest"
    )


def test_d5_is_flagged_time_sensitive() -> None:
    """The decaying defect is documented as decaying, and this file excludes exactly it.

    Two ways for the trap to reopen: the manifest stops warning about D5, or someone
    plants a second clock-dependent defect and the live check below starts asserting a
    count that rots. Both are the same assertion — the manifest's flagged set IS the
    exclusion set.
    """
    body = MANIFEST.read_text().partition("## Time-sensitive defect")[2]
    flagged = set(re.findall(r"\*\*(D\d+)\*\*", body))
    assert flagged == TIME_SENSITIVE, (
        f"seed/MANIFEST.md flags {sorted(flagged) or 'nothing'} as time-sensitive, this file "
        f"excludes {sorted(TIME_SENSITIVE)}. A count that decays must not be asserted as fixed."
    )
    assert "now()" in body, "the time-sensitive note no longer says what makes the count decay"


@pytest.mark.ge
def test_fingerprints_match_manifest_in_pk_order_utc() -> None:
    """`--fingerprint` against the live database equals the three hashes in the manifest.

    This is the idempotency claim, executed: md5 over every row in primary-key order
    with the session timezone pinned to UTC. Row counts and table sizes are deliberately
    NOT asserted — reported size wobbles by a few kB between runs (free-space-map
    bookkeeping after a drop-and-recreate), and the fingerprints are the authority.
    """
    manifest = dict(FINGERPRINT.findall(MANIFEST.read_text()))
    live = dict(FINGERPRINT.findall(_seed("--fingerprint")))
    assert len(manifest) == 3, f"seed/MANIFEST.md no longer quotes three fingerprints: {manifest}"
    assert live == manifest, (
        f"the seeded database does not match seed/MANIFEST.md's fingerprints.\n"
        f"  manifest: {manifest}\n  live:     {live}\n"
        "Re-establish it: python3 seed/seed_demo_data.py"
    )


@pytest.mark.ge
def test_seed_verify_runs_without_repo_root_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """`--verify-only` finds every planted defect, and does so from an unrelated cwd.

    The exit code is not the authority here and is not asserted: it goes to 1 on any
    mismatch, D5's clock decay included, which would make this check fail for the age of
    the data rather than for a defect that went missing. The printed table is parsed
    instead, so the time-sensitive row can be judged on its own terms.
    """
    monkeypatch.chdir(tmp_path)
    rows = {m[1]: (m[2], _n(m[3]), _n(m[4])) for m in VERIFY_ROW.finditer(_seed("--verify-only"))}
    planted = _manifest_counts()
    assert set(rows) == set(
        planted
    ), f"verify reported {sorted(rows)}, the manifest plants {sorted(planted)}"

    stale = {d: r for d, r in rows.items() if d not in TIME_SENSITIVE and r[1] != r[2]}
    assert not stale, (
        f"planted vs observed disagree (id: table, planted, observed): {stale}. "
        "The manifest is the ground truth — re-seed with `python3 seed/seed_demo_data.py`, "
        "do not relax the manifest."
    )
    for did in TIME_SENSITIVE:
        _table, count, observed = rows[did]
        assert observed <= count, (
            f"{did} is the clock-dependent defect and observed {observed} of {count} planted "
            "rows — more than were planted means the seed drifted, not that time passed."
        )
