# ruff: noqa: RUF001, RUF002
"""Spectroscopy: Beer–Lambert, IR and NMR tables, splitting, and the molecular ion."""

from __future__ import annotations

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.organic import organic_facts
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.smiles import most_common_isotope
from app.modules.chemistry.solvers.display import inp, num, verified
from app.modules.chemistry.solvers.relation import solve_paired
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.stoichiometry import monoisotopic_mass
from app.services.solving import SolveServiceError

_BEER = {
    "absorbance": ("A", "", "A = {}"),
    "epsilon": ("ε", "L/(mol·cm)", "ε = {} L/(mol·cm)"),
    "path": ("b", "cm", "b = {} cm"),
    "concentration": ("c", "mol/L", "c = {} mol/L"),
}


def solve_beer_lambert(intent: ChemistryIntent) -> ChemistryResult:
    values = {name: intent.params.get(name) for name in _BEER}
    missing = [name for name, value in values.items() if value is None]
    if len(missing) != 1:
        raise SolveServiceError("exactly one Beer–Lambert variable must be unknown")
    known_values = [value for value in values.values() if value is not None]
    if any(value < 0 for value in known_values) or any(
        values[name] == 0 for name in ("epsilon", "path", "concentration")
    ):
        raise SolveServiceError("Beer–Lambert inputs must be physically valid")
    unknown = missing[0]
    symbol, unit, _ = _BEER[unknown]
    known = {_BEER[name][0]: value for name, value in values.items() if value is not None}
    result, rearranged, substitution = solve_paired(known, symbol, ["A"], ["ε", "b", "c"])
    value = f"{num(result)}{f' {unit}' if unit else ''}"
    given = tuple(
        _BEER[name][2].format(inp(amount)) for name, amount in values.items() if amount is not None
    )
    return verified(
        "Verified Beer–Lambert calculation",
        given,
        symbol,
        *stated("beer_lambert"),
        (rearranged, substitution),
        f"{symbol} = {value}",
        value,
    )


# Textbook correlation ranges. A peak lists every group that contains it.
_IR: dict[str, tuple[tuple[str, int, int], ...]] = {
    "alcohol": (("O–H", 3200, 3600),),
    "phenol": (("O–H", 3200, 3600),),
    "carboxylic acid": (("O–H", 2500, 3300), ("C=O", 1700, 1725)),
    "aldehyde": (("C=O", 1720, 1740),),
    "ketone": (("C=O", 1705, 1725),),
    "ester": (("C=O", 1735, 1750),),
    "amide": (("C=O", 1630, 1690),),
    "alkene": (("C=C", 1620, 1680),),
    "alkyne": (("C≡C", 2100, 2260),),
    "nitrile": (("C≡N", 2210, 2260),),
    "amine": (("N–H", 3300, 3500),),
}


_NMR: dict[str, tuple[str, float, float]] = {
    "alkyl": ("C–H", 0.7, 1.3),
    "alcohol": ("H–C–O", 3.2, 4.5),
    "ether": ("H–C–O", 3.2, 4.5),
    "ester": ("H–C–O", 3.2, 4.5),
    "alkene": ("=C–H", 4.5, 6.5),
    "aromatic": ("Ar–H", 6.5, 8.5),
    "aldehyde": ("CHO", 9.0, 10.0),
    "carboxylic acid": ("COOH", 10.0, 13.0),
    "amine": ("N–H", 0.5, 5.0),
}


_SPLITTING = {
    1: "singlet",
    2: "doublet",
    3: "triplet",
    4: "quartet",
    5: "quintet",
    6: "sextet",
    7: "septet",
}


def solve_ir_ranges(intent: ChemistryIntent) -> ChemistryResult:
    return _ranges(intent, kind="ir", operation="ir_ranges")


def solve_nmr_ranges(intent: ChemistryIntent) -> ChemistryResult:
    return _ranges(intent, kind="nmr", operation="nmr_ranges")


def solve_ir_peak(intent: ChemistryIntent) -> ChemistryResult:
    return _peak(intent, kind="ir", operation="ir_peak")


def solve_nmr_peak(intent: ChemistryIntent) -> ChemistryResult:
    return _peak(intent, kind="nmr", operation="nmr_peak")


