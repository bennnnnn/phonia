"""Whole-request guards for already verified geometry measurements."""

from __future__ import annotations

import math
import re

from app.modules.math.match.literal_geometry import (
    GEOMETRY_DECIMAL as _DECIMAL,
)
from app.modules.math.match.literal_geometry import (
    RIGHT_TRIANGLE_LEGS as _RIGHT_LEGS,
)
from app.modules.math.match.literal_geometry import (
    literal_triangle_angles_draw,
    parse_named_rectangle_request,
)
from app.modules.math.match.literal_geometry import (
    measurement_request as _measurement_request,
)
from app.modules.math.match.units import solid_length_unit, strip_geometry_length_units
from app.services.solving import VerifiedMathBlock

_DIMENSIONS = re.compile(rf"({_DECIMAL})\s*(?:by|x|\u00d7|\*)\s*({_DECIMAL})")
_SIDES = re.compile(rf"sides?\s+({_DECIMAL})\s*(?:,|and)\s*({_DECIMAL})")


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def can_direct_rectangle(
    verified: VerifiedMathBlock, user_text: str, fences: list[dict[str, object]]
) -> bool:
    """Every requested dimension, unit and quantity must match the one diagram.

    This intentionally recognizes a small complete phrase, not extra glue words
    in the generic direct-answer matcher. Extra operations, shapes, teaching,
    malformed dimensions and unit changes retain the model path.
    """
    if len(user_text) > 1000 or len(fences) != 1 or fences[0].get("type") != "rectangle":
        return False
    named = parse_named_rectangle_request(user_text)
    if named is not None:
        geometry = fences[0]
        if (
            _finite_number(geometry.get("width")) != named.width
            or _finite_number(geometry.get("height")) != named.length
            or geometry.get("unit") != named.unit
            or geometry.get("show_angle") is not False
            or geometry.get("show_diagonal") is not (named.quantity == "diagonal")
            or geometry.get("show_perimeter")
            is not (named.quantity in {"perimeter", "area_and_perimeter"})
            or geometry.get("show_area")
            is not (
                named.quantity in {"area", "area_and_perimeter"} or named.given_area is not None
            )
        ):
            return False
        if named.quantity == "area_and_perimeter":
            area = _finite_number(geometry.get("area"))
            perimeter = _finite_number(geometry.get("perimeter"))
            answer = (verified.canonical_answer or "").strip()
            return (
                area is not None
                and perimeter is not None
                and answer
                == rf"A = {area:g}\ \mathrm{{{named.unit}}}^{{2}},\quad "
                rf"P = {perimeter:g}\ \mathrm{{{named.unit}}}"
            )
        field = named.target or named.quantity
        field = "height" if field == "length" else field
        value = _finite_number(geometry.get(field))
        answer = (verified.canonical_answer or "").strip()
        if value is None or value <= 0 or not answer or len(answer) > 64:
            return False
        try:
            return float(answer) == value
        except ValueError:
            return False
    parsed = _measurement_request(user_text)
    if parsed is None:
        return False
    quantity, request = parsed
    if quantity not in {"area", "perimeter", "diagonal"}:
        return False
    if not request.startswith("rectangle "):
        return False
    dimensions = request[10:]
    if dimensions.startswith("with "):
        dimensions = dimensions[5:]
    unit = solid_length_unit(dimensions)
    if unit is None:
        return False
    literal_dimensions = strip_geometry_length_units(dimensions).strip()
    pair = _DIMENSIONS.fullmatch(literal_dimensions) or _SIDES.fullmatch(literal_dimensions)
    if pair is None:
        return False
    width, height = (float(value) for value in pair.groups())
    if not (0 < width <= 1_000_000 and 0 < height <= 1_000_000):
        return False
    geometry = fences[0]
    if (
        _finite_number(geometry.get("width")) != width
        or _finite_number(geometry.get("height")) != height
        or geometry.get("unit") != unit
        or geometry.get("show_angle") is not False
    ):
        return False
    for flag in ("area", "perimeter", "diagonal"):
        if geometry.get(f"show_{flag}") is not (flag == quantity):
            return False
    value = _finite_number(geometry.get(quantity))
    answer = (verified.canonical_answer or "").strip()
    if value is None or value <= 0 or not answer or len(answer) > 64:
        return False
    try:
        return float(answer) == value
    except ValueError:
        return False


