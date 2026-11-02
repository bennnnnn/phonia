"""CommonMark inline code spans, as markdown-it reads them.

A code span binds tighter than anything else on the line: the phone's
markdown-it cuts it out before any ``$...$`` maths is read. Every
string-level pass that pairs dollars must agree, or it pairs a ``$`` with a
dollar on the far side of a code span and rewrites the code between them.
Mirrors apps/mobile/lib/markdown/inlineCode.ts.
"""

from __future__ import annotations


def escaped_at(text: str, at: int) -> bool:
    """True when an odd run of backslashes escapes ``text[at]``."""
    slashes = 0
    index = at - 1
    while index >= 0 and text[index] == "\\":
        slashes += 1
        index -= 1
    return slashes % 2 == 1


def _paragraph_end(text: str, start: int) -> int:
    """Start of the first blank line after ``start``: a code span ends there."""
    newline = text.find("\n", start)
    while newline >= 0:
        following = newline + 1
        while following < len(text) and text[following] in " \t":
            following += 1
        if following < len(text) and text[following] == "\n":
            return newline
        newline = text.find("\n", newline + 1)
    return len(text)


def read_inline_code_span(text: str, start: int) -> int | None:
    """End (exclusive) of the complete code span whose backtick run starts at ``start``."""
    if start >= len(text) or text[start] != "`":
        return None
    if (start > 0 and text[start - 1] == "`") or escaped_at(text, start):
        return None
    opener_end = start + 1
    while opener_end < len(text) and text[opener_end] == "`":
        opener_end += 1
    length = opener_end - start
    stop = _paragraph_end(text, opener_end)
    tick = text.find("`", opener_end)
    while 0 <= tick < stop:
        run_end = tick + 1
        while run_end < len(text) and text[run_end] == "`":
            run_end += 1
        if run_end - tick == length:
            return run_end
        tick = text.find("`", run_end)
    return None


def code_span_opens_within(text: str, start: int, stop: int) -> bool:
    """True when a complete code span opens anywhere in ``[start, stop)``."""
    tick = text.find("`", start)
    while 0 <= tick < stop:
        if read_inline_code_span(text, tick) is not None:
            return True
        tick = text.find("`", tick + 1)
    return False


def is_bare_number(body: str, following: str) -> bool:
    """``$2$`` is one number; "$5 and $10" are two prices and "$5$10" is not one."""
    stripped = body.strip()
    if not stripped or not stripped[0].isdigit() or following[:1].isdigit():
        return False
    whole, _, fraction = stripped.partition(".")
    return all(c.isdigit() or c == "," for c in whole) and (fraction == "" or fraction.isdigit())
