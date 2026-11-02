"""Broad regression matrix for the typed chemistry pipeline."""

from __future__ import annotations

import math
import re

import pytest
from pydantic import ValidationError

from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.catalog import CATALOG
from app.modules.chemistry.direct import (
    format_direct_chemistry_reply,
    maybe_direct_chemistry_reply,
)
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers import solve_chemistry
from app.modules.chemistry.solvers.types import format_number
from app.services.solving import SolveServiceError
from app.services.workout import as_formula_heading
from app.tests.modules.chemistry.new_law_cases import NEW_LAW_CASES

PIPELINE_CASES: list[tuple[str, str, str]] = [
    ("Balance H2 + O2 -> H2O", "balance", "2 H2 + O2 -> 2 H2O"),
    ("What is the molar mass of H2O?", "molar_mass", "M(H2O) = 18.02 g/mol"),
    (
        "How many moles are in 36 g of H2O?",
        "mass_to_moles",
        "n(H2O) = 2.0 mol",
    ),
    ("Find the mass of 2 mol of H2O", "moles_to_mass", "m(H2O) = 36 g"),
    (
        "How many molecules are in 2 mol of H2O?",
        "moles_to_particles",
        "N(H2O) = 1.2 × 10^24 particles",
    ),
    (
        "How many moles are in 6.022e23 molecules of H2O?",
        "particles_to_moles",
        "n(H2O) = 1.000 mol",
    ),
    (
        "Find percent composition of O in H2O",
        "percent_composition",
        "O in H2O = 88.81%",
    ),
    (
        "Find percent yield if actual yield = 8 g and theoretical yield = 10 g",
        "percent_yield",
        "Percent yield = 80%",
    ),
    (
        "How many moles of H2O from 4 mol H2 in H2 + O2 -> H2O?",
        "stoichiometry",
        "n(H2O) = 4.0 mol H2O",
    ),
    (
        "Find the limiting reagent and moles of H2O from 4 mol H2 and 1 mol O2 in H2 + O2 -> H2O",
        "limiting_reagent",
        "Limiting reagent = O2; 2.0 mol H2O",
    ),
    (
        "Find molarity of 0.5 mol in 2 L solution",
        "molarity",
        "c = 0.25 mol/L",
    ),
    (
        "Dilution using M1V1: M1=2, V1=50 mL, M2=0.5, find V2",
        "dilution",
        "V2 = 200 mL",
    ),
    (
        "Find molality for 2 mol solute in 4 kg solvent",
        "molality",
        "b = 0.50 mol/kg",
    ),
    (
        "Find mass percent for 5 g solute in 20 g solution",
        "mass_percent",
        "Mass percent = 25%",
    ),
    ("Find pH when [H+] = 0.001", "ph_from_h", "pH = 3.00"),
    ("Find pH when pOH = 3", "ph_from_poh", "pH = 11"),
    ("Find [H+] when pH = 4", "h_from_ph", "[H+] = 1.0 × 10^-4 mol/L"),
    ("Find pOH when [OH-] = 0.01", "poh_from_oh", "pOH = 2.00"),
    (
        "Find buffer pH with pKa=4.76, [A-]=0.2 and [HA]=0.1",
        "buffer_ph",
        "pH = 5.06",
    ),
    (
        "Find Gibbs ΔG when ΔH=-40 kJ, ΔS=-100 J and T=300 K",
        "gibbs",
        "ΔG = -10 kJ/mol",
    ),
    (
        "Find Kc for H2 + I2 -> HI when [H2]=0.2 M, [I2]=0.2 M, [HI]=0.8 M",
        "equilibrium_constant",
        "Kc = 16",
    ),
    (
        "Find reaction quotient Qc for H2 + I2 -> HI when [H2]=0.2 M, [I2]=0.2 M, [HI]=0.8 M",
        "reaction_quotient",
        "Qc = 16",
    ),
    (
        "Find first-order half-life when k=0.2 s^-1",
        "first_order_half_life",
        "t₁/₂ = 3.5 s",
    ),
    (
        "For a first-order reaction [A]0=1, k=0.1, t=10 s, find [A]",
        "first_order_concentration",
        "[A]ₜ = 0.37 mol/L",
    ),
    (
        "Use Arrhenius equation with A=1e10 s^-1, Ea=50 kJ, T=300 K",
        "arrhenius",
        "k = 20 s⁻¹",
    ),
    (
        "Find electrochemical Gibbs ΔG for a cell with n=2 and E°=1.1 V",
        "cell_gibbs",
        # -212 kJ to the two figures of 1.1 V: the hidden 2 is written as a power of ten.
        "ΔG° = -2.1 × 10^2 kJ/mol",
    ),
    (
        "Use Nernst equation with E°=1.1 V, n=2, Q=10, T=298 K",
        "nernst",
        "E = 1.1 V",
    ),
    (
        "Find mass deposited by electrolysis when molar mass=63.55 g/mol, "
        "current=2 A, time=3600 s, n=2",
        "electrolysis_mass",
        "m = 2.4 g",
    ),
    (
        "Use Beer-Lambert law: epsilon=100, path length=1 cm, "
        "concentration=0.02 M, find absorbance",
        "beer_lambert",
        "A = 2.0",
    ),
    (
        "Find the empirical formula from 40.0% C, 6.7% H, and 53.3% O",
        "empirical_formula",
        "CH2O",
    ),
    (
        "Find the molecular formula from 40.0% C, 6.7% H, and 53.3% O when molar mass=180",
        "molecular_formula",
        "C6H12O6",
    ),
    (
        "10 g of H2 reacts with excess O2 in H2 + O2 -> H2O. How many grams of H2O form?",
        "mass_stoichiometry",
        "m(H2O) = 89 g",
    ),
    (
        "0.50 L of 0.20 M HCl reacts with excess NaOH in HCl + NaOH -> NaCl + H2O. "
        "How many moles of NaCl form?",
        "solution_stoichiometry",
        "n(NaCl) = 0.10 mol",
    ),
    (
        "Chemistry: 2.0 L of H2 at 1 atm and 273.15 K reacts with excess O2 in "
        "H2 + O2 -> H2O. How many liters of H2O gas form?",
        "gas_stoichiometry",
        "V(H2O) = 2.0 L",
    ),
    (
        "How many grams of H2O from 22.4 L of H2 at 1 atm and 0 C in 2H2 + O2 -> 2H2O",
        "gas_stoichiometry",
        "m(H2O) = 18 g",
    ),
    (
        "Find the limiting reagent from masses 10 g H2 and 10 g O2 in H2 + O2 -> H2O",
        "limiting_mass",
        "Limiting reagent = O2; 11 g H2O",
    ),
    (
        "Find the limiting solution reagent and grams of NaCl: HCl=0.050 L (0.10 M) and "
        "NaOH=0.020 L (0.10 M) in HCl + NaOH -> NaCl + H2O",
        "limiting_solution",
        "Limiting reagent = NaOH; 0.12 g NaCl",
    ),
    ("Find the strong acid pH of 0.010 M HCl", "strong_acid_ph", "pH = 2.00"),
    ("What is the pOH of 0.010 M HCl?", "strong_acid_poh", "pOH = 12.00"),
    ("Find the strong base pH of 0.010 M NaOH", "strong_base_ph", "pH = 12.00"),
    ("What is the pOH of 0.010 M NaOH?", "strong_base_poh", "pOH = 2.00"),
    (
        "What is the pH of a buffer that is 0.20 M ammonia and 0.30 M ammonium chloride? "
        "Kb = 1.8e-5",
        "base_buffer_ph",
        "pH = 9.08",
    ),
    (
        "A 0.10 M weak acid has pH 3.50. What is Ka?",
        "weak_acid_ka",
        "Ka = 1.0 × 10^-6",
    ),
    (
        "Find the weak acid pH of 0.10 M HA when Ka=1.8e-5",
        "weak_acid_ph",
        "pH = 2.88",
    ),
    (
        "What is the pH of a 0.050 M solution of sodium acetate? The Ka of acetic acid is 1.8e-5.",
        "conjugate_salt_ph",
        "pH = 8.72",
    ),
    (
        "Find the weak base pH of 0.10 M B when Kb=1.8e-5",
        "weak_base_ph",
        "pH = 11.12",
    ),
    ("Find Kb from Ka=1.8e-5", "ka_kb", "Kb = 5.6 × 10^-10"),
    (
        "Strong acid strong base titration: Ma=0.10, Va=0.050 L, Mb=0.10, Vb=0.020 L, find pH",
        "titration_strong",
        "pH = 1.37",
    ),
    (
        "Weak acid strong base titration: Ma=0.10, Va=0.050 L, Mb=0.10, Vb=0.025 L, "
        "Ka=1.8e-5, find pH",
        "titration_weak",
        "pH = 4.74",
    ),
    (
        "Buffer after adding acid: pKa=4.76, HA=0.10 mol, A-=0.10 mol, added=0.02 mol acid",
        "buffer_addition",
        "pH = 4.58",
    ),
    (
        "Find the polyprotic pH of 0.10 M HA when Ka1=4.3e-7",
        "polyprotic_ph",
        "pH = 3.68",
    ),
    (
        "Use Dalton's law: P(N2)=0.8 atm and P(O2)=0.2 atm",
        "dalton",
        "Ptotal = 1.0 atm",
    ),
    (
        "Find the partial pressure when mole fraction=0.25 and total pressure=2 atm",
        "partial_pressure",
        "Pi = 0.50 atm",
    ),
    (
        "Gas collected over water at 25 C with total pressure=760 mmHg",
        "gas_over_water",
        "Pdry = 736 mmHg",
    ),
    (
        "Find calorimetry heat when calorimeter constant Ccal=200 J/C and ΔT=2 C",
        "calorimetry",
        "q_rxn = -400 J",
    ),
    (
        "Use Hess's law: ΔH1=-200 kJ, multiplier1=1, ΔH2=50 kJ, multiplier2=2",
        "hess",
        "ΔH = -100 kJ",
    ),
    (
        "Find the formation enthalpy for C + O2 -> CO2 when ΔHf(CO2)=-393.5 kJ/mol",
        "formation_enthalpy",
        "ΔH° = -393.5 kJ/mol",
    ),
    (
        "Find the bond enthalpy when bonds broken=800 kJ and bonds formed=1000 kJ",
        "bond_enthalpy",
        "ΔH = -200 kJ",
    ),
    (
        "Find the molar solubility from Ksp=1.8e-10 for AgCl(s) -> Ag+ + Cl-",
        "ksp",
        "s = 1.3 × 10^-5 mol/L",
    ),
    (
        "Compare precipitation when Qsp=2e-10 and Ksp=1.8e-10",
        "precipitation",
        "precipitate forms (Qsp > Ksp)",
    ),
    (
        "Common-ion solubility: Ksp=1.8e-10 for AgCl(s) -> Ag+ + Cl- when [Cl-]=0.01",
        "common_ion",
        "[Ag+] = 1.8 × 10^-8 mol/L",
    ),
    (
        "Find Kp for CaCO3(s) -> CaO(s) + CO2(g) when P(CO2)=0.2 atm",
        "kp",
        "Kp = 0.20",
    ),
    (
        "Convert Kc to Kp: Kc=0.5 at T=298 K for N2 + H2 -> NH3",
        "kc_kp",
        "Kp = 8.4 × 10^-4",
    ),
    (
        "Solve the ICE equilibrium for N2O4 -> NO2 when K=4 and [N2O4]=1",
        "ice_equilibrium",
        "x = 0.62\n[N2O4] = 0.38 mol/L\n[NO2] = 1.2 mol/L",
    ),
    (
        "For a zero-order reaction [A]0=1, k=0.1, t=2 s, find [A]",
        "zero_order",
        "[A]ₜ = 0.80 mol/L",
    ),
    (
        "For a second-order reaction [A]0=1, k=0.1, t=10 s, find [A]",
        "second_order",
        "[A]ₜ = 0.50 mol/L",
    ),
    (
        "For a zero-order reaction [A]0=1, k=0.1, find the half-life",
        "zero_order_half_life",
        "t₁/₂ = 5.0 (in the time unit of k)",
    ),
    (
        "For a second-order reaction [A]0=1, k=0.1, find the half-life",
        "second_order_half_life",
        "t₁/₂ = 10 (in the time unit of k)",
    ),
    (
        "Find the rate law from experiments a1=0.1, rate1=0.02, a2=0.2, rate2=0.08",
        "rate_law",
        "rate = 2.0 [A]^2",
    ),
    (
        "Use the two-temperature Arrhenius equation with k1=0.1, T1=300 K, k2=0.4, T2=320 K",
        "arrhenius_two_point",
        "Ea = 55 kJ/mol",
    ),
    (
        "Find the cell potential when cathode=0.34 V and anode=-0.76 V",
        "cell_potential",
        "E°cell = 1.10 V",
    ),
    (
        "Find the galvanic cell for Zn and Cu",
        "galvanic_cell",
        "E°cell = 1.10 V\nanode: Zn\ncathode: Cu\nn = 2 electrons transferred\nZn + Cu2+ -> Zn2+ + Cu\nspontaneous (E°cell > 0)",
    ),
    (
        "Balance the nuclear equation 238U -> 234Th + ?",
        "nuclear_equation",
        "238U → 234Th + 4He",
    ),
    (
        "Find the oxidation state of each element in FeSO4",
        "oxidation_state",
        "Fe = +2\nS = +6\nO = -2",
    ),
    (
        "Find the VSEPR shape of H2O",
        "vsepr",
        "geometry: bent, 104.5°\npolarity: polar\nhybridization: sp3\n"
        "central formal charge: 0\nelectron geometry: tetrahedral, ideal angle 109.5°",
    ),
    (
        "Why is water bent but CO2 linear?",
        "vsepr",
        "H2O: bent, 104.5°, polar\nCO2: linear, 180°, nonpolar",
    ),
    (
        "Find the formal charge when valence=4, nonbonding=0, bonding=8",
        "formal_charge",
        "FC = 0",
    ),
    ("Identify functional groups in SMILES CCO", "functional_groups", "alcohol"),
    (
        "Find the stereochemistry of SMILES C[C@H](N)C(=O)O",
        "stereochemistry",
        "atom 2 (C): S",
    ),
    (
        "What is the isomer relationship between SMILES CCO and COC?",
        "isomers",
        "constitutional isomers",
    ),
    (
        "Name the coordination complex [Co(NH3)6]Cl3",
        "coordination_complex",
        "name: hexaamminecobalt(III) chloride\nCo oxidation state: +3\ncoordination number: 6",
    ),
    (
        "Find the boiling point elevation when i=1, Kb=0.512, and molality=0.5",
        "boiling_elevation",
        "ΔTb = 0.26 °C",
    ),
    (
        "Find the freezing point depression when i=1, Kf=1.86, and molality=0.5",
        "freezing_depression",
        "ΔTf = 0.93 °C",
    ),
    (
        "Find the osmotic pressure when i=1, molarity=0.1, and T=298 K",
        "osmotic_pressure",
        "Π = 2.4 atm",
    ),
    (
        "Use Raoult's law when mole fraction=0.8 and pure pressure=100",
        "raoult",
        "P = 80",
    ),
    (
        "Use the calibration curve slope=2, intercept=0.1, signal=1.1, find concentration",
        "calibration",
        "c = 0.50",
    ),
    (
        "Gravimetric analysis: precipitate mass=0.5 g and factor=0.2",
        "gravimetric",
        "mass = 0.10 g",
    ),
    (
        "Standard addition: sample signal=0.2, spiked signal=0.6, "
        "standard concentration=0.01, standard volume=0.001 L, sample volume=0.01 L",
        "standard_addition",
        "c = 5.0 × 10^-4",
    ),
]


