"""Vertical kinematics under gravity: time to the ground, velocity, position, peak height
and acceleration. Rate and stopping-distance questions go to their own solvers.

`_read_fall` refuses a fall its givens cannot answer; `_VERTICAL_OPS` works the asked op.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Collection
from dataclasses import dataclass

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.arithmetic import latex_num, quadratic_roots
from app.modules.physics.solvers.average_speed import (
    _AVERAGE_SPEED_OPERATIONS,
    solve_average_speed,
)
from app.modules.physics.solvers.motion_scenes import fall_scenes, fall_speed_pictures
from app.modules.physics.solvers.rates import _RATE_OPERATIONS, _solve_distance_speed_time
from app.modules.physics.solvers.relative_motion import (
    RELATIVE_MOTION_OPERATIONS,
    solve_relative_motion,
)
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult, solved
from app.modules.physics.solvers.si import gravity_of, params_in_si
from app.modules.physics.solvers.stopping import _solve_stopping_distance
from app.modules.physics.solvers.two_stage import TWO_STAGE_OPERATIONS, solve_two_stage
from app.services.solving import SolveServiceError

# Motion that is not one vertical line under gravity, tried in this order.
_OTHER_MOTION: tuple[tuple[Collection[str], Callable[[PhysicsIntent], PhysicsResult]], ...] = (
    (_RATE_OPERATIONS, _solve_distance_speed_time),
    (_AVERAGE_SPEED_OPERATIONS, solve_average_speed),
    (frozenset({"stopping_distance"}), _solve_stopping_distance),
    (TWO_STAGE_OPERATIONS, solve_two_stage),
    (RELATIVE_MOTION_OPERATIONS, solve_relative_motion),
)


def solve_kinematics(intent: PhysicsIntent) -> PhysicsResult:
    for operations, solver in _OTHER_MOTION:
        if intent.physics_op in operations:
            return solver(intent)
    fall = _read_fall(intent)
    solve = _VERTICAL_OPS.get(fall.op)
    if solve is None:
        raise SolveServiceError(f"unsupported kinematics op: {fall.op}")
    return solve(fall)


@dataclass(frozen=True, slots=True)
class _Fall:
    """A drop or a throw on one vertical line, its givens in SI."""

    op: str
    g: float
    h0: float
    v0: float
    t: float | None
    # No stated height is not a height of zero: only a throw that comes back to
    # the hand is answered without one, and its working never shows an h₀.
    stated_height: bool

    def time_to_ground(self) -> float | None:
        # h0 + v0·t - ½g·t² = 0; the first moment after release it is 0.
        valid = [root for root in quadratic_roots(-0.5 * self.g, self.v0, self.h0) if root > 0]
        return valid[0] if valid else None


def _read_fall(intent: PhysicsIntent) -> _Fall:
    """The fall's givens, refused when no op could answer from them."""
    p = params_in_si(intent)
    fall = _Fall(
        op=intent.physics_op or "time_to_ground",
        g=gravity_of(p),
        h0=p.get("h0", 0.0),
        v0=p.get("v0", 0.0),
        t=p.get("t"),
        stated_height="h0" in (intent.physics_params or {}),
    )
    op, v0 = fall.op, fall.v0
    if fall.g <= 0:
        raise SolveServiceError("gravity must be positive")
    if not fall.stated_height and op != "acceleration":
        if op in ("time_to_ground", "time_to_peak", "vertical_max_height") and v0 <= 0:
            raise SolveServiceError("no stated height for a fall")
        if op == "position" and v0 <= 0:
            raise SolveServiceError("no stated height for a fall")
        if op in ("speed", "velocity") and fall.t is None:
            raise SolveServiceError("no stated height to land from")

    # Past impact, h(t) is negative and v(t) is still "in air" — not a fact.
    if op in ("position", "velocity", "speed"):
        t_asked = fall.t
        t_land = fall.time_to_ground()
        if t_asked is not None and t_land is not None and float(t_asked) > t_land:
            raise SolveServiceError("already on the ground")
    return fall


def _landed(fall: _Fall) -> float:
    landed = fall.time_to_ground()
    if landed is None:
        raise SolveServiceError("no positive real time to ground")
    return landed


