"""A captured expression rewritten for SymPy: LaTeX, ``dx``, English powers, and the guard."""

from __future__ import annotations

import re
from string import ascii_letters

from app.modules.math.match.letter_runs import looks_like_math_expr
from app.modules.math.tools.request_text import _MAX_MATH_INPUT, _strip_expr_leadins
from app.services.text_normalize import collapse_ws


def _normalize_latex_expr(expr: str) -> str:
    """Delegate to math_solve so limit/series paths share frac/abs handling."""
    from app.modules.math.solve import normalize_latex_to_sympy

    return normalize_latex_to_sympy(expr)


def _strip_trailing_differential(expr: str) -> str:
    """Peel ``dx`` / ``d x`` so implicit multiplication does not eat the integrand."""
    s = collapse_ws(expr)
    if len(s) > _MAX_MATH_INPUT:
        s = s[:_MAX_MATH_INPUT]
    lower = s.lower()
    for token in (f" d{space}{var}" for var in ascii_letters for space in ("", " ")):
        if lower.endswith(token):
            return s[: -len(token)].rstrip()
        marker = token + " from "
        idx = lower.find(marker)
        if idx != -1:
            return (s[:idx] + s[idx + len(token) :]).rstrip()
    return s


_ENGLISH_POWERS: tuple[tuple[str, str], ...] = (
    ("squared", "^2"),
    ("cubed", "^3"),
)


def _single_letter_or_digit_before(text: str, idx: int) -> bool:
    """True when ``text[idx]`` follows a 1-letter variable, a digit, or ``)``.

    ``area squared`` must not become ``are^2``; ``x squared`` / ``3 squared``
    / ``) squared`` should.
    """
    if idx <= 0:
        return False
    ch = text[idx - 1]
    if ch in ")]":
        return True
    if ch.isdigit():
        return True
    if not ch.isalpha():
        return False
    return idx < 2 or not text[idx - 2].isalpha()


def rewrite_english_powers(expr: str) -> str:
    """``x squared`` → ``x^2``. Leaves ``square root`` / ``draw a square`` alone."""
    if len(expr) > _MAX_MATH_INPUT:
        expr = expr[:_MAX_MATH_INPUT]
    lower = expr.lower()
    out: list[str] = []
    i = 0
    n = len(expr)
    while i < n:
        matched = False
        if _single_letter_or_digit_before(expr, i):
            j = i
            while j < n and expr[j].isspace():
                j += 1
            rest = lower[j:]
            for word, repl in _ENGLISH_POWERS:
                if not rest.startswith(word):
                    continue
                end = j + len(word)
                if end < n and lower[end].isalpha():
                    continue
                out.append(repl)
                i = end
                matched = True
                break
        if not matched:
            out.append(expr[i])
            i += 1
    return "".join(out)


# "simplify it": a pronoun, not the product ``i t``.
_PRONOUN_EXPR = re.compile(r"^\s*(?:it|its|it's)\s*(?:[.?!]+\s*)?", re.IGNORECASE)


def math_expr_or_none(expr: str) -> str | None:
    """Return ``expr`` only when it looks like math, not leftover English."""
    stripped = rewrite_english_powers(_strip_expr_leadins(expr))
    if not looks_like_math_expr(stripped) or _PRONOUN_EXPR.fullmatch(stripped):
        return None
    return stripped
