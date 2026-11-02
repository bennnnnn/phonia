"""The period and amplitude of ``y = A sin(Bx + C) + D`` (or cos), and a tangent's period."""

from __future__ import annotations

from typing import Any

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.school.equation_features.forms import _explicit, _Solved, _symbols, _tex
from app.services.workout import Workout, math_line


def _sinusoid(intent: MathIntent) -> tuple[Any, Any, Any, Any] | None:
    """``y = A sin(Bx + C) + D`` (or cos, tan) as (A, B, the function, F), checked exactly."""
    from sympy import Wild, cos, simplify, sin, tan

    (x,) = _symbols("x")
    expression = _explicit(intent)
    if expression is None or x not in expression.free_symbols:
        return None
    amplitude, frequency = Wild("A", exclude=[x]), Wild("B", exclude=[x])
    phase, shift = Wild("C", exclude=[x]), Wild("D", exclude=[x])
    for function in (sin, cos, tan):
        found = expression.match(amplitude * function(frequency * x + phase) + shift)
        if not found:
            continue
        a, b = found[amplitude], found[frequency]
        c, d = found.get(phase, 0), found.get(shift, 0)
        if not all(value.is_number and value.is_real for value in (a, b, c, d)):
            return None
        if a == 0 or b == 0:
            return None
        if simplify(expression - (a * function(b * x + c) + d)) != 0:
            return None
        return a, b, function, expression
    return None


def _period(intent: MathIntent) -> _Solved | None:
    from sympy import Abs, pi, tan

    found = _sinusoid(intent)
    if found is None:
        return None
    _a, b, function, expression = found
    base = pi if function is tan else 2 * pi
    period = base / Abs(b)
    answer = _tex(period)
    rule = r"\frac{\pi}{|B|}" if function is tan else r"\frac{2\pi}{|B|}"
    workout = Workout(
        given=(math_line(f"y = {_tex(expression)}"),),
        find=(math_line("T", "period"),),
        formula=(math_line(rf"T = {rule}", f"period of {function.__name__}(Bx + C)"),),
        substitution=(math_line(rf"T = \frac{{{_tex(base)}}}{{{_tex(Abs(b))}}} = {answer}"),),
    )
    return workout, answer, [f"Period: {period}"]


def _amplitude(intent: MathIntent) -> _Solved | None:
    from sympy import Abs, tan

    found = _sinusoid(intent)
    if found is None or found[2] is tan:
        # A tangent has no amplitude.
        return None
    a, _b, function, expression = found
    answer = _tex(Abs(a))
    workout = Workout(
        given=(math_line(f"y = {_tex(expression)}"),),
        find=(math_line("A", "amplitude"),),
        formula=(math_line("|A|", f"amplitude of A {function.__name__}(Bx + C) + D"),),
        substitution=(math_line(rf"|{_tex(a)}| = {answer}"),),
    )
    return workout, answer, [f"Amplitude: {Abs(a)}"]
