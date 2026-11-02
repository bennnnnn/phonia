#!/usr/bin/env python3
"""Delete remote branches whose pull requests are already merged.

A rebase merge leaves the old head on the remote, and GitHub then offers
Compare & pull request. This removes a head only when its patch is already
on main and no open pull request points at it. Unique work stays put.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROTECTED = {"main", "master", "HEAD"}


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


def safe_branch(name: str) -> bool:
    if name in PROTECTED or not name:
        return False
    if name.startswith("-") or ":" in name or ".." in name or " " in name:
        return False
    return True


def deletion_plan(
    branches: list[str],
    open_heads: set[str],
    merged_heads: set[str],
    closed_heads: set[str],
    ancestors: set[str],
    unique: set[str],
) -> tuple[list[str], list[str]]:
    """Return branches to delete, and merged heads that still have unique work."""
    delete: list[str] = []
    leftover: list[str] = []
    for name in branches:
        if not safe_branch(name) or name in open_heads:
            continue
        finished = name in merged_heads or name in closed_heads or name in ancestors
        if not finished:
            continue
        if name in unique:
            if name in merged_heads or name in closed_heads:
                leftover.append(name)
            continue
        delete.append(name)
    return delete, leftover


def local_deletion_plan(
    branches: list[str],
    current: str | None,
    open_heads: set[str],
    landed: set[str],
) -> list[str]:
    """Local names whose patches are already on main. Never the checked-out branch."""
    delete: list[str] = []
    for name in branches:
        if not safe_branch(name) or name == current or name in open_heads:
            continue
        if name in landed:
            delete.append(name)
    return delete


def pr_heads(root: Path, state: str) -> set[str] | None:
    result = run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            state,
            "--limit",
            "40",
            "--json",
            "headRefName",
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
    names: set[str] = set()
    for item in payload:
        if isinstance(item, dict):
            name = str(item.get("headRefName") or "")
            if safe_branch(name):
                names.add(name)
    return names


def remote_branches(root: Path) -> list[str]:
    result = run(
        ["git", "for-each-ref", "--format=%(refname:strip=3)", "refs/remotes/origin"],
        root,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def has_unique_work(root: Path, branch: str) -> bool | None:
    """True when origin/branch has a patch that is not on origin/main."""
    result = run(["git", "cherry", "origin/main", f"origin/{branch}"], root, timeout=20)
    if result.returncode != 0:
        return None
    return any(line.startswith("+") for line in result.stdout.splitlines())


def is_ancestor(root: Path, branch: str) -> bool:
    result = run(
        ["git", "merge-base", "--is-ancestor", f"origin/{branch}", "origin/main"],
        root,
    )
    return result.returncode == 0


def delete_remote(root: Path, branch: str) -> bool:
    result = run(["git", "push", "origin", "--delete", branch], root, timeout=20)
    return result.returncode == 0


def local_branches(root: Path) -> list[str]:
    result = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], root)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def current_branch(root: Path) -> str | None:
    result = run(["git", "branch", "--show-current"], root)
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    return name or None


def main_subjects(root: Path) -> set[str] | None:
    result = run(["git", "log", "origin/main", "--format=%s"], root, timeout=20)
    if result.returncode != 0:
        return None
    return set(result.stdout.splitlines())


def patch_landed(root: Path, branch: str, subjects: set[str]) -> bool:
    """True when every patch on the local branch already has the same subject on main."""
    result = run(["git", "cherry", "origin/main", branch], root, timeout=20)
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        if not line.startswith("+"):
            continue
        parts = line.split()
        if len(parts) < 2:
            return False
        shown = run(["git", "log", "-1", "--format=%s", parts[1]], root)
        if shown.returncode != 0 or shown.stdout.strip() not in subjects:
            return False
    return True


def delete_local(root: Path, branch: str) -> bool:
    result = run(["git", "branch", "-D", branch], root)
    return result.returncode == 0


def sweep(root: Path) -> str | None:
    run(["git", "fetch", "origin", "--prune"], root, timeout=25)
    open_heads = pr_heads(root, "open")
    merged_heads = pr_heads(root, "merged")
    closed_heads = pr_heads(root, "closed")
    if open_heads is None or merged_heads is None or closed_heads is None:
        return None
    branches = [name for name in remote_branches(root) if safe_branch(name)]
    ancestors: set[str] = set()
    unique: set[str] = set()
    for name in branches:
        if name in open_heads:
            continue
        if is_ancestor(root, name):
            ancestors.add(name)
            continue
        unique_work = has_unique_work(root, name)
        if unique_work is None:
            continue
        if unique_work:
            unique.add(name)
    delete, leftover = deletion_plan(
        branches,
        open_heads,
        merged_heads,
        closed_heads,
        ancestors,
        unique,
    )
    failed: list[str] = []
    for name in delete:
        if not delete_remote(root, name):
            failed.append(name)
    subjects = main_subjects(root)
    if subjects is not None:
        current = current_branch(root)
        local = [name for name in local_branches(root) if safe_branch(name)]
        landed = {
            name
            for name in local
            if name != current and name not in open_heads and patch_landed(root, name, subjects)
        }
        for name in local_deletion_plan(local, current, open_heads, landed):
            delete_local(root, name)
    if not leftover and not failed:
        return None
    lines: list[str] = []
    if leftover:
        listed = ", ".join(leftover)
        lines.append(
            "These merged or closed branches still have work that is not on "
            f"main: {listed}. Cherry-pick that work onto a new branch from "
            "origin/main, open one pull request, then delete the old branch. "
            "Do not push to a merged or closed head."
        )
    if failed:
        listed = ", ".join(failed)
        lines.append(f"These merged branches could not be deleted: {listed}.")
    return " ".join(lines)


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
        message = sweep(repo_root(cwd))
    except (subprocess.TimeoutExpired, OSError):
        print("{}")
        return
    if message is None:
        print("{}")
        return
    print(json.dumps({"followup_message": message}))


if __name__ == "__main__":
    main()
