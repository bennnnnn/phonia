"""Complete calculus requests retain all parameters without extra narration."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.modules.math.fence import validate_math_fences
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.direct_calculus import calculus_direct_request
from app.modules.math.tools.extract import extract_math_intent
from app.services.answer_fence import mark_server_answer_fences

_CASES = [
    ("Differentiate x^3", "3 x^{2}"),
    (
        "Differentiate x^3*sin(x)",
        r"x^{2} \left(x \cos{\left(x \right)} + 3 \sin{\left(x \right)}\right)",
    ),
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
]
_SETTINGS = Settings(math_tools_enabled=True)


def _verified(query):
    intent = extract_math_intent(query)
    assert intent is not None
    block = _build_verified_block(intent, _SETTINGS)
    assert block is not None
    return block


@pytest.mark.parametrize("query,answer", _CASES)
def test_complete_calculus_request_preserves_the_full_verified_answer(query, answer):
    block = _verified(query)
    assert block.canonical_answer == answer
    assert calculus_direct_request(query) is True
    reply = maybe_direct_math_reply(block, query)
    assert reply is not None
    assert f"```answer\n{answer}\n```" in reply
    assert (
        validate_math_fences(reply, verified=block).strip()
        == mark_server_answer_fences(reply).strip()
    )


@pytest.mark.parametrize("query,answer", _CASES)
@pytest.mark.parametrize(
    "suffix",
    [" and explain why", " and solve x+1=2", ", hint only", " with steps", " on the domain x>0"],
)
def test_extra_asks_domains_and_teaching_never_disappear(query, answer, suffix):
    assert maybe_direct_math_reply(_verified(query), query + suffix) is None


@pytest.mark.parametrize(
    "query",
    [
        "Find the fourth derivative of x^4",
        "Find twice the second derivative of x^4",
        "Differentiate x^3!",
        "Differentiate x^3; 2+2",
        "Differentiate x^3 + sin(x) and cos(x)",
        "Find the partial derivative of x^2*y with respect to y and x",
        "Find the partial derivative of x^2*y with respect to yy",
        "Integrate x^2 from 0 to 1 and 2",
        "Find the definite integral of x^2",
        "Find the indefinite integral of x^2 from 0 to 1",
        "Integrate x^2 with respect to x from 0 to 1, then evaluate at 3",
        "Find the limit of sin(x)/x as x approaches 0 along the complex plane",
        "Find the limit of sin(x)/x as x approaches 0 from both sides and compare them",
        "Sum n from n=1 to 10 excluding n=5",
        "Sum n from n=1 to 10 and n^2",
        "Sum n from n=1 to 10!",
        "Find the Taylor series of exp(x) at 1 order 2 and give the remainder",
        "Find the Taylor series of exp(x) at pi order 2",
        "Find the Maclaurin series of sin(x) order 3.5",
        "Find the Maclaurin series of sin(x) order 0",
    ],
)
def test_unsupported_or_partial_calculus_cannot_use_generic_prose_fallback(query):
    assert calculus_direct_request(query) is False
    assert maybe_direct_math_reply(_verified("Differentiate x^3"), query) is None


@pytest.mark.parametrize("query", ["Find the critical points of x^3-3x"])
def test_outcomes_without_complete_answer_or_method_presentation_keep_model(query):
    assert maybe_direct_math_reply(_verified(query), query) is None


def test_two_sided_nonexistent_limit_and_derivative_at_point_are_direct() -> None:
    limit_query = "Find the limit of 1/x as x approaches 0"
    assert maybe_direct_math_reply(_verified(limit_query), limit_query) == (
        "The two-sided limit does not exist because the one-sided limits disagree."
    )

    # d²/dx² x^4 = 12x^2, which is 48 at x = 2 (32 is the first derivative).
    derivative_query = "Find the second derivative of x^4 at x=2"
    reply = maybe_direct_math_reply(_verified(derivative_query), derivative_query)
    assert reply is not None and "```answer\n48\n```" in reply


def test_divergent_series_returns_a_complete_direct_explanation() -> None:
    query = "Sum (-1)^n from n=0 to infinity"
    assert maybe_direct_math_reply(_verified(query), query) == (
        "This series diverges; it has no ordinary sum."
    )


def test_existing_simple_ode_keeps_its_constant_and_direct_behavior():
    query = "Solve dy/dx=2x"
    assert calculus_direct_request(query) is None
    block = _verified(query)
    reply = maybe_direct_math_reply(block, query)
    assert reply is not None and block.canonical_answer in reply
    # The arbitrary constant stays, written as a student writes it.
    assert block.canonical_answer == "y = x^{2} + C"


@pytest.mark.parametrize(
    "query",
    [
        "Find the second derivative of t^4",
        "Find the partial derivative of x^2*y wrt x",
        "Integrate t^2 dt from -1 to 2",
        "Find the limit of 1/t as t approaches 0 from the left",
        "Sum k^2 from k=2 to 5",
        "Find the Taylor series of exp(x) at -1 order 3",
    ],
)
def test_nonfixture_variables_bounds_and_centers_are_preserved(query):
    block = _verified(query)
    assert calculus_direct_request(query) is True
    reply = maybe_direct_math_reply(block, query)
    assert reply is not None
    assert f"```answer\n{block.canonical_answer}\n```" in reply
    assert (
        validate_math_fences(reply, verified=block).strip()
        == mark_server_answer_fences(reply).strip()
    )


@pytest.mark.parametrize(
    "query,updates",
    [
        ("Find the second derivative of x^4", {"derivative_order": 1}),
        ("Find the second derivative of x^4", {"expr": "x^3"}),
        ("Find the partial derivative of x^2*y wrt y", {"variable": "x"}),
        ("Integrate x^2 from 0 to 1", {"integral_upper": "2"}),
        ("Find the limit of 1/x as x approaches 0 from the left", {"limit_direction": "+"}),
        ("Sum n from n=1 to 10", {"series_end": "11"}),
        ("Find the Taylor series of exp(x) at 1 order 2", {"limit_point": "0"}),
        ("Find the Maclaurin series of sin(x) order 3", {"taylor_n": 2}),
    ],
)
def test_whole_query_must_agree_with_every_extracted_parameter(query, updates):
    intent = extract_math_intent(query)
    assert intent is not None
    with patch(
        "app.modules.math.tools.direct_calculus.extract_math_intent",
        return_value=intent.model_copy(update=updates),
    ):
        assert calculus_direct_request(query) is False


def test_images_incomplete_fences_and_unevaluated_results_keep_model():
    query = "Find the second derivative of x^4"
    block = _verified(query)
    assert maybe_direct_math_reply(block, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(block, canonical_fence=None), query) is None
    assert maybe_direct_math_reply(replace(block, canonical_answer="different"), query) is None
    for answer in (r"\lim_{x\to0}f(x)", r"\int x dx", r"\sum n", r"\frac{d}{dx}f(x)"):
        unresolved = replace(
            block, canonical_answer=answer, canonical_fence={"type": "answer", "content": answer}
        )
        assert maybe_direct_math_reply(unresolved, query) is None


@pytest.mark.parametrize("query", ["Sum n from n=1 to infinity", "Sum -n from n=1 to infinity"])
def test_infinite_sums_retain_the_divergence_explanation(query):
    block = _verified(query)
    assert block.canonical_answer is not None and r"\infty" in block.canonical_answer
    assert maybe_direct_math_reply(block, query) is None


@pytest.mark.parametrize(
    "query",
    [
        # SymPy's accumulation bounds, <-1, 1>, were the verified answer.
        "Find the limit of sin(1/x) as x approaches 0",
        "limit of cos(1/x) as x->0",
        "Find the limit of cos(x) as x approaches infinity",
        "limit of cos(n*pi) as n->infinity",
        "limit of sin(1/x) as x approaches 0 from the right",
        "limit of tan(1/x) as x->0",
        # The limit is 1; SymPy bounds the two terms apart, <0, 2>.
        "limit of sin(1/x)^2 + cos(1/x)^2 as x->0",
        # The bounds inside a larger answer: |<-1, 1>|, oo*sign(<-1, 1>).
        "limit of |sin(1/x)| as x->0",
        "limit of x*sin(x) as x->infinity",
        "limit of sin(1/x)/x as x approaches 0 from the right",
        # Limit(...) unevaluated, then i and i*pi for a limit over the reals.
        "limit of sin(x)^x as x->infinity",
        "limit of sqrt(x) as x->-1",
        "limit of ln(x) as x->-1",
        # "The one-sided limits disagree", where there are no two sides (at
        # infinity) or neither side has a limit.
        "limit of (-2)^n as n->infinity",
        "limit of sin(1/x)/x as x->0",
        # An average value over an infinite interval: <0, 2> / oo = 0.
        "average value of sin(x) from 0 to oo",
        # "infinity" read as the product of the letters i, n, f, t, y.
        "average value of sin(x) from 0 to infinity",
        # The integral diverges; the working said it was -2 under an oo card.
        "find the average value of 1/x^2 on [-1, 1]",
        # The integral unevaluated, then one holding oo, i and a Limit (it is 0).
        "average value of x^x on [0, 1]",
        "average value of sin(1/x) on [-1, 1]",
    ],
)
def test_a_value_sympy_did_not_establish_is_not_verified(query):
    intent = extract_math_intent(query)
    assert intent is not None
    assert _build_verified_block(intent, _SETTINGS) is None


@pytest.mark.parametrize(
    "query,answer,reply",
    [
        ("limit of 1/x as x->0", None, "one-sided limits disagree"),
        ("limit of |x|/x as x->0", None, "one-sided limits disagree"),
        ("limit of e^(1/x) as x->0", None, "one-sided limits disagree"),
        ("limit of 1/x^2 as x->0", r"\infty", None),
        ("limit of -1/x^2 as x->0", r"-\infty", None),
        ("limit of x*sin(1/x) as x->0", "0", None),
        ("limit of sin(x)/x as x->infinity", "0", None),
        ("sum (-1)^n for n=1 to infinity", None, "diverges; it has no ordinary sum"),
        ("integrate sin(x) from 0 to infinity", None, "does not converge"),
        ("average value of x^2 from 0 to 3", "3", None),
        ("average value of x on [a, b]", r"\frac{a}{2} + \frac{b}{2}", None),
    ],
)
def test_a_limit_that_does_not_exist_keeps_its_verified_outcome(query, answer, reply):
    block = _verified(query)
    assert block.canonical_answer == answer
    if reply is not None:
        assert block.direct_reply is not None and reply in block.direct_reply


@pytest.mark.parametrize(
    "query",
    [
        "Integrate 1/x from -1 to 1",
        "Integrate 1/x^2 from -1 to 1",
    ],
)
def test_undefined_or_divergent_improper_integrals_keep_explanation(query):
    block = _verified(query)
    if "1/x^2" in query:
        assert block.canonical_answer is None
        assert "diverges to positive infinity" in block.text
        assert maybe_direct_math_reply(block, query) == (
            "This improper integral diverges to +∞; it does not converge to a finite value."
        )
    else:
        assert block.canonical_answer is None
        assert "did not establish a defined value" in block.text
        assert maybe_direct_math_reply(block, query) == (
            "This ordinary improper integral does not converge. "
            "A Cauchy principal value is a separate convention and was not requested."
        )
