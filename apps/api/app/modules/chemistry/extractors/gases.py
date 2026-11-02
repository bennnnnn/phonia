"""Gases: Dalton's law, partial pressures, a gas over water, Graham's law, Henry's law."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _CANONICAL_PRESSURE,
    _N,
    _PRESSURE_UNIT,
    _labeled,
    _partial_pressures,
    _search,
)
from app.modules.chemistry.quantity import to_atm
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.species_facts import (
    NAMED_COMPOUNDS,
    is_formula,
    without_formulas,
)
from app.modules.chemistry.stoichiometry import molar_mass

_PRESSURE = re.compile(rf"({_N})\s*({_PRESSURE_UNIT})(?![A-Za-z])", re.IGNORECASE)


_LISTED_PARTIALS = re.compile(r"\bpartial\s+pressures\b", re.IGNORECASE)


def _listed_partials(text: str) -> tuple[dict[str, float], str] | None:
    """ "The partial pressures are 0.3 atm, 0.5 atm and 0.2 atm": every pressure the question
    states is one gas's, numbered in order. A stated total would be a different question."""
    if not re.search(r"\btotal\s+pressure\b", text, re.IGNORECASE):
        return None
    rows = [(float(match.group(1)), match.group(2)) for match in _PRESSURE.finditer(text)]
    if len(rows) < 2 or re.search(rf"\btotal\s+pressure\s+(?:=|is|of)\s*{_N}", text, re.I):
        return None
    units = {_CANONICAL_PRESSURE[unit.lower()] for _value, unit in rows}
    if len(units) == 1:
        unit = units.pop()
        return {str(index): value for index, (value, _) in enumerate(rows, 1)}, unit
    return {str(index): to_atm(value, unit) for index, (value, unit) in enumerate(rows, 1)}, "atm"


def _extract_graham_rates(text: str) -> ChemistryIntent | None:
    if not re.search(r"\bGraham\b", text, re.IGNORECASE):
        return None
    found = _labeled(
        text,
        (
            ("rate1", rf"\br1\s*=\s*({_N})"),
            ("rate2", rf"\br2\s*=\s*({_N})"),
            ("molar1", rf"\bM1\s*=\s*({_N})"),
            ("molar2", rf"\bM2\s*=\s*({_N})"),
        ),
    )
    if len(found) != 3:
        return None
    return ChemistryIntent(kind="gases", chemistry_op="graham", params=found)


def _extract_gas_laws(text: str) -> ChemistryIntent | None:
    graham = _extract_graham_rates(text)
    if graham is not None:
        return graham
    # Boyle, Charles and the combined and ideal gas laws are physics' (physics/catalog/gas_laws.py),
    # answered in L and atm when the question is written in them.
    if (
        _LISTED_PARTIALS.search(text)
        and not re.search(r"\bP\(", text)
        and not _CHANGED.search(text)
    ):
        listed = _listed_partials(text)
        if listed is not None:
            return ChemistryIntent(
                kind="gases",
                chemistry_op="dalton",
                species=listed[0],
                units={"pressure": listed[1]},
            )
    total_asked = (
        _TOTAL_ASK.search(text) is not None
        and not _TOTAL_STATED.search(text)
        and not _CHANGED.search(text)
    )
    if re.search(r"\bDalton\b", text, re.IGNORECASE) or total_asked:
        partials = _partial_pressures(text) or (_gas_pressures(text) if total_asked else None)
        if partials is not None and len(partials[0]) >= 2:
            return ChemistryIntent(
                kind="gases",
                chemistry_op="dalton",
                species=partials[0],
                units={"pressure": partials[1]},
            )
        if re.search(r"\bDalton\b", text, re.IGNORECASE):
            return None
    if re.search(r"\bpartial pressure\b", text, re.IGNORECASE) and not _CHANGED.search(text):
        partial = _partial_from_fraction(text) or _partial_from_moles(text)
        if partial is not None:
            return partial
    if re.search(r"\bover water\b", text, re.IGNORECASE):
        wet = _search(rf"total pressure\s*=\s*({_N})\s*(mmHg|atm|torr|kPa|bar)", text)
        unit = re.search(r"total pressure\s*=\s*" + _N + r"\s*(mmHg|atm|torr|kPa|bar)", text)
        temperature = _search(rf"({_N})\s*(?:°\s*)?C\b", text)
        if wet is not None and temperature is not None and unit is not None:
            return ChemistryIntent(
                kind="gases",
                chemistry_op="gas_over_water",
                params={"total_pressure": wet, "temperature_c": temperature},
                units={"pressure": unit.group(1)},
            )
        return _collected_over_water(text)
    return None


