"""Squares, rhombuses, equilateral triangles, cube and cuboid diagonals, and angle facts."""

from __future__ import annotations

import math
from fractions import Fraction

from app.modules.math.tools.school.geometry_measures.working import (
    _approx,
    _degrees,
    _n,
    _Solved,
    _surd_answer,
    _unit,
)
from app.services.workout import math_line


def _square_from_diagonal(numbers: list[float], words: list[str]) -> _Solved | None:
    asked = words[0]
    unit = words[1] if len(words) > 1 else None
    d = numbers[0]
    given = (math_line(f"d = {_n(d)}", "diagonal"),)
    if asked == "area":
        return _Solved(
            given,
            (math_line("A", "area"),),
            (math_line(r"A = \frac{d^2}{2}", "A square's diagonal is s\\sqrt{2}"),),
            (math_line(rf"A = \frac{{{_n(d)}^2}}{{2}} = \frac{{{_n(d * d)}}}{{2}}"),),
            f"{_n(d * d / 2)}{_unit(unit, 2)}",
        )
    side = d / math.sqrt(2)
    if asked == "side":
        return _Solved(
            given,
            (math_line("s", "side"),),
            (math_line(r"d = s\sqrt{2}", "Pythagorean theorem on half the square"),),
            (math_line(rf"s = \frac{{{_n(d)}}}{{\sqrt{{2}}}}"),),
            _surd_answer(d * d / 2, unit),
        )
    return _Solved(
        given,
        (math_line("P", "perimeter"),),
        (math_line(r"P = 4s, \quad s = \frac{d}{\sqrt{2}}"),),
        (math_line(rf"P = 4 \times \frac{{{_n(d)}}}{{\sqrt{{2}}}} = {_n(2 * d)}\sqrt{{2}}"),),
        rf"{_n(2 * d)}\sqrt{{2}} \approx {_approx(4 * side)}{_unit(unit)}",
    )


def _rhombus(numbers: list[float], words: list[str]) -> _Solved | None:
    p, q = numbers[0], numbers[1]
    unit = words[0] if words else None
    return _Solved(
        (math_line(f"d_1 = {_n(p)}"), math_line(f"d_2 = {_n(q)}")),
        (math_line("A", "area"),),
        (math_line(r"A = \frac{d_1 d_2}{2}", "Rhombus or kite area"),),
        (math_line(rf"A = \frac{{{_n(p)} \times {_n(q)}}}{{2}} = \frac{{{_n(p * q)}}}{{2}}"),),
        f"{_n(p * q / 2)}{_unit(unit, 2)}",
    )


def _equilateral(numbers: list[float], words: list[str]) -> _Solved | None:
    asked = words[0]
    unit = words[1] if len(words) > 1 else None
    s = numbers[0]
    given = (math_line(f"s = {_n(s)}", "side"),)
    if asked == "perimeter":
        return _Solved(
            given,
            (math_line("P"),),
            (math_line("P = 3s"),),
            (math_line(f"P = 3({_n(s)})"),),
            f"{_n(3 * s)}{_unit(unit)}",
        )
    if asked in {"height", "altitude"}:
        exact = rf"{_n(s / 2)}\sqrt{{3}}" if s % 2 == 0 else rf"\frac{{{_n(s)}\sqrt{{3}}}}{{2}}"
        return _Solved(
            given,
            (math_line("h", "height"),),
            (math_line(r"h = \frac{\sqrt{3}}{2}s", "Pythagorean theorem on half the triangle"),),
            (math_line(rf"h = \frac{{\sqrt{{3}}}}{{2}}({_n(s)})"),),
            rf"{exact} \approx {_approx(math.sqrt(3) / 2 * s)}{_unit(unit)}",
        )
    coefficient = Fraction(s * s).limit_denominator(100) / 4
    exact = (
        rf"{coefficient.numerator}\sqrt{{3}}"
        if coefficient.denominator == 1
        else rf"\frac{{{coefficient.numerator}\sqrt{{3}}}}{{{coefficient.denominator}}}"
    )
    return _Solved(
        given,
        (math_line("A", "area"),),
        (math_line(r"A = \frac{\sqrt{3}}{4}s^2", "Equilateral triangle area"),),
        (math_line(rf"A = \frac{{\sqrt{{3}}}}{{4}}({_n(s)})^2"),),
        rf"{exact} \approx {_approx(math.sqrt(3) / 4 * s * s)}{_unit(unit, 2)}",
    )


