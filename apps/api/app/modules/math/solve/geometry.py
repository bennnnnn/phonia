"""2D/3D geometry measurements — no SymPy parse."""

from __future__ import annotations

import math

from pydantic import BaseModel

from app.modules.math.schemas import (
    CircleGeometryInput,
    CircleGeometryResult,
    ParallelogramInput,
    ParallelogramResult,
    RectangleGeometryInput,
    RectangleGeometryResult,
    RightTriangleGeometryInput,
    RightTriangleGeometryResult,
    SectorInput,
    SectorResult,
    SolidGeometryInput,
    SolidGeometryResult,
    SquareGeometryInput,
    SquareGeometryResult,
    TrapezoidInput,
    TrapezoidResult,
    TriangleGeometryInput,
    TriangleGeometryResult,
    TriangleSidesInput,
    TriangleSidesResult,
)
from app.modules.math.solve.triangle import cosine_rule_angle, heron_area, sine_rule_side
from app.services.solving import SolveServiceError

_ANGLE_INT_TOL_DEG = 0.11


def format_geometry_decimal(value: float, places: int = 2) -> str:
    """Round for display without turning 20.2 into 20.20 or 20 into 20.00."""
    return f"{value:.{places}f}".rstrip("0").rstrip(".") or "0"


def measure_text(value: float) -> str:
    """A measure as a card writes it: to at most 4 places, never in e-notation."""
    return format_geometry_decimal(value, 4)


def _rounded(**measures: float) -> frozenset[str]:
    """The measures a result holds only to 4 places: a root, π, a third."""
    return frozenset(
        name
        for name, value in measures.items()
        if not math.isclose(round(value, 4), value, rel_tol=1e-12, abs_tol=1e-12)
    )


def answer_is_rounded(answer: str, result: BaseModel | None) -> bool:
    """True when ``answer`` shows a measure of ``result`` rounded rather than exactly."""
    if result is None:
        return False
    try:
        shown = float(answer)
    except ValueError:
        return False
    rounded: frozenset[str] = getattr(result, "rounded", frozenset())
    for name in type(result).model_fields:
        value = getattr(result, name)
        if not isinstance(value, float) or answer not in (
            f"{value:g}",
            format_geometry_decimal(value),
            measure_text(value),
        ):
            continue
        return name in rounded or not math.isclose(shown, value, rel_tol=1e-12, abs_tol=1e-12)
    # A sum of measures (a perimeter with its hypotenuse) is as rounded as any part of it.
    return bool(rounded)


def angle_list(result: TriangleSidesResult, *, given: bool) -> str:
    """``120°, ≈ 38.2°, ≈ 21.8°``: a rounded angle says so, a given one is exact."""
    return ", ".join(
        rf"\approx {result.labels[name]}"
        if name in result.rounded and not given
        else result.labels[name]
        for name in ("angle_a", "angle_b", "angle_c")
    )


def format_degree_label(deg: float) -> str:
    """School labels: ``120°`` not ``119.9°`` when the value is a near-integer."""
    nearest = round(deg)
    if abs(deg - nearest) < _ANGLE_INT_TOL_DEG:
        return f"{int(nearest)}°"
    return f"{round(deg, 1):.1f}°"


def sides_from_interior_angles(
    angle_a: float,
    angle_b: float,
    angle_c: float,
) -> tuple[float, float, float]:
    """Law of sines with the smallest opposite side scaled to 1 (relative units)."""
    if min(angle_a, angle_b, angle_c) <= 0 or max(angle_a, angle_b, angle_c) >= 180:
        raise SolveServiceError("each interior angle must be between 0° and 180°")
    if abs(angle_a + angle_b + angle_c - 180.0) > 0.6:
        raise SolveServiceError("interior angles must sum to 180°")
    smallest = min(angle_a, angle_b, angle_c)
    side_a, side_b, side_c = (
        round(float(sine_rule_side(1, smallest, angle)), 4) for angle in (angle_a, angle_b, angle_c)
    )
    return side_a, side_b, side_c


