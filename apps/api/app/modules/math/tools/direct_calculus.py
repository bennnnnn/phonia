"""Whole-query guards for completed calculus answers; no solving here."""

from __future__ import annotations

import re

from app.modules.math.function_names import MATH_FUNCTION_NAMES
from app.modules.math.match import calc_op
from app.modules.math.schemas import MathIntent
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.tools.expr_rewrite import math_expr_or_none
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.request_text import _split_response_instruction_sentence
from app.services.number_text import bounded_decimal
from app.services.text_match import parens_balanced

_NUMBER = bounded_decimal(12)
# ``pi``, ``2pi``, ``pi/2`` and ``e`` are exact bounds, as common as numbers.
_CONSTANT_POINT = r"-?(?:[0-9]{1,3}\s*\*?\s*)?(?:pi|π)(?:\s*/\s*[0-9]{1,3})?|-?e"
_POINT = rf"(?:{_NUMBER}|-?(?:infinity|inf|oo)|{_CONSTANT_POINT})"
_INTEGER = r"[+-]?[0-9]{1,12}"
_WRT = re.compile(r"(.+) (?:with respect to|wrt) ([a-zA-Z])", re.IGNORECASE)
_AT_POINT = re.compile(rf"(.+) at ([a-zA-Z])\s*=\s*({_NUMBER})", re.IGNORECASE)
_INTEGRAL = re.compile(rf"(.+) from ({_POINT}) to ({_POINT})", re.IGNORECASE)
_INTEGRAL_BOUNDS_FIRST = re.compile(
    rf"(?:improper )?integral from ({_POINT}) to ({_POINT}) of (.+)", re.IGNORECASE
)
_UNICODE_INTEGRAL = re.compile(
    rf"∫\s*\[\s*({_POINT})\s*,\s*({_POINT})\s*\]\s*(.+?)(?:\s+d\s*([A-Za-z]))?",
    re.IGNORECASE,
)
_LEIBNIZ_DERIVATIVE = re.compile(
    r"d\^?(\d+)([a-zA-Z])/d([a-zA-Z])\^?(\d+)\s+(?:if\s+)?\2\s*=\s*(.+)",
    re.IGNORECASE,
)
_LIMIT = re.compile(
    rf"(.+) as ([a-zA-Z]) (?:approaches|goes to|tends to) ({_POINT})"
    r"(?: from (?:the )?(left|right))?",
    re.IGNORECASE,
)
_SUM = re.compile(
    rf"(.+) from ([a-zA-Z])\s*=\s*({_INTEGER}) to ({_INTEGER}|infinity|inf|oo)",
    re.IGNORECASE,
)
_TAYLOR = re.compile(rf"(.+) at ({_NUMBER}) (?:order|degree) ([0-9]{{1,3}})", re.IGNORECASE)
_MACLAURIN = re.compile(r"(.+) (?:order|degree) ([0-9]{1,3})", re.IGNORECASE)
_FUNCTIONS = MATH_FUNCTION_NAMES | {"pi"}
_ORDERS = {
    "derivative of ": 1,
    "first derivative of ": 1,
    "second derivative of ": 2,
    "2nd derivative of ": 2,
    "third derivative of ": 3,
    "3rd derivative of ": 3,
    "differentiate ": 1,
}


def _expression(raw: str) -> str | None:
    """Reject prose and qualifiers before the existing expression normalizer."""
    if not raw or any(
        not (char.isascii() and (char.isalnum() or char in " +-*/^().|")) for char in raw
    ):
        return None
    if not parens_balanced(raw):
        return None
    for word in re.findall(r"[A-Za-z]+", raw):
        if len(word) != 1 and word not in _FUNCTIONS:
            return None
    return math_expr_or_none(raw)


def _compact(value: str) -> str:
    return "".join(value.split()).replace("^", "**")


def _point(value: str | None) -> str | float | None:
    if value is None:
        return None
    if value.lower() in {"infinity", "inf", "oo", "-infinity", "-inf", "-oo"}:
        return "-oo" if value.startswith("-") else "oo"
    try:
        return float(value)
    except ValueError:
        pass
    if re.fullmatch(_CONSTANT_POINT, value.strip(), re.IGNORECASE) is None:
        return None
    from app.modules.math.solve.parse import parse_expression

    with sympy_decline():
        return float(parse_expression(value.replace("π", "pi"), []))
    return None


