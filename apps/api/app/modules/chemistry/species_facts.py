"""What a chemistry question means by the substances it names.

A question says "water", "table salt" or "HCl"; a law needs a formula, and some laws need
what the substance does in water: a strong acid gives up all its protons, a weak acid needs
its Ka stated, and a salt splits into i ions. These are school facts, not looked up.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.modules.chemistry.elements import BY_SYMBOL, ELEMENTS
from app.modules.chemistry.formula import parse_formula

# Common names a school question uses for a compound.
NAMED_COMPOUNDS: dict[str, str] = {
    "water": "H2O",
    "table salt": "NaCl",
    "sodium chloride": "NaCl",
    "potassium chloride": "KCl",
    "calcium chloride": "CaCl2",
    "magnesium chloride": "MgCl2",
    "ammonia": "NH3",
    "methane": "CH4",
    "ethane": "C2H6",
    "propane": "C3H8",
    "butane": "C4H10",
    "octane": "C8H18",
    "methanol": "CH3OH",
    "ethanol": "C2H5OH",
    "glucose": "C6H12O6",
    "sucrose": "C12H22O11",
    "sugar": "C12H22O11",
    "urea": "CO(NH2)2",
    "carbon dioxide": "CO2",
    "carbon monoxide": "CO",
    "sulfur dioxide": "SO2",
    "sulphur dioxide": "SO2",
    # A diatomic element named as the gas is its molecule.
    "hydrogen gas": "H2",
    "nitrogen gas": "N2",
    "oxygen gas": "O2",
    "fluorine gas": "F2",
    "chlorine gas": "Cl2",
    "hydrochloric acid": "HCl",
    "hydrobromic acid": "HBr",
    "hydroiodic acid": "HI",
    "nitric acid": "HNO3",
    "perchloric acid": "HClO4",
    "sulfuric acid": "H2SO4",
    "sulphuric acid": "H2SO4",
    "acetic acid": "CH3COOH",
    "ethanoic acid": "CH3COOH",
    "formic acid": "HCOOH",
    "hydrofluoric acid": "HF",
    "nitrous acid": "HNO2",
    "hydrocyanic acid": "HCN",
    "sodium hydroxide": "NaOH",
    "potassium hydroxide": "KOH",
    "lithium hydroxide": "LiOH",
    "calcium hydroxide": "Ca(OH)2",
    "barium hydroxide": "Ba(OH)2",
    "ammonium chloride": "NH4Cl",
    "sodium acetate": "CH3COONa",
    "potassium acetate": "CH3COOK",
}

# Protons a strong acid gives up, and hydroxides a strong base releases, per formula unit.
STRONG_ACIDS: dict[str, int] = {
    "HCl": 1,
    "HBr": 1,
    "HI": 1,
    "HNO3": 1,
    "HClO4": 1,
    "HClO3": 1,
}
STRONG_BASES: dict[str, int] = {
    "LiOH": 1,
    "NaOH": 1,
    "KOH": 1,
    "RbOH": 1,
    "CsOH": 1,
    "Ca(OH)2": 2,
    "Sr(OH)2": 2,
    "Ba(OH)2": 2,
}
# Weak electrolytes: a pH needs the stated Ka or Kb.

WEAK_ACIDS = frozenset({"CH3COOH", "HCOOH", "HF", "HNO2", "HCN", "HClO", "C6H5COOH"})
WEAK_BASES = frozenset({"NH3", "CH3NH2", "C5H5N", "C6H5NH2"})
# Protons an acid gives up, and hydroxides a base takes them with, in a full neutralization.
NEUTRALIZING_ACIDS: dict[str, int] = {**STRONG_ACIDS, "H2SO4": 2, **dict.fromkeys(WEAK_ACIDS, 1)}
NEUTRALIZING_BASES: dict[str, int] = {**STRONG_BASES, **dict.fromkeys(WEAK_BASES, 1)}
# The conjugate base of a weak acid, as the salt a buffer is made with.
CONJUGATE_SALTS = frozenset({"CH3COONa", "CH3COOK", "HCOONa", "NaF", "NaNO2", "NaCN", "NH4Cl"})
# Particles one dissolved formula unit gives, for an ideal colligative property.
VAN_T_HOFF: dict[str, int] = {
    "C6H12O6": 1,
    "C12H22O11": 1,
    "CO(NH2)2": 1,
    "C2H5OH": 1,
    "NaCl": 2,
    "KCl": 2,
    "KBr": 2,
    "NaBr": 2,
    "KNO3": 2,
    "NaNO3": 2,
    "CaCl2": 3,
    "MgCl2": 3,
    "Na2SO4": 3,
    "K2SO4": 3,
    "AlCl3": 4,
    "FeCl3": 4,
}

# An element named in words: "zinc", "copper" (and the American aluminum).
ELEMENT_NAMES: dict[str, str] = {
    **{element.name.lower(): element.symbol for element in ELEMENTS},
    "aluminum": "Al",
    "sulphur": "S",
}


def element_symbol(token: str) -> str | None:
    """An element named by symbol ("O", case as written) or in words ("oxygen")."""
    if token in BY_SYMBOL:
        return token
    return ELEMENT_NAMES.get(token.lower())


# A formula as a question writes it: capitals, digits and brackets, nothing glued on.
# A hydrate (CuSO4·5H2O, its dot written by ``input_text``) is one formula.
_FORMULA_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9()]*(?:\u00b7\d{0,2}[A-Z][A-Za-z0-9()]*)*)"
    r"(?![A-Za-z0-9(\u00b7])"
)
# An ion written with its charge: "Cu2+", "Fe3+".
_ION = re.compile(r"(?<![A-Za-z0-9])([A-Z][a-z]?)(\d?)\+")


@lru_cache(maxsize=1)
def _name_pattern() -> re.Pattern[str]:
    names = sorted(NAMED_COMPOUNDS, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(name) for name in names) + r")\b", re.IGNORECASE)


def is_formula(token: str) -> bool:
    """A formula of real elements: a compound ("HCl", "NH3") or a molecule of one ("O2").

    Never "Find" or "Kf", and never a bare symbol ("C", "K"): that is an element or a unit.
    """
    atoms = parse_formula(token)
    if not atoms or not all(symbol in BY_SYMBOL for symbol in atoms):
        return False
    return len(atoms) >= 2 or next(iter(atoms.values())) >= 2


def named_species(text: str) -> tuple[str, ...]:
    """The compounds a question names, as formulas, in the order it names them."""
    found: list[tuple[int, str]] = []
    for match in _name_pattern().finditer(text):
        found.append((match.start(), NAMED_COMPOUNDS[match.group(1).lower()]))
    for match in _FORMULA_TOKEN.finditer(text):
        if is_formula(match.group(1)):
            found.append((match.start(), match.group(1)))
    ordered: list[str] = []
    for _, formula in sorted(found):
        if formula not in ordered:
            ordered.append(formula)
    return tuple(ordered)


def named_elements(text: str) -> tuple[str, ...]:
    """The elements a question names in words ("zinc and copper"), as symbols, in order."""
    words = re.findall(r"[a-z]+", text.lower())
    symbols: list[str] = []
    for word in words:
        symbol = ELEMENT_NAMES.get(word)
        if symbol is not None and symbol not in symbols:
            symbols.append(symbol)
    return tuple(symbols)


def ion_charge(text: str, symbol: str) -> int | None:
    """The charge of the named ion of one element ("from Cu2+" is 2), if the question writes it."""
    for match in _ION.finditer(text):
        if match.group(1) == symbol:
            return int(match.group(2) or 1)
    return None


def formula_spans(text: str) -> list[tuple[int, int]]:
    """Where formulas and charged ions are written, so their digits are not read as numbers."""
    spans = [match.span(1) for match in _FORMULA_TOKEN.finditer(text) if is_formula(match.group(1))]
    spans.extend(match.span() for match in _ION.finditer(text) if match.group(1) in BY_SYMBOL)
    return sorted(spans)


def without_formulas(text: str) -> str:
    """The text with its formulas and ions blanked, so H2's 2 is not a stated number."""
    kept = list(text)
    for start, end in formula_spans(text):
        kept[start:end] = " " * (end - start)
    return "".join(kept)


