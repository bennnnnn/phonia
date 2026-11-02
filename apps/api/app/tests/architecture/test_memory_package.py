"""Memory calls its collaborators directly, and no test patches its package (audit CLAR-05).

``surface.py`` handed the package module to cache, crud, locks and retrieval as
``seams: Any``, so a test's ``patch("app.modules.memory.X")`` reached them: 51 lookups
mypy could not check, 19 forwarding wrappers and 42 re-exports kept only to stay
patchable. The collaborators now call each other through their modules, the package
resolves each export on access without keeping it, and a test patches the module that
defines the name.
"""

from __future__ import annotations

import ast
import importlib
from unittest.mock import patch

import app.modules.memory as memory_package

from .boundary_support import APP_ROOT
from .test_patch_targets import patch_targets

_MEMORY = APP_ROOT / "modules" / "memory"
_TESTS = APP_ROOT / "tests"


def _object_at(dotted: str) -> object:
    """What a dotted name refers to: the longest importable prefix, then attributes."""
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            found: object = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for part in parts[cut:]:
            found = getattr(found, part)
        return found
    raise ImportError(dotted)


def _aliases(path: str) -> dict[str, str]:
    """Each name a test file binds by import -> the dotted name it stands for."""
    found: dict[str, str] = {}
    for node in ast.walk(ast.parse((_TESTS / path).read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                found[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
    return found


def _patched_owner(where: str, target: str) -> object | None:
    """The object whose attribute a patch replaces, or None when it cannot be named."""
    owner = target.rsplit(".", 1)[0]
    if not owner.startswith("app."):
        head, _, rest = owner.partition(".")
        bound = _aliases(where.split(":", 1)[0]).get(head)
        if bound is None:
            return None
        owner = f"{bound}.{rest}" if rest else bound
    try:
        return _object_at(owner)
    except (ImportError, AttributeError):
        return None


def test_memory_has_no_seams() -> None:
    assert not (_MEMORY / "surface.py").exists()
    assert [path.name for path in sorted(_MEMORY.glob("*.py")) if "seams" in path.read_text()] == []


def test_no_test_patches_the_memory_package() -> None:
    through_package = [
        f"{where} {target}"
        for where, target in patch_targets(setattr_objects=True)
        if _patched_owner(where, target) is memory_package
    ]
    assert through_package == [], "patch the module that defines the name"


def test_a_patch_of_the_defining_module_reaches_package_callers() -> None:
    stand_in = object()
    with patch("app.modules.memory.retrieval.get_memory_block", stand_in):
        assert memory_package.get_memory_block is stand_in
    assert memory_package.get_memory_block is not stand_in


def test_the_guard_sees_a_patch_of_the_package() -> None:
    assert _patched_owner("architecture/test_memory_package.py:1", "app.modules.memory.x") is (
        memory_package
    )
    # ``memory_package`` is this file's own import of the package.
    assert _patched_owner("architecture/test_memory_package.py:1", "memory_package.x") is (
        memory_package
    )
