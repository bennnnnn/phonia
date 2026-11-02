"""Derivatives, integrals, limits and series — SymPy, with verified worked lines."""

from __future__ import annotations

import cmath
from typing import Any

from sympy import (
    Abs,
    AccumBounds,
    Integral,
    Limit,
    Mul,
    Sum,
    Symbol,
    diff,
    integrate,
    lambdify,
    latex,
    limit,
    log,
    nan,
    oo,
    simplify,
    sympify,
    zoo,
)

from app.modules.math.schemas import (
    MathExprResult,
    MathLimitResult,
    MathSeriesResult,
)
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.display import derivative_latex, format_verified_latex
from app.modules.math.solve.parse import SolveServiceError, parse_expression
from app.modules.math.solve.root_latex import expr_equal
from app.services.times_sign import TIMES

# A quadrature whose own error estimate is above _QUADRATURE_TRUST (relative) judges nothing; a
# closed form within _QUADRATURE_AGREE of a trusted one passes.
_QUADRATURE_TRUST = 1e-8
_QUADRATURE_AGREE = 1e-6


def _term_derivative_step(term: Any, sym: Any) -> str:
    """One verified worked line for the derivative of a single term, naming
    the rule by structure. The derivative itself is always SymPy-computed so
    the shown value is verified; the rule label is a best-effort classification
    (power/constant-multiple/product/quotient/chain) so the model can copy a
    real derivation instead of inventing one."""
    deriv = diff(term, sym)
    lhs = f"\\frac{{d}}{{d{latex(sym)}}}\\left[{latex(term)}\\right]"
    # Constant: no occurrence of the differentiation variable.
    if not term.free_symbols & {sym}:
        return f"Constant rule: ${lhs} = 0$"
    # Power rule: x or x^n with base == sym.
    if term == sym:
        return f"Power rule: ${lhs} = {latex(deriv)}$"
    if getattr(term, "is_Pow", False) and term.base == sym:
        return (
            f"Power rule: ${lhs} = {latex(term.exp)} {TIMES} "
            f"{latex(sym)}^{{{latex(term.exp - 1)}}} = {latex(deriv)}$"
        )
    # Product / quotient / constant-multiple.
    if getattr(term, "is_Mul", False):
        dep = [f for f in term.args if f.free_symbols & {sym}]
        if len(dep) == 1:
            const = [f for f in term.args if not (f.free_symbols & {sym})]
            return (
                f"Constant multiple: ${lhs} = {latex(Mul(*const) if const else 1)} {TIMES} "
                f"\\frac{{d}}{{d{latex(sym)}}}\\left[{latex(dep[0])}\\right] = {latex(deriv)}$"
            )
        return f"Product rule: ${lhs} = {latex(deriv)}$"
    if getattr(term, "is_Pow", False) and term.base != sym:
        # e.g. e^x, 2^x, sin(x)^2 — chain rule territory.
        return f"Chain rule: ${lhs} = {latex(deriv)}$"
    # Anything else with a function of sym (sin, cos, exp, log, …) → chain rule.
    return f"Chain rule: ${lhs} = {latex(deriv)}$"


def _differentiation_steps(parsed: Any, sym: Any, result_latex: str) -> list[str]:
    """Verified step-by-step derivation for a single-variable derivative.

    Sums are split by the sum rule (linearity); each term gets a rule-named
    line with its SymPy-computed derivative; the final result line closes.
    """
    steps: list[str] = []
    if getattr(parsed, "is_Add", False):
        steps.append(
            f"Sum rule (linearity): $\\frac{{d}}{{d{latex(sym)}}}\\left[{latex(parsed)}\\right] "
            f"= \\sum \\frac{{d}}{{d{latex(sym)}}}\\left[\\text{{each term}}\\right]$"
        )
        for term in parsed.args:
            steps.append(_term_derivative_step(term, sym))
    else:
        steps.append(_term_derivative_step(parsed, sym))
    steps.append(
        f"Result: $\\frac{{d}}{{d{latex(sym)}}}\\left[{latex(parsed)}\\right] = {result_latex}$"
    )
    return steps


