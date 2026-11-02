"""Graph / point / vertical verified blocks."""

from __future__ import annotations

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import GraphBlockSpec, GraphSampleInput, MathIntent
from app.modules.math.solve.inequality_graph import affine_inequality_graph_spec
from app.modules.math.tools.block.canonical import _diagram_block
from app.services.solving import VerifiedMathBlock


def _padded_y_bounds(ys: list[float]) -> tuple[float, float]:
    lo = min(min(ys), 0.0)
    hi = max(max(ys), 0.0)
    pad = max(1.0, (hi - lo) * 0.15)
    return lo - pad, hi + pad


def _verified_block_point(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.point_x is None or intent.point_y is None:
        return None
    px, py = intent.point_x, intent.point_y
    point_spec = GraphBlockSpec(
        expr=f"({px:g}, {py:g})",
        title=f"Point ({px:g}, {py:g})",
        x_min=px - 5,
        x_max=px + 5,
        points=[[px, py]],
    )
    lines.append(f"Point: ({px:g}, {py:g})")
    return _diagram_block(lines, point_spec, f"({px:g}, {py:g})")


def _verified_block_vertical(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.point_x is None:
        return None
    vx = float(intent.point_x)
    y_min, y_max = -10.0, 10.0
    vert_spec = GraphBlockSpec(
        type="vertical",
        x=vx,
        y_min=y_min,
        y_max=y_max,
        expr=f"x = {vx:g}",
        title=f"x = {vx:g}",
    )
    lines.append(f"Vertical line: x = {vx:g}.")
    # No numeric ```answer pill: this turn is the diagram, not "x equals 6".
    return _diagram_block(lines, vert_spec)


def _verified_block_graph(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not intent.expr:
        return None
    max_points = settings.math_graph_max_points
    if intent.school_op == "polar":
        sample = math_solve.sample_polar_curve(
            intent.expr[: settings.math_max_expr_length],
            intent.variable if intent.variable else "theta",
            max_points,
        )
        ys = [point[1] for point in sample.points]
        y_min, y_max = _padded_y_bounds(ys)
        spec = GraphBlockSpec(
            expr=sample.expr,
            variable=sample.variable,
            x_min=sample.x_min,
            x_max=sample.x_max,
            y_min=y_min,
            y_max=y_max,
            points=sample.points,
            title=sample.expr,
        )
        lines.append(f"Polar samples for {sample.expr}: {len(sample.points)} points.")
        return _diagram_block(lines, spec)
    if intent.school_op == "parametric" and intent.expr2:
        sample = math_solve.sample_parametric_curve(
            intent.expr[: settings.math_max_expr_length],
            intent.expr2[: settings.math_max_expr_length],
            intent.variable if intent.variable else "t",
            max_points,
        )
        ys = [point[1] for point in sample.points]
        y_min, y_max = _padded_y_bounds(ys)
        has_discontinuity = len(sample.segments) > 1
        spec = GraphBlockSpec(
            expr=sample.expr,
            variable=sample.variable,
            x_min=sample.x_min,
            x_max=sample.x_max,
            y_min=y_min,
            y_max=y_max,
            points=sample.points,
            segments=sample.segments if has_discontinuity else [],
            title=sample.expr,
        )
        lines.append(f"Parametric samples for {sample.expr}: {len(sample.points)} points.")
        return _diagram_block(lines, spec)
    # Axis-aligned circle/ellipse relations (x^2+y^2=1, x^2/9+y^2/4=1) are
    # not y=f(x) — sample parametrically into the same ```graph fence.
    ellipse_spec = math_solve.build_ellipse_graph_spec(
        intent.expr[: settings.math_max_expr_length], settings.math_graph_max_points
    )
    if ellipse_spec is not None:
        lines.append(
            f"Relation samples for {ellipse_spec.expr}: "
            f"{len(ellipse_spec.points)} parametric points "
            "(closed curve)."
        )
        return _diagram_block(lines, ellipse_spec)

    line_spec = math_solve.number_line_spec_from_expr(
        intent.expr[: settings.math_max_expr_length], intent.variable
    )
    if line_spec is not None:
        lines.append(
            f"Shaded region for {line_spec.expr} on the number line: "
            "open circle = endpoint not included, filled circle = included. "
            "This is a one-variable inequality rendered as a number line "
            '(type "number_line") — shade the solution '
            "interval, do not plot a y=f(x) curve."
        )
        return _diagram_block(lines, line_spec)

    # Use the user-named domain ("from 0 to 100") when present, else the
    # [-10, 10] default. Without this the verified block always sampled the
    # default window even when the user asked for a specific range, so the
    # model emitted its own (often wrong) spec.
    x_min = intent.graph_x_min if intent.graph_x_min is not None else -10
    x_max = intent.graph_x_max if intent.graph_x_max is not None else 10
    domain_explicit = intent.graph_x_min is not None and intent.graph_x_max is not None
    region = affine_inequality_graph_spec(intent.expr, x_min=x_min, x_max=x_max)
    if region is not None:
        boundary = (
            "dashed (not included)" if region.comparator in {"<", ">"} else "solid (included)"
        )
        lines.append(
            f"Verified shaded half-plane: {region.expr}. Boundary is {boundary}. "
            "Shade the side satisfying the inequality; this is a two-dimensional region, "
            "not a number line or only a function curve."
        )
        return _diagram_block(lines, region)
    sample = math_solve.sample_function(
        GraphSampleInput(
            expr=intent.expr[: settings.math_max_expr_length],
            variable=intent.variable,
            x_min=x_min,
            x_max=x_max,
            n=settings.math_graph_max_points,
        )
    )
    # Only attach segments when a real gap was detected (>1 segment)
    # — the overwhelmingly common case has none, and duplicating
    # every point into a redundant single-segment list would bloat
    # every graph fence for no benefit.
    has_discontinuity = len(sample.segments) > 1
    graph_spec = GraphBlockSpec(
        expr=sample.expr,
        variable=sample.variable,
        x_min=sample.x_min,
        x_max=sample.x_max,
        domain_explicit=domain_explicit,
        points=sample.points,
        segments=sample.segments if has_discontinuity else [],
        holes=sample.holes,
    )
    lines.append(f"Function samples for {sample.expr}: {len(sample.points)} points.")
    if has_discontinuity:
        lines.append(
            f"NOTE: {sample.expr} has a discontinuity in this range (e.g. a vertical "
            "asymptote) — the sampled points are split into "
            f"{len(sample.segments)} segments; do not describe it as a single "
            "continuous curve."
        )
    return _diagram_block(lines, graph_spec)


def _verified_block_graph_pair(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.expr and intent.expr2):
        return None
    x_min = intent.graph_x_min if intent.graph_x_min is not None else -10
    x_max = intent.graph_x_max if intent.graph_x_max is not None else 10
    domain_explicit = intent.graph_x_min is not None and intent.graph_x_max is not None
    sample1 = math_solve.sample_function(
        GraphSampleInput(
            expr=intent.expr[: settings.math_max_expr_length],
            variable=intent.variable,
            x_min=x_min,
            x_max=x_max,
            n=settings.math_graph_max_points,
        )
    )
    sample2 = math_solve.sample_function(
        GraphSampleInput(
            expr=intent.expr2[: settings.math_max_expr_length],
            variable=intent.variable,
            x_min=x_min,
            x_max=x_max,
            n=settings.math_graph_max_points,
        )
    )
    has_disc1 = len(sample1.segments) > 1
    has_disc2 = len(sample2.segments) > 1
    graph_spec = GraphBlockSpec(
        expr=sample1.expr,
        variable=sample1.variable,
        x_min=sample1.x_min,
        x_max=sample1.x_max,
        domain_explicit=domain_explicit,
        points=sample1.points,
        segments=sample1.segments if has_disc1 else [],
        holes=sample1.holes,
        expr2=sample2.expr,
        variable2=sample2.variable,
        points2=sample2.points,
        segments2=sample2.segments if has_disc2 else [],
        holes2=sample2.holes,
        label=f"y = {sample1.expr}",
        label2=f"y = {sample2.expr}",
    )
    lines.append(
        f"Function samples for y={sample1.expr} ({len(sample1.points)} points) and "
        f"y={sample2.expr} ({len(sample2.points)} points), same x-range for direct comparison."
    )
    return _diagram_block(lines, graph_spec)
