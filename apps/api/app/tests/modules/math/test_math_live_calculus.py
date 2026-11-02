"""Exact live-walkthrough cases: preserve requested form and complete solutions."""

from __future__ import annotations

import pytest
from sympy import S, Symbol, sin, solveset

from app.core.config import Settings
from app.modules.math import fence as math_fence
from app.modules.math import solve as math_solve
from app.modules.math.schemas import EquationInput
from app.modules.math.solve.trig_equations import _complete_solution_latex
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.extract import extract_math_intent
from app.services.solving import SolveServiceError, VerifiedMathBlock


def _verified(prompt: str) -> VerifiedMathBlock:
    intent = extract_math_intent(prompt)
    assert intent is not None
    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None
    return verified


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("Factor x^2-9", r"\left(x - 3\right) \left(x + 3\right)"),
        ("Factor x^2-2x+1", r"\left(x - 1\right)^{2}"),
        ("Expand (x-3)*(x+3)", r"x^{2} - 9"),
        ("Expand (x+1)^2", r"x^{2} + 2 x + 1"),
        ("Simplify complex (2+3i)+(4-5i)", "6 - 2 i"),
        ("SIMPLIFY COMPLEX (2+3i)+(4-5i)", "6 - 2 i"),
        ("evaluate complex (2+3j)+(4-5j)", "6 - 2 i"),
    ],
)
def test_requested_algebra_form_reaches_the_canonical_answer(prompt: str, expected: str) -> None:
    verified = _verified(prompt)
    assert verified.canonical_answer == expected
    final = math_fence.validate_math_fences("", verified=verified)
    assert f"```answer\nverified: true\n{expected}\n```" in final


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("Differentiate x^3", "3 x^{2}"),
        ("Find the second derivative of x^4", "12 x^{2}"),
        ("Find the third derivative of x^4", "24 x"),
        ("Find the partial derivative of x^2*y with respect to y", "x^{2}"),
        ("Integrate x^2", r"\frac{x^{3}}{3} + C"),
        ("Integrate x^2 from 0 to 1", r"\frac{1}{3}"),
        ("Find the limit of sin(x)/x as x approaches 0", "1"),
        ("Find the limit of 1/x as x approaches 0 from the left", r"-\infty"),
        ("Find the limit of 1/x as x approaches 0 from the right", r"\infty"),
        ("Sum n from n=1 to 10", "55"),
        ("Sum 1/n^2 from n=1 to infinity", r"\frac{\pi^{2}}{6}"),
        (
            "Find the Taylor series of exp(x) at 1 order 2",
            r"\frac{e \left(x - 1\right)^{2}}{2} + e \left(x - 1\right) + e",
        ),
        ("Find the Maclaurin series of sin(x) order 3", r"x - \frac{x^{3}}{6}"),
        ("Find the critical points of x^3-3x", "-1, 1"),
        ("Use Newton method to solve x^2-2=0 starting at 1", "1.41421"),
        ("Solve dy/dx=2x", r"y = x^{2} + C"),
    ],
)
def test_calculus_walkthrough_has_the_expected_verified_value(prompt: str, expected: str) -> None:
    assert _verified(prompt).canonical_answer == expected


@pytest.mark.parametrize(
    "prompt,message",
    [
        ("Find the limit of 1/x as x approaches 0", "two-sided limit does not exist"),
        ("Sum (-1)^n from n=0 to infinity", "diverges; it has no ordinary sum"),
    ],
)
def test_nonexistent_results_keep_verified_explanation_without_false_value(
    prompt: str, message: str
) -> None:
    verified = _verified(prompt)
    assert message in verified.text
    assert verified.canonical_answer is None


@pytest.mark.parametrize(
    "lhs,rhs,expected",
    [
        (
            "sin(x)",
            "1/2",
            r"x = 2 \pi k + \frac{\pi}{6} \text{ or } x = 2 \pi k + \frac{5 \pi}{6},\quad k \in \mathbb{Z}",
        ),
        (
            "cos(2x)",
            "0",
            r"x = \pi k + \frac{\pi}{4} \text{ or } x = \pi k + \frac{3 \pi}{4},\quad k \in \mathbb{Z}",
        ),
        ("tan(x)", "1", r"x = \pi k + \frac{\pi}{4},\quad k \in \mathbb{Z}"),
        ("sin(x)", "2", r"\text{no real solution}"),
        ("sin(x)**2+cos(x)**2", "1", r"x \in \mathbb{R}"),
    ],
)
def test_trig_equation_returns_all_real_branches(lhs: str, rhs: str, expected: str) -> None:
    result = math_solve.solve_equation(EquationInput(lhs=lhs, rhs=rhs))
    assert (result.canonical_solutions_latex or result.solutions_latex) == [expected]
    assert "Solve over the real numbers." in result.steps


def test_general_sine_solution_reaches_visible_canonical_answer() -> None:
    result = _verified("Solve sin(x)=1/2")
    assert result.canonical_answer is not None
    assert r"\frac{\pi}{6}" in result.canonical_answer
    assert r"\frac{5 \pi}{6}" in result.canonical_answer
    assert result.canonical_answer.count(r"2 \pi k") == 2
    assert r"k \in \mathbb{Z}" in result.canonical_answer


def test_trig_solution_parameter_does_not_reuse_the_solved_variable() -> None:
    k = Symbol("k")
    result = _complete_solution_latex(solveset(sin(k), k, domain=S.Reals), k)
    assert r"n \in \mathbb{Z}" in result
    assert "k =" in result


def test_unresolved_trig_equation_never_returns_only_principal_roots() -> None:
    with pytest.raises(SolveServiceError, match="unresolved"):
        math_solve.solve_equation(EquationInput(lhs="sin(x)", rhs="x/2"))


def test_nontrig_equation_retains_complex_roots() -> None:
    result = math_solve.solve_equation(EquationInput(lhs="x**2+1", rhs="0"))
    assert result.solutions_latex == ["x = -i", "x = i"]


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Solve x^2+1=0", r"x = \pm i"),
        ("Solve x^2-4x+5=0", r"x = 2 \pm i"),
        ("Solve x^2+4=0", r"x = \pm 2 i"),
        ("Solve x^2-4x+8=0", r"x = 2 \pm 2 i"),
    ],
)
def test_conjugate_roots_omit_only_unit_imaginary_coefficients(query: str, expected: str) -> None:
    assert _verified(query).canonical_answer == expected
