"""Verified calculus applications: area between curves, arc length, volume.

These are the shapes `extract_math_intent` refused outright after an area
question was answered with the *intersection points* of its two curves. The
refusal was the right stopgap; this replaces it with real answers, and keeps a
refusal for every case SymPy cannot close.

The rule throughout: a verified block tells the model not to recompute, so an
unevaluated integral, a non-finite result, or a region whose sign we cannot
establish is refused rather than approximated.
"""

from __future__ import annotations

import math
from typing import Any

from sympy import Eq, FiniteSet, Integral, Interval, S, Symbol, pi, simplify, solveset
from sympy.calculus.util import continuous_domain

from app.modules.math.solve import (
    SolveServiceError,
    definite_integral,
    format_verified_latex,
    parse_expression,
)

# A region split at more crossings than this is not a homework question, and
# each split multiplies the symbolic work.
_MAX_CROSSINGS = 32


def _expression(expr: str, variable: str):
    if not (expr or "").strip():
        raise SolveServiceError("an expression is required")
    try:
        parsed = parse_expression(expr, [variable], real=True)
    except SolveServiceError:
        raise
    except Exception as exc:
        raise SolveServiceError("could not parse the expression") from exc
    extra = {str(symbol) for symbol in parsed.free_symbols if str(symbol) != variable}
    if extra:
        raise SolveServiceError("calculus applications support one variable at a time")
    return parsed


def _ordered_bounds(lower: str, upper: str):
    low = parse_expression(lower, [], real=True)
    high = parse_expression(upper, [], real=True)
    try:
        width = float((high - low).evalf())
    except (TypeError, ValueError, OverflowError) as exc:
        raise SolveServiceError("the bounds must be finite real values") from exc
    if not math.isfinite(width):
        raise SolveServiceError("the bounds must be finite")
    if width <= 0:
        raise SolveServiceError("the upper bound must be greater than the lower bound")
    return low, high


def _require_continuous(expr, variable: Symbol, low, high) -> None:
    """A discontinuity inside the interval makes the integral improper.

    Answering one as if it were proper is the kind of confident wrong number
    this module exists to avoid.
    """
    try:
        domain = continuous_domain(expr, variable, S.Reals)
    except (NotImplementedError, TypeError) as exc:
        raise SolveServiceError("could not verify continuity on that interval") from exc
    if Interval(low, high).is_subset(domain) is not True:
        raise SolveServiceError("the expression is not continuous on that interval")


def _closed_form(value, label: str):
    if value.has(Integral):
        raise SolveServiceError(f"no closed form for this {label} was found")
    if value in {S.NaN, S.ComplexInfinity, S.Infinity, S.NegativeInfinity}:
        raise SolveServiceError(f"this {label} is not finite")
    return simplify(value)


def _integrate_absolute(expr, variable: Symbol, low, high):
    """Integrate |expr|, splitting at the crossings inside the interval.

    Integrating the signed difference would let a region below the axis cancel
    one above it, so "the area between" two curves that cross would come back
    smaller than it is — and for a symmetric crossing, zero.
    """
    if simplify(expr) == 0:
        return S.Zero
    try:
        roots = solveset(Eq(expr, 0), variable, domain=Interval(low, high))
    except (NotImplementedError, TypeError) as exc:
        raise SolveServiceError("could not locate the crossings symbolically") from exc
    if roots is S.EmptySet:
        # No crossing at all (y = 3x^2 + 1 stays above the axis): one piece.
        found: list[Any] = []
    elif isinstance(roots, FiniteSet):
        found = list(roots)
    else:
        raise SolveServiceError("could not enumerate every crossing on that interval")
    if len(found) > _MAX_CROSSINGS:
        raise SolveServiceError("too many crossings to verify")

    low_f = float(low.evalf())
    high_f = float(high.evalf())
    inner: list[tuple[float, object]] = []
    for root in found:
        if root.has(variable) or root.is_real is False:
            continue
        try:
            root_f = float(root.evalf())
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(root_f) and low_f < root_f < high_f:
            if not any(abs(root_f - seen) < 1e-10 for seen, _ in inner):
                inner.append((root_f, root))
    inner.sort(key=lambda item: item[0])

    points = [low, *(root for _, root in inner), high]
    total = S.Zero
    for index in range(len(points) - 1):
        left, right = points[index], points[index + 1]
        midpoint = simplify((left + right) / 2)
        try:
            sign = float(expr.subs(variable, midpoint).evalf())
        except (TypeError, ValueError, OverflowError) as exc:
            raise SolveServiceError("could not determine the sign between crossings") from exc
        if not math.isfinite(sign):
            raise SolveServiceError("the integrand is not finite on that interval")
        piece = definite_integral(expr, variable, left, right)
        if piece.has(Integral):
            raise SolveServiceError("no closed form for this area was found")
        total += -piece if sign < 0 else piece
    return simplify(total)


def area_between_curves(
    upper_expr: str, lower_expr: str, low: str, high: str, variable: str = "x"
) -> str:
    """The area enclosed between two curves over a stated interval."""
    sym = Symbol(variable, real=True)
    first = _expression(upper_expr, variable)
    second = _expression(lower_expr, variable)
    start, stop = _ordered_bounds(low, high)
    _require_continuous(first, sym, start, stop)
    _require_continuous(second, sym, start, stop)
    return format_verified_latex(
        _closed_form(_integrate_absolute(first - second, sym, start, stop), "area")
    )


def arc_length(expr: str, low: str, high: str, variable: str = "x") -> str:
    """Arc length of y = f(x): the integral of sqrt(1 + f'(x)^2)."""
    sym = Symbol(variable, real=True)
    parsed = _expression(expr, variable)
    start, stop = _ordered_bounds(low, high)
    _require_continuous(parsed, sym, start, stop)
    integrand = (1 + parsed.diff(sym) ** 2) ** S.Half
    return format_verified_latex(
        _closed_form(definite_integral(integrand, sym, start, stop), "arc length")
    )


def volume_of_revolution(
    expr: str, low: str, high: str, axis: str = "x", variable: str = "x"
) -> str:
    """Volume swept by y = f(x) revolved about an axis.

    About x it is the disk method, pi * integral of f^2. About y it is
    cylindrical shells, 2 pi * integral of x f(x) — which is only a volume when
    the interval stays on one side of the axis, so a straddling interval is
    refused rather than returned as a signed difference.
    """
    sym = Symbol(variable, real=True)
    parsed = _expression(expr, variable)
    start, stop = _ordered_bounds(low, high)
    _require_continuous(parsed, sym, start, stop)

    if axis == "x":
        value = pi * definite_integral(parsed**2, sym, start, stop)
        return format_verified_latex(_closed_form(value, "volume"))

    if axis != "y":
        raise SolveServiceError("only the x and y axes are supported")
    if float(start.evalf()) < 0 < float(stop.evalf()):
        raise SolveServiceError(
            "a shell volume needs an interval on one side of the axis of revolution"
        )
    shells = _integrate_absolute(sym * parsed, sym, start, stop)
    return format_verified_latex(_closed_form(2 * pi * shells, "volume"))
