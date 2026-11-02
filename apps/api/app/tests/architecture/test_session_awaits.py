"""No pooled connection is held idle in transaction across a slow call.

A session's first statement opens a transaction that lasts until commit or rollback.
Thumbnails awaited R2 and a resize queue, message lists awaited a stream's save, and
compaction awaited a model, each with a connection checked out: a few such requests
emptied a machine's 30-connection pool and every other request failed after the 5 s
pool timeout. CLAUDE.md: "Slow provider calls should run outside an open DB
transaction." This guard flags a slow await (a gateway call, a finalize wait, a sleep)
that runs while a session's transaction is open:

- inside ``async with SessionLocal() as session:`` (or a ``session_factory()``), after
  the block's first statement, with no commit or rollback in between; or
- in a function taking a session, after a statement on it, with no commit or rollback
  in between.

It reads statements in source order, so a branch can mislead it: a deliberate case
goes in ``_ALLOWED`` with its reason.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .boundary_support import APP_ROOT

# Calls that wait on something outside this process, by name.
_SLOW_NAMES = frozenset({"wait_for_pending_finalize", "wait_for_inflight_stream", "sleep"})
_END_TRANSACTION = frozenset({"commit", "rollback", "close"})
_SESSION_FACTORIES = frozenset({"SessionLocal", "session_factory"})
# (path under app/, function) → why its slow await inside a transaction is acceptable.
_ALLOWED: dict[tuple[str, str], str] = {
    ("modules/account/lifecycle.py", "delete_account"): (
        "users_repo.delete_user commits; the Apple revoke runs after it"
    ),
    ("modules/attachments/workflow.py", "store_local_upload"): (
        "local development storage only: the row lock is held on purpose while the "
        "upload is written to disk"
    ),
    ("modules/attachments/workflow.py", "get_file_access"): (
        "_verified_row ends its read before returning; the thumbnail runs after"
    ),
    ("modules/attachments/workflow.py", "get_download"): (
        "_verified_row ends its read before returning; presigning signs locally"
    ),
}


@dataclass(frozen=True)
class _Hit:
    path: str
    function: str
    line: int
    call: str


def _gateway_names(tree: ast.Module) -> set[str]:
    """Names this module binds to ``app.gateways`` modules or their members."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "app.gateways" or node.module.startswith("app.gateways."):
                names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.gateways."):
                    names.add(alias.asname or alias.name.split(".")[-1])
    return names


def _callee(call: ast.Call) -> tuple[str | None, str]:
    """``(receiver, name)``: ``a.b.c()`` → ``("a.b", "c")``; ``f()`` → ``(None, "f")``."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return ast.unparse(func.value), func.attr
    if isinstance(func, ast.Name):
        return None, func.id
    return None, ast.unparse(func)


def _is_slow(call: ast.Call, gateways: set[str]) -> bool:
    receiver, name = _callee(call)
    if name in _SLOW_NAMES and (receiver in (None, "asyncio", "finalize_registry")):
        return True
    if receiver is None:
        return name in gateways
    root = receiver.split(".")[0]
    return root in gateways or "gateway" in root.lower()


def _uses_session(call: ast.Call, session: str) -> bool:
    receiver, _name = _callee(call)
    if receiver == session:
        return True
    return any(isinstance(arg, ast.Name) and arg.id == session for arg in call.args) or any(
        isinstance(kw.value, ast.Name) and kw.value.id == session for kw in call.keywords
    )


def _ends_transaction(call: ast.Call, session: str) -> bool:
    receiver, name = _callee(call)
    return receiver == session and name in _END_TRANSACTION


def _awaited_calls(body: list[ast.stmt]) -> list[ast.Call]:
    calls = [
        node.value
        for statement in body
        for node in ast.walk(statement)
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
    ]
    return sorted(calls, key=lambda call: (call.lineno, call.col_offset))


def _scan(body: list[ast.stmt], session: str, gateways: set[str]) -> list[ast.Call]:
    """Slow awaits made while ``session`` has a transaction open, in source order."""
    open_transaction = False
    hits: list[ast.Call] = []
    for call in _awaited_calls(body):
        if _ends_transaction(call, session):
            open_transaction = False
        elif _uses_session(call, session):
            open_transaction = True
        elif open_transaction and _is_slow(call, gateways):
            hits.append(call)
    return hits


def _session_params(function: ast.AsyncFunctionDef) -> list[str]:
    params = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    return [
        param.arg
        for param in params
        if param.annotation is not None and "AsyncSession" in ast.unparse(param.annotation)
    ]


def _session_blocks(function: ast.AsyncFunctionDef) -> list[tuple[str, list[ast.stmt]]]:
    blocks: list[tuple[str, list[ast.stmt]]] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.AsyncWith):
            continue
        for item in node.items:
            expr = item.context_expr
            if (
                isinstance(expr, ast.Call)
                and _callee(expr)[1] in _SESSION_FACTORIES
                and isinstance(item.optional_vars, ast.Name)
            ):
                blocks.append((item.optional_vars.id, node.body))
    return blocks


def held_transaction_awaits(source: str, path: str) -> list[_Hit]:
    tree = ast.parse(source)
    gateways = _gateway_names(tree)
    hits: list[_Hit] = []
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)):
        scans = [(name, function.body) for name in _session_params(function)]
        scans.extend(_session_blocks(function))
        for session, body in scans:
            for call in _scan(body, session, gateways):
                hits.append(_Hit(path, function.name, call.lineno, ast.unparse(call.func)))
    return sorted(set(hits), key=lambda hit: (hit.path, hit.line))


def _production_files() -> list[Path]:
    return [
        path for path in APP_ROOT.rglob("*.py") if "tests" not in path.relative_to(APP_ROOT).parts
    ]


def test_the_guard_flags_a_slow_call_inside_an_open_transaction() -> None:
    source = """
from app.gateways import embedding_gateway
async def held(session: AsyncSession):
    row = await repo.get(session, 1)
    await embedding_gateway.embed_text(settings, row.text)
async def released(session: AsyncSession):
    row = await repo.get(session, 1)
    await session.commit()
    await embedding_gateway.embed_text(settings, row.text)
async def block():
    async with SessionLocal() as session:
        await repo.get(session, 1)
        await finalize_registry.wait_for_pending_finalize(chat_id, redis)
    await gateway.copy_bytes("a", "b")
"""
    hits = held_transaction_awaits(source, "x.py")
    assert [(hit.function, hit.call) for hit in hits] == [
        ("held", "embedding_gateway.embed_text"),
        ("block", "finalize_registry.wait_for_pending_finalize"),
    ]


def test_no_slow_call_runs_inside_an_open_transaction() -> None:
    found: list[str] = []
    for path in _production_files():
        relative = str(path.relative_to(APP_ROOT))
        for hit in held_transaction_awaits(path.read_text(), relative):
            if (hit.path, hit.function) not in _ALLOWED:
                found.append(f"{hit.path}:{hit.line} {hit.function} awaits {hit.call}")
    assert not found, "End the transaction (commit or rollback) before a slow call:\n" + "\n".join(
        found
    )


def test_every_allowance_still_applies() -> None:
    live = {
        (hit.path, hit.function)
        for path in _production_files()
        for hit in held_transaction_awaits(path.read_text(), str(path.relative_to(APP_ROOT)))
    }
    stale = sorted(
        f"{path} {function}" for path, function in _ALLOWED if (path, function) not in live
    )
    assert not stale, "Remove allowances that no longer match:\n" + "\n".join(stale)
