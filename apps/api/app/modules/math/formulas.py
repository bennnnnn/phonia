"""Closed-form school/undergrad calculations that are not a new MathIntent.kind."""

from __future__ import annotations

import math
from fractions import Fraction

from sympy import (
    Abs,
    AccumBounds,
    I,
    Integral,
    Limit,
    Matrix,
    Symbol,
    arg,
    conjugate,
    cos,
    diff,
    factorial,
    idiff,
    mod_inverse,
    nan,
    oo,
    simplify,
    sin,
    totient,
    zoo,
)
from sympy.ntheory.modular import solve_congruence

from app.modules.math.school import _format_school_number, _imaginary_unit_to_sympy, _progression
from app.modules.math.solve import (
    SolveServiceError,
    definite_integral,
    format_verified_latex,
    parse_expression,
)
from app.modules.math.solve.calculus import _parse_infinity_aware_point
from app.services.school_rounding import round_figures, round_places


def sale_price(base: float, rate: float) -> str:
    if not math.isfinite(base) or not math.isfinite(rate) or rate < 0 or rate > 100:
        raise SolveServiceError("discount needs a finite base and a rate in [0, 100]")
    return _format_school_number(base * (1.0 - rate / 100.0))


def percent_change_from(start: float, end: float) -> str:
    if not math.isfinite(start) or not math.isfinite(end) or start == 0:
        raise SolveServiceError("percent change needs a nonzero start")
    return _format_school_number((end - start) / start * 100.0)


def direct_proportion(a: float, b: float, c: float) -> str:
    if a == 0 or not all(math.isfinite(v) for v in (a, b, c)):
        raise SolveServiceError("direct proportion needs a nonzero first quantity")
    return _format_school_number(b / a * c)


def inverse_proportion(a: float, b: float, c: float) -> str:
    if c == 0 or not all(math.isfinite(v) for v in (a, b, c)):
        raise SolveServiceError("inverse proportion needs a nonzero third quantity")
    return _format_school_number(a * b / c)


def round_decimal_places(value: float, places: int) -> str:
    if not math.isfinite(value) or places < 0 or places > 12:
        raise SolveServiceError("rounding needs a finite value and 0-12 places")
    return _format_school_number(float(round_places(value, places)))


def round_significant_figures(value: float, figs: int) -> str:
    if not math.isfinite(value) or value == 0 or figs < 1 or figs > 12:
        raise SolveServiceError("significant figures need a nonzero finite value")
    mantissa, exponent = round_figures(value, figs)
    return _format_school_number(float(mantissa.scaleb(exponent)))


def infinite_geometric_sum(terms: list[float]) -> str:
    kind = _progression(terms)
    if kind is None or kind[0] != "gp":
        raise SolveServiceError("infinite sum needs a geometric sequence")
    _op, first, ratio = kind
    if abs(float(ratio)) >= 1:
        raise SolveServiceError("infinite geometric sum needs |r| < 1")
    return _format_school_number(float(first / (1 - ratio)))


def present_value(amount: float, rate: float, years: int) -> str:
    if not math.isfinite(amount) or not math.isfinite(rate) or years < 1:
        raise SolveServiceError("present value needs a finite amount, rate, and positive years")
    return _format_school_number(amount / ((1.0 + rate / 100.0) ** years))


def line_through(x1: float, y1: float, x2: float, y2: float) -> str:
    if x1 == x2:
        return f"x = {_format_school_number(x1)}"
    slope = Fraction(str(y2 - y1)) / Fraction(str(x2 - x1))
    intercept = Fraction(str(y1)) - slope * Fraction(str(x1))
    expr = slope * Symbol("x") + intercept
    return f"y = {format_verified_latex(expr)}"


def point_to_line(x0: float, y0: float, a: float, b: float, c: float) -> str:
    denom = math.hypot(a, b)
    if denom == 0:
        raise SolveServiceError("not a line")
    return _format_school_number(abs(a * x0 + b * y0 + c) / denom)


def vector_angle_degrees(a: list[float], b: list[float]) -> str:
    if len(a) != len(b) or not a:
        raise SolveServiceError("angle needs matching vectors")
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        raise SolveServiceError("angle needs nonzero vectors")
    cosine = sum(x * y for x, y in zip(a, b, strict=True)) / (mag_a * mag_b)
    cosine = max(-1.0, min(1.0, cosine))
    return _format_school_number(math.degrees(math.acos(cosine)))


def vector_unit(vec: list[float]) -> str:
    mag = math.sqrt(sum(c * c for c in vec))
    if mag == 0:
        raise SolveServiceError("zero vector has no unit vector")
    parts = ", ".join(_format_school_number(c / mag) for c in vec)
    return f"<{parts}>"


