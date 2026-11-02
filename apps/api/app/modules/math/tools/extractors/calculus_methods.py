"""Single-variable calculus asked for by its method.

Implicit differentiation (``find dy/dx if x^2 + y^2 = 25``), the average value of a function
on an interval, and a linear approximation at a point. ``calculus.py`` runs these in its
registry order.
"""

from __future__ import annotations

import re

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.expr_rewrite import math_expr_or_none
from app.modules.math.tools.function_def import peel_function_definition
from app.modules.math.tools.request_text import strip_trailing_filler
from app.services.number_text import DECIMAL_LITERAL

# "find dy/dx if x^2 + y^2 = 25": an equation in x and y, so implicit, without the word.
_DY_DX_GIVEN = re.compile(
    r"\b(?:find|what\s+is|calculate|work\s+out)\s+dy\s*/\s*dx\s+(?:if|for|given|when)\s+"
    r"(?P<lhs>[^=]+)=(?P<rhs>[^=]+)$",
    re.IGNORECASE,
)


def _dy_dx_given_intent(cleaned: str) -> MathIntent | None:
    found = _DY_DX_GIVEN.search(cleaned.strip().rstrip("?.!"))
    if found is None:
        return None
    lhs = math_expr_or_none(found["lhs"].strip())
    rhs = math_expr_or_none(strip_trailing_filler(found["rhs"].strip()))
    if not lhs or not rhs or lhs.replace(" ", "") == "y":
        # "find dy/dx if y = x^2" is ordinary differentiation.
        return None
    if "y" not in (lhs + rhs).replace(" ", "").lower():
        return None
    return MathIntent(
        kind="calculus",
        operation="differentiate",
        school_op="implicit",
        lhs=lhs,
        rhs=rhs,
        expr=f"({lhs})-({rhs})",
        variable="x",
    )


def extract_implicit_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if "implicit" not in lower:
        return _dy_dx_given_intent(cleaned)
    # iOS autocorrect can expand the compact token ``dy`` to ``day`` in an
    # otherwise unambiguous "implicitly" request. Accept that scoped spelling
    # so algebra cannot append a solve-for-x footer to a derivative answer.
    if not any(cue in lower for cue in ("differentiate", "derivative", "dy/dx", "day/dx")):
        return None
    eq = cleaned.find("=")
    if eq <= 0:
        return None
    raw_lhs = cleaned[:eq]
    # Natural homework phrasing puts the requested derivative before the
    # equation: "Find dy/dx implicitly for x² + xy + y² = 7".
    implicit_for = lower.find("implicitly for ")
    if implicit_for != -1:
        raw_lhs = cleaned[implicit_for + len("implicitly for ") : eq]
    for cue in ("implicitly differentiate", "implicit differentiate", "implicit derivative of"):
        idx = lower.find(cue)
        if idx != -1:
            raw_lhs = cleaned[idx + len(cue) : eq]
            break
    lhs = math_expr_or_none(raw_lhs.strip())
    rhs = math_expr_or_none(strip_trailing_filler(cleaned[eq + 1 :].strip()))
    if not lhs or not rhs:
        return None
    return MathIntent(
        kind="calculus",
        operation="differentiate",
        school_op="implicit",
        lhs=lhs,
        rhs=rhs,
        expr=f"({lhs})-({rhs})",
        variable="x",
    )


_AVERAGE_ON = re.compile(
    r"\baverage\s+value\s+of\s+(?:the\s+function\s+)?(?P<expr>.+?)\s+"
    r"(?:on|over|in)\s*(?:the\s+interval\s*)?\[\s*(?P<lo>[^,\]]+?)\s*,\s*(?P<hi>[^\]]+?)\s*\]"
    r"|\baverage\s+value\s+of\s+(?:the\s+function\s+)?(?P<expr2>.+?)\s+between\s+"
    r"(?:x\s*=\s*)?(?P<lo2>\S+)\s+and\s+(?:x\s*=\s*)?(?P<hi2>[^\s,;?.]+)",
    re.IGNORECASE,
)


_AVERAGE_REQUEST = re.compile(
    r"(?:(?:find|what\s+is|what's|calculate|work\s+out|determine)\s+)?(?:the\s+)?"
    r"average\s+value\s+of\s+[^?]+?\s+(?:(?:on|over|in)\s*(?:the\s+interval\s*)?\[[^\]]+\]"
    r"|from\s+\S+\s+to\s+\S+|between\s+\S+\s+and\s+\S+)\s*[?.]?",
    re.IGNORECASE,
)


def average_value_request(text: str) -> bool:
    """The whole request is one average value, so its worked reply may stand alone."""
    return _AVERAGE_REQUEST.fullmatch(" ".join(text.split())) is not None


def extract_average_value_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if "average value" not in lower:
        return None
    # "on [0, 3]", "over [0, 3]", "between 0 and 3".
    bracketed = _AVERAGE_ON.search(cleaned)
    if bracketed is not None:
        raw = bracketed["expr"] or bracketed["expr2"]
        expr = math_expr_or_none(peel_function_definition(raw.strip()))
        lo = (bracketed["lo"] or bracketed["lo2"]).strip()
        hi = (bracketed["hi"] or bracketed["hi2"]).strip()
        if expr is None:
            return None
        return MathIntent(
            kind="calculus",
            operation="integrate",
            school_op="average_value",
            expr=expr,
            variable="x",
            integral_lower=lo,
            integral_upper=hi,
        )
    of_at = lower.find(" of ")
    from_at = lower.find(" from ")
    to_at = lower.find(" to ", from_at + 1) if from_at != -1 else -1
    if of_at == -1 or from_at == -1 or to_at == -1:
        return None
    # "average value of f(x) = x^2 from 0 to 3": the function, not its name.
    expr = math_expr_or_none(peel_function_definition(cleaned[of_at + 4 : from_at].strip()))
    lo = cleaned[from_at + 6 : to_at].strip()
    hi_part = cleaned[to_at + 4 :].strip()
    end = 0
    while end < len(hi_part) and not hi_part[end].isspace() and hi_part[end] not in ",;":
        end += 1
    hi = hi_part[:end].strip()
    if expr is None or not lo or not hi:
        return None
    return MathIntent(
        kind="calculus",
        operation="integrate",
        school_op="average_value",
        expr=expr,
        variable="x",
        integral_lower=lo,
        integral_upper=hi,
    )


def extract_linear_approx_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if "linear approximation" not in lower and "linearize" not in lower:
        return None
    of_at = lower.find(" of ")
    at_at = lower.find(" at ")
    if of_at == -1 or at_at == -1 or at_at < of_at:
        return None
    expr = math_expr_or_none(cleaned[of_at + 4 : at_at].strip())
    point_m = DECIMAL_LITERAL.search(cleaned, at_at)
    if expr is None or point_m is None:
        return None
    if DECIMAL_LITERAL.search(cleaned, point_m.end()) is not None:
        return None
    return MathIntent(
        kind="calculus",
        operation="simplify",
        school_op="linear_approx",
        expr=expr,
        variable="x",
        limit_point=point_m.group(0),
    )
