"""A complex number as a book writes it: a + bi, the real part first, each part one number.

SymPy prints ``\\frac{5 i}{2} - \\frac{1}{2}`` for -1/2 + 5i/2, and a sum for b ran into a:
``2 + 1 + \\sqrt{2} i`` for 2 + (1 + √2)i.
"""

from __future__ import annotations

from typing import Any

from sympy import latex


def a_plus_bi(value: Any) -> str | None:
    """``a + bi`` for a number with both parts; None for anything else."""
    if getattr(value, "free_symbols", None) or not getattr(value, "is_number", False):
        return None
    real, imaginary = value.as_real_imag()
    if real == 0 or imaginary == 0 or not (real.is_comparable and imaginary.is_comparable):
        return None
    if imaginary.is_Add:
        # A sum's sign is its value's: √3 - 1 is positive though it "starts" with -1.
        negative = bool(imaginary < 0)
    else:
        # A product's sign is as printed: 3·sin(30) is a negative number printed bare.
        negative = imaginary.could_extract_minus_sign()
    size = -imaginary if negative else imaginary
    if size == 1:
        coefficient = ""
    elif size.is_Add:  # (1 + √2)i, never 1 + √2 i
        coefficient = rf"\left({latex(size)}\right) "
    else:
        coefficient = f"{latex(size)} "
    first = rf"\left({latex(real)}\right)" if real.is_Add else latex(real)
    return f"{first} {'-' if negative else '+'} {coefficient}i"


def restates(typed: str, answer: str) -> bool:
    """The answer is the question's own expression: ``x + 2`` asked "in the form a + bi",
    an unexpanded product, ``i y + x`` for ``x + yi``. It certifies nothing."""
    from app.modules.math.solve.key_steps import written_side

    written = written_side(typed, ["x"])
    if written is None:
        return False
    typed_tex, answer_tex = (sorted(tex.replace(" ", "")) for tex in (written[1], answer))
    return typed_tex == answer_tex  # the same symbols, whatever order SymPy put them in
