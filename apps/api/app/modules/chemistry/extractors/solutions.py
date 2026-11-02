"""Solutions: molarity, dilution, molality, mass percent, and colligative properties."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    _floats,
    _search,
)
from app.modules.chemistry.request import CHEMICAL_FORMULA, FORMULA_END
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.species_facts import (
    NAMED_COMPOUNDS,
    is_formula,
    named_species,
    without_formulas,
)
from app.modules.chemistry.stoichiometry import molar_mass


def _labeled_volume(text: str, label: str) -> tuple[float, str | None] | None:
    match = re.search(
        rf"\b{label}\s*=\s*({_N})(?:\s*(mL|L)\b)?",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    matched_unit = match.group(2)
    unit = None if matched_unit is None else ("mL" if matched_unit.lower() == "ml" else "L")
    return float(match.group(1)), unit


# "What volume of 6 M HCl is needed to make 500 mL of 1.5 M HCl?": the stock volume V1.
_MOLAR_VALUE = r"\s*(?-i:M)(?![A-Za-z])"


_STOCK_VOLUME = re.compile(
    r"\b(?:what\s+volume|how\s+(?:many|much)\s+(?P<asked>mL|L|milliliters?|millilitres?|"
    r"liters?|litres?))\s+of\s+(?:(?:the|a|an)\s+)?(?:stock\s+)?"
    rf"(?P<m1>{_N}){_MOLAR_VALUE}[^.?]{{0,80}}?\b(?:make|prepare|produce|obtain)\s+(?:an?\s+)?"
    rf"(?P<v2>{_N})\s*(?P<v2_unit>mL|L)\s+of\s+(?:an?\s+)?(?P<m2>{_N}){_MOLAR_VALUE}",
    re.IGNORECASE,
)


# "I have 12 M HCl stock. How many mL do I need to make 500 mL of 1.5 M HCl?": the stock named
# in a sentence of its own, the volume asked, and the solution to make.
_STOCK_STATED = re.compile(
    rf"(?P<m1>{_N}){_MOLAR_VALUE}(?:\s+[A-Za-z][A-Za-z0-9()]*)?\s+stock\b", re.IGNORECASE
)
_VOLUME_ASK = re.compile(
    r"\b(?:how\s+(?:many|much)\s+(?P<asked>mL|L|milliliters?|millilitres?|liters?|litres?)\b|"
    r"what\s+volume\b)",
    re.IGNORECASE,
)
_MAKE_SOLUTION = re.compile(
    rf"\b(?:make|prepare)\s+(?:an?\s+)?(?P<v2>{_N})\s*(?P<v2_unit>mL|L)\s+of\s+(?:an?\s+)?"
    rf"(?P<m2>{_N}){_MOLAR_VALUE}",
    re.IGNORECASE,
)
_ADDED = re.compile(r"\badd(?:s|ed|ing)?\b", re.IGNORECASE)


def _stated_stock_volume(text: str) -> ChemistryIntent | None:
    """V1 = M2V2 / M1 when the stock is stated apart from the question that asks its volume.

    The stock, the solution to make and the volume asked are each read once, every number of
    the text is one of the three, and one substance at most is named. Water to add is not
    the stock's volume.
    """
    stocks = list(_STOCK_STATED.finditer(text))
    makes = list(_MAKE_SOLUTION.finditer(text))
    ask = _VOLUME_ASK.search(text)
    if len(stocks) != 1 or len(makes) != 1 or ask is None or _ADDED.search(text):
        return None
    if len(named_species(text)) > 1 or len(re.findall(_N, without_formulas(text))) != 3:
        return None
    stock, make = stocks[0], makes[0]
    asked = (ask.group("asked") or make.group("v2_unit")).lower()
    v2_unit = "mL" if make.group("v2_unit").lower() == "ml" else "L"
    return ChemistryIntent(
        kind="solutions",
        chemistry_op="dilution",
        params={
            "m1": float(stock.group("m1")),
            "m2": float(make.group("m2")),
            "v2": float(make.group("v2")),
        },
        units={"v1": "mL" if asked.startswith(("ml", "milli")) else "L", "v2": v2_unit},
    )


def _stock_volume(text: str) -> ChemistryIntent | None:
    match = _STOCK_VOLUME.search(text)
    if match is None:
        return _stated_stock_volume(text)
    asked = (match.group("asked") or match.group("v2_unit")).lower()
    v1_unit = "mL" if asked.startswith(("ml", "milli")) else "L"
    return ChemistryIntent(
        kind="solutions",
        chemistry_op="dilution",
        params={
            "m1": float(match.group("m1")),
            "m2": float(match.group("m2")),
            "v2": float(match.group("v2")),
        },
        units={"v1": v1_unit, "v2": match.group("v2_unit")},
    )


# "Dilute 10 mL of 2 M HCl to 0.5 M": the stock volume and both concentrations, so V2.
_DILUTE_TO = re.compile(
    rf"\b(?:dilute|diluting)\s+(?P<v1>{_N})\s*(?P<unit>mL|L)\s+of\s+"
    rf"(?P<m1>{_N}){_MOLAR_VALUE}(?:\s+[A-Za-z][A-Za-z0-9]*)?\s+to\s+"
    rf"(?P<m2>{_N}){_MOLAR_VALUE}",
    re.IGNORECASE,
)
# "What is the final volume when 50 mL of 2.0 M HCl is diluted to 0.50 M?": the same, written
# in the passive, asked as a volume.
_DILUTED_TO = re.compile(
    rf"(?P<v1>{_N})\s*(?P<unit>mL|L)\s+of\s+(?:an?\s+)?(?P<m1>{_N}){_MOLAR_VALUE}"
    r"(?:\s+[A-Za-z][A-Za-z0-9()]*)?(?:\s+solution)?\s+(?:is|are|was|were|gets?|got)\s+diluted\s+to\s+"
    rf"(?P<m2>{_N}){_MOLAR_VALUE}",
    re.IGNORECASE,
)
_FINAL_VOLUME_ASK = re.compile(
    r"\b(?:final|new|total)\s+volume\b|\bwhat\s+volume\b|\bhow\s+many\s+(?:mL|L)\b",
    re.IGNORECASE,
)


def _dilute_to_concentration(text: str) -> ChemistryIntent | None:
    """V2 = M1V1 / M2. Water to add is V2 - V1, another question, so "add" declines."""
    match = _DILUTE_TO.search(text)
    if match is None and _FINAL_VOLUME_ASK.search(text):
        match = _DILUTED_TO.search(text)
    if match is None or _ADDED.search(text):
        return None
    unit = "mL" if match.group("unit").lower() == "ml" else "L"
    return ChemistryIntent(
        kind="solutions",
        chemistry_op="dilution",
        params={
            "m1": float(match.group("m1")),
            "v1": float(match.group("v1")),
            "m2": float(match.group("m2")),
        },
        units={"v1": unit},
    )


# "M1 = 12 M, M2 = 1.5 M, V2 = 500 mL": both concentrations labelled in molar units name a
# dilution without the word. A mass is never in M, so "M1 = 2 kg" stays physics'.
_BOTH_MOLARITIES = re.compile(
    rf"\bM1\s*=\s*{_N}{_MOLAR_VALUE}[\s\S]*\bM2\s*=\s*{_N}{_MOLAR_VALUE}"
    rf"|\bM2\s*=\s*{_N}{_MOLAR_VALUE}[\s\S]*\bM1\s*=\s*{_N}{_MOLAR_VALUE}"
)


def _extract_solutions(text: str) -> ChemistryIntent | None:
    mole_fraction = _extract_mole_fraction_masses(text)
    if mole_fraction is not None:
        return mole_fraction
    percent_solute = _extract_percent_solute(text)
    if percent_solute is not None:
        return percent_solute
    stock = _stock_volume(text)
    if stock is not None:
        return stock
    diluted = _dilute_to_concentration(text)
    if diluted is not None:
        return diluted
    if re.search(r"\b(?:dilut|M1V1)\w*", text, re.IGNORECASE) or _BOTH_MOLARITIES.search(text):
        m1 = _search(rf"\bM1\s*=\s*({_N})", text)
        m2 = _search(rf"\bM2\s*=\s*({_N})", text)
        v1 = _labeled_volume(text, "V1")
        v2 = _labeled_volume(text, "V2")
        known = sum(value is not None for value in (m1, m2, v1, v2))
        if known == 3:
            v1_unit = (
                (v1[1] if v1 is not None else None) or (v2[1] if v2 is not None else None) or "L"
            )
            params: dict[str, float] = {}
            units: dict[str, str] = {}
            if m1 is not None:
                params["m1"] = m1
            if m2 is not None:
                params["m2"] = m2
            if v1 is not None:
                params["v1"] = v1[0]
                units["v1"] = v1_unit
            if v2 is not None:
                params["v2"] = v2[0]
                units["v2"] = v2[1] or v1_unit
            return ChemistryIntent(
                kind="solutions",
                chemistry_op="dilution",
                params=params,
                units=units,
            )
    if re.search(r"\bmolality\b", text, re.IGNORECASE):
        moles = _search(rf"({_N})\s*mol(?:e|es)?(?:\s+of\s+solute)?", text)
        solvent = _search(rf"({_N})\s*kg(?:\s+of\s+solvent)?", text)
        if moles is not None and solvent is not None:
            return ChemistryIntent(
                kind="solutions",
                chemistry_op="molality",
                params={"moles": moles, "solvent_kg": solvent},
            )
    if re.search(r"\bmass percent\b|%\s*(?:by mass|w/w)", text, re.IGNORECASE):
        solute = _search(rf"({_N})\s*g(?:rams?)?\s+(?:of\s+)?solute", text)
        solution = _search(rf"({_N})\s*g(?:rams?)?\s+(?:of\s+)?solution", text)
        if solute is not None and solution is not None:
            return ChemistryIntent(
                kind="solutions",
                chemistry_op="mass_percent",
                params={"solute_mass": solute, "solution_mass": solution},
            )
    if re.search(r"\bmolarity\b|\bconcentration\s+of\s+(?:the\s+)?solution", text, re.IGNORECASE):
        moles = _search(rf"({_N})\s*mol(?:e|es)?", text)
        volume = _search(rf"({_N})\s*(?:L|liters?|litres?)\b", text)
        if moles is not None and volume is not None:
            return ChemistryIntent(
                kind="solutions",
                chemistry_op="molarity",
                params={"moles": moles, "volume_l": volume},
            )
    return None


_NAMED = "|".join(re.escape(name) for name in sorted(NAMED_COMPOUNDS, key=len, reverse=True))
# What the asked grams are of: a named compound, a formula, or the solute by a common noun.
_SOLUTE = rf"(?:{_NAMED}|solute|salt|sugar|{CHEMICAL_FORMULA}{FORMULA_END})"
# "How many grams of NaCl are needed to make 500 g of a 5.0% by mass solution?", "What mass of
# glucose is in 250 g of a 10.0% (w/w) glucose solution?": m(solute) = (mass % / 100) m(solution).
_PERCENT_SOLUTE = re.compile(
    r"\b(?:how\s+many\s+(?:grams|g)\s+of|how\s+much|what\s+mass\s+of|"
    r"(?:find|calculate|determine|what\s+is)\s+the\s+mass\s+of)\s+(?:the\s+)?"
    rf"(?P<solute>{_SOLUTE})\s+(?:(?:is|are|would\s+be|will\s+be)\s+)?"
    r"(?:(?:needed|required|used|dissolved|present|contained)\s+)?"
    r"(?:to\s+(?:make|prepare)|in|for)\s+"
    rf"(?P<mass>{_N})\s*(?P<unit>g|grams?|kg)\s+of\s+(?:an?\s+)?(?P<percent>{_N})\s*%\s*"
    r"(?P<basis>\(?\s*(?:by\s+(?:mass|weight|volume)|w/w|m/m|v/v|w/v|m/v)\s*\)?\s*)?"
    rf"(?:(?P<named>{_NAMED}|{CHEMICAL_FORMULA}{FORMULA_END})\s+)?(?:aqueous\s+)?solution\b",
    re.IGNORECASE,
)


def _extract_percent_solute(text: str) -> ChemistryIntent | None:
    """The solute's mass in a mass of solution of a stated mass percent.

    A percent of a solution weighed in grams is by mass; one written by volume (v/v, w/v)
    is another law and declines. The asked grams must be the solute's: the grams of water
    for the same solution are the rest of it, not this.
    """
    match = _PERCENT_SOLUTE.search(text)
    if match is None:
        return None
    basis = (match.group("basis") or "").lower()
    if "vol" in basis or "v" in basis.replace("by", ""):
        return None
    solute = match.group("solute")
    named = match.group("named")
    formula = NAMED_COMPOUNDS.get(solute.lower(), solute)
    if formula == "H2O" or (named and NAMED_COMPOUNDS.get(named.lower(), named) != formula):
        return None
    percent = float(match.group("percent"))
    if not 0 < percent <= 100:
        return None
    mass = float(match.group("mass"))
    unit = "g" if match.group("unit").lower().startswith("g") else "kg"
    return ChemistryIntent(
        kind="solutions",
        chemistry_op="solute_mass_from_percent",
        params={"percent": percent, "solution_mass": mass * (1000 if unit == "kg" else 1)},
        units={"solution_mass": unit},
    )


_SUBSTANCE = rf"(?:{_NAMED}|{CHEMICAL_FORMULA}{FORMULA_END})"
# "What is the mole fraction of ethanol in a solution of 46 g ethanol and 54 g water?"
_MOLE_FRACTION_OF = re.compile(
    rf"\bmole\s+fraction\s+of\s+(?P<asked>{_SUBSTANCE})\s+in\s+(?:an?\s+|the\s+)?"
    r"(?:solution|mixture)\s+(?:of|with|containing|made\s+(?:of|from))\s+"
    rf"(?P<mass_a>{_N})\s*g(?:rams?)?\s+(?:of\s+)?(?P<first>{_SUBSTANCE})\s+and\s+"
    rf"(?P<mass_b>{_N})\s*g(?:rams?)?\s+(?:of\s+)?(?P<second>{_SUBSTANCE})",
    re.IGNORECASE,
)


def _formula_of(token: str) -> str | None:
    named = NAMED_COMPOUNDS.get(token.lower())
    if named is not None:
        return named
    return token if is_formula(token) else None


def _extract_mole_fraction_masses(text: str) -> ChemistryIntent | None:
    """χ of one of two components weighed in grams, each a named compound or a formula."""
    match = _MOLE_FRACTION_OF.search(text)
    if match is None:
        return None
    asked = _formula_of(match.group("asked"))
    first, second = _formula_of(match.group("first")), _formula_of(match.group("second"))
    if asked is None or first is None or second is None or first == second:
        return None
    masses = {first: float(match.group("mass_a")), second: float(match.group("mass_b"))}
    if asked not in masses:
        return None
    other = second if asked == first else first
    return ChemistryIntent(
        kind="solutions",
        chemistry_op="mole_fraction_mass",
        formula=asked,
        target=other,
        params={
            "mass_a": masses[asked],
            "molar_mass_a": molar_mass(asked),
            "mass_b": masses[other],
            "molar_mass_b": molar_mass(other),
        },
    )


def _extract_colligative(text: str) -> ChemistryIntent | None:
    factor = _search(rf"\bi\s*=\s*({_N})", text)
    molality = _search(rf"\bmolality\s*=\s*({_N})", text)
    if re.search(r"\bboiling point elevation\b", text, re.IGNORECASE):
        constant = _search(rf"\bKb\s*=\s*({_N})", text, flags=0)
        params = _floats(i=factor, kb=constant, molality=molality)
        if params is not None:
            return ChemistryIntent(
                kind="solutions", chemistry_op="boiling_elevation", params=params
            )
    if re.search(r"\bfreezing point depression\b", text, re.IGNORECASE):
        constant = _search(rf"\bKf\s*=\s*({_N})", text, flags=0)
        params = _floats(i=factor, kf=constant, molality=molality)
        if params is not None:
            return ChemistryIntent(
                kind="solutions", chemistry_op="freezing_depression", params=params
            )
    if re.search(r"\bosmotic pressure\b", text, re.IGNORECASE):
        molarity = _search(rf"\bmolarity\s*=\s*({_N})", text)
        temperature = _search(rf"\bT\s*=\s*({_N})\s*K", text, flags=0)
        params = _floats(i=factor, molarity=molarity, temperature=temperature)
        if params is not None:
            return ChemistryIntent(kind="solutions", chemistry_op="osmotic_pressure", params=params)
    if re.search(r"\bRaoult\b", text, re.IGNORECASE):
        fraction = _search(rf"mole fraction\s*=\s*({_N})", text)
        pure = _search(rf"pure pressure\s*=\s*({_N})", text)
        if fraction is not None and pure is not None:
            return ChemistryIntent(
                kind="solutions",
                chemistry_op="raoult",
                params={"mole_fraction": fraction, "pure_pressure": pure},
            )
    return None
