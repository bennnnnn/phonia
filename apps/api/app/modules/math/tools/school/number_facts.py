"""Closed number facts asked in words.

Roots (``cube root of 27``), a fraction or decimal as a percentage, standard
form, and the sum of the first n natural, odd or even numbers. Each writes one
working line and leaves the result to the answer.
"""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from math import isqrt

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import request_body
from app.services.workout import math_line

NUMBER_FACT_OPS = frozenset(
    {"root_words", "to_percent", "to_fraction", "standard_form", "first_n_sum", "factor_count"}
)

_ASK = (
    r"(?:(?:what\s+is|what's|whats|wat\s+is|wat's|wats|find|calculate|work\s+out|evaluate|give)"
    r"\s+)?(?:the\s+)?"
)
# "squre"/"sqaure": how the word is often typed.
_ROOT_NAMES = {
    "square": 2,
    "squre": 2,
    "sqaure": 2,
    "cube": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
}
_ROOT = re.compile(
    rf"{_ASK}(square|squre|sqaure|cube|fourth|fifth|sixth)\s+root\s+of\s+(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_PERCENT = re.compile(
    rf"(?:convert\s+|write\s+|express\s+|{_ASK})(\d+\s*/\s*\d+|\d*\.\d+|\d+)\s+"
    r"(?:to|into|as)\s+(?:a\s+)?percent(?:age)?",
    re.IGNORECASE,
)
# "what is 0.375 as a fraction": a terminating decimal, in lowest terms.
_FRACTION = re.compile(
    rf"(?:convert\s+|write\s+|express\s+|{_ASK})(\d*\.\d+)\s+(?:to|into|as)\s+(?:a\s+)?"
    r"fraction(?:\s+in\s+(?:its\s+)?(?:simplest|lowest)\s+(?:form|terms))?",
    re.IGNORECASE,
)
# "how many factors does 36 have": its positive divisors, counted.
_FACTOR_COUNT = re.compile(
    r"how\s+many\s+(?:positive\s+)?(?:factors|divisors)\s+(?:does\s+(\d{1,7})\s+have|"
    r"(?:are\s+there\s+)?(?:of|for|in)\s+(\d{1,7})|has\s+(\d{1,7}))",
    re.IGNORECASE,
)
_STANDARD_FORM = re.compile(
    r"(?:write|convert|express|put)\s+(-?\d[\d,]*(?:\.\d+)?|-?\.\d+)\s+(?:in|into|as|to)\s+"
    r"(?:standard\s+form|scientific\s+notation)",
    re.IGNORECASE,
)
_FIRST_N = re.compile(
    r"(?:(?:what\s+is|find|calculate|work\s+out)\s+)?(?:the\s+)?sum\s+of\s+(?:the\s+)?first\s+"
    r"(\d{1,6})\s+(natural|counting|positive|whole|odd|even)\s+(?:numbers|integers)",
    re.IGNORECASE,
)


def extract_number_fact_intent(cleaned: str) -> MathIntent | None:
    body = request_body(cleaned)
    if not body or len(body) > 200:
        return None
    root = _ROOT.fullmatch(body)
    if root is not None:
        index = _ROOT_NAMES[root.group(1).lower()]
        if root.group(2).startswith("-") and index % 2 == 0:
            # Not a real number; the model explains the imaginary answer.
            return None
        return MathIntent(
            kind="arithmetic",
            school_op="root_words",
            combo_n=index,
            expr=root.group(2),
            operation="solve",
        )
    percent = _PERCENT.fullmatch(body)
    if percent is not None:
        return MathIntent(
            kind="arithmetic",
            school_op="to_percent",
            expr=percent.group(1).replace(" ", ""),
            operation="solve",
        )
    fraction = _FRACTION.fullmatch(body)
    if fraction is not None:
        return MathIntent(
            kind="arithmetic",
            school_op="to_fraction",
            expr=fraction.group(1),
            operation="solve",
        )
    count = _FACTOR_COUNT.fullmatch(body)
    if count is not None:
        number = int(next(group for group in count.groups() if group))
        if number < 1:
            return None
        return MathIntent(
            kind="arithmetic", school_op="factor_count", expr=str(number), operation="solve"
        )
    standard = _STANDARD_FORM.fullmatch(body)
    if standard is not None:
        return MathIntent(
            kind="arithmetic",
            school_op="standard_form",
            expr=standard.group(1).replace(",", ""),
            operation="solve",
        )
    first = _FIRST_N.fullmatch(body)
    if first is not None:
        kind = first.group(2).lower()
        return MathIntent(
            kind="arithmetic",
            school_op="first_n_sum",
            combo_n=int(first.group(1)),
            trial_outcome=kind if kind in {"odd", "even"} else "natural",
            operation="solve",
        )
    return None


def _root_parts(value: int, index: int) -> tuple[int, int]:
    """``50`` under a square root -> ``(5, 2)``: 5 sqrt(2). The outside and inside factors."""
    outside, inside = 1, value
    factor = 2
    while factor**index <= inside:
        while inside % factor**index == 0:
            inside //= factor**index
            outside *= factor
        factor += 1
    return outside, inside


