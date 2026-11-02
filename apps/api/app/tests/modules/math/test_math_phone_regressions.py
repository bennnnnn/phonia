"""Regressions found by the two 30-case iPhone math passes."""

import pytest

from app.core.config import Settings
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent

_SETTINGS = Settings(math_tools_enabled=True)


def _verified(query: str):
    intent = extract_math_intent(query)
    assert intent is not None, query
    block = _build_verified_block(intent, _SETTINGS)
    assert block is not None, query
    return intent, block


def test_requested_quadratic_formula_is_not_misread_as_factor_pronoun() -> None:
    query = "Solve x^2 - 5x + 6 = 0 using the quadratic formula. Do not factor it."
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.kind == "equation"
    assert intent.school_op == "quadratic_formula"
    assert reply is not None
    assert "Quadratic formula" in reply
    assert "Factor the left side" not in reply
    assert block.canonical_answer == r"x = 2 \text{ or } x = 3"


def test_numeric_base_logs_keep_the_logarithms_and_enforce_the_domain() -> None:
    query = "Solve log_2(x - 1) + log_2(x - 3) = 3."
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.kind == "equation"
    assert "ln(x - 1)" in (intent.lhs or "")
    assert block.canonical_answer == "x = 5"
    assert reply is not None
    assert "Domain restriction" in reply
    assert "x = -1" in reply
    assert "Reject values outside the domain" in reply


def test_bounded_powered_trig_equation_returns_only_degree_domain_roots() -> None:
    query = "Solve 2sin^2(x) - 3sin(x) + 1 = 0 for 0° <= x < 360°."
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.kind == "trig" and intent.school_op == "bounded_degree_equation"
    assert block.canonical_answer == r"x = 30^\circ,\;90^\circ,\;150^\circ"
    assert reply is not None
    assert "all real" not in reply.lower()


def test_bounds_first_divergent_series_is_not_misread_as_n_equals_zero() -> None:
    query = "Determine whether the series sum from n=0 to infinity of (-1)^n converges or diverges."
    intent, block = _verified(query)

    assert intent.kind == "series"
    assert intent.expr == "(-1)**n"
    assert block.canonical_answer is None
    assert "diverges" in block.text.lower()
    assert maybe_direct_math_reply(block, query) == (
        "This series diverges; it has no ordinary sum."
    )


def test_bounds_first_improper_integral_states_divergence_not_bare_infinity() -> None:
    query = "Evaluate the improper integral from 1 to infinity of 1/x dx."
    intent, block = _verified(query)

    assert intent.kind == "calculus"
    assert intent.integral_lower == "1" and intent.integral_upper == "infinity"
    assert block.canonical_answer is None
    assert maybe_direct_math_reply(block, query) == (
        "This improper integral diverges to +∞; it does not converge to a finite value."
    )


def test_absolute_inequality_number_line_suffix_stays_on_verified_path() -> None:
    query = "Solve |2x - 3| < 5 and show the answer on a number line."
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.kind == "inequality"
    assert reply is not None
    assert "```graph" in reply
    assert block.canonical_fence is not None
    assert block.canonical_fence["type"] == "number_line"


def test_rational_inequalities_show_clean_interval_notation() -> None:
    cases = {
        "Solve x/(x-3) > 0.": r"\left(-\infty,\;0\right) \cup \left(3,\;\infty\right)",
        "Solve (x+2)(x-1)/(x-4) <= 0.": (r"\left(-\infty,\;-2\right] \cup \left[1,\;4\right)"),
    }
    for query, interval in cases.items():
        _intent, block = _verified(query)
        reply = maybe_direct_math_reply(block, query)
        assert reply is not None
        assert interval in reply
        assert r"\wedge" not in reply


def test_singular_inverse_returns_a_fast_explanation() -> None:
    query = "Find the inverse of [[1,2],[2,4]]."
    _intent, block = _verified(query)

    assert block.canonical_answer is None
    assert maybe_direct_math_reply(block, query) == (
        "This matrix has no inverse because its determinant is 0."
    )


