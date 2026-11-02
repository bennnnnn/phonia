"""Completing the square, and the cosine rule for two sides and the angle between them.

``complete the square x^2 + 6x + 5`` -> ``(x + 3)^{2} - 4``;
``in triangle ABC, a = 7, b = 9, C = 60 degrees, find c`` -> ``\\sqrt{67}``.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.modules.math.schemas import MathIntent
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.triangle import cos_degrees, cosine_rule_side
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import _SIDE_ASKED
from app.services.number_text import DECIMAL
from app.services.workout import Workout, math_line, render_workout

ALGEBRA_FACT_OPS = frozenset({"complete_square", "cosine_rule", "polynomial_remainder"})

_COMPLETE_SQUARE = re.compile(
    r"(?:(?:please\s+)?(?:complete|completing)\s+the\s+square\s+(?:for|of|on|in)?\s*)(?P<expr>.+)"
    r"|(?P<expr2>.+?)\s*,?\s+(?:by\s+)?(?:completing|complete)\s+the\s+square",
    re.IGNORECASE,
)
# "what is the remainder when x^3 + 2x - 5 is divided by x - 2".
_REMAINDER = re.compile(
    r"(?:(?:what\s+is|what's|whats|find|calculate|work\s+out)\s+)?the\s+remainder\s+when\s+"
    r"(?P<dividend>.+?)\s+is\s+divided\s+by\s+(?P<divisor>.+)",
    re.IGNORECASE,
)
_NUMBER = rf"({DECIMAL})"
_SIDE = rf"\b([a-c])\s*=\s*{_NUMBER}"
_ANGLE = rf"\b([A-C])\s*=\s*{_NUMBER}\s*(?:°|degrees?|deg)?"


def extract_algebra_fact_intent(cleaned: str) -> MathIntent | None:
    body = " ".join(cleaned.split()).strip().rstrip("?.!")
    if not body or len(body) > 200:
        return None
    square = _COMPLETE_SQUARE.fullmatch(body)
    if square is not None:
        from app.modules.math.tools.expr_rewrite import math_expr_or_none

        raw = (square["expr"] or square["expr2"] or "").strip(" :")
        raw = re.sub(r"\s*=\s*0$", "", raw)
        expr = math_expr_or_none(raw)
        if expr is None or "=" in expr:
            return None
        return MathIntent(
            kind="arithmetic", school_op="complete_square", expr=expr, operation="solve"
        )
    remainder = _REMAINDER.fullmatch(body)
    if remainder is not None:
        return _remainder_intent(remainder["dividend"], remainder["divisor"])
    return _cosine_rule_intent(body)


def _polynomial(text: str) -> Any | None:
    """A polynomial in x with numeric coefficients, or None."""
    from sympy import Poly, Symbol

    from app.modules.math import solve as math_solve
    from app.modules.math.tools.expr_rewrite import math_expr_or_none

    expr = math_expr_or_none(text.strip().strip("()") if text.count("(") == 1 else text.strip())
    if expr is None or "=" in expr:
        return None
    x = Symbol("x")
    with sympy_decline() as declined:
        poly = Poly(math_solve.parse_expression(expr, ["x"]), x)
    if declined:
        return None
    if poly.free_symbols - {x} or not poly.domain.is_Numerical:
        return None
    return poly


def _remainder_intent(dividend: str, divisor: str) -> MathIntent | None:
    """Both sides polynomials in x, the divisor of degree 1 or more and no larger."""
    top, bottom = _polynomial(dividend), _polynomial(divisor)
    if top is None or bottom is None or not 1 <= bottom.degree() <= top.degree():
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="polynomial_remainder",
        expr=f"{top.as_expr()}|{bottom.as_expr()}",
        operation="solve",
    )


def _cosine_rule_intent(body: str) -> MathIntent | None:
    """Two sides, the angle between them, and the third side asked for."""
    sides = {match.group(1): float(match.group(2)) for match in re.finditer(_SIDE, body)}
    angles = {match.group(1): float(match.group(2)) for match in re.finditer(_ANGLE, body)}
    find = _SIDE_ASKED.search(body)
    if find is None or len(sides) != 2 or len(angles) != 1:
        return None
    target = find.group(1)
    angle_name, angle = next(iter(angles.items()))
    # The included angle is opposite the side asked for: a, b and C give c.
    if angle_name.lower() != target or target in sides or not 0 < angle < 180:
        return None
    (first_name, first), (second_name, second) = sorted(sides.items())
    return MathIntent(
        kind="arithmetic",
        school_op="cosine_rule",
        tri_a=first,
        tri_b=second,
        sector_angle_deg=angle,
        expr=f"{first_name},{second_name},{angle_name},{target}",
        operation="solve",
    )


def algebra_fact_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.school_op == "complete_square":
        return _complete_square(intent, lines)
    if intent.school_op == "polynomial_remainder":
        return _polynomial_remainder(intent, lines)
    return _cosine_rule(intent, lines)


def _polynomial_remainder(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    """The remainder of polynomial division, checked by P = Q D + R.

    A divisor x - a gives the remainder theorem's line: the remainder is P(a).
    """
    from sympy import Poly, Symbol, UnevaluatedExpr, div, expand, latex, solve, sympify

    x = Symbol("x")
    top_text, _, bottom_text = (intent.expr or "").partition("|")
    with sympy_decline() as declined:
        top, bottom = sympify(top_text), sympify(bottom_text)
        quotient, remainder = div(top, bottom, x)
    if declined:
        return None
    if expand(quotient * bottom + remainder - top) != 0:
        return None
    if Poly(remainder, x).degree() >= Poly(bottom, x).degree():
        return None
    answer = latex(remainder)
    rows = [
        math_line(
            rf"{latex(top)} = \left({latex(quotient)}\right)\left({latex(bottom)}\right)"
            rf" + {latex(remainder)}".replace("+ -", "- "),
            "dividend = quotient times divisor + remainder",
        )
    ]
    if Poly(bottom, x).degree() == 1:
        root = solve(bottom, x)[0]
        substituted = latex(top.subs(x, UnevaluatedExpr(root)), mul_symbol="times", order="rev-lex")
        rows.insert(
            0,
            math_line(
                rf"P({latex(root)}) = {substituted} = {latex(top.subs(x, root))}",
                f"remainder theorem: put x = {latex(root)} into the dividend",
            ),
        )
    lines.append(f"Remainder of ({top}) / ({bottom}) = {remainder}")
    block = finish_with_answer(lines, answer)
    working = render_workout(
        Workout(
            given=(math_line(rf"P(x) = {latex(top)}"), math_line(rf"D(x) = {latex(bottom)}")),
            find=(math_line(r"\text{the remainder}"),),
            steps=tuple(rows),
        ),
        answer,
    )
    return replace(block, worked_reply=working)


def _complete_square(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from sympy import Poly, Rational, Symbol, latex, nsimplify

    from app.modules.math import solve as math_solve

    x = Symbol("x")
    with sympy_decline() as declined:
        parsed = math_solve.parse_expression(intent.expr or "", ["x"])
        poly = Poly(parsed, x)
    if declined:
        return None
    if poly.degree() != 2 or poly.free_symbols - {x}:
        return None
    a, b, c = (nsimplify(coefficient) for coefficient in poly.all_coeffs())
    half = Rational(b) / (2 * a)
    shift = c - a * half**2
    inside = latex(x + half)
    squared = rf"\left({inside}\right)^{{2}}"
    lead = "" if a == 1 else ("-" if a == -1 else latex(a))
    answer = f"{lead}{squared}"
    if shift != 0:
        answer += f" {'-' if shift < 0 else '+'} {latex(abs(shift))}"
    rows: list[str] = []
    if a != 1:
        factored = latex(x**2 + (b / a) * x)
        rows.append(
            math_line(
                rf"{latex(parsed)} = {lead}\left({factored}\right) + {latex(c)}",
                f"take out {latex(a)}",
            )
        )
    correction = a * half**2
    removed = f"{lead}{squared} - {latex(correction)} + {latex(c)}".replace("+ -", "- ")
    rows.append(
        math_line(
            removed,
            rf"half of ${latex(Rational(b) / a)}$ is ${latex(half)}$; take away its square",
        )
    )
    lines.append(f"Completed square: {answer}")
    block = finish_with_answer(lines, answer)
    working = render_workout(Workout(given=(math_line(latex(parsed)),), steps=tuple(rows)), answer)
    return replace(block, worked_reply=working)


def _cosine_rule(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from sympy import latex

    a, b, angle = intent.tri_a, intent.tri_b, intent.sector_angle_deg
    names = (intent.expr or "").split(",")
    if a is None or b is None or angle is None or len(names) != 4:
        return None
    first, second, angle_name, target = names
    side = cosine_rule_side(a, b, angle)
    # Whole sides at an exact angle keep the surd (30°: 89 - 40√3); any other side is a decimal.
    exact = a.is_integer() and b.is_integer() and not side.is_Float
    square = side**2
    twice = (int(2 * a * b) if exact else 2 * a * b) * cos_degrees(angle)
    n = _number
    term = latex(abs(twice), order="none") if exact else n(abs(twice))
    total = latex(square, order="none") if exact else n(round(float(square), 4))
    # cos C < 0 past 90°: subtracting 2ab cos C adds.
    sign = "+" if twice.is_negative else "-"
    rows = [
        math_line(
            rf"{target}^2 = {n(a)}^2 + {n(b)}^2 - 2({n(a)})({n(b)})\cos {n(angle)}^\circ",
        ),
        math_line(rf"{target}^2 = {n(a * a)} + {n(b * b)} {sign} {term} = {total}"),
    ]
    lines.append(f"{target}^2 = {float(square):.6g}; {target} = {float(side):.6g}")
    answer = _side_answer(side, exact=exact)
    block = finish_with_answer(lines, answer)
    working = render_workout(
        Workout(
            given=(
                math_line(f"{first} = {n(a)}"),
                math_line(f"{second} = {n(b)}"),
                math_line(f"{angle_name} = {n(angle)}^\\circ", "the angle between them"),
            ),
            find=(math_line(target),),
            formula=(
                math_line(
                    rf"{target}^2 = {first}^2 + {second}^2 - 2{first}{second}\cos {angle_name}",
                    "Cosine rule",
                ),
            ),
            substitution=tuple(rows),
        ),
        answer,
    )
    return replace(block, worked_reply=working)


def _number(value: Any) -> str:
    return f"{float(value):g}"


def _side_answer(side: Any, *, exact: bool) -> str:
    """``\\sqrt{67} \\approx 8.185``, a whole number, or the decimal."""
    from sympy import latex

    value = float(side)
    if abs(value - round(value)) < 1e-9:
        return str(round(value))
    if exact:
        return rf"{latex(side, order='none')} \approx {value:.4g}"
    return f"{value:.4g}"
