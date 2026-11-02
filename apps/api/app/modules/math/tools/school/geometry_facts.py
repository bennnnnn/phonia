"""Two closed school geometry facts: the missing leg of a right triangle, and polygon angles.

``a right triangle has hypotenuse 13 and one leg 5, find the other leg`` -> 12;
``sum of the interior angles of a hexagon`` -> 720 degrees.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.number_text import DECIMAL
from app.services.workout import Workout, math_line, render_workout

_NUMBER = rf"({DECIMAL})"
_RIGHT = r"\bright(?:[- ]angled?)?\s+triangle\b"
_IS = r"\s+(?:of\s+|is\s+|=\s*)?"
_HYPOTENUSE = rf"\bhypotenuse{_IS}{_NUMBER}"
_LEG = rf"\b(?:one\s+|a\s+)?(?:leg|side){_IS}{_NUMBER}"
_ASKED_LEG = r".*?\b(?:other|missing|third|remaining)\s+(?:leg|side)\b"
_HYPOTENUSE_AND_LEG = re.compile(
    rf"{_RIGHT}.*?{_HYPOTENUSE}.*?{_LEG}{_ASKED_LEG}|{_RIGHT}.*?{_LEG}.*?{_HYPOTENUSE}{_ASKED_LEG}",
    re.IGNORECASE,
)
_POLYGONS = {
    "triangle": 3,
    "quadrilateral": 4,
    "pentagon": 5,
    "hexagon": 6,
    "heptagon": 7,
    "octagon": 8,
    "nonagon": 9,
    "decagon": 10,
    "dodecagon": 12,
}
_POLYGON = (
    r"(?:a\s+|an\s+|the\s+)?(?:regular\s+)?(?:("
    + "|".join(_POLYGONS)
    + r")"
    + (r"|(\d{1,3})[- ]sided\s+polygon|polygon\s+with\s+(\d{1,3})\s+sides|(\d{1,3})-gon)")
)
_ANGLE_SUM = re.compile(
    rf"\bsum\s+of\s+(?:the\s+)?(?:interior\s+)?angles\s+(?:of|in)\s+{_POLYGON}", re.I
)
_EACH_INTERIOR = re.compile(
    rf"\b(?:each|one|an?|the\s+size\s+of\s+(?:each|one|an?))\s+interior\s+angle\s+(?:of|in)\s+"
    rf"(?:a\s+|an\s+|the\s+)?regular\s+{_POLYGON}",
    re.I,
)
_EACH_EXTERIOR = re.compile(
    rf"\b(?:each|one|an?|the\s+size\s+of\s+(?:each|one|an?))\s+exterior\s+angle\s+(?:of|in)\s+"
    rf"(?:a\s+|an\s+|the\s+)?regular\s+{_POLYGON}",
    re.I,
)


def _sides(match: re.Match[str]) -> int | None:
    name, *counts = match.groups()[-4:]
    if name:
        return _POLYGONS[name.lower()]
    count = next((int(value) for value in counts if value), None)
    return count if count is not None and 3 <= count <= 360 else None


def extract_geometry_fact_intent(cleaned: str) -> MathIntent | None:
    if len(cleaned) > 300:
        return None
    leg = _HYPOTENUSE_AND_LEG.search(cleaned)
    if leg is not None:
        # The first alternative names the hypotenuse first, the second the leg.
        if leg.group(1) is not None:
            hypotenuse, known = float(leg.group(1)), float(leg.group(2))
        else:
            known, hypotenuse = float(leg.group(3)), float(leg.group(4))
        if not 0 < known < hypotenuse:
            return None
        return MathIntent(
            kind="arithmetic",
            school_op="pythagoras_leg",
            tri_c=hypotenuse,
            tri_a=known,
            operation="solve",
        )
    for pattern, op in (
        (_EACH_EXTERIOR, "polygon_exterior"),
        (_EACH_INTERIOR, "polygon_interior"),
        (_ANGLE_SUM, "polygon_angle_sum"),
    ):
        found = pattern.search(cleaned)
        if found is not None:
            sides = _sides(found)
            if sides is None:
                return None
            return MathIntent(kind="arithmetic", school_op=op, combo_n=sides, operation="solve")
    return None


def _number(value: float) -> str:
    return f"{value:g}"


def _degrees(value: float) -> str:
    shown = f"{value:g}" if float(value).is_integer() else f"{value:.2f}".rstrip("0")
    return f"{shown}^\\circ"


def geometry_fact_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.school_op == "pythagoras_leg":
        return _missing_leg(intent, lines)
    n = intent.combo_n
    if n is None:
        return None
    total = (n - 2) * 180
    if intent.school_op == "polygon_angle_sum":
        working = rf"S = ({n} - 2) \times 180^\circ"
        answer = _degrees(total)
        note = "interior angles of an n-sided polygon"
    elif intent.school_op == "polygon_interior":
        working = rf"\frac{{({n} - 2) \times 180^\circ}}{{{n}}} = \frac{{{_degrees(total)}}}{{{n}}}"
        answer = _degrees(total / n)
        note = "the angle sum shared equally"
    else:
        working = rf"\frac{{360^\circ}}{{{n}}}"
        answer = _degrees(360 / n)
        note = "the exterior angles add to 360 degrees"
    lines.append(f"Working: ${working}$ ({note})")
    block = finish_with_answer(lines, answer)
    return replace(block, worked_reply=f"{math_line(working, note)}\n\n```answer\n{answer}\n```\n")


def _missing_leg(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    c, a = intent.tri_c, intent.tri_a
    if c is None or a is None or not 0 < a < c:
        return None
    square = c * c - a * a
    b = math.sqrt(square)
    exact = round(b) if abs(b - round(b)) < 1e-9 else None
    answer = str(exact) if exact is not None else rf"\sqrt{{{_number(square)}}} \approx {b:.4g}"
    lines.append(f"b = sqrt({_number(c)}^2 - {_number(a)}^2) = {answer}")
    working = render_workout(
        Workout(
            given=(
                math_line(f"c = {_number(c)}", "hypotenuse"),
                math_line(f"a = {_number(a)}", "one leg"),
            ),
            find=(math_line("b", "the other leg"),),
            formula=(math_line("a^2 + b^2 = c^2", "Pythagorean theorem"),),
            substitution=(
                math_line(
                    rf"b = \sqrt{{{_number(c)}^2 - {_number(a)}^2}} = "
                    rf"\sqrt{{{_number(c * c)} - {_number(a * a)}}} = \sqrt{{{_number(square)}}}"
                ),
            ),
        ),
        answer,
    )
    return replace(finish_with_answer(lines, answer), worked_reply=working)
