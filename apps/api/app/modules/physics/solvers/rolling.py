"""Rolling without slipping (speed, acceleration and energy) and the parallel-axis theorem."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import one_unknown
from app.services.solving import SolveServiceError


@dataclass(frozen=True)
class _RollingLaw:
    """Rolling without slipping at one order: v = R omega, or a = R alpha."""

    linear: str
    angular: str
    linear_tex: str
    angular_tex: str
    linear_unit: str
    angular_unit: str
    angular_name: str


_SPEED = _RollingLaw("v", "omega", "v", r"\omega", "m/s", "rad/s", "angular velocity")
_ACCELERATION = _RollingLaw(
    "a", "ang_alpha", "a", r"\alpha", "m/s^2", "rad/s^2", "angular acceleration"
)


def _unit_tex(unit: str) -> str:
    """``m/s^2`` as the answer writes it: ``\\text{ m/s}^2``."""
    base, power = unit.split("^") if "^" in unit else (unit, "")
    return rf"\text{{ {base}}}" + (f"^{power}" if power else "")


def _rolling(params: dict[str, float], law: _RollingLaw) -> PhysicsResult:
    lin, ang, lt, at = law.linear, law.angular, law.linear_tex, law.angular_tex
    unknown = one_unknown(params, (lin, ang, "r"))
    if unknown != "r" and params["r"] <= 0:
        raise SolveServiceError("radius must be positive")
    if unknown == lin:
        value = params["r"] * params[ang]
        product = rf"{params['r']:g} \cdot {params[ang]:g}"
        return PhysicsResult(
            answer=rf"{lt} = R{at} = {product} \approx {value:.2f} {_unit_tex(law.linear_unit)}",
            formulas=(rf"{lt} = R{at}",),
            substitutions=(rf"{lt} = {product}",),
            quantities=(QuantityResult("", value, law.linear_unit),),
        )
    if unknown == ang:
        value = params[lin] / params["r"]
        quotient = rf"\frac{{{params[lin]:g}}}{{{params['r']:g}}}"
        formula = rf"{at} = \frac{{{lt}}}{{R}}"
        return PhysicsResult(
            answer=rf"{formula} = {quotient} \approx {value:.2f} {_unit_tex(law.angular_unit)}",
            formulas=(formula,),
            substitutions=(rf"{at} = {quotient}",),
            quantities=(QuantityResult("", value, law.angular_unit),),
        )
    if params[ang] == 0:
        raise SolveServiceError(f"{law.angular_name} must be nonzero to find the radius")
    value = params[lin] / params[ang]
    if value <= 0:
        raise SolveServiceError("radius must be positive")
    formula = rf"R = \frac{{{lt}}}{{{at}}}"
    return PhysicsResult(
        answer=rf"{formula} \approx {value:.2f} \text{{ m}}",
        formulas=(formula,),
        substitutions=(rf"R = \frac{{{params[lin]:g}}}{{{params[ang]:g}}}",),
        quantities=(QuantityResult("", value, "m"),),
    )


def _rolling_speed(params: dict[str, float]) -> PhysicsResult:
    return _rolling(params, _SPEED)


def _rolling_acceleration(params: dict[str, float]) -> PhysicsResult:
    return _rolling(params, _ACCELERATION)


def _rolling_energy(params: dict[str, float]) -> PhysicsResult:
    if params["m"] <= 0 or params["inertia"] <= 0:
        raise SolveServiceError("mass and moment of inertia must be positive")
    speed = params.get("v")
    omega = params.get("omega")
    radius = params.get("r")
    if speed is None and omega is not None and radius is not None:
        if radius <= 0:
            raise SolveServiceError("radius must be positive")
        speed = radius * omega
    elif omega is None and speed is not None and radius is not None:
        if radius <= 0:
            raise SolveServiceError("radius must be positive")
        omega = speed / radius
    if speed is None or omega is None:
        raise SolveServiceError("rolling energy needs both speeds, or one speed and the radius")
    value = 0.5 * params["m"] * speed**2 + 0.5 * params["inertia"] * omega**2
    answer = (
        r"K = \frac{1}{2}Mv^2 + \frac{1}{2}I\omega^2 \approx "
        rf"{value:.2f} \text{{ J}}"
    )
    return PhysicsResult(
        answer=answer,
        formulas=(r"K = \frac{1}{2}Mv^2 + \frac{1}{2}I\omega^2",),
        substitutions=(
            rf"K = \frac{{1}}{{2}} \cdot {params['m']:g} \cdot {speed:g}^2 + "
            rf"\frac{{1}}{{2}} \cdot {params['inertia']:g} \cdot {omega:g}^2",
        ),
        quantities=(QuantityResult("", value, "J"),),
    )


def _parallel_axis(params: dict[str, float]) -> PhysicsResult:
    unknown = one_unknown(params, ("inertia", "inertia_cm", "m", "d"))
    if unknown != "m" and params["m"] <= 0:
        raise SolveServiceError("mass must be positive")
    if unknown == "inertia":
        value = params["inertia_cm"] + params["m"] * params["d"] ** 2
        answer = (
            rf"I = I_{{cm}} + Md^2 = {params['inertia_cm']:g} + "
            rf"{params['m']:g} \cdot {latex_num(params['d'], square=True)} "
            rf"\approx {value:.2f} \text{{ kg}}\,\text{{m}}^2"
        )
        return PhysicsResult(
            answer=answer,
            formulas=(r"I = I_{cm} + Md^2",),
            substitutions=(
                rf"I = {params['inertia_cm']:g} + {params['m']:g} \cdot "
                rf"{latex_num(params['d'], square=True)}",
            ),
            quantities=(QuantityResult("", value, "kg*m^2"),),
        )
    if unknown == "inertia_cm":
        value = params["inertia"] - params["m"] * params["d"] ** 2
        answer = rf"I_{{cm}} = I - Md^2 \approx {value:.2f} \text{{ kg}}\,\text{{m}}^2"
        return PhysicsResult(
            answer=answer,
            formulas=(r"I_{cm} = I - Md^2",),
            substitutions=(
                rf"I_{{cm}} = {params['inertia']:g} - {params['m']:g} \cdot "
                rf"{latex_num(params['d'], square=True)}",
            ),
            quantities=(QuantityResult("", value, "kg*m^2"),),
        )
    if unknown == "m":
        if params["d"] == 0:
            raise SolveServiceError("a zero distance does not determine the mass")
        value = (params["inertia"] - params["inertia_cm"]) / params["d"] ** 2
        if value <= 0:
            raise SolveServiceError("mass must be positive")
        answer = rf"M = \frac{{I - I_{{cm}}}}{{d^2}} \approx {value:.2f} \text{{ kg}}"
        return PhysicsResult(
            answer=answer,
            formulas=(r"M = \frac{I - I_{cm}}{d^2}",),
            substitutions=(
                rf"M = \frac{{{params['inertia']:g} - {params['inertia_cm']:g}}}"
                rf"{{{latex_num(params['d'], square=True)}}}",
            ),
            quantities=(QuantityResult("", value, "kg"),),
        )
    square = (params["inertia"] - params["inertia_cm"]) / params["m"]
    if square < 0:
        raise SolveServiceError("those values do not give a real distance")
    value = math.sqrt(square)
    answer = rf"d = \sqrt{{\frac{{I - I_{{cm}}}}{{M}}}} \approx {value:.2f} \text{{ m}}"
    return PhysicsResult(
        answer=answer,
        formulas=(r"d = \sqrt{\frac{I - I_{cm}}{M}}",),
        substitutions=(
            rf"d = \sqrt{{\frac{{{params['inertia']:g} - {params['inertia_cm']:g}}}"
            rf"{{{params['m']:g}}}}}",
        ),
        quantities=(QuantityResult("", value, "m"),),
    )
