"""Closed school templates that used to be declined as advanced physics.

These are not general circuit, field, or gas solvers. Each one accepts one
stated shape and returns nothing when a condition it would have to invent
is missing.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.physics.extractors.school_ac import extract_ac
from app.modules.physics.extractors.school_circuits import (
    extract_inductor,
    extract_junction,
    extract_loop,
    extract_rl,
)
from app.modules.physics.extractors.school_fields import extract_faraday, extract_gauss
from app.modules.physics.extractors.school_matter import (
    extract_gravitation,
    extract_poiseuille,
    extract_thermal,
)
from app.modules.physics.schemas import PhysicsIntent

_EXTENSION_CUES = (
    "kirchhoff",
    "junction",
    "node",
    "loop",
    "gauss",
    "faraday",
    "induced emf",
    "flux changes",
    "inductor",
    "inductive",
    "henry",
    "henries",
    "impedance",
    "reactance",
    "rl circuit",
    "resonant",
    "resonance",
    "average power",
    "poiseuille",
    "gravitational potential",
    "orbital energy",
    "kepler",
    "monatomic",
    "adiabatic",
    "isobaric",
    "coefficient of performance",
    "heat pump",
    "refrigerator",
    "ideal gas",
)
# "rms" as a word: as a substring it is the end of "terms", "arms" and "forms",
# and "the first 5 terms of a series" went to physics.
_EXTENSION_CUE_RES = (re.compile(r"\brms\b", re.IGNORECASE),)

_CIRCUIT_BLOCK = re.compile(
    r"\b(?:kirchhoff(?:'s)?|junction rule|loop rule|inductors?|henrys?|henries|"
    r"impedance|reactance|\brms\b|rl circuits?)\b",
    re.IGNORECASE,
)
_FIELD_BLOCK = re.compile(
    r"\b(?:faraday(?:'s)?(?:\s+law)?|induced emf|flux changes|gauss(?:'s)?(?:\s+law)?)\b",
    re.IGNORECASE,
)
_THERMAL_BLOCK = re.compile(
    r"\b(?:monatomic|adiabatic|isobaric|refrigerators?|heat pumps?|"
    r"coefficient of performance)\b",
    re.IGNORECASE,
)

_EXTRACTORS: tuple[Callable[[str, str], PhysicsIntent | None], ...] = (
    extract_junction,
    extract_loop,
    extract_gauss,
    extract_faraday,
    extract_inductor,
    extract_rl,
    extract_ac,
    extract_poiseuille,
    extract_gravitation,
    extract_thermal,
)


def blocks_circuit(text: str) -> bool:
    return _CIRCUIT_BLOCK.search(text) is not None


def blocks_field(text: str) -> bool:
    return _FIELD_BLOCK.search(text) is not None


def blocks_fluids(text: str) -> bool:
    return re.search(r"\bpoiseuille\b", text, re.IGNORECASE) is not None


def blocks_thermal(text: str) -> bool:
    return _THERMAL_BLOCK.search(text) is not None


def extract_school_extension(cleaned: str) -> PhysicsIntent | None:
    """One complete school template, or nothing."""
    lower = cleaned.lower()
    if not any(cue in lower for cue in _EXTENSION_CUES) and not any(
        rx.search(lower) for rx in _EXTENSION_CUE_RES
    ):
        return None
    for extractor in _EXTRACTORS:
        intent = extractor(cleaned, lower)
        if intent is not None:
            return intent
    return None
