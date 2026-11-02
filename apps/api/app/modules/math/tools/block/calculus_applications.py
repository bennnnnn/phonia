"""Calculus applications: area between curves, arc length, volume of revolution."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block.canonical import finish_with_answer
from app.modules.math.tools.block.integrals import _bound_tex
from app.services.solving import VerifiedMathBlock
from app.services.workout import Workout, math_line, render_workout, text_line

_CALCULUS_APPLICATION_OPS = {
    "area_between_curves",
    "arc_length",
    "volume_revolution_x",
    "volume_revolution_y",
}


def _verified_calculus_application(
    intent: MathIntent, lines: list[str]
) -> VerifiedMathBlock | None:
    op = intent.school_op
    if op not in _CALCULUS_APPLICATION_OPS:
        return None
    expr, low, high = intent.expr, intent.integral_lower, intent.integral_upper
    if not expr or low is None or high is None:
        return None
    if op == "area_between_curves":
        if not intent.expr2:
            return None
        return _area_between_curves(intent, expr, intent.expr2, low, high, lines)
    if op == "arc_length":
        return _arc_length(intent, expr, low, high, lines)
    return _volume_of_revolution(intent, expr, low, high, "x" if op.endswith("_x") else "y", lines)


def _interval(low: str, var: str, high: str) -> str:
    return math_line(rf"{_bound_tex(low)} \le {var} \le {_bound_tex(high)}")


def _area_between_curves(
    intent: MathIntent, expr: str, expr2: str, low: str, high: str, lines: list[str]
) -> VerifiedMathBlock:
    from app.modules.math import calculus_applications as apps

    var = intent.variable
    answer = apps.area_between_curves(expr, expr2, low, high, var)
    lines.append(f"Area between the curves: {answer}")
    block = finish_with_answer(lines, answer)
    from sympy import Symbol, latex, simplify

    sym = Symbol(var, real=True)
    parsed = math_solve.parse_expression(expr, [var], real=True)
    second = math_solve.parse_expression(expr2, [var], real=True)
    difference = simplify(parsed - second)
    low_expr = math_solve.parse_expression(str(low), [], real=True)
    high_expr = math_solve.parse_expression(str(high), [], real=True)
    order = _curve_order(sym, parsed, second, difference, low_expr, high_expr)
    # "Area under y = f(x)" is the area between the curve and the x-axis.
    x_axis = second == 0
    meeting = intent.trial_outcome == "meeting points"
    given = (
        math_line(f"y = {latex(parsed)}"),
        math_line("y = 0", "the x-axis") if x_axis else math_line(f"y = {latex(second)}"),
        math_line(
            rf"{latex(low_expr)} \le {var} \le {latex(high_expr)}",
            "between where the curves meet",
        )
        if meeting
        else _interval(low, var, high),
    )
    working = _area_working(
        intent, sym, parsed, difference, order, (low_expr, high_expr), x_axis, answer
    )
    workout = Workout(
        given=given,
        find=(math_line("A", "area under the curve" if x_axis else "area between the curves"),),
        formula=(
            math_line(f"A = \\int_{{a}}^{{b}} y\\,d{var}", "Area under a curve")
            if x_axis
            else math_line(
                f"A = \\int_{{a}}^{{b}} \\left(y_{{\\text{{upper}}}} - "
                f"y_{{\\text{{lower}}}}\\right)\\,d{var}"
            ),
        ),
        substitution=working,
    )
    return replace(block, direct_reply=render_workout(workout, answer))


def _curve_order(
    sym: Any, parsed: Any, second: Any, difference: Any, low_expr: Any, high_expr: Any
) -> tuple[Any, Any, Any] | None:
    """(upper, lower, upper minus lower) when one curve stays on top over the interval."""
    from sympy import Eq, FiniteSet, Interval, S, simplify, solveset

    roots = solveset(Eq(difference, 0), sym, domain=Interval(low_expr, high_expr))
    interior_roots = []
    if isinstance(roots, FiniteSet):
        interior_roots = [root for root in roots if root != low_expr and root != high_expr]
    midpoint = simplify((low_expr + high_expr) / 2)
    sample = difference.subs(sym, midpoint)
    # No crossing comes back as EmptySet, which is not a FiniteSet.
    no_crossing = roots is S.EmptySet or (isinstance(roots, FiniteSet) and not interior_roots)
    single_order = no_crossing and sample.is_real is True
    if single_order and sample.is_nonnegative is True:
        return parsed, second, difference
    if single_order and sample.is_nonpositive is True:
        return second, parsed, -difference
    return None


def _area_working(
    intent: MathIntent,
    sym: Any,
    parsed: Any,
    difference: Any,
    order: tuple[Any, Any, Any] | None,
    bounds: tuple[Any, Any],
    x_axis: bool,
    answer: str,
) -> tuple[str, ...]:
    """Upper minus lower, integrated; or the absolute difference where the curves cross."""
    from sympy import integrate, latex

    low, high = _bound_tex(intent.integral_lower), _bound_tex(intent.integral_upper)
    var = intent.variable
    if order is None:
        return (
            math_line(
                f"A = \\int_{{{low}}}^{{{high}}} \\left|{latex(difference)}\\right|\\,d{var}",
                "the curve crosses the x-axis, so take its absolute value"
                if x_axis
                else "the curves cross, so take the absolute difference",
            ),
            math_line(f"= {answer}"),
        )
    upper, lower_curve, gap = order
    low_expr, high_expr = bounds
    antiderivative = integrate(gap, sym)
    side = "above" if upper is parsed else "below"
    return (
        text_line(
            f"${latex(upper)} \\ge {latex(lower_curve)}$ on $[{low}, {high}]$",
            f"the curve is {side} the x-axis" if x_axis else "upper curve first",
        ),
        math_line(
            f"A = \\int_{{{low}}}^{{{high}}} \\left({latex(gap)}\\right)\\,d{var}",
            "the height of the curve" if x_axis else "upper minus lower",
        ),
        math_line(f"= \\left[{latex(antiderivative)}\\right]_{{{low}}}^{{{high}}}", "integrate"),
        math_line(
            f"= {latex(antiderivative.subs(sym, high_expr))}"
            f" - \\left({latex(antiderivative.subs(sym, low_expr))}\\right)",
            "evaluate the endpoints",
        ),
        math_line(f"= {answer}"),
    )


def _arc_length(
    intent: MathIntent, expr: str, low: str, high: str, lines: list[str]
) -> VerifiedMathBlock:
    from app.modules.math import calculus_applications as apps

    var = intent.variable
    answer = apps.arc_length(expr, low, high, var)
    lines.append(f"Arc length: {answer}")
    block = finish_with_answer(lines, answer)
    from sympy import Symbol, diff, latex, sqrt

    sym = Symbol(var, real=True)
    parsed = math_solve.parse_expression(expr, [var], real=True)
    derivative = diff(parsed, sym)
    integrand = sqrt(1 + derivative**2)
    integral = rf"\int_{{{_bound_tex(low)}}}^{{{_bound_tex(high)}}}"
    workout = Workout(
        given=(math_line(f"y = {latex(parsed)}"), _interval(low, var, high)),
        find=(math_line("L", "arc length"),),
        formula=(
            math_line(f"L = \\int_{{a}}^{{b}} \\sqrt{{1 + (y')^{{2}}}}\\,d{var}", "Arc length"),
        ),
        substitution=(
            math_line(f"y' = {latex(derivative)}"),
            math_line(f"L = {integral} {latex(integrand)}\\,d{var}"),
            math_line(f"= {answer}"),
        ),
    )
    return replace(block, direct_reply=render_workout(workout, answer))


def _volume_of_revolution(
    intent: MathIntent, expr: str, low: str, high: str, axis: str, lines: list[str]
) -> VerifiedMathBlock:
    from app.modules.math import calculus_applications as apps

    var = intent.variable
    answer = apps.volume_of_revolution(expr, low, high, axis, var)
    lines.append(f"Volume about the {axis}-axis: {answer}")
    block = finish_with_answer(lines, answer)
    from sympy import Symbol, latex

    sym = Symbol(var, real=True)
    parsed = math_solve.parse_expression(expr, [var], real=True)
    low_expr = math_solve.parse_expression(str(low), [], real=True)
    high_expr = math_solve.parse_expression(str(high), [], real=True)
    method = _disk_working if axis == "x" else _shell_working
    formula, working = method(intent, sym, parsed, (low_expr, high_expr), answer)
    workout = Workout(
        given=(
            math_line(f"y = {latex(parsed)}"),
            _interval(low, var, high),
            text_line(f"about the {axis}-axis"),
        ),
        find=(math_line("V", "volume of revolution"),),
        formula=(formula,),
        substitution=working,
    )
    return replace(block, direct_reply=render_workout(workout, answer))


def _disk_working(
    intent: MathIntent, sym: Any, parsed: Any, bounds: tuple[Any, Any], answer: str
) -> tuple[str, tuple[str, ...]]:
    """About the x-axis: pi times the integral of y squared."""
    from sympy import integrate, latex, simplify

    low, high = _bound_tex(intent.integral_lower), _bound_tex(intent.integral_upper)
    var = intent.variable
    low_expr, high_expr = bounds
    cross_section = simplify(parsed**2)
    antiderivative = integrate(cross_section, sym)
    formula = math_line(f"V = \\pi\\int_{{a}}^{{b}} y^{{2}}\\,d{var}", "Disk method")
    return formula, (
        math_line(rf"V = \pi\int_{{{low}}}^{{{high}}}\left({latex(parsed)}\right)^2\,d{var}"),
        math_line(
            f"= \\pi\\int_{{{low}}}^{{{high}}} {latex(cross_section)}\\,d{var}",
            "simplify the cross-section",
        ),
        math_line(
            f"= \\pi\\left[{latex(antiderivative)}\\right]_{{{low}}}^{{{high}}}",
            "integrate",
        ),
        math_line(
            f"= \\pi\\left({latex(antiderivative.subs(sym, high_expr))}"
            f" - {latex(antiderivative.subs(sym, low_expr))}\\right)",
            "evaluate the endpoints",
        ),
        math_line(f"= {answer}"),
    )


def _shell_working(
    intent: MathIntent, sym: Any, parsed: Any, bounds: tuple[Any, Any], answer: str
) -> tuple[str, tuple[str, ...]]:
    """About the y-axis: 2 pi times the integral of x times y."""
    from sympy import integrate, latex, simplify

    low, high = _bound_tex(intent.integral_lower), _bound_tex(intent.integral_upper)
    var = intent.variable
    low_expr, high_expr = bounds
    shell_integrand = simplify(sym * parsed)
    antiderivative = integrate(shell_integrand, sym)
    formula = math_line(f"V = 2\\pi\\int_{{a}}^{{b}} {var}\\,y\\,d{var}", "Shell method")
    return formula, (
        math_line(
            rf"V = 2\pi\int_{{{low}}}^{{{high}}}{var}"
            rf"\left({latex(parsed)}\right)\,d{var}"
        ),
        math_line(f"= 2\\pi\\int_{{{low}}}^{{{high}}} {latex(shell_integrand)}\\,d{var}"),
        math_line(f"= 2\\pi\\left[{latex(antiderivative)}\\right]_{{{low}}}^{{{high}}}"),
        math_line(
            f"= 2\\pi\\left({latex(antiderivative.subs(sym, high_expr))}"
            f" - {latex(antiderivative.subs(sym, low_expr))}\\right)"
        ),
        math_line(f"= {answer}"),
    )
