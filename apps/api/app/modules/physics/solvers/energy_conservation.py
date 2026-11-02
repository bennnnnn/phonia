"""Closed mechanical-energy templates.

These are not a general energy-chain solver. Each operation has one unknown
among a fixed set, and non-conservative work is refused by the extractor.
"""

from __future__ import annotations

import math

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import gravity_of, one_unknown, params_in_si
from app.services.solving import SolveServiceError


def _positive_speed(disc: float) -> float:
    if disc < 0:
        raise SolveServiceError("those values do not give a real speed")
    return math.sqrt(disc)


def solve_energy_conservation(intent: PhysicsIntent) -> PhysicsResult:
    params = params_in_si(intent)
    operation = intent.physics_op or ""
    if operation == "work_energy":
        return _work_energy(params)
    if operation == "mechanical_energy_gravity":
        return _gravity(params)
    if operation == "mechanical_energy_spring":
        return _spring(params)
    raise SolveServiceError(f"unsupported energy conservation op: {operation}")


def _work_energy(params: dict[str, float]) -> PhysicsResult:
    unknown = one_unknown(params, ("W", "m", "v1", "v2"))
    if unknown != "m" and params["m"] <= 0:
        raise SolveServiceError("mass must be positive")
    if unknown == "W":
        work = 0.5 * params["m"] * (params["v2"] ** 2 - params["v1"] ** 2)
        answer = (
            r"W_{net} = \frac{1}{2}m(v_2^2 - v_1^2) = "
            rf"\frac{{1}}{{2}} \cdot {params['m']:g} \cdot "
            rf"({params['v2']:g}^2 - {params['v1']:g}^2) \approx {work:.2f} \text{{ J}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"W_{net} = \frac{1}{2}m(v_2^2 - v_1^2)",),
            substitutions=(
                rf"W_{{net}} = \frac{{1}}{{2}} \cdot {params['m']:g} \cdot ({params['v2']:g}^2 - "
                rf"{params['v1']:g}^2)",
            ),
            quantities=(QuantityResult("", work, "J"),),
        )
    if unknown == "m":
        change = params["v2"] ** 2 - params["v1"] ** 2
        if change == 0:
            raise SolveServiceError("mass is not determined when the speed does not change")
        mass = 2 * params["W"] / change
        if mass <= 0:
            raise SolveServiceError("mass must be positive")
        answer = (
            r"m = \frac{2W_{net}}{v_2^2 - v_1^2} = "
            rf"\frac{{2 \cdot {params['W']:g}}}{{{params['v2']:g}^2 - {params['v1']:g}^2}} "
            rf"\approx {mass:.2f} \text{{ kg}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"m = \frac{2W_{net}}{v_2^2 - v_1^2}",),
            substitutions=(
                rf"m = \frac{{2 \cdot {params['W']:g}}}{{{params['v2']:g}^2 - {params['v1']:g}^2}}",
            ),
            quantities=(QuantityResult("", mass, "kg"),),
        )
    if unknown == "v2":
        speed = _positive_speed(params["v1"] ** 2 + 2 * params["W"] / params["m"])
        answer = (
            r"v_2 = \sqrt{v_1^2 + \frac{2W_{net}}{m}} = "
            rf"\sqrt{{{params['v1']:g}^2 + \frac{{2 \cdot {params['W']:g}}}{{{params['m']:g}}}}} "
            rf"\approx {speed:.2f} \text{{ m/s}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"v_2 = \sqrt{v_1^2 + \frac{2W_{net}}{m}}",),
            substitutions=(
                rf"v_2 = \sqrt{{{params['v1']:g}^2 + \frac{{2 \cdot {params['W']:g}}}"
                rf"{{{params['m']:g}}}}}",
            ),
            quantities=(QuantityResult("", speed, "m/s"),),
        )
    speed = _positive_speed(params["v2"] ** 2 - 2 * params["W"] / params["m"])
    answer = (
        r"v_1 = \sqrt{v_2^2 - \frac{2W_{net}}{m}} = "
        rf"\sqrt{{{params['v2']:g}^2 - \frac{{2 \cdot {params['W']:g}}}{{{params['m']:g}}}}} "
        rf"\approx {speed:.2f} \text{{ m/s}}"
    )
    return PhysicsResult(
        answer=answer,
        formulas=(r"v_1 = \sqrt{v_2^2 - \frac{2W_{net}}{m}}",),
        substitutions=(
            rf"v_1 = \sqrt{{{params['v2']:g}^2 - \frac{{2 \cdot {params['W']:g}}}"
            rf"{{{params['m']:g}}}}}",
        ),
        quantities=(QuantityResult("", speed, "m/s"),),
    )


