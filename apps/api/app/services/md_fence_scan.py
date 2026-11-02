"""Markdown code fences: the one grammar every reader of a reply uses.

Three grammars and about nineteen ad-hoc readers disagreed (code-health audit DUP-03).
Backtick-only readers let any run of backticks close any fence, and the closer that
runs on every saved reply counted fence lines by parity, so a how-to showing a
```` ``` ```` line inside a ``~~~`` block got a stray fence appended. This reads fences
as CommonMark does: ``` or ~~~, a closer of the opener's character at least as long,
a fence line inside another fence is only its content. ``lenient`` (model text, the
default for the scans) also takes deeper indents and ``>`` quote markers; the region
rewriter reads strictly, as the phone's twin does. Linear: no nested regex runs on
untrusted assistant text.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass


def fence_lang(info: str) -> str:
    """The phone's ``parseFenceLang``: first word, cut at ``{ : [``, lower case."""
    words = info.strip().split()
    if not words:
        return ""
    return re.split(r"[{:\[]", words[0], maxsplit=1)[0].lower()


@dataclass(frozen=True)
class FenceMarker:
    """A fence line: its prefix (indent, quote markers), its run, and its info string."""

    prefix: str
    char: str
    length: int
    info: str

    @property
    def lang(self) -> str:
        return fence_lang(self.info)

    def closes(self, opener: FenceMarker) -> bool:
        """A closer of ``opener``: its character, at least as long, nothing after it."""
        return self.char == opener.char and self.length >= opener.length and not self.info


def read_fence_marker(line: str, *, lenient: bool = False) -> FenceMarker | None:
    """A fence line, or None. Strict: up to three spaces before the run (CommonMark).

    A backtick run's info has no backtick: ```` ```inline``` ```` on one line is code.
    """
    line = line.rstrip("\r")
    index = 0
    if lenient:
        while index < len(line) and line[index] in " \t>":
            index += 1
    else:
        while index < len(line) and index < 3 and line[index] == " ":
            index += 1
    if index >= len(line) or line[index] not in "`~":
        return None
    char = line[index]
    run_end = index
    while run_end < len(line) and line[run_end] == char:
        run_end += 1
    length = run_end - index
    info = line[run_end:].strip()
    if length < 3 or (char == "`" and "`" in info):
        return None
    return FenceMarker(line[:index], char, length, info)


# A line that may be a fence line: its prefix, then three backticks or tildes. Every line
# ``read_fence_marker`` accepts matches, so the scan reads only these lines and the
# pattern passes over prose in C (a whole-reply scan read every line in Python).
_FENCE_LINE = re.compile(r"^[ \t>]*(?:```|~~~)", re.MULTILINE)
_STRICT_FENCE_LINE = re.compile(r"^ {0,3}(?:```|~~~)", re.MULTILINE)


def next_fence_marker(
    text: str, from_index: int, *, lenient: bool = True
) -> tuple[int, int, FenceMarker] | None:
    """The next fence line at or after ``from_index``: (line start, after the line, marker)."""
    candidates = _FENCE_LINE if lenient else _STRICT_FENCE_LINE
    index = from_index
    length = len(text)
    while index < length:
        newline = text.find("\n", index)
        end = length if newline < 0 else newline
        marker = read_fence_marker(text[index:end], lenient=lenient)
        if marker is not None:
            return index, length if newline < 0 else newline + 1, marker
        if newline < 0:
            return None
        candidate = candidates.search(text, newline + 1)
        if candidate is None:
            return None
        index = candidate.start()
    return None


@dataclass(frozen=True)
class Fence:
    """One fence by offsets; an unclosed last fence runs to the end of the text."""

    start: int
    body_start: int
    body_end: int
    end: int
    opener: FenceMarker
    closed: bool

    @property
    def lang(self) -> str:
        return self.opener.lang


def iter_fences(text: str, *, lenient: bool = True) -> Iterator[Fence]:
    """Every fence in order. A fence line inside an open fence is its content.

    Except, in model text, an opener spelled like the open fence's own run with a
    language after it: inside ```graph, a ```python line is the model forgetting the
    closer, so the graph fence ends there unclosed and a new one starts. A different or
    longer run (~~~, ````) is how a reply shows ``` lines, so they stay its content.
    """
    index = 0
    while True:
        found = next_fence_marker(text, index, lenient=lenient)
        if found is None:
            return
        start, body_start, opener = found
        cursor = body_start
        while True:
            closing = next_fence_marker(text, cursor, lenient=lenient)
            if closing is None:
                yield Fence(start, body_start, len(text), len(text), opener, closed=False)
                return
            line_start, after, marker = closing
            if marker.closes(opener):
                yield Fence(start, body_start, line_start, after, opener, closed=True)
                index = after
                break
            if (
                lenient
                and marker.info
                and marker.char == opener.char
                and marker.length == opener.length
            ):
                yield Fence(start, body_start, line_start, line_start, opener, closed=False)
                index = line_start
                break
            cursor = after


