"""Geometry verified blocks."""

from __future__ import annotations

import math
from dataclasses import replace

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import (
    CircleGeometryBlockSpec,
    CircleGeometryInput,
    GeometryBlockSpec,
    MathIntent,
    ParallelogramGeometryBlockSpec,
    ParallelogramInput,
    RectangleGeometryInput,
    RightTriangleGeometryBlockSpec,
    RightTriangleGeometryInput,
    SectorGeometryBlockSpec,
    SectorInput,
    SquareGeometryInput,
    TrapezoidGeometryBlockSpec,
    TrapezoidInput,
    TriangleGeometryBlockSpec,
    TriangleGeometryInput,
    TriangleSidesGeometryBlockSpec,
    TriangleSidesInput,
)
from app.modules.math.solve.geometry import angle_list, answer_is_rounded
from app.modules.math.solve.geometry import measure_text as _shown
from app.modules.math.tools.block.answer_text import format_quantity
from app.modules.math.tools.block.canonical import _diagram_block, finish_with_answer
from app.services.solving import VerifiedMathBlock
from app.services.workout import Workout, math_line, render_workout


def _finish_geometry(
    intent: MathIntent,
    lines: list[str],
    spec: object,
    answer: str | None = None,
    result: BaseModel | None = None,
) -> VerifiedMathBlock:
    # Dimensions are enough to draw the shape, but not to choose a measurement.
    # Keep the native diagram while leaving the answer empty; the direct layer
    # asks which quantity the user wants instead of inventing one.
    display_answer: str | None = None
    if answer:
        if intent.wants_area and intent.wants_perimeter:
            display_answer = answer
        elif intent.wants_angle and intent.wants_diagonal:
            display_answer = answer
        elif intent.geometry_target is not None:
            display_answer = format_quantity(answer, intent.unit)
        elif intent.wants_circumference or intent.wants_diameter:
            display_answer = format_quantity(answer, intent.unit)
        elif intent.wants_perimeter:
            display_answer = format_quantity(answer, intent.unit)
        elif intent.wants_area:
            display_answer = format_quantity(answer, f"{intent.unit}²")
        elif intent.wants_diagonal or intent.wants_hypotenuse or intent.wants_arc_length:
            display_answer = format_quantity(answer, intent.unit)
        elif intent.wants_angle:
            display_answer = answer
        # A root or π shown to a few places is that rounding, not the value: the card says so.
        if display_answer and answer_is_rounded(answer, result):
            display_answer = rf"\approx {display_answer}"
    return _diagram_block(lines, spec, answer, display_answer=display_answer)


def _verified_block_rectangle(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.width and intent.height):
        return None
    rect_geo = math_solve.rectangle_geometry(
        RectangleGeometryInput(width=intent.width, height=intent.height, unit=intent.unit)
    )
    lines.append(
        f"Rectangle: width={rect_geo.width:g} {rect_geo.unit} "
        f"height={rect_geo.height:g} {rect_geo.unit} "
        f"diagonal={rect_geo.diagonal:g} angle={rect_geo.angle_deg:g}°"
    )
    # Only annotate the diagram with what was actually asked for. Supplying
    # dimensions alone is not an implicit area or diagonal request.
    show_area = intent.wants_area or intent.given_area is not None
    show_perimeter = intent.wants_perimeter
    show_diagonal = intent.wants_diagonal or intent.wants_angle
    show_angle = intent.wants_angle
    spec = GeometryBlockSpec(
        type="rectangle",
        width=rect_geo.width,
        height=rect_geo.height,
        unit=rect_geo.unit,
        show_diagonal=show_diagonal,
        show_angle=show_angle,
        show_area=show_area,
        show_perimeter=show_perimeter,
        show_ticks=True,
        diagonal=rect_geo.diagonal,
        angle_deg=rect_geo.angle_deg,
        area=rect_geo.area,
        perimeter=rect_geo.perimeter,
        labels=rect_geo.labels,
    )
    if intent.geometry_target == "width":
        answer = _shown(rect_geo.width)
    elif intent.geometry_target == "length":
        answer = _shown(rect_geo.height)
    elif intent.wants_angle and intent.wants_diagonal:
        # “Angle made by the diagonal” mentions the diagonal as a reference,
        # not as a request to substitute its length for the angle.
        answer = rf"{rect_geo.angle_deg:g}^\circ"
    elif intent.wants_area and intent.wants_perimeter:
        area = format_quantity(_shown(rect_geo.area), f"{intent.unit}²")
        perimeter = format_quantity(_shown(rect_geo.perimeter), intent.unit)
        answer = rf"A = {area},\quad P = {perimeter}"
    elif intent.wants_perimeter:
        answer = _shown(rect_geo.perimeter)
    elif intent.wants_diagonal and not intent.wants_area:
        answer = _shown(rect_geo.diagonal)
    elif intent.wants_area:
        answer = _shown(rect_geo.area)
    else:
        answer = None
    return _finish_geometry(intent, lines, spec, answer, rect_geo)


