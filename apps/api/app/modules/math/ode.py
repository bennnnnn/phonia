"""Linear ODEs in y up to second order, with the separable family's verified trace."""

from __future__ import annotations

from typing import Any

from sympy import (
    Derivative,
    Eq,
    Function,
    Integral,
    Symbol,
    dsolve,
    exp,
    integrate,
    latex,
    simplify,
    solve,
)

from app.modules.math.schemas import MathExprResult
from app.modules.math.solve import SolveServiceError, declines, parse_expression

_ODE_PLACEHOLDERS = {"y''": "Dyy", "y'": "Dy"}


def _ode_side(side: str, variable: str):
    """Parse one side of an ODE with y'' / y' standing in as plain symbols.

    ``Derivative(y(x), x)`` is not something the free-form parser accepts, so
    the derivative marks become ordinary symbols first and are swapped for the
    real derivatives afterwards. Longest mark first, or ``y''`` would be eaten
    as two ``y'``.
    """
    text = side
    for mark, name in _ODE_PLACEHOLDERS.items():
        text = text.replace(mark, name)
    return parse_expression(text, [variable, "y", "Dy", "Dyy"])


def solve_ode(
    expr: str,
    variable: str = "x",
    *,
    initial_x: str | None = None,
    initial_y: str | None = None,
) -> MathExprResult:
    """Linear ODE in ``y``, up to second order, with terms on either side.

    Handles the bare forms (``dy/dx = 2y``, ``y' = 2y``) and the general linear
    ones (``y'' + y = 0``, ``y'' + 3y' + 2y = 0``). Before this took the general
    form, ``y'' + y = 0`` fell through to the algebra extractor, which dropped
    the ``y''`` and returned a confident, verified ``y = 0``.
    """
    y = Function("y")
    ivar = Symbol(variable)
    text = expr.strip().replace("dy/dx", "y'").replace("d^2y/dx^2", "y''")
    eq_at = text.find("=")
    if eq_at == -1:
        raise SolveServiceError("could not solve ODE")
    lhs_raw = text[:eq_at].strip()
    rhs_raw = text[eq_at + 1 :].strip()
    if "'" not in lhs_raw and "'" not in rhs_raw:
        raise SolveServiceError("could not solve ODE")
    substitutions = {
        Symbol("Dyy"): Derivative(y(ivar), ivar, 2),
        Symbol("Dy"): Derivative(y(ivar), ivar),
        Symbol("y"): y(ivar),
    }
    x0 = None
    y0 = None
    try:
        eq = Eq(
            _ode_side(lhs_raw, variable).subs(substitutions),
            _ode_side(rhs_raw, variable).subs(substitutions),
        )
        ics = None
        if initial_x is not None and initial_y is not None:
            x0 = parse_expression(initial_x, [variable])
            y0 = parse_expression(initial_y, [variable])
            ics = {y(x0): y0}
        sol = dsolve(eq, y(ivar), ics=ics)
    except SolveServiceError:
        raise
    except Exception as exc:
        raise SolveServiceError("could not solve ODE") from exc
    tex = str(latex(sol))
    steps = _first_order_separable_ode_steps(eq, y, ivar, x0=x0, y0=y0)
    return MathExprResult(result=tex, latex=tex, solved=True, steps=steps)


def _first_order_separable_ode_steps(
    equation: Eq,
    dependent: Function,
    independent: Symbol,
    *,
    x0: Any | None,
    y0: Any | None,
) -> list[str]:
    """Verified trace for the family ``y' = f(x)y``.

    SymPy still owns the final ``dsolve`` result. This helper only emits a
    derivation when it can prove the ODE is separable into that family; other
    first- and second-order equations keep the verified answer without
    invented intermediate steps.
    """
    y_of_x = dependent(independent)
    derivative = Derivative(y_of_x, independent)
    with declines.sympy_decline() as declined:
        isolated = solve(equation, derivative)
        if len(isolated) != 1:
            return []
        rate = simplify(isolated[0] / y_of_x)
        if rate.has(y_of_x, derivative) or not rate.free_symbols <= {independent}:
            return []
        antiderivative = integrate(rate, independent)
        if antiderivative.has(Integral):
            return []
    if declined:
        return []

    var_tex = latex(independent)
    steps = [
        rf"\frac{{1}}{{y}}\,dy = {latex(rate)}\,d{var_tex}",
        rf"\ln\lvert y\rvert = {latex(antiderivative)} + C",
        rf"y = C e^{{{latex(antiderivative)}}},\quad C\in\mathbb{{R}}",
    ]
    if x0 is not None and y0 is not None:
        constant = simplify(y0 / exp(antiderivative.subs(independent, x0)))
        steps.append(rf"y({latex(x0)})={latex(y0)}\;\Longrightarrow\;C={latex(constant)}")
    return steps
