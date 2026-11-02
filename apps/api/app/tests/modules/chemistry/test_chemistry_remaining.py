"""Scenes, catalog lock, and the closed calculations past the school table."""

from __future__ import annotations

import json
from typing import get_args
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.catalog import CATALOG
from app.modules.chemistry.context import build_chemistry_augmentation
from app.modules.chemistry.direct import format_direct_chemistry_reply
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.notation import typeset_json
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.schemas.intent import ChemistryKind
from app.modules.chemistry.schemas.scene import (
    BalanceScene,
    CellScene,
    EquilibriumScene,
    StoichScene,
    TitrationScene,
    VseprScene,
    dump_scene,
)
from app.modules.chemistry.solvers.solver import CHEMISTRY_SOLVERS, solve_chemistry
from app.modules.physics.extract import needs_physics
from app.services.solving import SolveServiceError


def test_catalog_matches_operations_and_solvers() -> None:
    kinds = set(get_args(ChemistryKind))
    assert set(CATALOG) == set(CHEMISTRY_SOLVERS)
    assert all(spec.kind in kinds for spec in CATALOG.values())
    assert all(spec.law_name and spec.base_formula for spec in CATALOG.values())


@pytest.mark.parametrize(
    ("kind", "operation"),
    [
        # Not an operation the catalog declares.
        ("amounts", "moles_to_moons"),
        # Declared, but under another kind.
        ("gases", "molar_mass"),
    ],
)
def test_an_intent_names_only_a_catalog_operation_of_its_kind(kind: str, operation: str) -> None:
    with pytest.raises(ValueError, match="chemistry operation"):
        ChemistryIntent.model_validate({"kind": kind, "chemistry_op": operation})


def test_every_catalog_operation_is_a_valid_intent_of_its_kind() -> None:
    for operation, spec in CATALOG.items():
        assert ChemistryIntent.model_validate({"kind": spec.kind, "chemistry_op": operation})


def test_water_scene_keeps_the_molecular_angle() -> None:
    intent = extract_chemistry_intent("VSEPR of H2O")
    assert intent is not None
    result = solve_chemistry(intent)
    assert isinstance(result.scene, VseprScene)
    assert result.scene.bond_angle == "104.5°"
    assert result.scene.ideal_angle == "109.5°"
    assert result.scene.lone_pairs == 2
    verified = build_verified_chemistry(intent)
    assert verified is not None
    reply = format_direct_chemistry_reply(verified)
    payload = json.dumps(typeset_json(dump_scene(result.scene)), ensure_ascii=False)
    fence = f"```chem_scene\n{payload}\n```"
    assert reply.endswith(fence + "\n")
    assert "```chem_scene" not in reply[: reply.index(fence)]
    assert "104.5°" in reply


def test_balance_scene_tallies_atoms() -> None:
    intent = extract_chemistry_intent("Balance H2 + O2 -> H2O")
    assert intent is not None
    scene = solve_chemistry(intent).scene
    assert isinstance(scene, BalanceScene)
    rows = {row.element: row.model_dump() for row in scene.rows}
    assert rows["H"] == {"element": "H", "left": 4, "right": 4}
    assert rows["O"] == {"element": "O", "left": 2, "right": 2}
    assert scene.charge.model_dump() == {"left": 0, "right": 0}


def test_stoich_and_ice_scenes_are_tables_not_curves() -> None:
    stoich = extract_chemistry_intent(
        "10 g of H2 reacts with excess O2 in H2 + O2 -> H2O. How many grams of H2O form?"
    )
    assert stoich is not None
    chain = solve_chemistry(stoich).scene
    assert isinstance(chain, StoichScene)
    assert len(chain.steps) >= 2

    ice = extract_chemistry_intent(
        "Solve the ICE equilibrium for N2O4 -> NO2 when K=4 and [N2O4]=1"
    )
    assert ice is not None
    table = solve_chemistry(ice).scene
    assert isinstance(table, EquilibriumScene)
    rows = {row.species: row for row in table.rows}
    assert rows["N2O4"].change == "−x"
    assert rows["NO2"].change == "+2x"
    assert rows["N2O4"].equilibrium == "0.38 mol/L"


def test_titration_scene_uses_labeled_anchors() -> None:
    weak = extract_chemistry_intent(
        "Weak acid strong base titration: Ma=0.10, Va=0.050 L, Mb=0.10, Vb=0.025 L, "
        "Ka=1.8e-5, find pH"
    )
    assert weak is not None
    scene = solve_chemistry(weak).scene
    assert isinstance(scene, TitrationScene)
    labels = [anchor.label for anchor in scene.anchors]
    assert labels == ["start", "half-equivalence", "equivalence", "solved"]
    half = scene.anchors[1]
    assert half.ph == "4.74"
    assert scene.anchors[2].volume is not None

    strong = extract_chemistry_intent(
        "Strong acid strong base titration: Ma=0.10, Va=0.050 L, Mb=0.10, Vb=0.020 L, find pH"
    )
    assert strong is not None
    strong_scene = solve_chemistry(strong).scene
    assert isinstance(strong_scene, TitrationScene)
    strong_labels = [anchor.label for anchor in strong_scene.anchors]
    assert strong_labels == ["start", "equivalence", "solved"]
    assert strong_scene.anchors[1].ph == "7.00"