def test_non_diagonalizable_matrix_returns_a_fast_explanation() -> None:
    query = "Diagonalize [[1,1],[0,1]]."
    _intent, block = _verified(query)

    assert block.canonical_answer is None
    assert maybe_direct_math_reply(block, query) == (
        "This matrix is not diagonalizable: it does not have enough "
        "linearly independent eigenvectors."
    )


def test_combined_degree_trig_expression_is_evaluated_as_one_expression() -> None:
    query = "Evaluate 2sin(30 degrees)+cos(60 degrees)."
    intent, block = _verified(query)

    assert intent.kind == "trig"
    assert block.canonical_answer == r"\frac{3}{2}"


def test_exponential_equation_returns_exact_and_decimal_forms_directly() -> None:
    query = "Solve 2^x = 7. Give an exact answer and decimal approximation."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert block.canonical_answer is not None
    assert r"\log_{2} 7" in block.canonical_answer
    assert reply is not None
    assert "Exact answer" in reply
    assert r"x \approx 2.80735" in reply


def test_radical_returns_requested_exact_and_decimal_forms_directly() -> None:
    query = r"What is \sqrt[6]{9}? Give exact form and a decimal approximation."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert block.canonical_answer == r"\sqrt[3]{3}"
    assert reply is not None
    assert "— exact" in reply
    assert r"\approx 1.44225" in reply


def test_z_score_uses_all_labeled_values_and_does_not_search_for_meaning() -> None:
    query = (
        "A test has mean 72 and standard deviation 8. A student scored 88. "
        "What is the z-score? Then explain what it means, but do not assume "
        "the distribution is normal."
    )
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.kind == "arithmetic" and intent.school_op == "z_score"
    assert reply is not None
    assert r"\frac{88 - 72}{8} = 2" in reply
    assert "2 standard deviations above the mean" in reply
    assert "does not assume a normal distribution" in reply


def test_single_radical_equation_checks_and_rejects_extraneous_roots() -> None:
    query = "Solve √(2x + 3) = x."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert block.canonical_answer == "x = 3"
    assert reply is not None
    assert "Domain restrictions" in reply
    assert "x = -1" in reply
    assert "reject extraneous roots" in reply.lower()


def test_two_radical_equation_uses_verified_repeated_squaring() -> None:
    query = "Solve sqrt(x + 2) + sqrt(x - 1) = 3."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert block.canonical_answer == "x = 2"
    assert reply is not None
    assert "Isolate one radical" in reply
    assert "Square again" in reply
    assert "Check in the original equation" in reply


def test_rational_equations_keep_denominator_restrictions_and_reject_cancelled_root() -> None:
    query = "Solve (x-2)/(x^2-4) = 1/4."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert block.canonical_answer is not None
    assert block.canonical_answer.startswith(r"\text{no solution}")
    assert reply is not None
    assert r"x \ne -2" in reply and r"x \ne 2" in reply
    assert "Reject the excluded candidate" in reply


def test_real_fractional_power_keeps_both_real_branches() -> None:
    query = "Solve x^(2/3) = 4 over the real numbers."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert block.canonical_answer == r"x = \pm 8"
    assert reply is not None
    assert "real odd-root interpretation" in reply


def test_square_root_of_a_square_simplifies_to_absolute_value() -> None:
    query = "Simplify √(x^2)."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert block.canonical_answer == r"\left|{x}\right|"
    assert reply is not None
    assert "principal square root is never negative" in reply


def test_square_root_law_survives_ascii_equivalent_and_real_domain_wording() -> None:
    answers = []
    for query in (
        "Simplify sqrt(x^2) over the real numbers.",
        "Simplify sqrt(x*x) for real x.",
    ):
        _intent, block = _verified(query)
        answers.append(block.canonical_answer)

    assert answers == [r"\left|{x}\right|", r"\left|{x}\right|"]