# Anions a sparingly soluble salt releases, with their charge.
_SALT_ANIONS: dict[str, int] = {
    "F": -1,
    "Cl": -1,
    "Br": -1,
    "I": -1,
    "OH": -1,
    "IO3": -1,
    "O": -2,
    "S": -2,
    "SO4": -2,
    "SO3": -2,
    "CO3": -2,
    "CrO4": -2,
    "C2O4": -2,
    "PO4": -3,
    "AsO4": -3,
}
_NONMETALS = frozenset({"H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Se", "Br", "I"})
# A salt as cation then anion: "AgCl", "CaF2", "Ag2CrO4", "Ca3(PO4)2".
_SALT = re.compile(
    r"(?P<cation>[A-Z][a-z]?)(?P<cations>\d*)"
    r"(?:\((?P<group>[A-Za-z0-9]+)\)(?P<groups>\d+)|(?P<anion>[A-Z][A-Za-z0-9]*))"
)
_MONATOMIC = re.compile(r"(?P<symbol>[A-Z][a-z]?)(?P<count>\d*)")


def _ion_label(symbol: str, charge: int) -> str:
    """ "Ca2+", "F-", "SO4^2-": an anion of charge two or more keeps a caret ("O2-" is O₂⁻)."""
    sign = "+" if charge > 0 else "-"
    size = abs(charge)
    if size == 1:
        return f"{symbol}{sign}"
    return f"{symbol}{size}{sign}" if charge > 0 else f"{symbol}^{size}{sign}"


def dissolution_equation(formula: str) -> str | None:
    """How a sparingly soluble salt dissolves: "CaF2" is "CaF2(s) -> Ca2+ + F-".

    The cation's charge is the one that makes the salt neutral, so "Fe(OH)3" is Fe3+.
    None for anything that is not a metal cation with one known anion.
    """
    match = _SALT.fullmatch(formula)
    if match is None or match.group("cation") not in BY_SYMBOL:
        return None
    cation = match.group("cation")
    if cation in _NONMETALS:
        return None
    cations = int(match.group("cations") or 1)
    if match.group("group") is not None:
        anion, anions = match.group("group"), int(match.group("groups"))
    elif match.group("anion") in _SALT_ANIONS:
        anion, anions = match.group("anion"), 1
    else:
        single = _MONATOMIC.fullmatch(match.group("anion"))
        if single is None:
            return None
        anion, anions = single.group("symbol"), int(single.group("count") or 1)
    charge = _SALT_ANIONS.get(anion)
    if charge is None or (anions * -charge) % cations:
        return None
    cation_charge = anions * -charge // cations
    if not 1 <= cation_charge <= 4:
        return None
    return f"{formula}(s) -> {_ion_label(cation, cation_charge)} + {_ion_label(anion, charge)}"
