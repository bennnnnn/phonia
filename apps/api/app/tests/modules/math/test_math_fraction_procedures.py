"""Fractions use exact typed school procedures, never model-made working."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from app.core.config import Settings
from app.modules.math.fence import validate_math_fences
from app.modules.math.response_intent import classify_math_response_intent
from app.modules.math.schemas import FractionWorkSpec
from app.modules.math.tools import _build_verified_block, extract_math_intent
from app.modules.math.tools.direct import maybe_direct_math_reply

_SETTINGS = Settings(math_tools_enabled=True)


def _work(question: str) -> FractionWorkSpec:
    intent = extract_math_intent(question)
    assert intent is not None and intent.kind == "arithmetic"
    block = _build_verified_block(intent, _SETTINGS)
    assert block is not None
    candidates = [
        item
        for item in (block.canonical_fence, *block.canonical_fences)
        if item is not None and item.get("type") == "fraction"
    ]
    assert len(candidates) == 1
    return FractionWorkSpec.model_validate(candidates[0])


@pytest.mark.parametrize(
    "question, operation, answer",
    [
        ("Simplify 8/12", "simplify", r"\frac{2}{3}"),
        ("Show steps: 1/2 + 1/3", "add", r"\frac{5}{6}"),
        ("3/4 - 1/6", "subtract", r"\frac{7}{12}"),
        ("2/3 × 9/10", "multiply", r"\frac{3}{5}"),
        ("3/5 divided by 9/10", "divide", r"\frac{2}{3}"),
        ("Convert 2 1/3 to an improper fraction", "mixed_to_improper", r"\frac{7}{3}"),
        ("Convert 7/3 to a mixed number", "improper_to_mixed", r"2\frac{1}{3}"),
        ("3/4 of 20", "of_quantity", "15"),
        ("Compare 2/3 and 3/5", "compare", r"\frac{2}{3} > \frac{3}{5}"),
        (
            "Find an equivalent fraction to 2/3 with denominator 12",
            "equivalent",
            r"\frac{8}{12}",
        ),
    ],
)
def test_fraction_procedures_are_exact(question: str, operation: str, answer: str) -> None:
    spec = _work(question)
    assert spec.operation == operation
    assert spec.answer == answer
    assert spec.steps
    if spec.exact_numerator is not None and spec.exact_denominator is not None:
        assert Fraction(spec.exact_numerator, spec.exact_denominator) == Fraction(
            spec.exact_numerator, spec.exact_denominator
        )


def test_fraction_request_with_meaningful_leftover_fails_closed() -> None:
    assert extract_math_intent("Simplify 8/12 and solve 2x=4") is None
    assert extract_math_intent("Simplify 1/2 and calculate 99") is None


def test_complete_three_term_expression_is_not_mistaken_for_leftover_data() -> None:
    intent = extract_math_intent("1/2 + 1/3 + 99")
    assert intent is not None and intent.expr is not None
    assert "99" in intent.expr


def test_improper_to_mixed_procedure_shows_the_complete_conversion() -> None:
    spec = _work("Convert 29/4 to a mixed number and show the steps")

    assert len(spec.steps) == 2
    assert spec.steps[0].expression == "29"
    assert spec.steps[0].result == r"4\times 7+1"
    assert spec.steps[1].expression == r"\frac{29}{4}"
    assert spec.steps[1].result == r"7+\frac{1}{4}"
    assert spec.answer == r"7\frac{1}{4}"


def test_mixed_to_improper_procedure_keeps_the_denominator_visible() -> None:
    spec = _work("Convert 2 1/3 to an improper fraction and show the steps")

    assert len(spec.steps) == 2
    assert spec.steps[0].expression == r"2\times 3"
    assert spec.steps[0].result == "6"
    assert spec.steps[1].expression == r"\frac{6+1}{3}"
    assert spec.steps[1].result == r"\frac{7}{3}"


def test_fraction_direct_reply_and_fence_use_only_canonical_trace() -> None:
    question = "Show steps: 1/2 + 1/3"
    intent = extract_math_intent(question)
    assert intent is not None
    block = _build_verified_block(intent, _SETTINGS)
    assert block is not None

    reply = maybe_direct_math_reply(block, question)
    assert reply is not None and '"type":"fraction"' in reply
    block = replace(block, response_intent=classify_math_response_intent(question))
    cleaned = validate_math_fences(
        '```arithmetic\n{"type":"fraction","answer":"999"}\n```', verified=block
    )
    assert '"answer":"\\\\frac{5}{6}"' in cleaned
    assert '"answer":"999"' not in cleaned


def test_equal_denominators_skip_the_common_denominator_rewrite() -> None:
    # "1/2, 3/2 = 1/2, 3/2" rewrote the sum to itself; the denominators already match.
    spec = _work("Show steps: 1/2 + 3/2")

    assert [step.kind for step in spec.steps] == ["combine", "gcd"]
    assert "already the same" in spec.steps[0].explanation
    assert spec.steps[0].expression == r"\frac{1 + 3}{2}"
    assert spec.steps[0].result == r"\frac{4}{2}"
    assert spec.steps[1].result == spec.answer == "2"


def test_unequal_denominators_rewrite_the_sum_not_a_list() -> None:
    spec = _work("Show steps: 1/2 + 1/3")

    rewrite = spec.steps[0]
    assert rewrite.kind == "common_denominator"
    assert rewrite.expression == r"\frac{1}{2} + \frac{1}{3}"
    assert rewrite.result == r"\frac{3}{6} + \frac{2}{6}"
    assert [step.kind for step in spec.steps] == ["common_denominator", "combine"]


@pytest.mark.parametrize("symbol", ["+", "-"])
@pytest.mark.parametrize("first", ["1/2", "3/4", "5/6", "2/3", "1/4", "7/8"])
@pytest.mark.parametrize("second", ["1/2", "1/4", "1/3", "1/6", "3/8"])
def test_every_fraction_step_changes_something(symbol: str, first: str, second: str) -> None:
    question = f"Show steps: {first} {symbol} {second}"
    intent = extract_math_intent(question)
    if intent is None or (symbol == "-" and Fraction(first) < Fraction(second)):
        return
    spec = _work(question)
    for step in spec.steps:
        assert step.expression != step.result, (question, step)
        assert ",\\ " not in step.expression + step.result, (question, step)
    expected = (
        Fraction(first) + Fraction(second)
        if symbol == "+"
        else (Fraction(first) - Fraction(second))
    )
    assert Fraction(spec.exact_numerator or 0, spec.exact_denominator or 1) == expected
