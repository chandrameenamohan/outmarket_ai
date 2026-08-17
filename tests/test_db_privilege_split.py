"""B2 · SPEC §3.1's privilege split, asked of PostgreSQL rather than of our code.

Before `app/db/roles.sql` ran, "the analysis path never writes to the tables under
analysis" was a property of THIS CODEBASE: every statement in `app/rules/store.py`
names `{schema}.rules`, and
`tests/test_rule_store.py::test_the_store_has_no_writer_that_skips_the_validator`
reads those targets out of the source and asserts the set is exactly one. That is
a good check and it proves the wrong thing — it proves our code does not try. A
bug that tried would sail straight past it, because the connection had every right
in the database.

So none of the checks here read our source for the absence of an INSERT. Two of
them ISSUE one, against `public.orders`, on the very connections the product uses,
and assert that PostgreSQL refuses. The refusal is the deliverable.

They are marked `ge` with the rest of the layer that needs a reachable database —
they need no Great Expectations, but `make check` reaches no network and `make
check-ge` is the only target that does. The third check is offline and stays in
`make check`, because a DSN the code reads and `.env.example` never mentions is a
fresh clone that dies on its first query.
"""

from __future__ import annotations

import ast
import os

import psycopg2
import psycopg2.errors
import pytest

from conftest import REPO, source_files

# The table under analysis, and the one every check here tries to damage.
TARGET = "public.orders"

# Read off `.env.example` rather than restated: the point of the coverage check
# below is that this file and the code agree, and a third copy of the key names
# here would be one more thing to keep in step.
OWNER_KEY = "SUPABASE_DB_URL_DIRECT"