def test_compound_fraction_simplification_preserves_every_excluded_value() -> None:
    query = "Simplify (1/x + 1/y) / (1/x - 1/y)."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert reply is not None
    assert r"x \ne 0" in reply
    assert r"y \ne 0" in reply
    assert r"x \ne y" in reply


def test_implicit_derivative_consumes_the_whole_xy_equation() -> None:
    query = "Find dy/dx implicitly for x^2 + xy + y^2 = 7."
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.school_op == "implicit"
    assert block.canonical_answer == r"\frac{- 2 x - y}{x + 2 y}"
    assert reply is not None
    assert r"\frac{dy}{dx} x" in reply
    assert r"x + 2 y" in reply


def test_implicit_derivative_keeps_trailing_teaching_request_out_of_equation() -> None:
    for derivative_spelling in ("dy/dx", "day/dx"):
        query = (
            f"Find {derivative_spelling} implicitly for x^2 + xy + y^2 = 7. "
            "Show every differentiation step and collect the derivative terms."
        )
        intent, block = _verified(query)
        reply = maybe_direct_math_reply(block, query)

        assert intent.school_op == "implicit"
        assert block.canonical_answer == r"\frac{- 2 x - y}{x + 2 y}"
        assert reply is not None
        assert r"\frac{dy}{dx}" in reply
        assert "Solve the equation" not in reply


def test_logarithmic_substitution_uses_absolute_value_and_states_domain() -> None:
    query = "Integrate 1/(x ln x) dx."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert block.canonical_answer == r"\ln\left|\ln\left(x\right)\right| + C"
    assert reply is not None
    assert r"x \ne 1" in reply
    assert "x > 0" in reply


def test_logarithmic_substitution_honors_explicit_working_request_directly() -> None:
    query = (
        "Integrate 1/(x ln x) dx. Show the substitution, give the exact "
        "antiderivative, and state the real-domain restrictions."
    )
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert reply is not None
    assert "— substitute" in reply
    assert "— integrate" in reply
    assert "— substitute back" in reply
    assert r"x \ne 1" in reply
    assert "x > 0" in reply


def test_conditional_dice_enumerates_the_conditioned_sample_space() -> None:
    query = (
        "Two fair dice are rolled. Given that the sum is at least 10, what is the "
        "probability the sum is exactly 12? Show the conditional sample space."
    )
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.school_op == "dice_conditional_sum"
    assert block.canonical_answer == r"\frac{1}{6}"
    assert reply is not None
    assert "{(4, 6), (5, 5), (5, 6), (6, 4), (6, 5), (6, 6)}" in reply
    assert "```answer\n\\frac{1}{6}\n```" in reply
    assert r"\frac{1}{6}=\frac{1}{6}" not in reply


def test_conditional_dice_comparator_variation_uses_the_same_enumerator_logic() -> None:
    query = (
        "Two fair dice are thrown. Knowing the sum is at most 4, find the probability "
        "the sum is equal to 2. List the conditional sample space."
    )
    intent, block = _verified(query)

    assert intent.comparator == "<="
    assert block.canonical_answer == r"\frac{1}{6}"


def test_improper_endpoint_definite_integral_uses_verified_limits_directly() -> None:
    query = "Evaluate the integral from 0 to 1 of ln(x) dx."
    _intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert block.canonical_answer == "-1"
    assert reply is not None
    assert "as a limit at the endpoint" in reply
    assert "```answer\n-1\n```" in reply


def test_arc_length_with_sentence_period_uses_the_calculus_application() -> None:
    query = "Find the arc length of y = (2/3)x^(3/2) from x=0 to x=3."
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.school_op == "arc_length"
    assert block.canonical_answer == r"\frac{14}{3}"
    assert reply is not None
    assert "**Arc length formula**" in reply
    assert "no solution" not in reply.lower()


def test_volume_chain_bounds_and_when_wording_use_disk_method() -> None:
    query = "Find the volume when y=sqrt(x), 0<=x<=4, is revolved about the x-axis."
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.school_op == "volume_revolution_x"
    assert block.canonical_answer == r"8 \pi"
    assert reply is not None and "Disk method" in reply
    assert "simplify the cross-section" in reply
    assert "evaluate the endpoints" in reply


