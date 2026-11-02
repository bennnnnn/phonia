"""Electrochemistry: ΔG from E°, the Nernst equation, electrolysis, and galvanic cells."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    _search,
    seconds_per,
    temperature_kelvin,
    timed,
)
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import STANDARD_REDUCTION, STANDARD_TEMPERATURE_K
from app.modules.chemistry.species_facts import named_elements
from app.services.units import CELSIUS_OFFSET_K


def _extract_electrochem(text: str) -> ChemistryIntent | None:
    if re.search(r"\bNernst\b", text, re.IGNORECASE):
        standard = _search(rf"E(?:°|0)\s*=\s*({_N})\s*V", text)
        electrons = _search(rf"\bn\s*=\s*({_N})", text)
        quotient = _search(rf"\bQ\s*=\s*({_N})", text, flags=0)
        temperature = temperature_kelvin(text)
        if temperature is False:
            return None  # a stated temperature without a usable unit is never replaced by 25 °C
        if temperature is None:
            temperature = STANDARD_TEMPERATURE_K
        if standard is not None and electrons is not None and quotient is not None:
            return ChemistryIntent(
                kind="electrochemistry",
                chemistry_op="nernst",
                params={
                    "standard_potential": standard,
                    "electrons": electrons,
                    "quotient": quotient,
                    "temperature": temperature,
                },
            )
    # A degree sign is not a word character, so E° must not demand a trailing boundary.
    if re.search(r"\b(?:ΔG|Gibbs)\b", text, re.IGNORECASE) and re.search(
        r"\b(?:cell|electrochem)\b|\bE°", text, re.IGNORECASE
    ):
        electrons = _search(rf"\bn\s*=\s*({_N})", text)
        potential = _search(rf"E(?:cell)?(?:°|0)?\s*=\s*({_N})\s*V", text)
        if electrons is not None and potential is not None:
            return ChemistryIntent(
                kind="electrochemistry",
                chemistry_op="cell_gibbs",
                params={"electrons": electrons, "potential": potential},
            )
    if re.search(r"\b(?:electrolysis|deposited|Faraday's law)\b", text, re.IGNORECASE):
        molar = _search(rf"(?:molar mass|\bM)\s*=\s*({_N})\s*g/mol", text)
        current = _search(
            rf"(?:current|\bI)\s*(?:=|of)?\s*({_N})\s*(?:(?-i:A)(?![A-Za-z])|amps?\b)", text
        )
        elapsed = timed(text, r"(?:time|\bt)")
        time = None if elapsed is None else elapsed[0] * seconds_per(elapsed[1])
        electrons = _search(rf"\bn\s*=\s*({_N})", text)
        if molar is not None and current is not None and time is not None and electrons is not None:
            return ChemistryIntent(
                kind="electrochemistry",
                chemistry_op="electrolysis_mass",
                params={
                    "molar_mass": molar,
                    "current": current,
                    "time": time,
                    "electrons": electrons,
                },
            )
    return None


# Other metals match as tokens. Potassium is added only after a trailing "298 K"
# is removed, so kelvin is not a second electrode.
_METALS = tuple(symbol for symbol in STANDARD_REDUCTION if symbol != "K")


_KELVIN_UNIT = re.compile(r"\d\s*K\b")


# "Ag+/Ag (0.80 V)", "E°(Cu2+/Cu) = 0.34 V": a couple and its reduction potential.
_COUPLE = re.compile(
    r"(?<![A-Za-z0-9])(?P<ion>[A-Z][a-z]?)(?P<charge>\d?)\+\s*/\s*(?P<metal>[A-Z][a-z]?)"
    rf"(?![A-Za-z0-9])\s*\)?\s*(?:\(|=|:|,|is)?\s*(?P<volts>{_N})\s*V\b"
)
_VOLTS = re.compile(rf"(?<![A-Za-z0-9.]){_N}\s*V\b")
_CELL_ASK = re.compile(
    r"E\s*[°º]?\s*cell|\bcell\s+(?:potential|voltage)|\bemf\b|\bvoltage\b", re.IGNORECASE
)
_ELECTROLYTIC = re.compile(r"\belectroly", re.IGNORECASE)


def _stated_couples(text: str) -> ChemistryIntent | None:
    """E°cell from two stated reduction potentials: the higher one is the galvanic cathode."""
    if not _CELL_ASK.search(text) or _ELECTROLYTIC.search(text):
        return None
    couples = [
        float(match.group("volts"))
        for match in _COUPLE.finditer(text)
        if match.group("ion") == match.group("metal")
    ]
    if len(couples) != 2 or len(_VOLTS.findall(text)) != 2 or couples[0] == couples[1]:
        return None
    return ChemistryIntent(
        kind="electrochemistry",
        chemistry_op="cell_potential",
        params={"cathode": max(couples), "anode": min(couples)},
    )


# "[Zn2+] = 1.0 M": an ion's concentration.
_ION_CONCENTRATION = re.compile(
    rf"\[(?P<metal>[A-Z][a-z]?)(?P<charge>\d?)\+\]\s*=\s*(?P<value>{_N})\s*(?:M|mol/L)(?![A-Za-z])"
)


def _cell_metals(text: str) -> list[str]:
    without_kelvin = _KELVIN_UNIT.sub(" ", text)
    found = re.findall(r"\b(" + "|".join(_METALS) + r")\b", without_kelvin)
    found += [symbol for symbol in named_elements(text) if symbol in STANDARD_REDUCTION]
    unique: list[str] = []
    for symbol in found:
        if symbol not in unique and symbol != "H":
            unique.append(symbol)
    return unique


def _cell_at_concentrations(text: str) -> ChemistryIntent | None:
    """The Nernst potential of a cell of two table metals at stated ion concentrations.

    "Find the cell potential of a Zn/Cu cell with [Zn2+] = 1.0 M and [Cu2+] = 0.010 M at
    25 °C": E° from the reduction table, Q from the ions. Each ion must be the table's ion of
    its metal (Cu2+, not Cu+), and both must be stated.
    """
    if not _CELL_ASK.search(text) or _ELECTROLYTIC.search(text):
        return None
    ions: dict[str, float] = {}
    for match in _ION_CONCENTRATION.finditer(text):
        metal = match.group("metal")
        charge = int(match.group("charge") or 1)
        if metal not in STANDARD_REDUCTION or STANDARD_REDUCTION[metal][1] != charge:
            return None
        label = f"{metal}{charge if charge > 1 else ''}+"
        if label in ions:
            return None
        ions[label] = float(match.group("value"))
    metals = _cell_metals(text)
    if len(metals) != 2 or len(ions) != 2:
        return None
    if {label.rstrip("+").rstrip("0123456789") for label in ions} != set(metals):
        return None
    temperature = temperature_kelvin(text)
    if temperature is None:
        celsius = re.search(rf"\bat\s+({_N})\s*°\s*C\b", text)
        temperature = STANDARD_TEMPERATURE_K
        if celsius is not None:
            temperature = float(celsius.group(1)) + CELSIUS_OFFSET_K
    if temperature is False:
        return None
    return ChemistryIntent(
        kind="electrochemistry",
        chemistry_op="galvanic_nernst",
        formula=metals[0],
        target=metals[1],
        species=ions,
        params={"temperature": float(temperature)},
    )


def _extract_cells(text: str) -> ChemistryIntent | None:
    stated = _stated_couples(text) or _cell_at_concentrations(text)
    if stated is not None:
        return stated
    if re.search(r"\bcell potential\b", text, re.IGNORECASE):
        cathode = _search(rf"\bcathode\s*=\s*({_N})", text)
        anode = _search(rf"\banode\s*=\s*({_N})", text)
        if cathode is not None and anode is not None:
            return ChemistryIntent(
                kind="electrochemistry",
                chemistry_op="cell_potential",
                params={"cathode": cathode, "anode": anode},
            )
    if re.search(r"\bgalvanic cell\b", text, re.IGNORECASE):
        without_kelvin = _KELVIN_UNIT.sub(" ", text)
        found = re.findall(r"\b(" + "|".join(_METALS) + r"|K)\b", without_kelvin)
        # "a zinc-copper galvanic cell" names its metals in words.
        found += [symbol for symbol in named_elements(text) if symbol in STANDARD_REDUCTION]
        unique: list[str] = []
        for symbol in found:
            if symbol not in unique:
                unique.append(symbol)
        if len(unique) == 2:
            return ChemistryIntent(
                kind="electrochemistry",
                chemistry_op="galvanic_cell",
                formula=unique[0],
                target=unique[1],
            )
    return None
