"""Constant angular acceleration: omega, theta and alpha, and torque with a moment of inertia."""

from __future__ import annotations

import math

from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import one_unknown
from app.services.solving import SolveServiceError


def _omega(params: dict[str, float]) -> PhysicsResult:
    if {"omega0", "ang_alpha", "t"} <= params.keys():
        value = params["omega0"] + params["ang_alpha"] * params["t"]
        answer = (
            rf"\omega = \omega_0 + \alpha t = {params['omega0']:g} + "
            rf"{params['ang_alpha']:g} \cdot {params['t']:g} "
            rf"\approx {value:.2f} \text{{ rad/s}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\omega = \omega_0 + \alpha t",),
            substitutions=(
                rf"\omega = {params['omega0']:g} + {params['ang_alpha']:g} \cdot {params['t']:g}",
            ),
            quantities=(QuantityResult("", value, "rad/s"),),
        )
    if {"omega0", "ang_alpha", "theta"} <= params.keys():
        disc = params["omega0"] ** 2 + 2 * params["ang_alpha"] * params["theta"]
        if disc < 0:
            raise SolveServiceError("those values do not give a real angular velocity")
        value = math.sqrt(disc)
        answer = (
            r"\omega^2 = \omega_0^2 + 2\alpha\Delta\theta \Rightarrow "
            rf"\omega \approx {value:.2f} \text{{ rad/s}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\omega^2 = \omega_0^2 + 2\alpha\Delta\theta \Rightarrow \omega",),
            substitutions=(
                rf"\omega = \sqrt{{{params['omega0']:g}^2 + 2 \cdot {params['ang_alpha']:g}"
                rf" \cdot {params['theta']:g}}}",
            ),
            quantities=(QuantityResult("", value, "rad/s"),),
        )
    raise SolveServiceError("angular velocity needs omega0, alpha, and time or angle")


def _theta(params: dict[str, float]) -> PhysicsResult:
    # The catalog measures angular displacement from zero. There is no theta0 input.
    theta0 = 0.0
    if {"omega0", "ang_alpha", "t"} <= params.keys():
        value = (
            theta0 + params["omega0"] * params["t"] + 0.5 * params["ang_alpha"] * params["t"] ** 2
        )
        elapsed = latex_num(params["t"], square=True)
        answer = (
            r"\theta = \theta_0 + \omega_0 t + \frac{1}{2}\alpha t^2 = "
            rf"{theta0:g} + {params['omega0']:g} \cdot {params['t']:g} + "
            rf"\frac{{1}}{{2}} \cdot {params['ang_alpha']:g} \cdot {elapsed} "
            rf"\approx {value:.2f} \text{{ rad}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\theta = \theta_0 + \omega_0 t + \frac{1}{2}\alpha t^2",),
            substitutions=(
                rf"\theta = {theta0:g} + {params['omega0']:g} \cdot {params['t']:g} + "
                rf"\frac{{1}}{{2}} \cdot {params['ang_alpha']:g} \cdot {elapsed}",
            ),
            quantities=(QuantityResult("", value, "rad"),),
        )
    if {"omega", "omega0", "ang_alpha"} <= params.keys():
        if params["ang_alpha"] == 0:
            raise SolveServiceError("angular acceleration must be nonzero to find the angle")
        value = theta0 + (params["omega"] ** 2 - params["omega0"] ** 2) / (2 * params["ang_alpha"])
        answer = (
            r"\omega^2 = \omega_0^2 + 2\alpha\Delta\theta \Rightarrow "
            rf"\theta \approx {value:.2f} \text{{ rad}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\omega^2 = \omega_0^2 + 2\alpha\Delta\theta \Rightarrow \theta",),
            substitutions=(
                rf"\theta = \frac{{{params['omega']:g}^2 - {params['omega0']:g}^2}}"
                rf"{{2 \cdot {params['ang_alpha']:g}}}",
            ),
            quantities=(QuantityResult("", value, "rad"),),
        )
    # theta = (omega0 + omega) t / 2 eliminates alpha. Opposite signs mean the
    # rotation reversed, so this average is not the angle traveled.
    if {"omega", "omega0", "t"} <= params.keys() and "ang_alpha" not in params:
        if params["t"] == 0 and params["omega"] != params["omega0"]:
            raise SolveServiceError("elapsed time must be nonzero")
        if params["omega0"] * params["omega"] < 0:
            raise SolveServiceError(
                "the rotation reverses, so this is not the angular displacement"
            )
        value = theta0 + (params["omega0"] + params["omega"]) * params["t"] / 2
        answer = (
            r"\theta = \frac{\omega_0 + \omega}{2} t = "
            rf"\frac{{{params['omega0']:g} + {params['omega']:g}}}{{2}} "
            rf"\cdot {params['t']:g} \approx {value:.2f} \text{{ rad}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\theta = \frac{\omega_0 + \omega}{2} t",),
            substitutions=(
                rf"\theta = \frac{{{params['omega0']:g} + {params['omega']:g}}}{{2}}"
                rf" \cdot {params['t']:g}",
            ),
            quantities=(QuantityResult("", value, "rad"),),
        )
    raise SolveServiceError("angular displacement needs the constant-acceleration givens")