# Operations PubChem answers (a name's structure, a structure's name). IUPAC
# names are a PubChem property. The local solver refuses them so a missing
# lookup cannot be labeled verified.
PUBCHEM_OPS = frozenset({"iupac_name", "structure"})
_LOCAL_OPS = set(CATALOG) - PUBCHEM_OPS

REMAINING_CASES = (
    (
        "Calculate the mass defect of H-2 when nuclear mass = 2 u",
        "mass_defect",
        "Δm = 0.016 u\nE = 15 MeV\nE/A = 7.4 MeV/nucleon",
    ),
    (
        "Find the crystal field of K4[Fe(CN)6]",
        "crystal_field",
        "octahedral low-spin d6, 0 unpaired, μ = 0 BM",
    ),
    (
        "Find the standard deviation of these measurements: 2, 4, 4, 4, 5, 5, 7, 9",
        "standard_deviation",
        "s = 2.1",
    ),
    (
        "Find the standard error of these trials: 2, 4, 4, 4, 5, 5, 7, 9",
        "standard_error",
        "SE = 0.76",
    ),
    (
        "percent error experimental = 9.8 accepted = 10",
        "percent_error",
        "percent error = 2.0%",
    ),
    (
        "relative uncertainty a = 10 da = 0.1 b = 4 db = 0.2",
        "relative_uncertainty",
        "relative uncertainty = 0.051",
    ),
    (
        "retention factor spot = 2.4 solvent front = 8",
        "chromatography_rf",
        "Rf = 0.30",
    ),
    (
        "Michaelis-Menten Vmax = 10 Km = 2 S = 2",
        "michaelis_menten",
        "v = 5.0",
    ),
    (
        "bromine addition to SMILES C=C",
        "named_reaction",
        "product SMILES BrCCBr",
    ),
    (
        "IR ranges for SMILES CCO",
        "ir_ranges",
        "alcohol O–H 3200–3600 cm⁻¹",
    ),
    (
        "IR peak 1710",
        "ir_peak",
        "carboxylic acid\nketone",
    ),
    (
        "NMR ranges for SMILES CCO",
        "nmr_ranges",
        "alcohol H–C–O 3.2–4.5 ppm",
    ),
    (
        "NMR peak 9.5",
        "nmr_peak",
        "aldehyde",
    ),
    (
        "NMR splitting neighbors = 2",
        "nmr_splitting",
        "n+1 = 3 (triplet)",
    ),
    (
        "molecular ion of C2H6O",
        "molecular_ion",
        "M+ = 46.0419 (nominal m/z 46)",
    ),
    (
        "Use Graham's law when r1=2, M1=4, and M2=16. Find r2.",
        "graham",
        "rate2 = 1.0",
    ),
    (
        "Clausius-Clapeyron: P1=1, T1=300, P2=2, T2=350. Find the enthalpy.",
        "clausius_clapeyron",
        "ΔHvap = 12 kJ/mol",
    ),
    (
        "Use Henry's law when kH=0.034 and P=2. Find the concentration.",
        "henry",
        "C = 0.068",
    ),
)


