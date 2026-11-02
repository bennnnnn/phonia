"""Scan-friendly worked layouts for solver-verified geometry replies.

The geometry solver remains the source of every number. These layouts only
turn its validated dimensions and result into the familiar school sequence:
given values, requested quantity, named formula, and substitution. What was
asked comes from the intent's ``GeometryRequest``, never from the question.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.modules.math.schemas import GeometryRequest
from app.modules.math.schemas.geometry_request import GeometryQuantity, GeometryShape
from app.modules.math.tools.direct_geometry_working import (
    circles,
    quadrilaterals,
    solids,
    triangles,
)
from app.modules.math.tools.direct_geometry_working.layout import Working

_WORKINGS: dict[tuple[GeometryShape, GeometryQuantity], Working] = {
    ("rectangle", "area"): quadrilaterals.rectangle_area,
    ("rectangle", "perimeter"): quadrilaterals.rectangle_perimeter,
    ("rectangle", "diagonal"): quadrilaterals.rectangle_diagonal,
    ("rectangle", "area_and_perimeter"): quadrilaterals.rectangle_area_and_perimeter,
    ("square", "area"): quadrilaterals.square_area,
    ("square", "perimeter"): quadrilaterals.square_perimeter,
    ("square", "diagonal"): quadrilaterals.square_diagonal,
    ("parallelogram", "area"): quadrilaterals.parallelogram_area,
    ("parallelogram", "perimeter"): quadrilaterals.parallelogram_perimeter,
    ("trapezoid", "area"): quadrilaterals.trapezoid_area,
    ("triangle", "area"): triangles.triangle_area,
    ("right_triangle", "area"): triangles.triangle_area,
    ("right_triangle", "hypotenuse"): triangles.right_triangle_hypotenuse,
    ("right_triangle", "perimeter"): triangles.right_triangle_perimeter,
    ("triangle_sides", "area"): triangles.triangle_sides_area,
    ("triangle_sides", "perimeter"): triangles.triangle_sides_perimeter,
    ("circle", "area"): circles.circle_area,
    ("circle", "circumference"): circles.circle_circumference,
    ("circle", "diameter"): circles.circle_diameter,
    ("sector", "area"): circles.sector_area,
    ("sector", "arc_length"): circles.sector_arc_length,
    ("cube", "volume"): solids.cube,
    ("cube", "surface_area"): solids.cube,
    ("rectangular_prism", "volume"): solids.rectangular_prism,
    ("rectangular_prism", "surface_area"): solids.rectangular_prism,
    ("cylinder", "volume"): solids.cylinder,
    ("cylinder", "surface_area"): solids.cylinder,
    ("cone", "volume"): solids.cone,
    ("cone", "surface_area"): solids.cone,
    ("sphere", "volume"): solids.sphere,
    ("sphere", "surface_area"): solids.sphere,
    ("pyramid", "volume"): solids.square_pyramid,
    ("pyramid", "surface_area"): solids.square_pyramid,
}


def format_direct_geometry_working(
    request: GeometryRequest | None,
    spec: Mapping[str, object],
    answer: str,
    approximate: bool = False,
) -> str | None:
    """Lay out one verified measurement from its figure, without recomputing it.

    A rounded answer (the root of 34 as 5.831) ends its working with ≈, as its card does."""
    result = answer.strip()
    working = None if request is None else _WORKINGS.get((request.kind, request.quantity))
    if request is None or working is None or not result:
        return None
    laid_out = working(request, spec, result)
    if laid_out is None or not approximate:
        return laid_out
    head, equals, tail = laid_out.rpartition(f"= {result}")
    return f"{head}\\approx {result}{tail}" if equals else laid_out


def format_direct_solid_working(
    request: GeometryRequest | None, answer: str, approximate: bool = False
) -> str | None:
    """The same layout for a solid, whose measures travel on the request."""
    if request is None or request.solid is None:
        return None
    return format_direct_geometry_working(request, request.solid.model_dump(), answer, approximate)