def test_galvanic_scene_points_electrons_at_the_cathode() -> None:
    intent = extract_chemistry_intent("Find the galvanic cell for Zn and Cu")
    assert intent is not None
    scene = solve_chemistry(intent).scene
    assert isinstance(scene, CellScene)
    assert scene.anode == "Zn"
    assert scene.cathode == "Cu"
    assert scene.electrons == "anode to cathode"


def test_high_spin_aqua_complex_and_refuses_a_second_row_metal() -> None:
    aqua = extract_chemistry_intent("Find the magnetic moment of [Fe(H2O)6]Cl2")
    assert aqua is not None
    assert "high-spin" in solve_chemistry(aqua).answer
    platinum = extract_chemistry_intent("Find the crystal field of [Pt(NH3)6]Cl4")
    assert platinum is not None
    with pytest.raises(SolveServiceError):
        solve_chemistry(platinum)


def test_named_reaction_refuses_a_secondary_halide() -> None:
    intent = extract_chemistry_intent("hydroxide substitution of SMILES CC(Cl)C")
    assert intent is not None
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)


def test_mass_defect_without_a_mass_stays_unverified() -> None:
    assert extract_chemistry_intent("What is the mass defect?") is None


def test_supplied_nuclear_mass_is_not_a_physics_question() -> None:
    question = "Calculate the mass defect of H-2 when nuclear mass = 2 u"
    assert needs_physics(question) is False
    assert extract_chemistry_intent(question) is not None


def test_atomic_mass_is_not_treated_as_nuclear_mass() -> None:
    question = "binding energy of He-4, mass = 4.002603 u"
    assert extract_chemistry_intent(question) is None
    assert needs_physics(question) is True


def test_square_planar_d8_is_diamagnetic_and_bare_cn4_is_refused() -> None:
    stated = extract_chemistry_intent("Find the crystal field of square planar [Ni(CN)4]2-")
    assert stated is not None
    assert "0 unpaired" in solve_chemistry(stated).answer
    ambiguous = extract_chemistry_intent("Find the crystal field of [Ni(CN)4]2-")
    assert ambiguous is not None
    with pytest.raises(SolveServiceError):
        solve_chemistry(ambiguous)


def test_michaelis_menten_refuses_a_velocity_above_vmax() -> None:
    intent = extract_chemistry_intent("Michaelis-Menten v = 12 Vmax = 10 S = 2")
    assert intent is not None
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)


def test_peroxide_hbr_addition_stays_unverified() -> None:
    assert extract_chemistry_intent("HBr addition with peroxide of SMILES CC=C") is None


def test_hcl_and_hydrogenation_use_the_one_product_path() -> None:
    chloride = extract_chemistry_intent("HCl addition to SMILES C=CC")
    assert chloride is not None and chloride.target == "hcl"
    assert solve_chemistry(chloride).answer == "product SMILES CC(C)Cl"
    saturated = extract_chemistry_intent("catalytic hydrogenation of SMILES C=CC")
    assert saturated is not None and saturated.target == "hydrogenation"
    assert solve_chemistry(saturated).answer == "product SMILES CCC"
    two = extract_chemistry_intent("HCl addition to SMILES CCC=CC")
    assert two is not None and two.target == "hcl"
    with pytest.raises(SolveServiceError):
        solve_chemistry(two)


@pytest.mark.asyncio
async def test_iupac_name_is_verified_only_from_pubchem() -> None:
    settings = Settings()
    with patch(
        "app.modules.chemistry.context.pubchem_gateway.lookup_iupac_name",
        new=AsyncMock(return_value="ethanol"),
    ):
        text, verified, declined = await build_chemistry_augmentation(
            "IUPAC name of SMILES CCO", settings
        )
    assert declined is False
    assert verified is not None
    assert verified.result.answer == "ethanol"
    assert text is not None and "ethanol" in text
    reply = format_direct_chemistry_reply(verified)
    assert "ethanol" in reply
    assert "```chem_scene" not in reply

    with patch(
        "app.modules.chemistry.context.pubchem_gateway.lookup_iupac_name",
        new=AsyncMock(return_value=None),
    ):
        note, missing, declined = await build_chemistry_augmentation(
            "IUPAC name of SMILES CCO", settings
        )
    assert declined is True
    assert missing is None
    assert note is not None and "Do not invent" in note


def test_local_iupac_solver_does_not_invent_a_name() -> None:
    intent = extract_chemistry_intent("IUPAC name of SMILES CCO")
    assert intent is None
    from app.modules.chemistry.schemas import ChemistryIntent

    with pytest.raises(SolveServiceError):
        solve_chemistry(ChemistryIntent(kind="organic", chemistry_op="iupac_name", formula="CCO"))
