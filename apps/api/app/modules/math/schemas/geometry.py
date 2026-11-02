"""Structured math I/O — validated before SymPy and fence emission."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.math.schemas.operations import SolidShape


class MeasuredResult(BaseModel):
    """A solved figure. ``rounded`` names the measures held only to 4 places (a root, π, a
    third), so a card can say ≈ rather than show a rounding as the value itself."""

    rounded: frozenset[str] = frozenset()


class RectangleGeometryInput(BaseModel):
    width: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)


class RectangleGeometryResult(MeasuredResult):
    width: float
    height: float
    unit: str
    diagonal: float
    angle_deg: float
    area: float
    perimeter: float
    labels: dict[str, str] = Field(default_factory=dict)


class SquareGeometryInput(BaseModel):
    side: float = Field(gt=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)


class SquareGeometryResult(MeasuredResult):
    side: float
    unit: str
    diagonal: float
    area: float
    perimeter: float
    labels: dict[str, str] = Field(default_factory=dict)


class SolidGeometryInput(BaseModel):
    shape: SolidShape
    width: float | None = Field(default=None, gt=0, le=1_000_000)
    height: float | None = Field(default=None, gt=0, le=1_000_000)
    depth: float | None = Field(default=None, gt=0, le=1_000_000)
    side: float | None = Field(default=None, gt=0, le=1_000_000)
    radius: float | None = Field(default=None, gt=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)


class SolidGeometryResult(MeasuredResult):
    shape: SolidShape
    volume: float
    surface_area: float
    unit: str
    labels: dict[str, str] = Field(default_factory=dict)


class TriangleGeometryInput(BaseModel):
    base: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)


class TriangleGeometryResult(MeasuredResult):
    base: float
    height: float
    unit: str
    area: float
    labels: dict[str, str] = Field(default_factory=dict)


class RightTriangleGeometryInput(BaseModel):
    base: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)


class RightTriangleGeometryResult(MeasuredResult):
    base: float
    height: float
    unit: str
    hypotenuse: float
    area: float
    labels: dict[str, str] = Field(default_factory=dict)


class CircleGeometryInput(BaseModel):
    radius: float = Field(gt=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)


class CircleGeometryResult(MeasuredResult):
    radius: float
    unit: str
    diameter: float
    area: float
    circumference: float
    labels: dict[str, str] = Field(default_factory=dict)


class TriangleSidesInput(BaseModel):
    """A triangle given by its three side lengths (SSS) rather than
    base+height — area via Heron's formula, angles via the law of cosines."""

    a: float = Field(gt=0, le=1_000_000)
    b: float = Field(gt=0, le=1_000_000)
    c: float = Field(gt=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)

    @model_validator(mode="after")
    def valid_triangle(self) -> TriangleSidesInput:
        # Deferred: the solver package imports these schemas.
        from app.modules.math.solve.triangle import triangle_valid

        if not triangle_valid(self.a, self.b, self.c):
            raise ValueError("these three side lengths cannot form a triangle")
        return self


class TriangleSidesResult(MeasuredResult):
    a: float
    b: float
    c: float
    unit: str
    area: float
    perimeter: float
    # Angle opposite the side of the same letter.
    angle_a_deg: float
    angle_b_deg: float
    angle_c_deg: float
    labels: dict[str, str] = Field(default_factory=dict)


class TrapezoidInput(BaseModel):
    top: float = Field(gt=0, le=1_000_000)
    bottom: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)


class TrapezoidResult(MeasuredResult):
    top: float
    bottom: float
    height: float
    unit: str
    area: float
    labels: dict[str, str] = Field(default_factory=dict)


class ParallelogramInput(BaseModel):
    base: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    side: float = Field(gt=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)

    @model_validator(mode="after")
    def side_at_least_height(self) -> ParallelogramInput:
        # The slant side is the hypotenuse of the right triangle formed by
        # the height, so it can never be shorter than the height itself.
        if self.side < self.height:
            raise ValueError("side must be at least as long as height")
        return self


class ParallelogramResult(MeasuredResult):
    base: float
    height: float
    side: float
    unit: str
    area: float
    perimeter: float
    labels: dict[str, str] = Field(default_factory=dict)


