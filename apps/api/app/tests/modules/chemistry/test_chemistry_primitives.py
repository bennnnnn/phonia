"""Foundations shared by the verified chemistry operations."""

from __future__ import annotations

import pytest

from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.coordination import parse_complex_formula
from app.modules.chemistry.elements import BY_NUMBER, BY_SYMBOL, ELEMENTS
from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.nuclear import balance_nuclear, format_nuclear
from app.modules.chemistry.organic import isomer_relationship, organic_facts
from app.modules.chemistry.quantity import to_atm, to_kelvin, to_liters
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers import solve_chemistry
from app.modules.chemistry.species_facts import without_formulas
from app.modules.chemistry.structure import lewis_structure, oxidation_states
from app.services.solving import SolveServiceError


def test_periodic_table_has_every_element() -> None:
    assert len(ELEMENTS) == 118
    assert [element.number for element in ELEMENTS] == list(range(1, 119))
    assert set(BY_SYMBOL) == {element.symbol for element in ELEMENTS}
    assert set(BY_NUMBER) == set(range(1, 119))


def test_legacy_masses_and_names_stay_exact() -> None:
    carbon = BY_SYMBOL["C"]
    assert carbon.mass == 12.011
    assert carbon.name == "Carbon"
    assert carbon.electronegativity == 2.55
    assert BY_SYMBOL["Fe"].mass == 55.845
    assert BY_SYMBOL["He"].mass == 4.003
    assert BY_SYMBOL["Al"].name == "Aluminum"
    assert BY_SYMBOL["Cs"].name == "Cesium"
    assert "Xx" not in BY_SYMBOL


def test_helium_has_no_electronegativity_and_f_block_has_no_group() -> None:
    helium = BY_SYMBOL["He"]
    assert helium.electronegativity is None
    assert BY_SYMBOL["U"].group is None
    assert BY_SYMBOL["La"].group == 3
    assert BY_SYMBOL["Ac"].group == 3
    oganesson = BY_SYMBOL["Og"]
    assert oganesson.mass == 294.0
    assert oganesson.mass_is_isotope
    assert helium.configuration
    assert helium.number == 2


def test_redox_balance_checks_atoms_and_charge() -> None:
    half = balance_equation("Fe2+ -> Fe3+ + e-")
    assert half.balanced
    assert half.reactants == {"Fe2+": 1}
    assert half.products == {"Fe3+": 1, "e-": 1}
    redox = extract_chemistry_intent("Balance Fe2+ -> Fe3+ + e-")
    assert redox is not None
    assert solve_chemistry(redox).answer == "Fe2+ -> Fe3+ + e-"

    permanganate = balance_equation("MnO4- + Fe2+ + H+ -> Mn2+ + Fe3+ + H2O")
    assert permanganate.balanced
    assert permanganate.reactants == {"MnO4-": 1, "Fe2+": 5, "H+": 8}
    assert permanganate.products == {"Mn2+": 1, "Fe3+": 5, "H2O": 4}

    water = balance_equation("H2 + O2 -> H2O")
    assert water.reactants == {"H2": 2, "O2": 1}
    assert water.products == {"H2O": 2}


def test_explicit_phases_drop_out_of_the_equilibrium_expression() -> None:
    question = "Find Kc for CaCO3(s) -> CaO(s) + CO2(g) when [CO2]=0.2 M"
    intent = extract_chemistry_intent(question)
    assert intent is not None
    assert intent.chemistry_op == "equilibrium_constant"
    assert intent.species == {"CO2(g)": 0.2}
    assert solve_chemistry(intent).answer == "Kc = 0.20"


def test_school_units_convert_to_the_solvers_units() -> None:
    assert to_kelvin(25, "C") == 298.15
    assert to_liters(500, "mL") == 0.5
    assert to_atm(101.3, "kPa") == pytest.approx(1, rel=1e-3)
    assert to_atm(750, "mmHg") == pytest.approx(750 / 760)


