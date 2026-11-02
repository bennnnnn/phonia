"""School coordination formulas such as ``[Co(NH3)6]Cl3``.

Crystal-field splitting and molecular-orbital diagrams stay model-only.
Ligands are a fixed monodentate/bidentate table, not a general namer. A formula
this module cannot name completely is refused rather than named approximately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.chemistry.elements import BY_SYMBOL

# token, name, charge, donor atoms
_LIGANDS: tuple[tuple[str, str, int, int], ...] = (
    ("NH3", "ammine", 0, 1),
    ("H2O", "aqua", 0, 1),
    ("NO2", "nitro", -1, 1),  # N-bonded, the usual case; the O-bonded isomer is nitrito
    ("CN", "cyanido", -1, 1),
    ("OH", "hydroxido", -1, 1),
    ("CO", "carbonyl", 0, 1),
    ("Cl", "chlorido", -1, 1),
    ("Br", "bromido", -1, 1),
    ("F", "fluorido", -1, 1),
    ("I", "iodido", -1, 1),
    ("en", "ethylenediamine", 0, 2),
    ("ox", "oxalato", -2, 2),
    ("py", "pyridine", 0, 1),
)
_PREFIX = {1: "", 2: "di", 3: "tri", 4: "tetra", 5: "penta", 6: "hexa"}
# Names that already contain a numerical prefix or are easily misread take bis/tris.
_ENCLOSED = frozenset({"en", "ox", "py"})
_ENCLOSED_PREFIX = {1: "", 2: "bis", 3: "tris", 4: "tetrakis", 5: "pentakis", 6: "hexakis"}
_COUNTER_NAMES = {
    "Cl": "chloride",
    "Br": "bromide",
    "F": "fluoride",
    "I": "iodide",
    "CN": "cyanide",
    "OH": "hydroxide",
    "NO3": "nitrate",
    "ClO4": "perchlorate",
    "SO4": "sulfate",
    "CO3": "carbonate",
    "PO4": "phosphate",
    "K": "potassium",
    "Na": "sodium",
    "NH4": "ammonium",
}
_COUNTER_CHARGE = {
    "Cl": -1,
    "Br": -1,
    "F": -1,
    "I": -1,
    "CN": -1,
    "OH": -1,
    "NO3": -1,
    "ClO4": -1,
    "SO4": -2,
    "CO3": -2,
    "PO4": -3,
    "K": 1,
    "Na": 1,
    "NH4": 1,
}
# Anionic complexes take the -ate name, which for many metals is the Latin stem.
_ANION_NAMES = {
    "Al": "aluminate",
    "Ag": "argentate",
    "Au": "aurate",
    "Cd": "cadmate",
    "Co": "cobaltate",
    "Cr": "chromate",
    "Cu": "cuprate",
    "Fe": "ferrate",
    "Hg": "mercurate",
    "Ir": "iridate",
    "Mn": "manganate",
    "Mo": "molybdate",
    "Ni": "nickelate",
    "Os": "osmate",
    "Pb": "plumbate",
    "Pd": "palladate",
    "Pt": "platinate",
    "Rh": "rhodate",
    "Ru": "ruthenate",
    "Sn": "stannate",
    "Ti": "titanate",
    "V": "vanadate",
    "W": "tungstate",
    "Zn": "zincate",
}
_P_BLOCK_METALS = frozenset({"Al", "Ga", "In", "Tl", "Sn", "Pb"})
_ION = r"(?:\([A-Za-z0-9]+\)\d*|[A-Z][A-Za-z0-9]*)"
_COMPLEX_RE = re.compile(rf"^(?P<left>{_ION})?\[(?P<inside>.+)\](?P<right>{_ION})?$")
_ION_SUFFIX = re.compile(r"^(?P<body>\[[^\]]+\])\^?(?P<digits>\d*)(?P<sign>[+-])$")


@dataclass(frozen=True)
class CoordinationComplex:
    metal: str
    oxidation_state: int
    coordination_number: int
    name: str
    ligands: tuple[str, ...] = ()
    ligand_charge: int = 0


def _split_ligands(inside: str) -> list[tuple[str, int]] | None:
    found: list[tuple[str, int]] = []
    index = 0
    tokens = sorted(_LIGANDS, key=lambda item: len(item[0]), reverse=True)
    while index < len(inside):
        if inside[index] == "(":
            end = inside.find(")", index)
            if end < 0:
                return None
            token = inside[index + 1 : end]
            index = end + 1
        else:
            token = next((name for name, *_rest in tokens if inside.startswith(name, index)), "")
            if not token:
                return None
            index += len(token)
        count_digits = ""
        while index < len(inside) and inside[index].isdigit():
            count_digits += inside[index]
            index += 1
        found.append((token, int(count_digits or "1")))
    return found


def _counter(text: str | None) -> tuple[str, int] | None:
    """``(name, total charge)`` of a counter-ion group such as ``Cl3``, ``K4`` or ``(SO4)3``."""
    if not text:
        return "", 0
    grouped = re.fullmatch(r"\((?P<ion>[A-Za-z0-9]+)\)(?P<count>\d*)", text)
    if grouped is not None:
        ion, count = grouped.group("ion"), int(grouped.group("count") or "1")
        if ion not in _COUNTER_CHARGE:
            return None
        return _COUNTER_NAMES[ion], _COUNTER_CHARGE[ion] * count
    for known in sorted(_COUNTER_CHARGE, key=len, reverse=True):
        match = re.fullmatch(rf"{known}(?P<count>\d*)", text)
        if match is not None:
            count = int(match.group("count") or "1")
            return _COUNTER_NAMES[known], _COUNTER_CHARGE[known] * count
    return None


def _is_metal(symbol: str) -> bool:
    element = BY_SYMBOL.get(symbol)
    if element is None:
        return False
    return (element.group is not None and 3 <= element.group <= 12) or symbol in _P_BLOCK_METALS


def _ligand_prefix(token: str, count: int, name: str) -> str | None:
    if token in _ENCLOSED:
        prefix = _ENCLOSED_PREFIX.get(count)
        return None if prefix is None else f"{prefix}({name})"
    prefix = _PREFIX.get(count)
    return None if prefix is None else f"{prefix}{name}"


def _analyze(formula: str, forced_charge: int | None) -> CoordinationComplex | None:
    """Oxidation state, coordination number and additive name.

    ``forced_charge`` is the charge written after the brackets (``[Fe(CN)6]3-``); without
    it the charge comes from the counter-ions. The name is built only after the charge
    is known, so an anionic complex is never named as a cation.
    """
    match = _COMPLEX_RE.match(formula.replace(" ", ""))
    if match is None:
        return None
    body = match.group("inside")
    metal_match = re.match(r"^([A-Z][a-z]?)", body)
    if metal_match is None:
        return None
    metal = metal_match.group(1)
    if not _is_metal(metal) or any(metal == name for name, *_rest in _LIGANDS):
        return None
    ligands = _split_ligands(body[len(metal) :])
    if not ligands:
        return None
    table = {name: (label, charge, donors) for name, label, charge, donors in _LIGANDS}
    if any(token not in table for token, _count in ligands):
        return None
    left = _counter(match.group("left"))
    right = _counter(match.group("right"))
    if left is None or right is None:
        return None
    left_name, left_charge = left
    right_name, right_charge = right
    if forced_charge is not None:
        if left_name or right_name:
            return None
        complex_charge = forced_charge
    else:
        complex_charge = -(left_charge + right_charge)
    ligand_charge = sum(table[token][1] * count for token, count in ligands)
    ligand_names = tuple(token for token, _count in ligands)
    coordination = sum(table[token][2] * count for token, count in ligands)
    oxidation = complex_charge - ligand_charge
    roman = _roman(oxidation)
    if roman is None:
        return None
    parts: list[str] = []
    for token, count in sorted(ligands, key=lambda item: table[item[0]][0]):
        part = _ligand_prefix(token, count, table[token][0])
        if part is None:
            return None
        parts.append(part)
    if complex_charge < 0:
        metal_name = _ANION_NAMES.get(metal)
        if metal_name is None:
            return None
    else:
        metal_name = BY_SYMBOL[metal].name.lower()
    complex_name = f"{''.join(parts)}{metal_name}({roman})"
    if left_name:
        complex_name = f"{left_name} {complex_name}"
    if right_name:
        complex_name = f"{complex_name} {right_name}"
    return CoordinationComplex(
        metal, oxidation, coordination, complex_name, ligand_names, ligand_charge
    )


def parse_complex_formula(formula: str) -> CoordinationComplex | None:
    """Parse a complex, including an ion charge written after the brackets."""
    text = formula.replace(" ", "")
    suffix = _ION_SUFFIX.match(text)
    if suffix is None:
        return _analyze(text, None)
    magnitude = int(suffix.group("digits") or "1")
    charge = magnitude if suffix.group("sign") == "+" else -magnitude
    return _analyze(suffix.group("body"), charge)


def _roman(value: int) -> str | None:
    names = {0: "0", 1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII"}
    if value < 0:
        mapped = names.get(-value)
        return None if mapped is None else f"-{mapped}"
    return names.get(value)
