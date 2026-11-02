"""Unit conversion extractor and verified block."""

from __future__ import annotations

import math
import re
from typing import Any

from app.core.config import Settings
from app.modules.math.match.units import asked_conversion
from app.modules.math.schemas import MathIntent
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.block.answer_text import format_quantity
from app.modules.math.tools.extractors.readings import read
from app.modules.math.tools.school.worded_units import (
    extract_quantity_sum,
    extract_worded_conversion,
)
from app.modules.math.unit_conversion import convert_unit
from app.services.number_text import SIGNED_DECIMAL
from app.services.workout import Workout, math_line, render_workout

_UNIT_PATTERN = r"[A-Za-zµμ°][A-Za-z0-9µμ°*/^._-]{0,63}"
_TWICE_HOT_TAIL = re.compile(
    rf"^({_UNIT_PATTERN})\s*[.?!,;]*\s*(?:then\s+)?"
    rf"(?:(?:tell|explain)\s+me\s+)?(?:whether\s+|if\s+)?"
    rf"({SIGNED_DECIMAL})\s*({_UNIT_PATTERN})\s+is\s+twice\s+as\s+hot\s*[.?!]*$",
    re.IGNORECASE,
)


_ANGLE_UNITS = {
    "rad": "rad",
    "rads": "rad",
    "radian": "rad",
    "radians": "rad",
    "deg": "deg",
    "degs": "deg",
    "degree": "deg",
    "degrees": "deg",
    "°": "deg",
}
# A quantity written as an expression, then one plain unit: ``pi/2 radians``,
# ``2π rad``, ``3/4 km``. Compound units such as ``m/s`` keep the number path.
_EXPRESSION_QUANTITY = re.compile(r"(.*?[0-9)πi])\s*([A-Za-zµμ°]+)")
_QUANTITY_CHARS = re.compile(r"[0-9.\s()+\-*/^π]|pi")
_DEGREE_MARK = re.compile(r"\^\{?\\circ\}?")


def _quantity_expression(text: str) -> Any | None:
    """A numeric value made of numbers, π and arithmetic; never a variable."""
    from sympy import pi

    from app.modules.math.solve.parse import parse_expression

    compact = text.strip()
    if not compact or _QUANTITY_CHARS.sub("", compact):
        return None
    with sympy_decline() as declined:
        value = parse_expression(compact.replace("π", "pi"), [])
    if declined:
        return None
    if value is None or value.free_symbols or not value.is_finite or not value.is_real:
        return None
    return value.subs("pi", pi)


def _expression_unit_intent(source: str, dest: str) -> MathIntent | None:
    match = _EXPRESSION_QUANTITY.fullmatch(source.strip())
    if match is None:
        return None
    value = _quantity_expression(match.group(1))
    if value is None:
        return None
    return MathIntent(
        kind="unit",
        school_op="convert",
        percent_base=float(value),
        expr=str(value),
        unit_from=match.group(2),
        unit_to=dest,
        operation="solve",
    )


def _exact_angle(intent: MathIntent) -> str | None:
    """π/2 rad is 90°, and 90° is π/2 rad: an angle with π stays exact."""
    from sympy import Rational, latex, nsimplify, pi, sympify

    src = _ANGLE_UNITS.get(intent.unit_from.lower()) if intent.unit_from else None
    dest = _ANGLE_UNITS.get(intent.unit_to.lower()) if intent.unit_to else None
    if src is None or dest is None or src == dest or intent.percent_base is None:
        return None
    value = sympify(intent.expr) if intent.expr else nsimplify(intent.percent_base)
    if src == "rad":
        degrees = nsimplify(value * 180 / pi)
        return latex(degrees) if degrees.is_rational else None
    if not value.is_rational:
        return None
    radians = Rational(value) / 180
    if radians.q > 360:
        return None
    return latex(radians * pi)


# "25 degrees Celsius" is one unit in two words; the source must be one token.
_TEMPERATURE_WORDS = re.compile(
    r"\bdeg(?:rees?)?\s+(celsius|centigrade|fahrenheit|kelvin)\b", re.IGNORECASE
)


