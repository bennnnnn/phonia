# ruff: noqa: RUF002 -- answers use a multiplication sign and a true minus sign.
"""Regression tests for answers that used to be verified with the wrong number or unit.

Each case names the input that was silently mis-read before. A refusal (``None``
intent or a ``SolveServiceError``) is the correct outcome when a unit or a value
cannot be read with certainty.
"""

from __future__ import annotations

import math
import re

import pytest

from app.modules.chemistry.coordination import parse_complex_formula
from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.extractors.amounts import (
    _percents,
)
from app.modules.chemistry.formula import parse_formula as parse_formula_atoms
from app.modules.chemistry.lewis import lewis_structure
from app.modules.chemistry.nuclear import balance_nuclear, format_nuclear
from app.modules.chemistry.organic import organic_facts
from app.modules.chemistry.reactions import named_product
from app.modules.chemistry.request import EQUATION_RE
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.schemas.intent import ChemistryKind
from app.modules.chemistry.schemas.scene import TitrationScene
from app.modules.chemistry.solvers import solve_chemistry
from app.modules.chemistry.solvers.thermochemistry import (
    _formation,
)
from app.modules.chemistry.solvers.types import ChemistryResult, format_number
from app.modules.chemistry.species import parse_species, split_terms
from app.modules.chemistry.stoichiometry import limiting_reagent, molar_mass
from app.modules.chemistry.structure import oxidation_states
from app.services.solving import SolveServiceError


def _intent(question: str) -> ChemistryIntent:
    intent = extract_chemistry_intent(question)
    assert intent is not None, question
    return intent


def _solve(question: str) -> ChemistryResult:
    return solve_chemistry(_intent(question))


def _first_number(text: str) -> float:
    """First number after ``=``; understands ``1.2 × 10^24`` and ``1.2e24``."""
    match = re.search(
        r"=\s*(-?\d+(?:\.\d+)?)(?:\s*×\s*10\^(-?\d+)|e(-?\d+))?", text.replace("−", "-")
    )
    assert match is not None, text
    exponent = match.group(2) or match.group(3)
    return float(match.group(1)) * (10 ** int(exponent) if exponent else 1)


def _shown(value: float, figures: int) -> object:
    """``value`` as an answer shows it: rounded to the question's significant figures."""
    return pytest.approx(float(f"{value:.{figures}g}"), rel=1e-9, abs=0)


# --- gas mixtures: units are converted, never assumed -----------------------------------


def test_dalton_keeps_the_pressure_unit_it_was_given() -> None:
    result = _solve("Use Dalton's law: P(N2) = 600 mmHg and P(O2) = 160 mmHg")
    assert result.answer == "Ptotal = 760 mmHg"


def test_dalton_with_mixed_units_answers_in_atm() -> None:
    result = _solve("Use Dalton's law: P(N2) = 0.5 atm and P(O2) = 101.325 kPa")
    assert result.answer == "Ptotal = 1.5 atm"


def test_partial_pressure_keeps_its_unit() -> None:
    result = _solve("Find the partial pressure when mole fraction=0.25 and total pressure=200 kPa")
    assert result.answer == "Pi = 50 kPa"


def test_kp_converts_partial_pressures_to_atm() -> None:
    # 152 mmHg has three figures, so Kp does too.
    result = _solve("Find Kp for CaCO3(s) -> CaO(s) + CO2(g) when P(CO2)=152 mmHg")
    assert result.answer == "Kp = 0.200"


def test_kp_without_a_pressure_unit_is_not_verified() -> None:
    intent = extract_chemistry_intent("Find Kp for CaCO3(s) -> CaO(s) + CO2(g) when P(CO2)=0.2")
    assert intent is None or not intent.species


def test_gas_over_water_accepts_a_degree_sign() -> None:
    result = _solve("Gas collected over water at 25 °C with total pressure=760 mmHg")
    assert result.answer == "Pdry = 736 mmHg"


# --- kinetics, thermo, electrochemistry: units come from the text -----------------------


def test_first_order_half_life_uses_the_time_unit_of_k() -> None:
    result = _solve("Find first-order half-life when k = 0.05 min^-1")
    assert result.answer.endswith(" min")
    assert _first_number(result.answer) == _shown(math.log(2) / 0.05, 2)


def test_first_order_half_life_without_a_unit_is_not_verified() -> None:
    assert extract_chemistry_intent("Find first-order half-life when k=0.2") is None


def test_first_order_concentration_converts_k_to_the_time_unit_of_t() -> None:
    result = _solve("For a first-order reaction [A]0=1, k=6 min^-1, t=10 s, find [A]")
    assert _first_number(result.answer) == _shown(math.exp(-1.0), 2)


def test_zero_order_with_k_per_minute_and_t_in_seconds_is_not_verified() -> None:
    question = "For a zero-order reaction [A]0=1, k=0.1 M/min, t=2 s, find [A]"
    assert extract_chemistry_intent(question) is None


def test_calorimeter_constant_in_kilojoules_is_converted() -> None:
    result = _solve("Find calorimetry heat when calorimeter constant Ccal=3.2 kJ/C and ΔT=2 C")
    assert _first_number(result.answer) == pytest.approx(-6400)


def test_calorimeter_constant_without_a_unit_is_not_verified() -> None:
    assert extract_chemistry_intent("Find calorimetry heat when Ccal=200 and ΔT=2 C") is None


def test_hess_law_with_a_step_missing_its_multiplier_is_not_a_partial_sum() -> None:
    question = "Use Hess's law: ΔH1=-200 kJ, multiplier1=1, ΔH2=50 kJ"
    assert extract_chemistry_intent(question) is None


@pytest.mark.parametrize(
    "question",
    [
        "Find pH when [H+] = 5 mM",
        "Use Hess's law: ΔH1=-50 kcal, multiplier1=1",
        "Find the heat with specific heat = 1.0 cal/g°C, mass = 10 g, ΔT = 5 C",
    ],
)
def test_units_that_are_not_converted_stay_on_the_model_path(question: str) -> None:
    assert extract_chemistry_intent(question) is None


