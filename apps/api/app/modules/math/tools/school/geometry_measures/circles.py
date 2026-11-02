"""Circles from their circumference or area, semicircles and hemispheres."""

from __future__ import annotations

import math
from fractions import Fraction

from app.modules.math.tools.school.geometry_measures.working import _approx, _n, _Solved, _unit
from app.services.workout import math_line


def _pi_times(coefficient: Fraction) -> str:
    """``8\\pi``, ``\\frac{9}{2}\\pi``."""
    if coefficient == 1:
        return r"\pi"
    if coefficient.denominator == 1:
        return rf"{coefficient.numerator}\pi"
    return rf"\frac{{{coefficient.numerator}}}{{{coefficient.denominator}}}\pi"


def _pi_answer(coefficient: float, unit: str | None, power: int) -> str:
    """Exactly ``8\\pi`` when the coefficient is a short fraction, always with its decimal."""
    exact = Fraction(coefficient).limit_denominator(12)
    value = coefficient * math.pi
    decimal = rf"{_approx(value)}{_unit(unit, power)}"
    if abs(float(exact) - coefficient) < 1e-9:
        return rf"{_pi_times(exact)} \approx {decimal}"
    return rf"\approx {decimal}"


def _radius(kind: str, value: float) -> tuple[float, str]:
    """The radius, and its Given line, from a radius or a diameter."""
    if kind == "diameter":
        return value / 2, math_line(f"d = {_n(value)}", "diameter")
    return value, math_line(f"r = {_n(value)}", "radius")


def _semicircle(numbers: list[float], words: list[str]) -> _Solved | None:
    quantity, kind = words[0], words[1]
    unit = words[2] if len(words) > 2 else None
    r, given = _radius(kind, numbers[0])
    radius_row = (
        (math_line(rf"r = \frac{{{_n(numbers[0])}}}{{2}} = {_n(r)}"),) if kind == "diameter" else ()
    )
    if quantity == "area":
        return _Solved(
            (given,),
            (math_line("A", "area of the semicircle"),),
            (math_line(r"A = \frac{1}{2}\pi r^2", "Semicircle area"),),
            (*radius_row, math_line(rf"A = \frac{{1}}{{2}}\pi({_n(r)})^2")),
            _pi_answer(r * r / 2, unit, 2),
        )
    if quantity.startswith("arc"):
        return _Solved(
            (given,),
            (math_line("L", "the curved edge"),),
            (math_line(r"L = \pi r", "Half the circumference"),),
            (*radius_row, math_line(rf"L = \pi({_n(r)})")),
            _pi_answer(r, unit, 1),
        )
    value = math.pi * r + 2 * r
    return _Solved(
        (given,),
        (math_line("P", "perimeter of the semicircle"),),
        (math_line(r"P = \pi r + 2r", "Curved edge plus the diameter"),),
        (*radius_row, math_line(rf"P = \pi({_n(r)}) + 2({_n(r)})")),
        rf"{_n(r)}\pi + {_n(2 * r)} \approx {_approx(value)}{_unit(unit)}",
    )


def _hemisphere(numbers: list[float], words: list[str]) -> _Solved | None:
    quantity, kind = words[0], words[1]
    unit = words[2] if len(words) > 2 else None
    r, given = _radius(kind, numbers[0])
    if quantity == "volume":
        return _Solved(
            (given,),
            (math_line("V", "volume of the hemisphere"),),
            (math_line(r"V = \frac{2}{3}\pi r^3", "Half a sphere"),),
            (math_line(rf"V = \frac{{2}}{{3}}\pi({_n(r)})^3"),),
            _pi_answer(2 * r**3 / 3, unit, 3),
        )
    curved = quantity.startswith("curved")
    return _Solved(
        (given,),
        (math_line("S", "curved surface" if curved else "surface area, flat face included"),),
        (
            math_line(r"S = 2\pi r^2", "Half a sphere's surface")
            if curved
            else math_line(
                r"S = 2\pi r^2 + \pi r^2 = 3\pi r^2", "Curved surface plus the flat circle"
            ),
        ),
        (math_line(rf"S = {'2' if curved else '3'}\pi({_n(r)})^2"),),
        _pi_answer((2 if curved else 3) * r * r, unit, 2),
    )


def _circle_from_circumference(numbers: list[float], words: list[str]) -> _Solved | None:
    asked = words[0]
    unit = words[1] if len(words) > 1 else None
    c = numbers[0]
    r = c / (2 * math.pi)
    rows = [math_line(rf"r = \frac{{C}}{{2\pi}} = \frac{{{_n(c)}}}{{2\pi}} \approx {_approx(r)}")]
    if asked == "radius":
        answer = rf"\approx {_approx(r)}{_unit(unit)}"
    elif asked == "diameter":
        rows.append(math_line(rf"d = 2r \approx {_approx(2 * r)}"))
        answer = rf"\approx {_approx(c / math.pi)}{_unit(unit)}"
    else:
        rows.append(math_line(rf"A = \pi r^2 \approx \pi({_approx(r)})^2"))
        answer = rf"\approx {_approx(c * c / (4 * math.pi))}{_unit(unit, 2)}"
    return _Solved(
        (math_line(f"C = {_n(c)}", "circumference"),),
        (math_line(asked[0] if asked != "area" else "A", asked),),
        (math_line(r"C = 2\pi r", "Circumference"),),
        tuple(rows),
        answer,
    )


