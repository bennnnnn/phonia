"""The values a physics binding fills without reading them from the question.

A setting an input takes when the question names it without a number (g,
a planet's mass, an electron's charge, water's c), in the unit physics writes it.
"""

from __future__ import annotations

import re

from app.modules.physics.bodies import (
    SEA_LEVEL_PRESSURE,
    WATER_DENSITY,
    WATER_SPECIFIC_HEAT,
    named_body,
    named_particle_charge,
    named_particle_mass,
    names_only_water,
)
from app.modules.physics.display import si_symbol
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.services.law_binding.spec import VariableSpec
from app.services.text_match import word_index


def fallback_value(variable: VariableSpec, text: str, lower: str) -> float | None:
    """A setting an unstated input takes: g, a named planet's mass, an electron's charge."""
    fallback = variable.fallback
    if fallback == "gravity":
        return detect_gravity(text)
    if fallback in {"body_mass", "body_radius"}:
        body = named_body(lower)
        return None if body is None else body[0 if fallback == "body_mass" else 1]
    if fallback == "particle_charge":
        return named_particle_charge(lower)
    if fallback == "particle_mass":
        return named_particle_mass(lower)
    if fallback == "calorimeter_water":
        # The water a hot object is dropped into: its c, whatever else the question names.
        return WATER_SPECIFIC_HEAT if word_index(lower, "water") != -1 else None
    if fallback in {"water_specific_heat", "water_density"}:
        if not names_only_water(lower):
            return None
        return WATER_SPECIFIC_HEAT if fallback == "water_specific_heat" else WATER_DENSITY
    if fallback == "sea_level_pressure":
        return SEA_LEVEL_PRESSURE
    if fallback == "incident_from_air":
        return AIR_INDEX if light_enters_from_air(lower) else None
    return None


AIR_INDEX = 1.0
# Light that strikes, hits or enters a medium. Read alone, it came from air.
_ENTERS_RE = re.compile(
    r"\b(?:strikes?|striking|hits?|hitting|incident\s+on|falls?\s+on|falling\s+on"
    r"|enters?|entering)\b"
)
# Light that starts inside a medium, or comes from a named one, is not from air.
_STARTS_INSIDE_RE = re.compile(
    r"\b(?:inside|within|internal(?:ly)?|leaves?|leaving|emerges?|emerging|exits?|exiting"
    r"|escapes?|escaping|out\s+of|into\s+(?:the\s+)?(?:air|vacuum)|travell?ing\s+in|moving\s+in"
    r"|underwater|under\s+water|submerged|beneath|below\s+the\s+surface"
    r"|from\s+(?!(?:(?:a|an|the)\s+)?(?:air|surface|boundary|interface|normal|vacuum"
    r"|horizontal|vertical)\b)(?:a\s+|an\s+|the\s+)?[a-z]+)\b"
)


def light_enters_from_air(lower: str) -> bool:
    """A ray that strikes a medium and is never said to start inside one."""
    return _ENTERS_RE.search(lower) is not None and _STARTS_INSIDE_RE.search(lower) is None


def si_unit(variable: VariableSpec) -> str:
    if variable.name.startswith("angle"):
        return "deg"
    return si_symbol(variable.dimension) if variable.dimension else ""