def rectangle_geometry(data: RectangleGeometryInput) -> RectangleGeometryResult:
    w, h = data.width, data.height
    diagonal = math.sqrt(w * w + h * h)
    angle_deg = math.degrees(math.atan2(h, w))
    area = w * h
    perimeter = 2 * (w + h)
    unit = data.unit
    labels = {
        "width": f"{w:g} {unit}",
        "height": f"{h:g} {unit}",
        "diagonal": f"{format_geometry_decimal(diagonal)} {unit}",
        "angle": f"{angle_deg:.1f}°",
        "area": f"{area:g} {unit}²",
        "perimeter": f"{perimeter:g} {unit}",
    }
    return RectangleGeometryResult(
        rounded=_rounded(diagonal=diagonal, area=area, perimeter=perimeter),
        width=w,
        height=h,
        unit=unit,
        diagonal=round(diagonal, 4),
        angle_deg=round(angle_deg, 2),
        area=round(area, 4),
        perimeter=round(perimeter, 4),
        labels=labels,
    )


def square_geometry(data: SquareGeometryInput) -> SquareGeometryResult:
    s = data.side
    diagonal = math.sqrt(2 * s * s)
    area = s * s
    perimeter = 4 * s
    unit = data.unit
    labels = {
        "side": f"{s:g} {unit}",
        "diagonal": f"{format_geometry_decimal(diagonal)} {unit}",
        "area": f"{area:g} {unit}²",
        "perimeter": f"{perimeter:g} {unit}",
    }
    return SquareGeometryResult(
        rounded=_rounded(diagonal=diagonal, area=area, perimeter=perimeter),
        side=s,
        unit=unit,
        diagonal=round(diagonal, 4),
        area=round(area, 4),
        perimeter=round(perimeter, 4),
        labels=labels,
    )


def solid_geometry(data: SolidGeometryInput) -> SolidGeometryResult:
    """School volume and total surface area. Uses the same π as circle_geometry."""
    unit = data.unit
    shape = data.shape
    volume: float
    surface: float
    extra: dict[str, str] = {}

    if shape == "cube":
        if data.side is None:
            raise SolveServiceError("cube requires side")
        s = data.side
        volume = s * s * s
        surface = 6 * s * s
        extra["side"] = f"{s:g} {unit}"
    elif shape == "rectangular_prism":
        if data.width is None or data.height is None or data.depth is None:
            raise SolveServiceError("rectangular prism requires three edges")
        length, w, h = data.width, data.depth, data.height
        volume = length * w * h
        surface = 2 * (length * w + length * h + w * h)
        extra["length"] = f"{length:g} {unit}"
        extra["width"] = f"{w:g} {unit}"
        extra["height"] = f"{h:g} {unit}"
    elif shape == "cylinder":
        if data.radius is None or data.height is None:
            raise SolveServiceError("cylinder requires radius and height")
        r, h = data.radius, data.height
        volume = math.pi * r * r * h
        surface = 2 * math.pi * r * (r + h)
        extra["radius"] = f"{r:g} {unit}"
        extra["height"] = f"{h:g} {unit}"
    elif shape == "cone":
        if data.radius is None or data.height is None:
            raise SolveServiceError("cone requires radius and height")
        r, h = data.radius, data.height
        slant = math.sqrt(r * r + h * h)
        volume = (1.0 / 3.0) * math.pi * r * r * h
        surface = math.pi * r * (r + slant)
        extra["radius"] = f"{r:g} {unit}"
        extra["height"] = f"{h:g} {unit}"
        extra["slant"] = f"{format_geometry_decimal(slant)} {unit}"
    elif shape == "sphere":
        if data.radius is None:
            raise SolveServiceError("sphere requires radius")
        r = data.radius
        volume = (4.0 / 3.0) * math.pi * r * r * r
        surface = 4 * math.pi * r * r
        extra["radius"] = f"{r:g} {unit}"
    elif shape == "pyramid":
        pyr_h = data.height
        if pyr_h is None:
            raise SolveServiceError("pyramid requires height")
        if data.side is not None:
            s = data.side
            volume = (1.0 / 3.0) * s * s * pyr_h
            slant = math.sqrt(pyr_h * pyr_h + (s / 2.0) * (s / 2.0))
            surface = s * s + 2 * s * slant
            extra["base"] = f"{s:g} {unit}"
        elif data.width is not None and data.depth is not None:
            length, w = data.width, data.depth
            volume = (1.0 / 3.0) * length * w * pyr_h
            face_l = math.sqrt(pyr_h * pyr_h + (w / 2.0) * (w / 2.0))
            face_w = math.sqrt(pyr_h * pyr_h + (length / 2.0) * (length / 2.0))
            surface = length * w + length * face_l + w * face_w
            extra["length"] = f"{length:g} {unit}"
            extra["width"] = f"{w:g} {unit}"
        else:
            raise SolveServiceError("pyramid requires base side or length and width")
        extra["height"] = f"{pyr_h:g} {unit}"
    else:
        raise SolveServiceError(f"unsupported solid {shape}")

    uses_pi = shape in {"cylinder", "cone", "sphere"}
    volume_text = format_geometry_decimal(volume) if uses_pi else measure_text(volume)
    surface_text = format_geometry_decimal(surface) if uses_pi else measure_text(surface)
    vol_label = f"{volume_text} {unit}³"
    sa_label = f"{surface_text} {unit}²"
    labels = {**extra, "volume": vol_label, "surface_area": sa_label}
    return SolidGeometryResult(
        rounded=_rounded(volume=volume, surface_area=surface),
        shape=shape,
        volume=round(volume, 4),
        surface_area=round(surface, 4),
        unit=unit,
        labels=labels,
    )


