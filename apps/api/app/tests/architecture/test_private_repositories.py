"""A module's repositories stay inside it (code-health audit ARCH-05).

The public-surface check passed while images wrote attachments' rows and notifications
wrote to-dos': attachments' ``service.py`` forwarded thirteen repository functions, and
to-dos exported its ``repository`` and two of its writers. Another module now calls an
operation the owner keeps (``attachments.service.add_server_images``,
``todos.mark_reminder_pushed``), and neither a package surface nor a public file hands
a repository out.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .boundary_support import _PUBLIC_MODULE_TAILS, APP_ROOT

_MODULES = APP_ROOT / "modules"


def _is_repository(name: str) -> bool:
    leaf = name.rsplit(".", 1)[-1]
    return leaf == "repository" or leaf.endswith("_repository")


def _surface(init: Path) -> list[tuple[str, str]]:
    """``(exported name, the file it comes from)`` for each name the initializer declares."""
    entries: list[tuple[str, str]] = []
    for node in ast.parse(init.read_text()).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "_EXPORTS" and isinstance(node.value, ast.Dict):
                for key, value in zip(node.value.keys, node.value.values, strict=True):
                    source = ast.literal_eval(value)
                    module = source[0] if isinstance(source, tuple) else source
                    entries.append((ast.literal_eval(key) if key else "", module))
            elif target.id in {"_MODULE_EXPORTS", "__all__"} and isinstance(
                node.value, ast.List | ast.Tuple
            ):
                entries += [
                    (item.value, item.value)
                    for item in node.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                ]
    return entries


def _forwarded(source: str) -> list[str]:
    """Repository names a public file binds at its top level, to hand them on."""
    tree = ast.parse(source)
    aliases: set[str] = set()
    found: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if _is_repository(alias.name):
                    aliases.add(alias.asname or alias.name)
                elif _is_repository(node.module) and alias.asname == alias.name:
                    found.append(f"re-exports {node.module}.{alias.name}")
        elif isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            used = {name.id for name in ast.walk(node.value) if isinstance(name, ast.Name)}
            if used & aliases:
                found.append(f"binds a repository's name at line {node.lineno}")
    return found


def test_no_package_surface_names_a_repository() -> None:
    exported = [
        f"{init.parent.name}: {name} ({source})"
        for init in sorted(_MODULES.glob("*/__init__.py"))
        for name, source in _surface(init)
        if _is_repository(name) or _is_repository(source)
    ]
    assert exported == [], "export an operation the module keeps, not its repository"


def test_no_public_file_forwards_a_repository() -> None:
    forwarded = [
        f"{path.relative_to(APP_ROOT)} {what}"
        for path in sorted(_MODULES.glob("*/*.py"))
        if path.stem in _PUBLIC_MODULE_TAILS
        for what in _forwarded(path.read_text())
    ]
    assert forwarded == [], "write the operation here instead of handing the repository on"


def test_the_checks_catch_what_they_describe() -> None:
    leaked = (
        "from app.modules.attachments import repository as attachments_repo\n"
        "from app.modules.todos.email_repository import mark_sent as mark_sent\n"
        "get_by_ids = attachments_repo.get_by_ids\n"
        "create = _call_through(attachments_repo, 'create_pending')\n"
    )
    assert len(_forwarded(leaked)) == 3
    kept = (
        "from app.modules.attachments import repository as _repo\n"
        "async def get_by_ids(session, ids, user_id):\n"
        "    return await _repo.get_by_ids(session, ids, user_id)\n"
    )
    assert _forwarded(kept) == []
    assert _is_repository("email_repository")
    assert _is_repository("app.modules.attachments.chunks_repository")
    assert not _is_repository("repository_cleanup_note")
