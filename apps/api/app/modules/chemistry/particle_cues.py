"""Questions about particles: Avogadro-scale counts of a substance, or one atom's particles.

"1.20 x 10^24 atoms of iron", "How many atoms are in 5.0 g of Fe?" and "An atom 70X has
31 electrons. How many neutrons?" are chemistry, whatever else the line says.
"""

from __future__ import annotations

import re

from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.extractors.atom_particles import extract_atom_particles
from app.modules.chemistry.species_facts import ELEMENT_NAMES, NAMED_COMPOUNDS, is_formula

# A count of particles in powers of ten is Avogadro's scale: "1.20 x 10^24 atoms of iron".
_TIMES_TEN = r"\s*[x×*]\s*10\s*\^\s*"  # noqa: RUF001 -- a student types the multiplication sign
_PARTICLE_COUNT = re.compile(
    rf"(?<![\w.])(?:\d+(?:\.\d+)?{_TIMES_TEN}[-+]?\d{{1,3}}|\d+(?:\.\d+)?[eE][-+]?\d{{1,3}}"
    r"|10\s*\^\s*\d{1,3})\s*(?:atoms?|molecules?|formula\s+units?|ions?)\s+of\s+(?:the\s+)?"
    r"(?P<substance>[A-Za-z][A-Za-z0-9()]*)",
    re.IGNORECASE,
)
# "How many atoms are in 5.0 g of Fe?": a particle count of a stated amount.
_PARTICLES_IN_AMOUNT = re.compile(
    r"\b(?:how\s+many|number\s+of)\s+(?:atoms|molecules|formula\s+units)\s+(?:are\s+|is\s+)?"
    r"(?:there\s+)?in\s+(?:an?\s+)?\d",
    re.IGNORECASE,
)


def _particles_of_substance(text: str) -> bool:
    """Avogadro-scale particles of an element or a compound: "1.20 x 10^24 atoms of iron"."""
    for match in _PARTICLE_COUNT.finditer(text):
        word = match.group("substance")
        if word in BY_SYMBOL or word.lower() in ELEMENT_NAMES or is_formula(word):
            return True
        if any(text.lower().startswith(name, match.start("substance")) for name in _NAMED):
            return True
    return False


_NAMED = tuple(NAMED_COMPOUNDS)
# Particles of a compound written as a formula: "How many molecules are in 10 g of CO2?".
PARTICLE_WORD = re.compile(r"\b(?:atoms?|molecules?|formula\s+units?)\b", re.IGNORECASE)


def asks_about_particles(text: str) -> bool:
    """Particles of a substance or an amount, or one atom's or ion's particles."""
    return bool(
        _particles_of_substance(text)
        or _PARTICLES_IN_AMOUNT.search(text)
        or extract_atom_particles(text) is not None
    )
