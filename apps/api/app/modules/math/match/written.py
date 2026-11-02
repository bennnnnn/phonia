"""School-work arithmetic: spoken powers and one closed two-number operation.

The cue stripper lives in ``arithmetic``. This grammar only accepts a
complete request, so a leftover word is not a column sum.
"""

from __future__ import annotations

import re
from typing import Literal, cast

from app.modules.math.match.arithmetic import (
    _looks_like_date_or_phone,
    _strip_arith_cues,
    _unambiguous_single_slash,
    times_between_numbers,
)
from app.services.text_match import word_index
from app.services.text_normalize import collapse_ws

_MAX = 1000

_WRITTEN_OPERATOR_ALIASES = (
    ("multiplied by", "*"),
    ("divided by", "/"),
    ("devided by", "/"),
    ("divide by", "/"),
    ("devide by", "/"),
    ("times", "*"),
    ("plus", "+"),
    ("minus", "-"),
    ("\u00d7", "*"),
    ("\u00f7", "/"),
    # U+2212, the minus sign the app itself prints in suggestions.
    ("\u2212", "-"),
    ("*", "*"),
    ("/", "/"),
    ("+", "+"),
    ("-", "-"),
)
_WRITTEN_SCHOOL_OP = {
    "+": "column_addition",
    "-": "column_subtraction",
    "*": "column_multiplication",
    "/": "long_division",
}

# Presentation methods that select the typed school-work trace rather than
# changing the arithmetic.  Keep this as a small grammar (connector + method),
# not a list of complete user sentences.  The allowed-operation set prevents
# us from silently answering a request such as "2 + 3 using borrowing" with a
# carrying trace that does not follow the requested method.
_WRITTEN_METHODS: tuple[tuple[str, frozenset[str]], ...] = (
    ("column addition", frozenset({"column_addition"})),
    ("column subtraction", frozenset({"column_subtraction"})),
    ("column multiplication", frozenset({"column_multiplication"})),
    ("long multiplication", frozenset({"column_multiplication"})),
    ("carrying", frozenset({"column_addition", "column_multiplication"})),
    ("borrowing", frozenset({"column_subtraction"})),
    ("regrouping", frozenset({"column_addition", "column_subtraction"})),
    (
        "standard algorithm",
        frozenset({"column_addition", "column_subtraction", "column_multiplication"}),
    ),
)
_WRITTEN_METHOD_CONNECTORS = ("using the", "using", "use the", "use", "with", "by")


_OTHER_WRITTEN_METHODS = ("long division", "short division", "column method", "written method")


def requests_written_method(text: str) -> bool:
    """True when the learner names a written procedure: "8 + 7 using carrying"."""
    lower = collapse_ws(text).lower()
    names = (*(method for method, _ in _WRITTEN_METHODS), *_OTHER_WRITTEN_METHODS)
    return any(word_index(lower, name) != -1 for name in names)


def _strip_written_method_cues(value: str) -> tuple[str, frozenset[str] | None]:
    """Remove bounded method metadata and return the compatible school ops."""
    compatible: frozenset[str] | None = None
    stripped = value
    for method, allowed in _WRITTEN_METHODS:
        for connector in _WRITTEN_METHOD_CONNECTORS:
            phrase = f"{connector} {method}"
            index = word_index(stripped, phrase)
            if index == -1:
                continue
            if word_index(stripped[index + len(phrase) :], phrase) != -1:
                return value, frozenset()
            stripped = collapse_ws(f"{stripped[:index]} {stripped[index + len(phrase) :]}").strip(
                " :?.!"
            )
            compatible = allowed if compatible is None else compatible & allowed
    return stripped, compatible


_DIVISION_MODE_PHRASES: tuple[tuple[str, str], ...] = (
    ("quotient and remainder", "remainder"),
    ("with a remainder", "remainder"),
    ("with remainder", "remainder"),
    ("as a remainder", "remainder"),
    ("as a fraction", "fraction"),
    ("fraction answer", "fraction"),
    ("as a decimal", "decimal"),
    ("decimal answer", "decimal"),
    ("round up", "round_up"),
    ("discard the remainder", "discard"),
    ("ignore the remainder", "discard"),
)


