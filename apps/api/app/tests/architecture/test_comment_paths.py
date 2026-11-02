"""Comments name files that exist, and say why rather than what changed (audit CLAR-13).

Sixteen comments named deleted files: the camera-caption contract pointed at a module
gone since the math move, and the dev-auth security pointer at a retired router. And
nineteen ``BUG FIX:`` notes narrated history ("used to", "the most severe bug found"),
which ages into wrong claims. A path in an API or phone comment must name a file in
the repo (a bare name, any file of that name), and production comments give the reason
in the present tense.
"""

from __future__ import annotations

import ast
import io
import os
import re
import tokenize
from functools import cache
from pathlib import Path

from .boundary_support import APP_ROOT, MOBILE_ROOT

_REPO = APP_ROOT.parents[2]
_SKIP_DIRS = frozenset(
    {".git", "node_modules", "__pycache__", ".venv", "tmp", "ios", "android", ".expo", "dist"}
)
_PATH = re.compile(r"(?<![\w/.:-])((?:[\w-]+/)*[\w.-]+\.(?:py|tsx?|json|md|toml))(?![\w/])")


@cache
def _repo_files() -> tuple[frozenset[str], frozenset[str]]:
    """Every file's repo path, and every file name."""
    paths: set[str] = set()
    for folder, dirs, files in os.walk(_REPO):
        dirs[:] = [name for name in dirs if name not in _SKIP_DIRS]
        base = Path(folder).relative_to(_REPO).as_posix()
        paths.update(f"{base}/{name}" if base != "." else name for name in files)
    return frozenset(paths), frozenset(path.rsplit("/", 1)[-1] for path in paths)


def _exists(token: str) -> bool:
    paths, names = _repo_files()
    if "/" not in token:
        return token in names
    return any(path == token or path.endswith(f"/{token}") for path in paths)


def _python_comments(source: str) -> list[tuple[int, str]]:
    found = [
        (token.start[0], token.string)
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            doc = ast.get_docstring(node, clean=False)
            if doc and node.body:
                found.append((node.body[0].lineno, doc))
    return found


def _script_comments(source: str) -> list[tuple[int, str]]:
    return [
        (source.count("\n", 0, match.start()) + 1, match.group(0))
        for match in re.finditer(r"//[^\n]*|/\*.*?\*/", source, flags=re.S)
    ]


def _comments() -> list[tuple[str, int, str]]:
    """``(file, line, text)`` for every production comment and docstring."""
    out: list[tuple[str, int, str]] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if "tests" in path.relative_to(APP_ROOT).parts:
            continue
        name = path.relative_to(_REPO).as_posix()
        out += [(name, line, text) for line, text in _python_comments(path.read_text())]
    for folder, dirs, files in os.walk(MOBILE_ROOT):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS | {"__tests__", "vendor"}]
        for file in files:
            if file.endswith((".ts", ".tsx")):
                path = Path(folder) / file
                name = path.relative_to(_REPO).as_posix()
                out += [(name, line, text) for line, text in _script_comments(path.read_text())]
    return out


def test_comments_name_files_that_exist() -> None:
    stale = [
        f"{name}:{line}: {match.group(1)}"
        for name, line, text in _comments()
        for match in _PATH.finditer(text)
        if "://" not in text[max(0, match.start() - 12) : match.start()]
        and not _exists(match.group(1))
    ]
    assert stale == [], "point the comment at the file's new home"


def test_production_comments_give_reasons_not_history() -> None:
    notes = [f"{name}:{line}" for name, line, text in _comments() if "BUG FIX" in text]
    assert notes == [], "say why the code is this way, in the present tense"


def test_the_path_check_reads_both_sides() -> None:
    assert _exists("services/subject_scan.py") and _exists("subject_scan.py")
    assert not _exists("services/math_image_extract.py")
    # A URL's path is not a repo path.
    found = [m.group(1) for m in _PATH.finditer("see routers/auth.py and https://x.dev/a.md")]
    assert found == ["routers/auth.py"]
