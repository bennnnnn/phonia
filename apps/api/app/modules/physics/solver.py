"""Stable public facade for the subject-grouped physics solvers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.circuits import solve_circuit
from app.modules.physics.solvers.circular import solve_circular
from app.modules.physics.solvers.energy import solve_energy
from app.modules.physics.solvers.fluids import solve_fluids
from app.modules.physics.solvers.forces import solve_force
from app.modules.physics.solvers.friction import solve_friction
from app.modules.physics.solvers.gravitation import solve_gravitation
from app.modules.physics.solvers.kinematics import solve_kinematics
from app.modules.physics.solvers.magnetism import solve_magnetism
from app.modules.physics.solvers.materials import solve_materials
from app.modules.physics.solvers.modern import solve_modern
from app.modules.physics.solvers.momentum import solve_momentum
from app.modules.physics.solvers.optics import solve_optics
from app.modules.physics.solvers.oscillations import solve_spring
from app.modules.physics.solvers.projectile import solve_projectile
from app.modules.physics.solvers.relation import solve_expression
from app.modules.physics.solvers.results import PhysicsResult
from app.modules.physics.solvers.rotation import solve_rotation
from app.modules.physics.solvers.school_extensions import SCHOOL_SOLVERS
from app.modules.physics.solvers.si import params_in_si
from app.modules.physics.solvers.suvat import solve_suvat
from app.modules.physics.solvers.thermal import solve_thermal
from app.modules.physics.solvers.torque import solve_torque
from app.modules.physics.solvers.waves import solve_waves
from app.services.solving import SolveServiceError

# What callers import; the subject solvers stay reachable as module attributes for tests.
__all__ = ["PHYSICS_SOLVERS", "PhysicsResult", "solve_physics"]


def _accepts_si_params(
    fn: Callable[[dict[str, float]], PhysicsResult],
) -> Callable[[PhysicsIntent], PhysicsResult]:
    def run(intent: PhysicsIntent) -> PhysicsResult:
        return fn(params_in_si(intent))

    return run


def _claim_solvers() -> dict[str, Callable[[PhysicsIntent], PhysicsResult]]:
    """One operation, one solver. A second claim is a registration error."""
    from app.modules.physics.catalog import CATALOG

    by_kind: dict[str, Callable[[PhysicsIntent], PhysicsResult]] = {
        "kinematics": solve_kinematics,
        "suvat": solve_suvat,
        "projectile": solve_projectile,
        "force": solve_force,
        "energy": solve_energy,
        "momentum": solve_momentum,
        "friction": solve_friction,
        "circular": solve_circular,
        "spring": solve_spring,
        "circuit": solve_circuit,
        "torque": solve_torque,
        "waves": solve_waves,
        "optics": solve_optics,
        "thermal": solve_thermal,
        "gravitation": solve_gravitation,
        "fluids": solve_fluids,
        "rotation": solve_rotation,
        "magnetism": solve_magnetism,
        "materials": solve_materials,
        "modern": solve_modern,
    }
    claimed: dict[str, Callable[[PhysicsIntent], PhysicsResult]] = {}

    def claim(operation: str, fn: Callable[[PhysicsIntent], PhysicsResult]) -> None:
        if operation in claimed:
            raise RuntimeError(f"two physics solvers claim {operation}")
        claimed[operation] = fn

    # A law the catalog writes as arithmetic needs no solver of its own.
    for spec in CATALOG.values():
        if spec.expression is not None:
            claim(spec.id, solve_expression)
    for operation, fn in SCHOOL_SOLVERS.items():
        claim(operation, _accepts_si_params(fn))
    # Intent callables. The fluids and circular kind solvers do not know these ops.
    from app.modules.physics.solvers.drag import DRAG_SOLVERS

    for operation, drag_solver in DRAG_SOLVERS.items():
        claim(operation, drag_solver)
    for spec in CATALOG.values():
        if spec.id in claimed:
            continue
        kind_solver = by_kind.get(spec.kind)
        if kind_solver is None:
            raise RuntimeError(f"no physics solver for kind {spec.kind}")
        claim(spec.id, kind_solver)
    missing = set(CATALOG) - set(claimed)
    if missing:
        raise RuntimeError(f"physics catalog ids without a solver: {sorted(missing)}")
    return claimed


PHYSICS_SOLVERS = _claim_solvers()


def solve_physics(intent: PhysicsIntent) -> PhysicsResult:
    """Dispatch on the operation. The catalog id is the only key."""
    from app.modules.physics.solvers.catalog_scenes import catalog_scene
    from app.modules.physics.working import attach_recorded_working

    operation = intent.physics_op or ""
    solver = PHYSICS_SOLVERS.get(operation)
    if solver is None:
        raise SolveServiceError(f"unsupported physics op: {operation}")
    result = attach_recorded_working(solver(intent), intent)
    # A law solved as arithmetic has no solver of its own to draw it.
    if result.quantities and not result.simulation_specs and not result.graph_specs:
        scene = catalog_scene(intent, params_in_si(intent), result.quantities[0].value)
        if scene:
            result = replace(result, simulation_specs=scene)
    return result
