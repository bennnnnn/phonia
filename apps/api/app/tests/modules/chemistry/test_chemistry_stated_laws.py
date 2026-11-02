"""One stated number from each later chemistry law, and a decline when an input is missing."""

from __future__ import annotations

import pytest

from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.solvers import solve_chemistry
from app.services.solving import SolveServiceError
from app.services.subjects.dispatch import detect_subject
from app.tests.modules.chemistry.new_law_cases import STATED_LAW_CASES


@pytest.mark.parametrize(("question", "operation", "answer"), STATED_LAW_CASES)
def test_a_stated_law_answers_one_number(question: str, operation: str, answer: str) -> None:
    assert detect_subject(question) == "chemistry"
    intent = extract_chemistry_intent(question)
    assert intent is not None
    assert intent.chemistry_op == operation
    assert solve_chemistry(intent).answer == answer


@pytest.mark.parametrize(
    "question",
    [
        "The mass number is 23. Find the number of neutrons.",
        "The atomic number is 11. Find the ion charge.",
        "Find the maximum electrons.",
        "The bonding electron count is 8. Find the bond order.",
        "Find the wavenumber.",
        "The event count is 50. Find the quantum yield.",
        "Find the tetrahedral splitting.",
        "A buffer has pKb = 4.74. Find the pOH.",
        "The molar heat capacity is 75.0 J/(mol·K). Find the heat.",
        "The current is 1.00 A. Find the moles of electrons.",
        "Use the Hill equation. The ligand concentration is 2.00 M. Find the saturation.",
        "Use the Freundlich isotherm. The Freundlich constant is 2.00. Find the adsorbed amount.",
        "The polymer molar mass is 10000 g/mol. Find the degree of polymerization.",
        "The weight-average molar mass is 20000 g/mol. Find the polydispersity.",
        "Use the Carothers equation. Find the degree of polymerization.",
        "The monomer concentration is 3.00 M. Find the polymerization rate.",
        "Use the Butler-Volmer equation. The exchange current is 1.00e-6 A. Find the current.",
        "Use the Tafel equation. The current is 0.0100 A. Find the overpotential.",
        "The charge number z = 1.00. Find the electrochemical potential.",
        "The activity is 0.500. Find the chemical potential.",
        "The activity coefficient is 0.800. Find the activity.",
        "The field is 1.00 T. Find the Larmor frequency.",
        "The sample frequency is 4.00004e8 Hz. Find the chemical shift.",
        "The field is 0.500 T. Find the mass-to-charge ratio.",
        "The lattice constant is 0.400 nm. Find the interplanar spacing.",
        "Use the lever rule. The alpha composition is 0.200. Find the alpha fraction.",
        "The diffusion coefficient is 1.00e-5 cm^2/s. Find the mean-square displacement.",
        "Use the Stokes-Einstein equation. The radius is 1.00 nm. Find the diffusion coefficient.",
        "The standard deviation is 0.200. Find the relative standard deviation.",
        "Ka = 1.00e-5. Find the conjugate fraction.",
        "Ka = 1.00e-5. Find the acid fraction.",
        "[H+] = 1.00e-4 M. Find the acid fraction.",
        "The pH is 4.00. Find the conjugate fraction.",
    ],
)
def test_a_stated_law_declines_when_an_input_is_missing(question: str) -> None:
    assert extract_chemistry_intent(question) is None


def test_a_centimeter_radius_is_a_length_in_the_magnetic_sector() -> None:
    question = (
        "Use a magnetic sector mass spectrometer. The field is 0.500 T, "
        "the radius is 10.0 cm, and the voltage is 1000 V. Find the mass-to-charge ratio."
    )
    intent = extract_chemistry_intent(question)
    assert intent is not None
    assert intent.chemistry_op == "magnetic_sector"
    assert solve_chemistry(intent).answer == "m/q = 1.25 × 10^-6 kg/C"


def test_an_activity_coefficient_is_not_the_activity() -> None:
    question = (
        "The standard chemical potential is -10000 J/mol and the temperature is 298 K. "
        "The activity coefficient is 0.800. Find the chemical potential."
    )
    assert extract_chemistry_intent(question) is None


def test_a_stated_ph_does_not_turn_a_fraction_into_a_ph() -> None:
    question = "Ka = 1.00e-5, [H+] = 1.00e-4 M, and the pH is 4.00. Find the conjugate fraction."
    assert extract_chemistry_intent(question) is None


