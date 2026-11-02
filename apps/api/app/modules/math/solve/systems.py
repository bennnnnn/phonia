"""Systems of equations solved by SymPy, with a dependent system read as infinitely many
solutions and an inconsistent one as none."""

from __future__ import annotations

from typing import Any, Literal

from sympy import Eq, Symbol, latex, simplify, solve

from app.modules.math.schemas import MathSystemSolveResult, SystemOfEquationsInput
from app.modules.math.solve.equations import _reject_high_degree
from app.modules.math.solve.parse import SolveServiceError, parse_expression


def _classify_system_no_solution(pairs: list[tuple[Any, Any]]) -> Literal["none", "infinite"]:
    """Mirrors _classify_no_solution for the system case: solve() returning
    [] for every equation independently being a tautology (e.g. "x = x" AND
    "y = y") means infinitely many solutions; anything else defaults to
    "none", the same conservative default solve_equation uses. A genuinely
    underdetermined-but-non-trivial system (e.g. "x + y = 5" and
    "2x + 2y = 10") is NOT handled here — solve() already returns a
    parametrized solution for that case instead of an empty list, so it's
    caught by the free-symbol check in solve_system instead."""
    if all(simplify(lhs - rhs).is_zero for lhs, rhs in pairs):
        return "infinite"
    return "none"


def solve_system(data: SystemOfEquationsInput) -> MathSystemSolveResult:
    syms = [Symbol(v) for v in data.variables]
    equations = []
    parsed_pairs: list[tuple[Any, Any]] = []
    step_lines: list[str] = []
    for i, (lhs_raw, rhs_raw) in enumerate(data.equations, start=1):
        lhs = parse_expression(lhs_raw, data.variables)
        rhs = parse_expression(rhs_raw, data.variables)
        _reject_high_degree(lhs, rhs, data.variables)
        equations.append(Eq(lhs, rhs))
        parsed_pairs.append((lhs, rhs))
        step_lines.append(f"Equation {i}: {latex(lhs)} = {latex(rhs)}")

    try:
        raw_solutions = solve(equations, syms, dict=True)
    except Exception as exc:
        raise SolveServiceError("Could not solve system of equations") from exc

    solutions: list[dict[str, str]] = [
        {str(sym): latex(val) for sym, val in sol.items()} for sol in raw_solutions
    ]

    # solve() returns a non-empty (but parametrized) solution for a
    # dependent/underdetermined system rather than an empty list — a value
    # that still contains one of the OTHER declared unknowns as a free
    # symbol means the system has infinitely many solutions, not a single
    # finite one, even though `solutions` isn't empty.
    declared = set(syms)
    is_parametrized = any(
        any(sympy_val.free_symbols & declared for sympy_val in sol.values())
        for sol in raw_solutions
    )

    solution_kind: Literal["finite", "none", "infinite"] = "finite"
    if is_parametrized:
        solution_kind = "infinite"
        for sol in solutions:
            parts = ", ".join(f"{k} = {v}" for k, v in sol.items())
            step_lines.append(f"Infinitely many solutions (one free variable): {parts}")
    elif solutions:
        for sol in solutions:
            parts = ", ".join(f"{k} = {v}" for k, v in sol.items())
            step_lines.append(f"Solution: {parts}")
    else:
        solution_kind = _classify_system_no_solution(parsed_pairs)
        if solution_kind == "infinite":
            step_lines.append("Infinitely many solutions (every equation is an identity).")
        else:
            step_lines.append("No solution — the equations are inconsistent.")

    return MathSystemSolveResult(solutions=solutions, steps=step_lines, solution_kind=solution_kind)