def test_pipeline_matrix_covers_every_typed_operation() -> None:
    covered = {
        operation
        for _question, operation, _answer in (*PIPELINE_CASES, *REMAINING_CASES, *NEW_LAW_CASES)
    }
    assert covered == _LOCAL_OPS


@pytest.mark.parametrize(
    ("question", "operation", "answer"), (*PIPELINE_CASES, *REMAINING_CASES, *NEW_LAW_CASES)
)
def test_text_pipeline_matrix(question: str, operation: str, answer: str) -> None:
    assert is_chemistry_question(question)
    intent = extract_chemistry_intent(question)
    assert intent is not None
    assert intent.chemistry_op == operation

    result = solve_chemistry(intent)
    assert result.answer == answer
    # A trailing zero is a significant figure now; what must never show is float noise.
    assert not re.search(r"\d\.\d{5,}", result.answer)
    assert result.given
    assert result.find
    assert result.formula_name
    assert result.formula
    assert result.substitution


def test_direct_reply_has_scan_friendly_heading_order() -> None:
    intent = extract_chemistry_intent("Find pH when [H+] = 0.001")
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None

    reply = format_direct_chemistry_reply(verified)
    headings = ["**Given**", "**Required**", "**Solution**", "**Formula**", "**Substitution**"]
    read = as_formula_heading(reply)
    positions = [read.index(heading) for heading in [*headings, "**Answer**"]]
    assert positions == sorted(positions)
    # The law's name heads its equation, never a note beside it.
    assert "**Definition of pH formula**  \npH = −log₁₀[H⁺]\n" in reply
    assert reply.count("```answer") == 1
    assert "notation: chemistry\npH = 3.00\n" in reply
    assert "✅" not in reply
    assert maybe_direct_chemistry_reply(verified, has_image_attachment=False) == reply
    assert maybe_direct_chemistry_reply(verified, has_image_attachment=True) is None
    assert maybe_direct_chemistry_reply(None, has_image_attachment=False) is None


