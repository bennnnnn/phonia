# ruff: noqa: RUF001, RUF002, RUF003
"""Structure: electron configuration, oxidation states, VSEPR, formal charge, complexes."""

from __future__ import annotations

import math
import re

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.coordination import CoordinationComplex, parse_complex_formula
from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.nomenclature import Salt, salt_from_formula, salt_from_name
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.display import inp, num, verified
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.species import parse_species
from app.modules.chemistry.structure import lewis_structure, oxidation_states
from app.services.solving import SolveServiceError

# "3s2" in the element table: a subshell and the electrons it holds.
_SUBSHELL = re.compile(r"(?<![A-Za-z0-9])(\d[spdf])(\d{1,2})(?![A-Za-z0-9])")


def _configuration(table_text: str) -> str:
    """The table's ``[Ne] 3s2 3p4`` as ASCII notation, ``[Ne] 3s^2 3p^4``.

    The electron count is a superscript, so ``notation.typeset`` shows ``3s² 3p⁴``.
    """
    return _SUBSHELL.sub(r"\1^\2", table_text)


def solve_electron_configuration(intent: ChemistryIntent) -> ChemistryResult:
    element = BY_SYMBOL.get(intent.target or "")
    if element is None:
        raise SolveServiceError("an electron configuration needs an element")
    configuration = _configuration(element.configuration)
    return verified(
        "Verified electron configuration",
        (f"{element.name} ({element.symbol})", f"Z = {element.number}"),
        "Ground-state electron configuration of the neutral atom",
        *stated("electron_configuration"),
        (f"{element.number} electrons",),
        f"{element.symbol}: {configuration}",
        configuration,
    )


def _signed(value: int) -> str:
    if value > 0:
        return f"+{value}"
    return str(value)


def solve_oxidation_state(intent: ChemistryIntent) -> ChemistryResult:
    formula = intent.formula or ""
    states = oxidation_states(formula)
    species = parse_species(formula, coefficient_already_removed=True)
    if states is None or species is None:
        raise SolveServiceError("oxidation states are ambiguous")
    shown = "\n".join(f"{element} = {_signed(states[element])}" for element in species.composition)
    terms = " + ".join(
        f"({_signed(states[element])})({count})" for element, count in species.composition.items()
    )
    return verified(
        "Verified oxidation states",
        (formula,),
        "Oxidation states",
        *stated("oxidation_state"),
        (f"sum = {terms} = {species.charge}",),
        shown,
        shown,
    )


def solve_vsepr(intent: ChemistryIntent) -> ChemistryResult:
    formula = intent.formula or ""
    if "," in formula:
        return _vsepr_pair(formula)
    structure = lewis_structure(formula)
    if structure is None:
        raise SolveServiceError("no unique central-atom VSEPR structure")
    polarity = "polar" if structure.polar else "nonpolar"
    bonded = len(structure.terminal_elements)
    lone = structure.central_lone_pairs
    lines = [
        f"geometry: {structure.geometry}, {structure.bond_angle}",
        f"polarity: {polarity}",
        f"hybridization: {structure.hybridization}",
        f"central formal charge: {structure.central_formal_charge}",
    ]
    if (
        structure.electron_geometry != structure.geometry
        or structure.ideal_angle != structure.bond_angle
    ):
        lines.append(
            f"electron geometry: {structure.electron_geometry}, ideal angle {structure.ideal_angle}"
        )
    if structure.resonance_forms > 1:
        lines.append(f"resonance forms: {structure.resonance_forms}")
    shown = "\n".join(lines)
    return verified(
        "Verified VSEPR",
        (formula, f"valence electrons = {structure.electrons}"),
        "Geometry, polarity, and hybridization",
        *stated("vsepr"),
        (
            f"central atom {structure.central}: {bonded} bonded atoms, {lone} lone pairs",
            f"steric number = {bonded} + {lone} = {bonded + lone}",
            f"electron geometry {structure.electron_geometry}; "
            f"molecular geometry {structure.geometry}",
        ),
        shown,
        shown,
    )


