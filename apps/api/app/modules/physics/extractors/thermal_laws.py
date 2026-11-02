"""Thermal laws a question names: Carnot, entropy, conduction, expansion, latent heat,
the first law and engine efficiency."""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.physics.extractors.fluid_readings import AREA_PATTERN
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.thermal_readings import (
    _REJECTED_WORDS,
    _SUPPLIED_WORDS,
    _WORK_WORDS,
    _efficiency_intent,
    _nearest_labeled_energy,
    _reservoir_temperatures,
    _temperature_change,
    _temperature_value,
)
from app.modules.physics.extractors.unit_patterns import LENGTH_UNIT_PATTERN, MASS_UNITS, NUMBER
from app.modules.physics.schemas import PhysicsIntent


def _carnot(cleaned: str) -> PhysicsIntent | None:
    """The Carnot efficiency between two reservoirs."""
    reservoirs = _reservoir_temperatures(cleaned)
    if reservoirs is None:
        return None
    (hot, hot_unit), (cold, cold_unit) = reservoirs
    return PhysicsIntent(
        kind="thermal",
        physics_op="carnot_efficiency",
        physics_params={"temp": hot, "temp_env": cold},
        physics_units={"temp": hot_unit, "temp_env": cold_unit},
        operation="solve",
    )


def _entropy(cleaned: str) -> PhysicsIntent | None:
    """The entropy change for heat added at a temperature in kelvin."""
    heat = find_value_with_specific_unit(cleaned, r"kilojoules?|joules?|kJ|J", ("heat", "energy"))
    temp = _temperature_value(cleaned, ("temperature", "at"))
    if heat is None or temp is None or temp[1] != "K":
        return None
    return PhysicsIntent(
        kind="thermal",
        physics_op="entropy_change",
        physics_params={"heat": heat[0], "temp": temp[0]},
        physics_units={"heat": heat[1] or "J", "temp": "K"},
        operation="solve",
    )


def _conduction(cleaned: str) -> PhysicsIntent | None:
    """The rate of heat conduction through a slab."""
    conductivity = find_value_with_specific_unit(
        cleaned,
        r"W/m/K|W/\(m\s*K\)|watts?\s+per\s+met(?:er|re)\s+per\s+kelvin",
        ("thermal conductivity", "conductivity"),
    )
    area = find_value_with_specific_unit(cleaned, AREA_PATTERN, ("area",))
    thickness = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("thickness", "length"), require_keyword=True
    )
    rise = _temperature_change(cleaned, ("temperature difference", "difference", "delta t"))
    if conductivity is None or area is None or thickness is None or rise is None:
        return None
    return PhysicsIntent(
        kind="thermal",
        physics_op="heat_conduction_rate",
        physics_params={
            "thermal_conductivity": conductivity[0],
            "area": area[0],
            "delta_temp": rise[0],
            "L": thickness[0],
        },
        physics_units={
            "thermal_conductivity": conductivity[1] or "W/m/K",
            "area": area[1] or "m^2",
            "delta_temp": "K",
            "L": thickness[1] or "m",
        },
        operation="solve",
    )


def _expansion(cleaned: str) -> PhysicsIntent | None:
    """Linear thermal expansion: dL = alpha L0 dT."""
    length = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("rod", "wire", "length", "long")
    )
    alpha_match = re.search(
        rf"(?:coefficient(?:\s+of\s+linear\s+expansion)?|alpha|\u03b1)\s*"
        rf"(?:of|is|=|:)?\s*({NUMBER})\s*(1/K|/K|K\^?-?1|1/°C|/°C)",
        cleaned,
        re.IGNORECASE,
    )
    rise = _temperature_change(cleaned, ("heated by", "temperature change", "change", "by"))
    if length is None or alpha_match is None or rise is None:
        return None
    return PhysicsIntent(
        kind="thermal",
        physics_op="linear_expansion",
        physics_params={
            "L0": length[0],
            "alpha": float(alpha_match.group(1)),
            "delta_temp": rise[0],
        },
        physics_units={
            "L0": length[1] or "m",
            "alpha": alpha_match.group(2),
            "delta_temp": "K",
        },
        operation="solve",
    )


def _latent_heat(cleaned: str) -> PhysicsIntent | None:
    """A phase change: Q = mL."""
    mass = find_value_with_specific_unit(cleaned, MASS_UNITS, ("mass", "of"))
    latent = find_value_with_specific_unit(
        cleaned,
        r"J/kg|kJ/kg|joules?\s+per\s+kilogram|kilojoules?\s+per\s+kilogram",
        ("latent heat",),
    )
    if mass is None or latent is None:
        return None
    return PhysicsIntent(
        kind="thermal",
        physics_op="latent_heat",
        physics_params={"m": mass[0], "latent_heat": latent[0]},
        physics_units={"m": mass[1] or "kg", "latent_heat": latent[1] or "J/kg"},
        operation="solve",
    )


def _first_law(cleaned: str) -> PhysicsIntent | None:
    """The first law: dU = Q - W, with the work done by the system positive."""
    heat_match = re.search(
        rf"(?:heat|energy)\s+(?:added|absorbed|supplied)\D{{0,20}}?({NUMBER})\s*"
        r"(kilojoules?|joules?|kJ|J)",
        cleaned,
        re.IGNORECASE,
    )
    work_match = re.search(
        rf"work\s+(?:done\s+)?by\s+(?:the\s+)?(?:system|gas)\D{{0,20}}?({NUMBER})\s*"
        r"(kilojoules?|joules?|kJ|J)",
        cleaned,
        re.IGNORECASE,
    )
    if heat_match is None or work_match is None:
        # Refuse ambiguous sign conventions such as bare "work = 200 J".
        return None
    return PhysicsIntent(
        kind="thermal",
        physics_op="first_law_internal_energy",
        physics_params={"heat": float(heat_match.group(1)), "W": float(work_match.group(1))},
        physics_units={"heat": heat_match.group(2), "W": work_match.group(2)},
        operation="solve",
    )


def _efficiency(cleaned: str) -> PhysicsIntent | None:
    """A heat engine's efficiency, only from two labelled energies."""
    lower = cleaned.lower()
    if not any(word in lower for word in ("engine", "thermal", "heat")):
        # Machine/mechanical efficiency is handled by the energy
        # extractor, which runs later in the registry.
        return None
    # Two temperatures is a Carnot question. Two unlabeled energies are
    # not sorted into work and heat: that verifies the smaller number as work.
    return _efficiency_intent(
        _nearest_labeled_energy(cleaned, _WORK_WORDS),
        _nearest_labeled_energy(cleaned, _SUPPLIED_WORDS),
        _nearest_labeled_energy(cleaned, _REJECTED_WORDS),
    )


# Each named law and the phrases that name it, tried in this order. A question
# that names one is answered or declined by that law alone.
NAMED_THERMAL_LAWS: tuple[tuple[tuple[str, ...], Callable[[str], PhysicsIntent | None]], ...] = (
    (("carnot",), _carnot),
    (("entropy",), _entropy),
    (("heat conduction", "thermal conductivity"), _conduction),
    (("expansion",), _expansion),
    (("latent heat",), _latent_heat),
    (("first law", "internal energy"), _first_law),
    (("efficiency",), _efficiency),
)
