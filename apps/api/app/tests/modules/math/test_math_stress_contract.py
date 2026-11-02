"""High-risk domain, branch, invalid-input, and graph behavior."""

import math

import pytest

from app.core.config import Settings
from app.modules.math.schemas.intent import MathIntent
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent

_SETTINGS = Settings(math_tools_enabled=True)


def _verified(query: str):
    intent = extract_math_intent(query)
    assert intent is not None, query
    block = _build_verified_block(intent, _SETTINGS)
    assert block is not None, query
    return intent, block, maybe_direct_math_reply(block, query)


def test_parameter_equation_keeps_the_zero_coefficient_branch() -> None:
    _intent, block, reply = _verified("Solve ax=5.")
    assert block.canonical_answer is not None
    assert r"x = \frac{5}{a}" in block.canonical_answer
    assert r"a \ne 0" in block.canonical_answer
    assert "a = 0" in block.canonical_answer and "no solution" in block.canonical_answer
    assert reply is not None


def test_answer_only_no_graph_constraint_is_not_misread_as_a_graph_command() -> None:
    intent, block, reply = _verified("Solve x^2 < 4. Just the answer; no graph and no steps.")
    assert intent.kind == "inequality"
    assert block.canonical_answer == r"-2 < x < 2"
    assert reply == "```answer\n-2 < x < 2\n```\n"


def test_numeric_linear_equation_does_not_display_a_constant_domain_condition() -> None:
    _intent, block, reply = _verified("Solve 3x=1. Show every step.")
    assert block.canonical_answer == r"x = \frac{1}{3}"
    assert block.domain_conditions == ()
    assert reply is not None and r"3 \ne 0" not in reply


def test_false_square_root_identity_gives_domain_and_counterexample() -> None:
    _intent, block, reply = _verified("Is sqrt(x^2)=x always true?")
    assert block.canonical_answer == r"\text{false}"
    assert reply is not None
    assert r"\left[0, \infty\right)" in reply
    assert "left}=2" in reply and "right}=-2" in reply


def test_calculus_nonresults_are_not_rendered_as_numeric_answers() -> None:
    cases = {
        "Differentiate |x| at x=0.": "Left derivative: -1; right derivative: 1",
        "Differentiate x^(1/3) at x=0.": "not finite from both sides",
        "Find lim x->0 |x|/x.": "one-sided limits disagree",
        "Evaluate ∫[-1,1] 1/x dx.": "ordinary improper integral does not converge",
    }
    for query, phrase in cases.items():
        _intent, block, reply = _verified(query)
        assert reply is not None and phrase in reply
        if "Differentiate" not in query:
            assert block.canonical_answer is None


def test_series_ode_and_dependent_system_preserve_all_requested_structure() -> None:
    _series_intent, _series, series_reply = _verified(
        "Does Σ 1/n converge? What about Σ (-1)^(n+1)/n?"
    )
    assert series_reply is not None
    assert "diverges" in series_reply and "converges conditionally" in series_reply

    for ode_query in ("Solve y'=y with y(0)=2.", "Solve y’=y with y(0)=2."):
        _ode_intent, ode, _ode_reply = _verified(ode_query)
        assert ode.canonical_answer == r"y{\left(x \right)} = 2 e^{x}"
        assert _ode_reply is not None

    _system_intent, system, _system_reply = _verified("Solve x+y=2 and 2x+2y=4.")
    assert system.canonical_answer is not None
    assert "infinitely many solutions" in system.canonical_answer
    assert "one free variable" in system.canonical_answer


def test_invalid_probability_statistics_and_geometry_fail_helpfully() -> None:
    cases = {
        "Find expected value for outcomes [1,2,3] with probabilities [0.1,0.2,0.3].": (
            "sum to 0.6, not 1"
        ),
        "Find correlation between [1,2,3] and [4,5].": "3 values versus 2",
        "Can a triangle have side lengths 1, 2, and 3?": "non-degenerate triangle",
        (
            "A circle has radius 3 and a chord of length 8. Find distance from center to chord."
        ): "maximum chord length is the diameter, 6",
    }
    for query, phrase in cases.items():
        _intent, block, reply = _verified(query)
        assert block.canonical_answer is None
        assert reply is not None and phrase in reply


def test_graphs_keep_holes_domains_and_asymptote_segments() -> None:
    _hole_intent, hole, _hole_reply = _verified("Graph (x^2-1)/(x-1).")
    assert hole.canonical_fence is not None
    assert hole.canonical_fence["holes"] == [[1.0, 2.0]]

    _sqrt_intent, sqrt_graph, _sqrt_reply = _verified("Graph sqrt(x-2).")
    assert sqrt_graph.canonical_fence is not None
    assert min(point[0] for point in sqrt_graph.canonical_fence["points"]) >= 2

    _tan_intent, tan_graph, _tan_reply = _verified("Graph tan(x) from -π to π.")
    assert tan_graph.canonical_fence is not None
    assert math.isclose(tan_graph.canonical_fence["x_min"], -math.pi)
    assert math.isclose(tan_graph.canonical_fence["x_max"], math.pi)
    assert tan_graph.canonical_fence["domain_explicit"] is True
    assert len(tan_graph.canonical_fence["segments"]) == 3

    _default_intent, default_graph, _default_reply = _verified("Graph x^2.")
    assert default_graph.canonical_fence is not None
    assert default_graph.canonical_fence["domain_explicit"] is False


def test_temperature_ratio_uses_kelvin_and_answers_both_parts() -> None:
    intent, block, reply = _verified(
        "Convert 32°F to Celsius. Then tell me whether 64°F is twice as hot."
    )
    assert intent.school_op == "temperature_twice_compare"
    assert block.canonical_answer is None
    assert reply is not None
    assert "32\\,°F = 0\\,Celsius" in reply
    assert "absolute scale" in reply
    assert "not twice as hot" in reply


def test_a_bayes_intent_without_its_question_text_still_gets_its_answer_card() -> None:
    """The model's own tool call builds the intent with no request text; that used to
    raise inside the block builder, so the turn lost its verified answer."""
    intent = MathIntent(
        kind="probability", school_op="bayes", vec_a=[0.02, 0.95, 0.10], operation="solve"
    )
    block = _build_verified_block(intent, _SETTINGS)
    assert block is not None
    assert block.canonical_answer is not None
    assert float(block.canonical_answer) == pytest.approx(0.162393, rel=1e-4)


def test_named_medical_bayes_maps_specificity_to_the_false_positive_rate() -> None:
    queries = (
        (
            "A disease test has sensitivity 95%, specificity 90%, and prevalence 2%. "
            "If a person tests positive, what is the probability they actually have the "
            "disease? Show the Bayes calculation."
        ),
        "With prevalence 2 percent, sensitivity 95 percent, and specificity 90 percent, "
        "what is the positive predictive value?",
        "2% prevalence, 90% specificity, and 95% sensitivity: calculate PPV.",
    )
    for query in queries:
        intent, block, _reply = _verified(query)
        assert intent.school_op == "bayes"
        assert intent.vec_a == pytest.approx([0.02, 0.95, 0.10])
        assert block.canonical_answer == r"16.2393\%"
        assert block.direct_reply is not None
        assert "false-positive rate" in block.direct_reply
        assert r"P(+\mid D)" in block.direct_reply
        assert "=1-0.9=0.1" not in block.direct_reply
        assert "0.019" in block.direct_reply
        assert "0.117" in block.direct_reply
