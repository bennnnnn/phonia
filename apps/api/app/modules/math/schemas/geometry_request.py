"""The measurement a geometry question asks for, as extraction read it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.modules.math.schemas.geometry import SolidGeometryInput
from app.modules.math.schemas.operations import SolidShape

GeometryShape = Literal[
    "rectangle",
    "square",
    "triangle",
    "right_triangle",
    "triangle_sides",
    "parallelogram",
    "trapezoid",
    "circle",
    "sector",
    SolidShape,
]
GeometryQuantity = Literal[
    "area",
    "perimeter",
    "area_and_perimeter",
    "diagonal",
    "hypotenuse",
    "circumference",
    "diameter",
    "arc_length",
    "volume",
    "surface_area",
]


class GeometryRequest(BaseModel):
    """One measurement a question names, read once when its intent is extracted.

    Direct replies lay out their working from this and the verified figure
    instead of reading the question again.
    """

    model_config = ConfigDict(frozen=True)

    kind: GeometryShape
    quantity: GeometryQuantity
    # An area question asking for a side: "area 12, width 3; find the length".
    target: Literal["length", "width"] | None = None
    given_area: float | None = None
    # "length 4, width 3" keeps its names; in "8 by 5" the longer side is the length.
    named_sides: bool = False
    # A solid has no diagram, so the measures its solver used travel here.
    solid: SolidGeometryInput | None = None