def _school_number(token: str) -> str | None:
    value = token.strip()
    if not value or any(not (ch.isascii() and (ch.isdigit() or ch in ",.")) for ch in value):
        return None
    if value.count(".") > 1:
        return None
    whole, dot, fraction = value.partition(".")
    if dot and (not fraction or not fraction.isdigit()):
        return None
    if "," in whole:
        groups = whole.split(",")
        if not groups[0].isdigit() or not 1 <= len(groups[0]) <= 3:
            return None
        if any(len(group) != 3 or not group.isdigit() for group in groups[1:]):
            return None
        whole = "".join(groups)
    elif not whole.isdigit():
        return None
    return whole + (f".{fraction}" if dot else "")


_POWER_ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


def _power_atom(token: str) -> str | None:
    number = _school_number(token)
    if number is not None:
        return number
    return token.lower() if len(token) == 1 and token.isascii() and token.isalpha() else None


def _power_exponent(token: str) -> int | None:
    lower = token.lower()
    if lower in _POWER_ORDINALS:
        return _POWER_ORDINALS[lower]
    ordinal = re.fullmatch(r"^(\d+)(?:st|nd|rd|th)", lower)
    raw = ordinal.group(1) if ordinal is not None else lower
    if not raw.isdigit():
        return None
    value = int(raw)
    return value if value <= 1000 else None


def spoken_power_request(text: str) -> str | None:
    """Return canonical ``base^exponent`` for one complete spoken power ask.

    This is a bounded grammar, not a physics keyword exception.  It accepts
    both base-first (``2 to the power of 3``) and exponent-first (``the third
    power of 5``) forms only when the entire remaining request is consumed.
    """
    if not text or len(text) > _MAX:
        return None
    from app.modules.math.response_intent import strip_math_response_wrappers

    value, _had_cue = _strip_arith_cues(collapse_ws(strip_math_response_wrappers(text)).lower())
    tokens = value.split()
    if tokens[:1] == ["find"]:
        tokens = tokens[1:]
    if tokens[:1] == ["the"]:
        tokens = tokens[1:]

    # 2 to the power of 3 / 2 raised to the third power
    base = _power_atom(tokens[0]) if tokens else None
    tail = tokens[1:]
    exponent_token: str | None = None
    if tail[:4] == ["to", "the", "power", "of"] and len(tail) == 5:
        exponent_token = tail[4]
    elif tail[:5] == ["raised", "to", "the", "power", "of"] and len(tail) == 6:
        exponent_token = tail[5]
    elif len(tail) == 4 and tail[:2] == ["to", "the"] and tail[3] == "power":
        exponent_token = tail[2]
    elif len(tail) == 5 and tail[:3] == ["raised", "to", "the"] and tail[4] == "power":
        exponent_token = tail[3]
    if base is not None and exponent_token is not None:
        exponent = _power_exponent(exponent_token)
        return f"{base}^{exponent}" if exponent is not None else None

    # the third power of 5
    if len(tokens) == 4 and tokens[1:3] == ["power", "of"]:
        exponent = _power_exponent(tokens[0])
        base = _power_atom(tokens[3])
        if exponent is not None and base is not None:
            return f"{base}^{exponent}"
    return None


