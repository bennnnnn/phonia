"""An equation's roots in LaTeX: ``a + b i`` with ``i`` outside the fraction, and ± and
conjugate pairs on one answer line (``x^6 = 1`` as three lines, not six roots)."""

from __future__ import annotations

from typing import Any

from sympy import Abs, Symbol, conjugate, im, latex, log, simplify

from app.modules.math.solve.declines import declines
from app.modules.math.solve.display import format_verified_latex


@declines(False)
def expr_equal(left: Any, right: Any) -> bool:
    return bool(simplify(left - right) == 0)


@declines(False)
def _is_real_value(val: Any) -> bool:
    return bool(simplify(im(val)) == 0)


def _solution_value_latex(val: Any) -> str:
    """``a + b i`` with ``i`` outside the fraction, not ``\\frac{\\sqrt{3} i}{2}``."""
    val = simplify(val)
    if not val.is_number:
        return str(latex(val))
    real, imag = val.as_real_imag()
    real, imag = simplify(real), simplify(imag)
    if imag == 0:
        if real.has(log):
            # Exponential equations need their exact logarithmic solution;
            # the generic readability threshold would otherwise replace it
            # with a decimal before an exact+approximation request can render.
            return str(latex(real))
        return format_verified_latex(real)
    if real == 0:
        if imag == 1:
            return "i"
        if imag == -1:
            return "-i"
        return f"{format_verified_latex(imag)} i"
    if imag.is_number and imag < 0:
        return f"{format_verified_latex(real)} - {format_verified_latex(-imag)} i"
    return f"{format_verified_latex(real)} + {format_verified_latex(imag)} i"


def compact_root_answer_lines(variable: str, values: list[Any]) -> list[str]:
    """Pair ± reals and conjugate complexes so the answer pill is readable.

    ``x^6 = 1`` becomes three lines (``\\pm 1`` and two ``a \\pm b i``) instead
    of six comma-joined sympy strings that clip off the side of the gray box.
    """
    pool = [simplify(v) for v in values]
    used = [False] * len(pool)
    lines: list[str] = []
    var_l = str(latex(Symbol(variable)))

    for i, v in enumerate(pool):
        if used[i] or not _is_real_value(v) or expr_equal(v, 0):
            continue
        for j, w in enumerate(pool):
            if used[j] or i == j or not _is_real_value(w):
                continue
            if not expr_equal(v + w, 0):
                continue
            pos = v
            if v.is_number and w.is_number:
                pos = v if v >= 0 else w
            elif v.is_number and v < 0:
                pos = -v
            pos = simplify(Abs(pos)) if _is_real_value(pos) else simplify(pos)
            lines.append(f"{var_l} = \\pm {_solution_value_latex(pos)}")
            used[i] = used[j] = True
            break

    for i, v in enumerate(pool):
        if used[i] or _is_real_value(v):
            continue
        conj = simplify(conjugate(v))
        if expr_equal(v, conj):
            continue
        for j, w in enumerate(pool):
            if used[j] or i == j:
                continue
            if not expr_equal(w, conj):
                continue
            real, imag = v.as_real_imag()
            real, imag_abs = simplify(real), simplify(Abs(simplify(imag)))
            imag_l = "i" if imag_abs == 1 else f"{_solution_value_latex(imag_abs)} i"
            if real == 0:
                lines.append(f"{var_l} = \\pm {imag_l}")
            else:
                real_l = _solution_value_latex(real)
                lines.append(f"{var_l} = {real_l} \\pm {imag_l}")
            used[i] = used[j] = True
            break

    for i, v in enumerate(pool):
        if not used[i]:
            lines.append(f"{var_l} = {_solution_value_latex(v)}")
    return lines
