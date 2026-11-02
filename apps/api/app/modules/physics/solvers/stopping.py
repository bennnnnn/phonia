"""Stopping distance: the reaction distance plus the braking distance."""

from __future__ import annotations

import math

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def _solve_stopping_distance(intent: PhysicsIntent) -> PhysicsResult:
    """Reaction distance, braking distance, total, and the braking deceleration.

    The chip is the total distance. The other three results stay on the
    substitution rows the direct reply prints.
    """
    from app.modules.physics.display import latex_given

    params = params_in_si(intent)
    if "decel" in params:
        return _braking_at_a_rate(params)
    speed = params.get("v")
    reaction_time = params.get("t_react")
    brake_time = params.get("t_brake")
    if (
        speed is None
        or reaction_time is None
        or brake_time is None
        or not math.isfinite(speed)
        or not math.isfinite(reaction_time)
        or not math.isfinite(brake_time)
        or speed <= 0
        or reaction_time < 0
        or brake_time <= 0
    ):
        raise SolveServiceError("stopping distance needs a positive speed and a braking time")
    reaction = speed * reaction_time
    braking = speed * brake_time / 2.0
    total = reaction + braking
    acceleration = -speed / brake_time
    if not all(math.isfinite(item) for item in (reaction, braking, total, acceleration)):
        raise SolveServiceError("stopping distance is not finite")
    speed_text = latex_given(speed)
    react_text = latex_given(reaction_time)
    brake_text = latex_given(brake_time)
    formulas = (
        r"d_r = v t_r",
        r"d_b = \frac{v t_b}{2}",
        r"d = d_r + d_b",
        r"a = -\frac{v}{t_b}",
    )
    substitutions = (
        rf"d_r = {speed_text} \cdot {react_text} = {latex_given(reaction)}",
        rf"d_b = \frac{{{speed_text} \cdot {brake_text}}}{{2}} = {latex_given(braking)}",
        rf"d = {latex_given(reaction)} + {latex_given(braking)} = {latex_given(total)}",
        rf"a = -\frac{{{speed_text}}}{{{brake_text}}} = {latex_given(acceleration)}",
    )
    return PhysicsResult(
        answer=rf"d = {latex_given(total)}\,\mathrm{{m}}",
        formulas=formulas,
        substitutions=substitutions,
        quantities=(QuantityResult("", total, "m"),),
    )


def _braking_at_a_rate(params: dict[str, float]) -> PhysicsResult:
    """Reaction distance at constant speed, then v²/(2a) braking to rest."""
    from app.modules.physics.display import latex_given, latex_number

    speed, reaction_time, rate = params.get("v"), params.get("t_react"), params.get("decel")
    if (
        speed is None
        or reaction_time is None
        or rate is None
        or not all(math.isfinite(item) for item in (speed, reaction_time, rate))
        or speed <= 0
        or reaction_time < 0
        or rate <= 0
    ):
        raise SolveServiceError("stopping distance needs a positive speed and braking rate")
    reaction = speed * reaction_time
    braking = speed * speed / (2.0 * rate)
    total = reaction + braking
    speed_text, rate_text = latex_given(speed), latex_given(rate)
    substitutions = (
        rf"d_r = {speed_text} \cdot {latex_given(reaction_time)} = {latex_number(reaction)}",
        rf"d_b = \frac{{{speed_text}^2}}{{2 \cdot {rate_text}}} = {latex_number(braking)}",
        rf"d = {latex_number(reaction)} + {latex_number(braking)} = {latex_number(total)}",
    )
    return PhysicsResult(
        answer=rf"d = {latex_number(total)}\,\mathrm{{m}}",
        formulas=(r"d_r = v t_r", r"d_b = \frac{v^2}{2a}", r"d = d_r + d_b"),
        substitutions=substitutions,
        quantities=(QuantityResult("", total, "m"),),
    )
