#!/usr/bin/env python3
"""Refuse to end a turn while an open pull request conflicts with main.

GitHub then says the branch has conflicts that must be resolved. The user
should not have to paste that message.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run(args: list[str], cwd: Path, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def repo_root(cwd: Path) -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], cwd)
    if result.returncode != 0 or not result.stdout.strip():
        return cwd
    return Path(result.stdout.strip())


def open_pulls(root: Path) -> list[dict[str, object]] | None:
    result = run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "50",
            "--json",
            "number,headRefName,mergeable",
        ],
        root,
        timeout=20,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    return [item for item in payload if isinstance(item, dict)]


def conflict_files(root: Path, branch: str) -> list[str] | None:
    """Files that conflict with origin/main. None when the branch is not local."""
    ref = f"refs/remotes/origin/{branch}"
    if run(["git", "rev-parse", "--verify", "--quiet", ref], root).returncode != 0:
        return None
    result = run(
        ["git", "merge-tree", "--write-tree", "--name-only", "origin/main", f"origin/{branch}"],
        root,
        timeout=20,
    )
    if result.returncode == 0:
        return []
    files: list[str] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        marker = "Merge conflict in "
        if marker not in line:
            continue
        path = line.split(marker, 1)[1].strip()
        if path and path not in seen:
            seen.add(path)
            files.append(path)
    return files or ["unparsed conflict"]


def conflicting(root: Path) -> list[str]:
    run(["git", "fetch", "origin", "--prune"], root, timeout=25)
    pulls = open_pulls(root)
    if not pulls:
        return []
    lines: list[str] = []
    for item in pulls:
        name = str(item.get("headRefName") or "")
        number = item.get("number")
        if not name or ":" in name or name in {"main", "master"}:
            continue
        files = conflict_files(root, name)
        if files is None and item.get("mergeable") == "CONFLICTING":
            files = ["GitHub reports a conflict; the branch ref is not fetched"]
        if not files:
            continue
        listed = ", ".join(files)
        lines.append(f"- #{number} {name}: {listed}")
    return lines


def followup(root: Path) -> str | None:
    lines = conflicting(root)
    if not lines:
        return None
    listed = "\n".join(lines)
    return (
        "Open pull requests conflict with origin/main. GitHub will say they "
        "cannot be merged. Resolve every one before you finish, and do not "
        "leave it for the user to report. Do not merge the pull requests.\n"
        f"{listed}\n"
        "Merge origin/main into each branch and push. In .cursor/rules/lessons.mdc "
        "keep the branch lessons first, then the lessons that are only on main. "
        "If GitHub still says the branch cannot be rebased, put that resolved "
        "tree in one commit whose parent is origin/main and update the same "
        "pull request. Do not copy a dependency's source into the repo."
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("{}")
        return
    if not isinstance(payload, dict):
        print("{}")
        return
    status = payload.get("status")
    loop_count = payload.get("loop_count", 0)
    if status != "completed" or not isinstance(loop_count, int) or loop_count > 0:
        print("{}")
        return
    raw_cwd = payload.get("cwd")
    cwd = Path(raw_cwd) if isinstance(raw_cwd, str) and raw_cwd else Path.cwd()
    try:
        message = followup(repo_root(cwd))
    except (subprocess.TimeoutExpired, OSError):
        print("{}")
        return
    if message is None:
        print("{}")
        return
    print(json.dumps({"followup_message": message}))


if __name__ == "__main__":
    main()
