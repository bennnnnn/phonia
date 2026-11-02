"""Re-sample a verified curve the model listed too sparsely to draw.

Only the solver-owned expression is ever sampled; an unverified model curve is
never polished into a smooth plot.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import GraphBlockSpec, GraphSampleInput
from app.modules.math.solve import SolveServiceError

# Below this count a continuous y=f(x) fence is treated as "sparse key points"
# the model listed for prose, not a renderable curve sample.
_MIN_CURVE_POINTS = 48


def _is_point_marker(spec: GraphBlockSpec) -> bool:
    """True for coordinate markers / discrete points — never densify those
    into a continuous curve."""
    if spec.type in {"vertical", "number_line"}:
        return True
    if len(spec.points) <= 1:
        return True
    if len(spec.points) >= 2 and len({float(p[0]) for p in spec.points}) == 1:
        # All x's identical — vertical segment, not y=f(x).
        return True
    if spec.expr.strip().startswith("("):
        return True
    title = (spec.title or "").strip().lower()
    return title.startswith("point")


def _sample_domain(spec: GraphBlockSpec) -> tuple[float, float]:
    """Choose a densify window from key points union declared x_min/x_max.

    Take the span covering both (not "declared wins when wider") so
    off-window roots/extrema in ``points`` still expand a default
    [-10, 10] declaration, and a wider declared domain still covers
    sparse root-only point lists.
    """
    xs = [float(p[0]) for p in spec.points]
    if spec.points2:
        xs.extend(float(p[0]) for p in spec.points2)
    span_min, span_max = min(xs), max(xs)
    declared_min, declared_max = float(spec.x_min), float(spec.x_max)
    if declared_max > declared_min:
        span_min = min(span_min, declared_min)
        span_max = max(span_max, declared_max)
    if span_max <= span_min:
        return span_min - 1.0, span_max + 1.0
    pad = max(1.0, (span_max - span_min) * 0.25)
    return span_min - pad, span_max + pad


def _expr_samplable_as_function(expr: str, variable: str) -> bool:
    """False for relation forms like ``x = 4`` that aren't y=f(x)."""
    e = expr.strip().lower()
    if "=" in expr and not e.startswith((variable.lower() + "=", "y=")):
        return False
    if any(op in expr for op in (">", "<", "≥", "≤")):
        return False
    return True


def _curve_needs_densify(
    points: list[list[float]] | None,
    expr: str | None,
    variable: str,
) -> bool:
    if not expr or not points or len(points) < 2:
        return False
    if len(points) >= _MIN_CURVE_POINTS:
        return False
    return _expr_samplable_as_function(expr, variable)


def _resample_curve(
    expr: str,
    variable: str,
    x_min: float,
    x_max: float,
    n: int,
    max_expr_length: int,
) -> tuple[list[list[float]], list[list[list[float]]], str, str, float, float] | None:
    try:
        sample = math_solve.sample_function(
            GraphSampleInput(
                expr=expr[:max_expr_length],
                variable=variable,
                x_min=x_min,
                x_max=x_max,
                n=n,
            )
        )
    except (SolveServiceError, ValueError, TypeError):
        return None
    if len(sample.points) < 2:
        return None
    segments = sample.segments if len(sample.segments) > 1 else []
    return (
        sample.points,
        segments,
        sample.expr,
        sample.variable,
        sample.x_min,
        sample.x_max,
    )


def densify_sparse_graph(spec: GraphBlockSpec) -> GraphBlockSpec:
    """Re-sample sparse continuous curve(s) so the client draws smooth plots.

    Densifies curve 1 and curve 2 independently — previously an early return
    when curve 1 was already dense left a sparse ``points2`` as a jagged
    polyline, and densifying curve 1 preserved but never resampled curve 2.
    """
    if spec.type in {"vertical", "number_line", "trajectory", "inequality"} or _is_point_marker(
        spec
    ):
        return spec

    var2 = (spec.variable2 or spec.variable).strip() or "x"
    needs1 = _curve_needs_densify(spec.points, spec.expr, spec.variable)
    needs2 = _curve_needs_densify(spec.points2, spec.expr2, var2)
    if not needs1 and not needs2:
        return spec

    x_min, x_max = _sample_domain(spec)
    settings = get_settings()
    n = settings.math_graph_max_points
    max_len = settings.math_max_expr_length

    points = spec.points
    segments = spec.segments or []
    expr = spec.expr
    variable = spec.variable
    out_x_min, out_x_max = float(spec.x_min), float(spec.x_max)

    if needs1:
        sampled = _resample_curve(spec.expr, spec.variable, x_min, x_max, n, max_len)
        if sampled is not None:
            points, segments, expr, variable, out_x_min, out_x_max = sampled

    points2 = spec.points2
    segments2 = spec.segments2
    if needs2 and spec.expr2:
        sampled2 = _resample_curve(spec.expr2, var2, x_min, x_max, n, max_len)
        if sampled2 is not None:
            points2, segments2, _, _, _, _ = sampled2

    if points is spec.points and points2 is spec.points2:
        return spec

    return GraphBlockSpec(
        type="function",
        expr=expr,
        variable=variable,
        x_min=out_x_min,
        x_max=out_x_max,
        domain_explicit=spec.domain_explicit,
        title=spec.title,
        points=points,
        segments=segments,
        expr2=spec.expr2,
        variable2=spec.variable2,
        points2=points2,
        segments2=segments2,
        label=spec.label,
        label2=spec.label2,
    )
