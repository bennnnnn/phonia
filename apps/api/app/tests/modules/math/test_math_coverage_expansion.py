from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.math import function_analysis
from app.modules.math import match as math_match
from app.modules.math import solve as math_solve
from app.modules.math.schemas import MatrixInput
from app.modules.math.solve import SolveServiceError
from app.modules.math.tools import _build_verified_block, extract_math_intent
from app.modules.math.tools.direct import maybe_direct_math_reply


def test_function_domain_and_range_are_verified() -> None:
    assert function_analysis.real_domain("x^2/(x-1)") == (
        r"\left(-\infty, 1\right) \cup \left(1, \infty\right)"
    )
    assert function_analysis.real_range("x^2") == r"\left[0, \infty\right)"


def test_inverse_function_refuses_multivalued_full_domain() -> None:
    assert function_analysis.inverse_function("2*x+3") == r"\frac{x}{2} - \frac{3}{2}"
    with pytest.raises(SolveServiceError, match="not single-valued"):
        function_analysis.inverse_function("x^2")


def test_function_composition_is_symbolic_and_exact() -> None:
    assert function_analysis.compose_functions("x^2", "x+1") == r"\left(x + 1\right)^{2}"


def test_function_analysis_routes_through_symbolic_gate() -> None:
    for prompt in (
        "domain of 1/(x-2)",
        "range of x^2",
        "inverse of 2*x+3",
        "find f(g(x)) where f(x)=x^2 and g(x)=x+1",
    ):
        assert math_match.needs_symbolic(prompt) is True, prompt

    # Ordinary English uses of these words must not become math turns.
    assert math_match.needs_symbolic("what is the domain name for this website?") is False
    assert math_match.needs_symbolic("what is the range of this electric car?") is False


def test_function_analysis_intents_do_not_steal_other_math_families() -> None:
    domain = extract_math_intent("find the domain of f(x)=1/(x-2)")
    assert domain is not None
    assert domain.kind == "calculus"
    assert domain.school_op == "function_domain"
    assert domain.expr == "1/(x-2)"

    composed = extract_math_intent("find f(g(x)) where f(x)=x^2 and g(x)=x+1")
    assert composed is not None
    assert composed.kind == "calculus"
    assert composed.school_op == "function_compose"
    assert composed.expr == "x^2"
    assert composed.expr2 == "x+1"

    matrix = extract_math_intent("inverse of [[2,0],[0,3]]")
    assert matrix is not None
    assert matrix.kind == "matrix"
    assert matrix.matrix_op == "inverse"

    stats = extract_math_intent("range of 1, 4, 9")
    assert stats is not None
    assert stats.kind == "statistics"
    assert stats.stats_op == "range"


def test_restricted_function_domain_is_not_silently_dropped() -> None:
    assert extract_math_intent("inverse of x^2 on x >= 0") is None
    assert extract_math_intent("range of x^2 for x >= 2") is None


def test_function_analysis_builds_canonical_verified_answer() -> None:
    intent = extract_math_intent("range of x^2")
    assert intent is not None
    block = _build_verified_block(intent, Settings())
    assert block is not None
    assert block.canonical_answer == r"\left[0, \infty\right)"


def test_bivariate_statistics_are_verified() -> None:
    cases = (
        ("correlation between [1,2,3] and [2,4,6]", "correlation", "1"),
        ("covariance of [1,2,3] and [2,4,6]", "covariance", "1.333333333"),
        ("sample covariance of [1,2,3] and [2,4,6]", "sample_covariance", "2"),
        ("linear regression for [1,2,3] and [2,4,6]", "linear_regression", "y = 2x"),
    )
    for prompt, operation, expected in cases:
        assert math_match.needs_symbolic(prompt) is True, prompt
        intent = extract_math_intent(prompt)
        assert intent is not None, prompt
        assert intent.kind == "statistics", prompt
        assert intent.stats_op == operation, prompt
        block = _build_verified_block(intent, Settings())
        assert block is not None, prompt
        assert block.canonical_answer == expected, prompt


def test_bivariate_statistics_require_two_explicit_equal_lists() -> None:
    assert math_match.needs_symbolic("correlation between sales and weather") is False
    query = "correlation between [1,2,3] and [2,4]"
    intent = extract_math_intent(query)
    assert intent is not None
    block = _build_verified_block(intent, Settings())
    assert block is not None and block.canonical_answer is None
    reply = maybe_direct_math_reply(block, query)
    assert reply is not None and "3 values versus 2" in reply

    with pytest.raises(SolveServiceError):
        math_solve.compute_bivariate_statistics("correlation", [1, 1], [2, 3])


def test_advanced_matrix_operations() -> None:
    rows: list[list[float]] = [[1.0, 2.0], [2.0, 4.0]]

    rank = math_solve.compute_matrix(MatrixInput(operation="rank", rows=rows))
    assert rank.result_latex == "1"

    nullspace = math_solve.compute_matrix(MatrixInput(operation="nullspace", rows=rows))
    assert nullspace.result_latex is not None
    assert "operatorname{span}" in nullspace.result_latex

    columnspace = math_solve.compute_matrix(MatrixInput(operation="columnspace", rows=rows))
    assert columnspace.result_latex is not None
    assert "operatorname{span}" in columnspace.result_latex

    rowspace = math_solve.compute_matrix(MatrixInput(operation="rowspace", rows=rows))
    assert rowspace.result_latex is not None
    assert "operatorname{span}" in rowspace.result_latex


def test_eigenvectors_and_diagonalization() -> None:
    rows: list[list[float]] = [[2.0, 0.0], [0.0, 3.0]]
    eigenvectors = math_solve.compute_matrix(MatrixInput(operation="eigenvectors", rows=rows))
    assert eigenvectors.result_latex is not None
    assert r"\lambda=2" in eigenvectors.result_latex
    assert r"\lambda=3" in eigenvectors.result_latex

    diagonalized = math_solve.compute_matrix(MatrixInput(operation="diagonalize", rows=rows))
    assert diagonalized.result_latex is not None
    assert "P=" in diagonalized.result_latex
    assert "D=" in diagonalized.result_latex


def test_matrix_extraction_recognizes_new_operations() -> None:
    for prompt, operation in (
        ("rank of [[1,2],[2,4]]", "rank"),
        ("nullspace of [[1,2],[2,4]]", "nullspace"),
        ("column space of [[1,2],[2,4]]", "columnspace"),
        ("row space of [[1,2],[2,4]]", "rowspace"),
        ("eigenvectors of [[2,0],[0,3]]", "eigenvectors"),
        ("diagonalize [[2,0],[0,3]]", "diagonalize"),
    ):
        intent = extract_math_intent(prompt)
        assert intent is not None, prompt
        assert intent.kind == "matrix", prompt
        assert intent.matrix_op == operation, prompt
        assert math_match.needs_symbolic(prompt) is True, prompt


def test_square_matrix_rules_remain_strict() -> None:
    with pytest.raises(ValidationError):
        MatrixInput(
            operation="eigenvectors",
            rows=[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        )

    with pytest.raises(SolveServiceError, match="not diagonalizable"):
        math_solve.compute_matrix(
            MatrixInput(operation="diagonalize", rows=[[1.0, 1.0], [0.0, 1.0]])
        )