# "how many seconds in a day": units of one fixed size. A month or a year is not
# one (28-31 days; 365 or 366), so those are left to the model.
_FIXED_UNITS = {
    "second": "second",
    "seconds": "second",
    "minute": "minute",
    "minutes": "minute",
    "hour": "hour",
    "hours": "hour",
    "day": "day",
    "days": "day",
    "week": "week",
    "weeks": "week",
    "millimetre": "millimeter",
    "millimetres": "millimeter",
    "millimeter": "millimeter",
    "millimeters": "millimeter",
    "centimetre": "centimeter",
    "centimetres": "centimeter",
    "centimeter": "centimeter",
    "centimeters": "centimeter",
    "metre": "meter",
    "metres": "meter",
    "meter": "meter",
    "meters": "meter",
    "kilometre": "kilometer",
    "kilometres": "kilometer",
    "kilometer": "kilometer",
    "kilometers": "kilometer",
    "inch": "inch",
    "inches": "inch",
    "foot": "foot",
    "feet": "foot",
    "yard": "yard",
    "yards": "yard",
    "mile": "mile",
    "miles": "mile",
    "gram": "gram",
    "grams": "gram",
    "kilogram": "kilogram",
    "kilograms": "kilogram",
    "ounce": "ounce",
    "ounces": "ounce",
    "pound": "pound",
    "pounds": "pound",
    "millilitre": "milliliter",
    "millilitres": "milliliter",
    "milliliter": "milliliter",
    "milliliters": "milliliter",
    "litre": "liter",
    "litres": "liter",
    "liter": "liter",
    "liters": "liter",
}
_HOW_MANY_IN = re.compile(
    r"how\s+many\s+(?P<to>[a-z]+)\s+(?:are\s+)?(?:there\s+)?in\s+"
    r"(?:(?P<one>a|an|one)|(?P<n>\d+(?:\.\d+)?))\s+(?P<from>[a-z]+)\s*[?.]?",
    re.IGNORECASE,
)


def extract_how_many_in_intent(cleaned: str) -> MathIntent | None:
    """``how many seconds in a day`` is 1 day in seconds; both units of one fixed size."""
    match = _HOW_MANY_IN.fullmatch(" ".join(cleaned.split()))
    if match is None:
        return None
    dest = _FIXED_UNITS.get(match.group("to").lower())
    src = _FIXED_UNITS.get(match.group("from").lower())
    if dest is None or src is None or dest == src:
        return None
    return MathIntent(
        kind="unit",
        school_op="convert",
        percent_base=1.0 if match.group("one") else float(match.group("n")),
        unit_from=src,
        unit_to=f"{dest}s" if dest not in {"foot", "inch"} else match.group("to").lower(),
        operation="solve",
    )


def extract_asked_conversion(cleaned: str) -> MathIntent | None:
    """One quantity and the unit to show it in (``match.units.asked_conversion``)."""
    asked = asked_conversion(cleaned)
    if asked is None:
        return None
    value, src, dest = asked
    return MathIntent(
        kind="unit",
        school_op="convert",
        percent_base=value,
        unit_from=src,
        unit_to=dest,
        operation="solve",
    )


def _shown(value: str) -> str:
    """A conversion as people read it: exact when it ends within six decimals (1 mile
    is 1.609344 km), else four significant figures (72 °F is 22.22 °C, not 22.22222222)."""
    number = float(value)
    if math.isclose(number, round(number, 6), rel_tol=0, abs_tol=1e-9):
        return f"{round(number, 6):.10g}"
    return f"{number:.4g}"