def _gravity(params: dict[str, float]) -> PhysicsResult:
    unknown = one_unknown(params, ("v1", "h1", "v2", "h2"))
    gravity = gravity_of(params)
    if gravity <= 0:
        raise SolveServiceError("gravity must be positive")
    if unknown == "v2":
        speed = _positive_speed(params["v1"] ** 2 + 2 * gravity * (params["h1"] - params["h2"]))
        answer = (
            r"\frac{1}{2}v_1^2 + gh_1 = \frac{1}{2}v_2^2 + gh_2 \Rightarrow "
            rf"v_2 \approx {speed:.2f} \text{{ m/s}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\frac{1}{2}v_1^2 + gh_1 = \frac{1}{2}v_2^2 + gh_2 \Rightarrow v_2",),
            substitutions=(
                rf"v_2 = \sqrt{{{params['v1']:g}^2 + 2 \cdot {gravity:g} \cdot "
                rf"({params['h1']:g} - {params['h2']:g})}}",
            ),
            quantities=(QuantityResult("", speed, "m/s"),),
        )
    if unknown == "v1":
        speed = _positive_speed(params["v2"] ** 2 + 2 * gravity * (params["h2"] - params["h1"]))
        answer = (
            r"\frac{1}{2}v_1^2 + gh_1 = \frac{1}{2}v_2^2 + gh_2 \Rightarrow "
            rf"v_1 \approx {speed:.2f} \text{{ m/s}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\frac{1}{2}v_1^2 + gh_1 = \frac{1}{2}v_2^2 + gh_2 \Rightarrow v_1",),
            substitutions=(
                rf"v_1 = \sqrt{{{params['v2']:g}^2 + 2 \cdot {gravity:g} \cdot "
                rf"({params['h2']:g} - {params['h1']:g})}}",
            ),
            quantities=(QuantityResult("", speed, "m/s"),),
        )
    if unknown == "h2":
        height = params["h1"] + (params["v1"] ** 2 - params["v2"] ** 2) / (2 * gravity)
        answer = (
            r"h_2 = h_1 + \frac{v_1^2 - v_2^2}{2g} \approx "
            rf"{height:.2f} \text{{ m}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"h_2 = h_1 + \frac{v_1^2 - v_2^2}{2g}",),
            substitutions=(
                rf"h_2 = {params['h1']:g} + \frac{{{params['v1']:g}^2 - {params['v2']:g}^2}}"
                rf"{{2 \cdot {gravity:g}}}",
            ),
            quantities=(QuantityResult("", height, "m"),),
        )
    height = params["h2"] + (params["v2"] ** 2 - params["v1"] ** 2) / (2 * gravity)
    answer = (
        r"h_1 = h_2 + \frac{v_2^2 - v_1^2}{2g} \approx "
        rf"{height:.2f} \text{{ m}}"
    )
    return PhysicsResult(
        answer=answer,
        formulas=(r"h_1 = h_2 + \frac{v_2^2 - v_1^2}{2g}",),
        substitutions=(
            rf"h_1 = {params['h2']:g} + \frac{{{params['v2']:g}^2 - {params['v1']:g}^2}}"
            rf"{{2 \cdot {gravity:g}}}",
        ),
        quantities=(QuantityResult("", height, "m"),),
    )