def written_addition_request(text: str) -> list[str] | None:
    """Return every addend for one closed two-to-six-addend school sum."""
    if not text or len(text) > _MAX:
        return None
    from app.modules.math.response_intent import strip_math_response_wrappers

    value = collapse_ws(strip_math_response_wrappers(text)).strip(" :?.!").lower()
    for filler in ("for ", "of ", "me "):
        if value.startswith(filler):
            value = value[len(filler) :].lstrip()
            break
    value, _had_cue = _strip_arith_cues(value)
    if any(alias in value for alias in (" - ", " * ", " / ", "minus", "times", "divided")):
        return None
    raw_tokens = re.split(r"\s*(?:\+|\bplus\b)\s*", value)
    if not 2 <= len(raw_tokens) <= 6:
        return None
    numbers = [_school_number(token) for token in raw_tokens]
    if any(number is None for number in numbers):
        return None
    return [number for number in numbers if number is not None]


def division_answer_mode(
    text: str, left: str, right: str
) -> Literal["remainder", "fraction", "decimal", "round_up", "discard"]:
    """Select answer representation independently from response detail.

    Ordinary division means the ordinary numerical quotient.  Remainder form
    is a distinct interpretation and is selected only when the learner asks
    for it, or asks for school long division, and both operands are whole
    numbers. A decimal stays a decimal quotient.
    Whether the working is displayed is decided later by response intent.
    """
    lower = collapse_ws(text).lower()
    whole = "." not in left and "." not in right
    for phrase, mode in _DIVISION_MODE_PHRASES:
        if phrase in lower and (mode != "remainder" or whole):
            return cast(Literal["remainder", "fraction", "decimal", "round_up", "discard"], mode)
    if "long division" in lower and whole:
        return "remainder"
    return "decimal"


def written_arithmetic_request(text: str) -> tuple[str, str, str, str] | None:
    """Return ``(left, right, operator, school_op)`` for one closed school sum.

    This is deliberately narrower than the general calculator grammar. It
    accepts two non-negative literals and one operation, including grouping
    commas and common spoken operators, while rejecting every leftover word.
    """
    if not text or len(text) > _MAX:
        return None
    from app.modules.math.response_intent import strip_math_response_wrappers

    value = collapse_ws(strip_math_response_wrappers(text)).strip(" :?.!").lower()
    for filler in ("for ", "of ", "me "):
        if value.startswith(filler):
            value = value[len(filler) :].lstrip()
            break
    value, had_cue = _strip_arith_cues(value)
    value, compatible_methods = _strip_written_method_cues(value)
    if compatible_methods == frozenset():
        return None
    # A bare "show" selects presentation, not an arithmetic operation.  Do
    # this after the established "show long division" grammar has seen the
    # complete phrase below.
    if value.startswith("show me "):
        value = value[8:].lstrip()
        had_cue = True
    elif value.startswith("show ") and not value.startswith("show long division"):
        value = value[5:].lstrip()
        had_cue = True
    for phrase, _mode in _DIVISION_MODE_PHRASES:
        value = collapse_ws(value.replace(phrase, " ")).strip(" :?.!")
    value = times_between_numbers(value)
    had_long_division_cue = "long division" in value
    for phrase in (
        "using long division to",
        "use long division to",
        "show long division",
        "using long division",
        "use long division",
        "with long division",
    ):
        value = collapse_ws(value.replace(phrase, " ")).strip(" :?.!")
    found: tuple[str, str] | None = None
    for alias, operator in _WRITTEN_OPERATOR_ALIASES:
        index = value.find(alias)
        if index < 0:
            continue
        if value.find(alias, index + len(alias)) >= 0:
            return None
        if found is not None:
            return None
        found = (alias, operator)
    if found is None:
        return None
    alias, operator = found
    left_raw, right_raw = value.split(alias, 1)
    left, right = _school_number(left_raw), _school_number(right_raw)
    if left is None or right is None:
        return None
    compact = f"{left}{operator}{right}"
    school_op = _WRITTEN_SCHOOL_OP[operator]
    if compatible_methods is not None and school_op not in compatible_methods:
        return None
    if alias == "/" and not (
        had_cue or had_long_division_cue or _unambiguous_single_slash(compact)
    ):
        return None
    if alias == "-" and not had_cue and _looks_like_date_or_phone(compact):
        return None
    return left, right, operator, school_op
