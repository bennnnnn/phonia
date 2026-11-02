"""School rounding, for every subject: a 5 rounds up, on the number as it is written.

A float is read as the shortest decimal that names it, so a tie a student sees is a tie:
2.675 to two places is 2.68 and 62.5 to two figures is 63, not the 2.67 and 62 that a binary
float's round-half-even gives. A 5 rounds away from zero (-2.675 is -2.68). How many places
or figures an answer keeps is each subject's own policy; only the rule lives here.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Context, Decimal
from fractions import Fraction

# Decimal's default precision. A wider value gets the digits it needs, since 1e20 to twelve
# places has 33 and quantize would otherwise refuse it.
_PRECISION = 28


def _exact(value: float | str | Fraction) -> Decimal:
    if isinstance(value, Fraction):
        return Decimal(value.numerator) / Decimal(value.denominator)
    if isinstance(value, str):
        return Decimal(value)
    return Decimal(repr(float(value)))


def round_places(value: float | str | Fraction, places: int) -> Decimal:
    """``value`` half up to ``places`` decimals; a negative ``places`` rounds to tens, hundreds…"""
    exact = _exact(value)
    context = Context(prec=max(exact.adjusted() + 1 + places, _PRECISION))
    return exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP, context=context)


def round_figures(value: float | str | Fraction, figures: int) -> tuple[Decimal, int]:
    """``value`` half up to ``figures`` significant figures as ``(mantissa, exponent)``.

    The mantissa keeps every figure, zeros included; zero is ``(0, 0)``.
    """
    exact = _exact(value)
    if exact == 0:
        return Decimal(0), 0
    exponent = exact.adjusted()
    rounded = round_places(value, figures - 1 - exponent)
    if rounded.adjusted() != exponent:
        # 9.995 to three figures is 10.0: the rounding carried into a new leading digit.
        exponent = rounded.adjusted()
        rounded = rounded.quantize(Decimal(1).scaleb(exponent - figures + 1))
    return rounded.scaleb(-exponent), exponent


def format_places(value: float | str | Fraction, places: int) -> str:
    """``value`` to ``places`` decimals with the zeros a class writes: 3.999 is ``4.00``."""
    return format(round_places(value, places), "f")


def trim_zeros(text: str) -> str:
    """A written decimal without its trailing zeros: ``2.50`` is ``2.5``, ``3.0`` is ``3``."""
    return text.rstrip("0").rstrip(".") if "." in text else text