def test_nernst_temperature_in_celsius_is_converted() -> None:
    result = _solve("Use Nernst equation with E°=1.1 V, n=2, Q=10, T=37 °C")
    expected = 1.1 - 8.31446261815324 * 310.15 / (2 * 96485.33212) * math.log(10)
    assert _first_number(result.answer) == _shown(expected, 2)
    assert "310.15" in " ".join(result.substitution)


def test_nernst_temperature_without_a_unit_is_not_replaced_by_25_celsius() -> None:
    assert extract_chemistry_intent("Use Nernst equation with E°=1.1 V, n=2, Q=10, T=310") is None


def test_electrolysis_time_in_minutes_is_converted() -> None:
    result = _solve(
        "Find mass deposited by electrolysis when molar mass=63.55 g/mol, current=2 A, "
        "time=60 min, n=2"
    )
    assert _first_number(result.answer) == _shown(63.55 * 2 * 3600 / (2 * 96485.33212), 2)


# --- the question head decides what is asked --------------------------------------------


def test_moles_are_asked_even_when_the_given_is_in_grams() -> None:
    intent = _intent("How many moles of NH3 form from 10 grams of N2 in N2 + 3H2 -> 2NH3?")
    assert intent.units["find"] == "mol"
    result = solve_chemistry(intent)
    assert result.answer.startswith("n(NH3) = ")
    assert result.answer.endswith(" mol")
    assert _first_number(result.answer) == pytest.approx(2 * 10 / 28.01, rel=1e-2)


def test_grams_are_asked_when_the_head_says_grams() -> None:
    intent = _intent("How many grams of H2O from 2 mol H2 in H2 + O2 -> H2O?")
    assert intent.units["find"] == "g"


def test_a_reactant_is_not_answered_as_a_product() -> None:
    question = "How many moles of O2 are needed for 4 mol H2 in H2 + O2 -> H2O?"
    intent = extract_chemistry_intent(question)
    assert intent is None or intent.target != "H2O"


def test_atoms_are_counted_as_atoms() -> None:
    result = _solve("How many atoms are in 2 mol of H2O?")
    assert result.answer.endswith(" atoms")
    assert _first_number(result.answer) == _shown(2 * 3 * 6.02214076e23, 2)


def test_molecules_stay_molecules() -> None:
    result = _solve("How many molecules are in 2 mol of H2O?")
    assert result.answer.endswith(" particles")
    assert _first_number(result.answer) == _shown(2 * 6.02214076e23, 2)


# --- fragile capture --------------------------------------------------------------------


def test_percent_words_are_element_names_not_two_letter_symbols() -> None:
    assert _percents("40% Carbon, 60% Nitrogen") == {"C": 40.0, "N": 60.0}
    assert _percents("40% C, 60% N") == {"C": 40.0, "N": 60.0}
    assert _percents("40% Unobtainium") == {}


def test_empirical_formula_from_percentages_by_element_name() -> None:
    result = _solve(
        "Find the empirical formula of a compound with 40% carbon, 6.7% hydrogen and 53.3% oxygen"
    )
    assert result.answer == "CH2O"


def test_standard_deviation_uses_only_the_listed_numbers() -> None:
    intent = _intent("Find the standard deviation of 5 measurements: 10.1, 10.3, 10.2")
    assert intent.samples == [10.1, 10.3, 10.2]
    assert _intent("Find the standard deviation of 4, 8 and 15").samples == [4.0, 8.0, 15.0]


def test_standard_deviation_of_a_sentence_with_a_count_is_not_verified() -> None:
    question = "Find the standard deviation of the Cu2+ readings from 5 runs"
    assert extract_chemistry_intent(question) is None


def test_buffer_addition_reads_the_reagent_that_was_added() -> None:
    base = _solve("Buffer after adding NaOH: pKa=4.76, HA=0.10 mol, A-=0.10 mol, added=0.02 mol")
    # pKa = 4.76 has two decimals, so the pH has two.
    assert base.answer == f"pH = {4.76 + math.log10(0.12 / 0.08):.2f}"
    acid = _solve(
        "Buffer after adding strong acid to the conjugate base A-: pKa=4.76, HA=0.10 mol, "
        "A-=0.10 mol, added=0.02 mol"
    )
    assert acid.answer == f"pH = {4.76 + math.log10(0.08 / 0.12):.2f}"


def test_buffer_addition_without_a_reagent_is_not_verified() -> None:
    question = "Buffer after adding: pKa=4.76, HA=0.10 mol, A-=0.10 mol, added=0.02 mol"
    assert extract_chemistry_intent(question) is None


def test_michaelis_menten_reads_bracketed_substrate() -> None:
    assert _solve("Michaelis-Menten Vmax = 10 Km = 2 [S] = 2").answer == "v = 5.0"


def test_ir_peak_after_the_word_at() -> None:
    assert _intent("IR peak at 1710").chemistry_op == "ir_peak"


def test_a_solver_error_is_a_refusal_not_a_crash() -> None:
    with pytest.raises(SolveServiceError):
        solve_chemistry(
            ChemistryIntent(
                kind="solutions",
                chemistry_op="dilution",
                params={"m1": 1.0, "v1": 2.0, "m2": 0.0},
            )
        )


# --- parsing primitives -----------------------------------------------------------------

ARROWS = ["->", "→", "=>", "<=>", "⇌", "⇋", "<->", "-->", "⟶"]


@pytest.mark.parametrize("arrow", ARROWS)
def test_every_common_arrow_splits_and_balances(arrow: str) -> None:
    balanced = balance_equation(f"N2 + 3H2 {arrow} 2NH3")
    assert balanced.balanced, arrow
    assert balanced.reactants == {"N2": 1, "H2": 3}
    assert balanced.products == {"NH3": 2}


@pytest.mark.parametrize("arrow", ["<=>", "⇌", "-->"])
def test_reversible_arrows_reach_the_equilibrium_constant(arrow: str) -> None:
    result = _solve(f"Find Kc for N2 + 3H2 {arrow} 2NH3 when [N2]=0.5 M, [H2]=0.5 M, [NH3]=0.2 M")
    assert result.answer == "Kc = 0.64"


