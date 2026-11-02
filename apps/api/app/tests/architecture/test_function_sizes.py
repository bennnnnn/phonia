"""A production function may run to 100 lines; a longer one may only shrink (audit CLAR-03).

ES-19 to ES-37 cut functions over 100 lines from 87 to 61, but new ones arrived as fast
as tickets removed them, and the longest (152 to 218 lines) were never ticketed. Each
function over the limit is recorded in ``function_size_baseline.json`` at its length: it
may not grow, and no new one may join. After a split, rerun with ``UPDATE_FUNCTION_SIZES=1``
to lower the recorded lengths and drop functions back under the limit.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

from .boundary_support import APP_ROOT

LIMIT = 100
_BASELINE = Path(__file__).with_name("function_size_baseline.json")


def _function_sizes() -> dict[str, int]:
    """``file::qualified.name`` -> lines, for every production function."""
    sizes: dict[str, int] = {}

    def visit(node: ast.AST, file: str, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                name = f"{prefix}{child.name}"
                lines = (child.end_lineno or child.lineno) - child.lineno + 1
                key = f"{file}::{name}"
                sizes[key] = max(lines, sizes.get(key, 0))
                visit(child, file, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, file, f"{prefix}{child.name}.")
            else:
                visit(child, file, prefix)

    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT)
        if "tests" not in relative.parts:
            visit(ast.parse(path.read_text()), relative.as_posix(), "")
    return sizes


def _recorded(sizes: dict[str, int]) -> dict[str, int]:
    recorded: dict[str, int] = json.loads(_BASELINE.read_text())
    if os.environ.get("UPDATE_FUNCTION_SIZES"):
        recorded = {
            name: min(lines, sizes[name])
            for name, lines in sorted(recorded.items())
            if sizes.get(name, 0) > LIMIT
        }
        _BASELINE.write_text(json.dumps(recorded, indent=2) + "\n")
    return recorded


def test_no_long_function_grows_or_joins() -> None:
    sizes = _function_sizes()
    recorded = _recorded(sizes)
    new = [
        f"{name}: {lines}"
        for name, lines in sizes.items()
        if lines > LIMIT and name not in recorded
    ]
    grown = [
        f"{name}: {recorded[name]} -> {lines}"
        for name, lines in sizes.items()
        if name in recorded and lines > recorded[name]
    ]
    assert new == [], f"over {LIMIT} lines: split it by step (read, decide, write)"
    assert grown == [], "a recorded long function grew: put the new code in its own function"


def test_the_recorded_lengths_are_current() -> None:
    sizes = _function_sizes()
    shorter = [
        f"{name}: {lines} -> {sizes.get(name, 'gone')}"
        for name, lines in _recorded(sizes).items()
        if sizes.get(name, 0) < lines
    ]
    assert shorter == [], "shorter now: rerun with UPDATE_FUNCTION_SIZES=1 to lock it in"