_SQUARE_SIDE = re.compile(rf"side\s+({_DECIMAL})")
_BASE_HEIGHT = re.compile(rf"base\s+({_DECIMAL})\s+(?:and\s+)?height\s+({_DECIMAL})")
_THREE_SIDES = re.compile(
    rf"sides\s+({_DECIMAL})\s*,\s*({_DECIMAL})\s*(?:,\s*(?:and\s+)?|and\s+)({_DECIMAL})"
)
_PARALLELOGRAM = re.compile(
    rf"base\s+({_DECIMAL})\s+(?:and\s+)?height\s+({_DECIMAL})\s+(?:and\s+)?side\s+({_DECIMAL})"
)
_TRAPEZOID = re.compile(
    rf"top\s+({_DECIMAL})\s+(?:and\s+)?bottom\s+({_DECIMAL})\s+(?:and\s+)?height\s+({_DECIMAL})"
)
_TRAPEZOID_BASES = re.compile(
    rf"bases\s+({_DECIMAL})\s+(?:and|,)\s+({_DECIMAL})\s+(?:and\s+)?height\s+({_DECIMAL})"
)
_CIRCLE = re.compile(rf"(radius|diameter)\s+({_DECIMAL})")
_DEGREE_ANGLE = re.compile(rf"{_DECIMAL}(?:\s*(?:degrees|degree|°))?")
_SECTOR = re.compile(
    rf"radius\s+({_DECIMAL})\s+(?:and\s+)?angle\s+({_DECIMAL})(?:\s*(?:degrees|degree|°))?"
)


def can_direct_curved_or_slanted_geometry(
    verified: VerifiedMathBlock, user_text: str, fences: list[dict[str, object]]
) -> bool:
    """One complete measurement with literal dimensions and canonical precision."""
    if len(user_text) > 1000 or len(fences) != 1:
        return False
    geometry = fences[0]
    parsed = _measurement_request(user_text)
    if parsed is None:
        return False
    quantity, request = parsed
    kind = geometry.get("type")
    shapes: tuple[str, ...]
    keys: tuple[str, ...]
    if kind == "parallelogram":
        shapes, pattern, keys = ("parallelogram",), _PARALLELOGRAM, ("base", "height", "side")
        quantities = {"area", "perimeter"}
    elif kind == "trapezoid":
        shapes, pattern, keys = ("trapezoid", "trapezium"), _TRAPEZOID, ("top", "bottom", "height")
        quantities = {"area"}
    elif kind == "circle":
        shapes, pattern, keys = ("circle",), _CIRCLE, ("radius",)
        quantities = {"area", "circumference", "diameter"}
    elif kind == "sector":
        shapes, pattern, keys = ("circle sector", "sector"), _SECTOR, ("radius", "angle_deg")
        quantities = {"area", "arc length"}
    else:
        return False
    if quantity not in quantities:
        return False
    shape = next((shape for shape in shapes if request.startswith(shape + " ")), None)
    if shape is None:
        return False
    dimensions = request[len(shape) + 1 :]
    if dimensions.startswith("with "):
        dimensions = dimensions[5:]
    if kind == "sector" and _DEGREE_ANGLE.fullmatch(dimensions.partition(" angle ")[2]) is None:
        return False
    unit = solid_length_unit(dimensions)
    if unit is None or geometry.get("unit") != unit:
        return False
    literal_dimensions = strip_geometry_length_units(dimensions).strip()
    match = pattern.fullmatch(literal_dimensions)
    if match is None and kind == "trapezoid":
        match = _TRAPEZOID_BASES.fullmatch(literal_dimensions)
    if match is None:
        return False
    values: tuple[float, ...]
    if kind == "circle":
        dimension, literal = match.groups()
        amount = float(literal)
        if not 0 < amount <= 1_000_000:
            return False
        values = (amount / 2 if dimension == "diameter" else amount,)
        for flag in ("area", "circumference", "diameter"):
            expected = flag == quantity or (flag == "diameter" and dimension == "diameter")
            if geometry.get(f"show_{flag}") is not expected:
                return False
    else:
        values = tuple(float(value) for value in match.groups())
    if any(not 0 < value <= 1_000_000 for value in values):
        return False
    if any(
        _finite_number(geometry.get(key)) != value for key, value in zip(keys, values, strict=True)
    ):
        return False
    if kind == "parallelogram" and values[2] < values[1]:
        return False
    if kind in {"parallelogram", "trapezoid"} and geometry.get("show_angle") is not False:
        return False
    if kind == "sector" and values[1] > 360:
        return False
    field = "arc_length" if quantity == "arc length" else quantity
    value = _finite_number(geometry.get(field))
    if value is None or value <= 0:
        return False
    # These blocks already round circle measures/arc lengths to two places;
    # compare their existing presentation, without tolerances or recomputation.
    if (kind == "circle" and quantity != "diameter") or field == "arc_length":
        from app.modules.math.solve.geometry import format_geometry_decimal

        expected = format_geometry_decimal(value)
    else:
        expected = format(value, "g")
    return (verified.canonical_answer or "").strip() == expected