# "collected over water at 25 °C and 755 mmHg total pressure. What is the pressure of the dry
# gas?": the one pressure is the total, the one temperature the water's, the dry gas asked.
_DRY_ASK = re.compile(
    r"\bdry\b|\b(?:partial\s+)?pressure\s+of\s+(?:the\s+)?(?:collected\s+)?"
    r"(?:gas|hydrogen|oxygen|nitrogen|(?-i:[A-Z][A-Za-z0-9]*))\b",
    re.IGNORECASE,
)
_CELSIUS = re.compile(rf"({_N})\s*(?:°\s*C|deg\s*C|degrees?\s+C(?:elsius)?)(?![A-Za-z])", re.I)


# The one pressure must be the total: a stated dry pressure, or a total asked, is the reverse
# question.
_DRY_STATED = re.compile(rf"\bdry\b[^.?!\d]{{0,40}}{_N}\s*{_PRESSURE_UNIT}", re.IGNORECASE)
_TOTAL_ASKED = re.compile(
    r"\b(?:what|find|calculate|determine)\b[^.?!]*\btotal\s+pressure\b", re.IGNORECASE
)


def _collected_over_water(text: str) -> ChemistryIntent | None:
    pressures = _PRESSURE.findall(text)
    temperatures = _CELSIUS.findall(text)
    if len(pressures) != 1 or len(temperatures) != 1 or not _DRY_ASK.search(text):
        return None
    if _DRY_STATED.search(text) or _TOTAL_ASKED.search(text):
        return None
    if re.search(r"\bvapou?r\s+pressure\b", text, re.IGNORECASE):
        # A stated vapor pressure would be a second value this reading ignores.
        return None
    value, unit = pressures[0]
    return ChemistryIntent(
        kind="gases",
        chemistry_op="gas_over_water",
        params={"total_pressure": float(value), "temperature_c": float(temperatures[0])},
        units={"pressure": _CANONICAL_PRESSURE[unit.lower()]},
    )


# Gases a Graham question names in words, as the molecules that effuse.
_GAS_NAMES: dict[str, str] = {
    "hydrogen": "H2",
    "oxygen": "O2",
    "nitrogen": "N2",
    "chlorine": "Cl2",
    "fluorine": "F2",
    "helium": "He",
    "neon": "Ne",
    "argon": "Ar",
    "krypton": "Kr",
    "xenon": "Xe",
    "radon": "Rn",
}


_NOBLE = frozenset({"He", "Ne", "Ar", "Kr", "Xe", "Rn"})


_EFFUSION = re.compile(r"\b(?:effus\w*|diffus\w*|graham'?s?\s+law)\b", re.IGNORECASE)


_RATE_ASK = re.compile(
    r"\b(?:rates?|faster|slower|how\s+many\s+times|compare|comparison|ratio)\b", re.IGNORECASE
)


# A rate "slower" than another is the other's ratio to it; a time ratio is not a rate ratio.
_SLOWER = re.compile(r"\bslower\b", re.IGNORECASE)


_FASTER = re.compile(r"\bfaster\b", re.IGNORECASE)


_TIME_ASK = re.compile(r"\b(?:longer|time|takes?|took|how\s+long)\b", re.IGNORECASE)


_GAS_WORDS = "|".join(sorted((*_GAS_NAMES, *NAMED_COMPOUNDS), key=len, reverse=True))