def _vsepr_pair(written: str) -> ChemistryResult:
    """Two molecules' shapes, each from its own Lewis structure: "why is water bent but CO2
    linear" names "H2O, CO2". The rows say what makes each shape; the answer lists both."""
    formulas = [formula.strip() for formula in written.split(",")]
    structures = [lewis_structure(formula) for formula in formulas]
    if len(formulas) != 2 or len(set(formulas)) != 2:
        raise SolveServiceError("a VSEPR comparison names two different molecules")
    given: list[str] = []
    rows: list[str] = []
    answers: list[str] = []
    for formula, structure in zip(formulas, structures, strict=True):
        if structure is None:
            raise SolveServiceError("no unique central-atom VSEPR structure")
        bonded = len(structure.terminal_elements)
        lone = structure.central_lone_pairs
        polarity = "polar" if structure.polar else "nonpolar"
        given.append(f"{formula}: valence electrons = {structure.electrons}")
        rows.extend(
            (
                f"{formula}: central atom {structure.central}: {bonded} bonded atoms, "
                f"{lone} lone pairs",
                f"{formula}: steric number = {bonded} + {lone} = {bonded + lone}",
                f"{formula}: electron geometry {structure.electron_geometry}; "
                f"molecular geometry {structure.geometry}",
            )
        )
        answers.append(f"{formula}: {structure.geometry}, {structure.bond_angle}, {polarity}")
    shown = "\n".join(answers)
    return verified(
        "Verified VSEPR",
        given,
        "Geometry and polarity of each molecule",
        *stated("vsepr"),
        rows,
        shown,
        shown,
    )


def solve_formal_charge(intent: ChemistryIntent) -> ChemistryResult:
    valence = intent.params.get("valence")
    nonbonding = intent.params.get("nonbonding")
    bonding = intent.params.get("bonding")
    if valence is None or nonbonding is None or bonding is None:
        raise SolveServiceError("formal charge needs valence, nonbonding, and bonding electrons")
    if bonding % 2:
        raise SolveServiceError("bonding electrons must be even")
    value = valence - nonbonding - bonding / 2
    shown = f"FC = {num(value)}"
    return verified(
        "Verified formal charge",
        (
            f"valence electrons V = {inp(valence)}",
            f"nonbonding electrons N = {inp(nonbonding)}",
            f"bonding electrons B = {inp(bonding)}",
        ),
        "Formal charge",
        *stated("formal_charge"),
        (f"FC = {inp(valence)} − {inp(nonbonding)} − {inp(bonding)}/2",),
        shown,
        shown,
    )


def solve_coordination(intent: ChemistryIntent) -> ChemistryResult:
    complex_ = parse_complex_formula(intent.formula or "")
    if complex_ is None:
        raise SolveServiceError("coordination formula was not recognized")
    complex_charge = complex_.oxidation_state + complex_.ligand_charge
    shown = "\n".join(
        (
            f"name: {complex_.name}",
            f"{complex_.metal} oxidation state: {_signed(complex_.oxidation_state)}",
            f"coordination number: {complex_.coordination_number}",
        )
    )
    return verified(
        "Verified coordination complex",
        (intent.formula or "",),
        "Oxidation state, coordination number, and name",
        *stated("coordination_complex"),
        (
            f"complex charge = {_signed(complex_charge)}",
            f"ligand charges = {_signed(complex_.ligand_charge)}",
            f"{complex_.metal} = ({_signed(complex_charge)}) − ({_signed(complex_.ligand_charge)})"
            f" = {_signed(complex_.oxidation_state)}",
            f"coordination number = donor atoms of {' + '.join(complex_.ligands)} = "
            f"{complex_.coordination_number}",
        ),
        shown,
        shown,
    )


# Spectrochemical classes for octahedral d4–d7, where the spin state changes the answer.
_WEAK_FIELD = frozenset({"F", "Cl", "Br", "I", "H2O", "OH"})


_STRONG_FIELD = frozenset({"CN", "CO"})


_INTERMEDIATE_FIELD = frozenset({"NH3", "en", "NO2"})