def _matches_expression(actual: MathIntent, raw: str) -> bool:
    expected = _expression(raw)
    return expected is not None and _compact(actual.expr or "") == _compact(expected)


def _variable(expr: str, explicit: str | None) -> str:
    from app.modules.math.solve import guess_variables

    if explicit is not None:
        return explicit
    variables = guess_variables(expr)
    return variables[0] if len(variables) == 1 else "x"


def calculus_direct_request(text: str, *, answer: str | None = None) -> bool | None:
    """None is another family; False blocks partial asks from generic fallback.

    The complete expression and every operation parameter must agree with the
    existing extractor. Domains, evaluation points, and extra asks cannot be
    dropped through its trailing-clause cleanup.
    """
    if len(text) > 1000:
        return False
    request = " ".join(text.split()).replace("\u2212", "-")
    lower = request.lower()
    recognized = calc_op(request) in {
        "differentiate",
        "derivative",
        "integrate",
        "integral",
        "partial",
        "taylor",
    }
    recognized = recognized or any(
        word in lower.split() for word in ("limit", "sum", "series", "maclaurin")
    )
    recognized = recognized or bool(re.search(r"\bd\^?\d+[a-zA-Z]/d[a-zA-Z]\^?\d+\b", request))
    if not recognized:
        return None
    # The extractor already distinguishes the calculation from a trailing
    # presentation request ("Show the substitution", "State the domain").
    # Apply the same boundary to the strict whole-query guard. Without this,
    # a complete verified worked solution was discarded solely because the
    # learner explicitly asked to see its working.
    request = _split_response_instruction_sentence(request).rstrip(".?").rstrip()
    if request.lower().startswith("please "):
        request = request[7:]
    for prefix in (
        "find ",
        "calculate ",
        "compute ",
        "evaluate ",
        "determine ",
        "what is ",
        "what's ",
    ):
        if request.lower().startswith(prefix):
            request = request[len(prefix) :]
            break
    if request.lower().startswith("the "):
        request = request[4:]
    actual = extract_math_intent(text)
    if actual is None:
        # The math extractor declined the complete request, so the direct
        # renderer must not reinterpret only a calculus-looking fragment.
        return False
    if actual.operation == "dsolve":
        return None
    lower = request.lower()
    unicode_integral = _UNICODE_INTEGRAL.fullmatch(request)
    if unicode_integral:
        low, high, expr, explicit_variable = unicode_integral.groups()
        variable = explicit_variable or _variable(expr, None)
        return bool(
            actual.kind == "calculus"
            and actual.operation == "integrate"
            and _matches_expression(actual, expr)
            and actual.variable == variable
            and _point(actual.integral_lower) == _point(low)
            and _point(actual.integral_upper) == _point(high)
        )
    for prefix, order in _ORDERS.items():
        if not lower.startswith(prefix):
            continue
        expr = request[len(prefix) :]
        assignment = re.fullmatch(r"[a-zA-Z]\s*=\s*(.+)", expr)
        if assignment:
            expr = assignment[1]
        wrt = _WRT.fullmatch(expr)
        expr, variable = (wrt[1], wrt[2]) if wrt else (expr, None)
        at_point = _AT_POINT.fullmatch(expr)
        point: str | None = None
        if at_point:
            expr, variable, point = at_point[1], at_point[2], at_point[3]
        return (
            actual.kind == "calculus"
            and actual.operation == "differentiate"
            and actual.derivative_order == order
            and _matches_expression(actual, expr)
            and actual.variable == _variable(expr, variable)
            and (
                (point is None and actual.evaluation_point is None)
                or (
                    point is not None
                    and actual.evaluation_point is not None
                    and _point(point) == _point(actual.evaluation_point)
                )
            )
        )
    if lower.startswith("partial derivative of "):
        match = _WRT.fullmatch(request[len("partial derivative of ") :])
        return bool(
            match
            and actual.kind == "calculus"
            and actual.operation == "partial"
            and actual.variable == match[2]
            and _matches_expression(actual, match[1])
        )
    leibniz = _LEIBNIZ_DERIVATIVE.fullmatch(request)
    if leibniz:
        order = int(leibniz[1])
        return bool(
            order == int(leibniz[4])
            and actual.kind == "calculus"
            and actual.operation == "differentiate"
            and actual.derivative_order == order
            and actual.variable == leibniz[3]
            and _matches_expression(actual, leibniz[5])
        )
    for prefix in (
        "integrate ",
        "integral of ",
        "definite integral of ",
        "indefinite integral of ",
    ):
        if not lower.startswith(prefix):
            continue
        expr = request[len(prefix) :]
        bounds = _INTEGRAL.fullmatch(expr)
        if bounds:
            expr, low, high = bounds[1], bounds[2], bounds[3]
        else:
            low = high = None
        if (prefix == "definite integral of " and bounds is None) or (
            prefix == "indefinite integral of " and bounds is not None
        ):
            return False
        if answer is not None and r"\infty" in answer:
            return False
        wrt = _WRT.fullmatch(expr)
        expr, variable = (wrt[1], wrt[2]) if wrt else (expr, None)
        differential = re.fullmatch(r"(.+) d\s*([a-zA-Z])", expr)
        if differential:
            if variable is not None:
                return False
            expr, variable = differential[1], differential[2]
        return (
            actual.kind == "calculus"
            and actual.operation == "integrate"
            and _matches_expression(actual, expr)
            and actual.variable == _variable(expr, variable)
            and (
                actual.integral_lower is None
                if low is None
                else _point(actual.integral_lower) == _point(low)
            )
            and (
                actual.integral_upper is None
                if high is None
                else _point(actual.integral_upper) == _point(high)
            )
        )
    bounds_first = _INTEGRAL_BOUNDS_FIRST.fullmatch(request)
    if bounds_first:
        low, high, expr = bounds_first[1], bounds_first[2], bounds_first[3]
        differential = re.fullmatch(r"(.+) d\s*([a-zA-Z])", expr)
        variable = None
        if differential:
            expr, variable = differential[1], differential[2]
        return bool(
            actual.kind == "calculus"
            and actual.operation == "integrate"
            and _matches_expression(actual, expr)
            and actual.variable == _variable(expr, variable)
            and _point(actual.integral_lower) == _point(low)
            and _point(actual.integral_upper) == _point(high)
        )
    if lower.startswith("limit of "):
        match = _LIMIT.fullmatch(request[len("limit of ") :])
        return bool(
            match
            and actual.kind == "limit"
            and _matches_expression(actual, match[1])
            and actual.variable == match[2]
            and _point(actual.limit_point) == _point(match[3])
            and actual.limit_direction
            == {"left": "-", "right": "+", None: "+-"}[match[4].lower() if match[4] else None]
        )
    for prefix in ("sum of ", "sum "):
        if not lower.startswith(prefix):
            continue
        match = _SUM.fullmatch(request[len(prefix) :])
        # Infinite limits have a value in the extended reals, but an infinite
        # series answer needs its divergence explained rather than a bare sum.
        if answer is not None and r"\infty" in answer:
            return False
        return bool(
            match
            and actual.kind == "series"
            and _matches_expression(actual, match[1])
            and actual.variable == match[2]
            and _point(actual.series_start) == _point(match[3])
            and _point(actual.series_end) == _point(match[4])
        )
    for prefix, pattern in (("taylor series of ", _TAYLOR), ("maclaurin series of ", _MACLAURIN)):
        if not lower.startswith(prefix):
            continue
        match = pattern.fullmatch(request[len(prefix) :])
        if match is None:
            return False
        center, taylor_order = (
            (match[2], match[3]) if prefix.startswith("taylor") else ("0", match[2])
        )
        return (
            actual.kind == "calculus"
            and actual.operation == "taylor"
            and actual.variable == "x"
            and _matches_expression(actual, match[1])
            and _point(actual.limit_point) == _point(center)
            and actual.taylor_n == int(taylor_order)
        )
    return False