def differentiate_expression(expr: str, variable: str = "x", order: int = 1) -> MathExprResult:
    if order < 1 or order > 4:
        raise SolveServiceError("unsupported derivative order")
    sym = Symbol(variable)
    parsed = parse_expression(expr, [variable])
    result = diff(parsed, sym, order)
    result_latex = derivative_latex(result)
    if order == 1:
        steps = _differentiation_steps(parsed, sym, result_latex)
    else:
        ordinals = {1: "first", 2: "second", 3: "third", 4: "fourth"}
        current = parsed
        steps = []
        for index in range(1, order + 1):
            current = diff(current, sym)
            # The operator acts on the expression, ``\frac{d}{dx}\left(x^{4}\right)``;
            # no ``y`` the question did not name.
            derivative_tex = (
                rf"\frac{{d}}{{d{latex(sym)}}}"
                if index == 1
                else rf"\frac{{d^{{{index}}}}}{{d{latex(sym)}^{{{index}}}}}"
            )
            steps.append(
                f"${derivative_tex}\\left({latex(parsed)}\\right) = {derivative_latex(current)}$"
                f" — {ordinals[index]} derivative"
            )
    return MathExprResult(
        result=str(result),
        latex=result_latex,
        steps=steps,
    )


def differentiate_at_point(expr: str, variable: str, point: str) -> MathExprResult:
    """Evaluate the two-sided derivative definition at a named real point."""
    sym = Symbol(variable, real=True)
    parsed = parse_expression(expr, [variable], real=True)
    at = parse_expression(point, [variable], real=True)
    quotient = simplify((parsed - parsed.subs(sym, at)) / (sym - at))
    try:
        left = limit(quotient, sym, at, dir="-")
        right = limit(quotient, sym, at, dir="+")
    except Exception as exc:
        raise SolveServiceError("Could not evaluate derivative at the requested point") from exc
    finite = bool(left.is_finite is True and right.is_finite is True)
    if not finite or not expr_equal(left, right):
        if finite:
            reason = (
                f"Left derivative: {latex(left)}; right derivative: {latex(right)}; "
                "they do not agree."
            )
        else:
            reason = "The difference quotient is not finite from both sides."
        return MathExprResult(
            result="undefined",
            latex=r"\text{undefined}",
            steps=[reason],
        )
    value = simplify(left)
    return MathExprResult(
        result=str(value),
        latex=format_verified_latex(value),
        steps=[f"The left- and right-hand difference quotients both equal {latex(value)}."],
    )


def _absolute_logs(antiderivative: Any, integrand: Any, sym: Any) -> Any:
    """``∫ u'/u = ln|u|``: SymPy writes ``log(u)``, true only where ``u > 0``.

    A log the integrand already had (``∫ ln x``) keeps its own domain, and an
    argument that is always positive (``x² + 1``) needs no bars.
    """
    if integrand.has(log):
        return antiderivative
    real = Symbol(sym.name, real=True)
    bars = {
        term: log(Abs(term.args[0]))
        for term in antiderivative.atoms(log)
        if not term.args[0].subs(sym, real).is_positive
    }
    return antiderivative.xreplace(bars) if bars else antiderivative


def integrate_expression(expr: str, variable: str = "x") -> MathExprResult:
    sym = Symbol(variable)
    parsed = parse_expression(expr, [variable])
    result = _absolute_logs(integrate(parsed, sym), parsed, sym)
    # integrate() can fail to find a closed form and hand back a result that
    # still contains an unevaluated Integral(...) rather than raising —
    # callers must not treat that as a verified, fully-solved answer.
    solved = not result.has(Integral)
    return MathExprResult(result=str(result), latex=format_verified_latex(result), solved=solved)


def definite_integral(integrand: Any, sym: Any, low: Any, high: Any) -> Any:
    """``integrate(f, (x, a, b))``, refused when a numeric quadrature contradicts it.

    SymPy's route through a definite integral follows the process's string-hash seed: on 1.14
    about one SymPy pool worker in three gives ∫₀¹ (9ˣ - 3ˣ) dx = -76/ln 3, not 2/ln 3. A
    contradicted closed form is rebuilt as F(b) - F(a) and kept only if that agrees.
    """
    low, high = sympify(low), sympify(high)
    value = integrate(integrand, (sym, low, high))
    numeric = _quadrature(integrand, sym, low, high)
    if numeric is None or _agrees(value, numeric) is not False:
        return value
    antiderivative = integrate(integrand, sym)
    if not antiderivative.has(Integral):
        rebuilt = limit(antiderivative, sym, high, "-") - limit(antiderivative, sym, low, "+")
        if _agrees(rebuilt, numeric):
            return rebuilt
    raise SolveServiceError("the integral's closed form disagrees with a numeric check")