# Valence d+s count for the first-row metals. d electrons = this minus oxidation state.
_D_COUNT = {
    "Sc": 3,
    "Ti": 4,
    "V": 5,
    "Cr": 6,
    "Mn": 7,
    "Fe": 8,
    "Co": 9,
    "Ni": 10,
    "Cu": 11,
    "Zn": 12,
}


def solve_crystal_field(intent: ChemistryIntent) -> ChemistryResult:
    complex_ = parse_complex_formula(intent.formula or "")
    if complex_ is None:
        raise SolveServiceError("coordination formula was not recognized")
    valence = _D_COUNT.get(complex_.metal)
    if valence is None:
        raise SolveServiceError("crystal field is limited to the first-row metals")
    geometry = _crystal_geometry(complex_.coordination_number, intent.geometry)
    electrons = valence - complex_.oxidation_state
    if electrons < 0 or electrons > 10:
        raise SolveServiceError("d-electron count is outside 0 to 10")
    if geometry == "octahedral":
        low_spin, reason = _octahedral_low_spin(complex_, electrons)
        unpaired = _unpaired(electrons, low_spin=low_spin)
        spin = "low-spin" if low_spin else "high-spin"
    elif geometry == "tetrahedral":
        unpaired = _unpaired(electrons, low_spin=False)
        spin = "high-spin"
        reason = "the tetrahedral splitting is small, so electrons stay unpaired"
    else:
        # Square planar uses the large dx2-y2 gap: pair below it before occupying it.
        unpaired = _SQUARE_PLANAR_UNPAIRED[electrons]
        spin = "low-spin"
        reason = "square planar fills dz2, dxz/dyz and dxy before the high dx2-y2 orbital"
    moment = math.sqrt(unpaired * (unpaired + 2))
    label = "square planar" if geometry == "square_planar" else geometry
    shown = f"{label} {spin} d{electrons}, {unpaired} unpaired, μ = {num(moment)} BM"
    note = f"geometry = {label}"
    working = (
        f"{complex_.metal} oxidation state {complex_.oxidation_state:+d}, so "
        f"d electrons = {valence} − ({complex_.oxidation_state}) = {electrons}",
        f"coordination number {complex_.coordination_number} gives {label}; {reason}",
        f"unpaired electrons n = {unpaired}",
        f"μ = √({unpaired}({unpaired} + 2)) = {num(moment)} BM",
    )
    return verified(
        "Verified crystal field",
        (intent.formula or "", note),
        "Spin state, unpaired electrons, and spin-only magnetic moment",
        *stated("crystal_field"),
        working,
        shown,
        shown,
    )


def _octahedral_low_spin(complex_: CoordinationComplex, electrons: int) -> tuple[bool, str]:
    """Spin state of an octahedral d4–d7 complex and why, or a refusal when undecided.

    Only a ligand set that is all weak-field (halide, water, hydroxide) or all strong-field
    (CN⁻, CO) decides it. NH3, en and NO2⁻ sit in the middle: [Co(NH3)6]³⁺ is low-spin but
    [Fe(NH3)6]²⁺ is high-spin, so those need the metal, and everything else declines.
    """
    if electrons not in {4, 5, 6, 7}:
        # d1–d3 and d8–d10 have the same unpaired count in either spin state
        return False, "the unpaired count is the same in a high- or low-spin complex"
    ligands = set(complex_.ligands)
    if not ligands:
        raise SolveServiceError("the ligands are needed to choose the spin state")
    if ligands <= _WEAK_FIELD:
        return False, f"{', '.join(sorted(ligands))} are weak-field ligands, so the gap is small"
    if ligands <= _STRONG_FIELD:
        return True, f"{', '.join(sorted(ligands))} are strong-field ligands, so the gap is large"
    if (
        complex_.metal == "Co"
        and complex_.oxidation_state == 3
        and ligands <= _STRONG_FIELD | _INTERMEDIATE_FIELD
    ):
        return True, "Co(III) with these ligands has a large gap"
    raise SolveServiceError("the spin state of that ligand set depends on the metal")


# Unpaired electrons for square planar filling:
# dz2, then dxz/dyz, then dxy, then dx2-y2. d8 is diamagnetic.
_SQUARE_PLANAR_UNPAIRED = (0, 1, 0, 1, 2, 1, 0, 1, 0, 1, 0)


