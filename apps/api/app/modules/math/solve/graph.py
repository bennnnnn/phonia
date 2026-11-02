"""Function sampling, ellipses, inequality number lines."""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
from sympy import (
    EmptySet,
    FiniteSet,
    Interval,
    S,
    Symbol,
    Union,
    cos,
    denom,
    limit,
    sin,
    solve,
    tan,
)
from sympy.calculus.singularities import singularities
from sympy.utilities.lambdify import lambdify

from app.modules.math.schemas import (
    GraphBlockSpec,
    GraphSampleInput,
    GraphSampleResult,
    NumberLineInterval,
)
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.discrete import guess_variables
from app.modules.math.solve.extract_eq import (
    try_extract_compound_inequality_from_text,
    try_extract_inequality_from_text,
)
from app.modules.math.solve.graph_expr_text import graph_expr_text
from app.modules.math.solve.graph_sampling import sample_at
from app.modules.math.solve.inequalities import compound_solution_set, inequality_solution_set
from app.modules.math.solve.parse import parse_expression
from app.services.solving import SolveServiceError


def _split_into_segments(
    points: list[list[float]], percentile: float = 85.0
) -> list[list[list[float]]]:
    """Split a continuous point list wherever a vertical asymptote likely
    sits between two consecutive samples (e.g. tan(x) near pi/2) — without
    this, naively connecting every finite sample draws a near-vertical line
    straight across the discontinuity.

    Numeric heuristic, not full symbolic singularity detection: flag a gap
    only where consecutive y-values (a) flip sign AND (b) both sit above the
    given percentile of |y| across the whole sample. A pole is exactly this
    shape — y diverges to +inf on one side and -inf on the other, so the two
    samples straddling it are both large AND opposite in sign. An ordinary
    zero-crossing (e.g. sin(x)) also flips sign but both values are small
    there, so it's correctly left unsplit; matches empirical validation
    against tan(x) (isolates all 6 real asymptotes in [-10, 10] with no
    over-splitting) and sin(x)/x**2 (never splits).
    """
    if len(points) < 2:
        return [points] if points else []
    abs_ys = sorted(abs(p[1]) for p in points)
    idx = min(len(abs_ys) - 1, int(len(abs_ys) * percentile / 100))
    large_threshold = abs_ys[idx]
    if large_threshold <= 0:
        return [points]
    segments: list[list[list[float]]] = [[points[0]]]
    for i in range(1, len(points)):
        y0, y1 = points[i - 1][1], points[i][1]
        sign_flip = (y0 > 0) != (y1 > 0)
        both_large = abs(y0) > large_threshold and abs(y1) > large_threshold
        if sign_flip and both_large:
            segments.append([])
        segments[-1].append(points[i])
    return [seg for seg in segments if seg]


def _symbolic_pole_xs(parsed: Any, sym: Symbol, x_min: float, x_max: float) -> list[float]:
    """Real poles of ``parsed`` strictly inside the window, via SymPy.

    Only finite, exactly-known singularities are returned — ConditionSet /
    ImageSet results (tan(x), 1/sin(x), …) are left to the numeric heuristic
    in ``_split_into_segments``. Never raises: any SymPy failure means "no
    symbolic poles", not a failed graph.
    """
    with sympy_decline() as declined:
        found = singularities(parsed, sym)
    if declined:
        return []
    sets = list(found.args) if isinstance(found, Union) else [found]
    xs: list[float] = []
    for item in sets:
        if not isinstance(item, FiniteSet):
            continue
        for value in item:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if x_min < numeric < x_max and math.isfinite(numeric):
                xs.append(numeric)
    return sorted(xs)


