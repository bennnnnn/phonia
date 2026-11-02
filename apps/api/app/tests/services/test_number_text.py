"""One number grammar, and scientific notation is one number however it is typed."""

from __future__ import annotations

import re
import time

import pytest

from app.services.number_text import (
    DECIMAL_LITERAL,
    FRACTION_OR_DECIMAL,
    SIGNED_DECIMAL,
    SIGNED_DECIMAL_SCI,
    TEXT_DECIMAL,
    TEXT_NUMBER,
    bounded_decimal,
    finite_match_value,
    fold_scientific,
    number_immediately_before,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2 × 10^-6 C", "2e-6 C"),
        ("2x10^-6", "2e-6"),
        ("2 X 10^-6", "2e-6"),
        ("2*10**-6", "2e-6"),
        ("2·10⁻⁶ C", "2e-6 C"),
        ("1.5 × 10³", "1.5e3"),
        (r"2 \times 10^{-6}", "2e-6"),
        (r"6.63\,\times\,10^{-34}", "6.63e-34"),
        (r"1.6 \cdot 10^{-19}", "1.6e-19"),
        ("1.6 × 10^(−19) C", "1.6e-19 C"),
        ("−1.6×10^–19", "-1.6e-19"),
        ("4.5 x 10 ^ -3", "4.5e-3"),
        ("3 × 10^8 m/s", "3e8 m/s"),
        ("a speed of 10^8 m/s", "a speed of 1e8 m/s"),
        ("6,000 × 10^3", "6000e3"),
        # A full stop ending the sentence is not a decimal exponent.
        ("Ka = 1.8 × 10^-5. Find the pH", "Ka = 1.8e-5. Find the pH"),
        ("c = 3 × 10^8.", "c = 3e8."),
    ],
)
def test_fold_scientific_writes_one_float_literal(text: str, expected: str) -> None:
    assert fold_scientific(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Maths keeps the power of ten, which SymPy holds exactly.
        ("1.8·10⁻⁵ divided by 3", "1.8*10^(-5) divided by 3"),
        ("1.8 x 10^-5 * 2", "1.8*10^(-5) * 2"),
        ("3 x 10^4 + 2 x 10^3", "3*10^4 + 2*10^3"),
        ("1.8 X 10^+5", "1.8*10^5"),
        (r"1.6 \times 10^{-19}", "1.6*10^(-19)"),
        ("2*10**-6", "2*10^(-6)"),
        ("1.5 × 10³", "1.5*10^3"),
        ("10⁻⁵ * 3", "10^(-5) * 3"),
        ("10^5 / 2", "10^5 / 2"),
    ],
)
def test_fold_scientific_product_keeps_the_power(text: str, expected: str) -> None:
    assert fold_scientific(text, style="product") == expected


@pytest.mark.parametrize(
    "text",
    [
        "2 × 10 m",  # a product, not a power of ten
        "10^2.5",  # a fractional exponent is not notation
        "x10^5",  # a variable times a power
        "m/s^2",
        "2E-6",  # already one literal
        "in 2010 the",
        "10^1234",  # four-digit exponents are not read
    ],
)
@pytest.mark.parametrize("style", ["e", "product"])
def test_fold_scientific_leaves_other_text(text: str, style: str) -> None:
    assert fold_scientific(text, style=style) == text  # type: ignore[arg-type]


@pytest.mark.wall_clock
@pytest.mark.parametrize("head", ["10^", "2 x 10 ^", "2 x 10^{"])
@pytest.mark.parametrize("style", ["e", "product"])
def test_fold_scientific_stays_linear_on_a_pasted_run_of_spaces(head: str, style: str) -> None:
    text = head + " " * 20_000 + "x"
    started = time.perf_counter()
    assert fold_scientific(text, style=style) == text  # type: ignore[arg-type]
    assert time.perf_counter() - started < 0.5


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        (SIGNED_DECIMAL, "radius .5 cm", [".5"]),
        (SIGNED_DECIMAL, "3 - -2.5 + +4", ["3", "-2.5", "+4"]),
        (SIGNED_DECIMAL, "1e-5", ["1", "-5"]),
        (SIGNED_DECIMAL_SCI, "1e-5 and 6.02E+23", ["1e-5", "6.02E+23"]),
        # A typed value: a spaced sign ("x = - 3") and a fraction are one value.
        (FRACTION_OR_DECIMAL, "x = -1/2 or - 3 or 3 / 1.5", ["-1/2", "- 3", "3 / 1.5"]),
        # Running text: a plus is the operator, so "5+20% of 80" never reads +20.
        (TEXT_DECIMAL, "5+20% of 80, -3 °C", ["5", "20", "80", "-3"]),
        (TEXT_NUMBER, "1.5e3 J at .5 m", ["1.5e3", ".5"]),
        # A match never starts inside a number: "1.2.3" holds no ".3".
        (TEXT_DECIMAL, "version 1.2.3", ["1.2"]),
    ],
)
def test_named_patterns_read_whole_literals(pattern: str, text: str, expected: list[str]) -> None:
    assert re.findall(pattern, text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("12.5", "12.5"), ("-.25", "-.25"), ("1234567890123", None), ("1.5e3", "1.5")],
)
def test_bounded_decimal_caps_each_digit_run(text: str, expected: str | None) -> None:
    match = re.match(rf"{bounded_decimal(12)}(?![0-9])", text)
    assert (match.group(0) if match else None) == expected


def test_bounded_decimal_may_read_a_short_exponent() -> None:
    assert re.fullmatch(bounded_decimal(24, exponent_digits=4), "2.5e-3")
    assert not re.fullmatch(bounded_decimal(24, exponent_digits=4), "2.5e12345")


@pytest.mark.wall_clock
@pytest.mark.parametrize("pattern", [TEXT_NUMBER, bounded_decimal(24)])
def test_a_failed_search_stays_linear_on_a_pasted_digit_run(pattern: str) -> None:
    text = "9" * 50_000 + " km"
    started = time.perf_counter()
    assert re.search(rf"({pattern})\s*mi\b", text) is None
    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize(("text", "expected"), [("12.5", 12.5), ("1" * 400, None)])
def test_finite_match_value(text: str, expected: float | None) -> None:
    match = re.match(r"\d+(?:\.\d+)?", text)
    assert match is not None
    assert finite_match_value(match) == expected


@pytest.mark.parametrize(
    ("text", "before", "expected"),
    [("rate 5 %", "%", "5"), ("rate 2.5%", "%", "2.5"), ("rate 5x %", "%", None), ("%", "%", None)],
)
def test_number_immediately_before(text: str, before: str, expected: str | None) -> None:
    found = number_immediately_before(text, text.index(before))
    assert (found.group(0) if found else None) == expected
    assert found is None or found.re is DECIMAL_LITERAL
