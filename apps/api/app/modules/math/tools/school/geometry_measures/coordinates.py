"""Circles, lines and triangles on coordinates."""

from __future__ import annotations

from dataclasses import replace

from app.modules.math.schemas import MathIntent
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.tools.school.geometry_measures.working import _n, _Solved
from app.services.workout import math_line, text_line


def _signed(value: float, name: str) -> str:
    """``(x - 2)``, ``(y + 3)``, ``x``."""
    if value == 0:
        return name
    return rf"\left({name} {'-' if value > 0 else '+'} {_n(abs(value))}\right)"


def _circle_equation(numbers: list[float], words: list[str]) -> _Solved | None:
    h, k, r = numbers
    if r <= 0:
        return None
    answer = f"{_signed(h, 'x')}^2 + {_signed(k, 'y')}^2 = {_n(r * r)}"
    return _Solved(
        (math_line(rf"\text{{centre }} ({_n(h)}, {_n(k)})"), math_line(f"r = {_n(r)}")),
        (math_line(r"\text{the equation of the circle}"),),
        (math_line(r"(x - a)^2 + (y - b)^2 = r^2", "Circle with centre (a, b)"),),
        (math_line(rf"(x - ({_n(h)}))^2 + (y - ({_n(k)}))^2 = {_n(r)}^2"),),
        answer,
    )


def _circle_centre_radius(intent: MathIntent) -> _Solved | None:
    from sympy import Expr, Poly, Symbol, expand, latex, sqrt

    from app.modules.math import solve as math_solve

    x, y = Symbol("x"), Symbol("y")
    equation = intent.expr or ""
    left, _, right = equation.partition("=")
    with sympy_decline() as declined:
        lhs = math_solve.parse_expression(left, ["x", "y"])
        rhs = math_solve.parse_expression(right, ["x", "y"])
        if not (isinstance(lhs, Expr) and isinstance(rhs, Expr)):
            return None  # ``y = (1, 2)`` is a point, not a side of a circle's equation
        poly = Poly(expand(lhs - rhs), x, y)
    if declined:
        return None
    # Only x and y may be letters: "= z" or "+ 2kx" has no numeric centre or radius,
    # and comparing a letter with 0 below has no truth value.
    if not all(term.is_number and term.is_extended_real for term in poly.coeffs()):
        return None
    coefficient = poly.coeff_monomial(x**2)
    if (
        coefficient == 0
        or poly.coeff_monomial(y**2) != coefficient
        or poly.coeff_monomial(x * y) != 0
    ):
        return None
    if poly.total_degree() != 2:
        return None
    d = poly.coeff_monomial(x) / coefficient
    e = poly.coeff_monomial(y) / coefficient
    f = poly.coeff_monomial(1) / coefficient
    a, b = -d / 2, -e / 2
    square = a**2 + b**2 - f
    if square <= 0:
        return None
    radius = sqrt(square)
    return _Solved(
        (math_line(latex(lhs) + " = " + latex(rhs)),),
        (math_line(r"\text{centre and radius}"),),
        (math_line(r"(x - a)^2 + (y - b)^2 = r^2", "Complete the square in x and in y"),),
        (
            math_line(
                rf"{_signed(float(a), 'x')}^2 - {latex(a**2)} + "
                rf"{_signed(float(b), 'y')}^2 - {latex(b**2)}"
                rf" + {latex(f)} = 0".replace("+ -", "- ")
            ),
            math_line(
                rf"{_signed(float(a), 'x')}^2 + {_signed(float(b), 'y')}^2 = {latex(square)}"
            ),
        ),
        rf"\text{{centre }} ({latex(a)}, {latex(b)}),\ r = {latex(radius)}",
    )


def _triangle_vertices(numbers: list[float], words: list[str]) -> _Solved | None:
    x1, y1, x2, y2, x3, y3 = numbers
    twice = x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)
    if twice == 0:
        return None
    points = rf"({_n(x1)}, {_n(y1)}),\ ({_n(x2)}, {_n(y2)}),\ ({_n(x3)}, {_n(y3)})"
    return _Solved(
        (math_line(points, "vertices"),),
        (math_line("A", "area"),),
        (
            math_line(
                r"A = \frac{1}{2}\left|x_1(y_2 - y_3) + x_2(y_3 - y_1) + x_3(y_1 - y_2)\right|",
                "Shoelace formula",
            ),
        ),
        (
            math_line(
                rf"A = \frac{{1}}{{2}}\left|{_n(x1)}({_n(y2)} - {_n(y3)})"
                rf" + {_n(x2)}({_n(y3)} - {_n(y1)}) + {_n(x3)}({_n(y1)} - {_n(y2)})\right|"
                rf" = \frac{{1}}{{2}}\left|{_n(twice)}\right|"
            ),
        ),
        _n(abs(twice) / 2),
    )