@pytest.mark.parametrize(
    "question",
    [
        "",
        "What is chemistry?",
        "Find molarity of 2 mol",
        "Use the ideal gas law with P=1 atm",
        "Find buffer pH with pKa=4.7",
        "x" * 4001,
    ],
)
def test_incomplete_or_non_calculation_text_stays_on_model_path(question: str) -> None:
    assert extract_chemistry_intent(question) is None


def test_dilution_can_find_stock_concentration() -> None:
    intent = extract_chemistry_intent(
        "Dilution using M1V1: M2=0.250, V2=100.0 mL, V1=20.0 mL, find M1"
    )
    assert intent is not None
    result = solve_chemistry(intent)
    assert result.answer == "M1 = 1.25 mol/L"


def test_dilution_labeled_form_can_find_stock_volume() -> None:
    intent = extract_chemistry_intent("Dilution using M1V1: M1=2.00, M2=0.500, V2=100 mL, find V1")
    assert intent is not None
    result = solve_chemistry(intent)
    assert result.answer == "V1 = 25.0 mL"


def test_dilution_can_find_final_concentration() -> None:
    result = solve_chemistry(
        ChemistryIntent(
            kind="solutions",
            chemistry_op="dilution",
            params={"m1": 2, "v1": 50, "v2": 200},
            units={"v1": "mL"},
        )
    )
    assert result.answer == "M2 = 0.5 mol/L"
    assert result.formula == "M1V1 = M2V2"


