#!/usr/bin/env python3
"""File-size ratchet for production code (docs/ENGINEERING_STANDARDS.md).

A production file may run to 500 lines. A longer one needs an entry in
scripts/file_size_baseline.json saying why, and it may never grow past the size
recorded there. Tests, vendored code and generated files are not counted.

Usage:
  scripts/check_file_sizes.py [api|mobile ...]   check (default: both)
  scripts/check_file_sizes.py --update            after a split: lower recorded sizes and
                                                  drop entries back under the limit or gone
                                                  (it never raises or adds one)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "file_size_baseline.json"
TARGET_LINES = 300
REVIEW_LINES = 500

MOBILE_DIRS = ("app", "components", "contexts", "features", "hooks", "lib", "ui")
# app -> (directories scanned, file suffixes, path parts that mark non-production code)
APPS: dict[str, tuple[tuple[str, ...], tuple[str, ...], frozenset[str]]] = {
    "api": (("apps/api/app",), (".py",), frozenset({"tests", "__pycache__"})),
    "mobile": (
        tuple(f"apps/mobile/{name}" for name in MOBILE_DIRS),
        (".ts", ".tsx"),
        frozenset({"__tests__", "vendor", "node_modules"}),
    ),
}
GENERATED_SUFFIXES = (".d.ts", ".generated.ts")


def production_files(app: str) -> dict[str, int]:
    """Repo-relative path -> line count for every production file of one app."""
    dirs, suffixes, skip_parts = APPS[app]
    sizes: dict[str, int] = {}
    for directory in dirs:
        for path in (ROOT / directory).rglob("*"):
            relative = path.relative_to(ROOT)
            if (
                path.suffix not in suffixes
                or path.name.endswith(GENERATED_SUFFIXES)
                or skip_parts.intersection(relative.parts)
            ):
                continue
            with path.open(encoding="utf-8", errors="replace") as handle:
                sizes[relative.as_posix()] = sum(1 for _ in handle)
    return sizes


def belongs_to(path: str, app: str) -> bool:
    return any(path.startswith(f"{directory}/") for directory in APPS[app][0])


def load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def check(apps: list[str]) -> int:
    recorded: dict[str, dict[str, Any]] = load_baseline()["files"]
    errors: list[str] = []
    shrunk: list[str] = []
    over_target = 0
    for app in apps:
        sizes = production_files(app)
        over_target += sum(1 for lines in sizes.values() if lines > TARGET_LINES)
        for path, lines in sorted(sizes.items()):
            entry = recorded.get(path)
            if entry is None:
                if lines > REVIEW_LINES:
                    errors.append(
                        f"{path}: {lines} lines (limit {REVIEW_LINES}). Split it by "
                        "responsibility, or record a reviewed exception with its reason "
                        "in scripts/file_size_baseline.json."
                    )
            elif lines > entry["lines"]:
                errors.append(
                    f"{path}: grew from {entry['lines']} to {lines} lines. It is over "
                    f"{REVIEW_LINES} and may not grow; put the new code in its own module."
                )
            elif lines < entry["lines"]:
                shrunk.append(f"{path}: {entry['lines']} -> {lines}")
        shrunk += [
            f"{path}: gone"
            for path in recorded
            if belongs_to(path, app) and path not in sizes
        ]

    print(f"File sizes: {over_target} production files over the {TARGET_LINES}-line target.")
    if shrunk:
        print("Smaller than recorded; run scripts/check_file_sizes.py --update to lock it in:")
        print("\n".join(f"  {line}" for line in shrunk))
    for error in errors:
        print(f"ERROR {error}")
    return 1 if errors else 0


def update() -> int:
    document = load_baseline()
    sizes: dict[str, int] = {}
    for app in APPS:
        sizes.update(production_files(app))
    kept = {
        path: {**entry, "lines": min(sizes[path], entry["lines"])}
        for path, entry in document["files"].items()
        if sizes.get(path, 0) > REVIEW_LINES
    }
    print(f"Recorded files over {REVIEW_LINES} lines: {len(document['files'])} -> {len(kept)}.")
    document["files"] = dict(sorted(kept.items()))
    BASELINE.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    if argv == ["--update"]:
        return update()
    if any(arg not in APPS for arg in argv):
        print(__doc__)
        return 2
    return check(argv or list(APPS))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
