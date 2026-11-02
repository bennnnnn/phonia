"""An odd root of a number takes its sign from the number's value, never from how it is
written, and a question in complex numbers that writes one has no single value."""

from __future__ import annotations

import pytest
from sympy import I, Pow, Rational, sqrt

from app.core.config import Settings
from app.modules.math import school as math_school
from app.modules.math.solve.expressions import simplify_expression
from app.modules.math.solve.real_reading import complex_without_cause, real_odd_roots
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.extract import extract_math_intent
from app.services.solving import SolveServiceError

_SETTINGS = Settings(math_tools_enabled=True)


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        # 1 - √2 is negative though it is written with its positive term first.
        ("cbrt(1-sqrt(2))", r"- \sqrt[3]{\sqrt{2} - 1}"),
        ("cbrt(7-5*sqrt(2))", r"- \sqrt[3]{5 \sqrt{2} - 7}"),
        ("cbrt(2-sqrt(5))", r"- \sqrt[3]{\sqrt{5} - 2}"),
        ("cbrt(pi-4)", r"- \sqrt[3]{4 - \pi}"),
        # ∛((1 - √2)(1 + √2)) = ∛(-1).
        ("cbrt(1-sqrt(2))*cbrt(1+sqrt(2))", "-1"),
        # SymPy's -1, never Python's float: no "-1.0" in front of the fraction.
        ("1/cbrt(1-sqrt(2))", r"- \frac{1}{\sqrt[3]{\sqrt{2} - 1}}"),
        ("(-8)^(1/3)", "-2"),
        ("(-32)^(3/5)", "-8"),
        # A decimal base is read as written: evaluated, its power is already complex.
        ("(-0.008)^(2/3)", "0.04"),
        ("(-0.5)^(-1/3)", "-1.25992104989487"),
        ("(-2.5)^(2/3)", "1.84201574932019"),
        # A tiny radicand keeps its sign: its size is no reason to doubt it.
        ("cbrt(-10^-15)", r"- \frac{1}{100000}"),
        ("(-0.000000000000001)^(1/3)", "-1.0 \\cdot 10^{-5}"),
        # Inner roots first: ∛(∛(-27) - 5) = ∛(-8).
        ("cbrt(cbrt(-27)-5)", "-2"),
        # ∛(-8)·√(-9) = -2·3i; evaluated, SymPy folds it into 6·(-1)^(5/6).
        ("cbrt(-8)*sqrt(-9)", "- 6 i"),
        # A long exact form proved equal to an integer prints the integer, not 1.0.
        ("cbrt(sqrt(5)+2) - cbrt(sqrt(5)-2)", "1"),
        ("cbrt(20+14*sqrt(2)) + cbrt(20-14*sqrt(2))", "4"),
    ],
)
def test_odd_root_of_a_number_takes_the_sign_of_its_value(expression: str, value: str) -> None:
    assert simplify_expression(expression, "x").latex == value
    assert math_school.evaluate_arithmetic(expression) == value


def test_an_odd_root_of_a_positive_number_stays_real() -> None:
    for shown in (
        simplify_expression("(sqrt(3)-sqrt(2))^(2/3)", "x").latex,
        math_school.evaluate_arithmetic("(sqrt(3)-sqrt(2))^(2/3)"),
    ):
        assert shown == "0.465732"


@pytest.mark.parametrize(
    ("expression", "principal"),
    [
        ("(-16)^(1/4)", r"\sqrt{2} + \sqrt{2} i"),
        ("(-16)^(3/4)", r"- 4 \sqrt{2} + 4 \sqrt{2} i"),
        ("(-8)^(1/6)", r"\frac{\sqrt{6}}{2} + \frac{\sqrt{2}}{2} i"),
    ],
)
def test_an_even_root_of_a_negative_number_keeps_its_principal_value(
    expression: str, principal: str
) -> None:
    # No real root competes: like √(-9) = 3i, the principal value is the answer.
    assert simplify_expression(expression, "x").latex == principal


def test_a_number_written_with_its_minus_first_is_not_negated() -> None:
    # √2 - 1 is positive: its cube root keeps SymPy's real principal value.
    root = (sqrt(2) - 1) ** Rational(1, 3)
    assert real_odd_roots(root) == root


def test_an_odd_root_of_a_non_real_number_keeps_the_principal_root() -> None:
    assert math_school.evaluate_complex("cbrt(-8i)") == r"\sqrt{3} - i"
    assert math_school.evaluate_complex("cbrt(8i)") == r"\sqrt{3} + i"
    # A sixth root of a negative number has no real value to compete with.
    assert math_school.evaluate_complex("(-64)^(1/6)") == r"\sqrt{3} + i"


@pytest.mark.parametrize(
    "expression",
    [
        # -2 + 2i read with the real root, 1 + (2 + √3)i with the principal one.
        "(-8)^(1/3) + 2i",
        "(-8)^(1/3)",
        "(-8)^(2/3)",
        # Evaluated, i·∛(-8) is 2·(-1)^(5/6), an even root; it is read as written.
        "cbrt(-8)*i",
        "cbrt(1-sqrt(2))*i",
    ],
)
def test_odd_root_of_a_negative_number_in_complex_numbers_is_declined(expression: str) -> None:
    with pytest.raises(SolveServiceError):
        math_school.evaluate_complex(expression)


@pytest.mark.parametrize(
    "query",
    ["Write (-8)^(1/3) + 2i in the form a + bi", "Express (-8)^(1/3) in the form a+bi"],
)
def test_complex_form_of_an_odd_root_of_a_negative_is_not_certified(query: str) -> None:
    intent = extract_math_intent(query)
    block = _build_verified_block(intent, _SETTINGS) if intent is not None else None
    assert block is None or block.canonical_answer is None


def test_a_value_with_i_from_an_expression_without_it_is_not_certified() -> None:
    principal = (-1) ** Rational(5, 6)  # an odd root left on SymPy's principal branch
    assert complex_without_cause(sqrt(2), principal * 2)
    assert not complex_without_cause(3 * I, -2 + 3 * I)  # √(-9) is 3i as written
    assert not complex_without_cause(Pow(-16, Rational(1, 4), evaluate=False), principal)
    assert not complex_without_cause(sqrt(2), sqrt(2))


def test_the_sign_of_a_radicand_that_is_exactly_zero_is_not_searched_for() -> None:
    # √(5 + 2√6) = √2 + √3: SymPy's own sign test can search without end on such a zero.
    zero = sqrt(5 + 2 * sqrt(6)) - sqrt(2) - sqrt(3)
    root = Pow(zero, Rational(1, 3), evaluate=False)
    assert real_odd_roots(root) is root


@pytest.mark.parametrize("expression", ["5/0", "0/0", "log(0)", "tan(pi/2)"])
def test_an_undefined_value_is_not_read_as_a_complex_one(expression: str) -> None:
    assert math_school.evaluate_arithmetic(expression) == math_school.UNDEFINED_LATEX
