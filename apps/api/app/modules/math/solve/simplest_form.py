"""The form a "simplify" answer certifies: the one a school book prints.

SymPy's ``simplify`` keeps the form with the fewest operations, and on a tie or under
the principal complex branch that is not the book's: ``∛(162x⁵)/∛(3x²)`` stayed
``3∛2·∛(x⁵)/|x^(2/3)|``, ``(x-1)/(x³-1)`` was left uncancelled and ``x³ + x²`` came back
factored. Three rules, each one for every expression of its kind:

- An odd root of a real number is the real root (``∛(-8) = -2``). The radicals are
  combined as if every letter were positive, and that form is kept only when it equals
  the expression for every real value of its letters (``real_reading.agrees_on_reals``);
  otherwise SymPy's own form stands.
- A rational expression is in lowest terms: no factor is left common to the numerator
  and the denominator.
- A sum of polynomial terms with like terms or brackets is its collected terms, as long as
  collecting them is no longer than what was written: ``(x+1)² - 1`` is ``x² + 2x``, while
  ``(x+1)¹⁰ - 1``, a sum already collected and a product the student wrote keep SymPy's
  form.

Length alone does not decide: ``1/x + 1/(x+1)`` as one fraction is longer, and it is the
book's answer.
"""

from __future__ import annotations

from typing import Any

from sympy import (
    Dummy,
    Expr,
    cancel,
    count_ops,
    expand,
    factor,
    fraction,
    gcd,
    latex,
    simplify,
    together,
)

from app.modules.math.solve.complex_form import a_plus_bi
from app.modules.math.solve.radical_form import book_radicals_latex, has_radical
from app.modules.math.solve.real_reading import agrees_on_reals, real_odd_roots


def simplest_form(parsed: Any) -> tuple[Any, str | None]:
    """SymPy's simplification in the book's form, and its LaTeX when a rule here changed it.

    The usual display pass simplifies again, which would undo the book's form, so a
    changed result carries its own LaTeX."""
    result = simplify(parsed)
    if not isinstance(parsed, Expr) or not isinstance(result, Expr):
        return result, None
    chosen = _real_root_form(parsed, result)
    chosen = _lowest_terms(chosen)
    chosen = _collected_polynomial(parsed, chosen)
    radicals = book_radicals_latex(chosen) if has_radical(parsed) else None
    if radicals is not None:
        return chosen, radicals
    complex_number = a_plus_bi(chosen)  # ∛(-8) + √(-9) is -2 + 3i, real part first
    if complex_number is not None:
        return chosen, complex_number
    return chosen, (None if chosen == result else latex(chosen))


def _real_root_form(parsed: Expr, result: Expr) -> Expr:
    if not has_radical(parsed):
        return result
    symbols = sorted(parsed.free_symbols, key=str)
    positive = {symbol: Dummy(str(symbol), positive=True) for symbol in symbols}
    back = {dummy: symbol for symbol, dummy in positive.items()}
    candidate = simplify(real_odd_roots(parsed).subs(positive)).subs(back)
    if not symbols:
        # A number: the real odd root is its value (∛(-8) + √(-9) = -2 + 3i), even when
        # SymPy's principal root prints shorter (∛(1 - √2) is -∛(√2 - 1), not complex).
        return candidate
    if count_ops(candidate) > count_ops(result) or candidate == result:
        return result
    return candidate if agrees_on_reals(parsed, candidate) else result


def _lowest_terms(expr: Expr) -> Expr:
    symbols = sorted(expr.free_symbols, key=str)
    if not symbols or not expr.is_rational_function(*symbols):
        return expr
    numerator, denominator = fraction(together(expr))
    if not (gcd(numerator, denominator).free_symbols & set(symbols)):
        return expr
    lowest = cancel(expr)
    return min((factor(lowest), lowest), key=count_ops)


def _collected_polynomial(parsed: Expr, chosen: Expr) -> Expr:
    symbols = sorted(parsed.free_symbols, key=str)
    if not symbols or not parsed.is_Add or not parsed.is_polynomial(*symbols):
        return chosen
    collected = expand(parsed)
    if collected == parsed:
        return chosen  # nothing to collect: x³ + x² or i²R + i²r keep SymPy's form
    return collected if count_ops(collected) <= count_ops(parsed) else chosen
