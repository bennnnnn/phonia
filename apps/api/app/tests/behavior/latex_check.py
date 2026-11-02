"""LaTeX in a finished reply that the phone would show as source.

``docs/fixtures/latex_commands.json`` lists every command the phone draws: inline
maths by its native renderer, display maths by MathJax. The phone's
``lib/math/__tests__/latexCoverage.test.ts`` writes the file and renders every
entry both ways. A reply may use only those commands, and only inside maths
(``$...$``, ``$$...$$``, ``\\(...\\)``, ``\\[...\\]``, or a ``math`` or
``answer`` fence): TeX in prose reaches the screen as written. Other fences hold
code or a picture's JSON, not TeX a reader sees.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[5] / "docs" / "fixtures" / "latex_commands.json"

_FENCE = re.compile(r"^(`{3,}|~{3,})([^\n]*)\n(.*?)^\1[ \t]*$", re.DOTALL | re.MULTILINE)
_MATH_FENCES = {"math", "latex", "tex", "answer"}
_SPAN = re.compile(
    r"\$\$(.+?)\$\$|\\\((.+?)\\\)|\\\[(.+?)\\\]|(?<![\\$])\$(?!\$)([^$\n]+?)(?<!\\)\$",
    re.DOTALL,
)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_TEX_IN_PROSE = re.compile(r"\\[A-Za-z]+|[\^_]\{")
_COMMAND = re.compile(r"\\([A-Za-z]+)")


@cache
def drawn_commands() -> frozenset[str]:
    """Every command name the phone draws."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return frozenset([*data["symbols"], *data["operators"], *data["commands"]])


def _maths_and_prose(reply: str) -> tuple[list[str], list[str]]:
    maths: list[str] = []
    prose: list[str] = []
    last = 0
    for fence in _FENCE.finditer(reply):
        prose.append(reply[last : fence.start()])
        last = fence.end()
        if fence.group(2).strip().lower() in _MATH_FENCES:
            maths.append(fence.group(3))
    prose.append(reply[last:])

    def take(span: re.Match[str]) -> str:
        maths.append(next(group for group in span.groups() if group is not None))
        return " "

    return maths, [_SPAN.sub(take, _INLINE_CODE.sub("", part)) for part in prose]


def latex_problems(reply: str) -> list[str]:
    """Each command the phone cannot draw, and each piece of TeX outside maths."""
    maths, prose = _maths_and_prose(reply)
    drawn = drawn_commands()
    problems = [
        f"the phone draws no \\{name}"
        for body in maths
        for name in _COMMAND.findall(body)
        if name not in drawn
    ]
    problems += [
        f"TeX outside maths: {tex}" for part in prose for tex in _TEX_IN_PROSE.findall(part)
    ]
    return problems
