"""Triangle trigonometry: an extreme angle by the cosine rule, the sine rule, right-triangle
ratios and a ladder against a wall, with the laws from ``math/solve/triangle.py``.
"""

from __future__ import annotations

import math
from fractions import Fraction

from app.modules.math.solve import triangle as triangle_laws
from app.modules.math.tools.school.geometry_measures.working import (
    _approx,
    _degrees,
    _n,
    _Solved,
    _surd_answer,
)
from app.services.workout import math_line


def _extreme_angle(numbers: list[float], words: list[str]) -> _Solved | None:
    """The largest angle is opposite the longest side: ``\\cos C = (a^2 + b^2 - c^2) / 2ab``."""
    largest = words[0] != "smallest"
    sides = sorted(numbers)
    if not triangle_laws.triangle_valid(*sides):
        return None
    a, b, c = sides if largest else (sides[1], sides[2], sides[0])
    angle = triangle_laws.cosine_rule_angle(a, b, c)
    top = a * a + b * b - c * c
    bottom = 2 * a * b
    ratio = Fraction(str(triangle_laws.cosine_rule_cosine(a, b, c)))
    which = "largest" if largest else "smallest"
    return _Solved(
        (math_line(f"a = {_n(a)}"), math_line(f"b = {_n(b)}"), math_line(f"c = {_n(c)}")),
        (
            math_line(
                "C",
                f"the {which} angle, opposite the "
                f"{'longest' if largest else 'shortest'} side {_n(c)}",
            ),
        ),
        (math_line(r"\cos C = \frac{a^2 + b^2 - c^2}{2ab}", "Cosine rule"),),
        (
            math_line(
                rf"\cos C = \frac{{{_n(a)}^2 + {_n(b)}^2 - {_n(c)}^2}}{{2({_n(a)})({_n(b)})}}"
                rf" = \frac{{{_n(top)}}}{{{_n(bottom)}}}"
            ),
            math_line(
                rf"C = \cos^{{-1}}\left(\frac{{{ratio.numerator}}}{{{ratio.denominator}}}\right)"
            ),
        ),
        ("" if angle.is_Rational else r"\approx ") + _degrees(float(angle)),
    )


def _ladder(numbers: list[float], words: list[str]) -> _Solved | None:
    length, foot = numbers
    unit = {"metre": "m", "metres": "m", "meter": "m", "meters": "m", "feet": "ft"}.get(
        words[0] if words else "", words[0] if words else None
    )
    if not 0 < foot < length:
        return None
    square = length * length - foot * foot
    return _Solved(
        (
            math_line(f"L = {_n(length)}", "the ladder, the hypotenuse"),
            math_line(f"d = {_n(foot)}", "foot of the ladder to the wall"),
        ),
        (math_line("h", "height up the wall"),),
        (math_line(r"h^2 + d^2 = L^2", "Pythagorean theorem"),),
        (
            math_line(
                rf"h = \sqrt{{{_n(length)}^2 - {_n(foot)}^2}} = \sqrt{{{_n(length * length)} - "
                rf"{_n(foot * foot)}}} = \sqrt{{{_n(square)}}}"
            ),
        ),
        _surd_answer(square, unit),
    )


def _sine_rule(numbers: list[float], words: list[str]) -> _Solved | None:
    known, known_angle, target_angle = numbers
    known_name, target_name = words
    value = triangle_laws.sine_rule_side(known, known_angle, target_angle)
    k, t = known_name, target_name
    return _Solved(
        (
            math_line(f"{k} = {_n(known)}"),
            math_line(f"{k.upper()} = {_degrees(known_angle)}"),
            math_line(f"{t.upper()} = {_degrees(target_angle)}"),
        ),
        (math_line(t),),
        (
            math_line(
                rf"\frac{{{t}}}{{\sin {t.upper()}}} = \frac{{{k}}}{{\sin {k.upper()}}}", "Sine rule"
            ),
        ),
        (
            math_line(
                rf"{t} = \frac{{{_n(known)} \sin {_degrees(target_angle)}}}"
                rf"{{\sin {_degrees(known_angle)}}}"
            ),
        ),
        # At exact angles a surd whose square is whole (4\sqrt{2}); otherwise the decimal.
        rf"\approx {_approx(float(value))}"
        if value.is_Float
        else _surd_answer(float(value**2), None),
    )