class SectorInput(BaseModel):
    radius: float = Field(gt=0, le=1_000_000)
    angle_deg: float = Field(gt=0, le=360)
    unit: str = Field(default="cm", max_length=16)


class SectorResult(MeasuredResult):
    radius: float
    angle_deg: float
    unit: str
    arc_length: float
    area: float
    labels: dict[str, str] = Field(default_factory=dict)


class TriangleGeometryBlockSpec(BaseModel):
    type: Literal["triangle"] = "triangle"
    base: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    unit: str = "cm"
    show_labels: bool = True
    show_ticks: bool = True
    show_altitude: bool = True
    show_angle: bool = True
    area: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class RightTriangleGeometryBlockSpec(BaseModel):
    type: Literal["right_triangle"] = "right_triangle"
    base: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    unit: str = "cm"
    show_labels: bool = True
    show_hypotenuse: bool = True
    show_angle: bool = True
    hypotenuse: float | None = None
    area: float | None = None
    perimeter: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class TriangleSidesGeometryBlockSpec(BaseModel):
    type: Literal["triangle_sides"] = "triangle_sides"
    a: float = Field(gt=0, le=1_000_000)
    b: float = Field(gt=0, le=1_000_000)
    c: float = Field(gt=0, le=1_000_000)
    relative_lengths: bool = False
    unit: str = "cm"
    show_labels: bool = True
    show_ticks: bool = True
    show_altitude: bool = False
    show_median: bool = False
    show_angle: bool = True
    area: float | None = None
    perimeter: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_triangle(self) -> TriangleSidesGeometryBlockSpec:
        a, b, c = self.a, self.b, self.c
        if a + b <= c or a + c <= b or b + c <= a:
            raise ValueError("these three side lengths cannot form a triangle")
        return self


class TrapezoidGeometryBlockSpec(BaseModel):
    type: Literal["trapezoid"] = "trapezoid"
    top: float = Field(gt=0, le=1_000_000)
    bottom: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    unit: str = "cm"
    show_labels: bool = True
    show_angle: bool = False
    area: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class ParallelogramGeometryBlockSpec(BaseModel):
    type: Literal["parallelogram"] = "parallelogram"
    base: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    side: float = Field(gt=0, le=1_000_000)
    unit: str = "cm"
    show_labels: bool = True
    show_angle: bool = False
    show_perimeter: bool = False
    area: float | None = None
    perimeter: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class SectorGeometryBlockSpec(BaseModel):
    type: Literal["sector"] = "sector"
    radius: float = Field(gt=0, le=1_000_000)
    angle_deg: float = Field(gt=0, le=360)
    unit: str = "cm"
    show_labels: bool = True
    arc_length: float | None = None
    area: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class CircleGeometryBlockSpec(BaseModel):
    type: Literal["circle"] = "circle"
    radius: float = Field(gt=0, le=1_000_000)
    unit: str = "cm"
    show_labels: bool = True
    show_diameter: bool = False
    show_area: bool = False
    show_circumference: bool = False
    diameter: float | None = None
    area: float | None = None
    circumference: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class GeometryBlockSpec(BaseModel):
    type: Literal["rectangle", "rect", "square"] = "rectangle"
    width: float | None = Field(default=None, gt=0, le=1_000_000)
    height: float | None = Field(default=None, gt=0, le=1_000_000)
    side: float | None = Field(default=None, gt=0, le=1_000_000)
    unit: str = "cm"
    show_diagonal: bool = False
    show_angle: bool = False
    show_area: bool = False
    show_perimeter: bool = False
    show_ticks: bool = True
    diagonal: float | None = None
    angle_deg: float | None = None
    area: float | None = None
    perimeter: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_dimensions(self) -> GeometryBlockSpec:
        if self.type == "square":
            edge = self.side or self.width or self.height
            if edge is None:
                raise ValueError("square requires side or width/height")
            self.side = edge
            self.width = edge
            self.height = edge
            return self
        if self.width is None or self.height is None:
            raise ValueError("rectangle requires width and height")
        return self
