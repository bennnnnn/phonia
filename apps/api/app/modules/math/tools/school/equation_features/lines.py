"""Where a graph meets the axes, and straight lines: the y- and x-intercepts, a line's
slope and slope-intercept form, and the line through a point parallel or perpendicular
to another."""

from __future__ import annotations

from typing import Any

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.school.equation_features.forms import (
    _at,
    _bracket,
    _explicit,
    _line_tex,
    _linear,
    _num,
    _point,
    _Solved,
    _symbols,
    _tex,
)
from app.services.workout import Workout, math_line, solve_for_line


def _y_intercept(intent: MathIntent) -> _Solved | None:
    (x,) = _symbols("x")
    explicit = _explicit(intent)
    if explicit is not None:
        value = explicit.subs(x, 0)
        given = f"y = {_tex(explicit)}"
        working = rf"y = {_at(explicit, 0)} = {_num(value)}"
    else:
        line = _linear(intent)
        if line is None:
            return None
        a, b, c = line
        if b == 0:
            return None
        value = c / b
        given = f"{_tex(a * x + b * _symbols('y')[0])} = {_num(c)}"
        working = rf"{_num(b)}y = {_num(c)} \Rightarrow y = {_num(value)}"
    if not value.is_number or not value.is_finite or not value.is_real:
        return None
    answer = _point(0, value)
    workout = Workout(
        given=(math_line(given),),
        find=(math_line(r"\left(0, y\right)", "y-intercept"),),
        formula=(math_line("x = 0", "on the y-axis"),),
        substitution=(math_line(working),),
    )
    return workout, answer, [f"y-intercept: (0, {value})"]


def _x_intercepts(intent: MathIntent) -> _Solved | None:
    from sympy import Poly, S, solveset

    x, y = _symbols("x", "y")
    explicit = _explicit(intent)
    if explicit is not None:
        if not explicit.free_symbols or Poly(explicit, x).degree() not in {1, 2}:
            return None
        roots = sorted(solveset(explicit, x, domain=S.Reals), key=lambda value: float(value))
        given = f"y = {_tex(explicit)}"
        working = f"0 = {_tex(explicit)}"
    else:
        line = _linear(intent)
        if line is None:
            return None
        a, b, c = line
        if a == 0:
            return None
        roots = [c / a]
        given = f"{_tex(a * x + b * y)} = {_num(c)}"
        working = rf"{_num(a)}x = {_num(c)}"
    if not roots:
        return None
    answer = r",\ ".join(_point(root, 0) for root in roots)
    solved = r" \text{ or } ".join(f"x = {_num(root)}" for root in roots)
    workout = Workout(
        given=(math_line(given),),
        find=(math_line(r"\left(x, 0\right)", "x-intercept" + ("s" if len(roots) > 1 else "")),),
        formula=(math_line("y = 0", "on the x-axis"),),
        substitution=(math_line(working), math_line(solved)),
    )
    return workout, answer, [f"x-intercepts: {', '.join(str(root) for root in roots)}"]


def both_intercepts(intent: MathIntent) -> _Solved | None:
    """Both axes: where y = 0, then where x = 0. Missing either, nothing is verified."""
    crossing, meeting = _x_intercepts(intent), _y_intercept(intent)
    if crossing is None or meeting is None:
        return None
    (x_work, x_answer, x_record), (y_work, y_answer, y_record) = crossing, meeting
    workout = Workout(
        given=x_work.given,
        find=(math_line(r"\left(x, 0\right),\ \left(0, y\right)", "x- and y-intercepts"),),
        formula=(*x_work.formula, *y_work.formula),
        substitution=(*x_work.substitution, *y_work.substitution),
    )
    several = "s" if x_answer.count(r"\left(") > 1 else ""
    answer = rf"\text{{x-intercept{several} }} {x_answer};\ \text{{y-intercept }} {y_answer}"
    return workout, answer, [*x_record, *y_record]


def _slope_of(intent: MathIntent) -> tuple[Any, Any, str] | None:
    """(slope, intercept, the line as given) for a non-vertical straight line."""
    line = _linear(intent)
    if line is None:
        return None
    a, b, c = line
    if b == 0:
        return None
    x, y = _symbols("x", "y")
    return -a / b, c / b, f"{_tex(a * x + b * y)} = {_num(c)}"


def _slope(intent: MathIntent) -> _Solved | None:
    found = _slope_of(intent)
    if found is None:
        return None
    slope, intercept, given = found
    answer = f"m = {_num(slope)}"
    workout = Workout(
        given=(math_line(given),),
        find=(math_line("m", "slope"),),
        formula=(math_line("y = mx + c", "Slope-intercept form"),),
        substitution=(math_line(_line_tex(slope, intercept)),),
    )
    return workout, answer, [f"Slope: {slope}"]


def _slope_intercept(intent: MathIntent) -> _Solved | None:
    found = _slope_of(intent)
    if found is None:
        return None
    slope, intercept, given = found
    answer = _line_tex(slope, intercept)
    workout = Workout(
        given=(math_line(given),),
        find=(math_line("y = mx + c"),),
        steps=(solve_for_line("y"), math_line(answer)),
    )
    return workout, answer, [f"Slope-intercept form: {answer}"]


def _line_through(intent: MathIntent) -> _Solved | None:
    from sympy import Rational, nsimplify

    line = _linear(intent)
    if line is None or intent.point_x is None or intent.point_y is None:
        return None
    a, b, c = line
    px, py = nsimplify(intent.point_x, rational=True), nsimplify(intent.point_y, rational=True)
    relation = intent.trial_outcome
    x, y = _symbols("x", "y")
    given = (
        math_line(f"{_tex(a * x + b * y)} = {_num(c)}", "the line"),
        math_line(_point(px, py), "the point"),
    )
    if b == 0:
        # A vertical line: parallel lines are vertical, perpendicular ones horizontal.
        answer = f"x = {_num(px)}" if relation == "parallel" else f"y = {_num(py)}"
        workout = Workout(given=given, steps=(math_line(answer, f"{relation} to a vertical line"),))
        return workout, answer, [f"Line: {answer}"]
    slope = -a / b
    if relation == "parallel":
        new = slope
        rule = math_line(r"m_{\parallel} = m", "Parallel lines have equal slopes")
    elif slope == 0:
        answer = f"x = {_num(px)}"
        workout = Workout(given=given, steps=(math_line(answer, "perpendicular to a flat line"),))
        return workout, answer, [f"Line: {answer}"]
    else:
        new = Rational(-1) / slope
        rule = math_line(r"m_{\perp} = -\frac{1}{m}", "Perpendicular slopes multiply to -1")
    intercept = py - new * px
    answer = _line_tex(new, intercept)
    workout = Workout(
        given=given,
        find=(math_line("y = mx + c"),),
        formula=(rule, math_line(r"y - y_1 = m\left(x - x_1\right)", "Point-slope form")),
        substitution=(
            math_line(f"m = {_num(slope)}", "slope of the given line"),
            math_line(f"m = {_num(new)}", f"slope of the {relation} line"),
            math_line(rf"y - {_bracket(py)} = {_num(new)}\left(x - {_bracket(px)}\right)"),
            math_line(answer),
        ),
    )
    return workout, answer, [f"Line: {answer}"]
