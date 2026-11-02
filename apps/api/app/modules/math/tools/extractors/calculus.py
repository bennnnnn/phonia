"""Calculus intent extractors."""

from __future__ import annotations

import re
from typing import Literal

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.expr_rewrite import (
    _normalize_latex_expr,
    _strip_trailing_differential,
    math_expr_or_none,
)
from app.modules.math.tools.extractors.calculus_methods import (
    extract_average_value_intent,
    extract_implicit_intent,
    extract_linear_approx_intent,
)
from app.modules.math.tools.extractors.multivariable import (
    extract_directional_intent,
    extract_div_curl_intent,
    extract_double_integral_intent,
    extract_gradient_intent,
    extract_triple_integral_intent,
)
from app.modules.math.tools.function_def import peel_function_definition
from app.modules.math.tools.request_text import (
    _calc_expr_tail,
    _strip_series_prefix,
    strip_trailing_filler,
)

_WRT_VARIABLE = re.compile(r"\b(?:with\s+respect\s+to|wrt)\s+([a-zA-Z])\b", re.IGNORECASE)
_LEIBNIZ_VARIABLE = re.compile(r"/\s*d\s*([a-zA-Z])\b")
_INTEGRAL_VARIABLE = re.compile(r"\bd\s*([a-zA-Z])(?=\s+from\b|\s*$)")
_HIGHER_LEIBNIZ = re.compile(
    r"\bd\s*(?:\^\s*([2-4])|([²³⁴]))\s*[a-zA-Z]\s*/\s*"
    r"d\s*([a-zA-Z])\s*(?:\^\s*[2-4]|[²³⁴])",
    re.IGNORECASE,
)
_DERIVATIVE_AT_POINT = re.compile(
    r"\s+at\s+([a-zA-Z])\s*=\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*$",
    re.IGNORECASE,
)
# ``f'(3)``: a derivative asked at a number, in Lagrange's notation.
_PRIME_AT_NUMBER = re.compile(
    r"(?<![A-Za-z])[a-zA-Z]'{1,3}\(\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*\)"
)
_BY_PARTS = re.compile(
    r"^\s*(?:by|using)\s+(?:integration\s+by\s+)?parts\s+"
    r"|\s*,?\s+(?:by|using)\s+(?:integration\s+by\s+)?parts\s*[.?!]?\s*$",
    re.IGNORECASE,
)
_UNICODE_SIGMA_EXPR = re.compile(
    r"Σ\s*(.+?)(?=\s+(?:converges?|diverges?)\b|[?;]|$)",
    re.IGNORECASE,
)


def _calculus_variable(cleaned: str, raw: str, expr: str, *, integrate: bool) -> str:
    from app.modules.math.solve import guess_variables

    explicit = _WRT_VARIABLE.search(cleaned) or _LEIBNIZ_VARIABLE.search(cleaned)
    if explicit is not None:
        return explicit.group(1)
    if integrate:
        differential = _INTEGRAL_VARIABLE.search(raw)
        if differential is not None:
            return differential.group(1)
    variables = guess_variables(expr)
    return variables[0] if len(variables) == 1 else "x"


def _split_find_clause(s: str) -> str:
    """``f(x) = x^3 - 3x, find f''(x)`` → the definition before ``, find``."""
    lower = s.lower()
    cut: int | None = None
    for token in (", find ", ", what is ", ", what's "):
        idx = lower.find(token)
        if idx != -1 and (cut is None or idx < cut):
            cut = idx
    return s[:cut] if cut is not None else s


def _derivative_order(cleaned: str) -> int:
    """1-3 from Lagrange primes, then phrasing. Linear scans — no regex."""
    from app.modules.math.match.calculus import lagrange_prime_order

    primes = lagrange_prime_order(cleaned)
    if primes:
        return primes
    low = cleaned.lower()
    for phrase, order in (
        ("third derivative", 3),
        ("3rd derivative", 3),
        ("second derivative", 2),
        ("2nd derivative", 2),
    ):
        if phrase in low:
            return order
    compact = low.replace(" ", "")
    if "d^3" in compact or "d³" in compact:
        return 3
    if "d^2" in compact or "d²" in compact:
        return 2
    return 1


