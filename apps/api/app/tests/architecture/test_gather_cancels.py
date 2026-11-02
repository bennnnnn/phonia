"""A failed branch never leaves its siblings running: no bare ``asyncio.gather``.

``asyncio.gather`` propagates the first error and leaves the other children running
(a paid model call, a search, an OCR page) with their errors never retrieved. Chat
had about fourteen such sites. Use ``core/aio.gather_or_cancel``, or pass
``return_exceptions=True`` and handle every result when each branch must finish.
"""

from __future__ import annotations

import ast

from .boundary_support import APP_ROOT

_HELPER = APP_ROOT / "core" / "aio.py"


def _bare_gathers(source: str) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "gather"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "asyncio"
            and not any(keyword.arg == "return_exceptions" for keyword in node.keywords)
        ):
            lines.append(node.lineno)
    return lines


def test_the_guard_sees_a_bare_gather() -> None:
    source = (
        "import asyncio\n"
        "async def f():\n"
        "    await asyncio.gather(a(), b())\n"
        "    await asyncio.gather(a(), b(), return_exceptions=True)\n"
    )
    assert _bare_gathers(source) == [3]


def test_no_production_code_gathers_without_cancelling_or_collecting() -> None:
    found = [
        f"{path.relative_to(APP_ROOT)}:{line}"
        for path in sorted(APP_ROOT.rglob("*.py"))
        if "tests" not in path.relative_to(APP_ROOT).parts and path != _HELPER
        for line in _bare_gathers(path.read_text())
    ]
    assert not found, "Use gather_or_cancel or return_exceptions=True:\n" + "\n".join(found)
