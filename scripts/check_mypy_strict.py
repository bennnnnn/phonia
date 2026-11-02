#!/usr/bin/env python3
"""Strict-typing ratchet for the packages that decide replies (docs/STRUCTURE_TICKETS.md ST-02).

`uv run mypy` checks these packages loosely. This runs `mypy --strict` over each one not yet in
the strict overrides of apps/api/pyproject.toml and holds its error count file by file in
scripts/mypy_strict_baseline.json: a new error fails with its file:line, and a file with fewer
errors than recorded fails until the baseline is lowered, so the count only falls. A package
that reaches none fails until it joins the strict overrides, where `uv run mypy` holds it.

A suppression is no fix: each `# type: ignore` in a ratcheted package counts as one error of its
file, and a whole-file escape (`# mypy:` inline settings, a `# type: ignore` on a line of its own,
an `ignore_errors` or `disable_error_code` override in pyproject.toml) fails outright in any reply
package. A renamed or split file is new to the baseline: --update records it while its package's
total does not grow.

Usage (from apps/api, in its virtualenv):
  uv run python ../../scripts/check_mypy_strict.py            check
  uv run python ../../scripts/check_mypy_strict.py --update   after a fix: lower the recorded
                                                              counts (never raises or adds one)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tokenize
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "apps" / "api"
BASELINE = ROOT / "scripts" / "mypy_strict_baseline.json"
# The packages whose code decides what a reply says.
PACKAGES = (
    "app.modules.chat",
    "app.modules.chemistry",
    "app.modules.math",
    "app.modules.money",
    "app.modules.physics",
)
_ERROR = re.compile(r"^(app/[^:]+\.py):(\d+): error: (.*)$")
_IGNORE = re.compile(r"#\s*type:\s*ignore\b")
_INLINE_CONFIG = re.compile(r"#\s*mypy:")
# pyproject keys that switch checking off for a module rather than type it.
_ESCAPES = ("ignore_errors", "disable_error_code")


# What `--strict` turns on that an override can (all but the global warn_redundant_casts): a
# package leaves the ratchet only when an override holds every one of these for the package
# and every module below it. The architecture tests check this against mypy's own list.
STRICT_FLAGS = (
    "disallow_untyped_defs",
    "disallow_incomplete_defs",
    "check_untyped_defs",
    "disallow_untyped_decorators",
    "disallow_any_generics",
    "disallow_subclassing_any",
    "disallow_untyped_calls",
    "warn_return_any",
    "warn_unused_ignores",
    "no_implicit_reexport",
    "strict_equality",
    "extra_checks",
)


def _holds(override: dict[str, object], flag: str) -> bool:
    """``no_implicit_reexport = true`` or its other spelling, ``implicit_reexport = false``."""
    if override.get(flag) is True:
        return True
    return flag.startswith("no_") and override.get(flag.removeprefix("no_")) is False


def strict_packages() -> set[str]:
    """Packages pyproject.toml's strict override already holds (`uv run mypy` checks them).

    The package counts only with its submodules (``pkg.*``) and the whole flag set: listing
    ``app.modules.physics`` alone holds ``physics/__init__.py`` and nothing below it."""
    config = tomllib.loads((API / "pyproject.toml").read_text(encoding="utf-8"))
    named: set[str] = set()
    for override in config["tool"]["mypy"].get("overrides", []):
        if all(_holds(override, flag) for flag in STRICT_FLAGS):
            named.update(_modules(override))
    return {module for module in named if f"{module}.*" in named}


def ratcheted() -> list[str]:
    held = strict_packages()
    return [package for package in PACKAGES if package not in held]


def strict_errors(packages: list[str]) -> dict[str, list[str]]:
    """file -> its strict errors as "file:line: message", for the packages given."""
    if not packages:
        return {}
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--strict",
        # Imported packages are read for their types; only these packages' errors count.
        "--follow-imports=silent",
        # Strict options change every cached result: keep the loose run's cache warm.
        "--cache-dir=.mypy_cache_strict",
        "--no-error-summary",
        *(arg for package in packages for arg in ("-p", package)),
    ]
    # The command is this file's own constants and the virtualenv's python: no input reaches it.
    run = subprocess.run(command, cwd=API, capture_output=True, text=True, check=False)  # noqa: S603
    if run.returncode not in (0, 1):
        output = run.stderr or run.stdout
        raise SystemExit(f"mypy did not finish (exit {run.returncode}):\n{output}")
    found: dict[str, list[str]] = {}
    for line in run.stdout.splitlines():
        match = _ERROR.match(line)
        if match:
            found.setdefault(match[1], []).append(line)
    return found


def package_files(package: str) -> list[Path]:
    return sorted((API / package.replace(".", "/")).rglob("*.py"))


def _comments(path: Path) -> list[tuple[int, str, bool]]:
    """(line, comment, whether the comment is the line's only content) for each comment."""
    found: list[tuple[int, str, bool]] = []
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type == tokenize.COMMENT:
                alone = token.line[: token.start[1]].strip() == ""
                found.append((token.start[0], token.string, alone))
    return found


def measure(packages: list[str]) -> dict[str, list[str]]:
    """file -> what counts against it: its strict errors and each `# type: ignore`."""
    found = strict_errors(packages)
    for package in packages:
        for path in package_files(package):
            relative = path.relative_to(API).as_posix()
            for line, comment, _alone in _comments(path):
                if _IGNORE.search(comment):
                    found.setdefault(relative, []).append(
                        f"{relative}:{line}: suppressed, so counted: {comment}"
                    )
    return found


def bypasses() -> list[str]:
    """Ways a reply package's file stops being checked at all; each fails outright."""
    problems: list[str] = []
    for package in PACKAGES:
        for path in package_files(package):
            relative = path.relative_to(API).as_posix()
            for line, comment, alone in _comments(path):
                if _INLINE_CONFIG.search(comment):
                    problems.append(f"{relative}:{line}: `{comment}` changes mypy for the file")
                elif alone and _IGNORE.search(comment):
                    problems.append(f"{relative}:{line}: a `# type: ignore` alone on its line")
    config = tomllib.loads((API / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mypy"]
    sections = [("[tool.mypy]", config, ["app"])] + [
        (f"override {override.get('module')}", override, _modules(override))
        for override in config.get("overrides", [])
    ]
    for name, section, modules in sections:
        escapes = [key for key in _ESCAPES if section.get(key)]
        reached = [
            module
            for module in modules
            for package in PACKAGES
            if package.startswith(module.rstrip(".*")) or module.startswith(package)
        ]
        if escapes and reached:
            problems.append(f"pyproject.toml {name}: {', '.join(escapes)} reaches {reached[0]}")
    return problems


def _modules(override: dict[str, object]) -> list[str]:
    modules = override.get("module", [])
    if isinstance(modules, str):
        return [modules]
    return [str(module) for module in modules] if isinstance(modules, list) else []


def load_baseline() -> dict[str, int]:
    files: dict[str, int] = json.loads(BASELINE.read_text(encoding="utf-8"))["files"]
    return files


def package_of(path: str) -> str:
    return ".".join(Path(path).parts[:3])


def check() -> int:
    packages = ratcheted()
    found = measure(packages)
    counts = Counter({path: len(lines) for path, lines in found.items()})
    recorded = load_baseline()
    problems = bypasses()
    for path in sorted(set(counts) | set(recorded)):
        now, was = counts[path], recorded.get(path, 0)
        if package_of(path) not in packages:
            continue
        if now > was:
            moved = ""
            if path not in recorded and not _package_grew(package_of(path), counts, recorded):
                moved = (
                    f"\n  If it was renamed or split from a recorded file ({package_of(path)}'s "
                    "total did not grow), run this script with --update to record it."
                )
            problems.append(
                f"{path}: {now} strict type errors, {was} recorded. Type the new code; "
                "the file's errors are:\n    " + "\n    ".join(found[path]) + moved
            )
        elif now < was:
            problems.append(
                f"{path}: {now} strict type errors, {was} recorded. Lock the fix in: "
                "run this script with --update."
            )
    for package in packages:
        if not any(package_of(path) == package for path in counts):
            problems.append(
                f"{package} has no strict type errors: add it (and {package}.*) to the strict "
                "overrides in apps/api/pyproject.toml, then run this script with --update."
            )
    total = sum(counts.values())
    print(f"Strict typing: {total} errors in {len(counts)} files of {', '.join(packages)}.")
    for problem in problems:
        print(f"ERROR {problem}")
    return 1 if problems else 0


def update() -> int:
    packages = ratcheted()
    counts = Counter({path: len(lines) for path, lines in measure(packages).items()})
    recorded = load_baseline()
    kept = {
        path: min(counts[path], was)
        for path, was in recorded.items()
        if counts.get(path) and package_of(path) in packages
    }
    refused: list[str] = []
    for path in sorted(set(counts) - set(recorded)):
        if _package_grew(package_of(path), counts, recorded):
            refused.append(f"{path}: {counts[path]} errors")
        else:
            kept[path] = counts[path]  # a renamed or split file: its package's total held
    if refused:
        print("Not recorded: new errors in a package whose total grew. Type them first:")
        print("\n".join(f"  {line}" for line in refused))
        return 1
    print(f"Recorded files with strict errors: {len(recorded)} -> {len(kept)}.")
    document = json.loads(BASELINE.read_text(encoding="utf-8"))
    document["files"] = dict(sorted(kept.items()))
    BASELINE.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return 0


def _package_grew(package: str, counts: Counter[str], recorded: dict[str, int]) -> bool:
    now = sum(n for path, n in counts.items() if package_of(path) == package)
    was = sum(n for path, n in recorded.items() if package_of(path) == package)
    return now > was


def main(argv: list[str]) -> int:
    if argv == ["--update"]:
        return update()
    if argv:
        print(__doc__)
        return 2
    return check()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