def _time_to_ground(fall: _Fall) -> PhysicsResult:
    g, h0, v0 = fall.g, fall.h0, fall.v0
    # Solve h(t) = 0 for t > 0.
    t_val = _landed(fall)
    v0_sq = latex_num(v0, square=True)
    if fall.stated_height:
        formula = r"t = \frac{v_0 + \sqrt{v_0^2 + 2 g h_0}}{g}"
        substitution = (
            rf"t = \frac{{{latex_num(v0)} + \sqrt{{{v0_sq} + 2 \cdot {g:g} \cdot {h0:g}}}}}"
            rf"{{{g:g}}}"
        )
    else:
        # Up and back to the launch height: twice the time to the top.
        formula = r"t = \frac{2 v_0}{g}"
        substitution = rf"t = \frac{{2 \cdot {latex_num(v0)}}}{{{g:g}}}"
    answer_latex = rf"{formula} = {substitution.split(' = ', 1)[1]} \approx {t_val:.2f} \text{{ s}}"
    return solved(
        QuantityResult("", t_val, "s"),
        answer=answer_latex,
        formula=formula,
        substitution=substitution,
        simulation_specs=fall_scenes(h0, v0, g, t_val, ground=True),
    )


def _velocity_or_speed(fall: _Fall) -> PhysicsResult:
    op, g, h0, v0 = fall.op, fall.g, fall.h0, fall.v0
    # Need a time — look for a time param, else use time_to_ground.
    t_param = fall.t
    impact_without_time = t_param is None
    if t_param is None:
        t_param = _landed(fall)
    t_val = float(t_param)
    v_val = float(v0 - g * t_val)
    if impact_without_time:
        v_val, formula, substitution, answer_latex = _impact(fall)
    elif op == "speed":
        v_val = abs(v_val)
        formula = r"v = \lvert v_0 - g \cdot t\rvert"
        substitution = rf"v = \lvert {latex_num(v0)} - {g:g} \cdot {t_val:g}\rvert"
        answer_latex = (
            rf"v = \lvert v_0 - g \cdot t\rvert = "
            rf"\lvert {latex_num(v0)} - {g:g} \cdot {t_val:g}\rvert "
            rf"\approx {v_val:.2f} \text{{ m/s}}"
        )
    else:
        formula = r"v = v_0 - g t"
        substitution = rf"v = {latex_num(v0)} - {g:g} \cdot {t_val:g}"
        answer_latex = (
            rf"v = v_0 - g t = {latex_num(v0)} - {g:g} \cdot {t_val:g} "
            rf"\approx {v_val:.2f} \text{{ m/s}}"
        )
    scenes, graphs = fall_speed_pictures(
        h0, v0, g, t_val, speed=op == "speed", ground=impact_without_time or h0 > 0
    )
    return solved(
        QuantityResult("", v_val, "m/s"),
        answer=answer_latex,
        formula=formula,
        substitution=substitution,
        graph_specs=graphs,
        simulation_specs=scenes,
    )


def _impact(fall: _Fall) -> tuple[float, str, str, str]:
    """The velocity or speed on landing, from the height: no time was asked."""
    op, g, h0, v0 = fall.op, fall.g, fall.h0, fall.v0
    impact_magnitude = math.sqrt(v0 * v0 + 2 * g * h0)
    v_val = impact_magnitude if op == "speed" else -impact_magnitude
    symbol = "v" if op == "velocity" else r"v_{impact}"
    sign = "-" if op == "velocity" else ""
    formula = rf"{symbol} = {sign}\sqrt{{v_0^2 + 2gh_0}}"
    substitution = (
        rf"{symbol} = {sign}\sqrt{{{latex_num(v0, square=True)} + "
        rf"2 \cdot {g:g} \cdot {h0:g}}}"
    )
    answer_latex = (
        rf"{symbol} = {sign}\sqrt{{v_0^2 + 2gh_0}} = "
        rf"{sign}\sqrt{{{latex_num(v0, square=True)} + 2 \cdot {g:g} \cdot {h0:g}}} "
        rf"\approx {v_val:.2f} \text{{ m/s}}"
    )
    return v_val, formula, substitution, answer_latex


