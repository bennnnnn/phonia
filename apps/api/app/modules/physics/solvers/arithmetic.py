"""Small arithmetic a solver writes out: quadratic roots, a number set for LaTeX."""

from __future__ import annotations

import math


def quadratic_roots(a: float, b: float, c: float) -> tuple[float, ...]:
    """Real roots of ``a·x² + b·x + c = 0``, ascending; linear when ``a`` is 0.

    The closed form, in the cancellation-free arrangement: a plain quadratic
    does not need a symbolic solver on the request path.
    """
    if a == 0:
        return () if b == 0 else (-c / b,)
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return ()
    q = -0.5 * (b + math.copysign(math.sqrt(discriminant), b))
    if q == 0:
        return (0.0,)
    return tuple(sorted({q / a, c / q}))


def latex_num(value: float, *, square: bool = False) -> str:
    """Format a number for LaTeX so ``-5^2`` is not read as ``-(5^2)``."""
    text = f"{value:g}"
    if value < 0:
        text = f"({text})"
    if square:
        return f"{text}^{{2}}"
    return text