def can_direct_triangle_angles(user_text: str, fences: list[dict[str, object]]) -> bool:
    """Draw one fully specified angle triple, with relative lengths only."""
    if len(user_text) > 1000 or len(fences) != 1:
        return False
    spec = fences[0]
    if (
        spec.get("type") != "triangle_sides"
        or spec.get("relative_lengths") is not True
        or spec.get("unit") != "units"
        or spec.get("area") is not None
        or spec.get("perimeter") is not None
    ):
        return False
    angles = literal_triangle_angles_draw(user_text)
    if angles is None:
        return False
    from app.modules.math.solve.triangle import cosine_rule_angle, triangle_valid

    sides = [_finite_number(spec.get(key)) for key in ("a", "b", "c")]
    if any(value is None or not 0 < value <= 1_000_000 for value in sides):
        return False
    a, b, c = (float(value) for value in sides if value is not None)
    if not triangle_valid(a, b, c):
        return False
    # Canonical side lengths are rounded to four decimal places.
    return all(
        abs(float(cosine_rule_angle(adjacent_a, adjacent_b, opposite)) - angle) <= 0.01
        for opposite, adjacent_a, adjacent_b, angle in (
            (a, b, c, angles[0]),
            (b, a, c, angles[1]),
            (c, a, b, angles[2]),
        )
    )


def can_direct_square_or_triangle(
    verified: VerifiedMathBlock, user_text: str, fences: list[dict[str, object]]
) -> bool:
    """Recognize only a complete literal single-measure square/triangle request."""
    if len(user_text) > 1000 or len(fences) != 1:
        return False
    geometry = fences[0]
    kind = geometry.get("type")
    parsed = _measurement_request(user_text)
    if parsed is None:
        return False
    quantity, request = parsed
    keys: tuple[str, ...]
    if kind == "square":
        shape, pattern, keys = "square ", _SQUARE_SIDE, ("side",)
        quantities = {"area", "perimeter", "diagonal"}
    elif kind == "triangle":
        shape, pattern, keys = "triangle ", _BASE_HEIGHT, ("base", "height")
        quantities = {"area"}
    elif kind == "right_triangle":
        shape, pattern, keys = "right triangle ", _RIGHT_LEGS, ("base", "height")
        quantities = {"area", "perimeter", "hypotenuse"}
    elif kind == "triangle_sides":
        shape, pattern, keys = "triangle ", _THREE_SIDES, ("a", "b", "c")
        quantities = {"area", "perimeter"}
    else:
        return False
    if quantity not in quantities or not request.startswith(shape):
        return False
    dimensions = request[len(shape) :]
    if dimensions.startswith("with "):
        dimensions = dimensions[5:]
    unit = solid_length_unit(dimensions)
    if unit is None or geometry.get("unit") != unit:
        return False
    match = pattern.fullmatch(strip_geometry_length_units(dimensions).strip())
    if match is None:
        return False
    values = tuple(float(value) for value in match.groups())
    if any(not 0 < value <= 1_000_000 for value in values):
        return False
    if any(
        _finite_number(geometry.get(key)) != value for key, value in zip(keys, values, strict=True)
    ):
        return False
    if kind == "square":
        side = values[0]
        if any(_finite_number(geometry.get(key)) != side for key in ("width", "height")):
            return False
        for flag in ("area", "perimeter", "diagonal"):
            if geometry.get(f"show_{flag}") is not (flag == quantity):
                return False
    elif kind == "triangle" and (
        geometry.get("show_angle") is not False or geometry.get("show_ticks") is not False
    ):
        return False
    value = _finite_number(geometry.get(quantity))
    answer = (verified.canonical_answer or "").strip()
    if value is None or value <= 0 or not answer or len(answer) > 64:
        return False
    try:
        return float(answer) == value
    except ValueError:
        return False
