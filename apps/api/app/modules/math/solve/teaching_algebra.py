"""Polynomial division, the unit circle, and point transformations."""

from __future__ import annotations

import math
from fractions import Fraction

from sympy import QQ, Poly, Symbol, div, latex, simplify
from sympy.core.sympify import SympifyError
from sympy.polys.polyerrors import GeneratorsError, PolynomialError

from app.modules.math.schemas.teaching import (
    PolynomialDivisionSpec,
    PolynomialTermStep,
    TransformationSpec,
    TransformPoint,
    UnitCircleSpec,
)

_X = Symbol("x")
_STANDARD_DEGREES = (0, 30, 45, 60, 90, 120, 135, 150, 180, 210, 225, 240, 270, 300, 315, 330)
_RADIANS = {
    0: "0",
    30: r"\frac{\pi}{6}",
    45: r"\frac{\pi}{4}",
    60: r"\frac{\pi}{3}",
    90: r"\frac{\pi}{2}",
    120: r"\frac{2\pi}{3}",
    135: r"\frac{3\pi}{4}",
    150: r"\frac{5\pi}{6}",
    180: r"\pi",
    210: r"\frac{7\pi}{6}",
    225: r"\frac{5\pi}{4}",
    240: r"\frac{4\pi}{3}",
    270: r"\frac{3\pi}{2}",
    300: r"\frac{5\pi}{3}",
    315: r"\frac{7\pi}{4}",
    330: r"\frac{11\pi}{6}",
}
_ALLOWED_POLY = set("0123456789xX+-*/^(). ")


def _polynomial(source: str) -> Poly | None:
    if not source or len(source) > 80 or any(char not in _ALLOWED_POLY for char in source):
        return None
    if "xx" in source.lower():
        return None
    from app.modules.math.solve.parse import parse_expression
    from app.services.solving import SolveServiceError

    try:
        parsed_expr = parse_expression(source, ["x"])
    except SolveServiceError:
        return None
    if isinstance(parsed_expr, tuple) or getattr(parsed_expr, "free_symbols", set()) - {_X}:
        return None
    try:
        parsed = Poly(parsed_expr, _X, domain=QQ)
    except (TypeError, ValueError, SympifyError, PolynomialError, GeneratorsError):
        return None
    if parsed.free_symbols - {_X}:
        return None
    if parsed.degree() > 6:
        return None
    return parsed


def polynomial_division(dividend: str, divisor: str, method: str) -> PolynomialDivisionSpec | None:
    left, right = _polynomial(dividend), _polynomial(divisor)
    if left is None or right is None or right.degree() < 1 or right.as_expr() == 0:
        return None
    if method == "synthetic" and not _synthetic_root(right):
        return None
    quotient, remainder = div(left, right, domain=QQ)
    rebuilt = simplify(quotient.as_expr() * right.as_expr() + remainder.as_expr() - left.as_expr())
    if rebuilt != 0:
        return None
    stepped = _long_steps(left, right)
    if stepped is None:
        return None
    steps, stepped_remainder = stepped
    if simplify(stepped_remainder.as_expr() - remainder.as_expr()) != 0:
        return None
    root = _synthetic_root(right) if method == "synthetic" else None
    synthetic = _synthetic_rows(left, root) if root is not None else None
    if method == "synthetic" and synthetic is None:
        return None
    quotient_text = latex(quotient.as_expr())
    remainder_text = latex(remainder.as_expr())
    answer = (
        quotient_text
        if remainder.as_expr() == 0
        else f"{quotient_text} + {remainder_text}/({latex(right.as_expr())})"
    )
    speech = f"The quotient is {quotient.as_expr()} and the remainder is {remainder.as_expr()}."
    top, multiply, bottom = synthetic or ([], [], [])
    return PolynomialDivisionSpec(
        method="synthetic" if method == "synthetic" else "long",
        dividend=latex(left.as_expr()),
        divisor=latex(right.as_expr()),
        quotient=quotient_text,
        remainder=remainder_text,
        steps=steps,
        synthetic_root=None if root is None else str(root),
        synthetic_top=top,
        synthetic_multiply=multiply,
        synthetic_bottom=bottom,
        answer=answer,
        speech=speech,
    )


def _synthetic_root(divisor: Poly) -> int | None:
    if divisor.degree() != 1 or divisor.LC() != 1:
        return None
    root = -divisor.TC()
    if root != int(root) or abs(int(root)) > 20:
        return None
    return int(root)


def _long_steps(dividend: Poly, divisor: Poly) -> tuple[list[PolynomialTermStep], Poly] | None:
    remainder = dividend
    steps: list[PolynomialTermStep] = []
    for _ in range(8):
        if remainder.as_expr() == 0 or remainder.degree() < divisor.degree():
            return steps, remainder
        lead = remainder.LC() / divisor.LC()
        power = remainder.degree() - divisor.degree()
        term = lead * _X**power
        product = divisor.as_expr() * term
        remainder = Poly(simplify(remainder.as_expr() - product), _X, domain=QQ)
        steps.append(
            PolynomialTermStep(
                term=latex(simplify(term)),
                product=latex(simplify(product)),
                remainder=latex(remainder.as_expr()),
            )
        )
    return None


