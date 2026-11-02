"""Thermochemistry: Gibbs energy, calorimetry, Hess's law, formation and bond enthalpies."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    _equation,
    _labeled,
    _search,
)
from app.modules.chemistry.request import CHEMICAL_FORMULA
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.schemas.intent import MAX_STEPS
from app.modules.chemistry.species import ARROWS
from app.modules.chemistry.species_facts import without_formulas


def _extract_gibbs(text: str) -> ChemistryIntent | None:
    if re.search(r"\b(?:Gibbs|\u0394G|delta\s*G)\b", text, re.IGNORECASE):
        delta_h = _search(rf"(?:ΔH|delta\s*H)\s*=\s*({_N})\s*kJ", text)
        delta_s = _search(rf"(?:ΔS|delta\s*S)\s*=\s*({_N})\s*(k?J)", text)
        entropy_unit = re.search(r"(?:ΔS|delta\s*S)\s*=\s*" + _N + r"\s*(k?J)", text, re.IGNORECASE)
        temperature = _search(rf"(?:\bT|temperature)\s*(?:=|of)?\s*({_N})\s*K\b", text)
        if delta_h is not None and delta_s is not None and temperature is not None:
            if entropy_unit and entropy_unit.group(1).lower() == "j":
                delta_s /= 1000
            return ChemistryIntent(
                kind="thermochemistry",
                chemistry_op="gibbs",
                params={"delta_h": delta_h, "delta_s": delta_s, "temperature": temperature},
            )
    return None


def _extract_clausius(text: str) -> ChemistryIntent | None:
    if not re.search(r"\bClausius\b", text, re.IGNORECASE):
        return None
    found = _labeled(
        text,
        (
            ("p1", rf"\bP1\s*=\s*({_N})"),
            ("t1", rf"\bT1\s*=\s*({_N})"),
            ("p2", rf"\bP2\s*=\s*({_N})"),
            ("t2", rf"\bT2\s*=\s*({_N})"),
            ("delta_h", rf"\bdH\s*=\s*({_N})"),
        ),
    )
    points = {"p1", "t1", "p2", "t2"}
    pressure = {"p1", "t1", "t2", "delta_h"} <= set(found) or {"p2", "t1", "t2", "delta_h"} <= set(
        found
    )
    complete = set(found) == points or (pressure and "delta_h" in found and len(found) == 4)
    if complete:
        return ChemistryIntent(
            kind="thermochemistry", chemistry_op="clausius_clapeyron", params=found
        )
    return None


def _extract_enthalpy(text: str) -> ChemistryIntent | None:
    clausius = _extract_clausius(text)
    if clausius is not None:
        return clausius
    if re.search(r"\b(?:calorimeter constant|Ccal)\b", text, re.IGNORECASE):
        match = re.search(
            rf"(?:Ccal|calorimeter constant)\s*=\s*({_N})\s*(k?J)\s*/\s*(?:°\s*C|C|K)\b",
            text,
            re.IGNORECASE,
        )
        constant = None
        if match is not None:
            constant = float(match.group(1)) * (1000 if match.group(2).lower() == "kj" else 1)
        delta = _search(rf"(?:ΔT|delta\s*T)\s*=\s*({_N})", text)
        if constant is not None and delta is not None:
            return ChemistryIntent(
                kind="thermochemistry",
                chemistry_op="calorimetry",
                params={"c_cal": constant, "delta_t": delta},
            )
    from_equations = _hess_from_equations(text)
    if from_equations is not None:
        return from_equations
    if re.search(r"\bHess\b", text, re.IGNORECASE):
        params: dict[str, float] = {}
        steps = set(re.findall(r"ΔH(\d+)\s*=", text))
        multipliers = set(re.findall(r"multiplier(\d+)\s*=", text))
        if (
            not steps
            or len(steps) > 4
            or steps != multipliers
            or steps != {str(n) for n in range(1, len(steps) + 1)}
        ):
            return None  # a step without its multiplier would give a partial sum
        for index in range(1, 5):
            enthalpy = _search(rf"ΔH{index}\s*=\s*({_N})", text)
            multiplier = _search(rf"multiplier{index}\s*=\s*({_N})", text)
            if enthalpy is None or multiplier is None:
                break
            params[f"dh{index}"] = enthalpy
            params[f"m{index}"] = multiplier
        if params:
            return ChemistryIntent(kind="thermochemistry", chemistry_op="hess", params=params)
    listed = _formation_list(text)
    if listed is not None:
        return listed
    if re.search(r"\bformation enthalpy\b", text, re.IGNORECASE):
        equation = _equation(text)
        values = {
            match.group(1): float(match.group(2))
            for match in re.finditer(rf"ΔH(?:°f|f°?)\(({CHEMICAL_FORMULA})\)\s*=\s*({_N})", text)
        }
        if equation and values:
            return ChemistryIntent(
                kind="thermochemistry",
                chemistry_op="formation_enthalpy",
                equation=equation,
                species=values,
            )
    if re.search(r"\bbond enthalpy\b", text, re.IGNORECASE):
        broken = _search(rf"bonds broken\s*=\s*({_N})", text)
        formed = _search(rf"bonds formed\s*=\s*({_N})", text)
        if broken is not None and formed is not None:
            return ChemistryIntent(
                kind="thermochemistry",
                chemistry_op="bond_enthalpy",
                params={"broken": broken, "formed": formed},
            )
    return None


# "1/2 O2" and "½ O2" are a coefficient of one half: written as 0.5 so a term reads it whole.
_FRACTION_COEFFICIENT = re.compile(r"(?<![\w.])(\d+)\s*/\s*(\d+)(?=\s*[A-Z(])")
_ARROW = "(?:" + "|".join(re.escape(arrow) for arrow in sorted(ARROWS, key=len, reverse=True)) + ")"
_TERM = rf"(?:\d+(?:\.\d+)?\s*)?{CHEMICAL_FORMULA}"
_REACTION = re.compile(
    rf"(?<![A-Za-z0-9.\[])({_TERM}(?:\s*\+\s*{_TERM})*\s*{_ARROW}\s*{_TERM}(?:\s*\+\s*{_TERM})*)"
    r"(?![A-Za-z0-9])"
)
# A step's enthalpy: "ΔH = -393.5 kJ", "ΔH1 = -283.0 kJ/mol", "delta H = ...".
_STEP_ENTHALPY = re.compile(
    rf"(?:Δ\s*H|\bdelta\s*H)(?:°|º)?\s*\d?\s*=\s*({_N})\s*(kJ(?:\s*/\s*mol|\s+mol\^?-1)?)",
    re.IGNORECASE,
)
# Between a reaction and its ΔH: punctuation, and nothing that names another value.
_STEP_GAP = re.compile(r"[\s,;:(]*(?:with\s+|where\s+)?")
_ENTHALPY_ASK = re.compile(
    r"\b(?:find|calculate|determine|compute|what\s+is)\b[^.?!]*(?:Δ\s*H|\bdelta\s*H|enthalpy)",
    re.IGNORECASE,
)


def _hess_from_equations(text: str) -> ChemistryIntent | None:
    """Hess's law from written steps: each step's ΔH follows it, and one reaction is asked.

    "C + O2 → CO2, ΔH = -393.5 kJ; CO + 1/2 O2 → CO2, ΔH = -283.0 kJ. Find ΔH for
    C + 1/2 O2 → CO." The solver finds how many of each step make the asked reaction. Every
    number of the text is a coefficient or a step's ΔH, and the steps share one unit.
    """
    if not _ENTHALPY_ASK.search(text):
        return None
    written = _FRACTION_COEFFICIENT.sub(
        lambda match: str(int(match.group(1)) / int(match.group(2))), text.replace("½", "0.5")
    )
    reactions = list(_REACTION.finditer(written))
    enthalpies = list(_STEP_ENTHALPY.finditer(written))
    if len(reactions) < 2 or not enthalpies or len(reactions) > MAX_STEPS + 1:
        return None
    steps: dict[int, re.Match[str]] = {}
    for enthalpy in enthalpies:
        before = [reaction for reaction in reactions if reaction.end() <= enthalpy.start()]
        if not before:
            return None
        reaction = before[-1]
        gap = written[reaction.end() : enthalpy.start()]
        if not _STEP_GAP.fullmatch(gap) or reaction.start() in steps:
            return None
        steps[reaction.start()] = enthalpy
    asked = [reaction for reaction in reactions if reaction.start() not in steps]
    units = {" ".join(match.group(2).lower().split()) for match in enthalpies}
    if len(asked) != 1 or len(units) != 1:
        return None
    # Every number is a coefficient inside a reaction or a step's ΔH.
    blanked = list(written)
    for match in (*reactions, *enthalpies):
        blanked[match.start() : match.end()] = " " * (match.end() - match.start())
    if re.search(r"\d", "".join(blanked)):
        return None
    ordered = sorted(steps.items())
    unit = "kJ/mol" if "mol" in units.pop() else "kJ"
    return ChemistryIntent(
        kind="thermochemistry",
        chemistry_op="hess",
        equation=asked[0].group(1).strip(),
        steps=[reaction_text(written, start) for start, _enthalpy in ordered],
        params={
            f"dh{index}": float(enthalpy.group(1))
            for index, (_start, enthalpy) in enumerate(ordered, start=1)
        },
        units={"enthalpy": unit},
    )


def reaction_text(text: str, start: int) -> str:
    match = _REACTION.match(text, start)
    return "" if match is None else match.group(1).strip()


# "using ΔHf values: CH4 = -74.8, CO2 = -393.5, H2O(l) = -285.8 kJ/mol".
_FORMATION_CUE = re.compile(
    r"Δ\s*H\s*(?:°\s*)?f|\bdelta\s*H\s*f\b|\b(?:heats?|enthalp(?:y|ies))\s+of\s+formation\b"
    r"|\bformation\s+enthalp(?:y|ies)\b",
    re.IGNORECASE,
)
_REACTION_ENTHALPY_ASK = re.compile(
    r"\b(?:find|calculate|determine|compute|what\s+is)\b[^.?!]*(?:Δ\s*H|\bdelta\s*H|enthalpy)",
    re.IGNORECASE,
)


def _formation_list(text: str) -> ChemistryIntent | None:
    """ΔH°rxn from a list of formation enthalpies written "species = value".

    Each compound of the equation has exactly one listed value; an element in its standard
    state is zero (the solver's rule). A listed species the equation lacks, a value written
    twice, or a unit other than kJ/mol declines.
    """
    if not _FORMATION_CUE.search(text) or not _REACTION_ENTHALPY_ASK.search(text):
        return None
    if re.search(r"\bkJ\s*/\s*mol\b", text) is None:
        return None
    equation = _equation(text)
    if equation is None:
        return None
    from app.modules.chemistry.equations import balance_equation

    balanced = balance_equation(equation)
    if not balanced.balanced:
        return None
    labels = {*balanced.reactants, *balanced.products}
    outside = text.replace(equation, " ", 1)
    values: dict[str, float] = {}
    for match in re.finditer(
        rf"(?<![A-Za-z0-9])({CHEMICAL_FORMULA})\s*(?:=|:)\s*({_N})(?!\s*(?:K|°|M|g|mol)\b)",
        outside,
    ):
        label = match.group(1)
        if label not in labels or label in values:
            return None
        values[label] = float(match.group(2))
    if not values or len(re.findall(_N, without_formulas(outside))) != len(values):
        return None
    return ChemistryIntent(
        kind="thermochemistry",
        chemistry_op="formation_enthalpy",
        equation=equation,
        species=values,
    )