def _root(intent: MathIntent) -> tuple[str, str] | None:
    index, text = intent.combo_n or 2, intent.expr or ""
    symbol = r"\sqrt" if index == 2 else rf"\sqrt[{index}]"
    if text.startswith("-"):
        # An odd root of a negative number is real: the cube root of -27 is -3.
        # Only a whole root is read; an even root of a negative is not real.
        magnitude = text[1:]
        if index % 2 == 0 or not magnitude.isdigit():
            return None
        whole = round(int(magnitude) ** (1 / index))
        root = next((c for c in (whole - 1, whole, whole + 1) if c**index == int(magnitude)), None)
        if root is None:
            return None
        return f"{symbol}{{{text}}} = -{symbol}{{{magnitude}}} = -{root}", f"-{root}"
    if "." in text:
        value = float(text)
        result = value ** (1 / index)
        return f"{symbol}{{{text}}}", f"{result:.4g}"
    number = int(text)
    whole = round(number ** (1 / index))
    for candidate in (whole - 1, whole, whole + 1):
        if candidate >= 0 and candidate**index == number:
            return f"{symbol}{{{number}}} = {symbol}{{{candidate}^{{{index}}}}}", str(candidate)
    outside, inside = _root_parts(number, index)
    approx = f"{number ** (1 / index):.4g}"
    if outside == 1:
        return f"{symbol}{{{number}}}", rf"{symbol}{{{number}}} \approx {approx}"
    return (
        f"{symbol}{{{number}}} = {symbol}{{{outside}^{{{index}}} \\times {inside}}}",
        rf"{outside}{symbol}{{{inside}}} \approx {approx}",
    )


def _to_percent(intent: MathIntent) -> tuple[str, str] | None:
    text = intent.expr or ""
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    percent = value * 100
    exact = _terminates(percent)
    if percent.denominator == 1:
        shown = f"{percent.numerator}\\%"
    elif exact:
        shown = f"{_decimal_text(percent)}\\%"
    else:
        # 2/3 is 200/3 % exactly, about 66.67%.
        fraction = rf"\frac{{{percent.numerator}}}{{{percent.denominator}}}"
        shown = rf"{fraction}\% \approx {float(percent):.2f}\%"
    if "/" in text:
        top, bottom = text.split("/")
        working = rf"\frac{{{top}}}{{{bottom}}} \times 100\%"
        if exact:
            working += rf" = \frac{{{int(top) * 100}}}{{{bottom}}}\%"
    else:
        working = rf"{text} \times 100\%"
    return working, shown


def _to_fraction(intent: MathIntent) -> tuple[str, str] | None:
    """``0.375 = 375/1000 = 3/8``: the decimal over its place value, then in lowest terms."""
    text = intent.expr or ""
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    places = len(text.partition(".")[2])
    over = rf"\frac{{{int(text.replace('.', ''))}}}{{{10**places}}}"
    lowest = rf"\frac{{{value.numerator}}}{{{value.denominator}}}"
    if value.denominator == 1:
        lowest = str(value.numerator)
    working = f"{text} = {over}" if over == lowest else f"{text} = {over} = {lowest}"
    return working, lowest


def _factor_count(intent: MathIntent) -> tuple[str, str] | None:
    """``36 = 1 * 36 = 2 * 18 = 3 * 12 = 4 * 9 = 6 * 6``: each pair, then the count."""
    number = int(intent.expr or 0)
    if number < 1:
        return None
    pairs = [
        (small, number // small) for small in range(1, isqrt(number) + 1) if number % small == 0
    ]
    factors = sorted({value for pair in pairs for value in pair})
    products = " = ".join(rf"{small} \times {large}" for small, large in pairs)
    listed = ", ".join(str(value) for value in factors)
    return rf"{number} = {products}|factors: {listed}", str(len(factors))


def _terminates(value: Fraction) -> bool:
    denominator = value.denominator
    for prime in (2, 5):
        while denominator % prime == 0:
            denominator //= prime
    return denominator == 1


def _decimal_text(value: Fraction) -> str:
    """A terminating decimal, written exactly: 37.5, not 37.50000."""
    return f"{Decimal(value.numerator) / Decimal(value.denominator):f}".rstrip("0").rstrip(".")


def _standard_form(intent: MathIntent) -> tuple[str, str] | None:
    try:
        value = Decimal(intent.expr or "")
    except InvalidOperation:
        return None
    if value == 0:
        return None
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    exponent = magnitude.adjusted()
    mantissa = (magnitude / Decimal(10) ** exponent).normalize()
    shown = f"{sign}{mantissa:f} \\times 10^{{{exponent}}}"
    places = abs(exponent)
    direction = "left" if exponent > 0 else "right"
    note = (
        f"move the decimal point {places} place{'s' if places != 1 else ''} {direction}"
        if exponent
        else "already between 1 and 10"
    )
    return rf"{sign}{magnitude.normalize():f} = {shown}|{note}", shown


def _first_n(intent: MathIntent) -> tuple[str, str] | None:
    n = intent.combo_n
    if n is None or n < 1:
        return None
    kind = intent.trial_outcome
    if kind == "odd":
        return rf"1 + 3 + \cdots + {2 * n - 1} = {n}^{{2}}", str(n * n)
    if kind == "even":
        return rf"2 + 4 + \cdots + {2 * n} = {n}({n} + 1)", str(n * (n + 1))
    return (
        rf"1 + 2 + \cdots + {n} = \frac{{{n}({n} + 1)}}{{2}} = \frac{{{n} \times {n + 1}}}{{2}}",
        str(n * (n + 1) // 2),
    )


def number_fact_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    solved = {
        "root_words": _root,
        "to_percent": _to_percent,
        "to_fraction": _to_fraction,
        "factor_count": _factor_count,
        "standard_form": _standard_form,
        "first_n_sum": _first_n,
    }[intent.school_op or ""](intent)
    if solved is None:
        return None
    working, answer = solved
    working, _, note = working.partition("|")
    lines.append(f"Working: ${working}$")
    block = finish_with_answer(lines, answer)
    shown = math_line(working, note or None)
    return replace(block, worked_reply=f"{shown}\n\n```answer\n{answer}\n```\n")
