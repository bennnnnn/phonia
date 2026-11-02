"""What mypy sees is typed, and every suppression says why (code-health audit CLAR-06).

Seven lazy packages exported through ``def __getattr__(name) -> Any``, so 58 imports,
``can_use`` among them, typed as ``Any`` and a renamed parameter passed CI. Ten
``# type: ignore`` comments no longer suppressed anything, and most suppressions gave
no reason. Each lazy export now has a ``TYPE_CHECKING`` import, mypy reports a stale
ignore (``warn_unused_ignores``), and a ``noqa`` or ``type: ignore`` carries its reason
on the same line or the comment line above.
"""

from __future__ import annotations

import ast
import re

from .boundary_support import APP_ROOT

_NOQA = re.compile(r"#\s*noqa(?::\s*[A-Z0-9, ]+)?(?P<rest>.*)$")
_IGNORE = re.compile(r"#\s*type:\s*ignore(?:\[[^\]]*\])?(?P<rest>.*)$")
_REASON = re.compile(r"\s*(?:-|--|—|#)\s*\S")


def _type_checking_imports(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """Exported name -> (module, attribute) the ``if TYPE_CHECKING:`` block imports."""
    found: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.If) and ast.unparse(node.test).endswith("TYPE_CHECKING"):
            for statement in node.body:
                if isinstance(statement, ast.ImportFrom) and statement.module:
                    for alias in statement.names:
                        found[alias.asname or alias.name] = (statement.module, alias.name)
    return found


def test_every_lazy_export_is_typed() -> None:
    untyped: list[str] = []
    for init in sorted((APP_ROOT / "modules").glob("*/__init__.py")):
        tree = ast.parse(init.read_text())
        exports: dict[str, object] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "_EXPORTS" for target in node.targets
            ):
                exports = ast.literal_eval(node.value)
        stubs = _type_checking_imports(tree)
        package = f"app.modules.{init.parent.name}"
        for name, target in exports.items():
            module, attribute = target if isinstance(target, tuple) else (target, name)
            if stubs.get(name) != (f"{package}.{module}", attribute):
                untyped.append(f"{package}: {name}")
    assert untyped == [], "import it under `if TYPE_CHECKING:` so mypy sees its type"


def test_every_suppression_says_why() -> None:
    silent: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if "tests" in path.relative_to(APP_ROOT).parts:
            continue
        lines = path.read_text().split("\n")
        for number, line in enumerate(lines, start=1):
            above = lines[number - 2].strip() if number > 1 else ""
            for pattern in (_NOQA, _IGNORE):
                match = pattern.search(line)
                if match and not _REASON.match(match["rest"]) and not above.startswith("#"):
                    silent.append(f"{path.relative_to(APP_ROOT)}:{number}")
    assert silent == [], "give the suppression a one-line reason"