def test_dilution_normalizes_each_supplied_volume_unit() -> None:
    intent = extract_chemistry_intent("Dilution using M1V1: M1=1, V1=500 mL, V2=2 L, find M2")
    assert intent is not None
    assert intent.params == {"m1": 1, "v1": 500, "v2": 2}
    assert intent.units == {"v1": "mL", "v2": "L"}

    result = solve_chemistry(intent)
    assert result.given == ("M1 = 1 mol/L", "V1 = 500 mL", "V2 = 2 L")
    # Two volume units meet in litres, and the step to them is a row of its own.
    assert result.substitution == ("V1 = 500 mL = 0.500 L", "M2 = (1 mol/L)(0.500 L) / 2 L")
    assert result.answer == "M2 = 0.25 mol/L"

    implicit_unit = extract_chemistry_intent(
        "Dilution using M1V1: M1=1, V1=500 mL, V2=2000, find M2"
    )
    assert implicit_unit is not None
    assert implicit_unit.units == {"v1": "mL", "v2": "mL"}
    assert solve_chemistry(implicit_unit).answer == "M2 = 0.25 mol/L"


def test_explicit_zero_nernst_temperature_is_not_defaulted() -> None:
    intent = extract_chemistry_intent("Use Nernst equation with E°=1.1 V, n=2, Q=10, T=0 K")
    assert intent is not None
    assert intent.params["temperature"] == 0
    assert build_verified_chemistry(intent) is None