def vector_projection(a: list[float], b: list[float]) -> str:
    if len(a) != len(b) or not b:
        raise SolveServiceError("projection needs matching vectors")
    denom = sum(x * x for x in b)
    if denom == 0:
        raise SolveServiceError("cannot project onto the zero vector")
    scale = sum(x * y for x, y in zip(a, b, strict=True)) / denom
    parts = ", ".join(_format_school_number(scale * x) for x in b)
    return f"<{parts}>"


def _complex_value(expr: str):
    parsed = parse_expression(_imaginary_unit_to_sympy(expr), ["x"])
    if parsed.free_symbols:
        raise SolveServiceError("complex expression still has variables")
    return simplify(parsed)


def complex_modulus(expr: str) -> str:
    return format_verified_latex(Abs(_complex_value(expr)))


def complex_argument(expr: str) -> str:
    return format_verified_latex(arg(_complex_value(expr)))


def complex_conjugate(expr: str) -> str:
    return format_verified_latex(conjugate(_complex_value(expr)))


def complex_polar(expr: str) -> str:
    value = _complex_value(expr)
    radius = Abs(value)
    theta = arg(value)
    return format_verified_latex(radius * (cos(theta) + I * sin(theta)))


def geometric_pmf(k: int, p: float) -> str:
    if k < 1 or not (0.0 < p <= 1.0):
        raise SolveServiceError("geometric PMF needs k >= 1 and p in (0, 1]")
    return _format_school_number(((1.0 - p) ** (k - 1)) * p)


def poisson_pmf(k: int, lam: float) -> str:
    if k < 0 or lam < 0 or not math.isfinite(lam):
        raise SolveServiceError("Poisson PMF needs k >= 0 and lambda >= 0")
    return _format_school_number((lam**k) * math.exp(-lam) / float(factorial(k)))


def complement_probability(p: float) -> str:
    if not (0.0 <= p <= 1.0):
        raise SolveServiceError("probability must be in [0, 1]")
    return _format_school_number(1.0 - p)


def bayes_probability(prior: float, hit: float, miss: float) -> str:
    if not all(0.0 <= v <= 1.0 for v in (prior, hit, miss)):
        raise SolveServiceError("Bayes needs probabilities in [0, 1]")
    evidence = hit * prior + miss * (1.0 - prior)
    if evidence == 0:
        raise SolveServiceError("Bayes evidence is zero")
    return _format_school_number(hit * prior / evidence)


def quartiles(numbers: list[float]) -> str:
    if len(numbers) < 2:
        raise SolveServiceError("quartiles need at least two values")
    import statistics as stats

    cuts = stats.quantiles(numbers, n=4, method="inclusive")
    return ", ".join(_format_school_number(value) for value in cuts)


def interquartile_range(numbers: list[float]) -> str:
    if len(numbers) < 2:
        raise SolveServiceError("IQR needs at least two values")
    import statistics as stats

    cuts = stats.quantiles(numbers, n=4, method="inclusive")
    return _format_school_number(cuts[2] - cuts[0])


def percentile(numbers: list[float], p: int) -> str:
    if not numbers or p < 0 or p > 100:
        raise SolveServiceError("percentile needs p in 0-100")
    ordered = sorted(numbers)
    if p == 0:
        return _format_school_number(ordered[0])
    if p == 100:
        return _format_school_number(ordered[-1])
    import statistics as stats

    cuts = stats.quantiles(numbers, n=100, method="inclusive")
    return _format_school_number(cuts[p - 1])


def modular_inverse(a: int, modulus: int) -> str:
    if modulus <= 1:
        raise SolveServiceError("modular inverse needs modulus > 1")
    try:
        return str(int(mod_inverse(a, modulus)))
    except ValueError as exc:
        raise SolveServiceError("no modular inverse") from exc


def euler_totient(n: int) -> str:
    if n < 1:
        raise SolveServiceError("totient needs a positive integer")
    return str(int(totient(n)))


def chinese_remainder(a: int, m: int, b: int, n: int) -> str:
    if m <= 0 or n <= 0:
        raise SolveServiceError("CRT moduli must be positive")
    try:
        solved = solve_congruence((a, m), (b, n))
    except ValueError as exc:
        raise SolveServiceError("no CRT solution") from exc
    if solved is None:
        raise SolveServiceError("no CRT solution")
    residue, _modulus = solved
    return str(int(residue))


