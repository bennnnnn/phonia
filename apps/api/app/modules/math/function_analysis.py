"""Verified single-variable function analysis backed by SymPy.

These helpers intentionally cover closed homework operations that SymPy can
verify deterministically. Domain restrictions supplied in prose are not
silently discarded; callers only use the default real-domain forms here.
"""

from __future__ import annotations

from typing import Any

from sympy import Complement, Eq, FiniteSet, Intersection, S, Symbol, latex, simplify, solveset
from sympy.calculus.util import continuous_domain, function_range

from app.modules.math.solve import SolveServiceError, parse_expression


def _real_expression(expr: str, variable: str):
    if not (expr or "").strip():
        raise SolveServiceError("function expression is required")
    try:
        parsed = parse_expression(expr, [variable], real=True)
    except SolveServiceError:
        raise
    except Exception as exc:
        raise SolveServiceError("could not parse function expression") from exc
    extra = {str(symbol) for symbol in parsed.free_symbols if str(symbol) != variable}
    if extra:
        raise SolveServiceError("function analysis supports one variable at a time")
    return parsed


def real_domain(expr: str, variable: str = "x") -> str:
    """Return the maximal real domain as verified LaTeX."""
    parsed = _real_expression(expr, variable)
    sym = Symbol(variable, real=True)
    try:
        result = continuous_domain(parsed, sym, S.Reals)
    except Exception as exc:
        raise SolveServiceError("could not determine the real domain") from exc
    return str(latex(result))


def real_range(expr: str, variable: str = "x") -> str:
    """Return the real range over the maximal real domain as verified LaTeX."""
    parsed = _real_expression(expr, variable)
    sym = Symbol(variable, real=True)
    try:
        domain = continuous_domain(parsed, sym, S.Reals)
        result = function_range(parsed, sym, domain)
    except Exception as exc:
        raise SolveServiceError("could not determine the real range") from exc
    return str(latex(result))


def _candidate_set(solutions: Any) -> Any:
    """The candidates under the real-domain conditions SymPy wraps them in.

    ``e^x = t`` solves to ``Intersection({log(t)}, Reals)`` and ``(2x+1)/(x-3) = t``
    to ``Complement(Intersection({(3t+1)/(t-2)}, Reals), {3})``: one inverse, with
    the values it can take. ``x^2 = t`` keeps two candidates and is still refused.
    """
    current = solutions
    while isinstance(current, (Intersection, Complement)):
        if isinstance(current, Complement):
            current = current.args[0]
            continue
        finite = [arg for arg in current.args if isinstance(arg, FiniteSet)]
        if len(finite) != 1 or any(
            arg is not S.Reals and not isinstance(arg, FiniteSet) for arg in current.args
        ):
            return current
        current = finite[0]
    return current


def inverse_function(expr: str, variable: str = "x") -> str:
    """Return a single-valued real inverse, refusing ambiguous inverse relations.

    For functions such as x^2 on the full real domain there are multiple real
    inverse branches. We deliberately refuse to choose one without a user-given
    domain restriction instead of certifying an arbitrary branch.
    """
    parsed = _real_expression(expr, variable)
    sym = Symbol(variable, real=True)
    target = Symbol("_inverse_target", real=True)
    try:
        solutions = _candidate_set(solveset(Eq(parsed, target), sym, domain=S.Reals))
    except Exception as exc:
        raise SolveServiceError("could not determine an inverse function") from exc
    if not isinstance(solutions, FiniteSet) or len(solutions) != 1:
        raise SolveServiceError(
            "inverse is not single-valued on the full real domain; specify a restricted domain"
        )
    inverse = next(iter(solutions))
    # Verify the candidate really composes back to the target before exposing it.
    try:
        if simplify(parsed.subs(sym, inverse) - target) != 0:
            raise SolveServiceError("could not verify the inverse function")
    except SolveServiceError:
        raise
    except Exception as exc:
        raise SolveServiceError("could not verify the inverse function") from exc
    display = simplify(inverse.subs(target, sym))
    return str(latex(display))


def compose_functions(outer_expr: str, inner_expr: str, variable: str = "x") -> str:
    """Return f(g(x)) for two explicit one-variable expressions."""
    outer = _real_expression(outer_expr, variable)
    inner = _real_expression(inner_expr, variable)
    sym = Symbol(variable, real=True)
    try:
        result = simplify(outer.subs(sym, inner))
    except Exception as exc:
        raise SolveServiceError("could not compose the functions") from exc
    return str(latex(result))


def symmetry(expr: str, variable: str = "x") -> str:
    """Classify a function as even, odd, or neither.

    f(-x) == f(x) is even, f(-x) == -f(x) is odd. "Neither" is a real answer
    here rather than a failure: most functions are neither, and saying so is
    what the question asks for.
    """
    parsed = _real_expression(expr, variable)
    sym = Symbol(variable, real=True)
    reflected = simplify(parsed.subs(sym, -sym))
    if simplify(reflected - parsed) == 0:
        return "even"
    if simplify(reflected + parsed) == 0:
        return "odd"
    return "neither"
