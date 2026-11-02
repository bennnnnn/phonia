"""Whether a rewrite's card only restates the root it was asked to take.

"Find the cube root of 27a^3 + 54a^2b + 36ab^2 + 8b^3." was read by a model as a
simplification of (27a^3 + …)^(1/3); SymPy left the root on the whole expression, and the
checked card was \\sqrt[3]{27 a^{3} + …}: the question itself (2026-11-01; right: 3a + 2b).
A card that is a root of the very sum it was given, the root not taken, answers nothing; a
root of one term (``cbrt(x^2)``) may well be the simplest form.

The card and the expression are compared as SymPy trees parsed as written, never as text,
so 1/(x - 1) is no part of (x+1)/(x-1) - x/(x-1). A card equal to an expression with no root
left on it is an answer: "simplify (x+1)/(x-1)" is already simplest, its excluded value
stated beside it, and so is "factor x^2 + 1". A number, one letter or an equation is never
a restatement.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from sympy import Rational

from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.latex_normalize import normalize_latex_to_sympy
from app.modules.math.solve.parse import parse_expression

# The operations that rewrite one value: their card should differ from what they were given.
REWRITES = frozenset({"simplify", "factor", "expand"})
_CARD_PIECES = re.compile(r",|;|\\quad")


def card_restates(card: str, expressions: Sequence[str | None]) -> bool:
    """Every piece of ``card`` is a root of one of ``expressions``, as written, not taken."""
    given = [_as_written(text) for text in expressions if text]
    bases = [_root_base(expr) or expr for expr in given if expr is not None]
    pieces = [piece for piece in _CARD_PIECES.split(card) if piece.strip()]
    return bool(bases and pieces) and all(_restates(piece, bases) for piece in pieces)


def _as_written(text: str) -> Any | None:
    with sympy_decline():
        return parse_expression(normalize_latex_to_sympy(text.replace("$", " ")), evaluate=False)
    return None


def _root_base(expr: Any) -> Any | None:
    """The radicand when ``expr`` is a root (a power 1/n), else None."""
    if not getattr(expr, "is_Pow", False):
        return None
    with sympy_decline():
        power = expr.exp.doit()
        if isinstance(power, Rational) and power.p == 1 and power.q > 1:
            return expr.base
    return None


def _restates(piece: str, bases: list[Any]) -> bool:
    if "=" in piece:
        return False
    card = _as_written(piece)
    if card is None or not getattr(card, "free_symbols", None):
        return False
    radicand = _root_base(card)
    # A root of a sum: of one term ("cbrt(x^2)") it may well be the simplest form. The sum
    # is the given one in any order of its terms (the card prints them in SymPy's).
    if radicand is None or not radicand.is_Add:
        return False
    with sympy_decline():
        given = radicand.doit()
        return any(given == base.doit() for base in bases)
    return False
