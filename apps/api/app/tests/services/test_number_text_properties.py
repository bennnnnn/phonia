"""``fold_scientific`` keeps a number's value (Hypothesis; code-health audit TEST-08).

Physics and chemistry read ``a * 10^n`` as the float ``aen``; maths hands SymPy the
exact product. Whichever sign or power a student writes, the folded text must be the
same number.
"""

from __future__ import annotations

from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st
from sympy import Rational, sympify

from app.services.number_text import fold_scientific

_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def _power(exponent: int, form: str) -> str:
    if form == "superscript":
        return "10" + str(exponent).translate(_SUPERSCRIPT)
    return f"10^{exponent}"


@given(
    whole=st.integers(min_value=-999, max_value=999),
    fraction=st.integers(min_value=0, max_value=999),
    exponent=st.integers(min_value=-30, max_value=30),
    times=st.sampled_from(["×", "x", "*", "·"]),
    form=st.sampled_from(["caret", "superscript"]),
)
@settings(max_examples=200, deadline=None)
def test_folding_keeps_the_value(
    whole: int, fraction: int, exponent: int, times: str, form: str
) -> None:
    mantissa = f"{whole}.{fraction:03d}"
    text = f"{mantissa} {times} {_power(exponent, form)}"
    exact = Fraction(mantissa) * Fraction(10) ** exponent

    assert Fraction(float(fold_scientific(text))) == Fraction(float(exact))
    product = sympify(fold_scientific(text, "product").replace("^", "**"), rational=True)
    assert product == Rational(exact.numerator, exact.denominator)
