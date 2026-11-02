"""Tangent and normal lines, and stationary points, of ``y = f(x)``.

Read as plain algebra these went wrong: "the tangent to y = x^2 at x = 3" was
solved as the system ``y = x^2, x = 3`` and answered with the point (3, 9), and
"the stationary points of y = x^3 - 3x" solved the curve for ``x`` in terms of
``y``. Both now differentiate.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.modules.math.function_names import variable_letters
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.number_text import FRACTION_OR_DECIMAL as _NUMBER
from app.services.workout import Workout, math_line, render_workout

CURVE_POINT_OPS = frozenset(
    {
        "tangent_line",
        "normal_line",
        "stationary_points",
        "inflection_points",
        "monotonic_intervals",
        "extreme_value",
        "sum_max_product",
    }
)

_CURVE = r"(?:the\s+(?:curve|graph|function)\s+)?(?:(?:y|[a-z]\s*\(\s*x\s*\))\s*=\s*)?"
_TANGENT = re.compile(
    rf"\b(?P<kind>tangent|normal)(?:\s+line)?\s+(?:to|of|for)\s+{_CURVE}(?P<expr>.+?)\s+"
    rf"(?:at|where|when)\s+(?:the\s+point\s+)?"
    rf"(?:x\s*=\s*(?P<x>{_NUMBER})|\(\s*(?P<px>{_NUMBER})\s*,\s*(?P<py>{_NUMBER})\s*\))\s*$",
    re.IGNORECASE,
)
# "the gradient of the curve y = x^3 at x = 2": the derivative there, not a system to solve.
_GRADIENT_AT = re.compile(
    rf"\b(?:gradient|slope)\s+of\s+(?:the\s+)?(?:curve|graph|function|tangent\s+to)?\s*"
    rf"(?:of\s+)?{_CURVE}(?P<expr>.+?)\s+(?:at|where|when)\s+(?:the\s+point\s+)?"
    rf"(?:x\s*=\s*(?P<x>{_NUMBER})|\(\s*(?P<px>{_NUMBER})\s*,\s*(?P<py>{_NUMBER})\s*\))\s*$",
    re.IGNORECASE,
)
_STATIONARY = re.compile(
    # Not "critical points": those include where dy/dx is undefined, which
    # the critical-point solver looks for and this block does not.
    rf"\b(?:stationary|turning)\s+points?\s+(?:of|for|on)\s+{_CURVE}(?P<expr>.+?)\s*$"
    rf"|\b(?:local\s+)?(?:maximum|max)\s+and\s+(?:local\s+)?(?:minimum|min)(?:\s+points?)?"
    rf"\s+(?:of|for)\s+{_CURVE}(?P<expr2>.+?)\s*$",
    re.IGNORECASE,
)
_INFLECTION = re.compile(
    rf"\bpoints?\s+of\s+inflection\s+(?:of|for|on)\s+{_CURVE}(?P<expr>.+?)\s*$"
    rf"|\binflection\s+points?\s+(?:of|for|on)\s+{_CURVE}(?P<expr2>.+?)\s*$",
    re.IGNORECASE,
)
_MONOTONIC = re.compile(
    rf"^(?:where|when|for\s+what\s+values\s+of\s+x|on\s+what\s+intervals?)\s+is\s+{_CURVE}"
    r"(?P<expr>.+?)\s+(?P<way>increasing|decreasing)$"
    rf"|^(?:find\s+)?(?:the\s+)?intervals?\s+(?:where|on\s+which)\s+{_CURVE}(?P<expr2>.+?)\s+is\s+"
    r"(?P<way2>increasing|decreasing)$",
    re.IGNORECASE,
)
# "find the maximum value of f(x) = -x^2 + 4x", "h = 20t - 5t^2 ... the maximum height".
_EXTREME = re.compile(
    r"\b(?P<way>maximum|minimum|max|min|greatest|least|highest|lowest)\s+"
    r"(?:value|height|point|output|profit|area|cost)?\b",
    re.IGNORECASE,
)
_DEFINED = re.compile(
    r"(?<![A-Za-z])(?P<name>[a-zA-Z])(?:\s*\(\s*(?P<var>[a-z])\s*\))?\s*=\s*"
    r"(?P<expr>[^,;=\s](?:[^,;=]*?[^,;=\s])??|\s(?=\S|\Z))"
    r"(?=\s*(?:,|;|\.\s|\bfind\b|\bwhat\b|\bwhen\b|$))",
)
_SUM_PRODUCT = re.compile(
    r"\btwo\s+(?:positive\s+|real\s+)?numbers\s+(?:add|sum|add\s+up)\s+to\s+(?P<sum>\d+(?:\.\d+)?)"
    r"[^\d\n].*?\b(?:maximum|largest|greatest|biggest)\s+(?:possible\s+)?product\b",
    re.IGNORECASE,
)
_LEAD = re.compile(
    r"^\s*(?:(?:please\s+)?(?:find|determine|work\s+out|calculate|what\s+(?:is|are)|give)\s+)?"
    r"(?:the\s+)?(?:equation\s+of\s+(?:the\s+)?)?(?:all\s+(?:the\s+)?)?",
    re.IGNORECASE,
)


def _expression(raw: str) -> str | None:
    from app.modules.math.tools.expr_rewrite import math_expr_or_none

    text = raw.strip().rstrip(".?!").strip()
    return math_expr_or_none(text) if text else None


def extract_curve_point_intent(cleaned: str) -> MathIntent | None:
    """``find the equation of the tangent to y = x^2 at x = 3``; ``stationary points of ...``."""
    body = " ".join(cleaned.split()).rstrip(".?!")
    lead = _LEAD.match(body)
    request = body[lead.end() :] if lead else body
    tangent = _TANGENT.fullmatch(request)
    if tangent is not None:
        expr = _expression(tangent["expr"])
        point = tangent["x"] or tangent["px"]
        if expr is None or point is None:
            return None
        return MathIntent(
            kind="calculus",
            operation="differentiate",
            school_op="tangent_line" if tangent["kind"].lower() == "tangent" else "normal_line",
            expr=expr,
            variable="x",
            evaluation_point=point.replace(" ", ""),
        )
    gradient = _GRADIENT_AT.fullmatch(request)
    if gradient is not None:
        expr = _expression(gradient["expr"])
        point = gradient["x"] or gradient["px"]
        if expr is None or point is None:
            return None
        return MathIntent(
            kind="calculus",
            operation="differentiate",
            expr=expr,
            variable="x",
            evaluation_point=point.replace(" ", ""),
        )
    others = _other_curve_intents(body, request)
    if others is not None:
        return others
    stationary = _STATIONARY.fullmatch(request)
    if stationary is not None:
        expr = _expression(stationary["expr"] or stationary["expr2"] or "")
        if expr is None:
            return None
        return MathIntent(
            kind="calculus",
            operation="critical_points",
            school_op="stationary_points",
            expr=expr,
            variable="x",
        )
    return None


def _other_curve_intents(body: str, request: str) -> MathIntent | None:
    """Inflection points, where a curve rises or falls, and the largest or smallest value."""
    inflection = _INFLECTION.fullmatch(request)
    if inflection is not None:
        expr = _expression(inflection["expr"] or inflection["expr2"] or "")
        if expr is None:
            return None
        return MathIntent(
            kind="calculus",
            operation="critical_points",
            school_op="inflection_points",
            expr=expr,
            variable="x",
        )
    monotonic = _MONOTONIC.fullmatch(body)
    if monotonic is not None:
        expr = _expression(monotonic["expr"] or monotonic["expr2"] or "")
        way = (monotonic["way"] or monotonic["way2"] or "").lower()
        if expr is None:
            return None
        return MathIntent(
            kind="calculus",
            operation="critical_points",
            school_op="monotonic_intervals",
            expr=expr,
            variable="x",
            trial_outcome=way,
        )
    pair = _SUM_PRODUCT.search(body)
    if pair is not None:
        return MathIntent(
            kind="calculus",
            operation="critical_points",
            school_op="sum_max_product",
            expr="x",
            variable="x",
            percent_base=float(pair["sum"]),
        )
    extreme = _EXTREME.search(body)
    defined = _DEFINED.search(body)
    if extreme is not None and defined is not None:
        variable = defined["var"]
        expr = _expression(defined["expr"])
        if expr is None:
            return None
        letters = variable_letters(expr)
        if variable is None:
            if len(letters) != 1:
                return None
            variable = next(iter(letters))
        if letters - {variable} or variable == defined["name"].lower():
            return None
        way = extreme["way"].lower()
        largest = way in {"maximum", "max", "greatest", "highest"}
        return MathIntent(
            kind="calculus",
            operation="critical_points",
            school_op="extreme_value",
            expr=expr,
            variable=variable,
            trial_outcome="max" if largest else "min",
            # The name as written: "f(x)", or "h" for h = 20t - 5t^2.
            lhs=f"{defined['name']}({variable})" if defined["var"] else defined["name"],
        )
    return None


def _parse(expr: str, variable: str) -> tuple[Any, Any] | None:
    from sympy import Symbol

    from app.modules.math import solve as math_solve
    from app.services.solving import SolveServiceError

    symbol = Symbol(variable, real=True)
    try:
        parsed = math_solve.parse_expression(expr, [variable], real=True)
    except (SolveServiceError, SyntaxError, TypeError, ValueError):
        return None
    if isinstance(parsed, tuple) or parsed.free_symbols - {symbol}:
        return None
    return symbol, parsed


def _line_tex(slope: Any, intercept: Any, variable: str) -> str:
    """``y = mx + c`` in that order: no ``1x``, no ``+ 0``.

    ``y = -\\frac{1}{2} x + \\frac{3}{2}``, not SymPy's ``y = \\frac{3}{2} - \\frac{x}{2}``.
    """
    from sympy import latex

    if slope == 0:
        return f"y = {latex(intercept)}"
    if slope == 1:
        term = variable
    elif slope == -1:
        term = f"-{variable}"
    else:
        term = f"{latex(slope)} {variable}"
    if intercept == 0:
        return f"y = {term}"
    sign = "-" if intercept.is_negative else "+"
    return f"y = {term} {sign} {latex(abs(intercept))}"


def _tangent_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from sympy import diff, latex, simplify, sympify

    from app.modules.math.tools.school.function_value import _substituted_tex

    parsed = _parse(intent.expr or "", intent.variable)
    if parsed is None or intent.evaluation_point is None:
        return None
    symbol, curve = parsed
    x1 = sympify(intent.evaluation_point)
    y1 = simplify(curve.subs(symbol, x1))
    derivative = simplify(diff(curve, symbol))
    slope = simplify(derivative.subs(symbol, x1))
    if not (y1.is_real and slope.is_real):
        return None
    var = intent.variable
    normal = intent.school_op == "normal_line"
    steps = [
        math_line(f"y_1 = {_substituted_tex(curve, var, x1)} = {latex(y1)}", "point on the curve"),
        math_line(rf"\frac{{dy}}{{d{var}}} = {latex(derivative)}"),
        math_line(
            f"m = {_substituted_tex(derivative, var, x1)} = {latex(slope)}",
            f"gradient at ${var} = {latex(x1)}$",
        ),
    ]
    if normal:
        if slope == 0:
            answer = f"{var} = {latex(x1)}"
            steps.append(math_line(answer, "the tangent is flat, so the normal is vertical"))
            return _finish(intent, lines, steps, answer, curve)
        tangent_slope, slope = slope, simplify(-1 / slope)
        steps.append(
            math_line(
                rf"m_{{n}} = -\frac{{1}}{{{latex(tangent_slope)}}} = {latex(slope)}",
                "perpendicular to the tangent",
            )
        )
    intercept = simplify(y1 - slope * x1)
    coefficient = {1: "", -1: "-"}.get(slope, latex(slope)) if slope.is_Integer else latex(slope)
    point_form = f"y - {latex(y1)} = {coefficient}\\left({var} - {latex(x1)}\\right)"
    steps.append(math_line(point_form.replace("- -", "+ "), "point-slope form"))
    answer = _line_tex(slope, intercept, var)
    return _finish(intent, lines, steps, answer, curve)


def _finish(
    intent: MathIntent, lines: list[str], steps: list[str], answer: str, curve: Any
) -> VerifiedMathBlock:
    from sympy import latex

    name = "normal" if intent.school_op == "normal_line" else "tangent"
    lines.extend(steps)
    block = finish_with_answer(lines, answer)
    working = render_workout(
        Workout(
            given=(
                math_line(f"y = {latex(curve)}"),
                math_line(f"{intent.variable} = {intent.evaluation_point}"),
            ),
            find=(f"the {name} line",),
            formula=(math_line("y - y_1 = m(x - x_1)", "Point-slope form"),),
            steps=tuple(steps),
        ),
        answer,
    )
    return replace(block, worked_reply=working)


def _nature(derivative: Any, second: Any, symbol: Any, point: Any, others: list[Any]) -> str:
    """Maximum or minimum by the second derivative; the sign of dy/dx either side if it is 0."""
    value = second.subs(symbol, point)
    if value.is_negative:
        return "maximum"
    if value.is_positive:
        return "minimum"
    gaps = [abs(point - other) for other in others if other != point]
    step = min([*gaps, 1]) / 2
    before = derivative.subs(symbol, point - step)
    after = derivative.subs(symbol, point + step)
    if before.is_positive and after.is_negative:
        return "maximum"
    if before.is_negative and after.is_positive:
        return "minimum"
    return "point of inflection"


def _stationary_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from sympy import Eq, FiniteSet, S, diff, latex, simplify, solveset

    parsed = _parse(intent.expr or "", intent.variable)
    if parsed is None:
        return None
    symbol, curve = parsed
    var = intent.variable
    derivative = simplify(diff(curve, symbol))
    roots = solveset(Eq(derivative, 0), symbol, domain=S.Reals)
    if not isinstance(roots, FiniteSet) or len(roots) > 6:
        return None
    points = sorted(roots, key=lambda root: float(root))
    second = simplify(diff(derivative, symbol))
    dy = rf"\frac{{dy}}{{d{var}}}"
    d2y = rf"\frac{{d^{{2}}y}}{{d{var}^{{2}}}}"
    steps = [math_line(f"{dy} = {latex(derivative)}")]
    if not points:
        answer = r"\text{no stationary points}"
        steps.append(math_line(f"{latex(derivative)} = 0", "has no real solution"))
    else:
        roots_tex = r",\; ".join(f"{var} = {latex(point)}" for point in points)
        steps.append(
            math_line(f"{latex(derivative)} = 0 \\Rightarrow {roots_tex}", "set the gradient to 0")
        )
        steps.append(math_line(f"{d2y} = {latex(second)}"))
        found: list[str] = []
        for point in points:
            y_value = simplify(curve.subs(symbol, point))
            nature = _nature(derivative, second, symbol, point, points)
            curvature = simplify(second.subs(symbol, point))
            sign = "< 0" if curvature.is_negative else "> 0" if curvature.is_positive else "= 0"
            steps.append(
                math_line(
                    f"{var} = {latex(point)}:\\ y = {latex(y_value)},\\ {d2y} = "
                    f"{latex(curvature)} {sign}",
                    nature,
                )
            )
            found.append(rf"\left({latex(point)}, {latex(y_value)}\right)\ \text{{{nature}}}")
        answer = r",\; ".join(found)
    lines.extend(steps)
    block = finish_with_answer(lines, answer)
    working = render_workout(
        Workout(
            given=(math_line(f"y = {latex(curve)}"),),
            find=("the stationary points",),
            steps=tuple(steps),
        ),
        answer,
    )
    return replace(block, worked_reply=working)


def _workout_block(
    lines: list[str], answer: str, given: tuple[str, ...], find: str, rows: list[str]
) -> VerifiedMathBlock:
    lines.extend(rows)
    block = finish_with_answer(lines, answer)
    working = render_workout(Workout(given=given, find=(find,), steps=tuple(rows)), answer)
    return replace(block, worked_reply=working)


def _inflection_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from sympy import Eq, FiniteSet, S, diff, latex, simplify, solveset

    parsed = _parse(intent.expr or "", intent.variable)
    if parsed is None:
        return None
    x, curve = parsed
    var = intent.variable
    first = simplify(diff(curve, x))
    second = simplify(diff(first, x))
    roots = solveset(Eq(second, 0), x, domain=S.Reals)
    if not isinstance(roots, FiniteSet) and roots is not S.EmptySet:
        return None
    candidates = sorted(roots, key=lambda root: float(root)) if roots is not S.EmptySet else []
    d2 = rf"\frac{{d^{{2}}y}}{{d{var}^{{2}}}}"
    rows = [
        math_line(rf"\frac{{dy}}{{d{var}}} = {latex(first)}"),
        math_line(f"{d2} = {latex(second)}"),
    ]
    points: list[str] = []
    if candidates:
        rows.append(
            math_line(
                f"{latex(second)} = 0 \\Rightarrow "
                + r",\; ".join(f"{var} = {latex(root)}" for root in candidates),
                "where the curvature could change",
            )
        )
    for root in candidates:
        left = second.subs(x, root - S.Half)
        right = second.subs(x, root + S.Half)
        if left.is_positive == right.is_positive:
            rows.append(
                math_line(f"{var} = {latex(root)}", f"${d2}$ keeps its sign: not an inflection")
            )
            continue
        y_value = simplify(curve.subs(x, root))
        rows.append(
            math_line(f"{var} = {latex(root)}:\\ y = {latex(y_value)}", f"${d2}$ changes sign")
        )
        points.append(rf"\left({latex(root)}, {latex(y_value)}\right)")
    answer = r",\; ".join(points) if points else r"\text{no point of inflection}"
    return _workout_block(
        lines, answer, (math_line(f"y = {latex(curve)}"),), "the points of inflection", rows
    )


def _monotonic_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from sympy import S, diff, latex, simplify, solveset

    from app.modules.math.solve.inequalities import inequality_solution_latex

    parsed = _parse(intent.expr or "", intent.variable)
    if parsed is None:
        return None
    x, curve = parsed
    var = intent.variable
    first = simplify(diff(curve, x))
    rising = intent.trial_outcome != "decreasing"
    solution = solveset(first > 0 if rising else first < 0, x, domain=S.Reals)
    answer = inequality_solution_latex(solution, x)
    rows = [
        math_line(rf"f'({var}) = {latex(first)}"),
        math_line(
            f"{latex(first)} {'>' if rising else '<'} 0",
            "increasing where the gradient is positive"
            if rising
            else "decreasing where the gradient is negative",
        ),
    ]
    return _workout_block(
        lines,
        answer,
        (math_line(f"f({var}) = {latex(curve)}"),),
        f"where f is {'increasing' if rising else 'decreasing'}",
        rows,
    )


def _extreme_value_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from sympy import Eq, FiniteSet, S, diff, latex, simplify, solveset

    parsed = _parse(intent.expr or "", intent.variable)
    if parsed is None:
        return None
    x, curve = parsed
    var = intent.variable
    written = intent.lhs or "y"
    name = written.split("(", 1)[0]
    largest = intent.trial_outcome == "max"
    first = simplify(diff(curve, x))
    second = simplify(diff(first, x))
    roots = solveset(Eq(first, 0), x, domain=S.Reals)
    if not isinstance(roots, FiniteSet):
        return None
    wanted = [
        root
        for root in roots
        if (second.subs(x, root).is_negative if largest else second.subs(x, root).is_positive)
    ]
    if len(wanted) != 1:
        return None
    root = wanted[0]
    value = simplify(curve.subs(x, root))
    d = rf"\frac{{d{name}}}{{d{var}}}"
    rows = [
        math_line(f"{d} = {latex(first)}"),
        math_line(f"{latex(first)} = 0 \\Rightarrow {var} = {latex(root)}", "a stationary point"),
        math_line(
            rf"\frac{{d^{{2}}{name}}}{{d{var}^{{2}}}} = {latex(second.subs(x, root))} "
            f"{'<' if largest else '>'} 0",
            "a maximum" if largest else "a minimum",
        ),
        math_line(
            f"{name}({latex(root)}) = {_substituted(curve, var, root)}"
            if "(" in written
            else f"{name} = {_substituted(curve, var, root)}",
            None if "(" in written else f"at ${var} = {latex(root)}$",
        ),
    ]
    return _workout_block(
        lines,
        latex(value),
        (math_line(f"{written} = {latex(curve)}"),),
        f"the {'maximum' if largest else 'minimum'} value of ${name}$",
        rows,
    )


def _substituted(curve: Any, var: str, value: Any) -> str:
    from app.modules.math.tools.school.function_value import _substituted_tex

    return _substituted_tex(curve, var, value)


def _sum_max_product_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    total = intent.percent_base
    if total is None or total <= 0:
        return None
    n = f"{total:g}"
    half = f"{total / 2:g}"
    answer = f"{total * total / 4:g}"
    rows = [
        math_line(f"y = {n} - x", "the two numbers are x and y"),
        math_line(f"P = x({n} - x) = {n}x - x^2", "the product"),
        math_line(
            rf"\frac{{dP}}{{dx}} = {n} - 2x = 0 \Rightarrow x = {half}", "a stationary point"
        ),
        math_line(r"\frac{d^{2}P}{dx^{2}} = -2 < 0", "a maximum"),
        math_line(f"x = y = {half},\\ P = {half} \\times {half}"),
    ]
    return _workout_block(
        lines, answer, (math_line(f"x + y = {n}"),), "the largest product $P = xy$", rows
    )


def curve_point_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    op = intent.school_op
    if op == "stationary_points":
        return _stationary_block(intent, lines)
    if op == "inflection_points":
        return _inflection_block(intent, lines)
    if op == "monotonic_intervals":
        return _monotonic_block(intent, lines)
    if op == "extreme_value":
        return _extreme_value_block(intent, lines)
    if op == "sum_max_product":
        return _sum_max_product_block(intent, lines)
    return _tangent_block(intent, lines)
