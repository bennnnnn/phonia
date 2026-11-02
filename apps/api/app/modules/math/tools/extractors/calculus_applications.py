"""Intent extraction for area between curves, arc length, and volume.

Strict on purpose. These questions were refused outright at the funnel after an
area question was answered with its curves' *intersection points*; a partial
parse here would reopen exactly that hole, because a verified block tells the
model not to recompute. Every operand — both curves, both bounds, the axis —
has to be explicit or the request falls through unclaimed.
"""

from __future__ import annotations

import re

from app.modules.math.schemas import MathIntent
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.tools.expr_rewrite import _normalize_latex_expr, math_expr_or_none
from app.modules.math.tools.function_def import peel_function_definition
from app.modules.math.tools.request_text import strip_trailing_filler

# A bound may be a number, a fraction, pi, or e — the values school questions
# actually use. Anything else is left unclaimed rather than guessed at.
# Ordered longest-first, and closed with a lookahead, because a *partial* bound
# match silently shortens the interval instead of failing. "from 0 to 2*pi"
# matched just the "2" and answered the area on [0, 2] as though it were the
# area on [0, 2*pi] - a wrong number that looks entirely plausible.
_BOUND = (
    r"[-+]?(?:"
    r"\d+(?:\.\d+)?\s*\*\s*(?:pi|π|e)"
    r"|\d+(?:\.\d+)?\s*(?:pi|π)"
    r"|(?:pi|π|e)\s*/\s*\d+(?:\.\d+)?"
    r"|\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?"
    r"|pi|π|e"
    r"|\d+(?:\.\d+)?|\.\d+"
    # Reject a partial decimal (``3`` from ``3.5``), but allow the ordinary
    # sentence-ending period after a complete bound (``to x=3.``).
    r")(?![\w*]|\.\d)"
)
_FROM_TO_RE = re.compile(
    rf"\bfrom\s+(?:x\s*=\s*)?({_BOUND})\s+to\s+(?:x\s*=\s*)?({_BOUND})\b", re.IGNORECASE
)
_ON_INTERVAL_RE = re.compile(
    rf"\b(?:on|over)\s*\[\s*({_BOUND})\s*,\s*({_BOUND})\s*\]", re.IGNORECASE
)
_BETWEEN_BOUNDS_RE = re.compile(
    rf"\bbetween\s+x\s*=\s*({_BOUND})\s+and\s+x\s*=\s*({_BOUND})\b", re.IGNORECASE
)
_CHAIN_BOUNDS_RE = re.compile(
    rf"({_BOUND})\s*(?:<=|≤|<)\s*x\s*(?:<=|≤|<)\s*({_BOUND})", re.IGNORECASE
)


def _clean(raw: str) -> str | None:
    text = peel_function_definition(strip_trailing_filler(raw.strip(" ,;")))
    while text and text[-1] in ".?!":
        text = text[:-1].rstrip()
    return math_expr_or_none(_normalize_latex_expr(text))


def _bounds(cleaned: str) -> tuple[str, str, int] | None:
    for pattern in (_FROM_TO_RE, _ON_INTERVAL_RE, _BETWEEN_BOUNDS_RE, _CHAIN_BOUNDS_RE):
        match = pattern.search(cleaned)
        if match is not None:
            return (
                match.group(1).replace("π", "pi"),
                match.group(2).replace("π", "pi"),
                match.start(),
            )
    return None


_AREA_BETWEEN_RE = re.compile(
    r"\barea\s+(?:between|enclosed\s+(?:by|between)|bounded\s+by)\s+", re.IGNORECASE
)


def _extract_area_between_intent(cleaned: str) -> MathIntent | None:
    lead = _AREA_BETWEEN_RE.search(cleaned)
    if lead is None:
        return None
    interval = _bounds(cleaned)
    if interval is not None and interval[2] <= lead.start():
        return None
    end = interval[2] if interval is not None else len(cleaned)
    body = cleaned[lead.end() : end].strip(" ,;.?!")
    body = re.sub(r"^(?:the\s+)?curves\s+", "", body, flags=re.IGNORECASE)
    halves = re.split(r"\s*,?\s+and\s+", body, maxsplit=1, flags=re.IGNORECASE)
    if len(halves) != 2:
        return None
    first = _clean(halves[0])
    second = (
        "0"
        if re.fullmatch(r"(?:the\s+)?x[- ]axis", halves[1].strip(), re.I)
        else (_clean(halves[1]))
    )
    if first is None or second is None:
        return None
    if interval is None:
        # No interval stated: the region the curves enclose runs between where they meet.
        meeting = _meeting_points(first, second)
        if meeting is None:
            return None
        low, high = meeting
    else:
        low, high, _ = interval
    return MathIntent(
        kind="calculus",
        operation="solve",
        school_op="area_between_curves",
        expr=first,
        expr2=second,
        variable="x",
        integral_lower=low,
        integral_upper=high,
        trial_outcome="meeting points" if interval is None else None,
    )


