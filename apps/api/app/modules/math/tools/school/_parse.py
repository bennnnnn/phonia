"""Shared number and word scans for school arithmetic extractors."""

from __future__ import annotations

import re

from app.services.number_text import DECIMAL_LITERAL, finite_match_value, number_word_value

# The side a triangle question asks for: "Find c", "calculate the length of side b". The words
# are read in any case; the letter only as written, since "C" names the angle opposite side "c".
_SIDE_ASKED = re.compile(
    r"\b(?i:(?:find|calculate|determine|what\s+is|work\s+out)\s+"
    r"(?:the\s+(?:length\s+of\s+)?)?(?:side\s+)?)([a-c])\b"
)


def _count_char(text: str, needle: str) -> int:
    count = 0
    for char in text:
        if char == needle:
            count += 1
    return count


def request_body(text: str) -> str:
    """The request on one line, without its closing ``?``, ``.`` or ``!``."""
    return " ".join(text.split()).strip().rstrip("?.!").strip()


def count_value(word: str) -> int:
    """A count written as a word ("three") or in digits."""
    return number_word_value(word.lower()) or int(word)


def _exactly_n_numbers(cleaned: str, count: int) -> list[float] | None:
    matches = list(DECIMAL_LITERAL.finditer(cleaned))
    if len(matches) != count:
        return None
    values: list[float] = []
    for match in matches:
        value = finite_match_value(match)
        if value is None:
            return None
        values.append(value)
    return values


def _colon_ratio_parts(text: str) -> tuple[list[float], list[tuple[int, int]]] | None:
    """First ``a:b`` / ``a:b:c`` group. Linear scan, no nested regex."""
    search_from = 0
    length = len(text)
    while search_from < length:
        match = DECIMAL_LITERAL.search(text, search_from)
        if match is None:
            return None
        cursor = match.end()
        while cursor < length and text[cursor].isspace():
            cursor += 1
        if cursor >= length or text[cursor] != ":":
            search_from = match.end()
            continue
        values = [finite_match_value(match)]
        spans = [(match.start(), match.end())]
        if values[0] is None:
            search_from = match.end()
            continue
        cursor += 1
        while True:
            while cursor < length and text[cursor].isspace():
                cursor += 1
            nxt = DECIMAL_LITERAL.match(text, cursor)
            if nxt is None:
                break
            parsed = finite_match_value(nxt)
            if parsed is None:
                break
            values.append(parsed)
            spans.append((nxt.start(), nxt.end()))
            cursor = nxt.end()
            while cursor < length and text[cursor].isspace():
                cursor += 1
            if cursor < length and text[cursor] == ":":
                cursor += 1
                continue
            break
        finite_parts = [part for part in values if part is not None]
        if len(finite_parts) >= 2:
            return finite_parts, spans
        search_from = match.end()
    return None
