"""Planets, particles and water: what a question may name instead of giving numbers."""

from __future__ import annotations

import math
import re

from app.modules.physics.ask import SENTENCE
from app.modules.physics.constants import (
    ELECTRON_MASS,
    ELEMENTARY_CHARGE,
    NEUTRON_MASS,
    PROTON_MASS,
)
from app.services.text_match import word_index

_BODY_WORDS = re.compile(
    r"\b(?:earth|moon|mars|jupiter|sun|venus|mercury|saturn|uranus|neptune|pluto)\b",
    re.IGNORECASE,
)
# The same question asked again somewhere else: "Would it be different on Mars?",
# "and also tell me how this changes on the Moon", "Compare with Jupiter."
_SIDE_MARK = re.compile(
    r"\b(?:different|differ\w*|chang\w*|compar\w*|versus|vs|instead|what\s+about|"
    r"how\s+about|also|same|as\s+well|would\s+(?:it|this|that|the\s+\w+))\b",
    re.IGNORECASE,
)


def side_questions(text: str) -> list[tuple[int, int]]:
    """Spans of the sentences that ask the question again on another body.

    Such a sentence names a body, marks a comparison, and states no value of its
    own. The main question stays on Earth: "How fast does it hit the ground?
    Would it be different on Mars?" is answered with Earth's g, and the model
    takes the comparison.
    """
    return [
        sentence.span()
        for sentence in SENTENCE.finditer(text)
        if _BODY_WORDS.search(sentence.group())
        and _SIDE_MARK.search(sentence.group())
        and not any(char.isdigit() for char in sentence.group())
    ]


def main_question(text: str) -> str:
    """The text without its side questions about another body."""
    spans = side_questions(text)
    if not spans:
        return text
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(text[cursor:start])
        cursor = end
    pieces.append(text[cursor:])
    return " ".join(piece.strip() for piece in pieces if piece.strip())


# Mass (kg) and mean radius (m) of each body a school question names.
BODY_PROPERTIES: dict[str, tuple[float, float]] = {
    "earth": (5.9722e24, 6.371e6),
    "moon": (7.342e22, 1.7374e6),
    "mars": (6.4171e23, 3.3895e6),
    "jupiter": (1.8982e27, 6.9911e7),
    "sun": (1.9885e30, 6.957e8),
}


def body_name(mass: float, radius: float) -> str | None:
    """The body a mass and radius belong to, as a label: "Earth"."""
    for name, (body_mass, body_radius) in BODY_PROPERTIES.items():
        if math.isclose(mass, body_mass, rel_tol=1e-6) and math.isclose(
            radius, body_radius, rel_tol=1e-6
        ):
            return name.title()
    return None


def named_body(lower: str) -> tuple[float, float] | None:
    """(mass, radius) of the first body named in lowercased text, as a whole word."""
    for name, properties in BODY_PROPERTIES.items():
        if word_index(lower, name) != -1:
            return properties
    return None


# The surface gravity (m/s²) a school question takes for a body it names.
# Jupiter and the Sun have no agreed school value (it turns on the radius
# quoted), so a solve that needs g there declines instead of using Earth's.
SCHOOL_GRAVITY: dict[str, float] = {"earth": 9.81, "moon": 1.62, "mars": 3.71}


def names_body_without_school_gravity(lower: str) -> bool:
    """True when lowercased text names a body whose surface g has no school value."""
    return any(
        word_index(lower, name) != -1 for name in BODY_PROPERTIES if name not in SCHOOL_GRAVITY
    )


# Charge magnitude (C) of each particle a question names; e is exact in SI.
PARTICLE_CHARGES: dict[str, float] = {
    "electron": ELEMENTARY_CHARGE,
    "proton": ELEMENTARY_CHARGE,
    "alpha particle": 2 * ELEMENTARY_CHARGE,
}


def named_particle_charge(lower: str) -> float | None:
    """The charge magnitude of the one particle named in lowercased text."""
    named = [charge for name, charge in PARTICLE_CHARGES.items() if word_index(lower, name) != -1]
    return named[0] if len(named) == 1 else None


# Rest mass (kg) of each particle a question names. Pint has no alpha-particle mass, so it is
# the CODATA 2022 value Pint's other masses come from.
PARTICLE_MASSES: dict[str, float] = {
    "electron": ELECTRON_MASS,
    "proton": PROTON_MASS,
    "neutron": NEUTRON_MASS,
    "alpha particle": 6.6446573450e-27,
}


def named_particle_mass(lower: str) -> float | None:
    """The rest mass of the one particle named in lowercased text."""
    named = [mass for name, mass in PARTICLE_MASSES.items() if word_index(lower, name) != -1]
    return named[0] if len(named) == 1 else None


# Water, as a school question means it when it gives no number for it.
WATER_SPECIFIC_HEAT = 4186.0  # J/(kg·K)
WATER_DENSITY = 1000.0  # kg/m³
SEA_LEVEL_PRESSURE = 101325.0  # Pa
# Another substance in the question: water's numbers may not be the ones meant.
NOT_FRESH_WATER = (
    "sea",
    "seawater",
    "saltwater",
    "brine",
    "salt",
    "ice",
    "steam",
    "oil",
    "mercury",
    "alcohol",
    "ethanol",
    "glycerin",
    "copper",
    "iron",
    "aluminium",
    "aluminum",
    "steel",
    "lead",
    "brass",
    "glass",
    "metal",
)


# An amount of something names it, listed or not: "50 g of ethanol", "200 mL of milk".
_AMOUNT_OF = re.compile(
    r"\d\s*(?:mg|g|kg|grams?|kilograms?|ml|millilit(?:re|er)s?|l|lit(?:re|er)s?|cm\^?3|cm³"
    r"|m\^?3|m³)\s+of\s+(?:(?:a|an|the|some|hot|cold|warm|cool|boiling|pure|fresh|tap"
    r"|distilled|liquid)\s+)*([a-z]+)"
)


def names_only_water(lower: str) -> bool:
    """True when the text names water and no other substance its numbers could mean."""
    return (
        word_index(lower, "water") != -1
        and all(word_index(lower, other) == -1 for other in NOT_FRESH_WATER)
        and all(noun == "water" for noun in _AMOUNT_OF.findall(lower))
    )
