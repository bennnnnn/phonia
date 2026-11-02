"""Put a visible word space outside closed inline Markdown tokens.

Models sometimes emit ``at**40 km/h**``. CommonMark then draws ``at40``.
This repairs that boundary in assistant prose. It does not rewrite code
fences, indented code, blockquotes, URLs, math bodies, or punctuation. The
phone's twin is apps/mobile/lib/markdown/inlineBoundaries.ts.
"""

from __future__ import annotations

import re

from app.modules.chat.inline_code import code_span_opens_within, escaped_at, is_bare_number
from app.modules.chat.markdown_regions import (
    PRICE_TIER,
    leave_prose_line,
    map_prose_outside_fences,
)

_OPEN_PUNCT = set('([{"' + "\u201c\u2018\u00ab")
_CLOSE_PUNCT = set('.,;:!?)]}"' + "\u201d\u2019\u00bb\u2026\u2014\u2013/%")


def repair_inline_token_boundaries(text: str) -> str:
    """Insert missing prose spaces around closed bold, code, links, and math."""
    return map_prose_outside_fences(text, _repair_prose)


def _repair_prose(prose: str) -> str:
    return "\n".join(
        line if leave_prose_line(line) else _repair_line(line) for line in prose.split("\n")
    )


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3040 <= code <= 0x30FF
        or 0x3400 <= code <= 0x9FFF
        or 0xAC00 <= code <= 0xD7AF
        or 0x0E00 <= code <= 0x0E7F
        or 0xF900 <= code <= 0xFAFF
        # The supplementary ideographic planes (CJK extensions B and later).
        or 0x20000 <= code <= 0x3FFFF
    )


def _needs_word_space(char: str) -> bool:
    """Letters and digits in scripts that separate words with spaces."""
    if not char or char.isspace() or _is_cjk(char):
        return False
    return char.isalnum()


def _glue_before(previous: str) -> bool:
    if not previous or previous.isspace() or previous in _OPEN_PUNCT:
        return False
    return _needs_word_space(previous)


def _glue_after(nxt: str) -> bool:
    if not nxt or nxt.isspace() or nxt in _CLOSE_PUNCT:
        return False
    # A following delimiter is another inline token, not punctuation.
    if nxt in "$*`[":
        return True
    return _needs_word_space(nxt)


def _skip_command(text: str, index: int) -> int:
    cursor = index + 1
    if cursor < len(text) and text[cursor].isalpha():
        while cursor < len(text) and text[cursor].isalpha():
            cursor += 1
    elif cursor < len(text):
        cursor += 1
    return cursor


def _read_url(text: str, index: int) -> int | None:
    if text.startswith("https://", index) or text.startswith("http://", index):
        cursor = index
    elif text.startswith("www.", index):
        cursor = index
    else:
        return None
    while cursor < len(text) and not text[cursor].isspace():
        cursor += 1
    return cursor


def _read_price_tier(text: str, index: int) -> int | None:
    tier = PRICE_TIER.match(text, index)
    return tier.end() if tier is not None else None


def _read_code(text: str, index: int) -> int | None:
    if text[index] != "`":
        return None
    length = 0
    while index + length < len(text) and text[index + length] == "`":
        length += 1
    token = "`" * length
    close = text.find(token, index + length)
    if close < 0 or "\n" in text[index + length : close] or close == index + length:
        return None
    return close + length


def _ascii_digit(char: str) -> bool:
    return char.isascii() and char.isdigit()


def _read_math(text: str, index: int) -> int | None:
    if escaped_at(text, index):
        return None
    if text.startswith("$$", index):
        close = text.find("$$", index + 2)
        if close < 0 or "\n" in text[index + 2 : close] or close == index + 2:
            return None
        if code_span_opens_within(text, index + 2, close):
            return None
        return close + 2
    if text[index] != "$" or (index > 0 and text[index - 1] == "$"):
        return None
    start = index + 1
    while start < len(text):
        close = text.find("$", start)
        if close < 0 or "\n" in text[index + 1 : close]:
            return None
        if escaped_at(text, close):
            start = close + 1
            continue
        if close + 1 < len(text) and text[close + 1] == "$":
            return None
        # A pair never reaches across an inline code span: markdown-it reads
        # the code first, so this would pad dollars inside the code.
        if code_span_opens_within(text, index + 1, close):
            return None
        body = text[index + 1 : close]
        if not body.strip():
            return None
        # A price, then a dollar before a digit: two prices. Padding
        # "$38.40 = $19.20" as maths saved "$ 19.20", which then read as maths.
        # Maths glued to a digit (`$a_n$2`) is still padded.
        if _ascii_digit(text[close + 1 : close + 2]) and _ascii_digit(body.lstrip()[:1]):
            return None
        # "$5 and $10" is currency, not a math span. "$2$" is one number: when
        # it was skipped as a price, its closer opened a span with the next
        # dollar on the line and padded "$2 $".
        if (
            body[0].isdigit()
            and not any(char in body for char in "\\=^_")
            and not is_bare_number(body, text[close + 1 : close + 2])
        ):
            return None
        return close + 1
    return None