def last_fence(text: str) -> Fence | None:
    """The last fence, closed or not."""
    last: Fence | None = None
    for fence in iter_fences(text):
        last = fence
    return last


def block_end(text: str, fence: Fence) -> int:
    """Past the fence's last line, before that line's break."""
    return fence.end - 1 if text[fence.end - 1 : fence.end] == "\n" else fence.end


def without_fences(text: str, replacement: str = "") -> str:
    """The text with every fence, closed or left open, as ``replacement``."""
    pieces: list[str] = []
    cursor = 0
    for fence in iter_fences(text):
        pieces.append(text[cursor : fence.start])
        pieces.append(replacement)
        cursor = fence.end
    pieces.append(text[cursor:])
    return "".join(pieces)


def map_fence_blocks(
    text: str, replace: Callable[[Fence, str], str], *, lang: str | None = None
) -> str:
    """Each closed fence (of ``lang``, when given), opener through closer line, as
    ``replace(fence, body)`` writes it. The closer's newline stays, as a regex over the
    block left it.
    """
    pieces: list[str] = []
    cursor = 0
    for fence in iter_fences(text):
        if not fence.closed or (lang is not None and fence.lang != lang.lower()):
            continue
        pieces.append(text[cursor : fence.start])
        pieces.append(replace(fence, text[fence.body_start : fence.body_end]))
        cursor = block_end(text, fence)
    pieces.append(text[cursor:])
    return "".join(pieces)


def iter_closed_fences(text: str, lang: str) -> Iterator[tuple[int, int, str]]:
    """(start, end, body) of each closed ``lang`` fence, in order."""
    wanted = lang.lower()
    for fence in iter_fences(text):
        if fence.closed and fence.lang == wanted:
            yield fence.start, fence.end, text[fence.body_start : fence.body_end]


def replace_first_closed_fence_body(text: str, lang: str, new_body: str) -> str | None:
    """Replace the inner body of the first closed ```lang fence. Keep opener/closer."""
    wanted = lang.lower()
    hit = next((f for f in iter_fences(text) if f.closed and f.lang == wanted), None)
    if hit is None:
        return None
    body = new_body.rstrip("\n") + "\n"
    return text[: hit.body_start] + body + text[hit.body_end :]


def has_closed_fence(text: str, lang: str) -> bool:
    return next(iter_closed_fences(text, lang), None) is not None


def map_closed_fences(
    text: str,
    lang: str,
    replace: Callable[[str], str],
    *,
    max_count: int | None = None,
    leftover: Callable[[str], str] | None = None,
) -> str:
    """Rewrite closed ```lang fences. Linear scan.

    ``max_count`` limits how many fences ``replace`` sees. Further closed
    fences of this lang stay as-is unless ``leftover`` is set (then each
    extra fence is rewritten with that callback — used to fail-closed
    geometry/graph JSON beyond the per-kind cap).
    """
    pieces: list[str] = []
    cursor = 0
    count = 0
    for start, end, body in iter_closed_fences(text, lang):
        over_cap = max_count is not None and count >= max_count
        if over_cap:
            if leftover is None:
                break
            pieces.append(text[cursor:start])
            pieces.append(leftover(body))
        else:
            pieces.append(text[cursor:start])
            pieces.append(replace(body))
            count += 1
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def strip_closed_fences(text: str, lang: str) -> str:
    return map_closed_fences(text, lang, lambda _body: "")


_TABLE_HEAD_HINTS = ("point", "plot", "sketch", "table")


def _is_pipe_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2


def _is_gfm_sep_row(line: str) -> bool:
    """``|---|---|`` / ``|:---:|`` — not a data row."""
    s = line.strip()
    if not s.startswith("|") or s.count("|") < 2:
        return False
    i = 0
    n = len(s)
    saw_cell = False
    while i < n:
        if s[i] != "|":
            i += 1
            continue
        i += 1
        start = i
        while i < n and s[i] != "|":
            i += 1
        cell = s[start:i].strip()
        if not cell:
            continue
        for ch in cell:
            if ch not in "-:":
                return False
        if "-" not in cell:
            return False
        saw_cell = True
    return saw_cell


