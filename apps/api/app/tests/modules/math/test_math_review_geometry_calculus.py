"""Regression examples from the math category review (no providers or database)."""

from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.modules.math.schemas import MathIntent, MathSeriesResult
from app.modules.math.tools import extract_math_intent
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply


def test_direct_indefinite_integral_keeps_constant_of_integration() -> None:
    intent = extract_math_intent("integrate x^2")
    assert intent is not None
    result = _build_verified_block(intent, Settings())
    assert result is not None
    assert result.canonical_answer == r"\frac{x^{3}}{3} + C"
    reply = maybe_direct_math_reply(result, "integrate x^2")
    assert reply is not None and "+ C" in reply


@pytest.mark.parametrize(
    "question, answer",
    [
        ("perimeter of square side 3", "12"),
        ("area of square side 3", "9"),
        ("perimeter of triangle with sides 3, 4, 5", "12"),
        ("area of triangle with sides 3, 4, 5", "6"),
        ("perimeter of right triangle legs 3 and 4", "12"),
        ("perimeter of parallelogram base 6 height 3 side 4", "20"),
        ("area of parallelogram base 6 height 3 side 4", "18"),
        ("perimeter of rectangle 3 x 4", "14"),
    ],
)
def test_geometry_answer_matches_requested_quantity(question: str, answer: str) -> None:
    intent = extract_math_intent(question)
    assert intent is not None
    result = _build_verified_block(intent, Settings())
    assert result is not None
    assert result.canonical_answer == answer


@pytest.mark.parametrize(
    "question",
    [
        "perimeter of triangle base 3 height 4",
        "draw a triangle base 3 height 4 and find its perimeter",
        "perimeter of trapezoid top 3 bottom 5 height 4",
        "perimeter of parallelogram base 6 height 3",
        "draw a parallelogram base 6 side 4 and find its perimeter",
        "draw a parallelogram side 4 and find its perimeter",
        "draw a square and find its perimeter",
        "draw a circle and calculate its area",
        "draw a circle sector radius 5 and calculate its area",
    ],
)
def test_insufficient_dimensions_cannot_verify_a_perimeter(question: str) -> None:
    assert extract_math_intent(question) is None


@pytest.mark.parametrize(
    "question, direction, answer",
    [
        ("limit of 1/x as x approaches 0 from the left", "-", r"-\infty"),
        ("limit of 1/x as x approaches 0 from the right", "+", r"\infty"),
        ("limit 1/x as x approaches 0 from below", "-", r"-\infty"),
        ("lim x->0- 1/x", "-", r"-\infty"),
        (r"\lim_{x\to 0^-} 1/x", "-", r"-\infty"),
        (r"\lim_{x\to 0^{+}} 1/x", "+", r"\infty"),
        ("limit of sin(x)/x as x approaches 0", "+-", "1"),
        ("lim x->0 - x", "+-", "0"),
    ],
)
def test_limit_preserves_requested_direction(question: str, direction: str, answer: str) -> None:
    intent = extract_math_intent(question)
    assert isinstance(intent, MathIntent)
    assert intent.limit_direction == direction
    result = _build_verified_block(intent, Settings())
    assert result is not None
    assert result.canonical_answer == answer


def test_limit_does_not_ignore_unsupported_point_tail() -> None:
    assert extract_math_intent("limit of x^2 as x approaches 1/2") is None


def test_disagreeing_two_sided_limit_is_not_positive_infinity() -> None:
    intent = extract_math_intent("limit of 1/x as x approaches 0")
    assert intent is not None
    result = _build_verified_block(intent, Settings())
    assert result is not None
    assert result.canonical_answer is None
    assert "does not exist" in result.text


def test_oscillating_divergent_series_is_not_an_unevaluated_answer() -> None:
    intent = extract_math_intent("sum (-1)^n from n=0 to infinity")
    assert intent is not None
    result = _build_verified_block(intent, Settings())
    assert result is not None
    assert result.canonical_answer is None
    assert "diverges" in result.text


def test_unsolved_series_does_not_get_a_canonical_answer() -> None:
    intent = extract_math_intent("sum 1/n^2 from n=1 to infinity")
    assert intent is not None
    with patch(
        "app.modules.math.solve.evaluate_series_sum",
        return_value=MathSeriesResult(
            result="Sum(...)", latex="unevaluated", is_infinite=False, solved=False
        ),
    ):
        result = _build_verified_block(intent, Settings())
    assert result is not None
    assert result.canonical_answer is None
    assert "not evaluated" in result.text