def solve_nmr_splitting(intent: ChemistryIntent) -> ChemistryResult:
    neighbors = intent.params.get("neighbors")
    if (
        neighbors is None
        or neighbors < 0
        or neighbors != int(neighbors)
        or int(neighbors) + 1 not in _SPLITTING
    ):
        raise SolveServiceError("NMR splitting needs a neighbor count from 0 to 6")
    lines = int(neighbors) + 1
    shown = f"n+1 = {lines} ({_SPLITTING[lines]})"
    return verified(
        "Verified NMR splitting",
        (f"neighbors = {int(neighbors)}",),
        "Splitting",
        *stated("nmr_splitting"),
        (f"lines = {int(neighbors)} + 1 = {lines}",),
        shown,
        shown,
    )


def _halogen_pattern(counts: dict[str, int]) -> str | None:
    chlorine, bromine = counts.get("Cl", 0), counts.get("Br", 0)
    if chlorine == 1 and not bromine:
        return "one Cl adds an M+2 peak about a third the height of M+ (35Cl : 37Cl = 3 : 1)"
    if bromine == 1 and not chlorine:
        return "one Br adds an M+2 peak about as tall as M+ (79Br : 81Br = 1 : 1)"
    if chlorine or bromine:
        return "several Cl or Br atoms give M+2, M+4, ... peaks"
    return None


def solve_molecular_ion(intent: ChemistryIntent) -> ChemistryResult:
    formula = intent.formula or ""
    try:
        peak = monoisotopic_mass(formula)
    except (ValueError, SolveServiceError) as exc:
        raise SolveServiceError("molecular ion needs a formula or SMILES") from exc
    shown = f"M+ = {peak.exact:.4f} (nominal m/z {peak.nominal})"
    substitution = []
    for symbol, count in peak.counts.items():
        isotope = most_common_isotope(symbol)
        if isotope is not None:
            exact, number = isotope
            substitution.append(
                f"{symbol}: {count} × {exact:.4f} = {count * exact:.4f} (nominal {count * number})"
            )
    substitution.append(f"M+ = {peak.exact:.4f}, nominal m/z = {peak.nominal}")
    pattern = _halogen_pattern(peak.counts)
    if pattern is not None:
        substitution.append(pattern)
    return verified(
        "Verified molecular ion",
        (formula,),
        "Molecular ion m/z",
        *stated("molecular_ion"),
        substitution,
        shown,
        shown,
        verbatim=True,
    )


def _ranges(intent: ChemistryIntent, *, kind: str, operation: str) -> ChemistryResult:
    facts = organic_facts(intent.formula or "")
    if facts is None or not facts.groups:
        raise SolveServiceError("no functional group recognized")
    lines = _lines_for(facts.groups, kind=kind)
    if not lines:
        raise SolveServiceError("no correlation range for those groups")
    shown = "\n".join(lines)
    title = "IR ranges" if kind == "ir" else "1H NMR ranges"
    return verified(
        f"Verified {title}",
        (facts.canonical_smiles,),
        title,
        *stated(operation),
        (f"groups found: {', '.join(facts.groups)}", "look up each group's textbook range"),
        shown,
        shown,
        verbatim=True,
    )


def _peak(intent: ChemistryIntent, *, kind: str, operation: str) -> ChemistryResult:
    value = intent.params.get("peak")
    if value is None:
        raise SolveServiceError("a peak position is required")
    groups = []
    working = []
    unit = "cm⁻¹" if kind == "ir" else "ppm"
    if kind == "ir":
        for name, bands in _IR.items():
            for label, low, high in bands:
                if low <= value <= high:
                    groups.append(name)
                    working.append(f"{inp(value)} is within {name} {label} {low}–{high} {unit}")
                    break
    else:
        for name, (label, low_ppm, high_ppm) in _NMR.items():
            if low_ppm <= value <= high_ppm:
                groups.append(name)
                span = f"{num(low_ppm)}–{num(high_ppm)}"
                working.append(f"{inp(value)} is within {name} {label} {span} {unit}")
    if not groups:
        raise SolveServiceError("no functional group contains that peak")
    shown = "\n".join(groups)
    return verified(
        "Verified peak groups",
        (f"peak = {inp(value)} {unit}",),
        "Groups whose range contains the peak",
        *stated(operation),
        working,
        shown,
        shown,
        verbatim=True,
    )


def _lines_for(groups: tuple[str, ...], *, kind: str) -> list[str]:
    lines: list[str] = []
    for group in groups:
        if kind == "ir":
            for label, low, high in _IR.get(group, ()):
                lines.append(f"{group} {label} {low}–{high} cm⁻¹")
        else:
            band = _NMR.get(group)
            if band is not None:
                name, low_ppm, high_ppm = band
                lines.append(f"{group} {name} {num(low_ppm)}–{num(high_ppm)} ppm")
    return lines