def test_nuclear_equations_accept_the_same_arrows() -> None:
    assert balance_nuclear("238U --> 234Th + ?").balanced
    assert balance_nuclear("238U → 234Th + ?").balanced


def test_polyatomic_ion_charge_needs_a_caret_when_a_digit_precedes_the_sign() -> None:
    assert parse_species("SO42-") is None
    assert parse_species("Cr2O72-") is None
    assert parse_species("Fe(CN)63-") is None
    sulfate = parse_species("SO4^2-")
    assert sulfate is not None and sulfate.charge == -2
    nitrate = parse_species("NO3-")
    assert nitrate is not None and nitrate.charge == -1 and nitrate.composition == {"N": 1, "O": 3}
    iron = parse_species("Fe2+")
    assert iron is not None and iron.composition == {"Fe": 1} and iron.charge == 2
    copper = parse_species("Cu2+")
    assert copper is not None and copper.composition == {"Cu": 1} and copper.charge == 2
    superoxide = parse_species("O2-")
    assert superoxide is not None and superoxide.composition == {"O": 2} and superoxide.charge == -1
    peroxide = parse_species("O2^2-")
    assert peroxide is not None and peroxide.composition == {"O": 2} and peroxide.charge == -2
    hydrogen = parse_species("H2+")
    assert hydrogen is not None and hydrogen.composition == {"H": 2} and hydrogen.charge == 1


def test_dichromate_without_a_caret_is_refused_not_balanced_to_nonsense() -> None:
    assert not balance_equation("Cr2O72- + Fe2+ + H+ -> Cr3+ + Fe3+ + H2O").balanced


def test_dichromate_with_a_caret_balances() -> None:
    balanced = balance_equation("Cr2O7^2- + Fe2+ + H+ -> Cr3+ + Fe3+ + H2O")
    assert balanced.balanced
    assert balanced.reactants == {"Cr2O7^2-": 1, "Fe2+": 6, "H+": 14}
    assert balanced.products == {"Cr3+": 2, "Fe3+": 6, "H2O": 7}


def test_braced_charges_are_not_split_at_their_plus_sign() -> None:
    assert split_terms("Fe^{2+} + Ce^{4+}") == ["Fe^{2+}", "Ce^{4+}"]


@pytest.mark.parametrize(
    "formula",
    ["H0", "0H2O", "Fe0.95O", "H2O..2H2O", ".H2O", "H2O.", "H(2)", "(" * 30 + "H" + ")" * 30],
)
def test_malformed_formulas_are_not_parsed(formula: str) -> None:
    assert parse_formula_atoms(formula) == {}


def test_hydrates_and_groups_still_parse() -> None:
    assert parse_formula_atoms("CuSO4.5H2O") == {"Cu": 1, "S": 1, "O": 9, "H": 10}
    assert parse_formula_atoms("Ca(OH)2") == {"Ca": 1, "O": 2, "H": 2}
    assert parse_formula_atoms("Fe(aq)") == {"Fe": 1}


def test_hydrate_equation_is_not_truncated_to_its_water() -> None:
    assert EQUATION_RE.search("CuSO4.5H2O -> CuSO4 + H2O") is None
    match = EQUATION_RE.search("Balance 2H2 + O2 -> 2H2O.")
    assert match is not None and match.group(1) == "2H2 + O2 -> 2H2O"


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (999999.7, "1 × 10^6"),
        (9.999996e-4, "0.001"),
        (1.9999996e-5, "2 × 10^-5"),
        (0.5, "0.5"),
        (-40.0, "-40"),
        (0.0, "0"),
    ],
)
def test_format_number_rounds_before_it_chooses_a_form(value: float, text: str) -> None:
    assert format_number(value) == text


@pytest.mark.parametrize(
    ("formula", "mass", "substitution", "atom_count"),
    [
        ("C1CCCCC1", 84.16, "M = 6(12.011) + 12(1.008)", 18),
        ("C1CC1", 42.08, "M = 3(12.011) + 6(1.008)", 9),
        ("OC1CCCCC1", 100.16, "M = 1(15.999) + 6(12.011) + 12(1.008)", 19),
        ("C6H12O6", 180.16, "M = 6(12.011) + 12(1.008) + 6(15.999)", 24),
        ("CO2", 44.01, "M = 1(12.011) + 2(15.999)", 3),
        ("CO", 28.01, "M = 1(12.011) + 1(15.999)", 2),
        ("CCO", 46.07, "M = 2(12.011) + 1(15.999) + 6(1.008)", 9),
        ("N2", 28.01, "M = 2(14.007)", 2),
    ],
)
def test_molar_mass_keeps_hydrogens_of_ring_smiles_and_formulas_apart(
    formula: str, mass: float, substitution: str, atom_count: int
) -> None:
    assert molar_mass(formula) == pytest.approx(mass, abs=0.01)
    weighed = _solve(f"molar mass of {formula}")
    assert weighed.answer == f"M({formula}) = {mass:.2f} g/mol"
    assert weighed.substitution == (substitution,)
    counted = _solve(f"how many atoms in 1 mol of {formula}")
    assert counted.substitution == (
        f"N = (1 mol)(6.0221 × 10^23 mol⁻¹) × ({atom_count} atoms per {formula})",
    )


def test_limiting_reagent_keeps_micromole_yields() -> None:
    result = limiting_reagent("H2 + O2 -> H2O", {"H2": 2e-5, "O2": 1.0}, "H2O")
    assert result.limiting_reagent == "H2"
    assert result.product_amount == pytest.approx(2e-5)


def test_limiting_reagent_needs_an_amount_for_every_reactant() -> None:
    result = limiting_reagent("N2 + 3H2 -> 2NH3", {"N2": 1.0}, "NH3")
    assert result.error is not None and "H2" in result.error