def sas_triangle_area(side_a: float, side_b: float, angle_deg: float) -> str:
    if side_a <= 0 or side_b <= 0 or not (0 < angle_deg < 180):
        raise SolveServiceError("SAS area needs two positive sides and an angle in (0, 180)")
    return _format_school_number(0.5 * side_a * side_b * math.sin(math.radians(angle_deg)))


def average_value(expr: str, variable: str, lower: str, upper: str) -> str:
    parsed = parse_expression(expr, [variable])
    # "infinity" is oo, not the letters i, n, f, t and y; and an average needs
    # a finite interval (sin over [0, oo) was <0, 2> / oo = 0).
    lo = _parse_infinity_aware_point(lower)
    hi = _parse_infinity_aware_point(upper)
    if lo.is_finite is False or hi.is_finite is False:
        raise SolveServiceError("average value needs a finite interval")
    width = simplify(hi - lo)
    if width == 0:
        raise SolveServiceError("average value needs a nonempty interval")
    total = definite_integral(parsed, Symbol(variable), lo, hi)
    # 1/x^2 on [-1, 1] diverges; x^x is left unevaluated.
    unsettled = total.has(AccumBounds, Integral, Limit, nan, zoo, oo, -oo)
    if unsettled or total.is_extended_real is False:
        raise SolveServiceError("average value needs an integral with a finite value")
    return format_verified_latex(simplify(total / width))


def linear_approximation(expr: str, variable: str, point: str) -> str:
    parsed = parse_expression(expr, [variable])
    var = Symbol(variable)
    at = parse_expression(point, [variable])
    value = parsed.subs(var, at)
    slope = diff(parsed, var).subs(var, at)
    return format_verified_latex(simplify(value + slope * (var - at)))


def gradient_of(expr: str) -> str:
    parsed = parse_expression(expr, ["x", "y", "z"])
    names = sorted(str(symbol) for symbol in parsed.free_symbols)
    if not names:
        raise SolveServiceError("gradient needs a non-constant expression")
    parts = [diff(parsed, Symbol(name)) for name in names]
    return format_verified_latex(Matrix(parts))


def directional_derivative(expr: str, point: tuple[float, ...], direction: list[float]) -> str:
    parsed = parse_expression(expr, ["x", "y", "z"])
    names = ["x", "y", "z"][: len(point)]
    if len(direction) != len(point):
        raise SolveServiceError("direction must match the point dimension")
    mag = math.sqrt(sum(c * c for c in direction))
    if mag == 0:
        raise SolveServiceError("direction must be nonzero")
    unit = [c / mag for c in direction]
    total = 0
    for name, _coordinate, component in zip(names, point, unit, strict=True):
        partial = diff(parsed, Symbol(name))
        for other, value in zip(names, point, strict=True):
            partial = partial.subs(Symbol(other), value)
        total += partial * component
    return format_verified_latex(simplify(total))


def _vector_field(expr: str) -> list:
    parts = [part.strip() for part in expr.split(",")]
    if len(parts) not in {2, 3}:
        raise SolveServiceError("vector field needs 2 or 3 components")
    names = ["x", "y", "z"][: len(parts)]
    return [parse_expression(part, names) for part in parts]


def divergence_of(expr: str) -> str:
    components = _vector_field(expr)
    names = ["x", "y", "z"][: len(components)]
    total = sum(
        diff(component, Symbol(name)) for component, name in zip(components, names, strict=True)
    )
    return format_verified_latex(simplify(total))


def curl_of(expr: str) -> str:
    components = _vector_field(expr)
    if len(components) == 2:
        components = [*components, 0]
    cx, cy, cz = components
    x, y, z = Symbol("x"), Symbol("y"), Symbol("z")
    curl = Matrix(
        [
            diff(cz, y) - diff(cy, z),
            diff(cx, z) - diff(cz, x),
            diff(cy, x) - diff(cx, y),
        ]
    )
    return format_verified_latex(simplify(curl))


def implicit_derivative(lhs: str, rhs: str, independent: str = "x", dependent: str = "y") -> str:
    left = parse_expression(lhs, [independent, dependent])
    right = parse_expression(rhs, [independent, dependent])
    try:
        out = idiff(left - right, Symbol(dependent), Symbol(independent))
    except Exception as exc:
        raise SolveServiceError("could not implicitly differentiate") from exc
    return format_verified_latex(simplify(out))


def _term_ratio(terms: list[float]) -> Fraction | None:
    kind = _progression(terms)
    if kind is None or kind[0] != "gp":
        return None
    return kind[2]


def is_convergent_geometric(terms: list[float]) -> bool:
    ratio = _term_ratio(terms)
    return ratio is not None and abs(float(ratio)) < 1
