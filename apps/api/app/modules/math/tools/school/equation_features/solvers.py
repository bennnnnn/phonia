"""Work one equation feature into the verified card: ``_SOLVERS`` maps each feature to
its solver, and a shape it cannot read verifies nothing."""

from __future__ import annotations

from dataclasses import replace

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school.equation_features.lines import (
    _line_through,
    _slope,
    _slope_intercept,
    _x_intercepts,
    _y_intercept,
    both_intercepts,
)
from app.modules.math.tools.school.equation_features.quadratics import (
    _axis,
    _discriminant,
    _parameter,
    _roots_sum_or_product,
    _solution_count,
    _vertex,
)
from app.modules.math.tools.school.equation_features.sinusoids import _amplitude, _period
from app.services.workout import render_workout


def equation_feature_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from sympy.polys.polyerrors import BasePolynomialError

    op = (intent.school_op or "").removeprefix("equation_")
    try:
        solved = _SOLVERS[op](intent)
    except (
        BasePolynomialError,
        KeyError,
        ValueError,
        TypeError,
        ZeroDivisionError,
        AttributeError,
    ):
        # Not a polynomial or a line of the expected shape: nothing to verify.
        return None
    if solved is None:
        return None
    workout, answer, record = solved
    lines.extend(record)
    block = finish_with_answer(lines, answer)
    return replace(block, worked_reply=render_workout(workout, answer))


_SOLVERS = {
    "vertex": _vertex,
    "axis": _axis,
    "y_intercept": _y_intercept,
    "x_intercepts": _x_intercepts,
    "intercepts": both_intercepts,
    "discriminant": _discriminant,
    "root_sum": lambda intent: _roots_sum_or_product(intent, product=False),
    "root_product": lambda intent: _roots_sum_or_product(intent, product=True),
    "slope": _slope,
    "slope_intercept": _slope_intercept,
    "line_through": _line_through,
    "parameter": _parameter,
    "period": _period,
    "amplitude": _amplitude,
    "solution_count": _solution_count,
}