def test_limiting_reagent_reports_a_tie() -> None:
    result = limiting_reagent("H2 + Cl2 -> 2HCl", {"H2": 1.0, "Cl2": 1.0}, "HCl")
    assert result.limiting_reagent == "H2" and result.tied == ("Cl2",)
    verified = _solve(
        "Find the limiting reagent and moles of HCl from 1 mol H2 and 1 mol Cl2 in H2 + Cl2 -> 2HCl"
    )
    assert verified.answer == "Limiting reagent = H2 and Cl2; 2.0 mol HCl"


def test_percent_composition_builds_the_molar_mass_from_the_atomic_masses() -> None:
    result = _solve("Find percent composition of O in H2O")
    # 15.999 / 18.015, not 16.00 / 18.02 (88.79%): a rounded molar mass moves the answer.
    assert result.answer == "O in H2O = 88.81%"
    assert result.substitution == (
        "M(H2O) = 2(1.008) + 1(15.999) = 18.015 g/mol",
        "% O = 1 × 15.999 / 18.015 × 100",
    )


def test_a_balance_check_compares_the_written_coefficients() -> None:
    right = _solve("Is 2H2 + O2 -> 2H2O balanced?")
    assert right.answer == "Yes, it is balanced: 2 H2 + O2 -> 2 H2O"
    wrong = _solve("Is 2H2 + O2 -> 3H2O balanced?")
    assert wrong.answer == "No, it is not balanced. Balanced: 2 H2 + O2 -> 2 H2O"
    bare = _solve("Is H2 + O2 -> H2O balanced?")
    assert bare.answer.startswith("No, it is not balanced")


def test_arrhenius_rate_constant_has_the_unit_of_the_frequency_factor() -> None:
    # k is 19.7; A = 1e10 has one significant figure, so it shows the two-figure floor.
    bare = _solve("Use Arrhenius equation with A=1e10, Ea=50 kJ, T=300 K")
    assert bare.answer == "k = 20"
    timed = _solve("Use Arrhenius equation with A=1e10 min^-1, Ea=50 kJ, T=300 K")
    assert timed.answer == "k = 20 min⁻¹"


def test_arrhenius_temperature_in_celsius_is_converted() -> None:
    kelvin = _solve("Use Arrhenius equation with A=1e10 s^-1, Ea=50 kJ, T=300 K")
    celsius = _solve("Use Arrhenius equation with A=1e10 s^-1, Ea=50 kJ, T=26.85 °C")
    assert _first_number(celsius.answer) == pytest.approx(_first_number(kelvin.answer), rel=1e-3)


def test_solubility_gives_ksp() -> None:
    result = _solve("Find Ksp when the molar solubility = 1.3e-5 M for AgCl(s) -> Ag+ + Cl-")
    assert result.answer == "Ksp = 1.7 × 10^-10"


def test_rate_law_refuses_a_held_second_reactant() -> None:
    with pytest.raises(SolveServiceError, match="order in B"):
        _solve("Find the rate law: a1=1, rate1=2, a2=2, rate2=4, b1=3, b2=3")


def test_rate_law_with_only_a_is_first_order() -> None:
    result = _solve("Find the rate law: a1=1, rate1=2, a2=2, rate2=4")
    assert result.answer == "rate = 2.0 [A]"


def test_rate_law_can_change_the_second_reactant() -> None:
    result = _solve("Find the rate law: a1=1, rate1=2, a2=1, rate2=8, b1=1, b2=2")
    assert result.answer == "rate = 2.0 [B]^2"
    # [A] stays 3 while [B] doubles twice, so k is rate1 / [B]^2, not rate1 / [A]^2.
    shifted = _solve("Find the rate law: a1=3, rate1=8, a2=3, rate2=32, b1=2, b2=4")
    assert shifted.answer == "rate = 2.0 [B]^2"
    assert shifted.substitution[-1] == "k = rate1 / [B]^2 = 8 / (2)^2 = 2.0"
    assert shifted.given[0] == "experiment 1: [A] = 3, [B] = 2, rate = 8"


def test_half_equivalence_uses_charge_balance_when_ka_is_not_small() -> None:
    result = _solve(
        "Weak acid strong base titration: Ma=0.01, Va=1 L, Mb=0.01, Vb=0.5 L, Ka=0.1, find pH"
    )
    assert result.answer == "pH = 2.50"
    assert any("charge balance" in line or "C − [H+]" in line for line in result.substitution)


def test_titration_regions_scale_with_the_amounts() -> None:
    """A 1e-5 mol titration used to be judged by an absolute 1e-6 mol tolerance."""
    half = _solve(
        "Weak acid strong base titration: Ma=0.001, Va=0.010 L, Mb=0.001, Vb=0.005 L, "
        "Ka=1.8e-5, find pH"
    )
    # Ka is about 5% of this buffer, so half-equivalence is the charge-balance root, not pKa.
    assert isinstance(half.scene, TitrationScene)
    assert half.scene.region == "half-equivalence"
    assert half.answer == "pH = 4.79"
    near = _solve(
        "Weak acid strong base titration: Ma=0.001, Va=0.010 L, Mb=0.001, Vb=0.00905 L, "
        "Ka=1.8e-5, find pH"
    )
    assert isinstance(near.scene, TitrationScene)
    assert near.scene.region == "buffer region"


def test_strong_titration_keeps_water_next_to_equivalence() -> None:
    at = _solve(
        "Strong acid strong base titration: Ma=0.10, Va=0.050 L, Mb=0.10, Vb=0.050 L, find pH"
    )
    assert at.answer == "pH = 7.00"
    near = _solve(
        "Strong acid strong base titration: Ma=0.10, Va=0.050 L, Mb=0.10, Vb=0.04999999 L, find pH"
    )
    assert 6.0 < _first_number(near.answer) < 7.0


def test_weak_titration_past_equivalence_keeps_water() -> None:
    """A 1e-8 M excess of strong base used to print pH 6 from 14 + log10(excess)."""
    past = _solve(
        "Weak acid strong base titration: Ma=0.10, Va=0.050 L, Mb=0.10, Vb=0.05000001 L, "
        "Ka=1.8e-5, find pH"
    )
    assert 7.0 < _first_number(past.answer) < 7.1
    assert any("water's own ions" in line and "where c = " in line for line in past.substitution)