def _synthetic_rows(dividend: Poly, root: int) -> tuple[list[str], list[str], list[str]] | None:
    coefficients = [dividend.nth(power) for power in range(dividend.degree(), -1, -1)]
    if any(coef != int(coef) for coef in coefficients):
        return None
    top = [str(int(coef)) for coef in coefficients]
    brought = int(coefficients[0])
    multiply: list[str] = []
    bottom = [str(brought)]
    for coef in coefficients[1:]:
        product = brought * root
        brought = int(coef) + product
        multiply.append(str(product))
        bottom.append(str(brought))
    return top, multiply, bottom


def standard_degrees(degrees: int) -> int | None:
    if abs(degrees) > 720:
        return None
    reduced = degrees % 360
    if reduced not in _STANDARD_DEGREES:
        return None
    return reduced


def unit_circle_spec(degrees: int, answer: str | None = None) -> UnitCircleSpec | None:
    reduced = standard_degrees(degrees)
    if reduced is None or abs(degrees) > 360:
        return None
    from app.modules.math.school import evaluate_trig_degrees
    from app.services.solving import SolveServiceError

    try:
        cosine = evaluate_trig_degrees("cos", float(degrees))
        sine = evaluate_trig_degrees("sin", float(degrees))
        tangent = (
            "undefined" if reduced in {90, 270} else evaluate_trig_degrees("tan", float(degrees))
        )
    except SolveServiceError:
        return None
    shown = degrees if -360 <= degrees <= 360 else reduced
    point = rf"\left({cosine}, {sine}\right)"
    speech = (
        f"{shown} degrees is the point with cosine {cosine} and sine {sine} on the unit circle."
    )
    return UnitCircleSpec(
        degrees=shown,
        radians=_RADIANS[reduced],
        cosine=cosine,
        sine=sine,
        tangent=tangent,
        plot_x=round(math.cos(math.radians(reduced)), 6),
        plot_y=round(math.sin(math.radians(reduced)), 6),
        answer=answer or point,
        speech=speech,
    )


def _point_list(source: str) -> list[tuple[Fraction, Fraction]] | None:
    chunks = [chunk.strip() for chunk in source.split(";") if chunk.strip()]
    if not 1 <= len(chunks) <= 4:
        return None
    points: list[tuple[Fraction, Fraction]] = []
    for chunk in chunks:
        left, separator, right = chunk.partition(",")
        if not separator:
            return None
        try:
            x_value, y_value = Fraction(left), Fraction(right)
        except (ValueError, ZeroDivisionError):
            return None
        if abs(x_value) > 20 or abs(y_value) > 20:
            return None
        points.append((x_value, y_value))
    return points


def _format_coord(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def transformation_spec(kind: str, points: str, detail: str) -> TransformationSpec | None:
    originals = _point_list(points)
    if originals is None:
        return None
    images = [_map_point(kind, point, detail) for point in originals]
    if any(image is None for image in images):
        return None
    mapped = [image for image in images if image is not None]
    rule = _rule_text(kind, detail)
    if rule is None:
        return None
    before = [TransformPoint(x=_format_coord(x), y=_format_coord(y)) for x, y in originals]
    after = [TransformPoint(x=_format_coord(x), y=_format_coord(y)) for x, y in mapped]
    rendered = ", ".join(f"({point.x}, {point.y})" for point in after)
    speech = f"{rule} sends the point to {rendered}."
    return TransformationSpec.model_validate(
        {
            "kind": kind,
            "rule": rule,
            "before": [point.model_dump() for point in before],
            "after": [point.model_dump() for point in after],
            "answer": rendered,
            "speech": speech,
        }
    )


def _rule_text(kind: str, detail: str) -> str | None:
    if kind == "translation":
        shift = _point_list(detail)
        if shift is None or len(shift) != 1:
            return None
        dx, dy = shift[0]
        return f"Translate by ({_format_coord(dx)}, {_format_coord(dy)})"
    if kind == "reflection" and detail in {"x-axis", "y-axis", "origin"}:
        return f"Reflect across the {detail}"
    if kind == "rotation" and detail in {"90", "180", "270"}:
        return f"Rotate {detail} degrees about the origin"
    if kind == "dilation":
        try:
            factor = Fraction(detail)
        except (ValueError, ZeroDivisionError):
            return None
        if factor == 0 or abs(factor) > 12:
            return None
        return f"Dilate by {_format_coord(factor)} about the origin"
    return None


def _map_point(
    kind: str, point: tuple[Fraction, Fraction], detail: str
) -> tuple[Fraction, Fraction] | None:
    x_value, y_value = point
    if kind == "translation":
        shift = _point_list(detail)
        if shift is None or len(shift) != 1:
            return None
        return x_value + shift[0][0], y_value + shift[0][1]
    if kind == "reflection" and detail == "x-axis":
        return x_value, -y_value
    if kind == "reflection" and detail == "y-axis":
        return -x_value, y_value
    if kind == "reflection" and detail == "origin":
        return -x_value, -y_value
    if kind == "rotation" and detail == "90":
        return -y_value, x_value
    if kind == "rotation" and detail == "180":
        return -x_value, -y_value
    if kind == "rotation" and detail == "270":
        return y_value, -x_value
    if kind == "dilation":
        try:
            factor = Fraction(detail)
        except (ValueError, ZeroDivisionError):
            return None
        if factor == 0 or abs(factor) > 12:
            return None
        return x_value * factor, y_value * factor
    return None
