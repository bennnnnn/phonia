"""Modern physics: each law's reader is tried in a fixed order; a named law
answers or declines, and only then does E = mc² apply."""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.modern_laws import (
    _half_life,
    _mass_energy,
    _relativity,
    _stefan_boltzmann,
    _wien,
)
from app.modules.physics.extractors.quantum import (
    _compton,
    _de_broglie,
    _hydrogen_level,
    _particle_in_box,
    _photoelectric,
    _photon_energy,
    _uncertainty,
)
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_MODERN_CUES = (
    "photon",
    "de broglie",
    "planck",
    "photoelectric",
    "rest energy",
    "mass energy",
    "energy equivalent",
    "lorentz factor",
    "time dilation",
    "length contraction",
    "special relativity",
    "uncertainty principle",
    "momentum uncertainty",
    "particle in a box",
    "infinite box",
    "hydrogen energy",
    "hydrogen atom",
    "compton",
    "wien's law",
    "wien law",
    "stefan",
    "blackbody power",
)

_DECAY_SUBJECT = r"sample|isotope|radioactive|radioisotope|decay|nuclei|nuclide|substance"

_MODERN_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\bhalf[- ]li(?:ves|fe)\b.{{0,80}}?\b(?:{_DECAY_SUBJECT})\b", re.IGNORECASE),
    re.compile(rf"\b(?:{_DECAY_SUBJECT})\b.{{0,80}}?\bhalf[- ]li(?:ves|fe)\b", re.IGNORECASE),
)


# Each law with the words that name it, in the order they are tried.
_MODERN_LAWS: tuple[tuple[Callable[[str], bool], Callable[[str], PhysicsIntent | None]], ...] = (
    (
        lambda lower: any(
            cue in lower for cue in ("lorentz factor", "time dilation", "length contraction")
        ),
        _relativity,
    ),
    (lambda lower: "uncertainty" in lower, _uncertainty),
    (lambda lower: "particle in a box" in lower or "infinite box" in lower, _particle_in_box),
    (lambda lower: "hydrogen" in lower and "energy" in lower, _hydrogen_level),
    (lambda lower: "compton" in lower, _compton),
    (lambda lower: "wien" in lower, _wien),
    (lambda lower: "stefan" in lower or "blackbody power" in lower, _stefan_boltzmann),
    (lambda lower: "photoelectric" in lower, _photoelectric),
    (
        lambda lower: ("photon" in lower or "planck" in lower) and "momentum" not in lower,
        _photon_energy,
    ),
    (lambda lower: "de broglie" in lower, _de_broglie),
    (lambda lower: "half li" in lower or "half-li" in lower, _half_life),
)


def _extract_modern_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _MODERN_CUES, _MODERN_CUE_RES):
        return None
    without_level_assignment = re.sub(r"\bn\s*=\s*\d+\b", "", cleaned, flags=re.IGNORECASE)
    if has_equation(strip_param_assignments(without_level_assignment)):
        return None
    for names, law in _MODERN_LAWS:
        if names(lower):
            return law(cleaned)
    return _mass_energy(cleaned)