def line_fences(text: str) -> list[Fence | None]:
    """For each line of ``text.split("\\n")``, the fence holding it (opener and closer
    lines included), or None for prose. Line loops read this instead of toggling a
    flag on every ``` line, which a ``` shown inside a ~~~ block turned inside out."""
    starts = [0]
    newline = text.find("\n")
    while newline >= 0:
        starts.append(newline + 1)
        newline = text.find("\n", newline + 1)
    owners: list[Fence | None] = [None] * len(starts)
    fences = iter(iter_fences(text))
    fence = next(fences, None)
    for line, start in enumerate(starts):
        while fence is not None and start >= max(fence.end, fence.start + 1):
            fence = next(fences, None)
        if fence is not None and fence.start <= start < max(fence.end, fence.start + 1):
            owners[line] = fence
    return owners


def _fenced_lines(text: str) -> set[int]:
    """Indexes of the lines a fence holds, its opener and closer included."""
    return {line for line, fence in enumerate(line_fences(text)) if fence is not None}


def strip_gfm_pipe_tables(text: str) -> str:
    """Drop GFM pipe tables in prose (not inside fences).

    Verified-graph turns still dump an xy sample table; the plot is the
    figure, and ``$x$`` / a lone ``1`` cell also mis-render on mobile.
    """
    lines = text.split("\n")
    n = len(lines)
    fenced = _fenced_lines(text)
    out: list[str] = []
    i = 0
    while i < n:
        if i in fenced:
            out.append(lines[i])
            i += 1
            continue
        if (
            i + 1 < n
            and i + 1 not in fenced
            and _is_pipe_row(lines[i])
            and _is_gfm_sep_row(lines[i + 1])
        ):
            if out:
                prev = out[-1].strip()
                low = prev.lower()
                if prev.startswith("#") and any(h in low for h in _TABLE_HEAD_HINTS):
                    out.pop()
                    while out and out[-1].strip() == "":
                        out.pop()
            i += 2
            while i < n and _is_pipe_row(lines[i]):
                i += 1
            if i < n and lines[i].strip() == "":
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


_SKETCH_HEADS = (
    "### how to sketch",
    "### how to plot",
    "### sketching steps",
    "### quick sketch",
    "### points to plot",
    "### text-based sketch",
    "### sample points",
    "### mermaid diagram",
)
_SKETCH_PHRASES = (
    "ascii",
    "text-based sketch",
    "text based sketch",
    "mermaid diagram",
    "sketching steps",
    "sketching tips",
)
_KEEP_FENCE_LANGS = frozenset({"graph", "geometry", "answer"})


def _line_start_before(text: str, idx: int) -> int:
    nl = text.rfind("\n", 0, idx)
    return 0 if nl < 0 else nl + 1


def _next_owned_fence(text: str, start: int) -> int | None:
    return next(
        (
            fence.start
            for fence in iter_fences(text)
            if fence.start >= start and fence.lang in _KEEP_FENCE_LANGS
        ),
        None,
    )


def strip_hand_sketch_filler(text: str) -> str:
    """Drop 'how to sketch' / ASCII plot filler before the owned ```graph.

    After a verified plot exists, the model still writes a point table (already
    stripped) or an ASCII sketch in a quote — the same junk as the keypad graph
    screenshot.
    """
    lower = text.lower()
    cut_from: int | None = None
    for head in _SKETCH_HEADS:
        idx = lower.find(head)
        if idx < 0:
            continue
        line = _line_start_before(text, idx)
        if cut_from is None or line < cut_from:
            cut_from = line
    ascii_at = None
    for phrase in _SKETCH_PHRASES:
        idx = lower.find(phrase)
        if idx < 0:
            continue
        if ascii_at is None or idx < ascii_at:
            ascii_at = idx
    if ascii_at is not None:
        line = _line_start_before(text, ascii_at)
        if cut_from is None or line < cut_from:
            cut_from = line
    if cut_from is None:
        return text
    keep = _next_owned_fence(text, cut_from)
    head = text[:cut_from].rstrip()
    if keep is None:
        return head + ("\n" if head else "")
    return head + "\n\n" + text[keep:]


def close_unclosed_fences(text: str) -> str:
    """Close a fence left open (a cancel, a provider failure) with a closer that fits it.

    Fences are tracked open and closed, not counted: a ``` line inside a ~~~ block is
    that block's content, and a four-backtick fence needs four to close.
    """
    last = last_fence(text)
    if last is None or last.closed:
        return text
    return f"{text.rstrip()}\n{last.opener.char * last.opener.length}\n"