_RATIO_NAME = {"sin": "Sine ratio", "cos": "Cosine ratio", "tan": "Tangent ratio"}
# The two sides each ratio uses, read from the pair the question gave.
_RATIO = {
    ("hypotenuse", "opposite"): "sin",
    ("adjacent", "hypotenuse"): "cos",
    ("adjacent", "opposite"): "tan",
}


def _right_angle_from_sides(numbers: list[float], words: list[str]) -> _Solved | None:
    first, second = words
    pair = (first, second)
    if pair not in _RATIO:
        return None
    function = _RATIO[pair]
    values = dict(zip(words, numbers, strict=True))
    if function == "sin":
        top, bottom = values["opposite"], values["hypotenuse"]
    elif function == "cos":
        top, bottom = values["adjacent"], values["hypotenuse"]
    else:
        top, bottom = values["opposite"], values["adjacent"]
    value = top / bottom
    if function != "tan" and not 0 < value < 1:
        return None
    angle = math.degrees({"sin": math.asin, "cos": math.acos, "tan": math.atan}[function](value))
    names = {
        "sin": ("opposite", "hypotenuse"),
        "cos": ("adjacent", "hypotenuse"),
        "tan": ("opposite", "adjacent"),
    }
    over = names[function]
    return _Solved(
        tuple(math_line(rf"\text{{{name}}} = {_n(values[name])}") for name in over),
        (math_line(r"\theta", "the angle"),),
        (
            math_line(
                rf"\{function}\theta = \frac{{\text{{{over[0]}}}}}{{\text{{{over[1]}}}}}",
                _RATIO_NAME[function],
            ),
        ),
        (
            math_line(rf"\{function}\theta = \frac{{{_n(top)}}}{{{_n(bottom)}}}"),
            math_line(
                rf"\theta = \{function}^{{-1}}\left(\frac{{{_n(top)}}}{{{_n(bottom)}}}\right)"
            ),
        ),
        _degrees(round(angle, 1)) if abs(angle - round(angle)) > 1e-9 else _degrees(round(angle)),
    )


def _right_side_from_angle(numbers: list[float], words: list[str]) -> _Solved | None:
    angle, value = numbers
    known, target = words
    if not 0 < angle < 90:
        return None
    radians = math.radians(angle)
    rules = {
        ("hypotenuse", "opposite"): ("sin", lambda: value * math.sin(radians)),
        ("hypotenuse", "adjacent"): ("cos", lambda: value * math.cos(radians)),
        ("adjacent", "opposite"): ("tan", lambda: value * math.tan(radians)),
        ("opposite", "adjacent"): ("tan", lambda: value / math.tan(radians)),
        ("opposite", "hypotenuse"): ("sin", lambda: value / math.sin(radians)),
        ("adjacent", "hypotenuse"): ("cos", lambda: value / math.cos(radians)),
    }
    rule = rules.get((known, target))
    if rule is None:
        return None
    function, compute = rule
    result = compute()
    multiply = (known, target) in {
        ("hypotenuse", "opposite"),
        ("hypotenuse", "adjacent"),
        ("adjacent", "opposite"),
    }
    substitution = (
        rf"\text{{{target}}} = {_n(value)}\{function} {_degrees(angle)}"
        if multiply
        else rf"\text{{{target}}} = \frac{{{_n(value)}}}{{\{function} {_degrees(angle)}}}"
    )
    over = {
        "sin": ("opposite", "hypotenuse"),
        "cos": ("adjacent", "hypotenuse"),
        "tan": ("opposite", "adjacent"),
    }[function]
    return _Solved(
        (math_line(rf"\theta = {_degrees(angle)}"), math_line(rf"\text{{{known}}} = {_n(value)}")),
        (math_line(rf"\text{{{target}}}"),),
        (
            math_line(
                rf"\{function}\theta = \frac{{\text{{{over[0]}}}}}{{\text{{{over[1]}}}}}",
                _RATIO_NAME[function],
            ),
        ),
        (math_line(substitution),),
        _n(round(result, 10))
        if abs(result - round(result)) < 1e-9
        else rf"\approx {_approx(result)}",
    )
