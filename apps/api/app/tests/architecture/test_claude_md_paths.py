"""The paths CLAUDE.md's domain catalog and seams name exist (code-health audit ARCH-12).

CLAUDE.md is the map people and agents follow, and seven of its homes were wrong: the
model catalog under ``services/``, ``chat_history_rag.py``, legacy domains in
``services/``, a ``lib/todos`` the boundary test forbids. Its two tables now name only
files and folders that exist. A name in a cell may be relative to a folder the same cell
names first (``modules/chat/`` then ``ws_api.py``).
"""

from __future__ import annotations

import os
import re
from functools import cache
from pathlib import Path

from .boundary_support import APP_ROOT

_REPO = APP_ROOT.parents[2]
_ROOTS = (_REPO, APP_ROOT, _REPO / "apps" / "mobile", APP_ROOT.parent)
_SUFFIXES = (".py", ".ts", ".tsx", ".md", ".json", ".mdc", ".toml", ".sh", ".js")
_TABLES = ("## Domain catalog", "## Seams")
_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "tmp"})


def _table_rows(text: str, heading: str) -> list[str]:
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    return [line for line in section.splitlines() if line.startswith("|")]


def _is_path(token: str) -> bool:
    if any(mark in token for mark in " <>{}*") or token.startswith("/") or "→" in token:
        return False
    return "/" in token or token.endswith(_SUFFIXES)


@cache
def _file_names() -> frozenset[str]:
    """Every file name in the repo's code, for a bare name that names a kind of file."""
    names: set[str] = set()
    for _folder, dirs, files in os.walk(_REPO):
        dirs[:] = [name for name in dirs if name not in _SKIP_DIRS]
        names.update(files)
    return frozenset(names)


def _unresolved(cell: str) -> list[str]:
    """Paths in one cell that exist nowhere.

    A bare file name is relative to a folder the cell named before it (``routers/admin.py``,
    ``legal.py``); with none it names a kind of file (module ``api.py``), and some file
    must have that name.
    """
    bases: list[Path] = []
    missing: list[str] = []
    for token in re.findall(r"`([^`]+)`", cell):
        if not _is_path(token):
            continue
        bare = "/" not in token.rstrip("/") and not bases
        if bare and not any((root / token).exists() for root in _ROOTS):
            if token not in _file_names():
                missing.append(token)
            continue
        found = next((base / token for base in (*bases, *_ROOTS) if (base / token).exists()), None)
        if found is None:
            missing.append(token)
        else:
            bases.append(found if found.is_dir() else found.parent)
    return missing


def test_the_catalog_and_seams_name_paths_that_exist() -> None:
    text = (_REPO / "CLAUDE.md").read_text()
    missing = [
        f"{heading}: {token}"
        for heading in _TABLES
        for row in _table_rows(text, heading)
        for cell in row.split("|")
        for token in _unresolved(cell)
    ]
    assert missing == []


def test_the_check_reads_cells_as_the_tables_write_them() -> None:
    assert _unresolved("`modules/chat/` (`ws_api.py`, `post_turn.py`)") == []
    assert _unresolved("`routers/admin.py`, `legal.py`, `health.py`") == []
    assert _unresolved("`modules/chat/` (`chat_history_rag.py`)") == ["chat_history_rag.py"]
    assert _unresolved("`chat_history_rag.py`, `message_chunks`") == ["chat_history_rag.py"]
    assert _unresolved("module `api.py`; `services/model_catalog.py`; `/chats`; `free-chat`") == [
        "services/model_catalog.py"
    ]
