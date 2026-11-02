"""The conditions a solved equation states: ``x \\ne 2`` where the written equation divides
by zero (before SymPy cancels it), and ``a \\ne 0`` with the ``a = 0`` case where a symbolic
linear solve divides by a parameter."""

from __future__ import annotations

from typing import Any

from sympy import Eq, latex, simplify, solve, together

from app.modules.math.schemas import EquationInput
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.parse import SolveServiceError, parse_expression
from app.modules.math.solve.root_latex import expr_equal


def _original_domain_conditions(data: EquationInput, sym: Any) -> tuple[list[Any], list[str]]:
    """Restrictions from the original syntax, before SymPy cancellation."""
    excluded: list[Any] = []
    conditions: list[str] = []
    try:
        original_sides = (
            parse_expression(data.lhs, data.variables, real=True, evaluate=False),
            parse_expression(data.rhs, data.variables, real=True, evaluate=False),
        )
    except SolveServiceError:
        return excluded, conditions
    for side in original_sides:
        denominator = side.as_numer_denom()[1]
        parsed_sym = next(
            (item for item in getattr(denominator, "free_symbols", set()) if str(item) == str(sym)),
            None,
        )
        if parsed_sym is None:
            continue
        roots: list[Any] = []
        with sympy_decline():
            roots = solve(Eq(denominator, 0), parsed_sym)
        for value in roots:
            if any(expr_equal(value, seen) for seen in excluded):
                continue
            excluded.append(value)
            conditions.append(rf"{latex(sym)} \ne {latex(value)}")
    return excluded, conditions


def _parameter_solution_conditions(
    lhs: Any,
    rhs: Any,
    sym: Any,
    raw_solutions: list[dict[Any, Any]],
) -> tuple[list[str], list[str]]:
    """Conditions and zero-coefficient branches for symbolic linear solves."""
    conditions: list[str] = []
    cases: list[str] = []
    for solution in raw_solutions:
        value = solution.get(sym)
        if value is None:
            continue
        denominator = together(value).as_numer_denom()[1]
        denominator_symbols: set[Any] = set(getattr(denominator, "free_symbols", set()))
        if denominator != 1 and denominator_symbols and sym not in denominator_symbols:
            condition = rf"{latex(denominator)} \ne 0"
            if condition not in conditions:
                conditions.append(condition)
    with sympy_decline():
        polynomial = (lhs - rhs).as_poly(sym)
        if polynomial is None or polynomial.degree() != 1:
            return conditions, cases
        coefficient = simplify(polynomial.coeff_monomial(sym))
        constant = simplify(polynomial.coeff_monomial(1))
        parameters = sorted(coefficient.free_symbols - {sym}, key=str)
        if len(parameters) != 1:
            return conditions, cases
        parameter = parameters[0]
        zero_values = solve(Eq(coefficient, 0), parameter)
        if len(zero_values) != 1:
            return conditions, cases
        zero_value = zero_values[0]
        condition = rf"{latex(parameter)} \ne {latex(zero_value)}"
        # Prefer the readable parameter condition over an equivalent
        # denominator != 0 spelling.
        conditions = [item for item in conditions if item != rf"{latex(coefficient)} \ne 0"]
        if condition not in conditions:
            conditions.append(condition)
        collapsed = simplify(constant.subs(parameter, zero_value))
        if collapsed.is_zero:
            cases.append(
                rf"{latex(parameter)} = {latex(zero_value)}:\; {latex(sym)} \in \mathbb{{R}}"
            )
        elif not collapsed.free_symbols:
            cases.append(rf"{latex(parameter)} = {latex(zero_value)}:\; \text{{no solution}}")
    return conditions, cases