def test_a_missing_ice_reactant_is_declined() -> None:
    with pytest.raises(SolveServiceError, match="I2"):
        _solve("Solve the ICE equilibrium for H2 + I2 -> 2HI when K=50 and [H2]=1")


def test_an_omitted_ice_product_stays_zero() -> None:
    result = _solve("Solve the ICE equilibrium for N2O4 <=> 2NO2 when K=0.2 and [N2O4]=0.5")
    assert "x = 0.14" in result.answer
    assert "[NO2] = 0.27 mol/L" in result.answer


def test_a_very_weak_acid_is_declined_instead_of_reporting_pH_7() -> None:
    with pytest.raises(SolveServiceError):
        _solve("Find the weak acid pH of 0.01 M HA when Ka=1e-12")


def test_weak_acid_reports_when_the_quadratic_matters() -> None:
    result = _solve("Find the weak acid pH of 0.001 M HA when Ka=1e-3")
    assert any("exact quadratic" in line for line in result.substitution)


def test_galvanic_cell_with_the_hydrogen_electrode() -> None:
    result = _solve("Find the galvanic cell for Zn and H")
    assert "Zn + 2 H+ -> Zn2+ + H2" in result.answer
    assert "E°cell = 0.76 V" in result.answer
    reverse = _solve("Find the galvanic cell for H and Cu")
    assert "H2 + Cu2+ -> 2 H+ + Cu" in reverse.answer


def test_galvanic_cell_balances_electrons_between_unequal_metals() -> None:
    result = _solve("Find the galvanic cell for Al and Cu")
    assert "2 Al + 3 Cu2+ -> 2 Al3+ + 3 Cu" in result.answer


def test_galvanic_cell_does_not_read_kelvin_as_potassium() -> None:
    result = _solve("Find the galvanic cell for Zn and Cu at 298 K")
    assert "anode: Zn\ncathode: Cu" in result.answer


def test_galvanic_cell_accepts_potassium_paired_with_another_metal() -> None:
    result = _solve("Find the galvanic cell for K and Cu")
    assert "anode: K\ncathode: Cu" in result.answer


@pytest.mark.parametrize(
    "element",
    [
        "O3",
        "O(g)",
        "Br2(g)",
        "Cl(g)",
        "H(g)",
        "I2(g)",
        "Na(g)",
        "P",
        "S",
        "P(s)",
        "S(s)",
        "H",
        "N",
        "O",
        "F",
        "Cl",
        "Br",
        "I",
    ],
)
def test_formation_enthalpy_is_zero_only_for_a_standard_state(element: str) -> None:
    with pytest.raises(SolveServiceError):
        _formation(element, {})


@pytest.mark.parametrize(
    "element",
    ["H2", "O2", "N2", "Cl2", "Br2(l)", "I2(s)", "Hg(l)", "C(s)", "Fe(s)", "Na", "He", "S8", "P4"],
)
def test_formation_enthalpy_of_a_standard_state_is_zero(element: str) -> None:
    assert _formation(element, {}) == 0.0


def test_formation_enthalpy_accepts_standard_state_elements() -> None:
    result = _solve("Find the formation enthalpy for C + O2 -> CO2 when ΔHf(CO2)=-393.5 kJ/mol")
    assert _first_number(result.answer) == pytest.approx(-393.5)
    liquid = _solve("Find the formation enthalpy for H2 + Br2(l) -> HBr when ΔHf(HBr)=-36.3 kJ/mol")
    assert _first_number(liquid.answer) == pytest.approx(2 * -36.3)


def test_formation_enthalpy_refuses_free_atoms() -> None:
    with pytest.raises(SolveServiceError):
        _solve("Find the formation enthalpy for H + Cl -> HCl when ΔHf(HCl)=-92.3 kJ/mol")


def test_formation_enthalpy_of_hydrogen_chloride_uses_the_molecular_elements() -> None:
    result = _solve("Find the formation enthalpy for H2 + Cl2 -> 2HCl when ΔHf(HCl)=-92.3 kJ/mol")
    assert _first_number(result.answer) == pytest.approx(-184.6)


def test_water_vapor_pressure_is_accurate_between_table_points() -> None:
    from app.modules.chemistry.solvers.constants import water_vapor_mmhg

    assert water_vapor_mmhg(25) == pytest.approx(23.76)
    assert water_vapor_mmhg(22) == pytest.approx(19.83, abs=0.03)
    assert water_vapor_mmhg(37) == pytest.approx(47.07, abs=0.15)
    assert water_vapor_mmhg(101) is None


# --- structure: Lewis / VSEPR / oxidation numbers ---------------------------------------


@pytest.mark.parametrize(
    ("formula", "center", "geometry", "angle", "polar", "bonds"),
    [
        ("AlCl3", "Al", "trigonal planar", "120°", False, (1, 1, 1)),
        ("SnCl2", "Sn", "bent", "less than 120°", True, (1, 1)),
        ("SOCl2", "S", "trigonal pyramidal", "less than 109.5°", True, (2, 1, 1)),
        ("POCl3", "P", "tetrahedral", "109.5°", True, (2, 1, 1, 1)),
        ("XeO3", "Xe", "trigonal pyramidal", "less than 109.5°", True, (2, 2, 2)),
        ("XeOF4", "Xe", "square pyramidal", "less than 90°", True, (2, 1, 1, 1, 1)),
        ("ClO4-", "Cl", "tetrahedral", "109.5°", False, (2, 2, 2, 1)),
        ("H2S", "S", "bent", "less than 109.5°", True, (1, 1)),
        ("PH3", "P", "trigonal pyramidal", "less than 109.5°", True, (1, 1, 1)),
        ("NF3", "N", "trigonal pyramidal", "less than 109.5°", True, (1, 1, 1)),
        ("H2O", "O", "bent", "104.5°", True, (1, 1)),
        ("NH3", "N", "trigonal pyramidal", "107°", True, (1, 1, 1)),
    ],
)
def test_vsepr_beyond_the_period_two_water_and_ammonia_cases(
    formula: str,
    center: str,
    geometry: str,
    angle: str,
    polar: bool,
    bonds: tuple[int, ...],
) -> None:
    structure = lewis_structure(formula)
    assert structure is not None
    assert (structure.central, structure.geometry, structure.bond_angle) == (
        center,
        geometry,
        angle,
    )
    assert structure.polar is polar
    assert structure.bond_orders == bonds
    assert structure.central_formal_charge == 0