def _perpendicular_gradient(intent: MathIntent, words: list[str]) -> _Solved | None:
    from sympy import Poly, Rational, Symbol, latex, nsimplify

    from app.modules.math import solve as math_solve

    x = Symbol("x")
    with sympy_decline() as declined:
        line = math_solve.parse_expression((intent.expr or "").strip(), ["x"])
        poly = Poly(line, x)
    if declined:
        return None
    if poly.degree() != 1:
        return None
    m = nsimplify(poly.coeff_monomial(x))
    if words[0] == "parallel":
        return _Solved(
            (math_line(f"y = {latex(line)}"),),
            (math_line("m", "gradient of a parallel line"),),
            (math_line(r"m_{\parallel} = m", "Parallel lines have equal gradients"),),
            (math_line(f"m = {latex(m)}"),),
            latex(m),
        )
    if m == 0:
        return None
    perpendicular = -Rational(1) / m
    return _Solved(
        (math_line(f"y = {latex(line)}"),),
        (math_line(r"m_{\perp}", "gradient of a perpendicular line"),),
        (math_line(r"m_{\perp} = -\frac{1}{m}", "Perpendicular gradients multiply to -1"),),
        (math_line(rf"m = {latex(m)}, \quad m_{{\perp}} = -\frac{{1}}{{{latex(m)}}}"),),
        latex(perpendicular),
    )


def _perpendicular_bisector(numbers: list[float], words: list[str]) -> _Solved | None:
    from sympy import Rational, latex, nsimplify

    x1, y1, x2, y2 = (nsimplify(value) for value in numbers)
    if (x1, y1) == (x2, y2):
        return None
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    rows = [math_line(rf"M = \left({latex(mx)}, {latex(my)}\right)", "midpoint")]
    if y1 == y2:
        rows.append(text_line("the segment is horizontal, so the bisector is vertical"))
        answer = f"x = {latex(mx)}"
    elif x1 == x2:
        rows.append(text_line("the segment is vertical, so the bisector is horizontal"))
        answer = f"y = {latex(my)}"
    else:
        slope = (y2 - y1) / (x2 - x1)
        perpendicular = -Rational(1) / slope
        rows.append(
            math_line(
                rf"m = \frac{{{latex(y2)} - {latex(y1)}}}{{{latex(x2)} - {latex(x1)}}}"
                rf" = {latex(slope)},"
                rf" \quad m_{{\perp}} = {latex(perpendicular)}"
            )
        )
        rows.append(
            math_line(rf"y - {latex(my)} = {latex(perpendicular)}\left(x - {latex(mx)}\right)")
        )
        from app.modules.math.tools.school.curve_points import _line_tex

        answer = _line_tex(perpendicular, my - perpendicular * mx, "x")
    return _Solved(
        (math_line(rf"({latex(x1)}, {latex(y1)}),\ ({latex(x2)}, {latex(y2)})"),),
        (math_line(r"\text{the perpendicular bisector}"),),
        (math_line(r"y - y_M = m_{\perp}(x - x_M)", "Through the midpoint, perpendicular"),),
        tuple(rows),
        answer,
    )


def reflection_line(numbers: list[float], words: list[str]) -> _Solved | None:
    """The mirror that takes a point to its image: the perpendicular bisector of the two."""
    bisector = _perpendicular_bisector(numbers, words)
    if bisector is None:
        return None
    x1, y1, x2, y2 = numbers
    return replace(
        bisector,
        given=(
            math_line(rf"P = ({_n(x1)}, {_n(y1)})", "the point"),
            math_line(rf"P' = ({_n(x2)}, {_n(y2)})", "its image"),
        ),
        find=(math_line(r"\text{the line of reflection}"),),
        formula=(
            math_line(
                r"\text{line of reflection} = \text{perpendicular bisector of } PP'",
                "every point on the mirror is as far from P as from P'",
            ),
            *bisector.formula,
        ),
    )
