"""Workings for circles and sectors."""

from __future__ import annotations

from collections.abc import Mapping

from app.modules.math.schemas import GeometryRequest
from app.modules.math.tools.direct_geometry_working.layout import (
    display,
    figure_unit,
    given,
    number,
    section,
)

Spec = Mapping[str, object]


def _circle(spec: Spec) -> tuple[float, bool, list[str]] | None:
    """The radius, whether the working starts from the diameter, and the given line.

    The figure labels the diameter whenever the question names one, given or
    asked, and the working then starts from it too.
    """
    radius = number(spec.get("radius"))
    if radius is None:
        return None
    from_diameter = spec.get("show_diameter") is True
    unit = figure_unit(spec)
    if from_diameter:
        return radius, True, [given("Diameter", "d", radius * 2, unit)]
    return radius, False, [given("Radius", "r", radius, unit)]


def circle_area(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    circle = _circle(spec)
    if circle is None:
        return None
    radius, from_diameter, givens = circle
    area = rf"A = \pi({display(radius)})^2 = {display(radius**2)}\pi \approx {result}"
    # The section's name labels the first formula, so the area law leads.
    if from_diameter:
        formulas = [r"A = \pi r^2", r"r = \frac{d}{2}"]
        substitutions = [rf"r = \frac{{{display(radius * 2)}}}{{2}} = {display(radius)}", area]
    else:
        formulas, substitutions = [r"A = \pi r^2"], [area]
    return section(givens, "Area ($A$)", "Circle area formula", formulas, substitutions)


def circle_circumference(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    circle = _circle(spec)
    if circle is None:
        return None
    radius, from_diameter, givens = circle
    diameter = radius * 2
    if from_diameter:
        # From the diameter in one step: C = \pi d.
        formulas = [r"C = \pi d"]
        substitutions = [rf"C = \pi({display(diameter)}) = {display(diameter)}\pi \approx {result}"]
    else:
        formulas = [r"C = 2\pi r"]
        substitutions = [rf"C = 2\pi({display(radius)}) = {display(diameter)}\pi \approx {result}"]
    return section(
        givens, "Circumference ($C$)", "Circle circumference formula", formulas, substitutions
    )


def circle_diameter(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    circle = _circle(spec)
    if circle is None:
        return None
    radius, _from_diameter, givens = circle
    return section(
        givens,
        "Diameter ($d$)",
        "Radius-diameter relation",
        [r"d = 2r"],
        [rf"d = 2 \times {display(radius)} = {result}"],
    )


def _sector(spec: Spec) -> tuple[float, float, list[str]] | None:
    radius, angle = number(spec.get("radius")), number(spec.get("angle_deg"))
    if radius is None or angle is None:
        return None
    givens = [
        given("Radius", "r", radius, figure_unit(spec)),
        rf"Central angle: $\theta = {display(angle)}^\circ$",
    ]
    return radius, angle, givens


def sector_area(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    sector = _sector(spec)
    if sector is None:
        return None
    radius, angle, givens = sector
    return section(
        givens,
        "Sector area ($A$)",
        "Sector area formula",
        [r"A = \frac{\theta}{360^\circ}\pi r^2"],
        [
            rf"A = \frac{{{display(angle)}^\circ}}{{360^\circ}}"
            rf"\pi({display(radius)})^2 \approx {result}"
        ],
    )


def sector_arc_length(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    sector = _sector(spec)
    if sector is None:
        return None
    radius, angle, givens = sector
    return section(
        givens,
        "Arc length ($L$)",
        "Arc length formula",
        [r"L = \frac{\theta}{360^\circ}(2\pi r)"],
        [
            rf"L = \frac{{{display(angle)}^\circ}}{{360^\circ}}"
            rf"(2\pi \times {display(radius)}) \approx {result}"
        ],
    )