def _dotted(node: ast.AST) -> str:
    """`os.environ.get` -> 'os.environ.get'. Anything not a dotted name -> ''."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    parts.append(node.id)
    return ".".join(reversed(parts))


def _lookup(node: ast.AST) -> ast.AST | None:
    """The expression naming the environment key, for every spelling of a read."""
    if isinstance(node, ast.Subscript) and _dotted(node.value) == "os.environ":
        return node.slice
    if isinstance(node, ast.Call) and _dotted(node.func) in ("os.environ.get", "os.getenv"):
        return node.args[0] if node.args else None
    return None


def _constants(tree: ast.AST) -> dict[str, str]:
    """`DSN_VAR = "SUPABASE_DB_URL_ANALYSIS"` -> {'DSN_VAR': 'SUPABASE_DB_URL_ANALYSIS'}.

    The house convention: an environment key is named once, in a `*_VAR` constant,
    and every read goes through it. That is what makes the keys findable at all —
    not one `os.environ["LITERAL"]` exists in `app/`.
    """
    return {
        target.id: node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id.endswith("_VAR")
        and isinstance(node.value.value, str)
    }


def _scan() -> tuple[dict[str, set[str]], list[str]]:
    """Every environment key `app/` reads, by module — plus the reads it could not follow."""
    keys: dict[str, set[str]] = {}
    opaque: list[str] = []
    for path in source_files("app"):
        rel = str(path.relative_to(REPO))
        tree = ast.parse(path.read_text(), filename=rel)
        named = _constants(tree)
        for node in ast.walk(tree):
            # The two shapes `_lookup` can match, narrowed here so `node.lineno` is
            # a fact rather than a getattr.
            if not isinstance(node, ast.Subscript | ast.Call):
                continue
            if (arg := _lookup(node)) is None:
                continue
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                keys.setdefault(rel, set()).add(arg.value)
            elif isinstance(arg, ast.Name) and arg.id in named:
                keys.setdefault(rel, set()).add(named[arg.id])
            else:
                opaque.append(f"{rel}:{node.lineno}")
    return keys, opaque


def test_env_example_covers_every_key_read_by_code() -> None:
    """A key the code reads and `.env.example` never names is a fresh clone that dies.

    It dies late, too: `cp .env.example .env` succeeds, `./init.sh` passes its own
    checks, and the first query raises `Unavailable` naming a variable nobody was
    told about. The scan is `ast` over `app/`, so it follows the `*_VAR` constants
    the modules actually use instead of grepping for string literals that are not
    there — and it fails loudly if it stops being able to follow one, which is the
    only way this check could go quietly blind.
    """
    keys, opaque = _scan()
    assert not opaque, (
        f"environment reads this check could not follow: {opaque}. It resolves a string "
        "literal or a module-level `*_VAR` constant; anything else makes the key invisible "
        "to the coverage assertion below. Name the key in a `*_VAR` constant."
    )
    found = sorted({k for module in keys.values() for k in module})
    assert found, "the scan found no environment keys in app/ at all — it has stopped looking"

    documented = (REPO / ".env.example").read_text()
    missing = [k for k in found if k not in documented]
    assert not missing, (
        f"app/ reads {missing}, and .env.example does not mention them. Every key the code "
        f"reads is documented there — the file is the only contract a fresh clone has. "
        f"Keys read today: {found}"
    )


def test_no_application_module_connects_as_the_owner() -> None:
    """The wiring half of B2, and the half a test can check without a network.

    `SUPABASE_DB_URL_DIRECT` is the account that owns `orders`. Three things use it —
    `seed/`, `init.sh` and `app/db/roles.sql`, none of them application code. The
    moment a module under `app/` reads it again, the two roles below are decoration:
    the grants are still in place, and nothing goes through them.
    """
    keys, _ = _scan()
    offenders = sorted(module for module, read in keys.items() if OWNER_KEY in read)
    assert not offenders, (
        f"{offenders} read {OWNER_KEY}, the credential that OWNS the tables under analysis. "
        "The analysis path uses SUPABASE_DB_URL_ANALYSIS and the store uses "
        "SUPABASE_DB_URL_SYSTEM (app/db/roles.sql); a module holding the owner's DSN has "
        "every privilege the split exists to remove."
    )
    reads = {k for module in keys.values() for k in module}
    assert {"SUPABASE_DB_URL_ANALYSIS", "SUPABASE_DB_URL_SYSTEM"} <= reads, (
        f"app/ reads {sorted(reads)}. Both split DSNs should be in use — if neither is, the "
        "check above passes for the wrong reason (nothing connects at all)."
    )


def _refused(dsn: str, sql: str) -> psycopg2.Error:
    """Issue `sql` on a fresh connection and return the error PostgreSQL answered with."""
    conn = psycopg2.connect(dsn, connect_timeout=15)
    try:
        with pytest.raises(psycopg2.Error) as caught, conn, conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()
    return caught.value


@pytest.mark.ge
def test_readonly_role_cannot_write_target_schema() -> None:
    """The analysis connection, asked to write to `orders`, and refused by the database.

    Every one of these is a bug the product could plausibly have — a profiler that
    materialised a scratch table, an executor that "fixed" a row, a cleanup that
    truncated. None of them is refused by anything in this repository. All of them
    are refused here, by the grant.

    The DSN is read off `app/rules/schema.py`'s own constant rather than hard-coded,
    so pointing the analysis path back at a privileged credential fails this check
    instead of silently passing it.
    """
    from app.rules import schema as live  # noqa: PLC0415

    dsn = os.environ.get(live.DSN_VAR)
    assert dsn, f"{live.DSN_VAR} is not set; there is no analysis connection to test."

    with psycopg2.connect(dsn, connect_timeout=15) as conn, conn.cursor() as cur:
        cur.execute("select current_user")
        (who,) = cur.fetchone()
        cur.execute(f"select count(*) from {TARGET}")
        (rows,) = cur.fetchone()
    conn.close()
    assert rows > 0, (
        f"{who} read no rows from {TARGET}. A role that cannot do its job would pass every "
        "refusal below for the wrong reason, so the read is asserted first."
    )

    attacks = {
        f"insert into {TARGET} (order_reference) values ('dq-5pb.2')": "an invented row",
        f"update {TARGET} set order_total = 0 where false": "a rewritten value",
        f"delete from {TARGET} where false": "a deleted row",
        "create table public.dq_analyst_probe (x int)": "a table of its own in the target schema",
    }
    for sql, damage in attacks.items():
        error = _refused(dsn, sql)
        assert isinstance(error, psycopg2.errors.InsufficientPrivilege), (
            f"`{sql}` failed with {error!r}, which is not a privilege refusal. So {damage} was "
            "stopped by something else — a constraint, a typo, a missing column — and the grant "
            "is not what is holding."
        )
        assert "permission denied" in str(error).lower(), (
            f"`{sql}` was answered with {str(error).strip()!r} rather than a permission error. "
            f"{damage.capitalize()} is what {who} must never be able to produce."
        )


@pytest.mark.ge
def test_system_role_can_write_only_system_schema() -> None:
    """The store's own connection: it writes where it should, and nowhere else.

    Taken from `app/db/system.py` rather than opened here, because the claim is about
    the connection the product actually persists rules and run records on — not about
    a lookalike built from the same DSN.

    The write half is a scratch table rather than a row in `{schema}.rules`: the
    store is append-only by design, so a row inserted here could never be removed,
    and it would count toward coverage forever. `create`, `insert`, `select`,
    `drop` on a table of its own proves the same privilege and leaves nothing.
    """
    from app.db import system  # noqa: PLC0415
    from app.rules import store  # noqa: PLC0415

    schema = system.schema()
    probe = f"{schema}.privilege_probe"

    with system.cursor(store.DDL) as cur:
        cur.execute(f"create table if not exists {probe} (note text)")
        cur.execute(f"insert into {probe} values ('dq-5pb.2')")
    with system.cursor(store.DDL) as cur:
        cur.execute(f"select note from {probe}")
        written = cur.fetchall()
        cur.execute(f"drop table {probe}")
    assert written == [("dq-5pb.2",)], (
        f"the store's connection could not write to its own schema {schema!r} (got {written}). "
        "The split is meant to scope this role, not to disarm it."
    )

    # The half that did not exist before B2. The store never needed rights over the
    # tables under analysis, and until now it held them anyway.
    refusal = psycopg2.errors.InsufficientPrivilege
    for sql in (
        f"insert into {TARGET} (order_reference) values ('dq-5pb.2')",
        f"select count(*) from {TARGET}",
    ):
        with pytest.raises(refusal) as caught, system.cursor(store.DDL) as cur:
            cur.execute(sql)
        assert "permission denied" in str(caught.value).lower(), (
            f"the store's connection answered `{sql}` with {str(caught.value).strip()!r} rather "
            f"than a permission error. It is granted nothing on `public` (app/db/roles.sql) — "
            "not read, and certainly not write."
        )


def test_the_role_split_sql_is_committed_and_names_both_roles() -> None:
    """The grants have to be readable by a reviewer who will never run them.

    A privilege split that exists only in a database someone once typed into is not
    reviewable and not reproducible. This is the cheapest possible guard on that:
    the file is on disk and it mentions both roles it is supposed to create.
    """
    sql = (REPO / "app/db/roles.sql").read_text()
    for role in ("dq_analyst", "dq_system"):
        assert f"create role {role} login" in sql, (
            f"app/db/roles.sql does not create {role}. It is the reproduction recipe for the "
            "two checks above; if it drifts from the live database they stop meaning anything."
        )
    assert "grant select on all tables in schema public to dq_analyst" in sql, (
        "app/db/roles.sql no longer grants the analysis role its read. The refusals would "
        "still pass — a role with no rights refuses everything — and the product would be dead."
    )
