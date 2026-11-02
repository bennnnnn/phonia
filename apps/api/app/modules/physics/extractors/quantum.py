"""Quantum readers: uncertainty, a particle in a box, hydrogen levels, Compton,
the photoelectric effect, photons and de Broglie."""

from __future__ import annotations

import re

from app.modules.physics.constants import ELECTRON_MASS
from app.modules.physics.extractors.angles import INCLINE_ANGLE_RE
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.unit_patterns import (
    LENGTH_UNIT_PATTERN,
    MASS_UNITS,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.extractors.waves import _HERTZ_PATTERN
from app.modules.physics.schemas import PhysicsIntent


def _uncertainty(cleaned: str) -> PhysicsIntent | None:
    """The least momentum uncertainty for a stated position uncertainty."""
    uncertainty = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("position uncertainty", "delta x", "uncertainty")
    )
    if uncertainty is None:
        return None
    return PhysicsIntent(
        kind="modern",
        physics_op="uncertainty_momentum",
        physics_params={"uncertainty_x": uncertainty[0]},
        physics_units={"uncertainty_x": uncertainty[1] or "m"},
        operation="solve",
    )


def _particle_in_box(cleaned: str) -> PhysicsIntent | None:
    """A particle's energy level in an infinite square well."""
    lower = cleaned.lower()
    length = find_value_with_specific_unit(cleaned, LENGTH_UNIT_PATTERN, ("box", "width", "length"))
    level = re.search(r"\bn\s*(?:=|is)\s*(\d+)\b", cleaned, re.IGNORECASE)
    mass = find_value_with_specific_unit(cleaned, MASS_UNITS, ("mass", "particle"))
    if length is None or level is None or (mass is None and "electron" not in lower):
        return None
    return PhysicsIntent(
        kind="modern",
        physics_op="particle_box_energy",
        physics_params={
            "L": length[0],
            "quantum_n": float(level.group(1)),
            "m": mass[0] if mass is not None else ELECTRON_MASS,
        },
        physics_units={
            "L": length[1] or "m",
            "quantum_n": "",
            "m": mass[1] if mass is not None else "kg",
        },
        operation="solve",
    )


def _hydrogen_level(cleaned: str) -> PhysicsIntent | None:
    """The energy of one hydrogen level."""
    # Z = 1 is this law. A stated atomic number is the hydrogen-like formula.
    if re.search(r"hydrogen-like|hydrogenic|atomic number|\bZ\s*=", cleaned, re.IGNORECASE):
        return None
    # One level is its energy; two ("falls from n = 3 to n = 2") are a
    # transition, whose photon the level formula would misreport as E₃.
    levels = re.findall(r"\bn\s*(?:=|is)\s*(\d+)\b", cleaned, re.IGNORECASE)
    if len(levels) != 1:
        return None
    return PhysicsIntent(
        kind="modern",
        physics_op="hydrogen_energy_level",
        physics_params={"quantum_n": float(levels[0])},
        physics_units={"quantum_n": ""},
        operation="solve",
    )


def _compton(cleaned: str) -> PhysicsIntent | None:
    """The Compton shift at a stated scattering angle."""
    angle = INCLINE_ANGLE_RE.search(cleaned)
    if angle is None:
        return None
    return PhysicsIntent(
        kind="modern",
        physics_op="compton_shift",
        physics_params={"angle": float(angle.group(1))},
        physics_units={"angle": "deg"},
        operation="solve",
    )


def _photoelectric(cleaned: str) -> PhysicsIntent | None:
    """The photoelectric electrons' kinetic energy.

    Stopping potential uses the same frequency and work function, answered in
    volts. Leaving that ask here would publish the kinetic energy instead.
    """
    if re.search(r"\bstopping (?:potential|voltage)\b", cleaned, re.IGNORECASE):
        return None
    freq = find_value_with_specific_unit(cleaned, _HERTZ_PATTERN)
    work_function = find_value_with_specific_unit(
        cleaned,
        r"eV|electron\s*volts?|J|joules?",
        ("work function", "phi", "threshold energy"),
        require_keyword=True,
    )
    if freq is None or work_function is None:
        return None
    return PhysicsIntent(
        kind="modern",
        physics_op="photoelectric_kinetic_energy",
        physics_params={"freq": freq[0], "work_function": work_function[0]},
        physics_units={"freq": freq[1] or "Hz", "work_function": work_function[1] or "J"},
        operation="solve",
    )


def _photon_energy(cleaned: str) -> PhysicsIntent | None:
    """A photon's energy from its frequency or wavelength.

    A photon's momentum is not its energy: that law is the catalog binder's.
    Planck's law is a spectrum, not one photon's energy, and "how many photons
    per second" is a count: one photon's energy would leave the power unused.
    """
    if re.search(
        r"spectral radiance|planck(?:'s)? law|planck distribution|blackbody distribution"
        r"|\b(?:how\s+many|number\s+of)\s+photons\b|\bphotons\s+(?:per|each|every|a)\s",
        cleaned,
        re.IGNORECASE,
    ):
        return None
    freq = find_value_with_specific_unit(cleaned, _HERTZ_PATTERN)
    wavelength = find_value_with_specific_unit(
        cleaned,
        LENGTH_UNIT_PATTERN,
        ("wavelength",),
        require_keyword=True,
    )
    if freq is None and wavelength is None:
        return None
    if freq is not None:
        photon_params = {"freq": freq[0]}
        photon_units = {"freq": freq[1] or "Hz"}
    else:
        if wavelength is None:
            return None
        photon_params = {"wavelength": wavelength[0]}
        photon_units = {"wavelength": wavelength[1] or "m"}
    return PhysicsIntent(
        kind="modern",
        physics_op="photon_energy",
        physics_params=photon_params,
        physics_units=photon_units,
        operation="solve",
    )


def _de_broglie(cleaned: str) -> PhysicsIntent | None:
    """A particle's de Broglie wavelength."""
    lower = cleaned.lower()
    speed = find_value_with_specific_unit(cleaned, VELOCITY_UNIT_PATTERN)
    mass = find_value_with_specific_unit(cleaned, MASS_UNITS, ("mass",))
    if speed is None:
        return None
    # An electron's mass is not in the question, and naming it is the point
    # of the question; any other particle has to state one.
    if mass is None and "electron" not in lower:
        return None
    return PhysicsIntent(
        kind="modern",
        physics_op="de_broglie_wavelength",
        physics_params={
            "m": mass[0] if mass is not None else ELECTRON_MASS,
            "v": speed[0],
        },
        physics_units={"m": mass[1] if mass is not None else "kg", "v": speed[1] or "m/s"},
        operation="solve",
    )