@pytest.mark.parametrize("formula", ["N2O", "HOCl", "H2O2", "N2O4", "CH3COOH"])
def test_a_chain_or_an_unclear_center_is_not_a_single_center_structure(formula: str) -> None:
    assert lewis_structure(formula) is None


@pytest.mark.parametrize(
    "formula",
    [
        # Ionic salts (review, 2026-10-25: verified "linear, nonpolar"): a group 1 or 2 metal
        # other than beryllium, or any metal whose bonds are ionic.
        "CaCl2",
        "MgCl2",
        "MgBr2",
        "CaI2",
        "BaCl2",
        "SrCl2",
        "CaF2",
        "LiCl",
        "NaH",
        "AlF3",
        "SnF4",
        # Network solids: heavier group-14 atoms make no pi bonds.
        "SiO2",
        "GeO2",
        "SnO2",
        # Polarity that depends on which positions unlike atoms take.
        "PCl3F2",
        "PCl2F3",
        "SF4Cl2",
        "XeF2Cl2",
        # An oxoacid's hydrogen sits on oxygen, not on the centre.
        "HNO2",
        "HIO3",
    ],
)
def test_a_salt_a_network_solid_or_an_isomers_polarity_is_not_one_structure(formula: str) -> None:
    assert lewis_structure(formula) is None


@pytest.mark.parametrize(
    ("formula", "geometry", "polar"),
    [
        ("BeCl2", "linear", False),
        ("BeF2", "linear", False),
        ("BeF4^2-", "tetrahedral", False),
        ("H3O+", "trigonal pyramidal", True),
        ("BeH2", "linear", False),
        ("SnCl4", "tetrahedral", False),
        ("SiF4", "tetrahedral", False),
        ("CH2Cl2", "tetrahedral", True),
        ("CHCl3", "tetrahedral", True),
        ("CH2O", "trigonal planar", True),
        ("XeOF4", "square pyramidal", True),
        ("PCl5", "trigonal bipyramidal", False),
        ("SF6", "octahedral", False),
        ("XeF4", "square planar", False),
    ],
)
def test_covalent_centres_keep_their_shape_and_polarity(
    formula: str, geometry: str, polar: bool
) -> None:
    structure = lewis_structure(formula)
    assert structure is not None
    assert (structure.geometry, structure.polar) == (geometry, polar)


@pytest.mark.parametrize(
    ("formula", "states"),
    [
        ("ICl", {"I": 1, "Cl": -1}),
        ("IBr", {"I": 1, "Br": -1}),
        ("BrF", {"Br": 1, "F": -1}),
        ("NaBH4", {"Na": 1, "H": -1, "B": 3}),
        ("B2H6", {"B": 3, "H": -1}),
        ("PH3", {"P": -3, "H": 1}),
        ("H2O2", {"H": 1, "O": -1}),
        ("KMnO4", {"K": 1, "Mn": 7, "O": -2}),
    ],
)
def test_oxidation_states_follow_electronegativity(formula: str, states: dict[str, int]) -> None:
    assert oxidation_states(formula) == states


@pytest.mark.parametrize("formula", ["S2O8^2-", "CrO5", "KO2"])
def test_an_impossible_or_fractional_oxidation_state_is_refused(formula: str) -> None:
    assert oxidation_states(formula) is None


@pytest.mark.parametrize(
    ("formula", "name"),
    [
        ("[Co(NH3)6]Cl3", "hexaamminecobalt(III) chloride"),
        ("K4[Fe(CN)6]", "potassium hexacyanidoferrate(II)"),
        ("[Cu(NH3)4]SO4", "tetraamminecopper(II) sulfate"),
        ("[Co(NH3)6](NO3)3", "hexaamminecobalt(III) nitrate"),
        ("[Co(en)3]Cl3", "tris(ethylenediamine)cobalt(III) chloride"),
        ("K2[PtCl4]", "potassium tetrachloridoplatinate(II)"),
        ("K[Cr(ox)2]", "potassium bis(oxalato)chromate(III)"),
        ("Na3[Co(NO2)6]", "sodium hexanitrocobaltate(III)"),
        ("[Fe(CN)6]3-", "hexacyanidoferrate(III)"),
        ("[Fe(H2O)6]3+", "hexaaquairon(III)"),
        ("[Cu(NH3)4]2+", "tetraamminecopper(II)"),
    ],
)
def test_coordination_names_use_the_final_charge_and_latin_ate_stems(
    formula: str, name: str
) -> None:
    complex_ = parse_complex_formula(formula)
    assert complex_ is not None
    assert complex_.name == name


@pytest.mark.parametrize(
    "formula", ["[Xx(NH3)6]Cl3", "[Na(NH3)6]Cl", "[Co(NH3)6]Zz", "[Co(Qq)6]Cl3", "K2[CrO4]"]
)
def test_an_unnamed_metal_ligand_or_counter_ion_is_refused(formula: str) -> None:
    assert parse_complex_formula(formula) is None


def test_a_charge_suffix_cannot_be_combined_with_counter_ions() -> None:
    assert parse_complex_formula("K3[Fe(CN)6]3-") is None


