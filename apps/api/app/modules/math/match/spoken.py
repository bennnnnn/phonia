"""Maths said in words, in the notation the readers take: "what is 3 squared".

Dictation and casual typing write maths out: "what is 3 squared", "solve x squared minus
4 equals 0", "what is seven plus eight", "graph y equals x squared". The readers take
symbols, so these went to the model unchecked and the graph drew nothing. This turns the
spoken words into symbols. ``extract_math_intent`` tries it only when the message as
written gave no reading, and keeps it only when it gives one, so "plus I'm over it" stays
chat. A number word becomes a digit only beside an operator: "which one" stays words.
"""

from __future__ import annotations

import re

from app.services.text_normalize import collapse_ws

_ORDINAL_POWERS = {
    "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10,
}  # fmt: skip
_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}  # fmt: skip
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}  # fmt: skip
_UNIT = "|".join(_UNITS)
_TEN = "|".join(_TENS)
# "seven", "twenty one", "twenty-one", "one hundred", "a hundred and five".
_NUMBER_WORDS = re.compile(
    rf"\b(?:(?P<h>{_UNIT}|a)\s+hundred(?:\s+and)?\s*)?"
    rf"(?:(?P<t>{_TEN})(?:[\s-](?P<tu>{_UNIT}))?|(?P<u>{_UNIT}))?\b",
    re.IGNORECASE,
)
_ORDINAL = "|".join(_ORDINAL_POWERS)
_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in (
        (r"\bis\s+equal\s+to\b|\bequal\s+to\b|\bequals\b", "="),
        (r"\bmultiplied\s+by\b", "*"),
        (r"\bdivided\s+by\b", "/"),
        (rf"\b(?:raised\s+)?to\s+the\s+({_ORDINAL})(?:\s+power)?\b", r"^\1"),
        (r"\b(?:raised\s+)?to\s+the\s+power\s+of\b|\braised\s+to\b", "^"),
        (r"\bsquared\b", "^2"),
        (r"\bcubed\b", "^3"),
        (r"\b(?:the\s+)?square\s+root\s+of\b", "sqrt"),
        (r"\bpercent\b", "%"),
        (r"\bplus\b", "+"),
        (r"\bminus\b", "-"),
        (r"\btimes\b", "*"),
        (r"\bnegative\s+(?=\d|[a-z]\b)", "-"),
        (r"\bsine\b", "sin"),
        (r"\bcosine\b", "cos"),
        (r"\btangent\b", "tan"),
    )
)
# "3 over 4", "x over 2": a fraction only between two operands.
_OVER = re.compile(r"(\d+(?:\.\d+)?|\b[a-z]\b|\))\s+over\s+(\d|[a-z]\b|\()", re.IGNORECASE)
_OPERATOR = r"[-+*/^=%]"
_ORDINAL_EXPONENT = re.compile(rf"\^({_ORDINAL})\b", re.IGNORECASE)


def _number(match: re.Match[str]) -> str:
    hundreds = match.group("h")
    value = 0
    if hundreds:
        value += 100 * (1 if hundreds.lower() == "a" else _UNITS[hundreds.lower()])
    if match.group("t"):
        value += _TENS[match.group("t").lower()]
        if match.group("tu"):
            value += _UNITS[match.group("tu").lower()]
    elif match.group("u"):
        value += _UNITS[match.group("u").lower()]
    return str(value)


def _numbers_beside_operators(text: str) -> str:
    """Number words next to an operator or a digit become digits; the rest stay words."""
    out: list[str] = []
    last = 0
    for match in _NUMBER_WORDS.finditer(text):
        if not match.group(0).strip():
            continue
        before = text[: match.start()].rstrip()
        after = text[match.end() :].lstrip()
        beside = re.search(rf"(?:{_OPERATOR}|\d|\(|\bsqrt)$", before) or re.match(
            rf"(?:{_OPERATOR}|\d|\))", after
        )
        if not beside:
            continue
        out.append(text[last : match.start()])
        out.append(_number(match))
        last = match.end()
    out.append(text[last:])
    return "".join(out)


def spoken_math_to_plain(text: str) -> str:
    """``text`` with its spoken maths as symbols; unchanged when it says none."""
    plain = text
    for pattern, replacement in _PHRASES:
        plain = pattern.sub(replacement, plain)
    plain = _ORDINAL_EXPONENT.sub(lambda m: f"^{_ORDINAL_POWERS[m.group(1).lower()]}", plain)
    plain = _OVER.sub(r"\1 / \2", plain)
    plain = _numbers_beside_operators(plain)
    plain = re.sub(r"\bsqrt\s+(\d+(?:\.\d+)?|[a-z]\b)", r"sqrt(\1)", plain)
    plain = re.sub(r"\s*\^\s*", "^", plain)
    plain = re.sub(r"(\d)\s+%", r"\1%", plain)
    return collapse_ws(plain) if plain != text else text