def _extract_critical_points_intent(cleaned: str) -> MathIntent | None:
    """Intercept extrema asks so they cannot fall through to a fake equation solve."""
    low = cleaned.lower()
    if (
        "critical point" not in low
        and "extrema" not in low
        and "local max" not in low
        and "local min" not in low
    ):
        return None
    from app.modules.math import solve as math_solve

    expr: str | None = None
    pairs = math_solve.try_extract_equations_from_text(cleaned)
    if pairs:
        _lhs, rhs = pairs[0]
        expr = math_expr_or_none(rhs)
    if expr is None:
        of_at = low.find(" of ")
        if of_at != -1:
            expr = math_expr_or_none(strip_trailing_filler(cleaned[of_at + 4 :]))
    return MathIntent(
        kind="calculus",
        expr=expr or "",
        operation="critical_points",
        variable="x",
    )


_IDENTITY_CUES = ("show that", "prove that", "verify that", "always true")
_EXPLICIT_IDENTITY_CUE = re.compile(
    r"\b(?:an|the)\s+identity\b|\bidentity\s*:|"
    r"\b(?:prove|verify|show|check)\s+(?:the\s+)?identity\b",
    re.IGNORECASE,
)
_IDENTITY_SKIP_OPS = {
    "factor",
    "expand",
    "differentiate",
    "derivative",
    "integrate",
    "integral",
    "dsolve",
}


def _extract_identity_intent(cleaned: str) -> MathIntent | None:
    """Certify an identity equality. Must run before algebra solves for x."""
    from app.modules.math import match as mtm

    lower = cleaned.lower()
    # A bare mention is often a response-format instruction ("name the law or
    # identity you use"), not a request to prove the equation itself. Require
    # proposition wording such as "an identity", "identity:", or a proof cue.
    has_cue = bool(_EXPLICIT_IDENTITY_CUE.search(cleaned)) or any(
        cue in lower for cue in _IDENTITY_CUES
    )
    if not has_cue or not mtm.has_equation(cleaned):
        return None
    op_word = mtm.calc_op(cleaned)
    if op_word in _IDENTITY_SKIP_OPS:
        return None
    if "induction" in lower or "contradiction" in lower:
        return MathIntent(
            kind="calculus",
            operation="simplify",
            school_op="identity",
            lhs="",
            rhs="",
            expr="",
            variable="x",
        )
    if lower.startswith("is "):
        cleaned = cleaned[3:].lstrip()
        lower = cleaned.lower()
    eq = cleaned.find("=")
    if eq <= 0:
        return None
    lhs_raw = cleaned[:eq]
    rhs_raw = cleaned[eq + 1 :]
    rhs_lower = rhs_raw.lower().rstrip(" .?!")
    for suffix in (" always true", " true for all real numbers", " true for all real x"):
        if rhs_lower.endswith(suffix):
            rhs_raw = rhs_raw[: len(rhs_lower) - len(suffix)]
            break
    lhs_low = lhs_raw.lower()
    for cue in (*_IDENTITY_CUES, "the identity", "identity"):
        idx = lhs_low.find(cue)
        if idx != -1:
            lhs_raw = lhs_raw[idx + len(cue) :]
            break
    lhs = math_expr_or_none(_normalize_latex_expr(strip_trailing_filler(lhs_raw)))
    rhs = math_expr_or_none(_normalize_latex_expr(strip_trailing_filler(rhs_raw)))
    return MathIntent(
        kind="calculus",
        operation="simplify",
        school_op="identity",
        lhs=lhs or "",
        rhs=rhs or "",
        expr=f"({lhs or '0'})-({rhs or '0'})",
        variable="x",
    )


# ``∫_0^π`` / ``∫_{0}^{2}``: one bound each, a number, π, e or infinity.
_SCRIPT_BOUND = r"-?(?:\d+(?:\.\d+)?|π|pi|e|∞|oo|infinity)"
_INTEGRAL_SCRIPTS = re.compile(
    rf"_\s*(?:\{{\s*(?P<low_braced>{_SCRIPT_BOUND})\s*\}}|(?P<low>{_SCRIPT_BOUND}))\s*"
    rf"\^\s*(?:\{{\s*(?P<high_braced>{_SCRIPT_BOUND})\s*\}}|(?P<high>{_SCRIPT_BOUND}))"
    r"(?![\w.])",
    re.IGNORECASE,
)


def _script_bound(match: re.Match[str], name: str) -> str:
    bound = match.group(f"{name}_braced") or match.group(name)
    return bound.replace("π", "pi").replace("∞", "oo")


