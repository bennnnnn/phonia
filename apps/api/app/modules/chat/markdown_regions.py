"""Copy fenced regions byte-for-byte while rewriting the prose between them.

The phone's twin is apps/mobile/lib/markdown/markdownRegions.ts.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.chat.inline_code import read_inline_code_span
from app.services.md_fence_scan import FenceMarker, read_fence_marker

# Restaurant price tiers, ($) to ($$$$), are not maths.
PRICE_TIER = re.compile(r"\(\s*\$+\s*\)")


def rewrite_fenced(
    text: str,
    rewrite_prose: Callable[[str], str],
    rewrite_fence: Callable[[str, str, str], str | None],
) -> str:
    """Rewrite prose, and replace a fence when ``rewrite_fence`` returns text.

    ``rewrite_fence`` receives the opener line, the body, and the closer line.
    ``None`` keeps that fence byte-for-byte. An unclosed fence stays raw.
    """
    if not text:
        return rewrite_prose(text)
    lines = text.split("\n")
    out: list[str] = []
    prose: list[str] = []
    open_fence: FenceMarker | None = None
    opener_line = ""
    body: list[str] = []

    def flush() -> None:
        if not prose:
            return
        out.append(rewrite_prose("\n".join(prose)))
        prose.clear()

    for line in lines:
        marker = read_fence_marker(line)
        if open_fence is not None:
            if marker is not None and marker.closes(open_fence):
                replacement = rewrite_fence(opener_line, "\n".join(body), line)
                if replacement is None:
                    out.append(opener_line)
                    out.extend(body)
                    out.append(line)
                else:
                    out.append(replacement)
                open_fence = None
                body = []
            else:
                body.append(line)
            continue
        if marker is not None and "|" not in marker.info:
            flush()
            open_fence = marker
            opener_line = line
            continue
        prose.append(line)
    flush()
    if open_fence is not None:
        out.append(opener_line)
        out.extend(body)
    return "\n".join(out)


def map_prose_outside_fences(text: str, rewrite: Callable[[str], str]) -> str:
    """Apply ``rewrite`` to prose only. Fence openers, bodies, and closers stay intact."""
    if not text:
        return rewrite(text)
    lines = text.split("\n")
    out: list[str] = []
    prose: list[str] = []
    open_fence: FenceMarker | None = None

    def flush() -> None:
        if not prose:
            return
        out.append(rewrite("\n".join(prose)))
        prose.clear()

    for line in lines:
        marker = read_fence_marker(line)
        if open_fence is not None:
            out.append(line)
            if marker is not None and marker.closes(open_fence):
                open_fence = None
            continue
        # `` ``` | ```java `` is a broken table cell, not a fence opener.
        if marker is not None and "|" not in marker.info:
            flush()
            out.append(line)
            open_fence = marker
            continue
        prose.append(line)
    flush()
    return "\n".join(out)


def leave_prose_line(line: str) -> bool:
    """Indented code and blockquotes keep their source spacing."""
    stripped = line.lstrip(" ")
    if line.startswith("    ") or line.startswith("\t"):
        return True
    return stripped.startswith(">")


def display_math_lines(lines: list[str]) -> list[bool]:
    """Which lines belong to a display formula left open across lines.

    A ``$$`` or ``\\[`` that a line leaves open makes every line up to its closer
    one formula, which the phone draws as one maths block: none of them is a
    prose line to lay out. Inline code and price tiers hold no maths.
    """
    marks: list[bool] = []
    closer: str | None = None
    for line in lines:
        after = _display_closer(PRICE_TIER.sub("", line), closer)
        marks.append(closer is not None or after is not None)
        closer = after
    return marks


def _display_closer(line: str, closer: str | None) -> str | None:
    """The display closer (``$$`` or ``\\]``) still awaited after ``line``."""
    if "$" not in line and "\\" not in line:
        # Nothing here opens or closes one (a code span only moves the scan along).
        return closer
    index = 0
    # The backslashes just before ``index``, counted as the scan passes them: an odd run
    # escapes the character there (``escaped_at``, which counted back from every index and
    # was quadratic in a run of backslashes).
    slashes = 0
    while index < len(line):
        code_end = read_inline_code_span(line, index) if closer is None else None
        if code_end is not None:
            index, slashes = code_end, 0
        elif slashes % 2 == 0 and line.startswith("$$", index):
            if closer in (None, "$$"):
                closer = "$$" if closer is None else None
            index, slashes = index + 2, 0
        elif slashes % 2 == 0 and line.startswith("\\[", index) and closer is None:
            closer = "\\]"
            index, slashes = index + 2, 0
        elif slashes % 2 == 0 and line.startswith("\\]", index) and closer == "\\]":
            closer = None
            index, slashes = index + 2, 0
        else:
            slashes = slashes + 1 if line[index] == "\\" else 0
            index += 1
    return closer