def _meeting_points(first: str, second: str) -> tuple[str, str] | None:
    """The outermost real crossings, when the curves cross at two or more points.

    One crossing (y = x and y = 2x) or infinitely many (y = sin x and y = 0)
    encloses no single region, so the question stays unclaimed.
    """
    from sympy import Eq, FiniteSet, S, Symbol, solveset, sstr

    from app.modules.math import solve as math_solve

    x = Symbol("x", real=True)
    with sympy_decline() as declined:
        f = math_solve.parse_expression(first, ["x"], real=True)
        g = math_solve.parse_expression(second, ["x"], real=True)
        roots = solveset(Eq(f, g), x, domain=S.Reals)
    if declined:
        return None
    if not isinstance(roots, FiniteSet):
        return None
    real = sorted((root for root in roots if root.is_real), key=lambda root: float(root))
    if len(real) < 2:
        return None
    return sstr(real[0]), sstr(real[-1])


_AREA_UNDER_RE = re.compile(
    r"\barea\s+(?:under|below|beneath)\s+(?:the\s+(?:curve|graph)\s+(?:of\s+)?)?"
    r"|\barea\s+(?:bounded|enclosed)\s+by\s+(?:the\s+(?:curve|graph)\s+(?:of\s+)?)?",
    re.IGNORECASE,
)
_X_AXIS_RE = re.compile(r",?\s*(?:and\s+)?the\s+x[- ]axis\b,?", re.IGNORECASE)


def _extract_area_under_intent(cleaned: str) -> MathIntent | None:
    """``area under y = x^2 between x = 1 and x = 2``: the area between the curve and y = 0.

    The area-between solver already takes the curve's absolute value, so a
    stretch below the x-axis counts as area, not as a negative.
    """
    lead = _AREA_UNDER_RE.search(cleaned)
    if lead is None:
        return None
    interval = _bounds(cleaned)
    if interval is None:
        return None
    low, high, bounds_at = interval
    if bounds_at <= lead.end():
        return None
    body = _X_AXIS_RE.sub("", cleaned[lead.end() : bounds_at]).strip(" ,;")
    curve = _clean(body)
    if curve is None or "=" in curve:
        return None
    return MathIntent(
        kind="calculus",
        operation="solve",
        school_op="area_between_curves",
        expr=curve,
        expr2="0",
        variable="x",
        integral_lower=low,
        integral_upper=high,
    )


def _extract_arc_length_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    at = lower.find("arc length")
    if at == -1:
        return None
    interval = _bounds(cleaned)
    if interval is None:
        return None
    low, high, bounds_at = interval
    if bounds_at <= at:
        return None

    body = cleaned[at + len("arc length") : bounds_at].strip(" ,;")
    body = re.sub(r"^of\s+", "", body, flags=re.IGNORECASE)
    expr = _clean(body)
    if expr is None:
        return None
    return MathIntent(
        kind="calculus",
        operation="solve",
        school_op="arc_length",
        expr=expr,
        variable="x",
        integral_lower=low,
        integral_upper=high,
    )


_REVOLVE_RE = re.compile(r"\b(?:revolution|revolved|rotated|revolving|rotating)\b", re.IGNORECASE)


def _extract_volume_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if "volume" not in lower or _REVOLVE_RE.search(cleaned) is None:
        return None
    interval = _bounds(cleaned)
    if interval is None:
        return None
    low, high, bounds_at = interval

    # The axis decides the formula — disks about x, shells about y — so an
    # unnamed axis is refused rather than assumed to be x.
    if re.search(r"\bx[- ]axis\b", lower):
        axis = "x"
    elif re.search(r"\by[- ]axis\b", lower):
        axis = "y"
    else:
        return None

    start = lower.find("of ", lower.find("volume"))
    offset = 3
    if start == -1:
        start = lower.find("when ", lower.find("volume"))
        offset = len("when ")
    if start == -1 or start >= bounds_at:
        return None
    body = cleaned[start + offset : bounds_at].strip(" ,;")
    body = re.sub(
        r"^(?:revolution|the\s+region)\s+(?:of|under|bounded\s+by)\s+",
        "",
        body,
        flags=re.IGNORECASE,
    )
    expr = _clean(body)
    if expr is None:
        return None
    return MathIntent(
        kind="calculus",
        operation="solve",
        school_op=f"volume_revolution_{axis}",
        expr=expr,
        variable="x",
        integral_lower=low,
        integral_upper=high,
    )


def _extract_curve_point_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math.tools.school.curve_points import extract_curve_point_intent

    return extract_curve_point_intent(cleaned)


CALCULUS_APPLICATION_EXTRACTORS = (
    # Tangent/normal lines and stationary points: read as algebra, the curve
    # and the point became a system to solve.
    _extract_curve_point_intent,
    _extract_area_between_intent,
    _extract_area_under_intent,
    _extract_arc_length_intent,
    _extract_volume_intent,
)