def test_beer_lambert_solves_absorptivity_and_path() -> None:
    epsilon = extract_chemistry_intent(
        "Use Beer-Lambert law: absorbance=2, path length=1 cm, concentration=0.02 M, find epsilon"
    )
    path = extract_chemistry_intent(
        "Use Beer-Lambert law: absorbance=2, epsilon=100, concentration=0.02 M, find path length"
    )
    assert epsilon is not None and path is not None
    assert solve_chemistry(epsilon).answer == "ε = 100 L/(mol·cm)"
    assert solve_chemistry(path).answer == "b = 1.0 cm"


def test_ambiguous_oxidation_and_diprotic_strong_acid_are_refused() -> None:
    assert oxidation_states("FeSO4") == {"Fe": 2, "S": 6, "O": -2}
    assert oxidation_states("FeS") is None
    with pytest.raises(SolveServiceError, match="ambiguous"):
        solve_chemistry(
            ChemistryIntent(kind="structure", chemistry_op="oxidation_state", formula="FeS")
        )
    sulfuric = extract_chemistry_intent("Find the strong acid pH of 0.010 M H2SO4")
    assert sulfuric is not None
    assert build_verified_chemistry(sulfuric) is None


@pytest.mark.parametrize(
    ("formula", "geometry", "polar", "hybrid", "bonds", "lone_pairs", "angle", "electron"),
    [
        ("CO2", "linear", False, "sp", (2, 2), 0, "180°", "linear"),
        ("H2O", "bent", True, "sp3", (1, 1), 2, "104.5°", "tetrahedral"),
        ("NH3", "trigonal pyramidal", True, "sp3", (1, 1, 1), 1, "107°", "tetrahedral"),
        ("CH4", "tetrahedral", False, "sp3", (1, 1, 1, 1), 0, "109.5°", "tetrahedral"),
        ("BF3", "trigonal planar", False, "sp2", (1, 1, 1), 0, "120°", "trigonal planar"),
        (
            "PCl5",
            "trigonal bipyramidal",
            False,
            "sp3d",
            (1, 1, 1, 1, 1),
            0,
            "90° and 120°",
            "trigonal bipyramidal",
        ),
        ("SF6", "octahedral", False, "sp3d2", (1, 1, 1, 1, 1, 1), 0, "90°", "octahedral"),
        ("SO2", "bent", True, "sp2", (2, 2), 1, "less than 120°", "trigonal planar"),
    ],
)
def test_vsepr_for_a_unique_central_atom(
    formula: str,
    geometry: str,
    polar: bool,
    hybrid: str,
    bonds: tuple[int, ...],
    lone_pairs: int,
    angle: str,
    electron: str,
) -> None:
    structure = lewis_structure(formula)
    assert structure is not None
    assert structure.geometry == geometry
    assert structure.bond_angle == angle
    assert structure.electron_geometry == electron
    assert structure.polar is polar
    assert structure.hybridization == hybrid
    assert structure.bond_orders == bonds
    assert structure.central_lone_pairs == lone_pairs
    assert structure.central_formal_charge == 0
    assert structure.resonance_forms == 1


def test_stoichiometry_chain_converts_moles_and_particles_and_reports_excess() -> None:
    grams = extract_chemistry_intent("How many grams of H2O from 2 mol H2 in H2 + O2 -> H2O?")
    particles = extract_chemistry_intent(
        "How many grams of H2O from 1.2044e24 molecules of H2 in H2 + O2 -> H2O?"
    )
    limiting = extract_chemistry_intent(
        "Find the limiting reagent from masses 10 g H2 and 10 g O2 in H2 + O2 -> H2O"
    )
    assert grams is not None and particles is not None and limiting is not None
    assert grams.chemistry_op == "mass_stoichiometry"
    assert particles.chemistry_op == "mass_stoichiometry"
    # 2 mol limits the answer to two figures; 1.2044e24 molecules carry four (1.99995 mol).
    assert solve_chemistry(grams).answer == "m(H2O) = 36 g"
    assert solve_chemistry(particles).answer == "m(H2O) = 36.03 g"
    limited = solve_chemistry(limiting)
    assert any(line.startswith("excess H2 =") for line in limited.substitution)
    moles = extract_chemistry_intent("How many moles of H2O from 4 mol H2 in H2 + O2 -> H2O?")
    assert moles is not None and moles.chemistry_op == "stoichiometry"


