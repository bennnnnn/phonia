"""Property-based tests for the math extractors (Hypothesis).

The extractor registry is a hand-tuned regex decision tree; example tests pin
the cases we already know about. These properties pin the *invariants* over
generated inputs:

- extraction never raises and always returns a schema-valid intent (or None),
- a generated arithmetic prompt extracts an expression whose value matches
  the reference computation,
- a generated linear equation extracts sides symbolically equivalent to the
  generated equation.

Failing minimal examples printed by Hypothesis get pinned as regression tests
in the example-based suites.
"""

from __future__ import annotations

from fractions import Fraction

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from app.modules.math.match import needs_symbolic
from app.modules.math.schemas import MathIntent
from app.modules.math.solve import parse_expression
from app.modules.math.solve.fractions import build_fraction_work
from app.modules.math.solve.written_arithmetic import build_written_arithmetic_operands
from app.modules.math.tools.extract import extract_math_intent

_SMALL_INT = st.integers(min_value=-50, max_value=50)
_POS_INT = st.integers(min_value=1, max_value=9)


@given(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
        max_size=200,
    )
)
# Circled digits pass str.isdigit() but int() rejects them.
@example(text="P\u2776")
@example(text="\u2776P")
@settings(max_examples=100, deadline=None)
def test_extract_never_raises_and_stays_schema_valid(text: str) -> None:
    """Arbitrary unicode/punctuation soup: no crash, valid intent, deterministic."""
    first = extract_math_intent(text)
    second = extract_math_intent(text)
    assert first == second
    if first is not None:
        # Round-trip through the schema — an extractor must never emit a
        # half-formed intent that Pydantic would reject downstream.
        MathIntent.model_validate(first.model_dump())
    # The gate must survive the same input.
    assert needs_symbolic(text) in (True, False)


@given(a=_SMALL_INT, op=st.sampled_from(["+", "-", "*"]), b=_SMALL_INT)
@settings(max_examples=60, deadline=None, derandomize=True)
def test_generated_arithmetic_extracts_matching_value(a: int, op: str, b: int) -> None:
    text = f"what is {a} {op} {b}"
    intent = extract_math_intent(text)
    assert intent is not None, text
    assert intent.kind == "arithmetic"
    assert intent.expr is not None
    parsed = parse_expression(intent.expr)
    expected = a + b if op == "+" else (a - b if op == "-" else a * b)
    assert float(parsed) == pytest.approx(expected), text


@given(a=_POS_INT, b=_SMALL_INT, c=_SMALL_INT)
@settings(max_examples=60, deadline=None, derandomize=True)
def test_generated_linear_equation_extracts_equivalent_sides(a: int, b: int, c: int) -> None:
    sign = "+" if b >= 0 else "-"
    text = f"solve {a}x {sign} {abs(b)} = {c}"
    intent = extract_math_intent(text)
    assert intent is not None, text
    assert intent.kind == "equation"
    assert intent.lhs is not None and intent.rhs is not None
    lhs = parse_expression(intent.lhs, ["x"])
    rhs = parse_expression(intent.rhs, ["x"])
    reference = parse_expression(f"{a}*x + ({b}) - ({c})", ["x"])
    assert (lhs - rhs - reference).simplify() == 0, text


@given(values=st.lists(st.integers(min_value=0, max_value=9999), min_size=2, max_size=6))
@settings(max_examples=60, deadline=None, derandomize=True)
def test_written_addition_trace_preserves_sum(values: list[int]) -> None:
    tokens = [str(value) for value in values]
    spec = build_written_arithmetic_operands(tokens, "column_addition", "+".join(tokens))
    assert spec is not None
    assert int(spec.answer) == sum(values)
    assert all(len(column.addends) == len(values) for column in spec.addition_columns)


@given(
    top=st.integers(min_value=0, max_value=999_999),
    bottom=st.integers(min_value=0, max_value=999_999),
)
@settings(max_examples=60, deadline=None, derandomize=True)
def test_written_subtraction_trace_preserves_difference(top: int, bottom: int) -> None:
    larger, smaller = max(top, bottom), min(top, bottom)
    spec = build_written_arithmetic_operands(
        [str(larger), str(smaller)], "column_subtraction", f"{larger}-{smaller}"
    )
    assert spec is not None
    assert int(spec.answer) == larger - smaller


@given(left=st.integers(min_value=0, max_value=9999), right=st.integers(min_value=0, max_value=999))
@settings(max_examples=60, deadline=None, derandomize=True)
def test_written_multiplication_partial_products_sum_to_product(left: int, right: int) -> None:
    spec = build_written_arithmetic_operands(
        [str(left), str(right)], "column_multiplication", f"{left}*{right}"
    )
    assert spec is not None
    assert sum(int(product.shifted_product) for product in spec.partial_products) == left * right
    assert int(spec.answer) == left * right


@given(
    dividend=st.integers(min_value=0, max_value=999_999),
    divisor=st.integers(min_value=1, max_value=999),
)
@settings(max_examples=80, deadline=None, derandomize=True)
def test_long_division_trace_preserves_euclidean_invariant(dividend: int, divisor: int) -> None:
    spec = build_written_arithmetic_operands(
        [str(dividend)], "long_division", f"{dividend}/{divisor}"
    )
    assert spec is None

    spec = build_written_arithmetic_operands(
        [str(dividend), str(divisor)],
        "long_division",
        f"{dividend}/{divisor}",
        division_answer_mode="remainder",
    )
    assert spec is not None
    quotient = int(spec.quotient or "0")
    remainder = int(spec.remainder or "0")
    assert dividend == divisor * quotient + remainder
    assert 0 <= remainder < divisor


@given(
    a=st.integers(min_value=0, max_value=999),
    b=st.integers(min_value=1, max_value=99),
    c=st.integers(min_value=1, max_value=999),
    d=st.integers(min_value=1, max_value=99),
)
@settings(max_examples=80, deadline=None, derandomize=True)
def test_fraction_traces_preserve_exact_rational_invariants(a: int, b: int, c: int, d: int) -> None:
    left, right = Fraction(a, b), Fraction(c, d)
    for school_op, expected in (
        ("fraction_add", left + right),
        ("fraction_multiply", left * right),
        ("fraction_divide", left / right),
    ):
        intent = MathIntent(
            kind="arithmetic",
            school_op=school_op,
            fraction_operands=[f"{a}/{b}", f"{c}/{d}"],
            operation="solve",
        )
        work = build_fraction_work(intent)
        assert work is not None
        assert work.exact_numerator == expected.numerator
        assert work.exact_denominator == expected.denominator


@given(
    a=st.integers(min_value=0, max_value=999),
    b=st.integers(min_value=1, max_value=99),
    c=st.integers(min_value=0, max_value=999),
    d=st.integers(min_value=1, max_value=99),
)
@settings(max_examples=80, deadline=None, derandomize=True)
def test_nonnegative_fraction_subtraction_trace_is_exact(a: int, b: int, c: int, d: int) -> None:
    first, second = Fraction(a, b), Fraction(c, d)
    left, right = (first, second) if first >= second else (second, first)
    intent = MathIntent(
        kind="arithmetic",
        school_op="fraction_subtract",
        fraction_operands=[
            f"{left.numerator}/{left.denominator}",
            f"{right.numerator}/{right.denominator}",
        ],
        operation="solve",
    )
    work = build_fraction_work(intent)
    assert work is not None
    expected = left - right
    assert work.exact_numerator == expected.numerator
    assert work.exact_denominator == expected.denominator