def triangle_geometry(data: TriangleGeometryInput) -> TriangleGeometryResult:
    b, h = data.base, data.height
    area = 0.5 * b * h
    unit = data.unit
    labels = {
        "base": f"{b:g} {unit}",
        "height": f"{h:g} {unit}",
        "area": f"{area:g} {unit}²",
    }
    return TriangleGeometryResult(
        rounded=_rounded(area=area),
        base=b,
        height=h,
        unit=unit,
        area=round(area, 4),
        labels=labels,
    )


def right_triangle_geometry(data: RightTriangleGeometryInput) -> RightTriangleGeometryResult:
    b, h = data.base, data.height
    hypotenuse = math.sqrt(b * b + h * h)
    area = 0.5 * b * h
    unit = data.unit
    angle_at_base = math.degrees(math.atan2(h, b))
    angle_at_height = math.degrees(math.atan2(b, h))
    labels = {
        "base": f"{b:g} {unit}",
        "height": f"{h:g} {unit}",
        "hypotenuse": f"{format_geometry_decimal(hypotenuse)} {unit}",
        "area": f"{area:g} {unit}²",
        "angle": "90°",
        "angle_at_base": format_degree_label(angle_at_base),
        "angle_at_height": format_degree_label(angle_at_height),
    }
    return RightTriangleGeometryResult(
        rounded=_rounded(hypotenuse=hypotenuse, area=area),
        base=b,
        height=h,
        unit=unit,
        hypotenuse=round(hypotenuse, 4),
        area=round(area, 4),
        labels=labels,
    )


def circle_geometry(data: CircleGeometryInput) -> CircleGeometryResult:
    r = data.radius
    diameter = 2 * r
    area = math.pi * r * r
    circumference = 2 * math.pi * r
    unit = data.unit
    labels = {
        "radius": f"{r:g} {unit}",
        "diameter": f"{diameter:g} {unit}",
        "area": f"{format_geometry_decimal(area)} {unit}²",
        "circumference": f"{format_geometry_decimal(circumference)} {unit}",
    }
    return CircleGeometryResult(
        rounded=_rounded(diameter=diameter, area=area, circumference=circumference),
        radius=r,
        unit=unit,
        diameter=round(diameter, 4),
        area=round(area, 4),
        circumference=round(circumference, 4),
        labels=labels,
    )


