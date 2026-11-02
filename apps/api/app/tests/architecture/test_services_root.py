"""A root ``services/`` file serves two owners, or says why (code-health audit ARCH-03).

CLAUDE.md keeps the ``services/`` root for code that is genuinely cross-cutting, yet ten
root files had one importer, seven of them chat's. A root file that only one owner
imports (a module, a layer such as ``background``, or another root file) belongs in
that owner; one that stays says why here.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from .boundary_support import APP_ROOT

_SERVICES = APP_ROOT / "services"
# Root file -> why it stays with one owner.
_ONE_OWNER = {
    "calendar_facts": "time_context's calendar half, split from it for size",
}


def _owner(path: Path) -> str:
    parts = path.relative_to(APP_ROOT).parts
    if parts[0] == "modules":
        return f"modules.{parts[1]}"
    if parts[0] == "services":
        return f"services.{parts[1] if len(parts) > 2 else path.stem}"
    return parts[0] if len(parts) > 1 else path.stem


def _root_owners() -> dict[str, set[str]]:
    roots = {path.stem for path in _SERVICES.glob("*.py") if path.stem != "__init__"}
    owners: dict[str, set[str]] = {name: set() for name in roots}
    found: dict[str, set[str]] = defaultdict(set)
    for path in APP_ROOT.rglob("*.py"):
        if "tests" in path.relative_to(APP_ROOT).parts:
            continue
        me = _owner(path)
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module == "app.services":
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "app.services."
            ):
                names = [(node.module or "").split(".")[2]]
            elif isinstance(node, ast.Import):
                names = [
                    alias.name.split(".")[2]
                    for alias in node.names
                    if alias.name.startswith("app.services.")
                ]
            for name in names:
                if name in roots and me != f"services.{name}":
                    found[name].add(me)
    for name, importers in found.items():
        owners[name] = importers
    return owners


def test_services_root_files_serve_two_owners() -> None:
    single = {name for name, owners in _root_owners().items() if len(owners) < 2}
    unexplained = sorted(single - set(_ONE_OWNER))
    assert not unexplained, f"move these into their one owner, or say why here: {unexplained}"
    stale = sorted(set(_ONE_OWNER) - single)
    assert not stale, f"these serve two owners now or are gone: {stale}"
