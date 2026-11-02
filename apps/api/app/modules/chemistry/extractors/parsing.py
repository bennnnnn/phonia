# ruff: noqa: RUF003 -- users type × and a true minus sign.
"""Shared text helpers for the chemistry extractors: numbers, units, asked quantities."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.quantity import to_atm, to_kelvin
from app.modules.chemistry.request import CHEMICAL_FORMULA, EQUATION_RE, FORMULA_END
from app.modules.chemistry.species import counts_in_mass_action
from app.services.number_text import TEXT_NUMBER

# The extractors' short name for the shared running-text number.
_N = TEXT_NUMBER


TIME_UNIT_PATTERN = r"(?:seconds?|minutes?|hours?|days?|years?|sec|min|hr|yr|h|d|s)"
# unit word -> (label used in answers, seconds per unit)
TIME_UNITS: dict[str, tuple[str, float]] = {
    "s": ("s", 1),
    "sec": ("s", 1),
    "second": ("s", 1),
    "seconds": ("s", 1),
    "min": ("min", 60),
    "minute": ("min", 60),
    "minutes": ("min", 60),
    "h": ("h", 3600),
    "hr": ("h", 3600),
    "hour": ("h", 3600),
    "hours": ("h", 3600),
    "d": ("days", 86400),
    "day": ("days", 86400),
    "days": ("days", 86400),
    "yr": ("years", 31557600),
    "year": ("years", 31557600),
    "years": ("years", 31557600),
}
# A trailing concentration unit means k belongs to another order ("M^-1 s^-1").
_FOREIGN_RATE_UNIT = re.compile(r"\s*(?:M\b|L\b|mol\b|/)")


def rate_constant(text: str, label: str = "k") -> tuple[float, str | None] | None:
    """``k = 0.05 min^-1`` as ``(0.05, "min")``; the unit is ``None`` when none is written.

    ``k`` may also be written "the rate constant is", and ``s^-1`` as ``1/s``.
    ``None`` when the label is absent or its unit is one this reader does not understand.
    """
    # "the rate constant of a first-order reaction is 0.0450 s^-1" names whose constant it is.
    name = (
        rf"(?-i:{label})"
        if label != "k"
        else r"(?:(?-i:k)|rate\s+constant(?:\s+(?:of|for)\s+(?:the\s+|a\s+|an\s+|this\s+)?"
        r"[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*){0,3})?)"
    )
    match = re.search(
        rf"\b{name}\s*(?:=|is)\s*({_N})\s*(?:"
        rf"(?P<unit>{TIME_UNIT_PATTERN})\s*(?:\^\s*-\s*1|⁻¹)"
        rf"|(?:1\s*)?/\s*(?P<per>{TIME_UNIT_PATTERN})\b)?",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    word = match.group("unit") or match.group("per")
    if word is None:
        if _FOREIGN_RATE_UNIT.match(text[match.end() :]):
            return None
        return float(match.group(1)), None
    return float(match.group(1)), TIME_UNITS[word.lower()][0]


_TIME_TOKEN = re.compile(r"\b(?:min|minutes?|h|hr|hours?|d|days?|yr|years?)\b", re.IGNORECASE)


def k_time_unit_conflict(text: str) -> bool:
    """True when the phrase after ``k = …`` names a time unit other than seconds."""
    match = re.search(rf"\bk\s*=\s*{_N}([^,;]*)", text, re.IGNORECASE)
    return match is not None and _TIME_TOKEN.search(match.group(1)) is not None


def temperature_kelvin(text: str, label: str = "T") -> float | bool | None:
    """``T = 310 K`` or ``T = 37 °C`` in kelvin.

    ``None`` when there is no such label; ``False`` when a value is written without a
    usable unit, so the caller declines instead of assuming 25 °C or kelvin.
    """
    labelled = re.search(rf"\b(?-i:{label})\s*=\s*{_N}", text)
    if labelled is None:
        return None
    match = re.compile(
        rf"\b(?-i:{label})\s*=\s*({_N})\s*({_TEMPERATURE_UNIT})(?![A-Za-z])", re.IGNORECASE
    ).search(text)
    if match is None:
        return False
    return to_kelvin(float(match.group(1)), "celsius" if _celsius(match.group(2)) else "kelvin")


def timed(text: str, label: str) -> tuple[float, str] | None:
    """``t = 10 s`` / ``half-life 2 h`` as ``(10.0, "s")``; ``None`` without a time unit."""
    match = re.search(
        rf"{label}\s*(?:=|of|is)?\s*({_N})\s*({TIME_UNIT_PATTERN})\b", text, re.IGNORECASE
    )
    if match is None:
        return None
    return float(match.group(1)), TIME_UNITS[match.group(2).lower()][0]


def seconds_per(label: str) -> float:
    return next(scale for unit, scale in TIME_UNITS.values() if unit == label)


def _search(pattern: str, text: str, flags: int = re.IGNORECASE) -> float | None:
    match = re.search(pattern, text, flags)
    return float(match.group(1)) if match else None


def _floats(**values: float | None) -> dict[str, float] | None:
    """Return the mapping only when every value was found."""
    cleaned = {key: value for key, value in values.items() if value is not None}
    if len(cleaned) != len(values):
        return None
    return cleaned


def _equation(text: str) -> str | None:
    match = EQUATION_RE.search(text)
    return match.group(1).strip() if match else None


@dataclass(frozen=True)
class AskedQuantity:
    """What the question asks for: ``unit`` is g/mol/L/particles/atoms, ``species`` a formula.

    A unit no reader answers in (mL, kg, a cup) is kept as written, so each one declines it.
    """

    unit: str | None
    species: str | None


_UNIT_WORDS = {
    "mole": "mol",
    "moles": "mol",
    "mol": "mol",
    "amount": "mol",
    "gram": "g",
    "grams": "g",
    "mass": "g",
    "liter": "L",
    "liters": "L",
    "litre": "L",
    "litres": "L",
    "volume": "L",
    "molecules": "particles",
    "particles": "particles",
    # Atoms are not molecules: "atoms of O2" is twice the count of O2.
    "atoms": "atoms",
}
# A unit written after the substance: "How many H2O molecules", "how much H2O in liters".
_UNIT_AFTER = (
    r"(?:\s+(?:in\s+)?(?P<after>molecules|particles|atoms|moles?|mol|grams?|liters?|litres?|"
    r"milli(?:liters?|litres?)|mL|kilograms?|kg|milligrams?|mg|cups?|ounces?|oz|pounds?|lbs?)"
    r"(?![A-Za-z]))?"
)
_ASKED = re.compile(
    r"\b(?:how\s+(?:many|much)|what(?:\s+is)?(?:\s+the)?|find|calculate|determine)\s+"
    r"(?:the\s+)?"
    r"(?:(?P<unit>moles?|amount|grams?|mass|liters?|litres?|volume|molecules|particles|atoms)"
    rf"\s+(?:of\s+)?)?(?:(?P<species>{CHEMICAL_FORMULA}){FORMULA_END}{_UNIT_AFTER})?",
    re.IGNORECASE,
)


def asked_quantity(text: str) -> AskedQuantity | None:
    """Read the requested quantity from the question head, not from the given amounts.

    "How many moles of H2O from 10 grams of H2" asks for moles; the word "grams"
    belongs to the given. "How many H2O molecules" asks for particles. ``None`` when no
    question head names anything.
    """
    for match in _ASKED.finditer(text):
        unit_word = match.group("unit")
        species = match.group("species")
        if unit_word is None and species is None:
            continue
        unit = _UNIT_WORDS[unit_word.lower()] if unit_word else None
        after = match.group("after")
        if after is not None:
            written = _UNIT_WORDS.get(after.lower(), after.lower())
            if unit is not None and unit != written:
                # "how many grams of H2O molecules": two units, no one ask.
                return AskedQuantity("unread", species)
            unit = written
        return AskedQuantity(unit, species)
    return None


# What is left of a reactant is its amount minus what reacts: not a mole ratio's answer.
_LEFT_OVER = re.compile(r"\b(?:remain\w*|left(?:\s*over)?|leftover|excess|unreacted)\b", re.I)


def _target(text: str, equation: str) -> str | None:
    """The species the question asks about, or None when it asks about anything else.

    A product it asks for ("grams of CO2 produced"), or a reactant ("moles of O2 needed",
    "grams of KClO3 needed to produce 3.2 g of O2"). A reactant's leftover or excess is the
    amount minus what reacts, another question, and a species the equation lacks declines.
    """
    balanced = balance_equation(equation)
    if not balanced.balanced:
        return None
    asked = asked_quantity(text)
    if asked is not None and asked.species is not None:
        if asked.species in balanced.products:
            return asked.species
        if asked.species in balanced.reactants and not _LEFT_OVER.search(text):
            return asked.species
        return None
    outside = EQUATION_RE.sub(" ", text)
    mentioned = [
        product
        for product in balanced.products
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(product)}(?![A-Za-z0-9])", outside)
    ]
    if len(mentioned) == 1:
        return mentioned[0]
    if len(balanced.products) == 1:
        return next(iter(balanced.products))
    return None


_PRESSURE_UNIT = r"(?:kPa|Pa|mmHg|torr|atm|bar)"
_TEMPERATURE_UNIT = r"(?:°\s*C|deg\s*C|celsius|(?-i:K)|(?-i:C))"
_CANONICAL_PRESSURE = {
    "kpa": "kPa",
    "pa": "Pa",
    "mmhg": "mmHg",
    "torr": "torr",
    "atm": "atm",
    "bar": "bar",
}


def _celsius(unit: str) -> bool:
    return unit.lower().replace(" ", "") in {"c", "°c", "degc", "celsius"}


def _partial_pressures(text: str) -> tuple[dict[str, float], str] | None:
    """``P(N2) = 600 mmHg`` values with one shared unit (else all converted to atm)."""
    rows = [
        (match.group(1), float(match.group(2)), match.group(3))
        for match in re.finditer(
            rf"P\(({CHEMICAL_FORMULA})\)\s*=\s*({_N})\s*({_PRESSURE_UNIT})(?![A-Za-z])",
            text,
            re.IGNORECASE,
        )
    ]
    labelled = len(re.findall(rf"P\(({CHEMICAL_FORMULA})\)\s*=\s*{_N}", text))
    if not rows or len(rows) != labelled:
        return None
    units = {_CANONICAL_PRESSURE[unit.lower()] for _species, _value, unit in rows}
    if len(units) == 1:
        return {species: value for species, value, _unit in rows}, units.pop()
    return {species: to_atm(value, unit) for species, value, unit in rows}, "atm"


def _pressure_species(text: str, equation: str) -> dict[str, float]:
    """Partial pressures of the equation's gases in atm; empty when a unit is missing."""
    partials = _partial_pressures(text)
    if partials is None:
        return {}
    raw = {species: to_atm(value, partials[1]) for species, value in partials[0].items()}
    balanced = balance_equation(equation)
    if not balanced.balanced:
        return raw
    mapped: dict[str, float] = {}
    for species in (*balanced.reactants, *balanced.products):
        if not counts_in_mass_action(species):
            continue
        if species in raw:
            mapped[species] = raw[species]
            continue
        bare = species[: species.rfind("(")] if "(" in species else species
        if bare in raw:
            mapped[species] = raw[bare]
    return mapped


_NUCLIDE = r"(?:[A-Z][a-z]?-\d+|\d+[A-Z][a-z]?)"


def _labeled(text: str, labels: tuple[tuple[str, str], ...]) -> dict[str, float]:
    found: dict[str, float] = {}
    for key, pattern in labels:
        value = _search(pattern, text)
        if value is not None:
            found[key] = value
    return found
