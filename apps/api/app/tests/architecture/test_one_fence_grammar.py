"""Code fences are read with one grammar (``services/md_fence_scan.py``), not by hand.

Three grammars and about nineteen ad-hoc readers disagreed: backtick-only checks let
any run close any fence, a regex closed a fence on the first ``` anywhere, and line
loops toggled a flag on every ``` line, so a ``` shown inside a ~~~ block turned the
rest of the reply inside out (code-health audit DUP-03). A reader of a reply reads
markers with ``read_fence_marker`` or walks ``iter_fences`` / ``line_fences``; this
fails on a fence tested with ``startswith``, located with ``find`` or matched with a
regex anywhere else.
"""

from __future__ import annotations

import ast

import pytest

from .boundary_support import APP_ROOT

_OWNER = APP_ROOT / "services" / "md_fence_scan.py"
_USER_CUE = "reads the user's message, where a fence anywhere is a cue, not a block"
# path under app/ -> why it may read a fence by hand.
_ALLOWED = {
    "gateways/model_output.py": (
        "a whole model reply wrapped in one ```json fence, read before any markdown scan"
    ),
    "modules/turn_reading/coding.py": (
        "the user's message: a closer glued to the last code line still ends the code, "
        "so the question after it is read"
    ),
    "modules/turn_reading/chart.py": _USER_CUE,
    "modules/turn_reading/diagrams.py": _USER_CUE,
    "modules/turn_reading/teaching.py": _USER_CUE,
    "modules/turn_reading/visuals.py": _USER_CUE,
    "modules/web_search/patterns.py": _USER_CUE,
    "modules/chat/model_routing/route.py": (
        "the user's message: a ``` opening a line is code, ```print(1)``` on one line too"
    ),
}
_RUNS = ("```", "~~~", "`{3", "~{3")
_LOCATORS = {"startswith", "endswith", "find", "rfind", "index", "rindex"}
_REGEX_CALLS = {
    "compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split",
}  # fmt: skip


def _literal(node: ast.expr) -> str:
    """A string literal's text; an f-string's literal parts."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    return ""


def _hand_reads(source: str) -> list[int]:
    """Lines that test, locate or match a ``` or ~~~ run by hand."""
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if not node.args:
            continue
        text = _literal(node.args[0])
        name = node.func.attr
        if name in _LOCATORS and text[:3] in {"```", "~~~"}:
            found.append(node.lineno)
        elif (
            name in _REGEX_CALLS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re"
            and any(run in text for run in _RUNS)
        ):
            found.append(node.lineno)
    return found


@pytest.mark.parametrize(
    "source",
    [
        'if line.strip().startswith("```"):\n    pass\n',
        'at = text.rfind(f"```{lang}")\n',
        'FENCE = re.compile(r"^\\s*(?:`{3,}|~{3,})")\n',
        'body = re.sub(r"```json\\n(.*?)```", "", text)\n',
    ],
)
def test_the_guard_sees_a_hand_written_fence_read(source: str) -> None:
    assert _hand_reads(source) == [1]


def test_the_guard_leaves_other_text_alone() -> None:
    assert _hand_reads('if "```places" in text:\n    x = re.compile(r"\\d+")\n') == []


def test_no_production_code_reads_fences_by_hand() -> None:
    found = [
        f"{relative}:{line}"
        for path in sorted(APP_ROOT.rglob("*.py"))
        if "tests" not in (relative_path := path.relative_to(APP_ROOT)).parts
        and path != _OWNER
        and (relative := str(relative_path)) not in _ALLOWED
        for line in _hand_reads(path.read_text())
    ]
    assert not found, "Read fences with services/md_fence_scan:\n" + "\n".join(found)


def test_every_allowance_still_applies() -> None:
    stale = [path for path in _ALLOWED if not _hand_reads((APP_ROOT / path).read_text())]
    assert not stale, f"Remove allowances that no longer match: {stale}"