def _cube_diagonal(numbers: list[float], words: list[str]) -> _Solved | None:
    s = numbers[0]
    unit = words[0] if words else None
    return _Solved(
        (math_line(f"s = {_n(s)}", "edge"),),
        (math_line("d", "space diagonal"),),
        (math_line(r"d = \sqrt{s^2 + s^2 + s^2} = s\sqrt{3}", "Pythagorean theorem in 3D"),),
        (math_line(rf"d = {_n(s)}\sqrt{{3}}"),),
        rf"{_n(s)}\sqrt{{3}} \approx {_approx(s * math.sqrt(3))}{_unit(unit)}",
    )


def _cuboid_diagonal(numbers: list[float], words: list[str]) -> _Solved | None:
    length, width, height = numbers
    unit = words[0] if words else None
    square = length**2 + width**2 + height**2
    return _Solved(
        (
            math_line(f"l = {_n(length)}"),
            math_line(f"w = {_n(width)}"),
            math_line(f"h = {_n(height)}"),
        ),
        (math_line("d", "space diagonal"),),
        (math_line(r"d = \sqrt{l^2 + w^2 + h^2}", "Pythagorean theorem in 3D"),),
        (
            math_line(
                rf"d = \sqrt{{{_n(length)}^2 + {_n(width)}^2 + {_n(height)}^2}}"
                rf" = \sqrt{{{_n(square)}}}"
            ),
        ),
        _surd_answer(square, unit),
    )


def _third_angle(numbers: list[float], words: list[str]) -> _Solved | None:
    a, b = numbers
    if a + b >= 180 or min(a, b) <= 0:
        return None
    return _Solved(
        (math_line(f"{_degrees(a)},\\ {_degrees(b)}", "two angles"),),
        (math_line("x", "the third angle"),),
        (math_line(r"\text{angles in a triangle} = 180^\circ"),),
        (math_line(rf"x = 180^\circ - {_degrees(a)} - {_degrees(b)}"),),
        _degrees(180 - a - b),
    )


def _isosceles(numbers: list[float], words: list[str]) -> _Solved | None:
    given_kind, asked_kind = words[0], words[1]
    angle = numbers[0]
    if given_kind == "base" and asked_kind != "base":
        if not 0 < angle < 90:
            return None
        return _Solved(
            (math_line(_degrees(angle), "each base angle"),),
            (math_line("x", "the apex angle"),),
            (math_line(r"x + 2(\text{base angle}) = 180^\circ", "The base angles are equal"),),
            (math_line(rf"x = 180^\circ - 2({_degrees(angle)})"),),
            _degrees(180 - 2 * angle),
        )
    if given_kind != "base" and asked_kind == "base":
        if not 0 < angle < 180:
            return None
        return _Solved(
            (math_line(_degrees(angle), "the apex angle"),),
            (math_line("x", "each base angle"),),
            (math_line(r"2x + \text{apex angle} = 180^\circ", "The base angles are equal"),),
            (math_line(rf"x = \frac{{180^\circ - {_degrees(angle)}}}{{2}}"),),
            _degrees((180 - angle) / 2),
        )
    return None


def _supplement(numbers: list[float], words: list[str]) -> _Solved | None:
    angle = numbers[0]
    if not 0 < angle < 180:
        return None
    return _Solved(
        (math_line(_degrees(angle)),),
        (math_line("x", "its supplement"),),
        (math_line(r"x + \text{angle} = 180^\circ", "Supplementary angles"),),
        (math_line(rf"x = 180^\circ - {_degrees(angle)}"),),
        _degrees(180 - angle),
    )


def _complement(numbers: list[float], words: list[str]) -> _Solved | None:
    angle = numbers[0]
    if not 0 < angle < 90:
        return None
    return _Solved(
        (math_line(_degrees(angle)),),
        (math_line("x", "its complement"),),
        (math_line(r"x + \text{angle} = 90^\circ", "Complementary angles"),),
        (math_line(rf"x = 90^\circ - {_degrees(angle)}"),),
        _degrees(90 - angle),
    )


def _polygon_sides(numbers: list[float], words: list[str]) -> _Solved | None:
    kind, angle = words[0], numbers[0]
    exterior = angle if kind == "exterior" else 180 - angle
    if not 0 < exterior < 180:
        return None
    sides = 360 / exterior
    if abs(sides - round(sides)) > 1e-9:
        return None
    rows = []
    if kind == "interior":
        rows.append(
            math_line(
                rf"\text{{exterior angle}} = 180^\circ - {_degrees(angle)} = {_degrees(exterior)}"
            )
        )
    rows.append(math_line(rf"n = \frac{{360^\circ}}{{{_degrees(exterior)}}}"))
    return _Solved(
        (math_line(_degrees(angle), f"each {kind} angle"),),
        (math_line("n", "the number of sides"),),
        (math_line(r"n = \frac{360^\circ}{\text{exterior angle}}", "Exterior angles add to 360°"),),
        tuple(rows),
        str(round(sides)),
    )
