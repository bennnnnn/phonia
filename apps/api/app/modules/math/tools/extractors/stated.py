"""Equations that only state something, so there is nothing to solve.

``x = 6`` states a value and ``Ka = 1.8e-5`` names a constant: solving either
certifies what was typed. ``x = 2πk + π/6 or x = 2πk + 5π/6`` lists answers, and
solved together as a system they have no solution at all.
"""

from __future__ import annotations

import re

from app.services.number_text import FRACTION_OR_DECIMAL, SIGNED_DECIMAL_SCI

_LONE_LETTER = re.compile(r"\s*[A-Za-z]\s*")
_PLAIN_NUMBER = re.compile(rf"\s*(?:\u2212\s*)?(?:{FRACTION_OR_DECIMAL}|{SIGNED_DECIMAL_SCI})\s*")
# ``Ka``, ``pH``, ``Ksp``: a named constant is one quantity, not ``K`` times ``a``.
_NAMED_CONSTANT = re.compile(r"\s*(?:[A-Z][a-z]{1,2}|p[A-Z][a-z]?|p[A-Z]{1,2})\s*")
_OR = re.compile(r"\bor\b", re.IGNORECASE)


def already_solved(lhs: str, rhs: str) -> bool:
    """``x = 6`` (or ``6 = x``) states a value; solving it certifies the claim.

    A student's own answer typed back must be checked against the problem it
    answers, never "verified" by solving it again.
    """
    return bool(
        (_LONE_LETTER.fullmatch(lhs) and _PLAIN_NUMBER.fullmatch(rhs))
        or (_LONE_LETTER.fullmatch(rhs) and _PLAIN_NUMBER.fullmatch(lhs))
    )


def names_a_constant(lhs: str, rhs: str) -> bool:
    return bool(_NAMED_CONSTANT.fullmatch(lhs) or _NAMED_CONSTANT.fullmatch(rhs))


def lists_alternatives(text: str) -> bool:
    """Equations joined by "or" are answers to choose from, never a system.

    The "or" sits between two equals signs: ``x = 1 or x = 2``, not "solve it or explain".
    """
    first, last = text.find("="), text.rfind("=")
    return first != last and _OR.search(text, first, last) is not None


def one_of_several_answers(lhs: str, pairs: list[tuple[str, str]]) -> bool:
    """``x = 2πk + π/6, x = 2πk + 5π/6``: solving one answer drops the others."""
    return bool(_LONE_LETTER.fullmatch(lhs)) and sum(o.strip() == lhs.strip() for o, _ in pairs) > 1
