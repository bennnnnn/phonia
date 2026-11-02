"""A shape's unit and the measurement its question names, settled once at extraction."""

from __future__ import annotations

from pydantic import ValidationError

from app.modules.math.match.literal_geometry import (
    NamedRectangleRequest,
    measurement_request,
    parse_named_rectangle_request,
)
from app.modules.math.match.measure_relations import (
    measures_not_as_printed,
    surface_not_closed_total,
)
from app.modules.math.match.units import solid_length_unit
from app.modules.math.schemas import GeometryRequest, MathIntent, SolidGeometryInput
from app.modules.math.schemas.geometry_request import GeometryQuantity, GeometryShape
from app.modules.math.tools.school.geometry_measures import is_geometry_measure

_PLANE_SHAPES: dict[str, GeometryShape] = {
    "rectangle": "rectangle",
    "square": "square",
    "triangle": "triangle",
    "right_triangle": "right_triangle",
    "triangle_sides": "triangle_sides",
    "circle": "circle",
    "trapezoid": "trapezoid",
    "parallelogram": "parallelogram",
    "sector": "sector",
}
# What the literal measurement grammars call each quantity a working lays out.
_QUANTITIES: dict[str, GeometryQuantity] = {
    "area": "area",
    "perimeter": "perimeter",
    "area_and_perimeter": "area_and_perimeter",
    "diagonal": "diagonal",
    "hypotenuse": "hypotenuse",
    "circumference": "circumference",
    "diameter": "diameter",
    "arc length": "arc_length",
    "volume": "volume",
    "surface area": "surface_area",
    "total surface area": "surface_area",
}


def finish_geometry_intent(intent: MathIntent, cleaned: str) -> MathIntent | None:
    """Give a shape the question's unit and record the measurement it names.

    A natural-language measurement must not inherit the structured-input
    schema's legacy centimetre default; AAA triangles already carry relative
    side lengths in generic units. None declines a shape whose unit is unreadable,
    a question whose measures are not its printed numbers ("height 4 cm more than its
    radius"), and a solid's surface that is not the closed total ("curved surface area").
    """
    shape_reading = (
        intent.kind == "solid"
        or intent.kind in _PLANE_SHAPES
        or is_geometry_measure(intent.school_op)
    )
    if shape_reading and measures_not_as_printed(cleaned):
        return None
    if intent.kind == "solid" and surface_not_closed_total(
        cleaned, asks_surface=bool(intent.wants_surface_area)
    ):
        return None
    if intent.kind == "solid":
        return intent.model_copy(update={"geometry_request": _solid_request(intent, cleaned)})
    shape = _PLANE_SHAPES.get(intent.kind)
    if shape is None:
        return intent
    named = parse_named_rectangle_request(cleaned) if shape == "rectangle" else None
    update: dict[str, object] = {"geometry_request": _plane_request(shape, named, cleaned)}
    if shape != "triangle_sides" or intent.unit != "units":
        unit = named.unit if named is not None else solid_length_unit(cleaned)
        if unit is None:
            return None
        update["unit"] = unit
    return intent.model_copy(update=update)


def _asked_quantity(cleaned: str) -> GeometryQuantity | None:
    parsed = measurement_request(cleaned)
    return None if parsed is None else _QUANTITIES.get(parsed[0])


def _plane_request(
    shape: GeometryShape, named: NamedRectangleRequest | None, cleaned: str
) -> GeometryRequest | None:
    if named is None:
        asked = _asked_quantity(cleaned)
        return None if asked is None else GeometryRequest(kind=shape, quantity=asked)
    # "area 12, width 3; find the length" is an area question asking for a side.
    quantity: GeometryQuantity | None = (
        "area" if named.target is not None else _QUANTITIES.get(named.quantity)
    )
    if quantity is None:
        return None
    return GeometryRequest(
        kind="rectangle",
        quantity=quantity,
        target=named.target,
        given_area=named.given_area,
        named_sides=True,
    )


def _solid_request(intent: MathIntent, cleaned: str) -> GeometryRequest | None:
    quantity = _asked_quantity(cleaned)
    if intent.solid_shape is None or quantity is None or quantity not in {"volume", "surface_area"}:
        return None
    try:
        solid = SolidGeometryInput(
            shape=intent.solid_shape,
            width=intent.width,
            height=intent.height,
            depth=intent.depth,
            side=intent.side,
            radius=intent.radius,
            unit=intent.unit,
        )
    except ValidationError:
        return None
    return GeometryRequest(kind=intent.solid_shape, quantity=quantity, solid=solid)
