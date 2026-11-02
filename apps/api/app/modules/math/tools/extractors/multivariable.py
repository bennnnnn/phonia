"""Multivariable calculus asked for by name.

Double and triple integrals over named axes (``x=0 to 1 and y=0 to 2``), the gradient, a
directional derivative, divergence and curl. ``calculus.py`` runs these in its registry order.
"""

from __future__ import annotations

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.expr_rewrite import _normalize_latex_expr, math_expr_or_none
from app.services.text_match import word_index


def _named_axis_bounds(text: str, var: str) -> tuple[str, str] | None:
    """Linear scan for ``var=LO to HI`` — no regex."""
    lower = text.lower()
    needle = f"{var}="
    idx = lower.find(needle)
    if idx == -1:
        needle = f"{var} ="
        idx = lower.find(needle)
        if idx == -1:
            return None
    rest = text[idx + len(needle) :]
    to_at = rest.lower().find(" to ")
    if to_at == -1:
        return None
    lo = rest[:to_at].strip().rstrip(",")
    hi_part = rest[to_at + 4 :].strip()
    end = 0
    while end < len(hi_part) and not hi_part[end].isspace() and hi_part[end] not in ",;":
        end += 1
    hi = hi_part[:end].strip()
    if not lo or not hi:
        return None
    return lo, hi


def _integral_expr_after(cleaned: str, cue: str) -> str | None:
    lower = cleaned.lower()
    start = lower.find(cue)
    if start == -1:
        return None
    rest = cleaned[start + len(cue) :].lstrip()
    if rest.lower().startswith("of "):
        rest = rest[3:]
    from_at = rest.lower().find(" from ")
    if from_at == -1:
        return None
    return math_expr_or_none(rest[:from_at].strip())


def extract_triple_integral_intent(cleaned: str) -> MathIntent | None:
    x_bounds = _named_axis_bounds(cleaned, "x")
    y_bounds = _named_axis_bounds(cleaned, "y")
    z_bounds = _named_axis_bounds(cleaned, "z")
    if x_bounds is None or y_bounds is None or z_bounds is None:
        return None
    if "triple" not in cleaned.lower() and "integral" not in cleaned.lower():
        return None
    expr = _integral_expr_after(cleaned, "triple integral") or _integral_expr_after(
        cleaned, "integral"
    )
    if expr is None:
        return None
    return MathIntent(
        kind="calculus",
        operation="integrate",
        school_op="triple_integral",
        expr=expr,
        variable="x",
        variable2="y",
        variable3="z",
        integral_lower=x_bounds[0],
        integral_upper=x_bounds[1],
        integral_lower2=y_bounds[0],
        integral_upper2=y_bounds[1],
        integral_lower3=z_bounds[0],
        integral_upper3=z_bounds[1],
    )


def extract_double_integral_intent(cleaned: str) -> MathIntent | None:
    """Intercept ``double integral of … from x=a to b and y=c to d``."""
    lower = cleaned.lower()
    x_bounds = _named_axis_bounds(cleaned, "x")
    y_bounds = _named_axis_bounds(cleaned, "y")
    if x_bounds is None or y_bounds is None:
        return None
    if _named_axis_bounds(cleaned, "z") is not None:
        return None
    if "triple" in cleaned.lower():
        return None
    start = lower.find("double integral")
    if start != -1:
        rest = cleaned[start + len("double integral") :]
    else:
        start = lower.find("integral")
        if start == -1:
            return None
        rest = cleaned[start + len("integral") :]
    rest = rest.lstrip()
    if rest.lower().startswith("of "):
        rest = rest[3:]
    from_at = rest.lower().find(" from ")
    if from_at == -1:
        return None
    expr = math_expr_or_none(_normalize_latex_expr(rest[:from_at].strip()))
    if expr is None:
        return None
    return MathIntent(
        kind="calculus",
        operation="integrate",
        school_op="double_integral",
        expr=expr,
        variable="x",
        variable2="y",
        integral_lower=x_bounds[0],
        integral_upper=x_bounds[1],
        integral_lower2=y_bounds[0],
        integral_upper2=y_bounds[1],
    )


def extract_gradient_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if word_index(lower, "gradient") == -1 and word_index(lower, "grad") == -1:
        return None
    of_at = lower.find(" of ")
    if of_at == -1:
        return None
    expr = math_expr_or_none(cleaned[of_at + 4 :].strip())
    if expr is None:
        return None
    return MathIntent(
        kind="calculus",
        operation="partial",
        school_op="gradient",
        expr=expr,
        variable="x",
    )


def extract_directional_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math.match.coordinate_vector import literal_math_tuples

    lower = cleaned.lower()
    if "directional derivative" not in lower:
        return None
    of_at = lower.find(" of ")
    at_at = lower.find(" at ")
    if of_at == -1 or at_at == -1:
        return None
    expr = math_expr_or_none(cleaned[of_at + 4 : at_at].strip())
    points = literal_math_tuples(cleaned, "(", ")")
    vecs = literal_math_tuples(cleaned, "<", ">") or []
    if expr is None or points is None or len(points) != 1 or len(vecs) != 1:
        return None
    if len(points[0]) != len(vecs[0]):
        return None
    return MathIntent(
        kind="calculus",
        operation="partial",
        school_op="directional",
        expr=expr,
        vec_a=list(points[0]),
        vec_b=vecs[0],
        variable="x",
    )


def extract_div_curl_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    op = None
    if word_index(lower, "divergence") != -1 or word_index(lower, "div") != -1:
        op = "divergence"
    elif word_index(lower, "curl") != -1:
        op = "curl"
    if op is None:
        return None
    start = cleaned.find("<")
    end = cleaned.find(">", start + 1) if start != -1 else -1
    if start == -1 or end == -1:
        return None
    expr = cleaned[start + 1 : end].strip()
    if math_expr_or_none(expr.replace(",", "+")) is None:
        return None
    return MathIntent(
        kind="calculus",
        operation="partial",
        school_op=op,
        expr=expr,
        variable="x",
    )