def _read_link(text: str, index: int) -> int | None:
    cursor = index
    if text[cursor] == "!" and cursor + 1 < len(text) and text[cursor + 1] == "[":
        cursor += 1
    if cursor >= len(text) or text[cursor] != "[":
        return None
    close = text.find("]", cursor + 1)
    if close < 0 or "\n" in text[cursor + 1 : close]:
        return None
    if close + 1 < len(text) and text[close + 1] == "(":
        end = text.find(")", close + 2)
        if end < 0 or "\n" in text[close + 2 : end]:
            return None
        return end + 1
    if close + 1 < len(text) and text[close + 1] == "[":
        end = text.find("]", close + 2)
        if end < 0 or "\n" in text[close + 2 : end]:
            return None
        return end + 1
    return None


def _read_bold(text: str, index: int) -> int | None:
    if not text.startswith("**", index):
        return None
    marker_len = 3 if text.startswith("***", index) else 2
    close = text.find("*" * marker_len, index + marker_len)
    if close < 0:
        return None
    inner = text[index + marker_len : close]
    if not inner.strip() or "\n" in inner:
        return None
    return close + marker_len


def _read_emphasis(text: str, index: int) -> int | None:
    if text[index] != "*" or text.startswith("**", index):
        return None
    if index + 1 < len(text) and text[index + 1] == " ":
        return None
    close = text.find("*", index + 1)
    if close < 0 or text.startswith("**", close):
        return None
    inner = text[index + 1 : close]
    if not inner or "\n" in inner:
        return None
    if not any(char.isalpha() and not _is_cjk(char) for char in inner):
        return None
    return close + 1


# One letter in bold or italics, inside a word: a mnemonic's "**A**ffect is
# **A**ction" became "**A** ffect is **A** ction" (2026-10-29). Letters of an alphabet
# (Latin, Greek, Cyrillic): in a syllabary such as Amharic's, one sign is a syllable. A
# longer span ("the**US**economy"), or one against a digit ("**at**40"), is still a missing space.
_ALPHABET = "A-Za-z\u00c0-\u024f\u0370-\u03ff\u0400-\u04ff"
_IN_WORD = re.compile(rf"(\*{{1,3}})[{_ALPHABET}]\1")
_ALPHABET_LETTER = re.compile(rf"[{_ALPHABET}]")


def _in_word(span: str, neighbour: str) -> bool:
    return (
        _ALPHABET_LETTER.fullmatch(neighbour) is not None and _IN_WORD.fullmatch(span) is not None
    )


def _emit(out: list[str], span: str, nxt: str) -> None:
    previous = out[-1][-1:] if out else ""
    if out and _glue_before(previous) and not _in_word(span, previous):
        out.append(" ")
    out.append(span)
    if _glue_after(nxt[:1]) and not _in_word(span, nxt[:1]):
        out.append(" ")


# A run of characters no branch below acts on: none starts a command, a URL, a price
# tier, a code, maths or link span, or emphasis. It is copied whole instead of a
# character at a time through every reader.
_INERT = re.compile(r"(?:[^\\(`$!\[*hw]|h(?!ttps?://)|w(?!ww\.))+")


def _repair_line(line: str) -> str:
    out: list[str] = []
    index = 0
    length = len(line)
    while index < length:
        inert = _INERT.match(line, index)
        if inert is not None:
            out.append(inert.group())
            index = inert.end()
            continue
        if line[index] == "\\":
            end = _skip_command(line, index)
            out.append(line[index:end])
            index = end
            continue
        # A URL or a ($$) price tier is copied as written.
        verbatim_end = _read_url(line, index) or _read_price_tier(line, index)
        if verbatim_end is not None:
            out.append(line[index:verbatim_end])
            index = verbatim_end
            continue
        for reader in (_read_code, _read_math, _read_link, _read_bold, _read_emphasis):
            span_end = reader(line, index)
            if span_end is None:
                continue
            _emit(out, line[index:span_end], line[span_end : span_end + 1])
            index = span_end
            break
        else:
            if line[index] == "*":
                cursor = index
                while cursor < length and line[cursor] == "*":
                    cursor += 1
                # Horizontal rules and unclosed runs stay literal.
                if cursor - index >= 3 or cursor == length or line[cursor : cursor + 1].isspace():
                    out.append(line[index:cursor])
                    index = cursor
                    continue
            out.append(line[index])
            index += 1
    return "".join(out)
