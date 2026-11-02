"""Whole-request and metamorphic guarantees at the math extraction seam."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent


@pytest.mark.parametrize(
    "question, answer",
    [
        ("sin(30°) + cos(60°)", "1"),
        ("2sin(30°)+cos(60°)", r"\frac{3}{2}"),
        ("sin(pi/6)+cos(pi/3)", "1"),
        ("sin(π/6) + cos(π/3)", "1"),
        ("Evaluate sin(30°) + cos(60°)", "1"),
    ],
)
def test_complete_trig_expression_consumes_every_call(question: str, answer: str) -> None:
    intent = extract_math_intent(question)
    assert intent is not None and intent.school_op == "expression"
    block = _build_verified_block(intent, Settings())
    assert block is not None and block.canonical_answer == answer


@pytest.mark.parametrize(
    "question",
    [
        "sin(30°) + cos(60°) and calculate 99",
        "Simplify 8/12 and solve 2x=4",
        "Graph y=x^2 and solve 3x=9",
        "Find median of 1,2,3 and z-score for x=88, mean 72, standard deviation 8",
        "Solve 2x=4; also x must be positive",
        "Solve x²=4 for x > 0",
        "Solve x^2=4 where x is positive",
        "Solve x^2=4 where x is non-negative",
        "Solve x^2=4 where x is non-positive",
        "Solve x^2=x where x is nonzero",
        "Solve x^2=x where x is non-zero",
        "Solve x^2=x where x is not zero",
        "Solve x^2=x with x nonzero",
        "Solve x^2=x, x > 0",
        "Solve x^2=x subject to x is not zero",
        "Solve x^2=x where x is odd",
        "Solve x^2=x where x is even",
        "Solve x^2=x where x is prime",
        "Solve x^2=x given x = 1",
        "Solve x^2=4 for x != -2",
        "Solve x^2=4 for x>=0",
        "Solve x^2=4 where x!= -2",
        "Solve x^2=4 for x ≠ -2",
        "Solve x^2=4 where x is not equal to -2",
        "Solve x^2=2 where x is an integer",
        "Solve x^2=2 where x is integer",
        "Solve x+y=1, x-y=0 over the integers",
        "Solve x^2 < 4 over the integers",
        "Simplify sqrt(x^2) where x is positive",
        "Differentiate x² and evaluate it at x=3",
        "Find the derivative and second derivative of x³",
        "Graph x² and tell me its roots",
        "Find the area, perimeter and diagonal of a 3×4 rectangle",
        "Find sin(30°), cos(60°), and tan(45°)",
        "Solve x²=4 in the integers",
        "Solve x^2=2, x∈ℤ",
        r"Solve x^2=2, x\in\mathbb{Z}",
        "Solve x^2=4 for x in [0,∞)",
        "Solve x^2=4 over ℤ",
        "Solve x^2=4 for positive x",
        "Solve x^2=4 assuming nonnegative x",
        "Solve x^2=2 for integer x",
        "Solve x^2=4 given that x is positive",
        "Solve x^2=4 provided that x is nonnegative",
        "Solve x^2=4 if x is positive",
        "Solve x^2=4, positive solutions only",
        "Solve x^2=4. Give only the negative root",
        "Solve x^2=4; solutions that are nonnegative",
        "Solve x^2=4 such that x>0",
        "Solve x^2=4 under the condition that x is negative",
        "Assume x is positive. Solve x^2=4",
        "Let x be positive. Solve x^2=4",
        "Suppose that x is negative. Solve x^2=4",
        "Take x to be nonnegative. Solve x^2=4",
        "Solve x^2=4 where x has to be positive",
        "Solve x^2=4 where x should be positive",
        "Solve x^2=4 where x needs to be positive",
        "Solve x^2=4 where x can only be positive",
        "Solve x^2=4 where x must always be positive",
        "Solve x^2=4 where x has to be greater than 0",
        "Solve x^2=4 where x lies between 0 and 5",
        "Solve x^2=4 where x has to be real and positive",
        "Solve x^2=4 where x cannot be real",
        "Solve x^2=4 where x must not be real",
        "Solve x^2=4 where x should never be real",
        "Solve x^2=4; the solutions must be positive",
        "Solve x^2=4; the roots have to be positive",
        "Solve x^2=4; the roots must be strictly positive",
        "Solve x^2=4; the solutions are not negative",
    ],
)
def test_unsupported_multipart_request_fails_closed(question: str) -> None:
    assert extract_math_intent(question) is None


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Find the mean and standard deviation of 1,2,3,4", r"\bar{x} = 2.5,\quad \sigma = 1.118"),
        ("mean and standard deviation of 2,4,4,4,5,5,7,9", r"\bar{x} = 5,\quad \sigma = 2"),
        ("Find the mean and median of 1,2,3,4", r"\bar{x} = 2.5,\quad \text{median} = 2.5"),
        ("Find the median and mode of 1,1,2,3", r"\text{median} = 1.5,\quad \text{mode} = 1"),
        (
            "Find the mean and sample standard deviation of 2,4,4,4,5,5,7,9",
            r"\bar{x} = 5,\quad s = 2.1381",
        ),
    ],
)
def test_several_summary_statistics_are_answered_together(question: str, answer: str) -> None:
    """A second statistic is answered beside the first, never dropped."""
    intent = extract_math_intent(question)
    assert intent is not None and intent.kind == "statistics"
    block = _build_verified_block(intent, Settings())
    assert block is not None and block.canonical_answer == answer
    assert maybe_direct_math_reply(block, question) is None


def test_supported_geometry_multipart_retains_both_requested_values() -> None:
    question = "Find the area and perimeter of a rectangle 3 by 4"
    intent = extract_math_intent(question)
    assert intent is not None
    assert intent.wants_area is True
    assert intent.wants_perimeter is True
    block = _build_verified_block(intent, Settings())
    assert block is not None and block.canonical_fence is not None
    assert block.canonical_fence["area"] == 12
    assert block.canonical_fence["perimeter"] == 14
    assert maybe_direct_math_reply(block, question) is None


@pytest.mark.parametrize(
    "question",
    [
        "Solve x+y=3, y=1",
        "Solve x+y=3 given y=1",
        "Solve x+y=3 where y=1",
        "Let y=1. Solve x+y=3",
    ],
)
def test_system_equation_is_not_mistaken_for_a_domain_constraint(question: str) -> None:
    intent = extract_math_intent(question)
    assert intent is not None
    assert intent.kind == "system"
    assert set(intent.system_equations or []) == {("x+y", "3"), ("y", "1")}


def test_system_with_an_extra_inequality_constraint_fails_closed() -> None:
    assert extract_math_intent("Solve x+y=3, y=1, x>0") is None


@pytest.mark.parametrize(
    "question",
    [
        "Solve x^2=4, x∈ℝ",
        r"Solve x^2=4, x\in\mathbb{R}",
        r"Solve x^2=4, x in \mathbb{R}",
        "Solve x^2=4 where x is real",
        "Solve x^2=4 assuming x is a real number",
        "Let x be real. Solve x^2=4",
        "Solve x^2=4 where x has to be real",
        "Solve x^2=4 where x can be any real number",
    ],
)
def test_explicit_real_domain_is_already_represented(question: str) -> None:
    intent = extract_math_intent(question)
    assert intent is not None
    assert intent.kind == "equation"


def test_real_domain_plus_an_extra_sign_constraint_still_fails_closed() -> None:
    assert extract_math_intent("Solve x^2=4 where x is real and positive") is None


def test_z_score_input_labels_are_not_mistaken_for_requested_statistics() -> None:
    question = (
        "Find the z-score for x=88 where the population mean is 72 and standard deviation is 8"
    )
    intent = extract_math_intent(question)
    assert intent is not None
    assert intent.school_op == "z_score"
    block = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None and block.direct_reply is not None
    assert r"\frac{88 - 72}{8} = 2" in block.direct_reply


@pytest.mark.parametrize(
    "question",
    [
        "Graph the square root of x",
        "Find the graph of the square root of x",
    ],
)
def test_named_radical_in_graph_expression_is_not_a_roots_request(question: str) -> None:
    intent = extract_math_intent(question)
    assert intent is not None
    assert intent.kind == "graph"


def test_named_rectangle_multipart_is_verified_and_rendered_atomically() -> None:
    question = "A rectangle is 8 cm long and 3 cm wide. Find both its area and perimeter."
    intent = extract_math_intent(question)
    assert intent is not None
    assert intent.wants_area is True and intent.wants_perimeter is True
    block = _build_verified_block(intent, Settings())
    assert block is not None
    assert block.canonical_answer == (r"A = 24\ \mathrm{cm}^{2},\quad P = 22\ \mathrm{cm}")
    reply = maybe_direct_math_reply(block, question)
    assert reply is not None
    assert "A = 8 \\times 3 = 24" in reply
    assert "P = 2(8+3) = 22" in reply


@pytest.mark.parametrize(
    "question",
    [
        "solve 2x+3=11",
        "solve: 2x + 3 = 11",
        "please solve 2x+3=11",
        "show me how to solve 2x+3=11",
        "Solve 2x + 3 = 11.",
    ],
)
def test_equivalent_wrappers_preserve_the_same_equation(question: str) -> None:
    intent = extract_math_intent(question)
    assert intent is not None and intent.kind == "equation"
    assert (intent.lhs or "").replace(" ", "") == "2x+3"
    assert intent.rhs == "11"


def test_zero_exponent_law_is_part_of_verified_working() -> None:
    question = "Show steps: 3x^2 + x^0 = 3"
    intent = extract_math_intent(question)
    assert intent is not None
    block = _build_verified_block(intent, Settings())
    assert block is not None
    assert block.key_steps[0].label == "Use the zero-exponent law"
    assert block.key_steps[0].formula == "x^0 = 1"
    assert block.key_steps[0].conditions == r"x \ne 0"
    reply = maybe_direct_math_reply(block, question)
    assert reply is not None and "zero-exponent law" in reply.lower()
