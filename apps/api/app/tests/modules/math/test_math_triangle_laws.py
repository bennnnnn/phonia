"""The triangle laws in ``solve/triangle.py``: one implementation, exact where SymPy has a value.

Before ES-10 the cosine rule was computed in three places with three validity checks. The
two-sides-and-an-angle copy knew exact cosines only from a hand table of 60°, 120° and 90°,
so 30°, 45° and 150° came out as decimals. Each expected value here is worked from the
textbook formula, not from the code under test.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sympy import Expr, Float, Integer, Rational, simplify, sqrt

from app.modules.math.solve.triangle import (
    cos_degrees,
    cosine_rule_angle,
    cosine_rule_cosine,
    cosine_rule_side,
    heron_area,
    sine_rule_side,
    triangle_valid,
)
from app.services.solving import SolveServiceError


def _same(got: Expr, want: Expr) -> bool:
    return bool(simplify(got - want) == 0)


@pytest.mark.parametrize(
    ("angle", "exact"),
    [
        (0, Integer(1)),
        (30, sqrt(3) / 2),
        (45, sqrt(2) / 2),
        (60, Rational(1, 2)),
        (90, Integer(0)),
        (120, Rational(-1, 2)),
        (135, -sqrt(2) / 2),
        (150, -sqrt(3) / 2),
        (180, Integer(-1)),
    ],
)
def test_cos_degrees_is_exact_at_the_school_angles(angle: float, exact: Expr) -> None:
    got = cos_degrees(angle)
    assert not got.has(Float)
    assert _same(got, exact)


@pytest.mark.parametrize("angle", [15, 36, 40, 72, 22.5, 37.5])
def test_cos_degrees_is_a_float_at_other_angles(angle: float) -> None:
    # 15° and 72° have closed forms, but not ones a student is taught to use.
    got = cos_degrees(angle)
    assert got.is_Float
    assert float(got) == pytest.approx(math.cos(math.radians(angle)))


@pytest.mark.parametrize(
    ("a", "b", "angle", "exact"),
    [
        # Pinned before the move: the hand table's angles.
        (7, 9, 60, sqrt(67)),
        (5, 5, 120, 5 * sqrt(3)),
        (3, 4, 90, Integer(5)),
        # Missed by the hand table, decimals before.
        (5, 8, 30, sqrt(89 - 40 * sqrt(3))),
        (4, 6, 45, sqrt(52 - 24 * sqrt(2))),
        (3, 5, 150, sqrt(34 + 15 * sqrt(3))),
        (4, 6, 135, sqrt(52 + 24 * sqrt(2))),
        # A side is the decimal written: 2.5 is 5/2.
        (2.5, 3, 60, sqrt(31) / 2),
    ],
)
def test_cosine_rule_side_is_exact_at_a_school_angle(
    a: float, b: float, angle: float, exact: Expr
) -> None:
    got = cosine_rule_side(a, b, angle)
    assert not got.has(Float)
    assert _same(got, exact)


@pytest.mark.parametrize(("a", "b", "angle", "value"), [(6, 10, 72, 9.946), (7, 9, 40, 5.786)])
def test_cosine_rule_side_is_a_float_at_any_other_angle(
    a: float, b: float, angle: float, value: float
) -> None:
    got = cosine_rule_side(a, b, angle)
    assert got.is_Float
    assert float(got) == pytest.approx(value, abs=5e-4)


@pytest.mark.parametrize(
    ("sides", "cosine"),
    [
        ((7, 8, 9), Rational(2, 7)),
        ((3, 5, 7), Rational(-1, 2)),
        # Not the nearest small fraction of the float (-68/175).
        ((2.31, 3.77, 5.13), Rational(-67679, 174174)),
    ],
)
def test_cosine_rule_cosine_is_exact(sides: tuple[float, float, float], cosine: Expr) -> None:
    assert cosine_rule_cosine(*sides) == cosine


@pytest.mark.parametrize(("sides", "angle"), [((3, 5, 7), 120), ((3, 4, 5), 90), ((5, 5, 5), 60)])
def test_cosine_rule_angle_is_exact_when_the_cosine_is(
    sides: tuple[float, float, float], angle: int
) -> None:
    got = cosine_rule_angle(*sides)
    assert got == angle
    assert got.is_Rational


@pytest.mark.parametrize(
    ("sides", "angle"),
    [
        # cos C = 2/7, 2/3 and 1/7: no exact angle.
        ((7, 8, 9), 73.398),
        ((8, 9, 7), 48.190),
        ((2.5, 3.5, 4), 81.787),
    ],
)
def test_cosine_rule_angle_is_a_float_otherwise(
    sides: tuple[float, float, float], angle: float
) -> None:
    got = cosine_rule_angle(*sides)
    assert got.is_Float
    assert float(got) == pytest.approx(angle, abs=5e-4)


@pytest.mark.parametrize(
    ("side", "opposite", "angle", "exact"),
    [
        (5, 30, 90, Integer(10)),
        (5, 90, 30, Rational(5, 2)),
        (8, 45, 30, 4 * sqrt(2)),
        (10, 30, 60, 10 * sqrt(3)),
    ],
)
def test_sine_rule_side_is_exact_at_school_angles(
    side: float, opposite: float, angle: float, exact: Expr
) -> None:
    got = sine_rule_side(side, opposite, angle)
    assert not got.has(Float)
    assert _same(got, exact)


@pytest.mark.parametrize(
    ("side", "opposite", "angle", "value"),
    # 40° is not exact, so neither is a product with it; 30° alone would be.
    [(10, 40, 60, 13.473), (10, 30, 40, 12.856)],
)
def test_sine_rule_side_is_one_float_when_an_angle_is_not_exact(
    side: float, opposite: float, angle: float, value: float
) -> None:
    got = sine_rule_side(side, opposite, angle)
    assert got.is_Float
    assert float(got) == pytest.approx(value, abs=5e-4)


@pytest.mark.parametrize(("sides", "area"), [((3, 4, 5), 6.0), ((5, 6, 7), 6 * math.sqrt(6))])
def test_heron_area(sides: tuple[float, float, float], area: float) -> None:
    assert heron_area(*sides) == pytest.approx(area)


@pytest.mark.parametrize(
    ("sides", "valid"),
    [
        ((3, 4, 5), True),
        ((0.5, 0.5, 0.9), True),
        ((1, 1, 10), False),
        ((1, 2, 3), False),  # flat
        ((0, 1, 1), False),
        ((-1, 2, 2), False),
    ],
)
def test_triangle_valid(sides: tuple[float, float, float], valid: bool) -> None:
    assert triangle_valid(*sides) is valid
    assert triangle_valid(*reversed(sides)) is valid


@pytest.mark.parametrize(
    "call",
    [
        lambda: cosine_rule_side(0, 4, 60),
        lambda: cosine_rule_side(3, 4, 0),
        lambda: cosine_rule_side(3, 4, 180),
        lambda: cosine_rule_angle(1, 1, 10),
        lambda: sine_rule_side(5, 100, 80),
        lambda: sine_rule_side(-5, 30, 60),
        lambda: heron_area(1, 2, 3),
    ],
)
def test_impossible_triangles_raise(call: Callable[[], object]) -> None:
    with pytest.raises(SolveServiceError):
        call()


_SIDES = st.floats(min_value=0.5, max_value=100).map(lambda value: round(value, 2))


@given(a=_SIDES, b=_SIDES, angle=st.integers(min_value=1, max_value=179))
@settings(max_examples=80, deadline=None, derandomize=True)
def test_the_laws_agree_on_one_triangle(a: float, b: float, angle: int) -> None:
    """The side the cosine rule gives returns its angle, and the sine rule agrees."""
    c = float(cosine_rule_side(a, b, angle))
    assert float(cosine_rule_angle(a, b, c)) == pytest.approx(angle, abs=1e-6)
    angle_a = float(cosine_rule_angle(b, c, a))
    assert float(sine_rule_side(a, angle_a, angle)) == pytest.approx(c, rel=1e-6)
