"""Rotational mechanics solvers: moment of inertia, rotational kinetic energy and angular
momentum. Constant-alpha, rolling and parallel-axis operations go to rotational_dynamics.
"""

from __future__ import annotations

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.rotational_dynamics import solve_rotational_dynamics
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def solve_rotation(intent: PhysicsIntent) -> PhysicsResult:
    if intent.physics_op in {
        "rotational_omega",
        "rotational_theta",
        "rotational_alpha",
        "torque_inertia",
        "torque_angular_impulse",
        "angular_momentum_conservation",
        "rolling_speed",
        "rolling_acceleration",
        "rolling_kinetic_energy",
        "parallel_axis",
    }:
        return solve_rotational_dynamics(intent)

    p = params_in_si(intent)
    op = intent.physics_op or ""

    if op == "moment_of_inertia":
        factor = p["shape_factor"]
        value = factor * p["m"] * p["r"] ** 2
        return PhysicsResult(
            answer=(
                rf"I = {factor:g} m r^2 = {factor:g} \cdot {p['m']:g} \cdot "
                rf"{latex_num(p['r'], square=True)} \approx {value:.2f} "
                rf"\text{{ kg}}\,\text{{m}}^2"
            ),
            formulas=(rf"I = {factor:g} m r^2",),
            substitutions=(
                rf"I = {factor:g} \cdot {p['m']:g} \cdot {latex_num(p['r'], square=True)}",
            ),
            quantities=(QuantityResult("", value, "kg*m^2"),),
        )

    if op == "angular_momentum":
        value = p["inertia"] * p["omega"]
        return PhysicsResult(
            answer=(
                rf"L = I\omega = {p['inertia']:g} \cdot {p['omega']:g} "
                rf"\approx {value:.2f} \text{{ kg}}\,\text{{m}}^2\text{{/s}}"
            ),
            formulas=(r"L = I\omega",),
            substitutions=(rf"L = {p['inertia']:g} \cdot {p['omega']:g}",),
            quantities=(QuantityResult("", value, "kg*m^2/s"),),
        )

    if op == "rotational_kinetic_energy":
        value = 0.5 * p["inertia"] * p["omega"] ** 2
        return PhysicsResult(
            answer=(
                rf"E_k = \tfrac{{1}}{{2}} I \omega^2 = 0.5 \cdot {p['inertia']:g} \cdot "
                rf"{latex_num(p['omega'], square=True)} \approx {value:.2f} \text{{ J}}"
            ),
            formulas=(r"E_k = \tfrac{1}{2} I \omega^2",),
            substitutions=(
                rf"E_k = 0.5 \cdot {p['inertia']:g} \cdot {latex_num(p['omega'], square=True)}",
            ),
            quantities=(QuantityResult("", value, "J"),),
        )

    if op == "angular_displacement_rate":
        elapsed = p["t"]
        if elapsed <= 0:
            raise SolveServiceError("elapsed time must be positive")
        value = p["theta"] / elapsed
        return PhysicsResult(
            answer=(
                rf"\omega = \frac{{\theta}}{{t}} = \frac{{{p['theta']:g}}}{{{elapsed:g}}} "
                rf"\approx {value:.2f} \text{{ rad/s}}"
            ),
            formulas=(r"\omega = \frac{\theta}{t}",),
            substitutions=(rf"\omega = \frac{{{p['theta']:g}}}{{{elapsed:g}}}",),
            quantities=(QuantityResult("", value, "rad/s"),),
        )

    raise SolveServiceError(f"unsupported rotation op: {op}")