def _alpha(params: dict[str, float]) -> PhysicsResult:
    if {"omega", "omega0", "t"} <= params.keys():
        if params["t"] == 0:
            raise SolveServiceError("elapsed time must be nonzero")
        value = (params["omega"] - params["omega0"]) / params["t"]
        answer = (
            r"\alpha = \frac{\omega - \omega_0}{t} = "
            rf"\frac{{{params['omega']:g} - {params['omega0']:g}}}{{{params['t']:g}}} "
            rf"\approx {value:.2f} \text{{ rad/s}}^2"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\alpha = \frac{\omega - \omega_0}{t}",),
            substitutions=(
                rf"\alpha = \frac{{{params['omega']:g} - {params['omega0']:g}}}{{{params['t']:g}}}",
            ),
            quantities=(QuantityResult("", value, "rad/s^2"),),
        )
    if {"omega", "omega0", "theta"} <= params.keys():
        if params["theta"] == 0:
            raise SolveServiceError("angular displacement must be nonzero")
        value = (params["omega"] ** 2 - params["omega0"] ** 2) / (2 * params["theta"])
        answer = (
            r"\alpha = \frac{\omega^2 - \omega_0^2}{2\Delta\theta} \approx "
            rf"{value:.2f} \text{{ rad/s}}^2"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\alpha = \frac{\omega^2 - \omega_0^2}{2\Delta\theta}",),
            substitutions=(
                rf"\alpha = \frac{{{params['omega']:g}^2 - {params['omega0']:g}^2}}"
                rf"{{2 \cdot {params['theta']:g}}}",
            ),
            quantities=(QuantityResult("", value, "rad/s^2"),),
        )
    raise SolveServiceError("angular acceleration needs two angular velocities and time or angle")


def _torque_inertia(params: dict[str, float]) -> PhysicsResult:
    unknown = one_unknown(params, ("tau", "inertia", "ang_alpha"))
    if unknown == "tau":
        if params["inertia"] <= 0:
            raise SolveServiceError("moment of inertia must be positive")
        value = params["inertia"] * params["ang_alpha"]
        answer = (
            rf"\tau = I\alpha = {params['inertia']:g} \cdot {params['ang_alpha']:g} "
            rf"\approx {value:.2f} \text{{ N}}\cdot\text{{m}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\tau = I\alpha",),
            substitutions=(rf"\tau = {params['inertia']:g} \cdot {params['ang_alpha']:g}",),
            quantities=(QuantityResult("", value, "N*m"),),
        )
    if unknown == "ang_alpha":
        if params["inertia"] <= 0:
            raise SolveServiceError("moment of inertia must be positive")
        value = params["tau"] / params["inertia"]
        answer = (
            rf"\alpha = \frac{{\tau}}{{I}} = \frac{{{params['tau']:g}}}{{{params['inertia']:g}}} "
            rf"\approx {value:.2f} \text{{ rad/s}}^2"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\alpha = \frac{\tau}{I}",),
            substitutions=(rf"\alpha = \frac{{{params['tau']:g}}}{{{params['inertia']:g}}}",),
            quantities=(QuantityResult("", value, "rad/s^2"),),
        )
    if params["ang_alpha"] == 0:
        raise SolveServiceError("angular acceleration must be nonzero")
    value = params["tau"] / params["ang_alpha"]
    if value <= 0:
        raise SolveServiceError("moment of inertia must be positive")
    answer = (
        rf"I = \frac{{\tau}}{{\alpha}} = \frac{{{params['tau']:g}}}{{{params['ang_alpha']:g}}} "
        rf"\approx {value:.2f} \text{{ kg}}\,\text{{m}}^2"
    )
    return PhysicsResult(
        answer=answer,
        formulas=(r"I = \frac{\tau}{\alpha}",),
        substitutions=(rf"I = \frac{{{params['tau']:g}}}{{{params['ang_alpha']:g}}}",),
        quantities=(QuantityResult("", value, "kg*m^2"),),
    )
