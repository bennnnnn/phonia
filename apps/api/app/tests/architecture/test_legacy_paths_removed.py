"""Compatibility paths from the module migrations stay deleted.

Each migrated domain once kept a re-export under ``routers/``, ``services/``,
``repositories/``, ``background/`` or ``models/`` so callers could move one at a
time. Every caller now imports the owning module, so the old paths are gone and
nothing may name them again — not an import, not a ``patch("...")`` target.
"""

from __future__ import annotations

import ast
import importlib
import re

import pytest

from .boundary_support import APP_ROOT, RETIRED_LEGACY_MODULES

_RETIRED = re.compile(
    r"(?<![\w.])(" + "|".join(re.escape(name) for name in RETIRED_LEGACY_MODULES) + r")(?![\w])"
)
_THIS_CHECK = {
    APP_ROOT / "tests" / "architecture" / "boundary_support.py",
    APP_ROOT / "tests" / "architecture" / "test_legacy_paths_removed.py",
}


def _python_sources() -> list:
    return [
        path
        for path in APP_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and path not in _THIS_CHECK
    ]


@pytest.mark.parametrize("module", RETIRED_LEGACY_MODULES)
def test_retired_module_cannot_be_imported(module: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_no_code_or_test_names_a_retired_path() -> None:
    violations = [
        f"{path.relative_to(APP_ROOT)}: {match.group(1)}"
        for path in _python_sources()
        for match in _RETIRED.finditer(path.read_text())
    ]
    assert not violations, "\n".join(violations)


def test_no_package_import_reaches_a_retired_module() -> None:
    """``from app.services import plan`` names ``app.services.plan`` without the dotted string."""
    retired = set(RETIRED_LEGACY_MODULES)
    violations: list[str] = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            for alias in node.names:
                if f"{node.module}.{alias.name}" in retired:
                    violations.append(
                        f"{path.relative_to(APP_ROOT)} imports {node.module}.{alias.name}"
                    )
    assert not violations, "\n".join(violations)


def test_modules_install_no_import_aliases() -> None:
    assert not list((APP_ROOT / "modules").glob("*/legacy_alias.py"))
