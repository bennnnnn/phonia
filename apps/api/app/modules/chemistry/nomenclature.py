"""School names of ionic compounds, from one closed table of ions.

A salt is a cation and an anion in the fewest whole numbers that cancel their charges:
calcium nitrate is Ca(NO3)2, and Fe2(SO4)3 is iron(III) sulfate. A metal with more than one
common charge takes a Roman numeral, worked out from the anion's charge. Anything the table
does not hold (a molecular compound such as CO2, an acid, a hydrate, mercury(I)'s Hg2^2+)
is not named here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Ion:
    formula: str
    name: str
    charge: int
    # A group of atoms is bracketed when more than one is written: Ca(NO3)2.
    polyatomic: bool = False


# Cations with one common charge.
_FIXED_CATIONS: tuple[Ion, ...] = (
    Ion("Li", "lithium", 1),
    Ion("Na", "sodium", 1),
    Ion("K", "potassium", 1),
    Ion("Rb", "rubidium", 1),
    Ion("Cs", "cesium", 1),
    Ion("Ag", "silver", 1),
    Ion("NH4", "ammonium", 1, polyatomic=True),
    Ion("Be", "beryllium", 2),
    Ion("Mg", "magnesium", 2),
    Ion("Ca", "calcium", 2),
    Ion("Sr", "strontium", 2),
    Ion("Ba", "barium", 2),
    Ion("Zn", "zinc", 2),
    Ion("Cd", "cadmium", 2),
    Ion("Al", "aluminum", 3),
)
# Metals with more than one common charge: their name carries it, iron(III).
_VARIABLE_METALS: dict[str, tuple[str, tuple[int, ...]]] = {
    "Fe": ("iron", (2, 3)),
    "Cu": ("copper", (1, 2)),
    "Co": ("cobalt", (2, 3)),
    "Ni": ("nickel", (2, 3)),
    "Mn": ("manganese", (2, 3, 4)),
    "Cr": ("chromium", (2, 3)),
    "Pb": ("lead", (2, 4)),
    "Sn": ("tin", (2, 4)),
    "Au": ("gold", (1, 3)),
}
_ANIONS: tuple[Ion, ...] = (
    Ion("F", "fluoride", -1),
    Ion("Cl", "chloride", -1),
    Ion("Br", "bromide", -1),
    Ion("I", "iodide", -1),
    Ion("O", "oxide", -2),
    Ion("S", "sulfide", -2),
    Ion("N", "nitride", -3),
    Ion("P", "phosphide", -3),
    Ion("OH", "hydroxide", -1, polyatomic=True),
    Ion("CN", "cyanide", -1, polyatomic=True),
    Ion("NO3", "nitrate", -1, polyatomic=True),
    Ion("NO2", "nitrite", -1, polyatomic=True),
    Ion("SO4", "sulfate", -2, polyatomic=True),
    Ion("SO3", "sulfite", -2, polyatomic=True),
    Ion("HSO4", "hydrogen sulfate", -1, polyatomic=True),
    Ion("CO3", "carbonate", -2, polyatomic=True),
    Ion("HCO3", "hydrogen carbonate", -1, polyatomic=True),
    Ion("PO4", "phosphate", -3, polyatomic=True),
    Ion("HPO4", "hydrogen phosphate", -2, polyatomic=True),
    Ion("H2PO4", "dihydrogen phosphate", -1, polyatomic=True),
    Ion("ClO", "hypochlorite", -1, polyatomic=True),
    Ion("ClO2", "chlorite", -1, polyatomic=True),
    Ion("ClO3", "chlorate", -1, polyatomic=True),
    Ion("ClO4", "perchlorate", -1, polyatomic=True),
    Ion("MnO4", "permanganate", -1, polyatomic=True),
    Ion("CrO4", "chromate", -2, polyatomic=True),
    Ion("Cr2O7", "dichromate", -2, polyatomic=True),
    Ion("CH3COO", "acetate", -1, polyatomic=True),
    Ion("C2O4", "oxalate", -2, polyatomic=True),
    Ion("SCN", "thiocyanate", -1, polyatomic=True),
)
_ALIASES = {
    "aluminium": "aluminum",
    "caesium": "cesium",
    "sulphate": "sulfate",
    "sulphide": "sulfide",
    "sulphite": "sulfite",
    "bicarbonate": "hydrogen carbonate",
}
_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}
_FROM_ROMAN = {roman: value for value, roman in _ROMAN.items()}


@dataclass(frozen=True, slots=True)
class Salt:
    """One ionic compound: its cation and anion, how many of each, its formula and name."""

    cation: Ion
    anion: Ion
    cations: int
    anions: int

    @property
    def formula(self) -> str:
        return _part(self.cation, self.cations) + _part(self.anion, self.anions)

    @property
    def name(self) -> str:
        return f"{self.cation.name} {self.anion.name}"


def _part(ion: Ion, count: int) -> str:
    if count == 1:
        return ion.formula
    return f"({ion.formula}){count}" if ion.polyatomic else f"{ion.formula}{count}"


def _cation(symbol: str, charge: int) -> Ion | None:
    fixed = next((ion for ion in _FIXED_CATIONS if ion.formula == symbol), None)
    if fixed is not None:
        return fixed if fixed.charge == charge else None
    variable = _VARIABLE_METALS.get(symbol)
    if variable is None or charge not in variable[1]:
        return None
    return Ion(symbol, f"{variable[0]}({_ROMAN[charge]})", charge)


def _salt(cation: Ion, anion: Ion) -> Salt:
    common = math.lcm(cation.charge, -anion.charge)
    return Salt(cation, anion, common // cation.charge, common // -anion.charge)


def salt_from_name(name: str) -> Salt | None:
    """ "calcium nitrate" → Ca(NO3)2; "iron(III) sulfate" → Fe2(SO4)3. None off the table."""
    words = " ".join(_ALIASES.get(word, word) for word in name.lower().split())
    words = re.sub(r"\s?\(\s*([ivx]+)\s*\)", lambda match: f"({match.group(1).upper()})", words)
    for anion in sorted(_ANIONS, key=lambda ion: len(ion.name), reverse=True):
        if not words.endswith(" " + anion.name):
            continue
        head = words[: -len(anion.name) - 1].strip()
        fixed = next((ion for ion in _FIXED_CATIONS if ion.name == head), None)
        if fixed is not None:
            return _salt(fixed, anion)
        match = re.fullmatch(r"^([a-z]+)\(([IVX]+)\)", head)
        if match is None:
            return None
        symbol = next(
            (sym for sym, (word, _) in _VARIABLE_METALS.items() if word == match.group(1)), None
        )
        charge = _FROM_ROMAN.get(match.group(2))
        cation = None if symbol is None or charge is None else _cation(symbol, charge)
        return None if cation is None else _salt(cation, anion)
    return None


def salt_from_formula(formula: str) -> Salt | None:
    """ "Fe2(SO4)3" → iron(III) sulfate, the cation's charge from the anion's.

    None for a formula the ion table does not hold.
    """
    cations = [*(ion.formula for ion in _FIXED_CATIONS), *_VARIABLE_METALS]
    for symbol in sorted(cations, key=len, reverse=True):
        for cation_text in (f"({symbol})", symbol):
            if not formula.startswith(cation_text):
                continue
            rest = formula[len(cation_text) :]
            count_match = re.match(r"\d*", rest)
            cation_count = int(count_match.group() or 1) if count_match else 1
            rest = rest[count_match.end() if count_match else 0 :]
            found = _anion_part(rest)
            if found is None:
                continue
            anion, anion_count = found
            total = -anion.charge * anion_count
            if total % cation_count:
                continue
            cation = _cation(symbol, total // cation_count)
            if cation is None:
                continue
            salt = _salt(cation, anion)
            # Only the lowest whole numbers are this salt's formula: Fe2O3, not Fe4O6.
            if (salt.cations, salt.anions) == (cation_count, anion_count):
                return salt
    return None


def _anion_part(text: str) -> tuple[Ion, int] | None:
    for anion in _ANIONS:
        bracketed = re.fullmatch(rf"\({re.escape(anion.formula)}\)(\d+)", text)
        if bracketed is not None and anion.polyatomic and int(bracketed.group(1)) > 1:
            return anion, int(bracketed.group(1))
        bare = re.fullmatch(rf"{re.escape(anion.formula)}(\d*)", text)
        if bare is not None and (not anion.polyatomic or not bare.group(1)):
            return anion, int(bare.group(1) or 1)
    return None