def _leading_integral_bounds(cleaned: str) -> tuple[str, str, str] | None:
    """``integral from 1 to infinity of f(x) dx`` -> expression and bounds."""
    lower = cleaned.lower()
    integral_at = cleaned.find("∫")
    if integral_at != -1:
        rest = cleaned[integral_at + 1 :].strip()
        if rest.startswith("["):
            close = rest.find("]")
            if close != -1:
                bounds = rest[1:close].split(",")
                expr = rest[close + 1 :].strip()
                if len(bounds) == 2 and all(part.strip() for part in bounds) and expr:
                    return expr, bounds[0].strip(), bounds[1].strip()
        scripted = _INTEGRAL_SCRIPTS.match(rest)
        if scripted is not None:
            low = _script_bound(scripted, "low")
            high = _script_bound(scripted, "high")
            expr = rest[scripted.end() :].strip()
            return (expr, low, high) if expr else None
    marker = "integral from "
    start = lower.find(marker)
    if start == -1:
        return None
    rest = cleaned[start + len(marker) :].strip()
    to_at = rest.lower().find(" to ")
    if to_at == -1:
        return None
    after_to = rest[to_at + 4 :].strip()
    of_at = after_to.lower().find(" of ")
    if of_at == -1:
        return None
    low = rest[:to_at].strip()
    high = after_to[:of_at].strip()
    expr = after_to[of_at + 4 :].strip()
    if not low or not high or not expr or " " in low or " " in high:
        return None
    return expr, low, high


def _extract_calculus_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    higher_leibniz = _HIGHER_LEIBNIZ.search(cleaned)
    op_word = mtm.calc_op(cleaned)
    if op_word is None and higher_leibniz is not None:
        op_word = "differentiate"
    if op_word is None or op_word in {"taylor", "partial", "dsolve"}:
        return None
    if op_word == "factor" and any(
        phrase in cleaned.lower() for phrase in ("do not factor", "don't factor")
    ):
        # This is a method constraint on an equation, not a request to factor
        # the pronoun at the end of the sentence.
        return None
    calc_op: Literal["simplify", "differentiate", "integrate", "factor", "expand"] = (
        "differentiate" if op_word in {"differentiate", "derivative"} else "integrate"
    )
    if op_word == "simplify":
        calc_op = "simplify"
    elif op_word == "factor":
        calc_op = "factor"
    elif op_word == "expand":
        calc_op = "expand"
    if calc_op == "integrate" and re.search(r"\bprincipal[\s-]+value\b", cleaned, re.I):
        # The ordinary integrator does not compute a Cauchy principal value.
        # Do not strip this qualifier and certify a different mathematical request.
        return None
    leading_bounds = _leading_integral_bounds(cleaned) if calc_op == "integrate" else None
    tail = _calc_expr_tail(cleaned)
    if calc_op == "differentiate" and higher_leibniz is not None:
        # ``find d²y/dx² if y = ...`` puts the function after the derivative
        # request, not after a word such as "differentiate".  Keep the whole
        # function definition so ``peel_function_definition`` can remove y=.
        lower_cleaned = cleaned.lower()
        if_at = lower_cleaned.find(" if ", higher_leibniz.end())
        if if_at != -1:
            tail = cleaned[if_at + 4 :]
    raw = (
        strip_trailing_filler(leading_bounds[0])
        if leading_bounds is not None
        else (strip_trailing_filler(tail) if tail is not None else cleaned)
    )
    evaluation_point: str | None = None
    if calc_op == "differentiate":
        point_match = _DERIVATIVE_AT_POINT.search(raw.rstrip(".?!"))
        if point_match is not None:
            raw = raw[: point_match.start()].rstrip(" ,;.")
            evaluation_point = point_match.group(2)
        else:
            prime_at = _PRIME_AT_NUMBER.search(cleaned)
            if prime_at is not None:
                evaluation_point = prime_at.group(1)
    if calc_op == "simplify":
        lower_raw = raw.lower()
        for suffix in (
            " state all excluded values",
            " state the excluded values",
            " include all excluded values",
            # The symbolic verifier already creates real-valued symbols. A
            # real-domain qualifier therefore narrows the same task; consume
            # it instead of letting prose make sqrt(x*x) unverifiable.
            " over the real numbers",
            " over the reals",
            " assuming x is real",
            " for real x",
        ):
            at = lower_raw.find(suffix)
            if at != -1:
                raw = raw[:at].rstrip(" ,;.")
                break
    raw = _split_find_clause(raw)
    raw = peel_function_definition(raw)
    # ``simplify 4x+2x=18`` is an equation, not a simplify-of-equality. Fall
    # through so the algebra extractor can solve it. Explicit factor/expand
    # of a single ``poly=0`` stays calculus; a worked multi-equation paste
    # (`Factor it:` then 2x-1=0) must not steal the quadratic.
    if calc_op == "simplify" and "=" in raw:
        return None
    if calc_op in {"factor", "expand"} and "=" in raw:
        from app.modules.math import solve as math_solve

        pairs = math_solve.try_extract_equations_from_text(cleaned)
        if len(pairs) >= 2:
            return None
        if pairs and pairs[0][1].strip() in {"0", "0.0"}:
            raw = pairs[0][0]
    integral_lower: str | None = leading_bounds[1] if leading_bounds is not None else None
    integral_upper: str | None = leading_bounds[2] if leading_bounds is not None else None
    if calc_op == "integrate":
        # "integrate by parts x e^x" / "integrate x e^x by parts": the method is
        # how to teach it, as in "use integration by parts to integrate x e^x".
        raw = _BY_PARTS.sub("", raw).strip()
    raw_with_differential = raw
    if calc_op == "integrate":
        raw = _strip_trailing_differential(raw)
        bounds = mtm.integral_bounds(raw) if leading_bounds is None else None
        if bounds is not None:
            raw, integral_lower, integral_upper = bounds
    expr = math_expr_or_none(raw)
    if expr is None:
        return None
    if calc_op == "factor" and expr.strip().isdigit():
        # "factor 360" asks for its prime factors; SymPy's factor() returns 360.
        return None
    return MathIntent(
        kind="calculus",
        expr=expr,
        operation=calc_op,
        variable=_calculus_variable(
            cleaned, raw_with_differential, expr, integrate=calc_op == "integrate"
        ),
        integral_lower=integral_lower,
        integral_upper=integral_upper,
        derivative_order=_derivative_order(cleaned) if calc_op == "differentiate" else 1,
        evaluation_point=evaluation_point,
    )


