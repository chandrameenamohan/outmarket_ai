"""INV-3 · Great Expectations is a runtime, not the domain model.

Exactly one module may import great_expectations. This is the keystone
invariant: it is what lets GE's next breaking release be a one-file change
instead of a rewrite. It is enforced HERE, in the gate, not by convention.

Mechanism, in two halves so the check is never vacuous:

  half A (runs today, real)   no file outside GE_RUNTIME may reference GE.
                              Enforced by ast.parse for real imports. A second,
                              raw text scan covers the dodges AST misses —
                              importlib.import_module("great_expectations"),
                              __import__, re-exports through a string — but it
                              scans app/ only, so it PENDS until app/ exists
                              rather than passing over an empty file list.
  half B (PENDING)            GE_RUNTIME itself must exist and must import GE.
                              Skips until app/ exists; the moment it does, this
                              half also pins the module's location.
  half C (runs today, real)   nobody outside GE_RUNTIME calls get_context(), and
                              GE_RUNTIME calls it exactly once, at module level.
  half D (runs today, real)   the module a page load reads its cached run through
                              (`app/dq/runs.py`) has no path to GE_RUNTIME at all,
                              transitively. That is SPEC F9's "renders without
                              re-executing" as an import-boundary fact, which is
                              why it lives with the rest of the boundary rather
                              than beside the record's shape.

Half A is the one that matters — it fails the instant a second module reaches
for GE, which is exactly when the invariant would otherwise erode silently.

Half C is the same invariant one level down, and it exists because LT-1b was
bitten by it: `gx.get_context()` does not return a context, it INSTALLS one as a
process-global project. A second call silently orphans the first context's
datasources, and the failure does not surface at get_context() — it surfaces
later at validate(), as a DatasourceError naming a datasource that is sitting
right there in the object you are holding. So a request handler that calls
get_context() breaks every other request in flight and points the debugger at
configuration instead of at concurrency. One module, one call, one context.
"""

from __future__ import annotations

import ast
import pathlib

from conftest import REPO, pending, source_files

# Provisional path — one constant, change it here and the gate follows.
GE_RUNTIME = pathlib.Path("app/dq/ge_runtime.py")

# The module a page load reads a completed run through (half D). It is the ROOT of
# the walk, not a member of a list: the claim is about everything reachable from it.
RUN_CACHE = pathlib.Path("app/dq/runs.py")

# Directories the gate governs. learning-tests/ and seed/ are pre-gate scripts
# and are exempt on purpose (they import GE freely; that is their whole job).
GATED = ("app", "tests")

# The raw text scan runs on production code only. Tests are allowed to NAME the
# framework in prose and in expected-exception strings; they are not allowed to
# import it (the AST half above still covers them). A test that needs to exercise
# GE for real calls it through GE_RUNTIME, like everything else.
TEXT_SCANNED = ("app",)

NEEDLE = "great_expectations"

# The process-global factory (half C). Matched on the attribute/function name
# alone, so `gx.get_context()`, `great_expectations.get_context()` and a bare
# imported `get_context()` all count. Ceiling: an unrelated helper that happens
# to be called get_context would be a false positive — worth it, because the
# alternative is resolving aliases.
CONTEXT_FACTORY = "get_context"


def _parse(path: pathlib.Path) -> ast.AST:
    return ast.parse(path.read_text(), filename=str(path))


def _context_calls(tree: ast.AST) -> list[ast.Call]:
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == CONTEXT_FACTORY:
            calls.append(node)
        elif isinstance(func, ast.Name) and func.id == CONTEXT_FACTORY:
            calls.append(node)
    return calls


