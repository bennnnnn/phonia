"""Whole literal solid measurements may use their existing verified quantity."""

from __future__ import annotations

import re

from app.modules.math.match.geometry import classify_solid_shape, parse_solid
from app.modules.math.match.literal_geometry import GEOMETRY_DECIMAL, measurement_request
from app.modules.math.match.units import solid_length_unit, strip_geometry_length_units

_SIDE = re.compile(rf"(?:side|edge)\s+({GEOMETRY_DECIMAL})")
_TRIPLE = re.compile(
    rf"({GEOMETRY_DECIMAL})\s*(?:by|x|\u00d7)\s*"
    rf"({GEOMETRY_DECIMAL})\s*(?:by|x|\u00d7)\s*({GEOMETRY_DECIMAL})"
)
_RADIUS_HEIGHT = re.compile(
    rf"radius\s+({GEOMETRY_DECIMAL})\s+(?:and\s+)?height\s+({GEOMETRY_DECIMAL})"
)
_RADIUS = re.compile(rf"radius\s+({GEOMETRY_DECIMAL})")
_SIDE_HEIGHT = re.compile(
    rf"side\s+({GEOMETRY_DECIMAL})\s+(?:and\s+)?height\s+({GEOMETRY_DECIMAL})"
)


def solid_direct_request(text: str) -> bool | None:
    """Validate a whole request against the existing extractor, without re-solving.

    None denotes another family. False prevents a partial solid request from
    slipping through the generic prose allowance. Only ordinary closed solids
    with every required literal dimension qualify; square pyramids are explicit.
    """
    request = " ".join(text.lower().split())
    shape = classify_solid_shape(request)
    if shape is None:
        return None
    if len(text) > 1000:
        return False
    parsed = measurement_request(request)
    if parsed is None:
        return False
    quantity, body = parsed
    if quantity not in {"volume", "surface area", "total surface area"}:
        return False
    names: tuple[str, ...]
    fields: tuple[str, ...]
    if shape == "cube":
        names, pattern, fields = ("cube",), _SIDE, ("side",)
    elif shape == "rectangular_prism":
        names, pattern, fields = (
            ("rectangular prism", "cuboid"),
            _TRIPLE,
            ("width", "depth", "height"),
        )
    elif shape in {"cylinder", "cone"}:
        names, pattern, fields = (shape,), _RADIUS_HEIGHT, ("radius", "height")
    elif shape == "sphere":
        names, pattern, fields = ("sphere",), _RADIUS, ("radius",)
    elif shape == "pyramid":
        names, pattern, fields = ("square pyramid",), _SIDE_HEIGHT, ("side", "height")
    else:
        return False
    name = next((name for name in names if body.startswith(name + " ")), None)
    if name is None:
        return False
    dimensions = body[len(name) + 1 :]
    if dimensions.startswith("with "):
        dimensions = dimensions[5:]
    unit = solid_length_unit(dimensions)
    if unit is None:
        return False
    match = pattern.fullmatch(strip_geometry_length_units(dimensions).strip())
    if match is None:
        return False
    values = tuple(float(value) for value in match.groups())
    if any(not 0 < value <= 1_000_000 for value in values):
        return False
    actual = parse_solid(request)
    return bool(
        actual is not None
        and actual.shape == shape
        and actual.unit == unit
        and actual.wants_volume is (quantity == "volume")
        and actual.wants_surface_area is (quantity != "volume")
        and all(getattr(actual, key) == value for key, value in zip(fields, values, strict=True))
    )