def _extract_unit_intent(cleaned: str) -> MathIntent | None:
    from app.services.unit_text import QUANTITY_NUMBER

    how_many = read(extract_how_many_in_intent, cleaned)
    if how_many is not None:
        return how_many
    cleaned = _TEMPERATURE_WORDS.sub(r"\1", cleaned)
    asked = read(extract_asked_conversion, cleaned)
    if asked is not None:
        return asked
    worded = read(extract_worded_conversion, cleaned) or read(extract_quantity_sum, cleaned)
    if worded is not None:
        return worded
    lower = cleaned.lower()
    if "convert" not in lower and " to " not in lower:
        return None
    if "convert" not in lower:
        return None
    after = QUANTITY_NUMBER.search(cleaned)
    if after is None:
        return None
    convert_end = lower.find("convert") + len("convert")
    to_at = lower.find(" to ", convert_end)
    if to_at != -1 and (
        cleaned[convert_end : after.start()].strip()
        or len(cleaned[after.end() : to_at].split()) != 1
    ):
        # ``pi/2 radians``: the number is part of an expression. Reading
        # only the 2 converted 2 rad and certified 114.59°.
        destination = cleaned[to_at + 4 :].strip().split()
        if len(destination) != 1:
            return None
        return _expression_unit_intent(cleaned[convert_end:to_at], destination[0].strip("?."))
    value = float(after.group(0))
    # Temperature conversions allow zero and negative quantities. Retain
    # the sign instead of skipping to a later positive number.
    if abs(value) == float("inf"):
        return None
    idx = lower.find(" to ")
    if idx == -1:
        return None
    destination_text = cleaned[idx + 4 :].strip()
    comparison = _TWICE_HOT_TAIL.fullmatch(destination_text)
    destination = destination_text.split()
    if not destination or (
        comparison is None and len(destination) > 1 and destination[1:] != ["please"]
    ):
        return None
    dest = (comparison.group(1) if comparison is not None else destination[0]).strip("?.")
    # The complete source/destination must be one conversion. Dropping a
    # second request could otherwise turn it into a partial direct answer.
    source = cleaned[after.end() : idx].strip().split()
    if len(source) != 1:
        return None
    # The keypad's degree key types ``45^{\circ}``.
    src = _DEGREE_MARK.sub("°", source[0])
    if src.lower() in {"to"}:
        return None
    if not src or not dest:
        return None
    return MathIntent(
        kind="unit",
        school_op="temperature_twice_compare" if comparison is not None else "convert",
        percent_base=value,
        unit_from=src,
        unit_to=dest,
        temperature_compare_value=(float(comparison.group(2)) if comparison is not None else None),
        temperature_compare_unit=(comparison.group(3) if comparison is not None else None),
        operation="solve",
    )


def _verified_block_unit(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.percent_base is None or not intent.unit_from or not intent.unit_to:
        return None
    quantity = intent.expr or f"{intent.percent_base:g}"
    exact = _exact_angle(intent)
    if exact is not None:
        lines.append(f"{quantity} {intent.unit_from} = {exact} {intent.unit_to} (exact)")
        return finish_with_answer(lines, format_quantity(exact, intent.unit_to))
    answer = convert_unit(intent.percent_base, intent.unit_from, intent.unit_to)
    lines.append(f"{quantity} {intent.unit_from} = {answer} {intent.unit_to}")
    if (
        intent.school_op == "temperature_twice_compare"
        and intent.temperature_compare_value is not None
        and intent.temperature_compare_unit
    ):
        first_kelvin = float(convert_unit(intent.percent_base, intent.unit_from, "kelvin"))
        second_kelvin = float(
            convert_unit(
                intent.temperature_compare_value,
                intent.temperature_compare_unit,
                "kelvin",
            )
        )
        ratio = second_kelvin / first_kelvin
        verdict = math.isclose(ratio, 2.0, rel_tol=1e-9, abs_tol=1e-9)
        lines.append(
            f"Absolute-temperature comparison: {second_kelvin:g} K / "
            f"{first_kelvin:g} K = {ratio:.6g}; twice={verdict}."
        )
        direct = render_workout(
            Workout(
                given=(
                    math_line(f"{intent.percent_base:g}\\,{intent.unit_from}"),
                    math_line(
                        f"{intent.temperature_compare_value:g}\\,{intent.temperature_compare_unit}"
                    ),
                ),
                steps=(
                    math_line(
                        f"{intent.percent_base:g}\\,{intent.unit_from}"
                        f" = {answer}\\,{intent.unit_to}",
                        "convert",
                    ),
                    math_line(
                        f"{intent.temperature_compare_value:g}\\,{intent.temperature_compare_unit}"
                        f" = {second_kelvin:g}\\,K, \\quad "
                        f"{intent.percent_base:g}\\,{intent.unit_from} = {first_kelvin:g}\\,K",
                        "absolute scale",
                    ),
                    math_line(
                        f"{second_kelvin:g}/{first_kelvin:g} \\approx {ratio:.3f}",
                        "not 2, so not twice as hot (Fahrenheit's zero is arbitrary)",
                    ),
                ),
            )
        ).removesuffix("\n\n**Answer**")
        return VerifiedMathBlock(text="\n".join(lines), direct_reply=direct)
    return finish_with_answer(lines, format_quantity(_shown(answer), intent.unit_to))