def _imports_ge(path: pathlib.Path) -> bool:
    tree = _parse(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == NEEDLE for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == NEEDLE:
                return True
    return False


def test_no_module_outside_the_runtime_imports_ge() -> None:
    offenders = [
        p.relative_to(REPO)
        for p in source_files(*GATED)
        if p.relative_to(REPO) != GE_RUNTIME and _imports_ge(p)
    ]
    assert not offenders, (
        f"INV-3 violated: {offenders} import great_expectations. "
        f"Only {GE_RUNTIME} may. Route it through that module's dict-in/dict-out surface."
    )


def test_no_dynamic_import_dodges_the_ast_check() -> None:
    """AST only sees real import statements. This catches the string-based dodges.

    Guarded the same way its sibling below is: `app/` does not exist yet, so without
    the guard the body reduces to `assert not []` — green today, green forever, and
    a sixth of the gate's positive signal verifying nothing.
    """
    files = source_files(*TEXT_SCANNED)
    if not files:
        pending(f"{'/'.join(TEXT_SCANNED)}/ does not exist yet — the text scan has nothing to scan")
    offenders = []
    for p in files:
        rel = p.relative_to(REPO)
        if rel == GE_RUNTIME:
            continue
        if NEEDLE in p.read_text():
            offenders.append(rel)
    assert not offenders, (
        f"INV-3 violated: {offenders} mention '{NEEDLE}' outside {GE_RUNTIME}. "
        "A dynamic import is still an import."
    )


def test_the_ge_runtime_module_exists_and_is_the_one_importer() -> None:
    target = REPO / GE_RUNTIME
    if not target.exists():
        pending(f"{GE_RUNTIME} does not exist yet — F7 (GE compilation) is unbuilt")
    assert _imports_ge(target), f"{GE_RUNTIME} is the designated GE module but does not import it"


def test_no_module_outside_the_runtime_creates_a_context() -> None:
    """Half C, first part. Real today: it fails the instant a second caller appears."""
    offenders = [
        p.relative_to(REPO)
        for p in source_files(*GATED)
        if p.relative_to(REPO) != GE_RUNTIME and _context_calls(_parse(p))
    ]
    assert not offenders, (
        f"INV-3 violated: {offenders} call {CONTEXT_FACTORY}(). It installs a PROCESS-GLOBAL "
        f"project — a second call orphans the first context's datasources and the error only "
        f"shows up later at validate(). Only {GE_RUNTIME} may create one; ask it for the context."
    )


def test_the_ge_runtime_creates_exactly_one_context_at_module_level() -> None:
    """Half C, second part: one call, and not one per request.

    Module level is the assertion that matters. A single call site sitting inside
    a request handler is still one context per request, which is the exact bug
    LT-1b hit. Ceiling: this proves one context per import of one module, which is
    what "one process" means here; it does not chase a module imported twice under
    two names.
    """
    target = REPO / GE_RUNTIME
    if not target.exists():
        pending(f"{GE_RUNTIME} does not exist yet — the process-global context has no owner")
    tree = _parse(target)
    calls = _context_calls(tree)
    assert len(calls) == 1, (
        f"{GE_RUNTIME} calls {CONTEXT_FACTORY}() {len(calls)} times "
        f"(lines {[c.lineno for c in calls]}); the process gets exactly one context."
    )
    nested = {
        c.lineno
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef)
        for c in _context_calls(fn)
    }
    assert not nested, (
        f"{GE_RUNTIME} calls {CONTEXT_FACTORY}() inside a function (lines {sorted(nested)}). "
        "Build the context once at import and hand it out — one per request is the LT-1b bug."
    )


def test_reading_the_run_cache_cannot_reach_the_executor() -> None:
    """Half D. 'Renders without re-executing', made structural rather than careful.

    Timing proves nothing here — a fast page load may still have executed and a slow
    one may not have. What proves it is that the module a page load reads through has
    no path to the framework AT ALL: the import graph out of `RUN_CACHE` is walked
    transitively, and half A's own reader says whether each node it lands on imports
    Great Expectations. `GE_RUNTIME` imports it at module level, so the day a cache
    read reaches the executor by any route, this fails.

    The walk's own blindness is what it is guarded against, and the guard is that it
    followed EVERY `app.*` import it saw. A "did it reach at least these modules"
    guard cannot do that job: `runs.py` imports two modules directly, so the trivial
    graph satisfies it — and the realistic regression is a deferred
    `from app.dq.ge_runtime import run` inside a function, which is the idiom this
    codebase uses everywhere and which a resolver that only tries `<module>/<name>.py`
    drops on the floor.

    The counting proof, against the real framework, is in
    `tests/test_run_records_on_postgres.py`.
    """
    reached: set[pathlib.Path] = set()
    unfollowed: list[str] = []
    frontier = [RUN_CACHE]
    while frontier:
        current = frontier.pop()
        if current in reached:
            continue
        reached.add(current)
        found, missed = _app_imports(current)
        unfollowed += missed
        frontier += [p for p in found if p not in reached]

    assert not unfollowed, (
        f"the walk could not follow {unfollowed}. A node it silently drops is a node it cannot "
        "see the framework behind — which is exactly how the deferred-import idiom this "
        "codebase uses everywhere would walk straight past it."
    )
    importers = [str(p) for p in sorted(reached) if _imports_ge(REPO / p)]
    assert not importers, (
        f"a page load reads the cache through {RUN_CACHE}, and {importers} on that import graph "
        f"imports {NEEDLE}. Rendering a stored run must not be able to run one (SPEC F9)."
    )


def _app_imports(relative: pathlib.Path) -> tuple[list[pathlib.Path], list[str]]:
    """The files under `app/` this file imports — and the `app.*` imports it could NOT follow.

    Two spellings resolve differently and both have to work. `from app.dq import runs`
    names a MODULE, so the path is the package plus the alias; `from app.dq.ge_runtime
    import run` names a FUNCTION inside one, so `app/dq/ge_runtime/run.py` does not
    exist and the module itself is what must be followed.

    An `app.*` import that resolves to neither is RETURNED rather than dropped, the
    same way `tests/test_db_privilege_split.py` fails on an environment read it cannot
    follow: a scan that silently loses a node proves nothing about where it could not
    reach.
    """
    found: list[pathlib.Path] = []
    unfollowed: list[str] = []

    def resolve(named: str, *candidates: pathlib.Path) -> None:
        for candidate in candidates:
            if (REPO / candidate).exists():
                found.append(candidate)
                return
        unfollowed.append(f"{relative}: {named}")

    for node in ast.walk(_parse(REPO / relative)):
        if isinstance(node, ast.ImportFrom) and (module := node.module or "").startswith("app"):
            package = pathlib.Path(module.replace(".", "/"))
            for alias in node.names:
                resolve(
                    f"{module}.{alias.name}",
                    package / f"{alias.name}.py",
                    package.with_suffix(".py"),
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app"):
                    resolve(alias.name, pathlib.Path(alias.name.replace(".", "/") + ".py"))
    return found, unfollowed