def _verified_block_square(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.side or intent.width):
        return None
    side = intent.side or intent.width or 5
    square_geo = math_solve.square_geometry(SquareGeometryInput(side=side, unit=intent.unit))
    lines.append(
        f"Square: side={square_geo.side:g} {square_geo.unit} "
        f"diagonal={square_geo.diagonal:g} {square_geo.unit} "
        f"area={square_geo.area:g} {square_geo.unit}² "
        f"perimeter={square_geo.perimeter:g} {square_geo.unit}"
    )
    spec = GeometryBlockSpec(
        type="square",
        side=square_geo.side,
        width=square_geo.side,
        height=square_geo.side,
        unit=square_geo.unit,
        show_diagonal=intent.wants_diagonal,
        show_area=intent.wants_area,
        show_perimeter=intent.wants_perimeter,
        show_ticks=True,
        diagonal=square_geo.diagonal,
        area=square_geo.area,
        perimeter=square_geo.perimeter,
        labels=square_geo.labels,
    )
    answer: float | None = None
    if intent.wants_perimeter:
        answer = square_geo.perimeter
    elif intent.wants_diagonal and not intent.wants_area:
        answer = square_geo.diagonal
    elif intent.wants_area:
        answer = square_geo.area
    shown = _shown(answer) if answer is not None else None
    return _finish_geometry(intent, lines, spec, shown, square_geo)