def _quadrature(integrand: Any, sym: Any, low: Any, high: Any) -> complex | None:
    """mpmath's tanh-sinh value of the integral; None when it cannot judge.

    That is another symbol in the integrand or bounds, a point it cannot evaluate, or an error
    estimate too large to trust (an oscillating tail, a kink inside the interval).
    """
    import mpmath

    if integrand.free_symbols - {sym} or low.free_symbols or high.free_symbols:
        return None
    with sympy_decline() as declined:
        f = lambdify(sym, integrand, "mpmath")
        a, b = (lambdify((), bound, "mpmath")() for bound in (low, high))
        value, error = mpmath.quad(f, [a, b], error=True)
        numeric = complex(value)
    if declined or not cmath.isfinite(numeric):
        return None
    return numeric if error <= _QUADRATURE_TRUST * max(1.0, abs(numeric)) else None


def _agrees(value: Any, numeric: complex) -> bool | None:
    """Whether a finite closed form matches the quadrature; None when there is none to compare."""
    if value.has(Integral) or not (value.is_number and value.is_finite):
        return None
    with sympy_decline() as declined:
        closed = complex(value.evalf())
    if declined:
        return None
    return abs(closed - numeric) <= _QUADRATURE_AGREE * max(1.0, abs(numeric))


def integrate_definite(expr: str, variable: str, lower: str, upper: str) -> MathExprResult:
    """Definite integral of expr w.r.t. variable from `lower` to `upper`.

    Bounds are infinity-aware ("oo"/"inf"/"infty" → sympy.oo) via the same
    parser limits/series use. A divergent/improper integral may evaluate to
    oo/-oo/zoo; that is reported as the result rather than raising.
    """
    sym = Symbol(variable)
    parsed = parse_expression(expr, [variable])
    a = _parse_infinity_aware_point(lower)
    b = _parse_infinity_aware_point(upper)
    try:
        result = definite_integral(parsed, sym, a, b)
    except Exception as exc:
        raise SolveServiceError(f"Could not compute definite integral of: {expr}") from exc
    solved = not result.has(Integral)
    return MathExprResult(result=str(result), latex=format_verified_latex(result), solved=solved)


def integrate_double(
    expr: str,
    variable: str,
    lower: str,
    upper: str,
    variable2: str,
    lower2: str,
    upper2: str,
) -> MathExprResult:
    """Definite double integral over a named axis-aligned rectangle."""
    parsed = parse_expression(expr, [variable, variable2])
    a = _parse_infinity_aware_point(lower)
    b = _parse_infinity_aware_point(upper)
    c = _parse_infinity_aware_point(lower2)
    d = _parse_infinity_aware_point(upper2)
    try:
        result = integrate(
            parsed,
            (Symbol(variable), a, b),
            (Symbol(variable2), c, d),
        )
    except Exception as exc:
        raise SolveServiceError(f"Could not compute double integral of: {expr}") from exc
    solved = not result.has(Integral)
    return MathExprResult(result=str(result), latex=format_verified_latex(result), solved=solved)


def integrate_triple(
    expr: str,
    variable: str,
    lower: str,
    upper: str,
    variable2: str,
    lower2: str,
    upper2: str,
    variable3: str,
    lower3: str,
    upper3: str,
) -> MathExprResult:
    """Definite triple integral over a named axis-aligned box."""
    parsed = parse_expression(expr, [variable, variable2, variable3])
    a = _parse_infinity_aware_point(lower)
    b = _parse_infinity_aware_point(upper)
    c = _parse_infinity_aware_point(lower2)
    d = _parse_infinity_aware_point(upper2)
    e = _parse_infinity_aware_point(lower3)
    f = _parse_infinity_aware_point(upper3)
    try:
        result = integrate(
            parsed,
            (Symbol(variable), a, b),
            (Symbol(variable2), c, d),
            (Symbol(variable3), e, f),
        )
    except Exception as exc:
        raise SolveServiceError(f"Could not compute triple integral of: {expr}") from exc
    solved = not result.has(Integral)
    return MathExprResult(result=str(result), latex=format_verified_latex(result), solved=solved)


_INFINITY_WORDS = {"infinity", "inf", "oo", "infty"}


