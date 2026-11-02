"""Workings for solids: volume and total surface area.

A solid has no diagram, so its measures are the ones the request carries.
"""

from __future__ import annotations

import math
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


def cube(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    side = number(spec.get("side"))
    if side is None:
        return None
    givens = [given("Side length", "s", side, figure_unit(spec))]
    if request.quantity == "volume":
        return section(
            givens,
            "Volume ($V$)",
            "Cube volume formula",
            [r"V = s^3"],
            [rf"V = {display(side)}^3 = {result}"],
        )
    return section(
        givens,
        "Surface area ($S$)",
        "Cube surface area formula",
        [r"S = 6s^2"],
        [rf"S = 6({display(side)})^2 = {result}"],
    )


def rectangular_prism(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    # The solver reads the first edge as the length and the second as the width.
    length, width, height = (number(spec.get(key)) for key in ("width", "depth", "height"))
    if length is None or width is None or height is None:
        return None
    unit = figure_unit(spec)
    givens = [
        given("Length", "l", length, unit),
        given("Width", "w", width, unit),
        given("Height", "h", height, unit),
    ]
    ls, ws, hs = display(length), display(width), display(height)
    if request.quantity == "volume":
        return section(
            givens,
            "Volume ($V$)",
            "Rectangular prism volume formula",
            [r"V = lwh"],
            [rf"V = {ls} \times {ws} \times {hs} = {result}"],
        )
    faces = rf"{ls}\times{ws} + {ls}\times{hs} + {ws}\times{hs}"
    return section(
        givens,
        "Surface area ($S$)",
        "Rectangular prism surface area formula",
        [r"S = 2(lw+lh+wh)"],
        [rf"S = 2({faces}) = {result}"],
    )


def _radius_height(spec: Spec) -> tuple[float, float, list[str]] | None:
    radius, height = number(spec.get("radius")), number(spec.get("height"))
    if radius is None or height is None:
        return None
    unit = figure_unit(spec)
    return radius, height, [given("Radius", "r", radius, unit), given("Height", "h", height, unit)]


def cylinder(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    solid = _radius_height(spec)
    if solid is None:
        return None
    radius, height, givens = solid
    r, h = display(radius), display(height)
    if request.quantity == "volume":
        return section(
            givens,
            "Volume ($V$)",
            "Cylinder volume formula",
            [r"V = \pi r^2h"],
            [rf"V = \pi({r})^2({h}) \approx {result}"],
        )
    return section(
        givens,
        "Surface area ($S$)",
        "Closed cylinder surface area formula",
        [r"S = 2\pi r(r+h)"],
        [rf"S = 2\pi({r})({r}+{h}) \approx {result}"],
    )


def cone(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    solid = _radius_height(spec)
    if solid is None:
        return None
    radius, height, givens = solid
    r, h = display(radius), display(height)
    if request.quantity == "volume":
        return section(
            givens,
            "Volume ($V$)",
            "Cone volume formula",
            [r"V = \frac{1}{3}\pi r^2h"],
            [rf"V = \frac{{1}}{{3}}\pi({r})^2({h}) \approx {result}"],
        )
    slant = display(math.hypot(radius, height))
    return section(
        givens,
        "Surface area ($S$)",
        "Cone surface area formula",
        [r"l = \sqrt{r^2+h^2}", r"S = \pi r(r+l)"],
        [rf"l = \sqrt{{{r}^2+{h}^2}} = {slant}", rf"S = \pi({r})({r}+{slant}) \approx {result}"],
    )


def sphere(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    radius = number(spec.get("radius"))
    if radius is None:
        return None
    givens = [given("Radius", "r", radius, figure_unit(spec))]
    if request.quantity == "volume":
        return section(
            givens,
            "Volume ($V$)",
            "Sphere volume formula",
            [r"V = \frac{4}{3}\pi r^3"],
            [rf"V = \frac{{4}}{{3}}\pi({display(radius)})^3 \approx {result}"],
        )
    return section(
        givens,
        "Surface area ($S$)",
        "Sphere surface area formula",
        [r"S = 4\pi r^2"],
        [rf"S = 4\pi({display(radius)})^2 \approx {result}"],
    )


def square_pyramid(request: GeometryRequest, spec: Spec, result: str) -> str | None:
    side, height = number(spec.get("side")), number(spec.get("height"))
    if side is None or height is None:
        return None
    unit = figure_unit(spec)
    givens = [given("Base side", "s", side, unit), given("Height", "h", height, unit)]
    s, h = display(side), display(height)
    if request.quantity == "volume":
        return section(
            givens,
            "Volume ($V$)",
            "Square-pyramid volume formula",
            [r"V = \frac{1}{3}s^2h"],
            [rf"V = \frac{{1}}{{3}}({s})^2({h}) = {result}"],
        )
    slant = display(math.hypot(height, side / 2))
    return section(
        givens,
        "Surface area ($S$)",
        "Square-pyramid surface-area formula",
        [r"l = \sqrt{h^2+(s/2)^2}", r"S = s^2+2sl"],
        [rf"l = \sqrt{{{h}^2+({s}/2)^2}} = {slant}", rf"S = {s}^2 + 2({s})({slant}) = {result}"],
    )
