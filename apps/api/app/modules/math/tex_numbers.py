"""Exact numbers as a worked line writes them in TeX."""

from __future__ import annotations

from fractions import Fraction


def fraction_tex(value: Fraction) -> str:
    """``3``, or ``-\\frac{1}{2}``: a whole number as itself, else a fraction with its sign
    in front."""
    if value.denominator == 1:
        return str(value.numerator)
    sign = "-" if value < 0 else ""
    return rf"{sign}\frac{{{abs(value.numerator)}}}{{{value.denominator}}}"
