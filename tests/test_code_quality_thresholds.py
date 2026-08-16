"""Deterministic craft signals that ruff cannot express.

ruff already covers the two that matter most and needs no help:
  - dead code      F401 unused import, F841 unused variable
  - function size  C901 complexity, PLR0912 branches, PLR0915 statements

What ruff has no rule for is FILE size, and what nothing else can check is the
harness's own central claim — that `pending()` is the ONLY way to produce a stub.
Both live here, in stdlib `ast`, rather than as a new dependency. Duplication
detection is deliberately absent; see VERIFICATION.md §6 for the tool and the
trigger for adding it.
"""

from __future__ import annotations

import ast
import pathlib

from conftest import REPO, source_files

MAX_LINES = 400  # a file past this is doing two jobs; split it before it gets a third

# The routes to a quietly-green stub. `pending()` skips loudly with a reason;
# these skip silently or, worse, pass. conftest.py is exempt because it is where
# `pending()` itself calls pytest.skip — that is the single sanctioned use.
SKIP_DODGES = {
    "pytest.skip",
    "pytest.mark.skip",
    "pytest.mark.skipif",  # the commonest skip route in real projects
    "pytest.mark.xfail",
    "pytest.xfail",  # the imperative form; mark.xfail is not the only spelling
    "pytest.importorskip",  # what someone will reach for in the `ge` layer
    "mark.skip",
    "mark.skipif",
    "mark.xfail",
}

# Dotted spellings are only half of it: `from pytest import skip` then a bare
# `skip(...)` is an ast.Name call and invisible to the scan above. Rather than
# resolve aliases, ban the import — which catches renames-on-import for free.
SKIP_IMPORTS = {"skip", "xfail", "importorskip"}


def _dotted(node: ast.AST) -> str:
    """`pytest.mark.skip` -> 'pytest.mark.skip'. Anything else -> ''."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    parts.append(node.id)
    return ".".join(reversed(parts))


def _test_functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    # AsyncFunctionDef is NOT a subclass of FunctionDef. Omitting it makes every
    # `async def test_...` invisible to the vacuity check below.
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test_")
    ]


def _parsed_tests() -> list[tuple[pathlib.Path, ast.AST]]:
    return [
        (p.relative_to(REPO), ast.parse(p.read_text(), filename=str(p)))
        for p in source_files("tests")
    ]


def test_no_source_file_exceeds_the_size_threshold() -> None:
    """Covers the TypeScript side too. "This file is doing two jobs" is a craft
    threshold, not a Python one, and a 900-line `page.tsx` would otherwise walk
    straight past the only signal that catches it — eslint has no file-size rule
    either. `web/app` is the route tree, and holds no node_modules."""
    files = source_files("app", "tests") + list((REPO / "web/app").rglob("*.tsx"))
    oversized = [
        (p.relative_to(REPO), n)
        for p in files
        if (n := len(p.read_text().splitlines())) > MAX_LINES
    ]
    assert not oversized, f"files over {MAX_LINES} lines: {oversized}"


def test_no_test_function_is_vacuous() -> None:
    """A `test_` body with neither an assert nor a `pending()` verifies nothing.

    This is the check that keeps the rest of the harness honest: without it,
    `def test_x(): pass` is indistinguishable from a passing check.
    """
    vacuous = []
    for rel, tree in _parsed_tests():
        for fn in _test_functions(tree):
            nodes = list(ast.walk(fn))
            asserts = any(isinstance(n, ast.Assert) for n in nodes)
            pends = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "pending"
                for n in nodes
            )
            if not (asserts or pends):
                vacuous.append(f"{rel}:{fn.lineno} {fn.name}")
    assert not vacuous, (
        f"test functions that assert nothing and declare no PENDING: {vacuous}. "
        "Assert something, or call pending('what it is waiting for')."
    )


def test_pending_is_the_only_route_to_a_skip() -> None:
    """conftest.py says there is 'deliberately no other route' to a stub. Checked, not asserted."""
    dodges = []
    for rel, tree in _parsed_tests():
        if rel.name == "conftest.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and (name := _dotted(node)) in SKIP_DODGES:
                dodges.append(f"{rel}:{node.lineno} {name}")
            elif isinstance(node, ast.ImportFrom) and node.module == "pytest":
                for alias in node.names:
                    if alias.name in SKIP_IMPORTS:
                        dodges.append(f"{rel}:{node.lineno} from pytest import {alias.name}")
    assert not dodges, (
        f"silent skip routes found: {dodges}. A stub must be `pending(...)` from conftest, "
        "which prints a PENDING reason under `pytest -ra`; these do not."
    )


def test_no_test_function_is_async() -> None:
    """An `async def test_` here can only ever skip, so it is a silent stub by another name.

    Nothing here wires up async tests: pytest-asyncio 0.23.3 is present but runs in
    STRICT mode, so an unmarked coroutine is not its business. pytest collects the
    test, refuses to run it, and skips it with "async def function and no async
    plugin installed" — a reason that never starts with PENDING (verified 2026-08-16).
    Ban the shape rather than wire up a plugin nothing needs yet.
    """
    coroutines = [
        f"{rel}:{fn.lineno} {fn.name}"
        for rel, tree in _parsed_tests()
        for fn in _test_functions(tree)
        if isinstance(fn, ast.AsyncFunctionDef)
    ]
    assert not coroutines, (
        f"async test functions: {coroutines}. Nothing runs them — pytest skips an async test "
        "when no async plugin is installed, which is a silent stub. Make it sync, or install "
        "and configure a plugin first."
    )
