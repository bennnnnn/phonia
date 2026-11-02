"""Every number a physics question states, with its unit and dimension.

The scan is shared (``services.law_binding.givens``); physics brings its unit table
(``given_units``) and one unit no table can list: a speed written as a fraction of c.
"""

from __future__ import annotations

import re

from app.modules.physics.given_units import _LOWERCASE, _SYMBOLS, _WORDS
from app.services.law_binding.givens import Given
from app.services.law_binding.givens import scan_givens as _scan_givens
from app.services.law_binding.units import ANGLE, UnitTable, unit_dimension

__all__ = [
    "ANGLE",
    "FRACTION_OF_C",
    "PHYSICS_UNITS",
    "Given",
    "scan_givens",
    "unit_at",
    "unit_dimension",
    "unit_expression",
    "unit_readings",
]

# A speed written as a fraction of c. Written onto the number ("0.8c"), any
# number is one. With a space, only a decimal below 1 is ("0.8 c"): "question
# 2 c" and "part c)" label a part of the question, not a speed.
FRACTION_OF_C = re.compile(r"\dc(?![A-Za-z0-9])|(?<![\d.])0?\.\d+[ \t]c(?![A-Za-z0-9)])")
_LIGHT_SPEED_RE = re.compile(r"c(?![A-Za-z0-9])")
_SPACED_LIGHT_SPEED_RE = re.compile(r"[ \t]c(?![A-Za-z0-9)])")
_FRACTION_BEFORE_RE = re.compile(r"(?<![\d.])0?\.\d+\Z")


def _speed_of_light_at(text: str, end: int) -> bool:
    if _LIGHT_SPEED_RE.match(text, end):
        return True
    if not _SPACED_LIGHT_SPEED_RE.match(text, end):
        return False
    # A number is short; the window keeps this check constant-time.
    return _FRACTION_BEFORE_RE.search(text[max(0, end - 32) : end]) is not None


# "0.003 u of mass is lost": an atomic mass unit, written apart from its
# number and followed by "of" or the end of a sentence. Written onto the
# number ("2u") or inside an equation ("u + at") it is a velocity.
_ATOMIC_MASS_UNIT_RE = re.compile(r"[ \t]u(?=[ \t]+of\b|[ \t]*[.,;?!]|[ \t]*\Z)")


def _special_unit(text: str, end: int) -> tuple[str, str] | None:
    if _speed_of_light_at(text, end):
        return ("c", "speed_of_light")
    if _ATOMIC_MASS_UNIT_RE.match(text, end):
        return ("u", "dalton")
    return None


PHYSICS_UNITS = UnitTable(
    _SYMBOLS, _WORDS, special=_special_unit, exact={"c": "speed_of_light", "u": "dalton"}
)


def unit_expression(spelling: str) -> str | None:
    """The Pint expression of one spelling from the physics unit table."""
    return PHYSICS_UNITS.expression(spelling)


def unit_readings(unit: str) -> tuple[str, ...]:
    """The Pint expressions a unit an extractor wrote may mean, the table's first.

    The table reads the unit as written; the same spelling in lowercase is the
    second reading, for an extractor that matched without case; the spelling
    itself is the last, for Pint.
    """
    lower = unit.lower()
    readings = (
        PHYSICS_UNITS.expression(unit),
        PHYSICS_UNITS.symbols.get(lower) or PHYSICS_UNITS.words.get(lower) or _LOWERCASE.get(lower),
        unit,
    )
    return tuple(dict.fromkeys(reading for reading in readings if reading))


def unit_at(text: str, end: int) -> tuple[str, str] | None:
    """The unit written right after a number: (spelling, Pint expression)."""
    return PHYSICS_UNITS.at(text, end)


def scan_givens(text: str) -> list[Given]:
    """Every stated number in normalized physics input, in written order."""
    return _scan_givens(text, PHYSICS_UNITS)
