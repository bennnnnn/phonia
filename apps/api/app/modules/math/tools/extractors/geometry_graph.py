"""Geometry and graph intent extractors, in the order extraction tries them."""

from __future__ import annotations

from app.modules.math.tools.extractors.geometry import (
    _extract_circle_intent,
    _extract_parallelogram_intent,
    _extract_rectangle_intent,
    _extract_right_triangle_intent,
    _extract_sector_intent,
    _extract_solid_intent,
    _extract_square_intent,
    _extract_trapezoid_intent,
    _extract_triangle_angles_intent,
    _extract_triangle_intent,
    _extract_triangle_sides_intent,
)
from app.modules.math.tools.extractors.graph import (
    _extract_graph_intent,
    _extract_graph_pair_intent,
    _extract_point_intent,
    _extract_polar_or_parametric_intent,
    _extract_vertical_intent,
)

SOLID_EXTRACTOR = _extract_solid_intent
GEOMETRY_GRAPH_EXTRACTORS = (
    _extract_rectangle_intent,
    _extract_square_intent,
    _extract_sector_intent,
    _extract_circle_intent,
    _extract_trapezoid_intent,
    _extract_parallelogram_intent,
    _extract_right_triangle_intent,
    _extract_triangle_sides_intent,
    _extract_triangle_angles_intent,
    _extract_triangle_intent,
    _extract_point_intent,
    _extract_vertical_intent,
    _extract_polar_or_parametric_intent,
    _extract_graph_pair_intent,
    _extract_graph_intent,
)
