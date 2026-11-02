"""Complete real trigonometric solutions, including every periodic branch."""

from __future__ import annotations

from typing import Any

from sympy import (
    ConditionSet,
    FiniteSet,
    ImageSet,
    S,
    Symbol,
    Union,
    cos,
    cot,
    csc,
    latex,
    sec,
    sin,
    solveset,
    tan,
)

from app.modules.math.schemas import MathSolveResult
from app.services.solving import SolveServiceError


def _complete_solution_latex(solution: Any, variable: Any) -> str:
    """Use compact integer-parameter branches when solveset supplies them."""
    parts = solution.args if isinstance(solution, Union) else (solution,)
    branches: list[str] = []
    uses_integer = False
    parameter = Symbol("k" if str(variable) != "k" else "n", integer=True)
    for part in parts:
        if isinstance(part, ImageSet) and part.base_set == S.Integers:
            if len(part.lamda.variables) != 1:
                break
            value = part.lamda.expr.subs(part.lamda.variables[0], parameter)
            branches.append(f"{latex(variable)} = {latex(value)}")
            uses_integer = True
        elif isinstance(part, FiniteSet):
            branches.extend(
                f"{latex(variable)} = {latex(value)}" for value in sorted(part, key=str)
            )
        else:
            break
    else:
        if branches:
            answer = r" \text{ or } ".join(branches)
            if uses_integer:
                answer += f",\\quad {latex(parameter)} \\in \\mathbb{{Z}}"
            return answer
    # Keep any other fully solved set intact instead of truncating roots.
    return f"{latex(variable)} \\in {latex(solution)}"


def solve_real_trig_equation(lhs: Any, rhs: Any, variable: Any) -> MathSolveResult | None:
    """None means not trig; unsupported trig never falls back to partial roots."""
    atoms = lhs.atoms(sin, cos, tan, cot, sec, csc) | rhs.atoms(sin, cos, tan, cot, sec, csc)
    if not any(atom.has(variable) for atom in atoms):
        return None
    try:
        solution = solveset(lhs - rhs, variable, domain=S.Reals)
    except Exception as exc:
        raise SolveServiceError("Could not determine all real trigonometric solutions") from exc
    if solution.has(ConditionSet):
        raise SolveServiceError("Complete real trigonometric solution set is unresolved")
    steps = [f"Equation: {latex(lhs)} = {latex(rhs)}", "Solve over the real numbers."]
    if solution == S.EmptySet:
        steps.append("No real solutions.")
        return MathSolveResult(
            solutions_latex=[r"\text{no real solution}"],
            steps=steps,
            lhs_latex=latex(lhs),
            rhs_latex=latex(rhs),
        )
    if solution == S.Reals:
        answer = f"{latex(variable)} \\in \\mathbb{{R}}"
    else:
        answer = _complete_solution_latex(solution, variable)
    steps.append(f"All real solutions: {answer}")
    return MathSolveResult(
        solutions_latex=[answer],
        canonical_solutions_latex=[answer],
        steps=steps,
        lhs_latex=latex(lhs),
        rhs_latex=latex(rhs),
    )