def test_weak_base_titration_half_equivalence() -> None:
    intent = extract_chemistry_intent(
        "Weak base strong acid titration: Ma=0.10, Va=0.025 L, Mb=0.10, "
        "Vb=0.050 L, Kb=1.8e-5, find pH"
    )
    assert intent is not None
    assert intent.chemistry_op == "titration_weak"
    # Kb = 1.8e-5 has two figures, so pOH = 4.74 and pH = 9.26 keep two decimals.
    assert solve_chemistry(intent).answer == "pH = 9.26"


def test_hcn_is_carbon_centered_and_resonance_is_counted() -> None:
    hydrogen_cyanide = lewis_structure("HCN")
    assert hydrogen_cyanide is not None
    assert hydrogen_cyanide.central == "C"
    assert hydrogen_cyanide.terminal_elements == ("H", "N")
    assert hydrogen_cyanide.bond_orders == (1, 3)
    assert hydrogen_cyanide.geometry == "linear"
    assert hydrogen_cyanide.bond_angle == "180°"
    assert hydrogen_cyanide.electron_geometry == "linear"
    assert hydrogen_cyanide.polar is True
    assert hydrogen_cyanide.hybridization == "sp"
    assert hydrogen_cyanide.central_formal_charge == 0
    assert hydrogen_cyanide.resonance_forms == 1

    formaldehyde = lewis_structure("H2CO")
    assert formaldehyde is not None
    assert formaldehyde.central == "C"
    assert formaldehyde.geometry == "trigonal planar"
    assert formaldehyde.bond_orders == (1, 1, 2)
    assert formaldehyde.central_formal_charge == 0

    thiocyanate = lewis_structure("SCN-")
    assert thiocyanate is not None
    assert thiocyanate.central == "C"
    assert thiocyanate.bond_orders == (2, 2)
    assert thiocyanate.geometry == "linear"
    assert thiocyanate.resonance_forms == 1

    carbonate = lewis_structure("CO3^2-")
    ozone = lewis_structure("O3")
    nitrate = lewis_structure("NO3-")
    assert carbonate is not None and carbonate.resonance_forms == 3
    assert carbonate.geometry == "trigonal planar"
    assert ozone is not None and ozone.resonance_forms == 2
    assert ozone.geometry == "bent"
    assert ozone.bond_angle == "less than 120°"
    assert nitrate is not None and nitrate.resonance_forms == 3


def test_ambiguous_or_chained_structures_stay_unverified() -> None:
    assert lewis_structure("HOCl") is None
    assert lewis_structure("H2O2") is None
    assert lewis_structure("CH3COOH") is None
    assert lewis_structure("CO") is None


def test_organic_facts_and_coordination_names() -> None:
    ethanol = organic_facts("CCO")
    acid = organic_facts("CC(=O)O")
    alanine = organic_facts("C[C@H](N)C(=O)O")
    assert ethanol is not None and ethanol.groups == ("alcohol",)
    assert acid is not None and acid.groups == ("carboxylic acid",)
    assert alanine is not None and alanine.chirality == ("atom 2 (C): S",)
    assert isomer_relationship("CCO", "COC") == "constitutional isomers"

    cobalt = parse_complex_formula("[Co(NH3)6]Cl3")
    iron = parse_complex_formula("K4[Fe(CN)6]")
    assert cobalt is not None
    assert cobalt.oxidation_state == 3
    assert cobalt.coordination_number == 6
    assert cobalt.name == "hexaamminecobalt(III) chloride"
    assert iron is not None
    assert iron.oxidation_state == 2
    assert iron.name == "potassium hexacyanidoferrate(II)"


def test_nuclear_equations_conserve_nucleons() -> None:
    assert format_nuclear(balance_nuclear("238U -> 234Th + ?")) == "238U → 234Th + 4He"


@pytest.mark.parametrize(
    ("text", "blanked"),
    [
        ("2.0 g of H2 and 16 g of O2", "2.0 g of    and 16 g of   "),
        ("0.10 M Cu2+ from CuSO4", "0.10 M      from      "),
        ("Fe2O3 is 70% iron", "      is 70% iron"),
        ("no formula here", "no formula here"),
    ],
)
def test_without_formulas_blanks_formula_digits_in_place(text: str, blanked: str) -> None:
    assert without_formulas(text) == blanked
    assert len(without_formulas(text)) == len(text)