def _parse_infinity_aware_point(raw: str) -> Any:
    """Limit/series bounds routinely use "infinity"/"inf"/"oo" (with an
    optional leading "-") instead of a plain number — map those directly to
    sympy's oo/-oo rather than routing the bare word through
    parse_expression, which would reject it as an unrecognized symbol name.
    Anything else still goes through the same safety-checked expression
    parser as every other numeric input in this module."""
    s = raw.strip().lower()
    negative = s.startswith("-")
    core = s[1:].strip() if negative else s
    if core in _INFINITY_WORDS:
        return -oo if negative else oo
    return parse_expression(raw)


def _is_limit_value(value: Any) -> bool:
    """A real number or a signed infinity: a limit SymPy established.

    Accumulation bounds only bound the values near the point (``sin(1/x)`` at 0
    is ``<-1, 1>``), and prove nothing either way: ``sin(1/x)^2 + cos(1/x)^2``
    gets ``<0, 2>``, though it is 1. NaN, complex infinity inside an answer, an
    unevaluated ``Limit`` and a complex value (``sqrt(x)`` at -1 is ``i``) are
    no real limit either.
    """
    if value in (oo, -oo):
        return True
    return not value.has(AccumBounds, Limit, nan, zoo) and value.is_extended_real is not False


def compute_limit(expr: str, variable: str, point: str, direction: str = "+-") -> MathLimitResult:
    # School limits are over a real input unless another domain is stated.
    # Real assumptions are required for piecewise/absolute-value behavior:
    # without them SymPy cannot decide lim |x|/x at 0.
    sym = Symbol(variable, real=True)
    parsed = parse_expression(expr, [variable], real=True)
    point_val = _parse_infinity_aware_point(point)
    try:
        result = limit(parsed, sym, point_val, dir=direction)
    except ValueError as exc:
        if direction != "+-":
            raise SolveServiceError(f"Could not compute limit of: {expr}") from exc
        try:
            left = limit(parsed, sym, point_val, dir="-")
            right = limit(parsed, sym, point_val, dir="+")
        except Exception as side_exc:
            raise SolveServiceError(f"Could not compute limit of: {expr}") from side_exc
        if not (_is_limit_value(left) and _is_limit_value(right)):
            # sin(1/x)/x at 0: neither side has a limit, so they cannot disagree.
            raise SolveServiceError(f"Could not compute limit of: {expr}") from exc
        result = left if simplify(left - right) == 0 else zoo
    except Exception as exc:
        raise SolveServiceError(f"Could not compute limit of: {expr}") from exc
    # A limit can legitimately evaluate to oo/-oo (diverges) or zoo (the
    # two-sided limit doesn't exist because the two sides disagree). Keep
    # the symbolic result so presentation can distinguish these statuses.
    # zoo says that only for a two-sided limit at a point: at infinity there
    # are no two sides, and (-2)^n is unbounded both ways.
    if result == zoo:
        if direction != "+-" or point_val.is_finite is not True:
            raise SolveServiceError(f"Could not compute limit of: {expr}")
    elif not _is_limit_value(result):
        raise SolveServiceError(f"Could not compute limit of: {expr}")
    return MathLimitResult(
        result=str(result), latex=latex(result), is_infinite=bool(result.is_infinite)
    )


def evaluate_series_sum(expr: str, variable: str, start: str, end: str) -> MathSeriesResult:
    sym = Symbol(variable)
    parsed = parse_expression(expr, [variable])
    start_val = _parse_infinity_aware_point(start)
    end_val = _parse_infinity_aware_point(end)
    series = Sum(parsed, (sym, start_val, end_val))
    try:
        is_convergent = series.is_convergent()
    except NotImplementedError:
        is_convergent = None
    try:
        is_absolutely_convergent = series.is_absolutely_convergent()
    except NotImplementedError:
        is_absolutely_convergent = None
    try:
        result = series.doit()
    except Exception as exc:
        raise SolveServiceError(f"Could not evaluate series: {expr}") from exc
    if result.has(AccumBounds, nan, zoo):
        # 1/n from n = 0: a term is undefined, and the sum is complex infinity.
        raise SolveServiceError(f"Could not evaluate series: {expr}")
    return MathSeriesResult(
        result=str(result),
        latex=latex(result),
        is_infinite=bool(result.is_infinite),
        solved=not result.has(Sum),
        is_convergent=None if is_convergent is None else bool(is_convergent),
        is_absolutely_convergent=(
            None if is_absolutely_convergent is None else bool(is_absolutely_convergent)
        ),
    )
