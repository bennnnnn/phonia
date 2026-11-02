"""A broad ``except`` that swallows its error may only grow rarer.

An ``except Exception`` (or ``BaseException``, or a bare ``except``) whose body neither
raises nor reports the error hides a failure: production records nothing, and the turn
quietly does something else. Reporting means a log call at info level or above
(production logs at INFO, so a ``logger.debug`` alone is silent there) or a Sentry
``capture_exception``/``capture_message``; a raise or log inside a nested function is not
the handler's. A ``with suppress(Exception)`` is the same swallow and counts too.

Today's are counted per file in ``silent_except_baseline.json``; no file may gain one.
Log the error at the level it deserves, or catch the exceptions you expect by name.
After removing one, rerun with ``UPDATE_SILENT_EXCEPTS=1`` to lower the count.
"""

from __future__ import annotations

import ast
import json
import os
from collections import Counter
from collections.abc import Iterator
from functools import cache
from pathlib import Path

from .boundary_support import APP_ROOT

_BASELINE = Path(__file__).with_name("silent_except_baseline.json")
_BROAD = frozenset({"Exception", "BaseException"})
_REPORTING_LEVELS = frozenset(
    {"info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}
)
_LOGGERS = frozenset({"log", "logger", "logging"})
_SENTRY = frozenset({"capture_exception", "capture_message"})
# logging's level names and numbers; INFO (20) and above reach production logs.
_LEVELS = {
    "NOTSET": 0,
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "WARN": 30,
    "ERROR": 40,
    "CRITICAL": 50,
    "FATAL": 50,
}
_INFO = 20


def _is_broad(caught: ast.expr | None) -> bool:
    if caught is None:
        return True
    if isinstance(caught, ast.Name):
        return caught.id in _BROAD
    if isinstance(caught, ast.Attribute):
        return caught.attr in _BROAD
    if isinstance(caught, ast.Tuple):
        return any(_is_broad(element) for element in caught.elts)
    return False


def _level_names(tree: ast.AST) -> dict[str, int]:
    """Names a file gives logging levels: ``from logging import DEBUG as quiet`` and module
    constants such as ``TRACE = logging.DEBUG`` or ``TRACE = 5``."""
    names: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "logging":
            for alias in node.names:
                if alias.name in _LEVELS:
                    names[alias.asname or alias.name] = _LEVELS[alias.name]
    for node in getattr(tree, "body", []):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            level = _level_value(node.value, names)
            if level is not None:
                names[node.targets[0].id] = level
    return names


def _level_value(node: ast.expr | None, names: dict[str, int]) -> int | None:
    """The level ``node`` spells (``logging.DEBUG``, ``10``, an imported ``DEBUG``), if any."""
    if isinstance(node, ast.Attribute) and node.attr in _LEVELS:
        return _LEVELS[node.attr]
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.Name):
        return names.get(node.id)
    return None


def _reports(call: ast.Call, levels: dict[str, int]) -> bool:
    """``logger.warning(...)``, ``logging.exception(...)``, ``sentry_sdk.capture_exception()``."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in _SENTRY
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr in _SENTRY:
        return True
    owner = func.value
    name = (owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")).lower()
    is_logger = name.lstrip("_") in _LOGGERS or name.endswith("logger")
    if not is_logger or func.attr not in _REPORTING_LEVELS:
        return False
    return func.attr != "log" or _reported_level(call, levels)


def _reported_level(call: ast.Call, levels: dict[str, int]) -> bool:
    """``logger.log(level, …)`` reports at INFO or above; ``logging.DEBUG``, ``NOTSET``, an
    imported ``DEBUG`` or any number below 20 never reaches production logs. A level held in
    a variable the file does not name gets the benefit."""
    level = (
        call.args[0]
        if call.args
        else next((kw.value for kw in call.keywords if kw.arg == "level"), None)
    )
    if level is None:
        return False
    value = _level_value(level, levels)
    return value is None or value >= _INFO


def _own_nodes(statements: list[ast.stmt]) -> Iterator[ast.AST]:
    """Every node of ``statements`` outside nested functions and classes."""
    stack: list[ast.AST] = list(statements)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            stack.extend(ast.iter_child_nodes(node))


def _is_silent(handler: ast.ExceptHandler, levels: dict[str, int]) -> bool:
    return not any(
        isinstance(node, ast.Raise) or (isinstance(node, ast.Call) and _reports(node, levels))
        for node in _own_nodes(handler.body)
    )


def _suppresses_broadly(node: ast.AST) -> bool:
    """``suppress(Exception)``, ``contextlib.suppress(ValueError, BaseException)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return name == "suppress" and any(_is_broad(argument) for argument in node.args)


def _silent_counts(trees: dict[str, ast.AST]) -> dict[str, int]:
    """File -> broad handlers that neither raise nor report, and broad ``suppress`` calls."""
    counts: Counter[str] = Counter()
    for file, tree in trees.items():
        levels = _level_names(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ExceptHandler)
                and _is_broad(node.type)
                and _is_silent(node, levels)
            ):
                counts[file] += 1
            elif _suppresses_broadly(node):
                counts[file] += 1
    return dict(sorted(counts.items()))