def _fraction_tex(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    sign = "-" if value < 0 else ""
    return rf"{sign}\frac{{{abs(value.numerator)}}}{{{value.denominator}}}"


def _circle_from_circumference_pi(numbers: list[float], words: list[str]) -> _Solved | None:
    """``C = 10π``: r = 5 exactly, and the area is 25π."""
    asked = words[0]
    unit = words[1] if len(words) > 1 else None
    k = Fraction(numbers[0]).limit_denominator(1000)
    if k <= 0 or abs(float(k) - numbers[0]) > 1e-9:
        return None
    r = k / 2
    rows = [
        math_line(rf"r = \frac{{C}}{{2\pi}} = \frac{{{_pi_times(k)}}}{{2\pi}} = {_fraction_tex(r)}")
    ]
    if asked == "radius":
        answer = f"{_fraction_tex(r)}{_unit(unit)}"
    elif asked == "diameter":
        rows.append(math_line(rf"d = 2r = {_fraction_tex(k)}"))
        answer = f"{_fraction_tex(k)}{_unit(unit)}"
    else:
        rows.append(
            math_line(rf"A = \pi r^2 = \pi\left({_fraction_tex(r)}\right)^2 = {_pi_times(r * r)}")
        )
        answer = _pi_answer(float(r * r), unit, 2)
    return _Solved(
        (math_line(f"C = {_pi_times(k)}", "circumference"),),
        (math_line(asked[0] if asked != "area" else "A", asked),),
        (math_line(r"C = 2\pi r", "Circumference"),),
        tuple(rows),
        answer,
    )


def _circle_from_area_pi(numbers: list[float], words: list[str]) -> _Solved | None:
    """``A = 16π``: r = 4 exactly, and the circumference is 8π."""
    asked = words[0]
    unit = words[1] if len(words) > 1 else None
    k = Fraction(numbers[0]).limit_denominator(1000)
    if k <= 0 or abs(float(k) - numbers[0]) > 1e-9:
        return None
    root_num, root_den = math.isqrt(k.numerator), math.isqrt(k.denominator)
    if root_num * root_num != k.numerator or root_den * root_den != k.denominator:
        # r = √k is not a whole or a fraction: the decimal rules already cover it.
        return _circle_from_area([numbers[0] * math.pi], words)
    r = Fraction(root_num, root_den)
    rows = [
        math_line(
            rf"r = \sqrt{{\frac{{A}}{{\pi}}}} = \sqrt{{\frac{{{_pi_times(k)}}}{{\pi}}}}"
            rf" = {_fraction_tex(r)}"
        )
    ]
    if asked == "radius":
        answer = f"{_fraction_tex(r)}{_unit(unit)}"
    elif asked == "diameter":
        rows.append(math_line(rf"d = 2r = {_fraction_tex(2 * r)}"))
        answer = f"{_fraction_tex(2 * r)}{_unit(unit)}"
    else:
        rows.append(
            math_line(rf"C = 2\pi r = 2\pi\left({_fraction_tex(r)}\right) = {_pi_times(2 * r)}")
        )
        answer = _pi_answer(float(2 * r), unit, 1)
    return _Solved(
        (math_line(f"A = {_pi_times(k)}", "area"),),
        (math_line("C" if asked == "circumference" else asked[0], asked),),
        (math_line(r"A = \pi r^2", "Circle area"),),
        tuple(rows),
        answer,
    )


def _circle_from_area(numbers: list[float], words: list[str]) -> _Solved | None:
    asked = words[0]
    unit = words[1] if len(words) > 1 else None
    a = numbers[0]
    if a <= 0:
        return None
    r = math.sqrt(a / math.pi)
    rows = [
        math_line(
            rf"r = \sqrt{{\frac{{A}}{{\pi}}}} = \sqrt{{\frac{{{_n(a)}}}{{\pi}}}}"
            rf" \approx {_approx(r)}"
        )
    ]
    if asked == "radius":
        answer = rf"\approx {_approx(r)}{_unit(unit)}"
    elif asked == "diameter":
        rows.append(math_line(rf"d = 2r \approx 2({_approx(r)})"))
        answer = rf"\approx {_approx(2 * r)}{_unit(unit)}"
    else:
        rows.append(math_line(rf"C = 2\pi r \approx 2\pi({_approx(r)})"))
        answer = rf"\approx {_approx(2 * math.pi * r)}{_unit(unit)}"
    return _Solved(
        (math_line(f"A = {_n(a)}", "area"),),
        (math_line("C" if asked == "circumference" else asked[0], asked),),
        (math_line(r"A = \pi r^2", "Circle area"),),
        tuple(rows),
        answer,
    )
