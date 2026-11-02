"""A typed column is read as an attribute, not through getattr (code-health audit CLAR-11).

``getattr(user, "memory_enabled", True)`` types as ``Any``, so a renamed column breaks
nothing, and its default becomes the behaviour: chat read memory as on and live talk as
off. A row annotated as a model reads its columns directly, a user's columns are never
read through ``getattr``, and the Settings → Memory switch has one reader,
``memory.switch.memory_switch_on``. Rows that come in several shapes (message dicts and
rows alike) stay duck-typed until they get one type.
"""

from __future__ import annotations

import ast
from functools import cache

import app.models.orm  # noqa: F401 - registers every table
from app.core.db import Base

from .boundary_support import APP_ROOT


@cache
def _columns() -> dict[str, frozenset[str]]:
    """Model class name -> its column attributes."""
    return {
        mapper.class_.__name__: frozenset(column.key for column in mapper.column_attrs)
        for mapper in Base.registry.mappers
    }


def _typed_reads(source: str) -> list[str]:
    """``getattr(row, "column", default)`` where ``row`` is a model or a user."""
    found: list[str] = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        params = function.args.posonlyargs + function.args.args + function.args.kwonlyargs
        models = {
            param.arg: {name for name in _columns() if name in ast.unparse(param.annotation)}
            for param in params
            if param.annotation is not None
        }
        for node in ast.walk(function):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) == 3
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                continue
            target, column = ast.unparse(node.args[0]), node.args[1].value
            typed = any(column in _columns()[model] for model in models.get(target, ()))
            if typed or target == "user" or target.endswith(".user"):
                found.append(f"{node.lineno}: getattr({target}, {column!r}, ...)")
    return sorted(set(found))


def test_typed_columns_are_read_as_attributes() -> None:
    found = [
        f"{path.relative_to(APP_ROOT)}:{line}"
        for path in sorted(APP_ROOT.rglob("*.py"))
        if "tests" not in path.relative_to(APP_ROOT).parts
        for line in _typed_reads(path.read_text())
    ]
    assert found == [], "read the column as an attribute"


def _switch_checks(source: str) -> list[int]:
    """Lines that ask a user's ``memory_enabled`` yes or no outside ``memory_switch_on``."""
    tree = ast.parse(source)
    asked: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If | ast.While | ast.IfExp):
            asked.append(node.test)
        elif isinstance(node, ast.BoolOp):
            asked.extend(node.values)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            asked.append(node.operand)
    return sorted(
        {
            node.lineno
            for node in asked
            if isinstance(node, ast.Attribute)
            and node.attr == "memory_enabled"
            and (ast.unparse(node.value) == "user" or ast.unparse(node.value).endswith(".user"))
        }
    )


def test_the_memory_switch_has_one_reader() -> None:
    readers = [
        f"{path.relative_to(APP_ROOT)}:{line}"
        for path in sorted(APP_ROOT.rglob("*.py"))
        if "tests" not in path.relative_to(APP_ROOT).parts and path.name != "switch.py"
        for line in _switch_checks(path.read_text())
    ]
    assert readers == [], "ask memory_switch_on(user)"


def test_the_check_sees_what_it_describes() -> None:
    sample = (
        "def a(user: User, memory: Memory | None, row):\n"
        "    getattr(user, 'timezone', None)\n"
        "    getattr(memory, 'topic', None)\n"
        "    getattr(row, 'content', None)\n"
        "    getattr(t.user, 'locale', 'en')\n"
    )
    assert _typed_reads(sample) == [
        "2: getattr(user, 'timezone', ...)",
        "3: getattr(memory, 'topic', ...)",
        "5: getattr(t.user, 'locale', ...)",
    ]
    checks = (
        "if not user.memory_enabled:\n    pass\n"
        "on = ctx.user.memory_enabled and ready\n"
        "changed = fields['memory_enabled'] != user.memory_enabled\n"
    )
    assert _switch_checks(checks) == [1, 3]
