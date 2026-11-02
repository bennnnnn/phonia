"""Workings for triangles: base and height, right triangles, and three sides."""

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
)

Spec = Mapping[str, object]


def _base_height(request: GeometryRequest, spec: Spec) -> tuple[float, float, list[str]] | None:
    base, height = number(spec.get("base")), number(spec.get("height"))
    if base is None or height is None:
        return None
    unit = figure_unit(spec)
    if request.kind == "right_triangle":
        # The legs are a and b, the names the Pythagorean theorem uses.
        return base, height, [given("Leg", "a", base, unit), given("Leg", "b", height, unit)]
    return base, height, [given("Base", "b", base, unit), given("Height", "h", height, unit)]


def triangle_area(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    triangle = _base_height(request, spec)
    if triangle is None:
        return None
    base, height, givens = triangle
    right = request.kind == "right_triangle"
    return section(
        givens,
        "Area ($A$)",
        "Right-triangle area formula" if right else "Triangle area formula",
        [r"A = \frac{1}{2}ab" if right else r"A = \frac{1}{2}bh"],
        [rf"A = \frac{{1}}{{2}} \times {display(base)} \times {display(height)} = {result}"],
    )


def _legs_and_hypotenuse(
    request: GeometryRequest, spec: Spec
) -> tuple[float, float, float, list[str]] | None:
    triangle = _base_height(request, spec)
    hypotenuse = number(spec.get("hypotenuse"))
    if triangle is None or hypotenuse is None:
        return None
    base, height, givens = triangle
    return base, height, hypotenuse, givens


def right_triangle_hypotenuse(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    triangle = _legs_and_hypotenuse(request, spec)
    if triangle is None:
        return None
    base, height, _hypotenuse, givens = triangle
    return section(
        givens,
        "Hypotenuse ($c$)",
        "Pythagorean theorem",
        [r"c^2 = a^2 + b^2"],
        [root_of_squares("c", base, height, result)],
        solved=r"c = \sqrt{a^2 + b^2}",
    )


def right_triangle_perimeter(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    triangle = _legs_and_hypotenuse(request, spec)
    if triangle is None:
        return None
    base, height, hypotenuse, givens = triangle
    return section(
        givens,
        "Perimeter ($P$)",
        "Right-triangle perimeter formula",
        [r"c = \sqrt{a^2 + b^2}", r"P = a + b + c"],
        [
            root_of_squares("c", base, height, display(hypotenuse)),
            rf"P = {display(base)} + {display(height)} + {display(hypotenuse)} = {result}",
        ],
    )


def _three_sides(spec: Spec) -> tuple[float, float, float, list[str]] | None:
    a, b, c = (number(spec.get(key)) for key in ("a", "b", "c"))
    if a is None or b is None or c is None:
        return None
    unit = figure_unit(spec)
    givens = [given("Side", "a", a, unit), given("Side", "b", b, unit), given("Side", "c", c, unit)]
    return a, b, c, givens


def triangle_sides_perimeter(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    triangle = _three_sides(spec)
    if triangle is None:
        return None
    a, b, c, givens = triangle
    return section(
        givens,
        "Perimeter ($P$)",
        "Triangle perimeter formula",
        [r"P = a + b + c"],
        [rf"P = {display(a)} + {display(b)} + {display(c)} = {result}"],
    )


def triangle_sides_area(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    """Heron's formula, from the semiperimeter."""
    triangle = _three_sides(spec)
    if triangle is None:
        return None
    a, b, c, givens = triangle
    half = (a + b + c) / 2
    s = display(half)
    # Every row: the differences, their product, then the root (no jump to the answer).
    factors = r" \cdot ".join(display(value) for value in (half, half - a, half - b, half - c))
    product = display(half * (half - a) * (half - b) * (half - c))
    return section(
        givens,
        "Area ($A$)",
        "Heron's formula",
        [r"s = \frac{a+b+c}{2}", r"A = \sqrt{s(s-a)(s-b)(s-c)}"],
        [
            rf"s = \frac{{{display(a)}+{display(b)}+{display(c)}}}{{2}} = {s}",
            rf"A = \sqrt{{{s}({s}-{display(a)})({s}-{display(b)})({s}-{display(c)})}}"
            rf" = \sqrt{{{factors}}} = \sqrt{{{product}}} = {result}",
        ],
    )
