"""Canonical registry of verified physics operations.

Law name, base equation, result symbol, and assumptions are read from here.
``PhysicsIntent.physics_op`` is a catalog id, and ``check_intent`` is the one
place that decides which ids, kinds and parameters exist.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.modules.physics.catalog.astrophysics import SPECS as ASTROPHYSICS
from app.modules.physics.catalog.buoyancy import SPECS as BUOYANCY
from app.modules.physics.catalog.capacitors import SPECS as CAPACITORS
from app.modules.physics.catalog.circuit import SPECS as CIRCUIT
from app.modules.physics.catalog.circular import SPECS as CIRCULAR
from app.modules.physics.catalog.condensed_matter import SPECS as CONDENSED_MATTER
from app.modules.physics.catalog.electric_field import SPECS as ELECTRIC_FIELD
from app.modules.physics.catalog.energy import SPECS as ENERGY
from app.modules.physics.catalog.fluids import SPECS as FLUIDS
from app.modules.physics.catalog.force import SPECS as FORCE
from app.modules.physics.catalog.friction import SPECS as FRICTION
from app.modules.physics.catalog.gas_laws import SPECS as GAS_LAWS
from app.modules.physics.catalog.gravitation import SPECS as GRAVITATION
from app.modules.physics.catalog.heat import SPECS as HEAT
from app.modules.physics.catalog.heat import WATER_ONLY
from app.modules.physics.catalog.inductance_ac import SPECS as INDUCTANCE_AC
from app.modules.physics.catalog.kinematics import SPECS as KINEMATICS
from app.modules.physics.catalog.machine_ratios import SPECS as MACHINE_RATIOS
from app.modules.physics.catalog.machines import SPECS as MACHINES
from app.modules.physics.catalog.magnetism import SPECS as MAGNETISM
from app.modules.physics.catalog.materials import SPECS as MATERIALS
from app.modules.physics.catalog.modern import SPECS as MODERN
from app.modules.physics.catalog.momentum import SPECS as MOMENTUM
from app.modules.physics.catalog.nuclear import SPECS as NUCLEAR
from app.modules.physics.catalog.optics import SPECS as OPTICS
from app.modules.physics.catalog.particles import SPECS as PARTICLES
from app.modules.physics.catalog.plasma import SPECS as PLASMA
from app.modules.physics.catalog.projectile import SPECS as PROJECTILE
from app.modules.physics.catalog.quantum import SPECS as QUANTUM
from app.modules.physics.catalog.relativity import SPECS as RELATIVITY
from app.modules.physics.catalog.rotation import SPECS as ROTATION
from app.modules.physics.catalog.spring import SPECS as SPRING
from app.modules.physics.catalog.suvat import SPECS as SUVAT
from app.modules.physics.catalog.thermal import SPECS as THERMAL
from app.modules.physics.catalog.torque import SPECS as TORQUE
from app.modules.physics.catalog.wave_optics import SPECS as WAVE_OPTICS
from app.modules.physics.catalog.waves import SPECS as WAVES
from app.services.law_binding.spec import (
    FormulaSpec,
    formula,
    matching_variant,
    select_formula,
    symbol_for,
    variable_for,
    visible_assumptions,
)

__all__ = [
    "CATALOG",
    "WATER_ONLY",
    "FormulaSpec",
    "check_intent",
    "formula",
    "formula_spec",
    "matching_variant",
    "select_formula",
    "symbol_for",
    "variable_for",
    "visible_assumptions",
]


def _register(*groups: tuple[FormulaSpec, ...]) -> dict[str, FormulaSpec]:
    catalog: dict[str, FormulaSpec] = {}
    for group in groups:
        for spec in group:
            if spec.id in catalog:
                raise RuntimeError(f"duplicate physics formula {spec.id}")
            catalog[spec.id] = spec
    return catalog


CATALOG: dict[str, FormulaSpec] = _register(
    KINEMATICS,
    PROJECTILE,
    SUVAT,
    FORCE,
    ENERGY,
    MACHINES,
    MACHINE_RATIOS,
    MOMENTUM,
    FRICTION,
    CIRCULAR,
    SPRING,
    TORQUE,
    ROTATION,
    CIRCUIT,
    CAPACITORS,
    INDUCTANCE_AC,
    WAVES,
    OPTICS,
    WAVE_OPTICS,
    THERMAL,
    GAS_LAWS,
    HEAT,
    GRAVITATION,
    FLUIDS,
    BUOYANCY,
    MAGNETISM,
    ELECTRIC_FIELD,
    PLASMA,
    MATERIALS,
    MODERN,
    QUANTUM,
    RELATIVITY,
    NUCLEAR,
    PARTICLES,
    CONDENSED_MATTER,
    ASTROPHYSICS,
)


def formula_spec(operation: str) -> FormulaSpec | None:
    return CATALOG.get(operation)


def check_intent(kind: str, operation: str, params: Iterable[str], units: Iterable[str]) -> None:
    """Refuse a kind, operation, or parameter the formula catalog does not contain.

    The intent schema calls this for every intent it validates; a ValueError
    here is that intent's validation error.
    """
    spec = CATALOG.get(operation)
    if spec is None or spec.kind != kind:
        raise ValueError(f"{kind} does not define {operation}")
    allowed = {variable.name for variable in spec.variables}
    given = set(params)
    unknown = given - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"{operation} does not declare {names}")
    extra_units = set(units) - given
    if extra_units:
        names = ", ".join(sorted(extra_units))
        raise ValueError(f"{operation} units are not parameters: {names}")