def test_beer_lambert_can_find_concentration() -> None:
    result = solve_chemistry(
        ChemistryIntent(
            kind="spectroscopy",
            chemistry_op="beer_lambert",
            params={"absorbance": 2, "epsilon": 100, "path": 1},
        )
    )
    assert result.answer == "c = 0.02 mol/L"


@pytest.mark.parametrize(
    "intent",
    [
        ChemistryIntent(kind="solutions", chemistry_op="molarity", params={"moles": 1}),
        ChemistryIntent(
            kind="solutions",
            chemistry_op="mass_percent",
            params={"solute_mass": 6, "solution_mass": 5},
        ),
        ChemistryIntent(
            kind="kinetics",
            chemistry_op="first_order_half_life",
            params={"rate_constant": 0},
        ),
        ChemistryIntent(
            kind="electrochemistry",
            chemistry_op="nernst",
            params={
                "standard_potential": 1,
                "electrons": 0,
                "quotient": 1,
                "temperature": 298,
            },
        ),
    ],
)
def test_physically_invalid_inputs_are_rejected(intent: ChemistryIntent) -> None:
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)
    assert build_verified_chemistry(intent) is None


def test_non_finite_inputs_are_rejected_at_schema_boundary() -> None:
    with pytest.raises(ValidationError, match="finite"):
        ChemistryIntent(kind="solutions", chemistry_op="molarity", params={"moles": math.inf})


def test_operation_must_belong_to_its_typed_group() -> None:
    with pytest.raises(ValidationError, match="not a 'gases'"):
        ChemistryIntent(kind="gases", chemistry_op="molarity", params={})


@pytest.mark.parametrize(
    ("value", "formatted"),
    [(20.0, "20"), (20.2, "20.2"), (-0.0, "0"), (6.022e23, "6.022 × 10^23")],
)
def test_number_formatting_removes_only_unnecessary_zeros(value: float, formatted: str) -> None:
    assert format_number(value) == formatted