_GAS_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?P<formula>(?-i:[A-Z][A-Za-z0-9()]*))(?![A-Za-z0-9(])"
    rf"|\b(?P<name>{_GAS_WORDS})\b",
    re.IGNORECASE,
)


def _gases(text: str) -> list[str]:
    """The gases a question names, as formulas, in the order it names them."""
    gases: list[str] = []
    for match in _GAS_TOKEN.finditer(text):
        token = match.group("formula")
        if token is not None:
            gas = token if is_formula(token) or token in _NOBLE else None
        else:
            name = match.group("name").lower()
            gas = _GAS_NAMES.get(name) or NAMED_COMPOUNDS.get(name)
        if gas is not None and gas not in gases:
            gases.append(gas)
    return gases


def _states_a_number(text: str) -> bool:
    """A digit outside the formulas: a rate, a time or a mass the reader does not take."""
    return re.search(r"\d", without_formulas(text)) is not None


# A mixture whose volume, temperature or contents change is another state: its pressures are
# not the ones stated.
_CHANGED = re.compile(
    r"\b(?:doubl\w*|halv\w*|tripl\w*|compress\w*|expand\w*|heat\w*|cool\w*|add\w*|"
    r"remov\w*|transfer\w*|connect\w*|pump\w*|leak\w*|after|then|volume|temperature)\b",
    re.IGNORECASE,
)
# "what's the total pressure?" asks the sum; "at a total pressure of 4.0 atm" states it.
_TOTAL_ASK = re.compile(
    r"\b(?:find|calculate|determine|what(?:'s|\s+is)?)\s+(?:is\s+)?(?:the\s+)?total\s+pressure\b"
    r"|\btotal\s+pressure\s*\??\s*$",
    re.IGNORECASE,
)
_TOTAL_STATED = re.compile(
    rf"\btotal\s+pressure\s+(?:=|is|of|was)\s*{_N}|\b(?:at|under)\s+(?:a\s+)?total\s+pressure\b",
    re.IGNORECASE,
)


def _gas_word(token: str) -> str | None:
    """A gas named by its formula ("O2", "He") or by its name ("helium", "carbon dioxide")."""
    if is_formula(token) or token in _NOBLE:
        return token
    name = token.lower()
    return _GAS_NAMES.get(name) or NAMED_COMPOUNDS.get(name)


# "He at 0.40 atm", "neon: 0.25 atm", "argon = 0.15 atm": each gas beside its own pressure.
_GAS_AT_PRESSURE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<gas>(?-i:[A-Z][A-Za-z0-9()]*)|\b(?:{_GAS_WORDS})\b)\s*"
    rf"(?:at|=|:|of|is|with)\s*(?P<value>{_N})\s*(?P<unit>{_PRESSURE_UNIT})(?![A-Za-z])",
    re.IGNORECASE,
)


def _gas_pressures(text: str) -> tuple[dict[str, float], str] | None:
    """Each named gas's pressure, when every pressure the question states is one gas's."""
    rows: list[tuple[str, float, str]] = []
    for match in _GAS_AT_PRESSURE.finditer(text):
        gas = _gas_word(match.group("gas"))
        if gas is None or any(gas == row[0] for row in rows):
            return None
        rows.append((gas, float(match.group("value")), match.group("unit")))
    if len(rows) < 2 or len(rows) != len(_PRESSURE.findall(text)):
        return None
    units = {_CANONICAL_PRESSURE[unit.lower()] for _gas, _value, unit in rows}
    if len(units) == 1:
        return {gas: value for gas, value, _unit in rows}, units.pop()
    return {gas: to_atm(value, unit) for gas, value, unit in rows}, "atm"


_STATED_TOTAL = re.compile(
    rf"total\s+pressure\s*(?:=|is|of|was)\s*({_N})\s*({_PRESSURE_UNIT})(?![A-Za-z])",
    re.IGNORECASE,
)


