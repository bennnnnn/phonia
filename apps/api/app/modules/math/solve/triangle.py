"""The triangle laws, each computed once: the cosine and sine rules, Heron's formula, validity.

A result is exact (SymPy) when every angle in it has an exact cosine of the form ±√q: 0°, 30°,
45°, 60°, 90° and their supplements, the angles a student learns exact values for. SymPy
decides which angles those are (the cosine squared is rational), not a table. Any other angle
gives one SymPy ``Float``. A side is the decimal it was written as: 2.5 is 5/2.
"""

from __future__ import annotations

import math

from sympy import Expr, Float, Rational, acos, cos, pi, sin, sqrt

from app.services.solving import SolveServiceError


def triangle_valid(a: float, b: float, c: float) -> bool:
    """Three positive sides, each shorter than the other two together."""
    return min(a, b, c) > 0 and a + b > c and a + c > b and b + c > a


def cos_degrees(angle: float) -> Expr:
    """cos of an angle in degrees: exact at a school angle, else a ``Float``."""
    return _exact_or_float(cos(_radians(angle)), math.cos(math.radians(angle)))


def cosine_rule_side(a: float, b: float, angle_c: float) -> Expr:
    """c from two sides and the angle between them: c² = a² + b² - 2ab cos C."""
    if min(a, b) <= 0 or not 0 < angle_c < 180:
        raise SolveServiceError("two positive sides and an angle between 0° and 180°")
    x, y = _rational(a), _rational(b)
    return _settled(sqrt(x**2 + y**2 - 2 * x * y * cos_degrees(angle_c)))


def cosine_rule_cosine(a: float, b: float, c: float) -> Rational:
    """cos C, opposite c, exactly: cos C = (a² + b² - c²) / 2ab."""
    if not triangle_valid(a, b, c):
        raise SolveServiceError("these three side lengths cannot form a triangle")
    x, y, z = _rational(a), _rational(b), _rational(c)
    return (x**2 + y**2 - z**2) / (2 * x * y)


def cosine_rule_angle(a: float, b: float, c: float) -> Expr:
    """C in degrees, opposite c. Exact at 60°, 90° and 120°, the angles a rational cosine has."""
    cosine = cosine_rule_cosine(a, b, c)
    degrees = acos(cosine) * 180 / pi
    if degrees.is_Rational:
        return degrees
    return Float(math.degrees(math.acos(float(cosine))))


def sine_rule_side(side: float, opposite: float, angle: float) -> Expr:
    """The side opposite ``angle``, from a side and the angle opposite it: t / sin T = k / sin K."""
    if side <= 0 or min(opposite, angle) <= 0 or opposite + angle >= 180:
        raise SolveServiceError("a positive side and two angles of one triangle")
    return _settled(_rational(side) * _sin_degrees(angle) / _sin_degrees(opposite))


def heron_area(a: float, b: float, c: float) -> float:
    """Area from three sides: A = √(s(s - a)(s - b)(s - c)), with s half the perimeter."""
    if not triangle_valid(a, b, c):
        raise SolveServiceError("these three side lengths cannot form a triangle")
    s = (a + b + c) / 2
    return math.sqrt(s * (s - a) * (s - b) * (s - c))


def _sin_degrees(angle: float) -> Expr:
    return _exact_or_float(sin(_radians(angle)), math.sin(math.radians(angle)))


def _exact_or_float(exact: Expr, approximate: float) -> Expr:
    return exact if (exact**2).is_rational else Float(approximate)


def _radians(angle: float) -> Expr:
    return _rational(angle) * pi / 180


def _rational(value: float) -> Rational:
    return Rational(str(value))


def _settled(value: Expr) -> Expr:
    """Exact, or one ``Float``: an exact sine times an inexact one is evaluated."""
    return value.evalf() if value.has(Float) else value
