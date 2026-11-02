"""Strict declines in math root and tools/ (ES-39 part 3): a parse that is no expression.

``parse_expression`` hands back what the text names: a point ``(1, 2)`` as a tuple, ``True``,
``x == 1`` as False, ``limit`` as SymPy's function. These callers then subtracted it or read its
``free_symbols``, and the silent ``except`` took the ``TypeError`` for a decline. Each now
declines on purpose; under strict declines the old code raised.
"""

from __future__ import annotations

import json

import pytest
from sympy import Symbol

from app.core.config import Settings
from app.modules.math.schemas import MathIntent
from app.modules.math.solve import SolveServiceError
from app.modules.math.tool_check import _parse, tool_call_matches_user_text
from app.modules.math.tools.block.algebra import _rational_interval_is_clearer
from app.modules.math.tools.block.integrals import (
    _fundamental_theorem_working,
    _is_log_over_x_integral,
)
from app.modules.math.tools.block.limits import _limit_working
from app.modules.math.tools.school import apply_calculus_extension
from app.modules.math.tools.school.geometry_measures.coordinates import _circle_centre_radius


@pytest.fixture(autouse=True)
def _strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECALL_STRICT_DECLINES", "1")


@pytest.mark.parametrize("text", ["(1, 2)", "1, 2", "True", "x == 1", "limit", "N"])
def test_tool_check_parse_keeps_only_expressions(text: str) -> None:
    assert _parse(text) is None


def test_tool_check_parse_still_reads_an_expression() -> None:
    assert _parse("2x") == 2 * Symbol("x")


def test_tool_check_a_point_before_the_expression_keeps_the_match() -> None:
    """``(1, 2)`` parsed to a tuple; ``2x - (1, 2)`` raised past every check, so no match."""
    args = json.dumps({"action": "simplify", "expr": "2*x"})
    assert tool_call_matches_user_text(args, ["plot (1, 2) and simplify 2x"])
    assert not tool_call_matches_user_text(args, ["plot (1, 2) and simplify 3x"])


def test_limit_working_declines_a_point_written_as_the_expression() -> None:
    intent = MathIntent(kind="limit", expr="(1, 2)", limit_point="0", operation="limit")
    assert _limit_working(intent, "L") is None


def test_limit_working_declines_a_bare_function_name() -> None:
    intent = MathIntent(kind="limit", expr="limit", limit_point="0", operation="limit")
    assert _limit_working(intent, "L") is None


@pytest.mark.parametrize("lower", ["(1, 2)", "True", "limit"])
def test_fundamental_theorem_working_declines_a_bound_that_is_no_number(lower: str) -> None:
    intent = MathIntent(
        kind="calculus",
        operation="integrate",
        expr="x^2",
        integral_lower=lower,
        integral_upper="3",
    )
    assert _fundamental_theorem_working(intent, Symbol("x", real=True) ** 2, "I") is None


@pytest.mark.parametrize("expr", ["(1, 2)", "True", "limit"])
def test_log_over_x_integral_is_false_for_a_non_expression(expr: str) -> None:
    assert _is_log_over_x_integral(expr, "x") is False


@pytest.mark.parametrize("lhs", ["(1, 2)", "Interval(0, 1)", "limit"])
def test_rational_interval_is_not_clearer_for_a_non_expression(lhs: str) -> None:
    intent = MathIntent(kind="inequality", lhs=lhs, rhs="0", comparator=">", variable="x")
    assert _rational_interval_is_clearer(intent) is False


def test_implicit_derivative_refuses_a_side_that_is_a_truth_value() -> None:
    """``x == 1`` is no expression: it is refused like any text that does not parse."""
    intent = MathIntent(
        kind="calculus", school_op="implicit", lhs="x == 1", rhs="25", operation="differentiate"
    )
    with pytest.raises(SolveServiceError, match="Could not parse expression"):
        apply_calculus_extension(intent, Settings(math_tools_enabled=True), [])


@pytest.mark.parametrize("expr", ["y = (1, 2)", "y = limit"])
def test_circle_centre_radius_declines_a_side_that_is_no_expression(expr: str) -> None:
    intent = MathIntent(
        kind="arithmetic",
        school_op="geometry_measure:circle_centre_radius",
        expr=expr,
        operation="solve",
    )
    assert _circle_centre_radius(intent) is None