def _verified_block_circle(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not intent.radius:
        return None
    if intent.chord_length is not None and intent.wants_center_distance:
        chord = intent.chord_length
        diameter = 2 * intent.radius
        if chord > diameter:
            message = (
                f"A chord of length {chord:g} cannot fit in a circle of radius "
                f"{intent.radius:g}; the maximum chord length is the diameter, {diameter:g}."
            )
            lines.append(message)
            return VerifiedMathBlock(text="\n".join(lines), direct_reply=message)
        distance = math.sqrt(intent.radius**2 - (chord / 2) ** 2)
        answer = math_solve.format_geometry_decimal(distance)
        direct = render_workout(
            Workout(
                given=(
                    math_line(f"r = {intent.radius:g}", "radius"),
                    math_line(f"c = {chord:g}", "chord"),
                ),
                find=(math_line("d", "distance from the centre to the chord"),),
                formula=(
                    math_line("d = \\sqrt{r^2-(c/2)^2}", "Perpendicular bisector of the chord"),
                ),
                substitution=(
                    math_line(f"d = \\sqrt{{{intent.radius:g}^2-({chord:g}/2)^2}} = {answer}"),
                ),
            ),
            f"{answer} {intent.unit}",
        )
        return replace(
            finish_with_answer(lines, answer),
            display_answer=f"{answer} {intent.unit}",
            direct_reply=direct,
        )
    circle_geo = math_solve.circle_geometry(
        CircleGeometryInput(radius=intent.radius, unit=intent.unit)
    )
    lines.append(
        f"Circle: radius={circle_geo.radius:g} {circle_geo.unit} "
        f"diameter={circle_geo.diameter:g} {circle_geo.unit} "
        f"area={math_solve.format_geometry_decimal(circle_geo.area)} {circle_geo.unit}² "
        f"circumference={math_solve.format_geometry_decimal(circle_geo.circumference)} "
        f"{circle_geo.unit}"
    )
    circle_spec = CircleGeometryBlockSpec(
        type="circle",
        radius=circle_geo.radius,
        unit=circle_geo.unit,
        show_diameter=intent.wants_diameter or intent.given_diameter,
        show_area=intent.wants_area,
        show_circumference=intent.wants_circumference,
        diameter=circle_geo.diameter,
        area=circle_geo.area,
        circumference=circle_geo.circumference,
        labels=circle_geo.labels,
    )
    # The verified final answer must match what the user asked for —
    # "circumference of circle r=4" used to return the area (≈50.27)
    # because the canonical answer was unconditionally the area. Honor an
    # explicit circumference or diameter request; fall back to area when
    # only area or nothing specific was asked.
    circle_answer: str | None
    if intent.wants_circumference:
        circle_answer = math_solve.format_geometry_decimal(circle_geo.circumference)
    elif intent.wants_diameter and not intent.wants_area:
        circle_answer = _shown(circle_geo.diameter)
    elif intent.wants_area:
        circle_answer = math_solve.format_geometry_decimal(circle_geo.area)
    else:
        circle_answer = None
    return _finish_geometry(intent, lines, circle_spec, circle_answer, circle_geo)


def _verified_block_triangle(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.base and intent.height):
        return None
    tri_geo = math_solve.triangle_geometry(
        TriangleGeometryInput(base=intent.base, height=intent.height, unit=intent.unit)
    )
    lines.append(
        f"Triangle: base={tri_geo.base:g} {tri_geo.unit} "
        f"height={tri_geo.height:g} {tri_geo.unit} area={tri_geo.area:g} {tri_geo.unit}²"
    )
    tri_spec = TriangleGeometryBlockSpec(
        type="triangle",
        base=tri_geo.base,
        height=tri_geo.height,
        unit=tri_geo.unit,
        show_labels=True,
        show_ticks=False,
        show_altitude=True,
        show_angle=False,
        area=tri_geo.area,
        labels=tri_geo.labels,
    )
    area = _shown(tri_geo.area) if intent.wants_area else None
    return _finish_geometry(intent, lines, tri_spec, area, tri_geo)


def _verified_block_right_triangle(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.base and intent.height):
        return None
    rt_geo = math_solve.right_triangle_geometry(
        RightTriangleGeometryInput(base=intent.base, height=intent.height, unit=intent.unit)
    )
    lines.append(
        f"Right triangle: base={rt_geo.base:g} {rt_geo.unit} "
        f"height={rt_geo.height:g} {rt_geo.unit} "
        f"hypotenuse={rt_geo.hypotenuse:g} {rt_geo.unit} "
        f"area={rt_geo.area:g} {rt_geo.unit}² "
        f"angles=90° / {rt_geo.labels['angle_at_base']} at base / "
        f"{rt_geo.labels['angle_at_height']} at height. "
        f"Opposite the base ({rt_geo.base:g} {rt_geo.unit}) is "
        f"{rt_geo.labels['angle_at_height']}; opposite the height "
        f"({rt_geo.height:g} {rt_geo.unit}) is {rt_geo.labels['angle_at_base']}. "
        "Do not swap those opposite-side angles."
    )
    rt_spec = RightTriangleGeometryBlockSpec(
        type="right_triangle",
        base=rt_geo.base,
        height=rt_geo.height,
        unit=rt_geo.unit,
        show_labels=True,
        show_hypotenuse=True,
        show_angle=True,
        hypotenuse=rt_geo.hypotenuse,
        area=rt_geo.area,
        perimeter=rt_geo.base + rt_geo.height + rt_geo.hypotenuse,
        labels=rt_geo.labels,
    )
    lines.append("Interior-angle labels: all three vertices (not only the 90° square).")
    # Draw-and-label asks are the diagram — do not attach a leftover area pill
    # (6x4 default used to dump a gray "12" under a 3-4-5 request).
    answer = _shown(rt_geo.area) if intent.wants_area else None
    if intent.wants_hypotenuse and not (intent.wants_area or intent.wants_perimeter):
        answer = _shown(rt_geo.hypotenuse)
    if intent.wants_perimeter:
        answer = _shown(rt_geo.base + rt_geo.height + rt_geo.hypotenuse)
    return _finish_geometry(intent, lines, rt_spec, answer, rt_geo)


def _verified_block_triangle_sides(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.tri_a and intent.tri_b and intent.tri_c):
        return None
    try:
        tri_geo = math_solve.triangle_sides_geometry(
            TriangleSidesInput(a=intent.tri_a, b=intent.tri_b, c=intent.tri_c, unit=intent.unit)
        )
    except ValidationError:
        message = (
            "These side lengths do not form a non-degenerate triangle, so its area is not "
            "defined as a triangle."
        )
        lines.append(message)
        return VerifiedMathBlock(text="\n".join(lines), direct_reply=message)
    relative = intent.triangle_relative_lengths
    if relative:
        lines.append(
            f"Relative side ratio a:b:c={tri_geo.a:g}:{tri_geo.b:g}:{tri_geo.c:g}. "
            "Only angles were supplied; physical lengths, area and perimeter are undetermined."
        )
    else:
        lines.append(
            f"Triangle: a={tri_geo.a:g} {tri_geo.unit} b={tri_geo.b:g} {tri_geo.unit} "
            f"c={tri_geo.c:g} {tri_geo.unit} area={tri_geo.area:g} {tri_geo.unit}² "
            f"perimeter={tri_geo.perimeter:g} {tri_geo.unit} "
            f"angles={tri_geo.angle_a_deg:g}°/{tri_geo.angle_b_deg:g}°/{tri_geo.angle_c_deg:g}°"
        )
    isosceles = (
        abs(tri_geo.a - tri_geo.b) < 1e-9
        or abs(tri_geo.a - tri_geo.c) < 1e-9
        or abs(tri_geo.b - tri_geo.c) < 1e-9
    )
    tri_spec = TriangleSidesGeometryBlockSpec(
        type="triangle_sides",
        a=tri_geo.a,
        b=tri_geo.b,
        c=tri_geo.c,
        relative_lengths=relative,
        unit=tri_geo.unit,
        show_labels=True,
        show_ticks=True,
        show_altitude=False,
        show_median=isosceles,
        show_angle=True,
        area=None if relative else tri_geo.area,
        perimeter=None if relative else tri_geo.perimeter,
        labels=(
            {key: value for key, value in tri_geo.labels.items() if key.startswith("angle_")}
            if relative
            else tri_geo.labels
        ),
    )
    if intent.unit == "units":
        lines.append(
            "Lengths use generic units, not centimetres. When the user supplied only "
            "interior angles, these side lengths express relative proportions "
            "(law of sines), not a known physical size."
        )
    lines.append(
        "Angles via the law of cosines."
        if relative
        else "Area via Heron's formula; angles via the law of cosines."
    )
    if relative and (intent.wants_area or intent.wants_perimeter):
        return _finish_geometry(intent, lines, tri_spec)
    if relative and not (intent.wants_angle or intent.wants_area or intent.wants_perimeter):
        # Pure AAA drawings already label the supplied angles. Retaining a
        # canonical answer would make finalization append a redundant card.
        return _finish_geometry(intent, lines, tri_spec)
    if intent.wants_angle and not (intent.wants_area or intent.wants_perimeter):
        answer = angle_list(tri_geo, given=bool(relative))
        return _finish_geometry(intent, lines, tri_spec, answer)
    quantity: float | None = None
    if intent.wants_perimeter:
        quantity = tri_geo.perimeter
    elif intent.wants_area:
        quantity = tri_geo.area
    shown = _shown(quantity) if quantity is not None else None
    return _finish_geometry(intent, lines, tri_spec, shown, tri_geo)


def _verified_block_trapezoid(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.trapezoid_top and intent.trapezoid_bottom and intent.height):
        return None
    trap_geo = math_solve.trapezoid_geometry(
        TrapezoidInput(
            top=intent.trapezoid_top,
            bottom=intent.trapezoid_bottom,
            height=intent.height,
            unit=intent.unit,
        )
    )
    lines.append(
        f"Trapezoid: top={trap_geo.top:g} {trap_geo.unit} "
        f"bottom={trap_geo.bottom:g} {trap_geo.unit} "
        f"height={trap_geo.height:g} {trap_geo.unit} area={trap_geo.area:g} {trap_geo.unit}²"
    )
    trap_spec = TrapezoidGeometryBlockSpec(
        type="trapezoid",
        top=trap_geo.top,
        bottom=trap_geo.bottom,
        height=trap_geo.height,
        unit=trap_geo.unit,
        show_labels=True,
        show_angle=bool(intent.wants_angle),
        area=trap_geo.area,
        labels=trap_geo.labels,
    )
    lines.append("area = (top + bottom) / 2 \\times height")
    area = _shown(trap_geo.area) if intent.wants_area else None
    return _finish_geometry(intent, lines, trap_spec, area, trap_geo)


def _verified_block_parallelogram(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.base and intent.height and intent.side):
        return None
    para_geo = math_solve.parallelogram_geometry(
        ParallelogramInput(
            base=intent.base, height=intent.height, side=intent.side, unit=intent.unit
        )
    )
    lines.append(
        f"Parallelogram: base={para_geo.base:g} {para_geo.unit} height={para_geo.height:g} "
        f"{para_geo.unit} side={para_geo.side:g} {para_geo.unit} area={para_geo.area:g} "
        f"{para_geo.unit}² perimeter={para_geo.perimeter:g} {para_geo.unit}"
    )
    para_spec = ParallelogramGeometryBlockSpec(
        type="parallelogram",
        base=para_geo.base,
        height=para_geo.height,
        side=para_geo.side,
        unit=para_geo.unit,
        show_labels=True,
        show_angle=bool(intent.wants_angle),
        show_perimeter=intent.wants_perimeter and not intent.wants_area,
        area=para_geo.area,
        perimeter=para_geo.perimeter,
        labels=para_geo.labels,
    )
    answer: float | None = None
    if intent.wants_perimeter:
        answer = para_geo.perimeter
    elif intent.wants_area:
        answer = para_geo.area
    shown = _shown(answer) if answer is not None else None
    return _finish_geometry(intent, lines, para_spec, shown, para_geo)


def _verified_block_sector(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.radius and intent.sector_angle_deg):
        return None
    sector_geo = math_solve.sector_geometry(
        SectorInput(radius=intent.radius, angle_deg=intent.sector_angle_deg, unit=intent.unit)
    )
    lines.append(
        f"Circle sector: radius={sector_geo.radius:g} {sector_geo.unit} "
        f"angle={sector_geo.angle_deg:g}° "
        f"arc_length={math_solve.format_geometry_decimal(sector_geo.arc_length)} "
        f"{sector_geo.unit} area={math_solve.format_geometry_decimal(sector_geo.area)} "
        f"{sector_geo.unit}²"
    )
    sector_spec = SectorGeometryBlockSpec(
        type="sector",
        radius=sector_geo.radius,
        angle_deg=sector_geo.angle_deg,
        unit=sector_geo.unit,
        show_labels=True,
        arc_length=sector_geo.arc_length,
        area=sector_geo.area,
        labels=sector_geo.labels,
    )
    answer: str | None = None
    if intent.wants_area:
        answer = _shown(sector_geo.area)
    elif intent.wants_arc_length:
        answer = math_solve.format_geometry_decimal(sector_geo.arc_length)
    return _finish_geometry(intent, lines, sector_spec, answer, sector_geo)