def test_a_numeric_magnetic_moment_is_not_a_complex() -> None:
    assert (
        extract_chemistry_intent(
            "A magnetic moment of 0.200 A m^2 is in a 0.500 T field at 30 degrees. Find the torque."
        )
        is None
    )


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Find the magnetic moment of [Co(NH3)6]3+", "low-spin d6, 0 unpaired"),
        ("Find the crystal field of [Co(en)3]Cl3", "low-spin d6, 0 unpaired"),
        ("Find the crystal field of [Fe(H2O)6]Cl2", "high-spin d6, 4 unpaired"),
        ("Find the crystal field of K4[Fe(CN)6]", "low-spin d6, 0 unpaired"),
    ],
)
def test_crystal_field_spin_follows_the_ligand_set(question: str, expected: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is not None
    assert expected in solve_chemistry(intent).answer


def test_crystal_field_refuses_when_the_spin_depends_on_the_metal() -> None:
    intent = extract_chemistry_intent("Find the crystal field of [Fe(NH3)6]2+")
    assert intent is not None
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)
    oxalate = extract_chemistry_intent("Find the crystal field of [Co(ox)3]3-")
    assert oxalate is not None
    with pytest.raises(SolveServiceError, match="depends on the metal"):
        solve_chemistry(oxalate)
    pyridine = extract_chemistry_intent("Find the crystal field of [Co(py)6]3+")
    assert pyridine is not None
    with pytest.raises(SolveServiceError, match="depends on the metal"):
        solve_chemistry(pyridine)


def test_the_coordination_name_question_accepts_a_charged_ion_and_trailing_punctuation() -> None:
    intent = extract_chemistry_intent("Name the coordination complex [Fe(CN)6]3-?")
    assert intent is not None
    answer = solve_chemistry(intent).answer
    assert "hexacyanidoferrate(III)" in answer
    assert "Fe oxidation state: +3" in answer


@pytest.mark.parametrize(
    ("equation", "shown"),
    [
        ("7Be + e- -> 7Li", "7Be + e- → 7Li"),
        ("11C->11B+e+", "11C → 11B + e+"),
        ("11C -> 11B + β+", "11C → 11B + e+"),
        ("238U -> 234Th + α", "238U → 234Th + 4He"),
        ("^{238}_{92}U -> ^{234}_{90}Th + alpha", "238U → 234Th + 4He"),
        ("U-238 -> Th-234 + alpha", "238U → 234Th + 4He"),
        ("235U + n -> 141Ba + 92Kr + 3n", "235U + 1n → 141Ba + 92Kr + 3 1n"),
        ("60Co -> 60Ni + β- + γ", "60Co → 60Ni + e- + γ"),
        ("14N + alpha -> 17O + p", "14N + 4He → 17O + 1H"),
        ("20Ne + 4He -> 23Mg + n", "20Ne + 4He → 23Mg + 1n"),
    ],
)
def test_nuclear_equations_accept_written_particles(equation: str, shown: str) -> None:
    balanced = balance_nuclear(equation)
    assert balanced.balanced
    assert format_nuclear(balanced) == shown


def test_electron_capture_keeps_the_captured_electron() -> None:
    captured = balance_nuclear("7Be -> 7Li")
    assert not captured.balanced  # a nucleon count alone cannot balance the charge
    assert format_nuclear(balance_nuclear("7Be + e- -> 7Li")) == "7Be + e- → 7Li"


@pytest.mark.parametrize(
    "equation",
    [
        "1H -> 1He",  # more protons than nucleons
        "238U -> 200Th + 38He",  # 38He is not a nuclide
        "238U -> 234Th",  # charge and mass are missing a product
        "1H + 1H -> 2H + e+ + ?",  # a neutrino is not modelled, so the rest is not unique
        "238U -> ?",
    ],
)
def test_impossible_or_incomplete_nuclear_equations_are_not_balanced(equation: str) -> None:
    assert not balance_nuclear(equation).balanced


@pytest.mark.parametrize(
    ("question", "answer", "note"),
    [
        ("molecular ion of C2H6O", "M+ = 46.0419 (nominal m/z 46)", None),
        ("molecular ion of SMILES CCO", "M+ = 46.0419 (nominal m/z 46)", None),
        ("molecular ion of CH3Cl", "M+ = 49.9923 (nominal m/z 50)", "35Cl : 37Cl = 3 : 1"),
        ("molecular ion of CH3Br", "M+ = 93.9418 (nominal m/z 94)", "79Br : 81Br = 1 : 1"),
        ("molecular ion of CH2Cl2", "M+ = 83.9534 (nominal m/z 84)", "M+4"),
    ],
)
def test_molecular_ion_is_the_monoisotopic_mass_not_the_molar_mass(
    question: str, answer: str, note: str | None
) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is not None
    result = solve_chemistry(intent)
    assert result.answer == answer
    if note is None:
        assert not any("M+2" in line for line in result.substitution)
    else:
        assert note in result.substitution[-1]


def test_a_labelled_isotope_smiles_has_no_molecular_ion() -> None:
    intent = ChemistryIntent(kind="spectroscopy", chemistry_op="molecular_ion", formula="[13CH4]")
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)


@pytest.mark.parametrize(
    ("smiles", "groups"),
    [
        ("CC(=O)C(=O)O", {"carboxylic acid", "ketone"}),  # pyruvic acid
        ("OCC(=O)O", {"carboxylic acid", "alcohol"}),  # glycolic acid
        ("C=Cc1ccccc1", {"alkene", "aromatic"}),  # styrene
        ("NC(=O)CC(N)C(=O)O", {"carboxylic acid", "amide", "amine"}),  # asparagine
        ("OC=O", {"carboxylic acid"}),  # formic acid is not an aldehyde
        ("COC=O", {"ester"}),  # nor is methyl formate
        ("NC=O", {"amide"}),  # nor formamide
        ("C=O", {"aldehyde"}),
        ("CC=O", {"aldehyde"}),
        ("CN(C)C", {"tertiary amine"}),
        ("CC(=O)OC", {"ester"}),  # the ester oxygen is not an ether
        ("CCOCC", {"ether"}),
        ("C[N+](=O)[O-]", {"nitro"}),
        ("CCS", {"thiol"}),
        ("CC(Cl)=O", {"acyl halide"}),
        ("CC(=O)OC(C)=O", {"anhydride"}),  # an anhydride is not an ester or a ketone
        ("Clc1ccccc1", {"aryl halide", "aromatic"}),
    ],
)
def test_functional_groups_are_matched_atom_by_atom(smiles: str, groups: set[str]) -> None:
    facts = organic_facts(smiles)
    assert facts is not None
    assert set(facts.groups) == groups


