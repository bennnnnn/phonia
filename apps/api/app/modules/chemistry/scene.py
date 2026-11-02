"""Server-owned teaching scenes for balance and VSEPR.

Stoichiometry, ICE, titration, and galvanic scenes are built inside the
solver that already computed those numbers. This module does not parse
formatted answers or run a second calculation.
"""

from __future__ import annotations

from dataclasses import replace

from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.lewis import lewis_structure
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.schemas.scene import (
    BalanceRow,
    BalanceScene,
    ChargeTally,
    ChemistryScene,
    VseprScene,
)
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.species import parse_species


def attach_scene(intent: ChemistryIntent, result: ChemistryResult) -> ChemistryResult:
    if result.scene is not None:
        return result
    if intent.chemistry_op == "vsepr" and intent.formula and "," in intent.formula:
        scenes = [_vsepr(formula.strip()) for formula in intent.formula.split(",")]
        drawn = [scene for scene in scenes if scene is not None]
        if len(drawn) != len(scenes) or not drawn:
            return result
        return replace(result, scene=drawn[0], more_scenes=tuple(drawn[1:]))
    scene = _scene(intent)
    if scene is None:
        return result
    return replace(result, scene=scene)


def _scene(intent: ChemistryIntent) -> ChemistryScene | None:
    op = intent.chemistry_op
    if op == "balance" and intent.equation:
        return _balance(intent.equation)
    if op == "vsepr" and intent.formula:
        return _vsepr(intent.formula)
    return None


def _tally(side: dict[str, int]) -> tuple[dict[str, int], int] | None:
    atoms: dict[str, int] = {}
    charge = 0
    for label, coefficient in side.items():
        species = parse_species(label, coefficient_already_removed=True)
        if species is None:
            return None
        charge += species.charge * coefficient
        for element, count in species.composition.items():
            atoms[element] = atoms.get(element, 0) + count * coefficient
    return atoms, charge


def _balance(equation: str) -> BalanceScene | None:
    balanced = balance_equation(equation)
    if not balanced.balanced:
        return None
    left = _tally(balanced.reactants)
    right = _tally(balanced.products)
    if left is None or right is None:
        return None
    left_atoms, left_charge = left
    right_atoms, right_charge = right
    elements = list(dict.fromkeys((*left_atoms, *right_atoms)))
    rows = [
        BalanceRow(
            element=element, left=left_atoms.get(element, 0), right=right_atoms.get(element, 0)
        )
        for element in elements
    ]
    return BalanceScene(
        title="Atom tally",
        rows=rows,
        charge=ChargeTally(left=left_charge, right=right_charge),
    )


def _vsepr(formula: str) -> VseprScene | None:
    structure = lewis_structure(formula)
    if structure is None:
        return None
    return VseprScene(
        title=formula,
        central=structure.central,
        terminals=list(structure.terminal_elements),
        lone_pairs=structure.central_lone_pairs,
        geometry=structure.geometry,
        bond_angle=structure.bond_angle,
        electron_geometry=structure.electron_geometry,
        ideal_angle=structure.ideal_angle,
    )
