"""How a feature solver reads the equation, and how it writes numbers in the working.

``_explicit`` reads ``y = F(x)``, ``_linear`` ``ax + by = c`` and ``_quadratic``
``y = ax^2 + bx + c``; ``_num``, ``_point``, ``_bracket``, ``_at`` and ``_line_tex``
write the TeX. ``_Solved`` is what every solver returns.
"""

from __future__ import annotations

import re
from typing import Any

from app.modules.math.schemas import MathIntent
from app.services.workout import Workout


def _parse(text: str, names: list[str]) -> Any:
    from app.modules.math import solve as math_solve

    parsed = math_solve.parse_expression(text, names)
    if isinstance(parsed, tuple):
        raise ValueError("not one expression")
    from sympy import nsimplify

    return nsimplify(parsed, rational=True)


def _symbols(*names: str) -> tuple[Any, ...]:
    from sympy import Symbol

    return tuple(Symbol(name) for name in names)


def _plain(expr: Any) -> Any:
    """The same expression over plain symbols, whatever assumptions the parser set."""
    from sympy import Symbol

    return expr.xreplace({s: Symbol(str(s)) for s in expr.free_symbols})


def _sides(intent: MathIntent, names: list[str]) -> tuple[Any, Any]:
    return _plain(_parse(intent.lhs or "", names)), _plain(_parse(intent.rhs or "", names))


_NAMED_LHS = re.compile(r"^\s*(?:y|[a-z]\s*\(\s*x\s*\))\s*$")


def _explicit(intent: MathIntent) -> Any | None:
    """``y = F(x)`` or ``f(x) = F(x)``: F, in x only."""
    lhs_text, rhs_text = intent.lhs or "", intent.rhs or ""
    if _NAMED_LHS.match(lhs_text):
        side = rhs_text
    elif _NAMED_LHS.match(rhs_text):
        side = lhs_text
    else:
        return None
    (x,) = _symbols("x")
    expr = _plain(_parse(side, ["x"]))
    return expr if expr.free_symbols <= {x} else None


def _linear(intent: MathIntent) -> tuple[Any, Any, Any] | None:
    """``ax + by = c`` (or ``y = mx + b``) as (a, b, c) with ax + by = c."""
    from sympy import Poly

    x, y = _symbols("x", "y")
    explicit = _explicit(intent)
    if explicit is not None:
        expression = y - explicit
    else:
        if re.search(r"[a-z]\s*\(", intent.lhs or "") or re.search(r"[a-z]\s*\(", intent.rhs or ""):
            return None
        lhs, rhs = _sides(intent, ["x", "y"])
        expression = lhs - rhs
    if not expression.free_symbols or not expression.free_symbols <= {x, y}:
        return None
    poly = Poly(expression, x, y)
    if poly.total_degree() != 1:
        return None
    a, b = poly.coeff_monomial(x), poly.coeff_monomial(y)
    c = -poly.coeff_monomial(1)
    return a, b, c


def _quadratic(intent: MathIntent, *, explicit_only: bool) -> tuple[Any, Any, Any, Any] | None:
    """(a, b, c, F) for ``y = ax^2 + bx + c``; unless ``explicit_only``, ``P(x) = Q(x)`` too."""
    from sympy import Poly

    (x,) = _symbols("x")
    expression = _explicit(intent)
    if expression is None:
        if explicit_only:
            return None
        lhs, rhs = _sides(intent, ["x"])
        expression = lhs - rhs
        if not expression.free_symbols <= {x}:
            return None
    if x not in expression.free_symbols:
        return None
    poly = Poly(expression, x)
    if poly.degree() != 2:
        return None
    a, b, c = poly.all_coeffs()
    return a, b, c, expression


def _tex(value: Any) -> str:
    from sympy import latex

    return str(latex(value))


def _num(value: Any) -> str:
    """``-\\frac{1}{2}`` (no space after the sign), ``3``, ``\\sqrt{2} - 1``."""
    tex = _tex(value)
    return "-" + tex[2:] if tex.startswith("- ") else tex


def _at(expression: Any, value: Any) -> str:
    """``x^2 - 6x + 5`` at 3 → ``\\left(3\\right)^{2} - 6 \\cdot 3 + 5``."""
    from sympy import sympify

    from app.modules.math.tools.school.function_value import _substituted_tex

    return _substituted_tex(expression, "x", sympify(value))


def _point(x_value: Any, y_value: Any) -> str:
    return rf"\left({_num(x_value)}, {_num(y_value)}\right)"


def _bracket(value: Any) -> str:
    tex = _num(value)
    return rf"\left({tex}\right)" if tex.startswith("-") else tex


def _line_tex(slope: Any, intercept: Any) -> str:
    from sympy import Rational

    if slope == 0:
        return f"y = {_num(intercept)}"
    if slope == 1:
        term = "x"
    elif slope == -1:
        term = "-x"
    else:
        term = f"{_num(slope)}x"
    if intercept == 0:
        return f"y = {term}"
    sign = "-" if intercept < Rational(0) else "+"
    return f"y = {term} {sign} {_num(abs(intercept))}"


_Solved = tuple[Workout, str, list[str]]