def test_area_between_curves_names_order_and_shows_endpoint_evaluation() -> None:
    query = "Find the area between y=x and y=x^2 from x=0 to x=1."
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.school_op == "area_between_curves"
    assert block.canonical_answer == r"\frac{1}{6}"
    assert reply is not None
    assert "upper curve first" in reply
    assert "— integrate" in reply
    assert "evaluate the endpoints" in reply


def test_bounded_radian_trig_and_reciprocal_domain_are_direct() -> None:
    cases = {
        "Solve cos(2x) = 0 for 0 <= x < 2 pi.": (
            r"\frac{\pi}{4}",
            r"\frac{7 \pi}{4}",
        ),
        "Find all x where sec(x) is undefined on 0 <= x <= 2 pi.": (
            r"\frac{\pi}{2}",
            r"\frac{3 \pi}{2}",
        ),
    }
    for query, expected in cases.items():
        intent, block = _verified(query)
        reply = maybe_direct_math_reply(block, query)
        assert intent.school_op == "bounded_radian_equation"
        assert reply is not None
        assert all(value in reply for value in expected)
        if query.startswith("Solve cos"):
            assert "periodic zero law" in reply
            assert r"k\in\mathbb{Z}" in reply
            assert r"k = 0,\;1,\;2,\;3" in reply
            assert r"0 \le x < 2 \pi" in reply


def test_exact_composite_degree_angle_uses_angle_sum_identity() -> None:
    queries = (
        "Find the exact value of cos(75 degrees).",
        "Find the exact value of cos(75 degrees). "
        "Use an angle-sum identity and keep radicals in exact form.",
    )
    for query in queries:
        intent, block = _verified(query)
        reply = maybe_direct_math_reply(block, query)

        assert intent.school_op == "cos"
        assert block.canonical_answer == r"\frac{- \sqrt{2} + \sqrt{6}}{4}"
        assert reply is not None
        assert "Angle-sum identity" in reply
        assert r"75^\circ = 30^\circ + 45^\circ" in reply
        # Four short component lines stay readable on a narrow phone instead
        # of becoming a single clipped equation chain.
        assert r"\cos(30^\circ)=\frac{\sqrt{3}}{2}" in reply
        assert r"\cos(45^\circ)=\frac{\sqrt{2}}{2}" in reply
        assert r", \quad" not in reply


def test_product_and_second_derivatives_use_verified_working_directly() -> None:
    cases = {
        "Differentiate y = x^2 e^(3x).": "Product rule",
        "Find d^2y/dx^2 if y = e^x sin x.": "second derivative",
    }
    for query, expected in cases.items():
        _intent, block = _verified(query)
        reply = maybe_direct_math_reply(block, query)
        assert reply is not None
        assert expected in reply


def test_natural_mean_score_wording_stays_on_z_score_path() -> None:
    query = (
        "A class has mean score 72 and standard deviation 8. A student scored 88. "
        "Find the z-score and say whether this assumes a normal distribution."
    )
    intent, block = _verified(query)
    reply = maybe_direct_math_reply(block, query)

    assert intent.school_op == "z_score"
    assert reply is not None
    assert r"\frac{88 - 72}{8} = 2" in reply


@pytest.mark.parametrize("query", ["F = ma", "solve F = ma", "E = mc^2", "A = lw"])
def test_a_formula_without_its_unknown_is_not_certified_no_solution(query: str) -> None:
    """Solved for an x it does not contain, ``F = ma`` came back "no solution", verified."""
    intent = extract_math_intent(query)
    block = _build_verified_block(intent, _SETTINGS) if intent is not None else None
    assert block is None or "no solution" not in (block.canonical_answer or "")


@pytest.mark.parametrize("query", ["x - x = 5", "2x + 3 = 2x + 5"])
def test_a_contradiction_in_its_unknown_is_still_no_solution(query: str) -> None:
    _intent, block = _verified(query)
    assert block.canonical_answer == r"\text{no solution}"