def _spring(params: dict[str, float]) -> PhysicsResult:
    unknown = one_unknown(params, ("v1", "x1", "v2", "x2"))
    mass = params["m"]
    stiffness = params["k"]
    if mass <= 0 or stiffness <= 0:
        raise SolveServiceError("mass and the spring constant must be positive")
    ratio = stiffness / mass
    if unknown == "v2":
        speed = _positive_speed(params["v1"] ** 2 + ratio * (params["x1"] ** 2 - params["x2"] ** 2))
        answer = (
            r"\frac{1}{2}mv_1^2 + \frac{1}{2}kx_1^2 = "
            r"\frac{1}{2}mv_2^2 + \frac{1}{2}kx_2^2 \Rightarrow "
            rf"v_2 \approx {speed:.2f} \text{{ m/s}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(
                r"\frac{1}{2}mv_1^2 + \frac{1}{2}kx_1^2 = \frac{1}{2}mv_2^2 + \frac{1}{2}kx_2^2 "
                r"\Rightarrow v_2",
            ),
            substitutions=(
                rf"v_2 = \sqrt{{{params['v1']:g}^2 + \frac{{{stiffness:g}}}{{{mass:g}}}"
                rf"({params['x1']:g}^2 - {params['x2']:g}^2)}}",
            ),
            quantities=(QuantityResult("", speed, "m/s"),),
        )
    if unknown == "v1":
        speed = _positive_speed(params["v2"] ** 2 + ratio * (params["x2"] ** 2 - params["x1"] ** 2))
        answer = (
            r"\frac{1}{2}mv_1^2 + \frac{1}{2}kx_1^2 = "
            r"\frac{1}{2}mv_2^2 + \frac{1}{2}kx_2^2 \Rightarrow "
            rf"v_1 \approx {speed:.2f} \text{{ m/s}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(
                r"\frac{1}{2}mv_1^2 + \frac{1}{2}kx_1^2 = \frac{1}{2}mv_2^2 + \frac{1}{2}kx_2^2 "
                r"\Rightarrow v_1",
            ),
            substitutions=(
                rf"v_1 = \sqrt{{{params['v2']:g}^2 + \frac{{{stiffness:g}}}{{{mass:g}}}"
                rf"({params['x2']:g}^2 - {params['x1']:g}^2)}}",
            ),
            quantities=(QuantityResult("", speed, "m/s"),),
        )
    if unknown == "x2":
        square = params["x1"] ** 2 + (mass / stiffness) * (params["v1"] ** 2 - params["v2"] ** 2)
        if square < 0:
            raise SolveServiceError("those values do not give a real displacement")
        displacement = math.sqrt(square)
        answer = (
            r"\frac{1}{2}kx_2^2 = \frac{1}{2}kx_1^2 + \frac{1}{2}m(v_1^2 - v_2^2) \Rightarrow "
            rf"x_2 \approx {displacement:.4g} \text{{ m}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(
                r"\frac{1}{2}kx_2^2 = \frac{1}{2}kx_1^2 + \frac{1}{2}m(v_1^2 - v_2^2) \Rightarrow "
                r"x_2",
            ),
            substitutions=(
                rf"x_2 = \sqrt{{{params['x1']:g}^2 + \frac{{{mass:g}}}{{{stiffness:g}}}"
                rf"({params['v1']:g}^2 - {params['v2']:g}^2)}}",
            ),
            quantities=(QuantityResult("", displacement, "m"),),
        )
    square = params["x2"] ** 2 + (mass / stiffness) * (params["v2"] ** 2 - params["v1"] ** 2)
    if square < 0:
        raise SolveServiceError("those values do not give a real displacement")
    displacement = math.sqrt(square)
    answer = (
        r"\frac{1}{2}kx_1^2 = \frac{1}{2}kx_2^2 + \frac{1}{2}m(v_2^2 - v_1^2) \Rightarrow "
        rf"x_1 \approx {displacement:.4g} \text{{ m}}"
    )
    return PhysicsResult(
        answer=answer,
        formulas=(
            r"\frac{1}{2}kx_1^2 = \frac{1}{2}kx_2^2 + \frac{1}{2}m(v_2^2 - v_1^2) \Rightarrow x_1",
        ),
        substitutions=(
            rf"x_1 = \sqrt{{{params['x2']:g}^2 + \frac{{{mass:g}}}{{{stiffness:g}}}"
            rf"({params['v2']:g}^2 - {params['v1']:g}^2)}}",
        ),
        quantities=(QuantityResult("", displacement, "m"),),
    )
