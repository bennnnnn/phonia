"""Workings for rectangles, squares, parallelograms and trapezoids."""

from __future__ import annotations

from collections.abc import Mapping

from app.modules.math.schemas import GeometryRequest
from app.modules.math.tools.direct_geometry_working.layout import (
    display,
    figure_unit,
    given,
    number,
    root_of_squares,
    section,
    unit_tex,
)

Spec = Mapping[str, object]


def _length_and_width(request: GeometryRequest, spec: Spec) -> tuple[float, float] | None:
    width, height = number(spec.get("width")), number(spec.get("height"))
    if width is None or height is None:
        return None
    if not request.named_sides and width > height:
        # "8 by 5": the length is the longer side. Named sides keep their names.
        width, height = height, width
    return height, width


def _rectangle_givens(length: float, width: float, unit: str) -> list[str]:
    return [given("Length", "l", length, unit), given("Width", "w", width, unit)]


def rectangle_area(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    sides = _length_and_width(request, spec)
    if sides is None:
        return None
    length, width = sides
    unit = figure_unit(spec)
    if request.target is not None:
        return _rectangle_side(request, length, width, unit, result)
    return section(
        _rectangle_givens(length, width, unit),
        "Area ($A$)",
        "Rectangle area formula",
        [r"A = l \times w"],
        [rf"A = {display(length)} \times {display(width)} = {result}"],
    )


def _rectangle_side(
    request: GeometryRequest, length: float, width: float, unit: str, result: str
) -> str:
    """The side an area question asks for, from the area and the other side."""
    area = display(request.given_area or 0)
    area_line = rf"Area: $A = {area}\,{unit_tex(unit)}^2$"
    if request.target == "length":
        return section(
            [area_line, given("Width", "w", width, unit)],
            "Length ($l$)",
            "Rectangle area formula",
            [r"A = l \times w"],
            [rf"l = \frac{{{area}}}{{{display(width)}}} = {result}"],
            solved=r"l = \frac{A}{w}",
        )
    return section(
        [area_line, given("Length", "l", length, unit)],
        "Width ($w$)",
        "Rectangle area formula",
        [r"A = l \times w"],
        [rf"w = \frac{{{area}}}{{{display(length)}}} = {result}"],
        solved=r"w = \frac{A}{l}",
    )


def rectangle_perimeter(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    sides = _length_and_width(request, spec)
    if sides is None:
        return None
    length, width = sides
    return section(
        _rectangle_givens(length, width, figure_unit(spec)),
        "Perimeter ($P$)",
        "Rectangle perimeter formula",
        [r"P = 2(l + w)"],
        [rf"P = 2({display(length)} + {display(width)}) = {result}"],
    )


def rectangle_diagonal(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    sides = _length_and_width(request, spec)
    if sides is None:
        return None
    length, width = sides
    return section(
        _rectangle_givens(length, width, figure_unit(spec)),
        "Diagonal ($d$)",
        "Pythagorean theorem",
        [r"d^2 = l^2 + w^2"],
        [root_of_squares("d", length, width, result)],
        solved=r"d = \sqrt{l^2 + w^2}",
    )


def rectangle_area_and_perimeter(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    sides = _length_and_width(request, spec)
    area, perimeter = number(spec.get("area")), number(spec.get("perimeter"))
    if sides is None or area is None or perimeter is None:
        return None
    length, width = sides
    return section(
        _rectangle_givens(length, width, figure_unit(spec)),
        "Area ($A$) and perimeter ($P$)",
        "Rectangle formulas",
        [r"A = l \times w", r"P = 2(l+w)"],
        [
            rf"A = {display(length)} \times {display(width)} = {display(area)}",
            rf"P = 2({display(length)}+{display(width)}) = {display(perimeter)}",
        ],
    )


def _square_side(spec: Spec) -> tuple[float, list[str]] | None:
    side = number(spec.get("side"))
    if side is None:
        return None
    return side, [given("Side length", "s", side, figure_unit(spec))]


def square_area(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    square = _square_side(spec)
    if square is None:
        return None
    side, givens = square
    return section(
        givens,
        "Area ($A$)",
        "Square area formula",
        [r"A = s^2"],
        [rf"A = {display(side)}^2 = {result}"],
    )


def square_perimeter(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    square = _square_side(spec)
    if square is None:
        return None
    side, givens = square
    return section(
        givens,
        "Perimeter ($P$)",
        "Square perimeter formula",
        [r"P = 4s"],
        [rf"P = 4 \times {display(side)} = {result}"],
    )


def square_diagonal(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    square = _square_side(spec)
    if square is None:
        return None
    side, givens = square
    return section(
        givens,
        "Diagonal ($d$)",
        "Pythagorean theorem",
        [r"d^2 = s^2 + s^2"],
        [rf"d = {display(side)}\sqrt{{2}} = {result}"],
        solved=r"d = s\sqrt{2}",
    )


def _parallelogram(spec: Spec) -> tuple[float, float, float, list[str]] | None:
    base, height, side = (number(spec.get(key)) for key in ("base", "height", "side"))
    if base is None or height is None or side is None:
        return None
    unit = figure_unit(spec)
    givens = [
        given("Base", "b", base, unit),
        given("Height", "h", height, unit),
        given("Side", "s", side, unit),
    ]
    return base, height, side, givens


def parallelogram_area(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    shape = _parallelogram(spec)
    if shape is None:
        return None
    base, height, _side, givens = shape
    return section(
        givens,
        "Area ($A$)",
        "Parallelogram area formula",
        [r"A = bh"],
        [rf"A = {display(base)} \times {display(height)} = {result}"],
    )


def parallelogram_perimeter(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    shape = _parallelogram(spec)
    if shape is None:
        return None
    base, _height, side, givens = shape
    return section(
        givens,
        "Perimeter ($P$)",
        "Parallelogram perimeter formula",
        [r"P = 2(b+s)"],
        [rf"P = 2({display(base)} + {display(side)}) = {result}"],
    )


def trapezoid_area(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    top, bottom, height = (number(spec.get(key)) for key in ("top", "bottom", "height"))
    if top is None or bottom is None or height is None:
        return None
    unit = figure_unit(spec)
    return section(
        [
            given("Top base", "a", top, unit),
            given("Bottom base", "b", bottom, unit),
            given("Height", "h", height, unit),
        ],
        "Area ($A$)",
        "Trapezoid area formula",
        [r"A = \frac{1}{2}(a+b)h"],
        [
            rf"A = \frac{{1}}{{2}}({display(top)}+{display(bottom)})"
            rf" \times {display(height)} = {result}"
        ],
    )