def _partial_from_fraction(text: str) -> ChemistryIntent | None:
    """Pi = Xi Ptotal from a stated mole fraction: "its mole fraction is 0.25"."""
    fraction = _search(rf"mole fraction\s*(?:=|is|of)\s*({_N})", text)
    total = _STATED_TOTAL.search(text)
    if fraction is None or total is None or len(re.findall(_N, without_formulas(text))) != 2:
        return None
    return ChemistryIntent(
        kind="gases",
        chemistry_op="partial_pressure",
        params={"mole_fraction": fraction, "total_pressure": float(total.group(1))},
        units={"pressure": _CANONICAL_PRESSURE[total.group(2).lower()]},
    )


_MOLES_OF_GAS = re.compile(
    rf"(?P<moles>{_N})\s*mol(?:es?)?\s+(?:of\s+)?(?P<gas>(?-i:[A-Z][A-Za-z0-9()]*))(?![A-Za-z0-9(])"
)
_PARTIAL_OF = re.compile(
    r"\bpartial\s+pressure\s+of\s+(?:the\s+)?(?P<gas>(?-i:[A-Z][A-Za-z0-9()]*))(?![A-Za-z0-9(])",
    re.IGNORECASE,
)


def _partial_from_moles(text: str) -> ChemistryIntent | None:
    """Pi = (ni / Σn) Ptotal: "2.0 mol O2 and 6.0 mol N2 at a total pressure of 4.0 atm".

    Every gas of the mixture is stated in moles, and the asked gas is one of them.
    """
    asked = _PARTIAL_OF.search(text)
    total = re.search(
        rf"total\s+pressure\s*(?:=|is|of|was)?\s*({_N})\s*({_PRESSURE_UNIT})(?![A-Za-z])",
        text,
        re.IGNORECASE,
    )
    if asked is None or total is None:
        return None
    amounts: dict[str, float] = {}
    for match in _MOLES_OF_GAS.finditer(text):
        gas = _gas_word(match.group("gas"))
        if gas is None or gas in amounts:
            return None
        amounts[gas] = float(match.group("moles"))
    target = _gas_word(asked.group("gas"))
    if len(amounts) < 2 or target not in amounts:
        return None
    if len(re.findall(_N, without_formulas(text))) != len(amounts) + 1:
        return None
    return ChemistryIntent(
        kind="gases",
        chemistry_op="partial_pressure",
        species=amounts,
        target=target,
        params={"total_pressure": float(total.group(1))},
        units={"pressure": _CANONICAL_PRESSURE[total.group(2).lower()]},
    )


def _extract_graham(text: str) -> ChemistryIntent | None:
    """ "Compare the rates of effusion of H2 and O2": rate(H2) / rate(O2) = √(M(O2) / M(H2)).

    "How many times slower does O2 effuse than H2?" asks rate(H2) / rate(O2), so a "slower"
    question swaps the gases. A time asked, or both directions asked, declines.
    """
    if not _EFFUSION.search(text) or not _RATE_ASK.search(text) or _states_a_number(text):
        return None
    slower = _SLOWER.search(text) is not None
    if _TIME_ASK.search(text) or (slower and _FASTER.search(text)):
        return None
    gases = _gases(text)
    if len(gases) != 2:
        return None
    first, second = reversed(gases) if slower else gases
    return ChemistryIntent(
        kind="gases",
        chemistry_op="graham_ratio",
        formula=first,
        target=second,
        params={"molar_mass_a": molar_mass(first), "molar_mass_b": molar_mass(second)},
    )


def _extract_henry(text: str) -> ChemistryIntent | None:
    if not re.search(r"\bHenry'?s?\s+law\b", text, re.IGNORECASE):
        return None
    found = _labeled(
        text,
        (
            ("concentration", rf"\bC\s*=\s*({_N})"),
            ("henry_constant", rf"\bkH\s*=\s*({_N})"),
            ("pressure", rf"\bP\s*=\s*({_N})"),
        ),
    )
    if len(found) != 2:
        return None
    return ChemistryIntent(kind="solutions", chemistry_op="henry", params=found)
