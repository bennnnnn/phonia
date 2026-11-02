"""Numeric root finding: Newton's method, every iteration kept for the worked steps."""

from __future__ import annotations

from sympy import Symbol, diff, latex
from sympy.utilities.lambdify import lambdify

from app.modules.math.schemas import (
    NewtonIterationStep,
    NewtonMethodInput,
    NewtonMethodResult,
)
from app.modules.math.solve.display import format_verified_latex
from app.modules.math.solve.parse import SolveServiceError, parse_expression


def newton_method(data: NewtonMethodInput) -> NewtonMethodResult:
    """Manual Newton iteration (not mpmath.findroot) so every step is
    inspectable and can be shown as verified "worked steps," mirroring
    _worked_isolation_steps's role for algebraic solves — the model copies
    the iteration history verbatim instead of inventing its own numbers."""
    sym = Symbol(data.variable)
    parsed = parse_expression(data.expr, [data.variable])
    derivative = diff(parsed, sym)

    f = lambdify(sym, parsed, modules=["math"])
    fprime = lambdify(sym, derivative, modules=["math"])

    x_n = float(data.initial_guess)
    iterations: list[NewtonIterationStep] = []
    converged = False
    for i in range(data.max_iterations):
        try:
            fx = float(f(x_n))
        except Exception as exc:
            raise SolveServiceError(f"Could not evaluate function at x={x_n}") from exc
        iterations.append(NewtonIterationStep(n=i, x_n=round(x_n, 10), f_x_n=round(fx, 10)))
        if abs(fx) < data.tolerance:
            converged = True
            break
        try:
            fpx = float(fprime(x_n))
        except Exception as exc:
            raise SolveServiceError(f"Could not evaluate derivative at x={x_n}") from exc
        if fpx == 0:
            # Derivative vanished — Newton's method can't continue from here.
            break
        x_n = x_n - fx / fpx

    indexed = Symbol(f"{data.variable}_n")
    indexed_latex = latex(indexed)
    recurrence = (
        rf"{data.variable}_{{n+1}} = {indexed_latex} - "
        rf"\frac{{{format_verified_latex(parsed.subs(sym, indexed))}}}"
        rf"{{{format_verified_latex(derivative.subs(sym, indexed))}}}"
    )
    return NewtonMethodResult(
        function_latex=format_verified_latex(parsed),
        derivative_latex=format_verified_latex(derivative),
        recurrence_latex=recurrence,
        iterations=iterations,
        converged=converged,
        root=round(x_n, 10) if converged else None,
        iterations_used=len(iterations),
    )