def triangle_sides_geometry(data: TriangleSidesInput) -> TriangleSidesResult:
    """Area via Heron's formula, angles via the law of cosines — for a
    triangle given as three side lengths rather than base+height."""
    a, b, c = data.a, data.b, data.c
    area = heron_area(a, b, c)
    perimeter = a + b + c
    angle_a = float(cosine_rule_angle(b, c, a))
    angle_b = float(cosine_rule_angle(a, c, b))
    angle_c = 180.0 - angle_a - angle_b
    unit = data.unit
    labels = {
        "a": f"{a:g} {unit}",
        "b": f"{b:g} {unit}",
        "c": f"{c:g} {unit}",
        "area": f"{format_geometry_decimal(area)} {unit}²",
        "perimeter": f"{perimeter:g} {unit}",
        "angle_a": format_degree_label(angle_a),
        "angle_b": format_degree_label(angle_b),
        "angle_c": format_degree_label(angle_c),
    }
    # An angle label to a tenth (38.2°) or the nearest degree is a rounding unless exact.
    shown_angles = {"angle_a": angle_a, "angle_b": angle_b, "angle_c": angle_c}
    angles_rounded = {
        name
        for name, angle in shown_angles.items()
        if not math.isclose(float(labels[name].rstrip("°")), angle, abs_tol=1e-9)
    }
    return TriangleSidesResult(
        rounded=_rounded(area=area, perimeter=perimeter) | angles_rounded,
        a=a,
        b=b,
        c=c,
        unit=unit,
        area=round(area, 4),
        perimeter=round(perimeter, 4),
        angle_a_deg=round(angle_a, 2),
        angle_b_deg=round(angle_b, 2),
        angle_c_deg=round(angle_c, 2),
        labels=labels,
    )


def trapezoid_geometry(data: TrapezoidInput) -> TrapezoidResult:
    area = (data.top + data.bottom) / 2 * data.height
    unit = data.unit
    labels = {
        "top": f"{data.top:g} {unit}",
        "bottom": f"{data.bottom:g} {unit}",
        "height": f"{data.height:g} {unit}",
        "area": f"{area:g} {unit}²",
    }
    return TrapezoidResult(
        rounded=_rounded(area=area),
        top=data.top,
        bottom=data.bottom,
        height=data.height,
        unit=unit,
        area=round(area, 4),
        labels=labels,
    )


def parallelogram_geometry(data: ParallelogramInput) -> ParallelogramResult:
    area = data.base * data.height
    perimeter = 2 * (data.base + data.side)
    unit = data.unit
    labels = {
        "base": f"{data.base:g} {unit}",
        "height": f"{data.height:g} {unit}",
        "side": f"{data.side:g} {unit}",
        "area": f"{area:g} {unit}²",
        "perimeter": f"{perimeter:g} {unit}",
    }
    return ParallelogramResult(
        rounded=_rounded(area=area, perimeter=perimeter),
        base=data.base,
        height=data.height,
        side=data.side,
        unit=unit,
        area=round(area, 4),
        perimeter=round(perimeter, 4),
        labels=labels,
    )


def sector_geometry(data: SectorInput) -> SectorResult:
    r, theta_deg = data.radius, data.angle_deg
    theta_rad = math.radians(theta_deg)
    arc_length = r * theta_rad
    area = 0.5 * r * r * theta_rad
    unit = data.unit
    labels = {
        "radius": f"{r:g} {unit}",
        "angle": f"{theta_deg:g}°",
        "arc_length": f"{format_geometry_decimal(arc_length)} {unit}",
        "area": f"{format_geometry_decimal(area)} {unit}²",
    }
    return SectorResult(
        rounded=_rounded(arc_length=arc_length, area=area),
        radius=r,
        angle_deg=theta_deg,
        unit=unit,
        arc_length=round(arc_length, 4),
        area=round(area, 4),
        labels=labels,
    )
