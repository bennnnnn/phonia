"""Fluid extractors: pressure, upthrust, Bernoulli, continuity, flow."""

from __future__ import annotations

import re

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.fluid_laws import NAMED_FLUID_LAWS, pipe_sections
from app.modules.physics.extractors.fluid_readings import (
    _DENSITY_PATTERN,
    _PRESSURE_PATTERN,
    _VOLUME_PATTERN,
    AREA_PATTERN,
    FluidReading,
    read_fluid,
)
from app.modules.physics.extractors.school_extensions import blocks_fluids
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.modules.physics.extractors.unit_patterns import MASS_UNITS
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_FLUIDS_CUES = (
    "upthrust",
    "buoyant force",
    "buoyancy",
    "archimedes",
    "hydrostatic",
    "flow rate",
    "pascal's principle",
    "hydraulic",
    "bernoulli",
    "mass flow rate",
    "torricelli",
    "stokes drag",
    "stokes' drag",
    "reynolds number",
    "surface tension",
    "laplace pressure",
    "soap bubble",
)

_FLUIDS_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"\bpressure\b.{{0,80}}?\d\s*(?:{AREA_PATTERN}|{_PRESSURE_PATTERN})\b", re.IGNORECASE
    ),
    re.compile(
        rf"\d\s*(?:{AREA_PATTERN}|{_PRESSURE_PATTERN})\b.{{0,80}}?\bpressure\b", re.IGNORECASE
    ),
    re.compile(r"\bpressure\b.{0,80}?\bdepth\b", re.IGNORECASE),
    re.compile(rf"\bdensity\b.{{0,80}}?\d\s*(?:{_VOLUME_PATTERN})\b", re.IGNORECASE),
    re.compile(
        rf"\A(?=.*\bdensity\b)(?=.*\d\s*(?:{MASS_UNITS})\b)"
        rf"(?=.*\d\s*(?:{_VOLUME_PATTERN})\b)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(rf"\d\s*(?:{_DENSITY_PATTERN})\b", re.IGNORECASE),
    re.compile(rf"\bpipe\b.{{0,80}}?\d\s*(?:{AREA_PATTERN})\b", re.IGNORECASE),
    # "a pipe of diameter 4 cm, which narrows to 2 cm"
    re.compile(
        r"\A(?=.*\b(?:pipe|tube|hose)s?\b)"
        r"(?=.*\b(?:narrow(?:s|ing)?|widen(?:s|ing)?|taper(?:s|ing)?)\s+(?:\w+\s+){0,3}?to\b)"
        r"(?=.*\d\s*(?:cm|mm|m)\b)(?=.*\d\s*(?:m/s|cm/s)(?![A-Za-z0-9]))",
        re.IGNORECASE | re.DOTALL,
    ),
)

_STRESS_WORDS = ("stress", "strain", "young", "modulus", "tensile")

_ABSOLUTE_PRESSURE_RE = re.compile(r"\babsolute\b|\batmospheric\b", re.IGNORECASE)


def _extract_fluids_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _FLUIDS_CUES, _FLUIDS_CUE_RES):
        return None
    if blocks_fluids(cleaned):
        return None
    if any(word in lower for word in _STRESS_WORDS):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    reading = read_fluid(cleaned)
    for phrases, law in NAMED_FLUID_LAWS:
        if any(phrase in lower for phrase in phrases):
            return law(reading)
    return _general_law(reading)


def _general_law(f: FluidReading) -> PhysicsIntent | None:
    """Laws a fluid question states by its numbers, tried in a fixed order."""
    # --- continuity through a pipe given by its diameters ----------------
    if len(f.areas) < 2 and (sections := pipe_sections(f)) is not None:
        return sections
    # --- continuity: A1 v1 = A2 v2 --------------------------------------
    if len(f.areas) >= 2 and f.speed:
        if f.areas[1][0] == 0:
            return None
        return PhysicsIntent(
            kind="fluids",
            physics_op="continuity_velocity",
            physics_params={"A1": f.areas[0][0], "A2": f.areas[1][0], "v": f.speed[0][0]},
            physics_units={
                "A1": f.areas[0][1] or "m^2",
                "A2": f.areas[1][1] or "m^2",
                "v": f.speed[0][1] or "m/s",
            },
            operation="solve",
        )

    # --- flow rate: Q = A v ---------------------------------------------
    if "flow" in f.lower and f.area is not None and f.speed:
        return PhysicsIntent(
            kind="fluids",
            physics_op="flow_rate",
            physics_params={"area": f.area[0], "v": f.speed[0][0]},
            physics_units={"area": f.area[1] or "m^2", "v": f.speed[0][1] or "m/s"},
            operation="solve",
        )

    # --- upthrust: rho V g ----------------------------------------------
    if any(word in f.lower for word in ("upthrust", "buoyan", "archimedes")):
        rho = f.fluid_density()
        if f.volume is None or rho is None:
            return None
        if not any(word in f.lower for word in ("submerged", "immersed", "displac")):
            # A floating body displaces its own weight, not its own volume.
            # Which one is meant changes the answer, so it has to be said.
            return None
        return PhysicsIntent(
            kind="fluids",
            physics_op="upthrust",
            physics_params={"rho": rho, "volume": f.volume[0], "g": detect_gravity(f.cleaned)},
            physics_units={"rho": "kg/m^3", "volume": f.volume[1] or "m^3", "g": "m/s^2"},
            operation="solve",
        )

    # --- pressure at depth: rho g h -------------------------------------
    if f.depth is not None:
        if _ABSOLUTE_PRESSURE_RE.search(f.cleaned):
            return None
        rho = f.fluid_density()
        if rho is None:
            return None
        return PhysicsIntent(
            kind="fluids",
            physics_op="pressure_at_depth",
            physics_params={"rho": rho, "depth": f.depth[0], "g": detect_gravity(f.cleaned)},
            physics_units={"rho": "kg/m^3", "depth": f.depth[1] or "m", "g": "m/s^2"},
            operation="solve",
        )

    # --- density: rho = m / V -------------------------------------------
    # A density already written is the fluid's. m/V is only when none is given.
    if "density" in f.lower and f.mass is not None and f.volume is not None and f.density is None:
        return PhysicsIntent(
            kind="fluids",
            physics_op="density",
            physics_params={"m": f.mass[0], "volume": f.volume[0]},
            physics_units={"m": f.mass[1] or "kg", "volume": f.volume[1] or "m^3"},
            operation="solve",
        )

    # --- pressure from a force: P = F / A --------------------------------
    if f.force is not None and f.area is not None:
        return PhysicsIntent(
            kind="fluids",
            physics_op="pressure_from_force",
            physics_params={"F": f.force[0], "area": f.area[0]},
            physics_units={"F": f.force[1] or "N", "area": f.area[1] or "m^2"},
            operation="solve",
        )
    return None
