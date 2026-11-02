"""Magnetism: force on a current or a moving charge, flux, solenoids and motional emf."""

from __future__ import annotations

import re

from app.modules.physics.bodies import named_particle_mass
from app.modules.physics.constants import ELEMENTARY_CHARGE
from app.modules.physics.extractors.angles import _stated_angle
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.circuit_patterns import (
    _COULOMB_PATTERN,
)
from app.modules.physics.extractors.cues import (
    _has_cue_either_case,
)
from app.modules.physics.extractors.fluid_readings import AREA_PATTERN
from app.modules.physics.extractors.school_extensions import blocks_field
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.unit_patterns import (
    AMP_PATTERN,
    LENGTH_UNIT_PATTERN,
    MASS_UNITS,
    NUMBER,
    TESLA_PATTERN,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_MAGNETISM_CUES = (
    "magnetic field",
    "magnetic flux",
    "solenoid",
    "flux density",
    "motional emf",
    "magnetic radius",
    "charged particle radius",
)

_MAGNETISM_CUE_RES: tuple[re.Pattern[str], ...] = (
    # A tesla value beside a current or a charge is the signature itself.
    re.compile(
        rf"\d\s*(?:{TESLA_PATTERN})(?![A-Za-z0-9]).{{0,80}}?"
        rf"\d\s*(?:A|amps?|amperes?|C|coulombs?)(?![A-Za-z0-9])"
    ),
    re.compile(
        rf"\d\s*(?:A|amps?|amperes?|C|coulombs?)(?![A-Za-z0-9]).{{0,80}}?"
        rf"\d\s*(?:{TESLA_PATTERN})(?![A-Za-z0-9])"
    ),
    # A named particle in a field: "a proton at 3e6 m/s in a 0.5 T field".
    re.compile(
        rf"\b(?:[Pp]roton|[Ee]lectron|[Aa]lpha particle)\b.{{0,80}}?"
        rf"\d\s*(?:{TESLA_PATTERN})(?![A-Za-z0-9])"
    ),
)


def _extract_magnetism_intent(cleaned: str) -> PhysicsIntent | None:
    # The tesla signature is case-sensitive (a bare lowercase t is a tonne), so
    # this gate reads the original casing the way the pre-filter now does.
    if not _has_cue_either_case(cleaned, _MAGNETISM_CUES, _MAGNETISM_CUE_RES):
        return None
    # Hall voltage uses the same current, field, and thickness as F = BIL.
    # The catalog law owns it; this extractor must not answer first.
    if re.search(r"\bhall\b", cleaned, re.IGNORECASE):
        return None
    if blocks_field(cleaned):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    lower = cleaned.lower()
    field = find_value_with_specific_unit(cleaned, TESLA_PATTERN)
    current = find_value_with_specific_unit(cleaned, AMP_PATTERN)
    charge = find_value_with_specific_unit(cleaned, _COULOMB_PATTERN)
    speed = find_value_with_specific_unit(cleaned, VELOCITY_UNIT_PATTERN)
    mass = find_value_with_specific_unit(cleaned, MASS_UNITS, ("mass", "particle"))
    length = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("wire", "conductor", "long", "length")
    )
    area = find_value_with_specific_unit(cleaned, AREA_PATTERN)
    radius = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("distance", "from", "radius"), require_keyword=True
    )

    if charge is None and re.search(r"\b(?:proton|electron)\b", cleaned, re.IGNORECASE):
        # Magnetic force here is a magnitude; the sign distinguishes the
        # direction, which this scalar template intentionally does not infer.
        charge = (ELEMENTARY_CHARGE, "C")
    if mass is None and (particle := named_particle_mass(lower)) is not None:
        # "a proton travels at 3e6 m/s": the particle names its mass.
        mass = (particle, "kg")

    # "2000 turns per meter" is n = N/L. One metre of that winding is the
    # catalog's N and L, so B = μ0 n I. This has to run before the wire
    # branch, which declines any other "magnetic field" that also has a length.
    if field is None and "solenoid" in lower and current is not None:
        density = re.search(
            rf"({NUMBER})\s*turns?\s+per\s+met(?:er|re)\b",
            cleaned,
            re.IGNORECASE,
        )
        if density is not None:
            return PhysicsIntent(
                kind="magnetism",
                physics_op="solenoid_field",
                physics_params={"turns": float(density.group(1)), "I": current[0], "L": 1.0},
                physics_units={"turns": "", "I": current[1] or "A", "L": "m"},
                operation="solve",
            )

    # Field around a long straight wire: B = mu0 I / (2 pi r).
    if field is None and "magnetic field" in lower and current is not None and radius is not None:
        if not any(word in lower for word in ("straight wire", "long wire", "from a wire")):
            return None
        return PhysicsIntent(
            kind="magnetism",
            physics_op="magnetic_field_wire",
            physics_params={"I": current[0], "r": radius[0]},
            physics_units={"I": current[1] or "A", "r": radius[1] or "m"},
            operation="solve",
        )

    if field is None:
        return None

    # Radius of a charged particle's circular path in a perpendicular field.
    if "radius" in lower and charge is not None and speed is not None and mass is not None:
        return PhysicsIntent(
            kind="magnetism",
            physics_op="charged_particle_radius",
            physics_params={
                "m": mass[0],
                "v": speed[0],
                "Q": abs(charge[0]),
                "b_field": field[0],
            },
            physics_units={
                "m": mass[1] or "kg",
                "v": speed[1] or "m/s",
                "Q": charge[1] or "C",
                "b_field": field[1] or "T",
            },
            operation="solve",
        )

    # Motional emf for perpendicular field, rod, and motion.
    if "emf" in lower and speed is not None and length is not None:
        if "perpendicular" not in lower:
            return None
        return PhysicsIntent(
            kind="magnetism",
            physics_op="motional_emf",
            physics_params={"b_field": field[0], "wire_L": length[0], "v": speed[0]},
            physics_units={
                "b_field": field[1] or "T",
                "wire_L": length[1] or "m",
                "v": speed[1] or "m/s",
            },
            operation="solve",
        )

    # F = q v B, checked before F = B I L: a moving charge names both.
    if charge is not None and speed is not None:
        params = {"Q": charge[0], "v": speed[0], "b_field": field[0]}
        units = {
            "Q": charge[1] or "C",
            "v": speed[1] or "m/s",
            "b_field": field[1] or "T",
        }
        return PhysicsIntent(
            kind="magnetism",
            physics_op="magnetic_force_charge",
            physics_params=_with_stated_angle(cleaned, params),
            physics_units=_with_stated_angle_unit(cleaned, units),
            operation="solve",
        )

    if current is not None and length is not None:
        params = {"I": current[0], "wire_L": length[0], "b_field": field[0]}
        units = {
            "I": current[1] or "A",
            "wire_L": length[1] or "m",
            "b_field": field[1] or "T",
        }
        return PhysicsIntent(
            kind="magnetism",
            physics_op="magnetic_force_wire",
            physics_params=_with_stated_angle(cleaned, params),
            physics_units=_with_stated_angle_unit(cleaned, units),
            operation="solve",
        )

    if area is not None:
        params = {"area": area[0], "b_field": field[0]}
        units = {"area": area[1] or "m^2", "b_field": field[1] or "T"}
        return PhysicsIntent(
            kind="magnetism",
            physics_op="magnetic_flux",
            physics_params=_with_stated_angle(cleaned, params),
            physics_units=_with_stated_angle_unit(cleaned, units),
            operation="solve",
        )
    return None


def _with_stated_angle(text: str, params: dict[str, float]) -> dict[str, float]:
    angle = _stated_angle(text)
    if angle is None:
        return params
    return {**params, "angle": angle[0]}


def _with_stated_angle_unit(text: str, units: dict[str, str]) -> dict[str, str]:
    angle = _stated_angle(text)
    if angle is None:
        return units
    return {**units, "angle": angle[1]}
