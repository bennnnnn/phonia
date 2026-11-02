"""A law's name over its formulas: **Constant acceleration formula**, not **Formula**.

The catalog names a law the way a textbook index does ("Kinetic-energy formula",
"SUVAT constant-acceleration equation"). Over the formula itself, "formula" or
"equation" says nothing the rows below do not, so the heading keeps what the law
is about: "Kinetic energy", "Constant acceleration". A law named for itself
("Snell's law", "Continuity equation", "Stefan-Boltzmann law") keeps its name. The
heading over the formulas is that title through the one rule every subject heads a
formula with (``services.workout.formula_heading``): "Kinetic energy formula".
"""

from __future__ import annotations

import re

from app.services.workout import formula_heading

# Where the rule below reads wrong: a pair of quantities is not one compound noun
# ("Frequency-period relation" is frequency and period, not a frequency period).
_TITLES: dict[str, str] = {
    "SUVAT constant-acceleration equation": "Constant acceleration",
    "Rydberg formula": "Rydberg formula",
    "Vis-viva equation": "Vis-viva equation",
    "Lens-maker equation": "Lensmaker's equation",
    "Charge-current relation": "Charge and current",
    "Frequency-period relation": "Frequency and period",
    "Energy-momentum relation": "Energy-momentum relation",
    "Adiabatic temperature-volume relation": "Adiabatic temperature and volume",
}

# "Projectile-motion equation": an equation named by a compound noun, read as that noun.
_DESCRIBED = re.compile(r"^(?P<what>.*\b[A-Za-z]+(?:-[a-z]+)+) (?:equation|relation)$")
# The hyphen of a compound noun ("kinetic-energy"), not of two names ("Stefan-Boltzmann").
_COMPOUND_HYPHEN = re.compile(r"(?<=[a-z])-(?=[a-z])")


def law_title(law_name: str) -> str:
    """The heading for a catalog law: ``Kinetic-energy formula`` → ``Kinetic energy``."""
    name = law_name.strip()
    if name in _TITLES:
        return _TITLES[name]
    described = _DESCRIBED.match(name)
    if name.endswith(" formula"):
        name = name.removesuffix(" formula")
    elif described:
        name = described.group("what")
    else:
        return name
    return _COMPOUND_HYPHEN.sub(" ", name)


def law_heading(law_name: str) -> str:
    """The heading over a catalog law's formulas: ``Kinetic-energy formula`` →
    ``Kinetic energy formula``; ``SUVAT constant-acceleration equation`` →
    ``Constant acceleration formula``; ``Snell's law`` stays."""
    return formula_heading(law_title(law_name))
