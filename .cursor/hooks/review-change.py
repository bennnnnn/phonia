#!/usr/bin/env python3
"""After an agent turn, ask for a split or a doc check when the diff needs it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
LINE_CAP = 800
SKIP_PARTS = {"node_modules", "vendor"}


def repo_root() -> Path:
    out = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
    )
    return Path(out.strip())


def paths_from_porcelain(raw: bytes) -> list[str]:
    parts = raw.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    paths: list[str] = []
    index = 0
    while index < len(parts):
        entry = parts[index].decode()
        index += 1
        if len(entry) < 4:
            continue
        status = entry[:2]
        path = entry[3:]
        if "R" in status or "C" in status:
            if index < len(parts):
                path = parts[index].decode()
                index += 1
        if "D" in status:
            continue
        paths.append(path)
    return paths


def changed_paths(root: Path) -> list[str]:
    raw = subprocess.check_output(
        ["git", "status", "--porcelain", "-z"],
        cwd=root,
    )
    return paths_from_porcelain(raw)


def _skipped(path: str) -> bool:
    parts = Path(path).parts
    if any(part in SKIP_PARTS for part in parts):
        return True
    return "alembic/versions" in path.replace("\\", "/")


def is_source(path: str) -> bool:
    if not path.startswith("apps/"):
        return False
    if _skipped(path):
        return False
    return Path(path).suffix in SOURCE_SUFFIXES


def is_doc(path: str) -> bool:
    return Path(path).suffix in {".md", ".mdc"}


def line_count(root: Path, path: str) -> int | None:
    file_path = root / path
    if not file_path.is_file():
        return None
    count = 0
    with file_path.open("rb") as handle:
        for _ in handle:
            count += 1
    return count


def build_followup(
    over: list[tuple[str, int]],
    source_changed: bool,
    docs_changed: bool,
) -> str | None:
    parts: list[str] = []
    if over:
        listed = ", ".join(f"{path} ({count} lines)" for path, count in over)
        parts.append(
            "These changed source files are over 800 lines and must be split "
            f"before you finish: {listed}. Extract hooks, components, or helpers. "
            "Do not add more to them."
        )
    if source_changed and not docs_changed:
        parts.append(
            "Source changed and no markdown or rule file changed with it. "
            "Update only the docs or rules this change made wrong "
            "(CLAUDE.md, FEATURES.md, docs/, .cursor/rules/). "
            "If nothing they say is now false, do not edit them."
        )
    if not parts:
        return None
    return " ".join(parts)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("{}")
        return
    status = payload.get("status")
    loop_count = payload.get("loop_count", 0)
    if status != "completed" or not isinstance(loop_count, int) or loop_count > 0:
        print("{}")
        return
    root = repo_root()
    paths = changed_paths(root)
    source = [path for path in paths if is_source(path)]
    docs_changed = any(is_doc(path) for path in paths)
    over: list[tuple[str, int]] = []
    for path in source:
        count = line_count(root, path)
        if count is not None and count > LINE_CAP:
            over.append((path, count))
    message = build_followup(over, bool(source), docs_changed)
    if message is None:
        print("{}")
        return
    print(json.dumps({"followup_message": message}))


if __name__ == "__main__":
    main()