def _crystal_geometry(coordination_number: int, stated: str | None) -> str:
    if coordination_number == 6:
        if stated in {None, "octahedral"}:
            return "octahedral"
        raise SolveServiceError("coordination number 6 is octahedral, not the stated geometry")
    if coordination_number == 4:
        if stated == "tetrahedral":
            return "tetrahedral"
        if stated == "square_planar":
            return "square_planar"
        raise SolveServiceError(
            "coordination number 4 needs an explicit tetrahedral or square planar geometry"
        )
    raise SolveServiceError("crystal field needs coordination number 4 or 6")


def _unpaired(electrons: int, *, low_spin: bool) -> int:
    if not low_spin:
        return electrons if electrons <= 5 else 10 - electrons
    if electrons <= 3:
        return electrons
    if electrons <= 6:
        return 6 - electrons
    if electrons <= 8:
        return electrons - 6
    return 10 - electrons


def _valence(symbol: str) -> int:
    """A main-group atom's valence electrons from its group; helium has two."""
    element = BY_SYMBOL.get(symbol)
    if element is None or element.group is None or 3 <= element.group <= 12:
        raise SolveServiceError(f"{symbol} is not a main-group element")
    if symbol == "He":
        return 2
    return element.group if element.group <= 2 else element.group - 10


def solve_valence_electrons(intent: ChemistryIntent) -> ChemistryResult:
    formula = intent.formula or ""
    species = parse_species(formula, coefficient_already_removed=True)
    if species is None or not species.composition:
        raise SolveServiceError("valence electrons need an element or a formula")
    rows = []
    total = 0
    for symbol, count in species.composition.items():
        each = _valence(symbol)
        group = BY_SYMBOL[symbol].group
        total += count * each
        rows.append(
            f"{symbol}: group {group}, {each} valence electrons"
            + ("" if count == 1 else f" × {count} = {count * each}")
        )
    if species.charge:
        total -= species.charge
        rows.append(f"charge {_signed(species.charge)}: {_signed(-species.charge)} electrons")
    if total <= 0:
        raise SolveServiceError("that species has no valence electrons to count")
    single = len(species.composition) == 1 and sum(species.composition.values()) == 1
    if not single:
        rows.append(f"total = {total}")
    shown = f"{formula}: {total} valence electrons"
    return verified(
        "Verified valence electrons",
        (f"{'Element' if single else 'Formula'} = {formula}",),
        "Valence electrons",
        *stated("valence_electrons"),
        tuple(rows),
        shown,
        str(total),
    )


def _charge(value: int) -> str:
    return f"{'+' if value > 0 else '−'}{abs(value)}"


def _salt_rows(salt: Salt) -> tuple[str, ...]:
    cation, anion = salt.cation, salt.anion
    return (
        f"cation {cation.formula} ({cation.name}): charge {_charge(cation.charge)}",
        f"anion {anion.formula} ({anion.name}): charge {_charge(anion.charge)}",
        f"{salt.cations} × ({_charge(cation.charge)}) + {salt.anions} × ({_charge(anion.charge)})"
        " = 0",
    )


def solve_ionic_formula(intent: ChemistryIntent) -> ChemistryResult:
    salt = salt_from_name(intent.target or "")
    if salt is None:
        raise SolveServiceError("that name is not a salt of the ion table")
    return verified(
        "Verified ionic formula",
        (f"Name = {salt.name}",),
        "Formula",
        *stated("ionic_formula"),
        _salt_rows(salt),
        f"{salt.name}: {salt.formula}",
        salt.formula,
    )


def solve_ionic_name(intent: ChemistryIntent) -> ChemistryResult:
    salt = salt_from_formula(intent.formula or "")
    if salt is None:
        raise SolveServiceError("that formula is not a salt of the ion table")
    return verified(
        "Verified ionic name",
        (f"Formula = {salt.formula}",),
        "Name",
        *stated("ionic_name"),
        _salt_rows(salt),
        f"{salt.formula}: {salt.name}",
        salt.name,
    )
