"""Equilibria: Ksp and precipitation, the common-ion effect, Kp, Kc ↔ Kp, and ICE tables."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    _equation,
    _pressure_species,
    _search,
)
from app.modules.chemistry.quantity import to_kelvin
from app.modules.chemistry.request import CHEMICAL_FORMULA, EQUATION_RE
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.species_facts import dissolution_equation, named_species

_ICE_ASK = re.compile(r"\bICE equilibrium\b|\bequilibrium\s+concentrations?\b", re.IGNORECASE)


_CONCENTRATION_CHAIN = re.compile(rf"((?:\[{CHEMICAL_FORMULA}\]\s*=\s*)+)({_N})")


def _extract_equilibrium(text: str) -> ChemistryIntent | None:
    qsp = _search(rf"\bQsp\s*=\s*({_N})", text, flags=0)
    ksp = _search(rf"\bKsp\s*=\s*({_N})", text, flags=0)
    if qsp is not None and ksp is not None:
        return ChemistryIntent(
            kind="equilibrium", chemistry_op="precipitation", params={"qsp": qsp, "ksp": ksp}
        )
    equation = _equation(text)
    if re.search(r"\bcommon-ion\b", text, re.IGNORECASE) and equation and ksp is not None:
        concentrations = {
            match.group(1): float(match.group(2))
            for match in re.finditer(rf"\[({CHEMICAL_FORMULA})\]\s*=\s*({_N})", text)
        }
        return ChemistryIntent(
            kind="equilibrium",
            chemistry_op="common_ion",
            equation=equation,
            params={"ksp": ksp},
            species=concentrations,
        )
    if ksp is not None and equation and re.search(r"\bsolubility\b", text, re.IGNORECASE):
        return ChemistryIntent(
            kind="equilibrium", chemistry_op="ksp", equation=equation, params={"ksp": ksp}
        )
    solubility = _search(
        rf"(?:molar\s+)?solubility\s*(?:=|of|is)?\s*({_N})\s*(?:(?-i:M)(?![A-Za-z])|mol/L)", text
    )
    if solubility is not None and equation and re.search(r"\bKsp\b", text, flags=0):
        return ChemistryIntent(
            kind="equilibrium",
            chemistry_op="ksp",
            equation=equation,
            params={"solubility": solubility},
        )
    salt = None if equation else _salt_solubility(text)
    if salt is not None:
        return salt
    if (
        re.search(r"\bKp\b", text, re.IGNORECASE)
        and equation
        and re.search(r"\bFind Kp\b", text, re.IGNORECASE)
    ):
        # "Kc = 0.5 at 500 K. Find Kp." converts the stated Kc; it has no partial pressures.
        kc = _search(rf"\bKc\s*=\s*({_N})", text, flags=0)
        temperature = _search(rf"({_N})\s*K\b", text, flags=0)
        if kc is not None and temperature is not None:
            return ChemistryIntent(
                kind="equilibrium",
                chemistry_op="kc_kp",
                equation=equation,
                params={"kc": kc, "temperature": temperature},
            )
        return ChemistryIntent(
            kind="equilibrium",
            chemistry_op="kp",
            equation=equation,
            species=_pressure_species(text, equation),
        )
    converted = _stated_k_to_convert(text, equation)
    if converted is not None:
        return converted
    if re.search(r"\b(?:Kc to Kp|Kp to Kc)\b", text, re.IGNORECASE) and equation:
        temperature = _search(rf"\bT\s*=\s*({_N})\s*K", text, flags=0)
        kc = _search(rf"\bKc\s*=\s*({_N})", text, flags=0)
        kp = _search(rf"\bKp\s*=\s*({_N})", text, flags=0)
        params = {}
        if temperature is not None:
            params["temperature"] = temperature
        if kc is not None:
            params["kc"] = kc
        if kp is not None:
            params["kp"] = kp
        return ChemistryIntent(
            kind="equilibrium", chemistry_op="kc_kp", equation=equation, params=params
        )
    if (_ICE_ASK.search(text) or _AT_EQUILIBRIUM.search(text)) and equation:
        constant = _search(rf"\bK(?:c|eq)?\s*=\s*({_N})", text, flags=0)
        # "[H2] = [I2] = 1.0 M" gives both the one value.
        concentrations = {
            name: float(match.group(2))
            for match in _CONCENTRATION_CHAIN.finditer(text)
            for name in re.findall(rf"\[({CHEMICAL_FORMULA})\]", match.group(1))
        } or _starting_amounts(text, equation)
        if constant is not None and concentrations:
            return ChemistryIntent(
                kind="equilibrium",
                chemistry_op="ice_equilibrium",
                equation=equation,
                params={"k": constant},
                species=concentrations,
            )
    return None


# "what is [HI] at equilibrium?", "the equilibrium [HI]": one concentration asked.
_AT_EQUILIBRIUM = re.compile(
    rf"\[{CHEMICAL_FORMULA}\]\s+at\s+equilibrium\b|\bequilibrium\s+\[{CHEMICAL_FORMULA}\]",
    re.IGNORECASE,
)
# "if you start with 0.50 M H2 and 0.50 M I2": the initial concentrations, in words.
_STARTING = re.compile(
    r"\b(?:start(?:s|ed|ing)?\s+with|initial(?:ly)?|begin(?:s|ning)?\s+with)\b", re.IGNORECASE
)
_MOLAR_OF = re.compile(
    rf"({_N})\s*(?:(?-i:M)|mol/L)\s+(?:of\s+)?({CHEMICAL_FORMULA})(?![A-Za-z0-9])"
)


def _starting_amounts(text: str, equation: str) -> dict[str, float]:
    """Each starting concentration "0.50 M H2" of a species the equation names.

    Every molar value the question states is one species' start; a value of a species the
    equation does not name, or a species stated twice, leaves the start unread.
    """
    if not _STARTING.search(text):
        return {}
    from app.modules.chemistry.species import parse_reaction

    reaction = parse_reaction(equation)
    if reaction is None:
        return {}
    labels = {term.species.label for term in (*reaction.reactants, *reaction.products)}
    found: dict[str, float] = {}
    for match in _MOLAR_OF.finditer(EQUATION_RE.sub(" ", text)):
        value, formula = float(match.group(1)), match.group(2)
        if formula not in labels or formula in found:
            return {}
        found[formula] = value
    return found


# "Kp for N2 + 3H2 ⇌ 2NH3 is 1.45 x 10^-5 at 500 °C. Find Kc.": one constant stated, the
# other asked, at a stated temperature.
_FIND_K = re.compile(r"\b(?:find|calculate|determine|what\s+is)\s+(?:the\s+)?(?-i:(Kc|Kp))\b", re.I)
_TEMPERATURE = re.compile(rf"\b(?:at|T\s*=)\s*({_N})\s*(°\s*C|K)(?![A-Za-z])")


def _stated_k(text: str, symbol: str) -> float | None:
    values = re.findall(
        rf"(?<![A-Za-z]){symbol}(?![A-Za-z0-9])(?:\s+(?:for|of)\s+[^.?!=]{{0,80}}?)?\s*(?:=|is)\s*({_N})",
        EQUATION_RE.sub(" the reaction ", text),
    )
    return float(values[0]) if len(values) == 1 else None


def _stated_k_to_convert(text: str, equation: str | None) -> ChemistryIntent | None:
    asked = _FIND_K.search(text)
    if asked is None or equation is None:
        return None
    target = asked.group(1)
    source = "Kp" if target == "Kc" else "Kc"
    value = _stated_k(text, source)
    temperatures = _TEMPERATURE.findall(text)
    if value is None or len(temperatures) != 1 or _stated_k(text, target) is not None:
        return None
    number, unit = temperatures[0]
    kelvin = to_kelvin(float(number), "celsius" if "C" in unit else "kelvin")
    return ChemistryIntent(
        kind="equilibrium",
        chemistry_op="kc_kp",
        equation=equation,
        params={source.lower(): value, "temperature": kelvin},
    )


_KSP_OF = re.compile(
    rf"\bKsp\s*(?:\(\s*({CHEMICAL_FORMULA})\s*\)|(?:value\s+)?(?:of|for)\s+({CHEMICAL_FORMULA}))?"
    rf"\s*(?:=|is|:)\s*({_N})"
)


_SOLUBILITY_OF = re.compile(
    rf"\bsolubility\s+(?:of\s+({CHEMICAL_FORMULA})\s+)?(?:=|is)\s*({_N})\s*"
    r"(?:(?-i:M)(?![A-Za-z])|mol\s*/\s*L)",
    re.IGNORECASE,
)


def _salt_solubility(text: str) -> ChemistryIntent | None:
    """A salt named by its formula instead of its dissolution equation.

    "The Ksp of AgCl is 1.8e-10. Find its molar solubility." The equation is the salt's ions
    (``dissolution_equation``); the other direction gives the solubility and asks for Ksp.
    """
    ksp = _KSP_OF.search(text)
    solubility = _SOLUBILITY_OF.search(text)
    if ksp is not None and solubility is None and re.search(r"\bsolubility\b", text, re.I):
        stated, params = ksp.group(1) or ksp.group(2), {"ksp": float(ksp.group(3))}
    elif solubility is not None and ksp is None and re.search(r"(?<![A-Za-z])Ksp\b", text):
        stated, params = solubility.group(1), {"solubility": float(solubility.group(2))}
    else:
        return None
    salts = [stated] if stated else [f for f in named_species(text) if dissolution_equation(f)]
    if len(salts) != 1 or (equation := dissolution_equation(salts[0])) is None:
        return None
    return ChemistryIntent(
        kind="equilibrium", chemistry_op="ksp", equation=equation, formula=salts[0], params=params
    )
