"""A chase that closes a gap, and two legs at right angles (``extractors/relative_motion.py``)."""

from __future__ import annotations

import math

from app.modules.physics.display import latex_given, latex_number, latex_unit, plain_number
from app.modules.physics.extractors.relative_motion import COMPASS_NAMES
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError

RELATIVE_MOTION_OPERATIONS = frozenset({"catch_up_time", "displacement_two_legs"})


def _catch_up_time(intent: PhysicsIntent) -> PhysicsResult:
    """t = d/(v₁ - v₂): the gap closes at the difference of the speeds."""
    p = params_in_si(intent)
    closing = p["v_chaser"] - p["v_target"]
    if closing <= 0 or p["d"] <= 0:
        raise SolveServiceError("a slower chaser never catches up")
    value = p["d"] / closing
    substitution = (
        rf"t = \frac{{{latex_given(p['d'])}}}{{{latex_given(p['v_chaser'])} - "
        rf"{latex_given(p['v_target'])}}} = {latex_number(value)}"
    )
    return PhysicsResult(
        answer=substitution,
        formulas=(r"t = \frac{d}{v_1 - v_2}",),
        substitutions=(substitution,),
        quantities=(QuantityResult("", value, "s"),),
    )


def _displacement(intent: PhysicsIntent) -> PhysicsResult:
    """d = √(d₁² + d₂²), at atan(d₂/d₁) from the first leg toward the second."""
    params = intent.physics_params or {}
    unit = (intent.physics_units or {}).get("d1", "m")
    d1, d2 = params["d1"], params["d2"]
    first = COMPASS_NAMES[int(params["heading1"])]
    second = COMPASS_NAMES[int(params["heading2"])]
    if d1 <= 0 or d2 <= 0:
        raise SolveServiceError("two legs need two lengths")
    value = math.hypot(d1, d2)
    angle = math.degrees(math.atan2(d2, d1))
    shown = latex_unit(unit)
    # The legs keep the unit they were walked in: the arithmetic is in km.
    leg1, leg2 = f"{latex_given(d1)}{shown}", f"{latex_given(d2)}{shown}"
    rows = (
        rf"d = \sqrt{{({leg1})^2 + ({leg2})^2}} = {latex_number(value)}{shown}",
        rf"\theta = \arctan\frac{{{leg2}}}{{{leg1}}} = {latex_number(angle)}^\circ",
    )
    return PhysicsResult(
        answer=rows[0],
        formulas=(r"d = \sqrt{d_1^2 + d_2^2}", r"\theta = \arctan\frac{d_2}{d_1}"),
        substitutions=rows,
        quantities=(
            QuantityResult("", value, unit, detail=f"{plain_number(angle)}° {second} of {first}"),
        ),
    )


def solve_relative_motion(intent: PhysicsIntent) -> PhysicsResult:
    if intent.physics_op == "catch_up_time":
        return _catch_up_time(intent)
    if intent.physics_op == "displacement_two_legs":
        return _displacement(intent)
    raise SolveServiceError(f"unsupported relative motion op: {intent.physics_op}")
