"""Representative extraction-to-answer checks, without external IO."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math import tools as math_tools


def _settings() -> Settings:
    """Build deterministic test settings without loading a developer .env file."""
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "text,kind,answer",
    [
        ("7*8", "arithmetic", "56"),
        ("8-8*2", "arithmetic", "-8"),
        ("what is 9/9", "arithmetic", "1"),
        ("15% of 80", "arithmetic", "12"),
        ("increase 200 by 12%", "arithmetic", "224"),
        ("decrease 200 by 12%", "arithmetic", "176"),
        ("what percent of 50 is 12", "arithmetic", "24"),
        ("12 is what percent of 50", "arithmetic", "24"),
        ("simplify ratio 6:8", "arithmetic", "3:4"),
        ("split 120 in the ratio 2:3", "arithmetic", "48:72"),
        ("10th term of 3, 7, 11, 15", "arithmetic", "39"),
        ("sum of the first 10 terms of 3, 7, 11, 15", "arithmetic", "210"),
        ("sum of the first 20 even numbers", "arithmetic", "420"),
        ("sum of the first 20 odd numbers", "arithmetic", "400"),
        ("5th term of 2, 4, 8, 16", "arithmetic", "32"),
        ("compound interest on 1000 at 5% for 3 years", "arithmetic", "157.625"),
        ("simple interest on 1000 at 5% for 3 years", "arithmetic", "150"),
        ("compound amount on 1000 at 5% for 3 years", "arithmetic", "1157.625"),
        ("union of {1,2,3} and {3,4}", "arithmetic", "{1, 2, 3, 4}"),
        ("intersection of {1,2,3} and {3,4}", "arithmetic", "{3}"),
        ("difference of {1,2,3} and {3,4}", "arithmetic", "{1, 2}"),
        (
            "A can do a job in 6 hours and B in 3 hours. How long together?",
            "arithmetic",
            "2",
        ),
        ("mix 3 liters of 10% with 5 liters of 20%", "arithmetic", "16.25"),
        (
            "Tom has twice as many apples as Ann. Together they have 30",
            "arithmetic",
            "10 and 20",
        ),
        ("20% discount on 80", "arithmetic", "64"),
        ("80 with 10% tax", "arithmetic", "88"),
        ("percent change from 50 to 80", "arithmetic", "60"),
        ("if 3 cost 12, what do 5 cost", "arithmetic", "20"),
        ("inverse proportion 6 workers 4 days 8 workers", "arithmetic", "3"),
        ("round 3.14159 to 3 decimal places", "arithmetic", "3.142"),
        ("sum to infinity of 8, 4, 2", "arithmetic", "16"),
        ("present value of 1157.625 at 5% for 3 years", "arithmetic", "1000"),
        ("equation of the line through (1,2) and (3,6)", "coord", "y = 2 x"),
        ("unit vector of <3,4>", "vector", "<0.6, 0.8>"),
        ("angle between <1,0> and <0,1>", "vector", "90"),
        ("modulus of 3+4i", "complex", "5"),
        ("range of 1,2,3,4", "statistics", "3"),
        ("modular inverse of 3 mod 11", "number_theory", "4"),
        ("totient of 10", "number_theory", "4"),
        (
            "add [[1,2],[3,4]] and [[0,1],[1,0]]",
            "matrix",
            r"\left[\begin{matrix}1 & 3\\4 & 4\end{matrix}\right]",
        ),
        (
            "transpose [[1,2],[3,4]]",
            "matrix",
            r"\left[\begin{matrix}1 & 3\\2 & 4\end{matrix}\right]",
        ),
        ("geometric k=2 p=0.5", "probability", "0.25"),
        ("complement of 0.3", "probability", "0.7"),
        ("average value of x**2 from 0 to 1", "calculus", r"\frac{1}{3}"),
        (
            "triple integral of 1 from x=0 to 1 and y=0 to 1 and z=0 to 1",
            "calculus",
            "1",
        ),
        ("show that (x+1)**2=x**2+2*x+1", "calculus", "true"),
        ("show that sin(x)**2+cos(x)**2=1", "calculus", "true"),
        ("show that sin(2*x)=2*sin(x)*cos(x)", "calculus", "true"),
        (
            "double integral of x*y from x=0 to 1 and y=0 to 1",
            "calculus",
            r"\frac{1}{4}",
        ),
        (
            "multiply [[1,2],[3,4]] and [[0,1],[1,0]]",
            "matrix",
            r"\left[\begin{matrix}2 & 1\\4 & 3\end{matrix}\right]",
        ),
        (
            "rref [[1,2],[3,4]]",
            "matrix",
            r"\left[\begin{matrix}1 & 0\\0 & 1\end{matrix}\right]",
        ),
        ("eigenvalues of [[2,0],[0,3]]", "matrix", "2, 3"),
        (r"\sqrt[6]{9}", "arithmetic", r"\sqrt[3]{3}"),
        (r"sqrt[6]{9}", "arithmetic", r"\sqrt[3]{3}"),
        (r"\sqrt{\sqrt{16}}", "arithmetic", "2"),
        (r"2/\frac{1}{2}", "arithmetic", "4"),
        (r"\frac{2}{3}^2", "arithmetic", r"\frac{4}{9}"),
        (r"$\sqrt[6]{9}$", "arithmetic", r"\sqrt[3]{3}"),
        (r"9^{1/6}", "arithmetic", r"\sqrt[3]{3}"),
        (r"what is $9^{1/6}$?", "arithmetic", r"\sqrt[3]{3}"),
        (r"what is \sqrt{81}", "arithmetic", "9"),
        ("Let x=-5. Evaluate x^2", "arithmetic", "25"),
        ("Let x=-5. Evaluate 2*x^2", "arithmetic", "50"),
        ("Let x=5. Evaluate 2x", "arithmetic", "10"),
        ("simplify ratio 1.5:2.5", "arithmetic", "3:5"),
        ("simplify ratio 0.5:0.75", "arithmetic", "2:3"),
        ("solve 2x+3=7", "equation", "x = 2"),
        ("solve x^2=9", "equation", r"x = \pm 3"),
        ("solve x+y=5; x-y=1", "system", "x = 3, y = 2"),
        ("differentiate x^3", "calculus", "3 x^{2}"),
        ("differentiate y^3 with respect to y", "calculus", "3 y^{2}"),
        ("differentiate y^3 wrt y", "calculus", "3 y^{2}"),
        ("differentiate y^3 with respect to x", "calculus", "0"),
        ("d/dt t^3", "calculus", "3 t^{2}"),
        ("integrate y^2 dy", "calculus", r"\frac{y^{3}}{3} + C"),
        ("integrate t^2 dt from 0 to 2", "calculus", r"\frac{8}{3}"),
        ("integrate x^2 from 0 to 1", "calculus", r"\frac{1}{3}"),
        ("limit of sin(x)/x as x approaches 0", "limit", "1"),
        ("sum 1/n^2 from n=1 to infinity", "series", r"\frac{\pi^{2}}{6}"),
        ("area of rectangle 3 by 4", "rectangle", "12"),
        ("area of triangle base 3 height 4", "triangle", "6"),
        ("mean of 1,2,3,4", "statistics", "2.5"),
        ("mean of 1/2,3/2", "statistics", "1"),
        ("mean of 1e3,3e3", "statistics", "2000"),
        ("sample variance of 1,2,3", "statistics", "1"),
        ("population variance of 1,2,3", "statistics", "0.666667"),
        ("binomial n=5 k=2 p=0.5", "probability", "0.3125"),
        ("binomial p=1/2 k=2 n=5", "probability", "0.3125"),
        ("expected value of 1,2,3", "probability", "2"),
        ("expected value of 1/2,3/2", "probability", "1"),
        ("5 choose 2", "combinatorics", "10"),
        ("10 permute 3", "combinatorics", "720"),
        ("5!", "combinatorics", "5! = 5 \u00d7 4 \u00d7 3 \u00d7 2 \u00d7 1 = 120"),
        ("determinant [[1,2],[3,4]]", "matrix", "-2"),
        ("sin(30 degrees)", "trig", r"\frac{1}{2}"),
        ("sin(-30 degrees)", "trig", r"- \frac{1}{2}"),
        ("sin(pi/2 + 1)", "trig", r"\cos{\left(1 \right)}"),
        ("sin(1 radians)", "trig", r"\sin{\left(1 \right)}"),
    ],
)
def test_supported_categories_match_the_requested_calculation(text, kind, answer):
    assert math_tools.needs_symbolic_math(text)
    intent = math_tools.extract_math_intent(text)
    assert intent is not None and intent.kind == kind
    block = math_tools._build_verified_block(intent, _settings())
    assert block is not None
    assert block.canonical_answer == answer


@pytest.mark.parametrize(
    "text",
    [
        "sin(30)+cos(60)",
        "-sin(30)",
        "2 sin(30)",
        "x sin(30)",
        "x - sin(30)",
        "sin(2x)",
        "sin(pi*x)",
        "binomial n=5.5 k=2 p=0.5",
        "binomial n=5 k=2.5 p=0.5",
        "binomial n=5 k=2 p=2",
        "expected value of 0,1 with probabilities 0.9,0.1",
        "mean of 1/0,3",
        "mean of 1+2,3",
        "weighted mean of [(1,1),(3,3)]",
        "5.5 choose 2",
        "5 choose 2.5",
        "factorial of 5.5",
        "gcd of 1.5 and 2.5",
        "gcd of 1/2 and 3/2",
        "inverse [[1,2],[2,4]]",
        "simplify ratio 0:0",
        "10th term of 1, 2, 4, 7",
        "increase 200 by 12% and 5%",
        "what percent of 50 is 12 of 20",
        "compound interest on 1000 at 5% for 3 months",
        "union of {1,2,3}",
        "A can do a job in 6 hours and B in 3 hours and 4 hours together",
        "mix 3 liters of 10% with 5 liters of 20% and 2 liters of 30%",
        "prove by induction that 1=1",
        "double integral of x*y from x=0 to 1",
        "20% discount on 80 and 10",
        "if 3 cost 12, what do 5 cost plus 7",
        "sum to infinity of 1, 2, 3",
        "triple integral of 1 from x=0 to 1 and y=0 to 1",
    ],
)
def test_unsupported_or_invalid_input_never_certifies_a_different_problem(text):
    intent = math_tools.extract_math_intent(text)
    block = math_tools._build_verified_block(intent, _settings()) if intent else None
    assert block is None or block.canonical_answer is None


def test_false_show_that_claim_is_rejected_with_its_actual_equality_set() -> None:
    intent = math_tools.extract_math_intent("show that 2*x+3=7")
    assert intent is not None
    block = math_tools._build_verified_block(intent, _settings())
    assert block is not None
    assert block.canonical_answer == r"\text{false}"
    assert block.direct_reply is not None
    assert r"\left\{2\right\}" in block.direct_reply


def test_response_instruction_that_names_identity_still_solves_the_equation() -> None:
    text = (
        "Solve 3x^2 + x^0 = 3. Show every step and name each mathematical "
        "law or identity when it is used."
    )
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.school_op != "identity"
    assert intent.lhs == "3x^2 + x^0"
    assert intent.rhs == "3"

    block = math_tools._build_verified_block(intent, _settings())
    assert block is not None
    assert block.canonical_answer is not None
    assert r"\sqrt{6}" in block.canonical_answer


def test_matrix_inverse_preserves_exact_fractions():
    intent = math_tools.extract_math_intent("inverse [[1,2],[3,4]]")
    assert intent is not None and intent.kind == "matrix"
    block = math_tools._build_verified_block(intent, _settings())
    assert block is not None
    assert block.canonical_answer == (
        r"\left[\begin{matrix}-2 & 1\\\frac{3}{2} & - \frac{1}{2}\end{matrix}\right]"
    )


def test_polar_cardioid_samples_cartesian_points():
    intent = math_tools.extract_math_intent("graph r=1+cos(theta)")
    assert intent is not None and intent.kind == "graph"
    assert intent.school_op == "polar"
    block = math_tools._build_verified_block(intent, _settings())
    assert block is not None and block.canonical_fence is not None
    points = block.canonical_fence["points"]
    assert isinstance(points, list) and len(points) > 10
    assert points[0][0] == pytest.approx(2.0, abs=0.05)
    assert points[0][1] == pytest.approx(0.0, abs=0.05)


def test_parametric_unit_circle_samples():
    intent = math_tools.extract_math_intent("graph x=cos(t), y=sin(t)")
    assert intent is not None and intent.kind == "graph"
    assert intent.school_op == "parametric"
    block = math_tools._build_verified_block(intent, _settings())
    assert block is not None and block.canonical_fence is not None
    points = block.canonical_fence["points"]
    assert isinstance(points, list) and len(points) > 10
    radii = [abs((x**2 + y**2) ** 0.5 - 1.0) for x, y in points]
    assert max(radii) < 0.05


def test_parametric_refuses_a_bare_point():
    intent = math_tools.extract_math_intent("graph x=2, y=3")
    assert intent is None or intent.school_op != "parametric"