def test_stereo_labels_are_one_based_cip_labels() -> None:
    alanine = organic_facts("C[C@H](N)C(=O)O")
    trans = organic_facts("C/C=C/C")
    cis = organic_facts("C/C=C\\C")
    bare = organic_facts("CC=CC")
    lactic = organic_facts("CC(O)C(=O)O")
    assert alanine is not None and alanine.chirality == ("atom 2 (C): S",)
    assert trans is not None and trans.double_bond_stereo == ("C2=C3: E",)
    assert cis is not None and cis.double_bond_stereo == ("C2=C3: Z",)
    assert bare is not None and bare.double_bond_stereo == ("C2=C3: unspecified",)
    assert lactic is not None and lactic.chirality == ("atom 2 (C): unspecified",)


def test_an_oversized_smiles_is_not_parsed() -> None:
    assert organic_facts("C" * 501) is None


@pytest.mark.parametrize(
    ("reaction", "smiles", "product"),
    [
        ("hbr", "CC=CC", "CCC(C)Br"),  # a symmetric alkene: both faces give the same product
        ("hbr", "C=CC", "CC(C)Br"),  # Markovnikov
        ("hbr", "CCC=CC", None),  # 2-pentene: two products, none preferred
        ("hbr", "C=COC", None),  # the ether oxygen, not alkyl count, directs the addition
        ("hcl", "C=CC", "CC(C)Cl"),
        ("hcl", "CC=CC", "CCC(C)Cl"),
        ("hcl", "CCC=CC", None),
        ("hi", "C=CC", "CC(C)I"),
        ("hi", "CCC=CC", None),
        ("hydrogenation", "C=CC", "CCC"),
        ("hydrogenation", "CC=CC", "CCCC"),
        ("hydrogenation", "C=CC=C", None),  # two alkenes are not one addition
        ("bromine", "CC=CC", "CC(Br)C(C)Br"),
        ("hydroxide", "CCl", "CO"),  # methyl
        ("hydroxide", "CCCl", "CCO"),
        ("hydroxide", "CC(Cl)C", None),  # secondary
        ("hydroxide", "C=CCl", None),  # a vinyl halide is not an SN2 substrate
        ("hydroxide", "CC(Br)CBr", None),  # a second halogen makes the site ambiguous
        ("hydroxide", "Clc1ccccc1", None),
    ],
)
def test_named_reactions_refuse_an_ambiguous_product(
    reaction: str, smiles: str, product: str | None
) -> None:
    assert named_product(reaction, smiles) == product


def test_molarity_and_molality_refuse_a_negative_amount() -> None:
    with pytest.raises(SolveServiceError):
        _solve("Find the molarity of -2 mol in 1 L")
    with pytest.raises(SolveServiceError):
        _solve("Find the molality of -2 mol in 1 kg")


def test_standard_addition_refuses_a_spiked_signal_below_the_sample() -> None:
    with pytest.raises(SolveServiceError):
        _solve(
            "Standard addition: sample signal=5, spiked signal=2, "
            "standard concentration=1, standard volume=1, sample volume=1"
        )


@pytest.mark.parametrize(
    ("capital", "lower"),
    [
        (
            "Use Hess's law: ΔH1=-200 kJ, multiplier1=1, ΔH2=50 kJ, multiplier2=2",
            "Use hess's law: ΔH1=-200 kJ, multiplier1=1, ΔH2=50 kJ, multiplier2=2",
        ),
        (
            "Find Kp for CaCO3(s) -> CaO(s) + CO2(g) when P(CO2)=0.2 atm",
            "find kp for CaCO3(s) -> CaO(s) + CO2(g) when P(CO2)=0.2 atm",
        ),
        (
            "Convert Kc to Kp: Kc=0.5 at T=298 K for N2 + H2 -> NH3",
            "convert kc to kp: Kc=0.5 at T=298 K for N2 + H2 -> NH3",
        ),
        (
            "Solve the ICE equilibrium for N2O4 -> NO2 when K=4 and [N2O4]=1",
            "solve the ice equilibrium for N2O4 -> NO2 when K=4 and [N2O4]=1",
        ),
    ],
)
def test_lowercase_cues_extract_the_same_operation(capital: str, lower: str) -> None:
    expected = extract_chemistry_intent(capital)
    actual = extract_chemistry_intent(lower)
    assert expected is not None and actual is not None
    assert actual.chemistry_op == expected.chemistry_op


def test_nmr_methyl_region_is_not_labeled_amine_alone() -> None:
    result = _solve("NMR peak 1.2")
    assert "alkyl" in result.answer
    assert result.answer != "amine"


def test_esterification_needs_an_alcohol_partner_not_an_acid() -> None:
    assert named_product("esterification", "CC(=O)O", "CCO") == "CCOC(C)=O"
    assert named_product("esterification", "CC(=O)O", "OC(=O)C") is None


@pytest.mark.parametrize(
    ("kind", "operation", "params"),
    [
        ("kinetics", "arrhenius_two_point", {"k1": 0.1, "t1": 300.0, "k2": 0.4}),
        ("kinetics", "rate_law", {"a1": 0.1, "rate1": 0.02, "a2": 0.2}),
        (
            "analytical",
            "standard_addition",
            {
                "sample_signal": 2.0,
                "spiked_signal": 5.0,
                "standard_concentration": 1.0,
                "standard_volume": 1.0,
            },
        ),
    ],
)
def test_a_missing_input_is_refused_not_defaulted(
    kind: ChemistryKind, operation: str, params: dict[str, float]
) -> None:
    intent = ChemistryIntent(kind=kind, chemistry_op=operation, params=params)
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)