def _extract_limit_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    limit_hit = mtm.parse_limit(cleaned)
    if limit_hit is None:
        return None
    expr = _normalize_latex_expr(strip_trailing_filler(limit_hit.expr)).replace("^", "**")
    limit_point = limit_hit.point.lstrip("\\")
    guarded = math_expr_or_none(expr)
    if guarded is None:
        return None
    return MathIntent(
        kind="limit",
        expr=guarded,
        variable=limit_hit.var,
        limit_point=limit_point,
        limit_direction=limit_hit.direction,
        operation="limit",
    )


def _extract_series_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm
    from app.modules.math import solve as math_solve

    if "Σ" in cleaned:
        raw_expressions = [
            match.group(1).strip() for match in _UNICODE_SIGMA_EXPR.finditer(cleaned)
        ]
        expressions: list[str] = []
        variable: str | None = None
        for raw in raw_expressions[:2]:
            guarded = math_expr_or_none(_normalize_latex_expr(raw).replace("^", "**"))
            if guarded is None:
                return None
            names = math_solve.guess_variables(guarded)
            if len(names) != 1:
                return None
            if variable is not None and names[0] != variable:
                return None
            variable = names[0]
            expressions.append(guarded)
        if expressions and variable is not None:
            return MathIntent(
                kind="series",
                expr=expressions[0],
                expr2=expressions[1] if len(expressions) == 2 else None,
                variable=variable,
                series_start="1",
                series_end="infinity",
                operation="series",
                school_op="series_convergence",
            )

    series_hit = mtm.parse_series(cleaned)
    if series_hit is None:
        return None
    expr = _normalize_latex_expr(
        _strip_series_prefix(strip_trailing_filler(series_hit.expr))
    ).replace("^", "**")
    end = series_hit.end.lstrip("\\")
    guarded = math_expr_or_none(expr)
    if guarded is None:
        return None
    return MathIntent(
        kind="series",
        expr=guarded,
        variable=series_hit.var,
        series_start=series_hit.start,
        series_end=end,
        operation="series",
    )


CALCULUS_EXTRACTORS = (
    _extract_critical_points_intent,
    _extract_identity_intent,
    extract_implicit_intent,
    extract_triple_integral_intent,
    extract_average_value_intent,
    extract_linear_approx_intent,
    extract_gradient_intent,
    extract_directional_intent,
    extract_div_curl_intent,
    extract_double_integral_intent,
    _extract_calculus_intent,
    _extract_limit_intent,
    _extract_series_intent,
)