def test_an_angstrom_lattice_and_an_si_diffusion_coefficient() -> None:
    spacing = extract_chemistry_intent(
        "Use the cubic crystal spacing. The lattice constant is 4.00 angstrom, "
        "h = 1, k = 0, and l = 0. Find the interplanar spacing."
    )
    assert spacing is not None
    assert solve_chemistry(spacing).answer == "d = 0.40 nm"
    spread = extract_chemistry_intent(
        "The diffusion coefficient is 1.00e-9 m^2/s and the time is 10.0 s. "
        "Find the mean-square displacement."
    )
    assert spread is not None
    assert solve_chemistry(spread).answer == "⟨x²⟩ = 2.00 × 10^-4 cm²"


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        (
            "Mass number 56 and atomic number 26 how many neutrons",
            "neutron_count",
            "N = 30",
        ),
        (
            "Mass number 238 and atomic number 92. How many neutrons?",
            "neutron_count",
            "N = 146",
        ),
        (
            "Iron-56 has atomic number 26. How many neutrons?",
            "neutron_count",
            "N = 30",
        ),
        (
            "How many neutrons are in Iron-56?",
            "neutron_count",
            "N = 30",
        ),
        (
            "How many neutrons are in carbon-14?",
            "neutron_count",
            "N = 8",
        ),
        (
            "Use the Hill equation. The ligand concentration is 3.00 M, "
            "the Hill coefficient n = 2.00, and Kd = 3.00 M. Find the saturation.",
            "hill_saturation",
            "θ = 0.500",
        ),
        (
            "A buffer has pKb = 4.20, the conjugate is 0.050 M, and the base is 0.200 M. "
            "What is the pOH?",
            "base_buffer_poh",
            "pOH = 3.60",
        ),
        (
            "The t2g count is 3.00, the eg count is 2.00, and delta_o is 200 kJ/mol. "
            "Find the crystal field stabilization energy.",
            "crystal_field_stabilization",
            "CFSE = 0 kJ/mol",
        ),
        (
            "Oxygen has atomic number 8 and 10 electrons. What is the charge of the ion?",
            "ion_charge",
            "q = -2.0",
        ),
        (
            "How many electrons fit in the shell with n = 5?",
            "shell_capacity",
            "N = 50",
        ),
        (
            "2.00 mol of gas has a molar heat capacity of 37.0 J/(mol·K) and the temperature "
            "rises by 5.00 K. How much heat is absorbed?",
            "molar_heat",
            "q = 370 J",
        ),
        (
            "Freundlich constant KF = 4.00, concentration C = 3.00 M, and n = 1.00. What is q?",
            "freundlich",
            "q = 12.0",
        ),
        (
            "Mw is 5000 g/mol and Mn is 10000 g/mol. What is the polydispersity?",
            "polydispersity",
            "Đ = 0.5000",
        ),
        (
            "Step-growth polymerization has extent of reaction 0.980. Use Carothers and find Xn.",
            "carothers",
            "Xn = 50.0",
        ),
        (
            "Stokes-Einstein at 20 °C, viscosity 1.00e-3 Pa·s, radius 0.150 nm. What is D?",
            "stokes_einstein",
            "D = 1.43 × 10^-9 m²/s",
        ),
        (
            "K = 1.0e-5 at 298 K. What is the standard free-energy change?",
            "gibbs_from_equilibrium",
            "ΔG° = 29 kJ/mol",
        ),
        (
            "The rate constant is 0.045 1/s. What is the half-life of this first-order reaction?",
            "first_order_half_life",
            "t₁/₂ = 15 s",
        ),
        (
            "What is the oxidation number of chromium in K2Cr2O7?",
            "oxidation_state",
            "K = +1\nCr = +6\nO = -2",
        ),
        (
            "Find the molarity when 5.00 g of NaCl is dissolved in 250 mL of water.",
            "molarity_from_mass",
            "c = 0.342 mol/L",
        ),
    ],
)
def test_ordinary_wording_still_reaches_the_law(question: str, operation: str, answer: str) -> None:
    assert detect_subject(question) == "chemistry"
    intent = extract_chemistry_intent(question)
    assert intent is not None
    assert intent.chemistry_op == operation
    assert solve_chemistry(intent).answer == answer


def test_carothers_declines_when_the_extent_reaches_one() -> None:
    intent = extract_chemistry_intent(
        "Use the Carothers equation. The extent of reaction is 1.00. "
        "Find the degree of polymerization."
    )
    assert intent is not None
    with pytest.raises(SolveServiceError, match="below 1"):
        solve_chemistry(intent)
