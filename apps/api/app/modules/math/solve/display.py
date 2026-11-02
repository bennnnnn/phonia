"""A verified SymPy result as LaTeX: exact when short, a derivative as a textbook writes it."""

from __future__ import annotations

import cmath
from typing import Any

_EXACT_LATEX_DECIMAL_THRESHOLD = 40


def without_unit_factors(expr: Any) -> Any:
    """``1/(x - 2)`` parses unevaluated as ``1·(x - 2)⁻¹``, printed ``1 \\frac{1}{x - 2}``,
    which reads as a mixed number. The typed expression has no factor 1."""
    if not any(getattr(expr, kind, False) for kind in ("is_Add", "is_Mul", "is_Pow")):
        return expr  # a leaf, a function, or the tuple ``2, 3`` parses to
    args = [without_unit_factors(arg) for arg in expr.args]
    if expr.is_Mul:
        args = [arg for arg in args if arg != 1] or [expr.args[0]]
        if len(args) == 1:
            return args[0]
    if args == list(expr.args):
        return expr
    return expr.func(*args, evaluate=False)


def derivative_latex(expr: Any) -> str:
    """A derivative as a textbook writes it.

    A quotient keeps one fraction bar: the denominator factored, the numerator
    expanded unless factoring shows a repeated factor:
    ``\\frac{x^{2} - 2 x - 1}{\\left(x - 1\\right)^{2}}``, not SymPy's
    ``\\frac{- x^{2} + 2 x \\left(x - 1\\right) - 1}{...}``. Anything else is
    left to ``format_verified_latex``.
    """
    from sympy import cancel, expand, factor, fraction, latex, together

    symbols: set[Any] = set(getattr(expr, "free_symbols", set()))
    if len(symbols) != 1 or not expr.is_rational_function(*symbols):
        return format_verified_latex(expr)
    numerator, denominator = fraction(cancel(together(expr)))
    if not denominator.free_symbols:
        return format_verified_latex(expr)
    factored = factor(numerator)
    repeated = factored.is_Pow or (
        factored.is_Mul and any(part.is_Pow and part.free_symbols for part in factored.args)
    )
    top = factored if repeated else expand(numerator)
    bottom = factor(denominator)
    if top.could_extract_minus_sign() and not top.is_Add:
        return rf"- \frac{{{latex(-top)}}}{{{latex(bottom)}}}"
    return rf"\frac{{{latex(top)}}}{{{latex(bottom)}}}"


def format_verified_latex(expr: Any) -> str:
    """Exact latex when short; decimal via evalf when the exact form is a wall."""
    from sympy import latex, simplify

    val = simplify(expr)
    if getattr(val, "is_Float", False) and float(val).is_integer() and abs(float(val)) < 1e15:
        # ``x = 2``, not ``x = 2.0``: a decimal input that solves to a whole number.
        # A float this large is a rounded value (6.02e23 * 2), not an exact
        # integer; its binary digits would print as 1203999999999999857393664.
        from sympy import Integer

        val = Integer(int(val))
    tex = str(latex(val))
    # A derivative or antiderivative stays exact: ``0.434294 x`` is not ``x / ln 10``.
    if len(tex) <= _EXACT_LATEX_DECIMAL_THRESHOLD or getattr(val, "free_symbols", None):
        return tex
    whole = _exact_integer(val)
    if whole is not None:
        return str(whole)  # ∛(√5 + 2) - ∛(√5 - 2) is 1, not the decimal 1.0
    approximate = str(latex(val.evalf(6)))
    # ``evalf`` also converts harmless exact integer coefficients inside a
    # symbolic expression (``3`` -> ``3.0``).  Only use the approximation when
    # it actually makes a long exact result easier to read.
    return approximate if len(approximate) < len(tex) else tex


def _exact_integer(value: Any) -> int | None:
    """The integer a long exact number equals, proved by its minimal polynomial; tried only
    when it agrees with that integer to 20 digits."""
    from sympy import Dummy, minimal_polynomial
    from sympy.polys.polyerrors import BasePolynomialError

    try:
        approximate = complex(value.evalf(30, maxn=60))
    except (TypeError, ValueError, ArithmeticError):
        return None
    if not cmath.isfinite(approximate):
        return None  # 1e999 is past a float
    nearest = round(approximate.real)
    if abs(approximate - nearest) > 1e-20 * max(1, abs(nearest)):
        return None
    t = Dummy("t")
    try:
        return nearest if minimal_polynomial(value - nearest, t) == t else None
    except (BasePolynomialError, NotImplementedError, ArithmeticError):
        # Not algebraic (π, sin 4) or past SymPy's reach: the decimal stands.
        return None
