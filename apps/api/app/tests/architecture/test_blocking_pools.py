"""Blocking calls run on a bounded pool of their own, never the shared default executor.

The default executor has five threads on a one-CPU machine. R2 retries, thumbnail
resizes, PDF parses, Google sign-in and a stalled DuckDuckGo search all queued there,
and a timed-out wait left its thread running. ``core/blocking.run_blocking`` gives each
kind its own pool; CPU-bound parsing runs in killable processes (``core/document_executor``).
"""

from __future__ import annotations

import ast

from .boundary_support import APP_ROOT

_POOLS = APP_ROOT / "core" / "blocking.py"


def _default_executor_calls(source: str) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "to_thread":
            lines.append(node.lineno)
        elif node.func.attr == "run_in_executor":
            lines.append(node.lineno)
    return lines


def test_the_guard_sees_the_default_executor() -> None:
    source = (
        "import asyncio\n"
        "async def f(loop):\n"
        "    await asyncio.to_thread(g)\n"
        "    await loop.run_in_executor(None, g)\n"
    )
    assert _default_executor_calls(source) == [3, 4]


def test_no_production_code_uses_the_default_executor() -> None:
    found = [
        f"{path.relative_to(APP_ROOT)}:{line}"
        for path in sorted(APP_ROOT.rglob("*.py"))
        if "tests" not in path.relative_to(APP_ROOT).parts and path != _POOLS
        for line in _default_executor_calls(path.read_text())
    ]
    assert not found, "Use core.blocking.run_blocking with a kind:\n" + "\n".join(found)