def _confirmed_pole_xs(points: list[list[float]], pole_xs: list[float]) -> list[float]:
    """Keep only symbolic poles the samples confirm as diverging.

    sin(x)/x has a *removable* singularity at 0 — y stays near 1 — and must
    render as one smooth curve; 1/x**2 has an even-order pole (no sign flip)
    that the numeric sign-flip heuristic misses entirely. A percentile-of-|y|
    test cannot separate them (a small-magnitude curve makes y≈1 look
    "large"), so confirmation is a ratio: the sample nearest the pole must
    dwarf the curve's own median |y| (pole-adjacent samples are orders of
    magnitude larger; sin(x)/x's center is only ~5x its median).
    """
    if not points or not pole_xs:
        return []
    abs_ys = sorted(abs(p[1]) for p in points)
    median = abs_ys[len(abs_ys) // 2]
    scale = max(median, 1e-9)
    confirmed: list[float] = []
    for pole in pole_xs[:8]:  # a pathological expr cannot explode segment count
        nearest = min(points, key=lambda p: abs(p[0] - pole))
        if abs(nearest[1]) > 25 * scale:
            confirmed.append(pole)
    return confirmed


def _split_at_xs(points: list[list[float]], pole_xs: list[float]) -> list[list[list[float]]]:
    """Split an x-sorted point list at each pole (one segment per side)."""
    segments: list[list[list[float]]] = []
    current: list[list[float]] = []
    idx = 0
    for point in points:
        while idx < len(pole_xs) and point[0] > pole_xs[idx]:
            idx += 1
            if current:
                segments.append(current)
                current = []
        current.append(point)
    if current:
        segments.append(current)
    return segments


def _removable_holes(
    original: Any, simplified: Any, sym: Symbol, x_min: float, x_max: float
) -> list[list[float]]:
    """Finite limits at zeros of the *original* denominator.

    Sampling the simplified expression alone loses removable discontinuities:
    SymPy turns ``(x^2-1)/(x-1)`` into ``x+1``.  The original parse is kept
    unevaluated solely to recover its domain; the plotted y-coordinate still
    comes from the verified two-sided limit of the simplified expression.
    """
    with sympy_decline() as declined:
        roots = solve(denom(original), sym)
    if declined:
        return []
    holes: list[list[float]] = []
    for root in roots[:8]:
        try:
            x_value = float(root)
            y_limit = limit(simplified, sym, root)
            y_value = float(y_limit)
        except (TypeError, ValueError, OverflowError):
            continue
        if x_min <= x_value <= x_max and math.isfinite(x_value) and math.isfinite(y_value):
            holes.append([round(x_value, 4), round(y_value, 4)])
    return holes


_MAX_GRAPH_SAMPLES = 500
_OSCILLATION_SAMPLES_PER_PERIOD = 16
_OSCILLATION_PERIODS_IN_VIEW = 8


def _oscillation_period(parsed: Any, sym: Symbol) -> float | None:
    """2π/|ω| (or π/|ω| for tan) when the expr contains sin/cos/tan of a linear arg."""
    for fn, base in ((tan, math.pi), (sin, 2 * math.pi), (cos, 2 * math.pi)):
        for atom in parsed.atoms(fn):
            arg = atom.args[0]
            if not arg.has(sym):
                continue
            deriv = arg.diff(sym)
            try:
                omega = abs(float(deriv))
            except (TypeError, ValueError):
                continue
            if omega > 0:
                return base / omega
    return None


def _adapt_sample_window(
    x_min: float, x_max: float, n: int, period: float | None
) -> tuple[float, float, int]:
    """Raise n or zoom so an oscillation is not aliased by a huge domain."""
    if period is None or period <= 0:
        return x_min, x_max, n
    width = x_max - x_min
    if width <= 0:
        return x_min, x_max, n
    needed = width / period * _OSCILLATION_SAMPLES_PER_PERIOD
    if needed <= n:
        return x_min, x_max, n
    if needed <= _MAX_GRAPH_SAMPLES:
        return x_min, x_max, min(_MAX_GRAPH_SAMPLES, max(n, math.ceil(needed)))
    mid = 0.0 if x_min < 0 < x_max else (x_min + x_max) / 2.0
    half = (_OSCILLATION_PERIODS_IN_VIEW * period) / 2.0
    zoom_n = min(
        _MAX_GRAPH_SAMPLES,
        max(n, int(_OSCILLATION_PERIODS_IN_VIEW * _OSCILLATION_SAMPLES_PER_PERIOD)),
    )
    return mid - half, mid + half, zoom_n


def sample_function(data: GraphSampleInput) -> GraphSampleResult:
    if data.x_max <= data.x_min:
        raise SolveServiceError("x_max must be greater than x_min")
    sym = Symbol(data.variable)
    parsed = parse_expression(data.expr, [data.variable])
    original = parse_expression(data.expr, [data.variable], evaluate=False)
    if parsed.is_Relational:
        raise SolveServiceError("Inequality expressions are number lines, not y=f(x) plots")

    numpy_fn = lambdify(sym, parsed, modules=["numpy"])
    x_min, x_max, n = _adapt_sample_window(
        data.x_min, data.x_max, data.n, _oscillation_period(parsed, sym)
    )
    xs = np.linspace(x_min, x_max, n)
    try:
        ys = sample_at(numpy_fn, xs)
    except Exception as exc:
        raise SolveServiceError(f"Could not sample function: {data.expr}") from exc
    points: list[list[float]] = []
    for x_val, y_val in zip(xs, ys, strict=False):
        if not np.isfinite(y_val):
            continue
        points.append([round(float(x_val), 4), round(float(y_val), 4)])

    # Symbolic poles (confirmed diverging by the samples) split at the true
    # singularity x — including even-order poles like 1/x**2 whose samples
    # never flip sign, which the numeric heuristic below cannot see. When
    # SymPy finds nothing decidable (tan, 1/sin, …) the numeric sign-flip
    # heuristic stays the fallback.
    pole_xs = _confirmed_pole_xs(points, _symbolic_pole_xs(parsed, sym, x_min, x_max))
    return GraphSampleResult(
        # The phone re-reads this to resample on zoom, so it is SymPy's reading, not the raw text.
        expr=graph_expr_text(parsed, data.variable) or data.expr,
        variable=data.variable,
        x_min=x_min,
        x_max=x_max,
        points=points,
        segments=_split_at_xs(points, pole_xs) if pole_xs else _split_into_segments(points),
        holes=_removable_holes(original, parsed, sym, x_min, x_max),
    )


def _viewport_from_points(points: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_min = min(x_min, 0.0)
    x_max = max(x_max, 0.0)
    y_min = min(y_min, 0.0)
    y_max = max(y_max, 0.0)
    span_x = x_max - x_min
    span_y = y_max - y_min
    pad_x = max(1.0, span_x * 0.15 if span_x > 1e-9 else 1.0)
    pad_y = max(1.0, span_y * 0.15 if span_y > 1e-9 else 1.0)
    return x_min - pad_x, x_max + pad_x, y_min - pad_y, y_max + pad_y


def sample_polar_curve(expr: str, variable: str = "theta", n: int = 96) -> GraphSampleResult:
    """Sample ``r = f(θ)`` on ``[0, 2π]`` into cartesian `` ```graph `` points."""
    count = max(16, min(int(n), 500))
    sym = Symbol(variable)
    parsed = parse_expression(expr, [variable])
    numpy_fn = lambdify(sym, parsed, modules=["numpy"])
    thetas = np.linspace(0.0, 2.0 * math.pi, count, endpoint=True)
    points: list[list[float]] = []
    try:
        radii = sample_at(numpy_fn, thetas)
    except Exception as exc:
        raise SolveServiceError(f"Could not sample polar curve: {expr}") from exc
    for theta, radius in zip(thetas, radii, strict=False):
        if not np.isfinite(radius):
            continue
        points.append(
            [
                round(float(radius * math.cos(float(theta))), 4),
                round(float(radius * math.sin(float(theta))), 4),
            ]
        )
    if len(points) < 2:
        raise SolveServiceError(f"Could not sample polar curve: {expr}")
    x_min, x_max, _y_min, _y_max = _viewport_from_points(points)
    return GraphSampleResult(
        expr=f"r = {expr}",
        variable=variable,
        x_min=x_min,
        x_max=x_max,
        points=points,
        segments=[],
    )


def sample_parametric_curve(
    x_expr: str, y_expr: str, variable: str = "t", n: int = 96
) -> GraphSampleResult:
    """Sample ``x(t), y(t)`` on ``[0, 2π]`` into cartesian `` ```graph `` points."""
    count = max(16, min(int(n), 500))
    sym = Symbol(variable)
    parsed_x = parse_expression(x_expr, [variable])
    parsed_y = parse_expression(y_expr, [variable])
    fx = lambdify(sym, parsed_x, modules=["numpy"])
    fy = lambdify(sym, parsed_y, modules=["numpy"])
    ts = np.linspace(0.0, 2.0 * math.pi, count, endpoint=True)
    points: list[list[float]] = []
    try:
        xs = sample_at(fx, ts)
        ys = sample_at(fy, ts)
    except Exception as exc:
        raise SolveServiceError(f"Could not sample parametric curve: {x_expr}, {y_expr}") from exc
    for x_val, y_val in zip(xs, ys, strict=False):
        if not np.isfinite(x_val) or not np.isfinite(y_val):
            continue
        points.append([round(float(x_val), 4), round(float(y_val), 4)])
    if len(points) < 2:
        raise SolveServiceError(f"Could not sample parametric curve: {x_expr}, {y_expr}")
    x_min, x_max, _y_min, _y_max = _viewport_from_points(points)
    return GraphSampleResult(
        expr=f"x = {x_expr}, y = {y_expr}",
        variable=variable,
        x_min=x_min,
        x_max=x_max,
        points=points,
        segments=_split_into_segments(points),
    )


# Axis-aligned ellipse / circle relations only (not general F(x,y)=0).
_CIRCLE_RELATION_RE = re.compile(r"^(?:x\*\*2\+y\*\*2|y\*\*2\+x\*\*2)=(\d+(?:\.\d+)?)$")
_ELLIPSE_DIV_RELATION_RE = re.compile(r"^x\*\*2/(\d+(?:\.\d+)?)\+y\*\*2/(\d+(?:\.\d+)?)=1$")
_ELLIPSE_DIV_RELATION_YX_RE = re.compile(r"^y\*\*2/(\d+(?:\.\d+)?)\+x\*\*2/(\d+(?:\.\d+)?)=1$")
_ELLIPSE_SCALE_RELATION_RE = re.compile(
    r"^\(x/(\d+(?:\.\d+)?)\)\*\*2\+\(y/(\d+(?:\.\d+)?)\)\*\*2=1$"
)


def parse_ellipse_relation(expr: str) -> tuple[float, float] | None:
    """Parse ``x^2+y^2=r^2`` / ``x^2/a^2+y^2/b^2=1`` into semi-axes ``(a, b)``.

    Returns ``None`` for anything that is not this narrow homework shape —
    general implicit curves stay out of scope.
    """
    s = expr.strip().replace("^", "**")
    s = re.sub(r"\s+", "", s)
    if not s:
        return None
    m = _CIRCLE_RELATION_RE.fullmatch(s)
    if m:
        r2 = float(m.group(1))
        if r2 <= 0:
            return None
        r = math.sqrt(r2)
        return r, r
    m = _ELLIPSE_DIV_RELATION_RE.fullmatch(s)
    if m:
        a2, b2 = float(m.group(1)), float(m.group(2))
        if a2 <= 0 or b2 <= 0:
            return None
        return math.sqrt(a2), math.sqrt(b2)
    m = _ELLIPSE_DIV_RELATION_YX_RE.fullmatch(s)
    if m:
        b2, a2 = float(m.group(1)), float(m.group(2))
        if a2 <= 0 or b2 <= 0:
            return None
        return math.sqrt(a2), math.sqrt(b2)
    m = _ELLIPSE_SCALE_RELATION_RE.fullmatch(s)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a <= 0 or b <= 0:
            return None
        return a, b
    return None


def sample_ellipse(a: float, b: float, n: int = 96) -> GraphSampleResult:
    """Parametric samples for ``(x/a)^2 + (y/b)^2 = 1`` as a closed polyline."""
    if a <= 0 or b <= 0:
        raise SolveServiceError("Ellipse semi-axes must be positive")
    count = max(16, min(int(n), 500))
    thetas = np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)
    points: list[list[float]] = [
        [round(float(a * math.cos(t)), 4), round(float(b * math.sin(t)), 4)] for t in thetas
    ]
    # Close the loop so the SVG polyline does not leave a gap at θ=0.
    points.append(points[0])
    if abs(a - b) < 1e-12:
        label = f"x**2 + y**2 = {a * a:g}"
    else:
        label = f"x**2/{a * a:g} + y**2/{b * b:g} = 1"
    pad_x = max(1.0, a * 0.15)
    return GraphSampleResult(
        expr=label,
        variable="x",
        x_min=-(a + pad_x),
        x_max=a + pad_x,
        points=points,
        segments=[],
    )


def build_ellipse_graph_spec(expr: str, n: int) -> GraphBlockSpec | None:
    """If ``expr`` is an axis-aligned circle/ellipse relation, return the
    parametrically-sampled ``GraphBlockSpec`` (with a square-ish viewport
    around the curve); otherwise ``None``.

    Shared by the heuristic ``_verified_block_graph`` (math/tools) and the
    MCP ``sympy`` adapter so the sampling and y-range padding live in one
    place — previously both copied the same ``-(b + max(1.0, b * 0.15))`` /
    ``b + max(1.0, b * 0.15)`` viewport math, which could drift.
    """
    ellipse = parse_ellipse_relation(expr)
    if ellipse is None:
        return None
    a, b = ellipse
    sample = sample_ellipse(a, b, n)
    return GraphBlockSpec(
        expr=sample.expr,
        variable=sample.variable,
        x_min=sample.x_min,
        x_max=sample.x_max,
        y_min=-(b + max(1.0, b * 0.15)),
        y_max=b + max(1.0, b * 0.15),
        points=sample.points,
        segments=[],
        title=sample.expr,
    )


_MAX_NUMBER_LINE_INTERVALS = 8


def expr_looks_like_inequality(expr: str) -> bool:
    """True when ``expr`` has a comparison op (not a plain y=f(x) or x=c)."""
    compact = expr.replace(" ", "")
    return any(op in compact for op in (">=", "<=", ">", "<", "≥", "≤"))


def _finite_or_none(bound: Any) -> float | None:
    if bound is None:
        return None
    if getattr(bound, "is_infinite", False):
        return None
    try:
        value = float(bound)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _collect_number_line_intervals(sol: Any, out: list[NumberLineInterval]) -> bool:
    """Walk a SymPy set into number-line intervals. False = unsupported shape."""
    if sol is None or sol is EmptySet or sol == S.EmptySet:
        return True
    if sol == S.Reals:
        out.append(NumberLineInterval(start=None, end=None))
        return True
    if isinstance(sol, Interval):
        start = _finite_or_none(sol.start)
        end = _finite_or_none(sol.end)
        out.append(
            NumberLineInterval(
                start=start,
                end=end,
                start_inclusive=start is not None and not bool(sol.left_open),
                end_inclusive=end is not None and not bool(sol.right_open),
            )
        )
        return True
    if isinstance(sol, FiniteSet):
        for point in sol:
            value = _finite_or_none(point)
            if value is None:
                return False
            out.append(
                NumberLineInterval(
                    start=value,
                    end=value,
                    start_inclusive=True,
                    end_inclusive=True,
                )
            )
        return True
    if isinstance(sol, Union):
        return all(_collect_number_line_intervals(arg, out) for arg in sol.args)
    return False


def _inequality_solution_set(expr: str, variable: str) -> Any:
    """The set a number line draws: the answer card's own (``solve/inequalities.py``)."""
    compound = try_extract_compound_inequality_from_text(expr)
    if compound is not None:
        return compound_solution_set(*compound, variable)
    ineq = try_extract_inequality_from_text(expr)
    if ineq is None:
        raise SolveServiceError("Not a 1-variable inequality")
    lhs, rhs, comparator = ineq
    return inequality_solution_set(lhs, rhs, comparator, variable)


def number_line_spec_from_expr(expr: str, variable: str = "x") -> GraphBlockSpec | None:
    """Turn ``x > 3`` / ``1 < x < 5`` into a number-line fence, or None.

    Two-variable relations (``y > 2x``) stay out — those are half-planes, not
    a 1D number line. Unsolvable / exotic sets also return None.
    """
    cleaned = expr.strip()
    if not cleaned or not expr_looks_like_inequality(cleaned):
        return None
    vars_found = guess_variables(cleaned)
    if len(vars_found) > 1:
        return None
    var = vars_found[0] if vars_found else variable
    try:
        sol = _inequality_solution_set(cleaned, var)
        intervals: list[NumberLineInterval] = []
        if not _collect_number_line_intervals(sol, intervals):
            return None
        if len(intervals) > _MAX_NUMBER_LINE_INTERVALS:
            return None
    except SolveServiceError:
        return None
    return GraphBlockSpec(
        type="number_line",
        expr=cleaned[:256],
        variable=var,
        title=cleaned[:64],
        intervals=intervals,
    )