def _position(fall: _Fall) -> PhysicsResult:
    g, h0, v0 = fall.g, fall.h0, fall.v0
    t_param = fall.t
    if t_param is None:
        raise SolveServiceError("position requires a time t")
    t_val = float(t_param)
    h_val = float(h0 + v0 * t_val - 0.5 * g * t_val**2)
    if fall.stated_height:
        formula = r"h = h_0 + v_0 t - \frac{1}{2} g t^2"
        substitution = (
            rf"h = {h0:g} + {latex_num(v0)} \cdot {t_val:g} - "
            rf"\frac{{1}}{{2}} \cdot {g:g} \cdot {latex_num(t_val, square=True)}"
        )
    else:
        # The height above the launch point.
        formula = r"h = v_0 t - \frac{1}{2} g t^2"
        substitution = (
            rf"h = {latex_num(v0)} \cdot {t_val:g} - "
            rf"\frac{{1}}{{2}} \cdot {g:g} \cdot {latex_num(t_val, square=True)}"
        )
    answer_latex = rf"{formula} = {substitution.split(' = ', 1)[1]} \approx {h_val:.2f} \text{{ m}}"
    return solved(
        QuantityResult("", h_val, "m"),
        answer=answer_latex,
        formula=formula,
        substitution=substitution,
        simulation_specs=fall_scenes(h0, v0, g, t_val, ground=h0 > 0),
    )


def _time_to_peak(fall: _Fall) -> PhysicsResult:
    g, v0 = fall.g, fall.v0
    if v0 <= 0:
        raise SolveServiceError("only an upward launch has a top to reach")
    t_top = v0 / g
    formula = r"t_{\text{top}} = \frac{v_0}{g}"
    substitution = rf"t_{{\text{{top}}}} = \frac{{{latex_num(v0)}}}{{{g:g}}}"
    answer_latex = (
        rf"t_{{\text{{top}}}} = \frac{{v_0}}{{g}} = \frac{{{latex_num(v0)}}}{{{g:g}}} "
        rf"\approx {t_top:.2f} \text{{ s}}"
    )
    # As for the peak height: the picture is the whole trip, the answer its top.
    t_val = _landed(fall)
    return solved(
        QuantityResult("", t_top, "s"),
        answer=answer_latex,
        formula=formula,
        substitution=substitution,
        simulation_specs=fall_scenes(fall.h0, v0, g, t_val, ground=True),
    )


def _vertical_max_height(fall: _Fall) -> PhysicsResult:
    g, h0, v0 = fall.g, fall.h0, fall.v0
    if v0 <= 0:
        raise SolveServiceError("maximum height for a vertical launch requires v0 > 0")
    h_val = h0 + v0**2 / (2 * g)
    rise = rf"\frac{{{latex_num(v0, square=True)}}}{{2 \cdot {g:g}}}"
    if fall.stated_height:
        formula = r"h_{\max} = h_0 + \frac{v_0^2}{2g}"
        substitution = rf"h_{{\max}} = {h0:g} + {rise}"
    else:
        # The rise above the launch point.
        formula = r"h_{\max} = \frac{v_0^2}{2g}"
        substitution = rf"h_{{\max}} = {rise}"
    answer_latex = rf"{formula} = {substitution.split(' = ', 1)[1]} \approx {h_val:.2f} \text{{ m}}"
    # The visual shows the complete trip back to the landing plane while
    # the scalar answer remains the requested peak height.
    t_val = _landed(fall)
    return solved(
        QuantityResult("", h_val, "m"),
        answer=answer_latex,
        formula=formula,
        substitution=substitution,
        simulation_specs=fall_scenes(h0, v0, g, t_val, ground=True),
    )


def _acceleration(fall: _Fall) -> PhysicsResult:
    g = fall.g
    # Constant g for free-fall templates only. The extractor returns
    # None unless a gravity-motion cue is present — do not use this
    # for two-point velocity acceleration.
    answer_latex = rf"a = -g = -{g:g} \text{{ m/s}}^2"
    return PhysicsResult(
        answer=answer_latex,
        formulas=(r"a = -g",),
        substitutions=(rf"a = -{g:g} \text{{ m/s}}^2",),
        quantities=(QuantityResult("", -g, "m/s^2"),),
    )


_VERTICAL_OPS: dict[str, Callable[[_Fall], PhysicsResult]] = {
    "time_to_ground": _time_to_ground,
    "velocity": _velocity_or_speed,
    "speed": _velocity_or_speed,
    "position": _position,
    "time_to_peak": _time_to_peak,
    "vertical_max_height": _vertical_max_height,
    "acceleration": _acceleration,
}
