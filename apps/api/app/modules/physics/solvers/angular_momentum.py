"""Angular impulse and the conservation of angular momentum."""

from __future__ import annotations

from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import one_unknown
from app.services.solving import SolveServiceError


def _angular_impulse(params: dict[str, float]) -> PhysicsResult:
    unknown = one_unknown(params, ("tau", "L_i", "L_f", "t"))
    if unknown != "t" and params["t"] == 0:
        raise SolveServiceError("elapsed time must be nonzero")
    if unknown == "tau":
        value = (params["L_f"] - params["L_i"]) / params["t"]
        answer = (
            r"\tau = \frac{\Delta L}{\Delta t} = "
            rf"\frac{{{params['L_f']:g} - {params['L_i']:g}}}{{{params['t']:g}}} "
            rf"\approx {value:.2f} \text{{ N}}\cdot\text{{m}}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"\tau = \frac{\Delta L}{\Delta t}",),
            substitutions=(
                rf"\tau = \frac{{{params['L_f']:g} - {params['L_i']:g}}}{{{params['t']:g}}}",
            ),
            quantities=(QuantityResult("", value, "N*m"),),
        )
    if unknown == "L_f":
        value = params["L_i"] + params["tau"] * params["t"]
        answer = (
            rf"L_f = L_i + \tau\Delta t \approx {value:.2f} "
            r"\text{ kg}\,\text{m}^2\text{/s}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"L_f = L_i + \tau\Delta t",),
            substitutions=(rf"L_f = {params['L_i']:g} + {params['tau']:g} \cdot {params['t']:g}",),
            quantities=(QuantityResult("", value, "kg*m^2/s"),),
        )
    if unknown == "L_i":
        value = params["L_f"] - params["tau"] * params["t"]
        answer = (
            rf"L_i = L_f - \tau\Delta t \approx {value:.2f} "
            r"\text{ kg}\,\text{m}^2\text{/s}"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"L_i = L_f - \tau\Delta t",),
            substitutions=(rf"L_i = {params['L_f']:g} - {params['tau']:g} \cdot {params['t']:g}",),
            quantities=(QuantityResult("", value, "kg*m^2/s"),),
        )
    if params["tau"] == 0:
        raise SolveServiceError("a zero torque does not determine the time")
    value = (params["L_f"] - params["L_i"]) / params["tau"]
    answer = rf"\Delta t = \frac{{\Delta L}}{{\tau}} \approx {value:.2f} \text{{ s}}"
    return PhysicsResult(
        answer=answer,
        formulas=(r"\Delta t = \frac{\Delta L}{\tau}",),
        substitutions=(
            rf"\Delta t = \frac{{{params['L_f']:g} - {params['L_i']:g}}}{{{params['tau']:g}}}",
        ),
        quantities=(QuantityResult("", value, "s"),),
    )


def _angular_momentum(params: dict[str, float]) -> PhysicsResult:
    unknown = one_unknown(params, ("inertia_i", "omega_i", "inertia_f", "omega_f"))
    for key in ("inertia_i", "inertia_f"):
        if key != unknown and params[key] <= 0:
            raise SolveServiceError("moment of inertia must be positive")
    if unknown == "omega_f":
        value = params["inertia_i"] * params["omega_i"] / params["inertia_f"]
        shown = r"\omega_f"
        plugged = (
            rf"\omega_f = \frac{{{params['inertia_i']:g} \cdot {params['omega_i']:g}}}"
            rf"{{{params['inertia_f']:g}}}"
        )
    elif unknown == "omega_i":
        value = params["inertia_f"] * params["omega_f"] / params["inertia_i"]
        shown = r"\omega_i"
        plugged = (
            rf"\omega_i = \frac{{{params['inertia_f']:g} \cdot {params['omega_f']:g}}}"
            rf"{{{params['inertia_i']:g}}}"
        )
    elif unknown == "inertia_f":
        if params["omega_f"] == 0:
            raise SolveServiceError("final angular velocity must be nonzero")
        value = params["inertia_i"] * params["omega_i"] / params["omega_f"]
        shown = "I_f"
        plugged = (
            rf"I_f = \frac{{{params['inertia_i']:g} \cdot {params['omega_i']:g}}}"
            rf"{{{params['omega_f']:g}}}"
        )
    else:
        if params["omega_i"] == 0:
            raise SolveServiceError("initial angular velocity must be nonzero")
        value = params["inertia_f"] * params["omega_f"] / params["omega_i"]
        shown = "I_i"
        plugged = (
            rf"I_i = \frac{{{params['inertia_f']:g} \cdot {params['omega_f']:g}}}"
            rf"{{{params['omega_i']:g}}}"
        )
    if unknown.startswith("inertia") and value <= 0:
        raise SolveServiceError("moment of inertia must be positive")
    unit = r"\text{ rad/s}" if unknown.startswith("omega") else r"\text{ kg}\,\text{m}^2"
    readable = "rad/s" if unknown.startswith("omega") else "kg*m^2"
    answer = rf"I_i\omega_i = I_f\omega_f \Rightarrow {shown} \approx {value:.2f} {unit}"
    return PhysicsResult(
        answer=answer,
        formulas=(rf"I_i\omega_i = I_f\omega_f \Rightarrow {shown}",),
        substitutions=(plugged,),
        quantities=(QuantityResult("", value, readable),),
    )