@cache
def _production_counts() -> dict[str, int]:
    trees: dict[str, ast.AST] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT)
        if "tests" not in relative.parts and "__pycache__" not in relative.parts:
            trees[relative.as_posix()] = ast.parse(path.read_text())
    return _silent_counts(trees)


def _recorded(counts: dict[str, int]) -> dict[str, int]:
    recorded: dict[str, int] = json.loads(_BASELINE.read_text())
    if os.environ.get("UPDATE_SILENT_EXCEPTS"):
        recorded = {
            file: min(count, counts[file])
            for file, count in sorted(recorded.items())
            if counts.get(file, 0) > 0
        }
        _BASELINE.write_text(json.dumps(recorded, indent=2) + "\n")
    return recorded


def test_silent_counts_only_broad_swallows() -> None:
    silent = (
        "try:\n    a()\nexcept Exception:\n    return None\n",
        "try:\n    a()\nexcept:\n    pass\n",
        "try:\n    a()\nexcept (ValueError, BaseException):\n    x = 1\n",
        "try:\n    a()\nexcept Exception as exc:\n    logger.debug('a failed: %s', exc)\n",
        "try:\n    a()\nexcept Exception as exc:\n    log.append(exc)\n",
        "try:\n    a()\nexcept Exception:\n    catalog.info('a')\n",
        "try:\n    a()\nexcept Exception:\n    def later():\n        raise ValueError\n",
        "try:\n    a()\nexcept* Exception:\n    pass\n",
        "with contextlib.suppress(Exception):\n    a()\n",
        "with suppress(ValueError, BaseException):\n    a()\n",
        # 2026-11-01: a DEBUG line through ``log`` never reaches production logs either.
        "try:\n    a()\nexcept Exception:\n    logger.log(logging.DEBUG, 'a failed')\n",
        "try:\n    a()\nexcept Exception:\n    logger.log(10, 'a failed')\n",
        "try:\n    a()\nexcept Exception:\n    logger.log(logging.NOTSET, 'a failed')\n",
        "try:\n    a()\nexcept Exception:\n    logger.log(level=logging.DEBUG, msg='a failed')\n",
    )
    # Each in a file of its own: the level is named by an import or a constant.
    named_silent = (
        "from logging import DEBUG\ntry:\n    a()\nexcept Exception:\n    logger.log(DEBUG, 'x')\n",
        "from logging import DEBUG as QUIET\ntry:\n    a()\nexcept Exception:\n    logger.log(QUIET, 'x')\n",
        "TRACE = logging.DEBUG\ntry:\n    a()\nexcept Exception:\n    logger.log(TRACE, 'x')\n",
        "TRACE = 5\ntry:\n    a()\nexcept Exception:\n    logger.log(TRACE, 'x')\n",
    )
    named_reported = (
        "from logging import WARNING\ntry:\n    a()\nexcept Exception:\n    logger.log(WARNING, 'x')\n",
        "LOUD = logging.ERROR\ntry:\n    a()\nexcept Exception:\n    logger.log(LOUD, 'x')\n",
    )
    for source in named_silent:
        assert _silent_counts({"x.py": ast.parse(source)}) == {"x.py": 1}, source
    for source in named_reported:
        assert _silent_counts({"x.py": ast.parse(source)}) == {}, source
    reported = (
        "try:\n    a()\nexcept ValueError:\n    pass\n",
        "with suppress(ValueError):\n    a()\n",
        "try:\n    a()\nexcept Exception:\n    logger.warning('a failed')\n",
        "try:\n    a()\nexcept Exception:\n    self._logger.info('a failed')\n",
        "try:\n    a()\nexcept Exception:\n    logging.exception('a failed')\n",
        "try:\n    a()\nexcept Exception:\n    sentry_sdk.capture_exception()\n",
        "try:\n    a()\nexcept Exception as exc:\n    raise RuntimeError from exc\n",
        "try:\n    a()\nexcept Exception:\n    if b():\n        raise\n",
        "try:\n    a()\nexcept Exception:\n    logger.log(logging.WARNING, 'a failed')\n",
        "try:\n    a()\nexcept Exception:\n    logger.log(level, 'a failed')\n",
    )
    assert _silent_counts({"x.py": ast.parse("".join(silent))}) == {"x.py": len(silent)}
    assert _silent_counts({"x.py": ast.parse("".join(reported))}) == {}


def test_no_file_gains_a_silent_broad_except() -> None:
    counts = _production_counts()
    recorded = _recorded(counts)
    gained = [
        f"{file}: {recorded.get(file, 0)} -> {count}"
        for file, count in counts.items()
        if count > recorded.get(file, 0)
    ]
    assert gained == [], (
        "a broad except or suppress swallows its error: log it at info or above, or catch"
        " the exceptions you expect by name\n  " + "\n  ".join(gained)
    )


def test_the_recorded_counts_are_current() -> None:
    counts = _production_counts()
    fewer = [
        f"{file}: {count} -> {counts.get(file, 0)}"
        for file, count in _recorded(counts).items()
        if counts.get(file, 0) < count
    ]
    assert fewer == [], "fewer now: rerun with UPDATE_SILENT_EXCEPTS=1 to lock it in"
