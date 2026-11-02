# ruff: noqa: RUF002, RUF003 -- the test reads × and the dots it replaces.
"""Multiplication prints × in every server-written row, never a dot."""

from __future__ import annotations

import pytest

from app.services.law_binding.expression import Notation, to_latex
from app.services.law_binding.reduction import reduce_substitution
from app.services.times_sign import times, with_times
from app.services.workout import math_line


@pytest.mark.parametrize(
    "written, shown",
    [
        (r"KE = \frac{1}{2} \cdot 2 \cdot 10^{2}", r"KE = \frac{1}{2} \times 2 \times (10)^{2}"),
        ("KE = 0.5 · 2 · 100", r"KE = 0.5 \times 2 \times 100"),
        (r"v_f = \frac{2\cdot 3 + 1\cdot 0}{2+1}", r"v_f = \frac{2 \times 3 + 1 \times 0}{2+1}"),
        (r"P = F \cdot v", r"P = F \times v"),
        ("2 ⋅ 3", r"2 \times 3"),
        # A quantity times a quantity: the unit before the dot does not make it a unit.
        (
            r"d = 25\,\mathrm{m/s} \cdot 200\,\mathrm{s}",
            r"d = 25\,\mathrm{m/s} \times 200\,\mathrm{s}",
        ),
        # A 10 that is not raised, or not alone, is a number like any other.
        (r"2 \cdot 10 + 1", r"2 \times 10 + 1"),
        (r"2 \cdot 100^{2}", r"2 \times 100^{2}"),
    ],
)
def test_with_times_writes_a_product_as_times(written: str, shown: str) -> None:
    assert with_times(written) == shown


@pytest.mark.parametrize(
    "written",
    [
        r"\vec{a} \cdot \vec{b} = 4 + 10 + 18",
        r"\mathbf{F} \cdot \mathbf{d}",
        r"J = 3\,\mathrm{N·s}",
        r"J = 3 \text{ N}\cdot\text{s}",
        r"1 + 2 + \cdots + n",
        r"a \cdotp b",
        r"3.31 \times 10^{-19}",
        "",
    ],
)
def test_with_times_leaves_what_is_not_a_product(written: str) -> None:
    assert with_times(written) == written


def test_times_brackets_a_raised_ten_after_the_sign() -> None:
    assert times("2", "10^{2}") == r"2 \times (10)^{2}"
    assert times("10^{2}", "3") == r"10^{2} \times 3"


def test_expression_printer_writes_times() -> None:
    plain = Notation(constants={}, number=lambda value: f"{value:g}")
    row = to_latex("0.5*m*v**2", {"m": "m", "v": "v"}, {"m": 2.0, "v": 10.0}, notation=plain)
    assert row == r"0.5 \times 2 \times (10)^{2}"


def test_reduction_reads_a_bracketed_ten_as_a_power() -> None:
    """``2 × (10)²`` is 2 × 100, not the scientific 2 × 10² read as one number."""
    reduction = reduce_substitution("KE", r"0.5 \times 2 \times (10)^{2}", lambda n: f"{n:g}")
    assert reduction is not None
    assert reduction.value == pytest.approx(100.0)
    assert any("100" in row and r"(10)" not in row for row in reduction.rows)


def test_math_line_prints_times() -> None:
    assert math_line(r"x = 3 \cdot 4") == r"$x = 3 \times 4$"
