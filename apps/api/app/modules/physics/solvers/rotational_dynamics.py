"""Constant-alpha rotation, angular momentum, rolling and the parallel-axis theorem.

Each operation is solved in its topic module; this module picks it.
"""

from __future__ import annotations

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.angular_momentum import _angular_impulse, _angular_momentum
from app.modules.physics.solvers.results import PhysicsResult
from app.modules.physics.solvers.rolling import (
    _parallel_axis,
    _rolling_acceleration,
    _rolling_energy,
    _rolling_speed,
)
from app.modules.physics.solvers.rotational_kinematics import (
    _alpha,
    _omega,
    _theta,
    _torque_inertia,
)
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def solve_rotational_dynamics(intent: PhysicsIntent) -> PhysicsResult:
    params = params_in_si(intent)
    operation = intent.physics_op or ""
    if operation == "rotational_omega":
        return _omega(params)
    if operation == "rotational_theta":
        return _theta(params)
    if operation == "rotational_alpha":
        return _alpha(params)
    if operation == "torque_inertia":
        return _torque_inertia(params)
    if operation == "torque_angular_impulse":
        return _angular_impulse(params)
    if operation == "angular_momentum_conservation":
        return _angular_momentum(params)
    if operation == "rolling_speed":
        return _rolling_speed(params)
    if operation == "rolling_acceleration":
        return _rolling_acceleration(params)
    if operation == "rolling_kinetic_energy":
        return _rolling_energy(params)
    if operation == "parallel_axis":
        return _parallel_axis(params)
    raise SolveServiceError(f"unsupported rotational op: {operation}")
