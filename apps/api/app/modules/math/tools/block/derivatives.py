"""A derivative at a point: the derivative's formula, then the point put in."""

from __future__ import annotations

from dataclasses import replace

from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block.canonical import finish_with_answer
from app.services.solving import VerifiedMathBlock


def _derivative_at_point(
    intent: MathIntent, expr: str, point: str, lines: list[str]
) -> VerifiedMathBlock:
    out = math_solve.differentiate_at_point(expr, intent.variable, point)
    lines.extend(out.steps)
    answer = out.latex
    working = _derivative_at_point_working(expr, intent.variable, point, out.result)
    if working is None:
        working = f"At ${intent.variable} = {point}$: {out.steps[0]}"
    direct = f"{working}\n\n```answer\n{answer}\n```\n"
    return replace(
        finish_with_answer(lines, answer),
        direct_reply=direct,
        direct_requires_calculus_guard=True,
    )


def _derivative_at_point_working(expr: str, variable: str, point: str, value: str) -> str | None:
    """``dy/dx = 2x``, then ``dy/dx`` at ``x = 3`` with 3 put in: ``2(3)``.

    None when the derivative's formula does not give the checked value there
    (``|x|`` at 0); the difference-quotient reason stands in.
    """
    from sympy import Symbol, diff, latex, simplify, sympify

    from app.modules.math import solve as math_solve
    from app.modules.math.tools.school.function_value import _substituted_tex

    try:
        parsed = math_solve.parse_expression(expr, [variable])
        at = sympify(point)
        derivative = simplify(diff(parsed, Symbol(variable)))
        if derivative.free_symbols - {Symbol(variable)}:
            return None
        if simplify(derivative.subs(variable, at) - sympify(value)) != 0:
            return None
    except (math_solve.SolveServiceError, TypeError, ValueError, SyntaxError):
        return None
    d = rf"\frac{{dy}}{{d{variable}}}"
    return (
        f"${d} = {latex(derivative)}$  \n"
        rf"$\left.{d}\right|_{{{variable} = {latex(at)}}} = "
        f"{_substituted_tex(derivative, variable, at)}$"
    )


def _higher_derivative_at_point(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    """``d^2y/dx^2 = 12x^2``, then at ``x = 2``: ``12(2)^2``. The answer is that value.

    The difference-quotient check covers a first derivative only; read with
    it, "the second derivative of x^4 at x = 2" was answered with the first (32).
    """
    from sympy import Symbol, diff, latex, simplify, sympify

    from app.modules.math.solve.display import format_verified_latex
    from app.modules.math.tools.school.function_value import _substituted_tex

    order = intent.derivative_order
    variable = intent.variable
    try:
        parsed = math_solve.parse_expression(intent.expr or "", [variable])
        at = sympify(intent.evaluation_point)
    except (math_solve.SolveServiceError, TypeError, ValueError, SyntaxError):
        return None
    symbol = Symbol(variable)
    if isinstance(parsed, tuple) or parsed.free_symbols - {symbol}:
        return None
    derivative = simplify(diff(parsed, symbol, order))
    value = simplify(derivative.subs(symbol, at))
    if not (value.is_number and value.is_finite):
        return None
    answer = format_verified_latex(value)
    d = rf"\frac{{d^{{{order}}}y}}{{d{variable}^{{{order}}}}}"
    working = (
        f"${d} = {latex(derivative)}$  \n"
        rf"$\left.{d}\right|_{{{variable} = {latex(at)}}} = "
        f"{_substituted_tex(derivative, variable, at)}$"
    )
    lines.append(
        f"Derivative of order {order}: {latex(derivative)}; at {variable} = {at}: {answer}"
    )
    return replace(
        finish_with_answer(lines, answer),
        direct_reply=f"{working}\n\n```answer\n{answer}\n```\n",
        direct_requires_calculus_guard=True,
    )
