"""Code outside ``modules/`` uses a module through its public files too (audit ARCH-01).

The public-surface rule only walked ``modules/``, so 26 imports from routing, the subject
dispatcher, the verified-block types and the schedulers reached 22 internal module files.
A module's public files are ``api``, ``schemas``, ``service`` and ``crud``, and whatever its
``__init__`` names (``_EXPORTS``, ``_MODULE_EXPORTS``, ``__all__``). The composition roots
below wire every module together and may reach any file.
"""

from __future__ import annotations

import ast

from .boundary_support import APP_ROOT, _foreign_module_import_violations

# Root -> what it wires.
_COMPOSITION_ROOTS = {
    "main.py": "mounts every module's HTTP and socket routes",
    "process_bootstrap.py": "starts and stops each module's process-wide pieces",
    "background/handlers.py": "registers each module's jobs with the queue",
    "models/orm/__init__.py": "gathers every module's tables for SQLAlchemy",
    "models/orm/user.py": "the user row's relationships to module tables",
    "services/mcp/__init__.py": "registers each module's model tools",
}


def test_code_outside_modules_imports_modules_only_through_public_files() -> None:
    violations: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        if relative.startswith(("modules/", "tests/")) or relative in _COMPOSITION_ROOTS:
            continue
        tree = ast.parse(path.read_text())
        violations += _foreign_module_import_violations(tree, owner="", label=relative)
    assert violations == []


def test_every_composition_root_still_exists() -> None:
    gone = sorted(name for name in _COMPOSITION_ROOTS if not (APP_ROOT / name).is_file())
    assert not gone, f"take these off the list: {gone}"
