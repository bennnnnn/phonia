"""Laws a school chemistry question asks that the catalog did not answer before.

The answers are hand-worked in ``new_law_cases.py`` and the corpus; these tests pin what each
reader takes, what it declines, and the units a question may write.
"""

from __future__ import annotations

import pytest

from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.solvers import solve_chemistry
from app.modules.chemistry.solvers.types import format_number
from app.modules.chemistry.species_facts import dissolution_equation
from app.services.solving import SolveServiceError
from app.services.subjects.dispatch import detect_subject


def _answer(question: str) -> str | None:
    intent = extract_chemistry_intent(question)
    return None if intent is None else solve_chemistry(intent).answer


@pytest.mark.parametrize(
    ("formula", "equation"),
    [
        ("AgCl", "AgCl(s) -> Ag+ + Cl-"),
        ("CaF2", "CaF2(s) -> Ca2+ + F-"),
        ("Ag2CrO4", "Ag2CrO4(s) -> Ag+ + CrO4^2-"),
        ("Ca3(PO4)2", "Ca3(PO4)2(s) -> Ca2+ + PO4^3-"),
        # The cation's charge is the one that makes the salt neutral.
        ("Fe(OH)3", "Fe(OH)3(s) -> Fe3+ + OH-"),
        ("Bi2S3", "Bi2S3(s) -> Bi3+ + S^2-"),
        # Not salts: an acid, a molecule, a hydrocarbon.
        ("HCl", None),
        ("H2O", None),
        ("CH4", None),
    ],
)
def test_a_salt_formula_gives_its_dissolution(formula: str, equation: str | None) -> None:
    assert dissolution_equation(formula) == equation


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("The Ksp of AgCl is 1.8 × 10^-10. Find its molar solubility.", "s = 1.3 × 10^-5 mol/L"),
        ("Ksp(PbI2) = 7.1e-9. What is the molar solubility?", "s = 0.0012 mol/L"),
        ("The molar solubility of PbI2 is 1.5 × 10^-3 M. Find Ksp.", "Ksp = 1.4 × 10^-8"),
    ],
)
def test_a_solubility_product_reads_the_salt_by_its_formula(question: str, answer: str) -> None:
    assert _answer(question) == answer


def test_partial_pressures_listed_in_words_are_numbered_in_order() -> None:
    intent = extract_chemistry_intent(
        "The partial pressures are 0.30 atm, 0.50 atm and 0.20 atm. Find the total pressure."
    )
    assert intent is not None
    result = solve_chemistry(intent)
    assert result.given == ("P₁ = 0.30 atm", "P₂ = 0.50 atm", "P₃ = 0.20 atm")
    assert result.answer == "Ptotal = 1.00 atm"


def test_a_stated_total_is_not_a_partial_pressure() -> None:
    question = (
        "The total pressure is 2 atm and the partial pressures are 0.3 atm and 0.5 atm. "
        "Find the third."
    )
    assert extract_chemistry_intent(question) is None


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Compare the rates of effusion of H2 and O2.", "rate(H2) / rate(O2) = 3.984"),
        # Gases named in words; a noble gas is a single atom.
        (
            "How many times faster does helium effuse than oxygen?",
            "rate(He) / rate(O2) = 2.827",
        ),
        # "Times slower" asks how many times the second gas outpaces the first.
        ("How many times slower does O2 effuse than H2?", "rate(H2) / rate(O2) = 3.984"),
    ],
)
def test_grahams_law_compares_two_named_gases(question: str, answer: str) -> None:
    assert _answer(question) == answer


@pytest.mark.parametrize(
    "question",
    [
        "How many times longer does it take O2 to effuse than H2?",
        "Which gas effuses faster and which slower, H2 or O2?",
    ],
)
def test_grahams_law_declines_a_time_or_an_unclear_direction(question: str) -> None:
    # A time ratio is the inverse of the rate ratio; asked both ways, the direction is unclear.
    assert extract_chemistry_intent(question) is None


def test_a_particle_count_divides_by_avogadros_number_as_one_quantity() -> None:
    intent = extract_chemistry_intent("How many grams do 3.01 × 10^23 molecules of H2O weigh?")
    assert intent is not None
    assert solve_chemistry(intent).substitution == (
        "m = [3.01 × 10^23 / (6.0221 × 10^23 mol⁻¹)](18.015 g/mol)",
    )


def test_grahams_law_with_a_stated_rate_declines() -> None:
    # A rate or a time is another Graham question, not the ratio of two known gases.
    question = "H2 effuses at 4.0 mL/s. How fast does O2 effuse by Graham's law?"
    assert extract_chemistry_intent(question) is None


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("How many grams of oxygen are in 10.0 g of H2O?", "m(O) = 8.88 g"),
        ("Find the mass of carbon in 50.0 g of glucose.", "m(C) = 20.0 g"),
        # The element is not in the compound.
        ("How many grams of sulfur are in 10.0 g of H2O?", None),
    ],
)
def test_an_elements_mass_in_a_sample(question: str, answer: str | None) -> None:
    assert _answer(question) == answer


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        # Unstated masses come from the isotope table, not the mass numbers (35.48 u).
        (
            "Chlorine has isotopes 35Cl (75.77%) and 37Cl (24.23%). Find its average atomic mass.",
            "A(Cl) = 35.45 u",
        ),
        (
            "Copper has two isotopes: Cu-63 (62.93 amu, 69.17%) and Cu-65 (64.93 amu, 30.83%). "
            "Calculate the average atomic mass of copper.",
            "A(Cu) = 63.55 u",
        ),
        # Abundances that do not make 100% are a different question.
        ("Chlorine has isotopes 35Cl (70%) and 37Cl (20%). Find its average atomic mass.", None),
        # An isotope the table lacks, with no stated mass.
        ("Tin has isotopes Sn-118 (50%) and Sn-120 (50%). Find its average atomic mass.", None),
    ],
)
def test_an_average_atomic_mass_weights_isotope_masses(question: str, answer: str | None) -> None:
    assert _answer(question) == answer


@pytest.mark.parametrize(
    "question",
    [
        # 1 + 1 -> 1 is not the balanced equation.
        "What is the atom economy of H2 + O2 -> H2O?",
        # Two products, and the question does not say which mass is desired.
        "What is the atom economy of CH3COOH + CH3OH -> CH3COOCH3 + H2O?",
    ],
)
def test_atom_economy_declines_an_unbalanced_or_unnamed_product(question: str) -> None:
    assert extract_chemistry_intent(question) is None


def test_atom_economy_prints_each_coefficient() -> None:
    question = "What is the atom economy of NH3 in N2 + 3 H2 -> 2 NH3?"
    intent = extract_chemistry_intent(question)
    assert intent is not None
    result = solve_chemistry(intent)
    assert result.answer == "Atom economy of NH3 = 100%"
    assert result.formula == "% atom economy = 2 M(NH3) / (M(N2) + 3 M(H2)) × 100"


def test_atom_economy_names_a_product_without_its_phase() -> None:
    question = "What is the atom economy of CaO in CaCO3(s) -> CaO(s) + CO2(g)?"
    intent = extract_chemistry_intent(question)
    assert intent is not None and intent.target == "CaO(s)"
    assert solve_chemistry(intent).answer.startswith("Atom economy of CaO(s) = ")


def test_atom_economy_keeps_the_phase_the_question_names() -> None:
    question = "What is the atom economy of H2O(l) in 2 H2 + O2 -> H2O(l) + H2O(g)?"
    intent = extract_chemistry_intent(question)
    assert intent is not None and intent.target == "H2O(l)"
    unnamed = "What is the atom economy of H2O in 2 H2 + O2 -> H2O(l) + H2O(g)?"
    assert extract_chemistry_intent(unnamed) is None


def test_atom_economy_does_not_treat_a_charged_name_as_the_neutral_product() -> None:
    charged = "What is the atom economy of KCl+ in 2 KClO3 -> 2 KCl + 3 O2?"
    assert extract_chemistry_intent(charged) is None
    neutral = "What is the atom economy of KCl in 2 KClO3 -> 2 KCl + 3 O2?"
    intent = extract_chemistry_intent(neutral)
    assert intent is not None and intent.target == "KCl"


def test_atom_economy_declines_a_spectator_or_a_charge_the_question_did_not_name() -> None:
    spectator = "What is the atom economy of H2O in Pt + 2 H2 + O2 -> Pt + 2 H2O?"
    neutral = "What is the atom economy of NH4 in NH4Cl -> NH4+ + Cl-?"
    assert extract_chemistry_intent(spectator) is None
    assert extract_chemistry_intent(neutral) is None
    ion = "What is the atom economy of NH4+ in NH4Cl -> NH4+ + Cl-?"
    intent = extract_chemistry_intent(ion)
    assert intent is not None and intent.target == "NH4+"


def test_atom_economy_accepts_a_common_multiple_of_the_coefficients() -> None:
    question = "What is the atom economy of H2O in 4 H2 + 2 O2 -> 4 H2O?"
    assert _answer(question) == "Atom economy of H2O = 100%"


def test_ppm_allows_no_solute_and_rejects_a_solute_heavier_than_the_solution() -> None:
    assert _answer("What is the ppm of 0 mg of solute in 1.00 kg of solution?") == "ppm = 0 ppm"
    heavier = extract_chemistry_intent("What is the ppm of 2 kg of solute in 1 kg of solution?")
    assert heavier is not None
    with pytest.raises(SolveServiceError):
        solve_chemistry(heavier)


def test_diprotic_steps_past_the_first_dissociation() -> None:
    amphiprotic = "What is the pH of an amphiprotic solution with pKa1 = 4.00 and pKa2 = 9.00?"
    second = "What is [A2-] for a diprotic acid with Ka2 = 1.0e-8?"
    assert _answer(amphiprotic) == "pH = 6.50"
    assert _answer(second) == "[A2-] = 1.0 × 10^-8 mol/L"
    from_ka = "What is the pH of the intermediate form when Ka1 = 1.0e-4 and Ka2 = 1.0e-9?"
    assert _answer(from_ka) == "pH = 6.50"
    swapped = extract_chemistry_intent(
        "What is the pH of an amphiprotic solution with pKa1 = 9.00 and pKa2 = 4.00?"
    )
    assert swapped is not None and swapped.chemistry_op == "amphiprotic_ph"
    with pytest.raises(SolveServiceError):
        solve_chemistry(swapped)
    strong_second = extract_chemistry_intent("What is [A2-] when Ka2 = 0.012?")
    assert strong_second is not None and strong_second.chemistry_op == "diprotic_a2"
    with pytest.raises(SolveServiceError):
        solve_chemistry(strong_second)
    assert (
        extract_chemistry_intent("What is the pH of an amphiprotic solution with pKa1 = 4.00?")
        is None
    )
    # Mentioning A2- in a pH question, or stating [A2-] as a given, is not that ask.
    mentioned = (
        "What is the pH of 0.10 M H2A? Ka = 1.0e-4. The acid also forms A2- with Ka2 = 1.0e-8."
    )
    acid = extract_chemistry_intent(mentioned)
    assert acid is None or acid.chemistry_op != "diprotic_a2"
    given = "Ka2 = 1.0e-8 and [A2-] = 1.0e-6. What is the ratio?"
    ratio = extract_chemistry_intent(given)
    assert ratio is None or ratio.chemistry_op != "diprotic_a2"
    typeset = "What is [A\u00b2\u207b] for a diprotic acid with Ka2 = 1.0e-8?"
    assert _answer(typeset) == "[A2-] = 1.0 \u00d7 10^-8 mol/L"
    deprotonated = "What is the concentration of the fully deprotonated form if Ka2 = 1.0e-8?"
    assert _answer(deprotonated) == "[A2-] = 1.0 \u00d7 10^-8 mol/L"
    hydrogen = "What is the concentration of H+ in a diprotic acid that also forms A2-? Ka2 = 1e-8"
    asked = extract_chemistry_intent(hydrogen)
    assert asked is None or asked.chemistry_op != "diprotic_a2"
    crowded = "What is [A2-] in 1.0e-10 M diprotic H2A with Ka1 = 1e-4 and Ka2 = 1e-8?"
    too_much = extract_chemistry_intent(crowded)
    assert too_much is not None and too_much.chemistry_op == "diprotic_a2"
    with pytest.raises(SolveServiceError):
        solve_chemistry(too_much)
    dilute = "What is the pH of a 1e-10 M amphiprotic salt with pKa1 = 4.00 and pKa2 = 9.00?"
    trace = extract_chemistry_intent(dilute)
    assert trace is not None and trace.chemistry_op == "amphiprotic_ph"
    with pytest.raises(SolveServiceError):
        solve_chemistry(trace)
    stated = "What is the pH of a 0.10 M amphiprotic solution with pKa1 = 4.00 and pKa2 = 9.00?"
    assert _answer(stated) == "pH = 6.50"


def test_binary_vapor_pressure_rejects_fractions_that_do_not_sum_to_one() -> None:
    question = (
        "What is the total vapor pressure if the mole fraction of A is 0.400, "
        "the vapor pressure of A is 0.800 atm, the mole fraction of B is 0.700, "
        "and the vapor pressure of B is 0.400 atm?"
    )
    intent = extract_chemistry_intent(question)
    assert intent is not None
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)


def test_van_t_hoff_declines_without_both_temperatures_and_the_known_constant() -> None:
    question = "Use the van 't Hoff equation. K1 = 1.00 and T1 = 300 K. What is K2?"
    assert extract_chemistry_intent(question) is None


@pytest.mark.parametrize(
    "question",
    [
        # The closed apostrophe is the common spelling; the gate already accepts it.
        "Use van't Hoff: K1 = 1.0, T1 = 300 K, T2 = 350 K, ΔH = 50 kJ/mol; find K2",
        # Typeset working copies K2 and T1 back as K₂ and T₁.
        "Use van't Hoff: K₁ = 1.0, T₁ = 300 K, T₂ = 350 K, ΔH = 50 kJ/mol; find K₂",
    ],
)
def test_van_t_hoff_accepts_the_closed_apostrophe_and_subscripted_labels(question: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is not None
    assert intent.chemistry_op == "vant_hoff_constant"
    assert intent.params == pytest.approx({"k1": 1.0, "t1": 300.0, "t2": 350.0, "enthalpy": 50.0})


def test_subscripted_van_t_hoff_labels_keep_the_hand_worked_answers() -> None:
    constant = (
        "Use the van 't Hoff equation. K₁ = 1.00, T₁ = 300 K, T₂ = 350 K, "
        "and ΔH = 50.0 kJ/mol. What is K₂?"
    )
    enthalpy = (
        "Use the van 't Hoff equation. K₁ = 0.10, T₁ = 300 K, K₂ = 0.50, "
        "and T₂ = 350 K. What is ΔH?"
    )
    assert _answer(constant) == "K2 = 17.5"
    assert _answer(enthalpy) == "ΔH° = 28 kJ/mol"


def test_gibbs_and_vant_hoff_enthalpy_show_the_joule_to_kilojoule_step() -> None:
    gibbs = extract_chemistry_intent("K = 10 at 298.15 K. What is ΔG°?")
    enthalpy = extract_chemistry_intent(
        "Use the van 't Hoff equation. K1 = 0.10, T1 = 300 K, K2 = 0.50, "
        "and T2 = 350 K. What is ΔH?"
    )
    assert gibbs is not None and enthalpy is not None
    assert solve_chemistry(gibbs).substitution == (
        "ΔG° = −(8.3145 J/(mol·K))(298.15) ln(10) / 1000",
    )
    assert solve_chemistry(enthalpy).substitution == (
        "ΔH° = [−(8.3145 J/(mol·K)) ln(0.50/0.10) / (1/350 − 1/300)] / 1000",
    )
    assert solve_chemistry(gibbs).answer == "ΔG° = -5.7 kJ/mol"
    assert solve_chemistry(enthalpy).answer == "ΔH° = 28 kJ/mol"


def test_a_redox_pair_gains_water_protons_and_electrons_for_its_medium() -> None:
    acidic = "Balance the half-reaction Cr2O7^2- -> Cr3+ in acidic solution."
    basic = "Balance the half-reaction MnO4- -> MnO2 in basic solution."
    assert _answer(acidic) == "Cr2O7^2- + 14 H+ + 6 e- -> 2 Cr3+ + 7 H2O"
    assert _answer(basic) == "MnO4- + 2 H2O + 3 e- -> MnO2 + 4 OH-"
    oxidation = "Balance Fe2+ -> Fe3+ in acidic solution."
    assert _answer(oxidation) == "Fe2+ -> Fe3+ + e-"
    # The pair itself may be water or H+. Those are not only species we add.
    assert _answer("Balance O2 -> H2O in acidic solution.") == "O2 + 4 H+ + 4 e- -> 2 H2O"
    assert _answer("Balance H+ -> H2 in acidic solution.") == "2 H+ + 2 e- -> H2"


def test_a_half_reaction_declines_when_the_oxidation_state_or_the_equation_is_wider() -> None:
    ambiguous = extract_chemistry_intent("Balance FeS -> Fe2+ in acidic solution.")
    assert ambiguous is not None and ambiguous.chemistry_op == "half_reaction"
    with pytest.raises(SolveServiceError):
        solve_chemistry(ambiguous)
    wider = "Balance MnO4- + Fe2+ -> Mn2+ + Fe3+ in acidic solution."
    intent = extract_chemistry_intent(wider)
    assert intent is None or intent.chemistry_op != "half_reaction"
    bare = extract_chemistry_intent("Balance MnO4- -> Mn2+.")
    assert bare is None or bare.chemistry_op != "half_reaction"
    # Acidic medium alone is not a request to balance the pair.
    gibbs = extract_chemistry_intent(
        "For Fe2+ -> Fe3+ in acidic solution, calculate ΔG° when E° = 0.77 V and n = 1"
    )
    assert gibbs is not None and gibbs.chemistry_op == "cell_gibbs"
    # No oxidation-number change stays with the ordinary balancer.
    unchanged = "Balance N2O4 -> NO2 in acidic solution."
    intent = extract_chemistry_intent(unchanged)
    assert intent is not None and intent.chemistry_op == "balance"
    assert _answer(unchanged) == "N2O4 -> 2 NO2"
    # A one-element ion may have a fractional average oxidation number.
    assert _answer("Balance the half-reaction O2 -> O2- in acidic solution.") == "O2 + e- -> O2-"
    for question in (
        "Balance H2O -> H2 in acidic solution.",
        "Balance H2 -> H2O in acidic solution.",
    ):
        water = extract_chemistry_intent(question)
        assert water is not None and water.chemistry_op == "half_reaction"
        with pytest.raises(SolveServiceError):
            solve_chemistry(water)


def test_binary_vapor_pressure_declines_when_only_one_pressure_is_stated() -> None:
    question = (
        "What is the total vapor pressure if the mole fraction of A is 0.400, "
        "the vapor pressure of A is 0.800 atm, and the mole fraction of B is 0.600?"
    )
    assert extract_chemistry_intent(question) is None


def test_an_ions_electron_configuration_is_not_the_atoms() -> None:
    assert _answer("What is the electron configuration of copper?") == "Cu: [Ar] 3d^10 4s^1"
    assert extract_chemistry_intent("Write the electron configuration of Fe3+.") is None


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("What is the pH of 5 mM HCl?", "pH = 2.30"),
        ("What is the pH of a 250 µM HNO3 solution?", "pH = 3.602"),
        ("How much heat is released when 2.0 mol react if ΔH = -10 kcal/mol?", "q = -84 kJ"),
        (
            "Vmax = 10 μmol/min, Km = 2.0 mM and [S] = 2.0 mM. Find the reaction rate.",
            "v = 5.0 μmol/min",
        ),
    ],
)
def test_millimolar_micromolar_and_kilocalories_are_converted(question: str, answer: str) -> None:
    assert _answer(question) == answer


def test_a_template_never_reads_a_millimolar_value_as_molar() -> None:
    # The labelled dilution template would take 5 mM as 5 M; such a question goes unread.
    assert extract_chemistry_intent("Dilution: M1 = 5 mM, V1 = 10 mL, V2 = 50 mL. Find M2.") is None


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("What volume of 6.0 M HCl is needed to make 500 mL of 1.5 M HCl?", "V1 = 1.3 × 10^2 mL"),
        (
            "How many liters of 18 M H2SO4 do you need to make 2.0 L of 3.0 M H2SO4?",
            "V1 = 0.33 L",
        ),
    ],
)
def test_a_dilution_finds_the_stock_volume(question: str, answer: str) -> None:
    assert _answer(question) == answer


def test_dilute_this_volume_to_a_weaker_concentration_finds_the_final_volume() -> None:
    assert _answer("Dilute 10 mL of 2 M HCl to 0.5 M") == "V2 = 40 mL"


def test_a_stock_weaker_than_its_dilution_has_no_answer() -> None:
    intent = extract_chemistry_intent(
        "What volume of 0.5 M NaCl is needed to make 100 mL of 2 M NaCl?"
    )
    assert intent is not None
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)


def test_a_first_order_half_life_gives_k_per_its_time_unit() -> None:
    assert _answer("The half-life of a first-order reaction is 20.0 min. Find k.") == (
        "k = 0.0347 min⁻¹"
    )
    assert _answer(
        "A first-order reaction has a half-life of 3.0 hours. What is the rate constant?"
    ) == ("k = 0.23 h⁻¹")


def test_an_ice_table_reads_a_chain_of_equal_concentrations() -> None:
    intent = extract_chemistry_intent(
        "For H2 + I2 ⇌ 2HI, Kc = 50 and the initial [H2] = [I2] = 1.0 M. "
        "Find the equilibrium concentrations."
    )
    assert intent is not None
    assert intent.species == {"H2": 1.0, "I2": 1.0}


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "25.0 mL of NaOH is neutralized by 20.0 mL of 0.100 M HCl. "
            "Find the concentration of the NaOH.",
            "C₂ = 0.0800 mol/L",
        ),
        # H2SO4 gives two protons: it neutralizes twice its amount of NaOH.
        (
            "40.0 mL of NaOH is neutralized by 25.0 mL of 0.0500 M H2SO4. "
            "Find the concentration of the NaOH.",
            "C₂ = 0.0625 mol/L",
        ),
    ],
)
def test_a_neutralization_finds_the_unknown_concentration(question: str, answer: str) -> None:
    assert _answer(question) == answer


@pytest.mark.parametrize(
    "question",
    [
        "25.0 mL of NaOH is neutralized by 20.0 mL of 0.100 M HCl. Find the concentration.",
        "Compare the rates of effusion of H2 and O2.",
        "How many grams of oxygen are in 10 g of H2O?",
        "Vmax = 10 μmol/min, Km = 2 mM and [S] = 2 mM. Find the reaction rate.",
        "What volume of 6 M HCl is needed to make 500 mL of 1.5 M HCl?",
        "The partial pressures are 0.3 atm, 0.5 atm and 0.2 atm. Find the total pressure.",
    ],
)
def test_each_new_reading_reaches_chemistry(question: str) -> None:
    assert is_chemistry_question(question)
    assert detect_subject(question) == "chemistry"


def test_combustion_analysis_is_only_a_closed_cho_formula() -> None:
    hydrocarbon = (
        "Combustion of a 0.30070 g sample containing only carbon and hydrogen "
        "produced 0.88018 g of CO2 and 0.54045 g of H2O. What is the empirical formula?"
    )
    assert _answer(hydrocarbon) == "CH3"
    nitrogen = (
        "Combustion of a 0.60052 g sample of a compound containing nitrogen produced "
        "0.88018 g of CO2 and 0.36030 g of H2O. What is the empirical formula?"
    )
    assert extract_chemistry_intent(nitrogen) is None
    open_masses = (
        "Combustion of a 0.20000 g sample of a compound containing only C, H, and O produced "
        "0.88018 g of CO2 and 0.36030 g of H2O. What is the empirical formula?"
    )
    intent = extract_chemistry_intent(open_masses)
    assert intent is not None and intent.chemistry_op == "combustion_analysis"
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)
    percent = "A compound is 40.0% C, 6.7% H and 53.3% O. Find its empirical formula."
    percents = extract_chemistry_intent(percent)
    assert percents is not None and percents.chemistry_op == "empirical_formula"


def test_hydrate_water_is_an_integer_coefficient() -> None:
    fractional = (
        "A 2.00000 g sample of a hydrate of CuSO4 leaves 1.59602 g of anhydrous CuSO4. "
        "How many waters of hydration?"
    )
    intent = extract_chemistry_intent(fractional)
    assert intent is not None and intent.chemistry_op == "hydrate_water"
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)
    unnamed = "A 2.49677 g hydrate leaves 1.59602 g of solid. How many waters of hydration?"
    assert extract_chemistry_intent(unnamed) is None


@pytest.mark.parametrize(
    ("value", "figures", "shown"),
    [
        # Zeros that are the number's own digits stay plain.
        (200.0, 2, "200"),
        (16700.0, 3, "16700"),
        (110.02, 2, "110"),
        # Rounding that replaces a whole number's digits with zeros writes a power of ten.
        (1780.0, 2, "1.8 × 10^3"),
        (125.0, 2, "1.3 × 10^2"),
    ],
)
def test_a_rounded_whole_number_is_not_mistaken_for_measured_zeros(
    value: float, figures: int, shown: str
) -> None:
    assert format_number(value, significant=figures, keep_zeros=True) == shown


@pytest.mark.parametrize(
    "question",
    [
        # A charge is missing, so the sum is not the ionic strength.
        "The cation concentration is 0.10 M and the cation charge is 2. "
        "The anion concentration is 0.20 M. Find the ionic strength.",
        # A third ion is not folded into the two-ion sum.
        "The cation concentration is 0.10 M and the cation charge is 2. "
        "The anion concentration is 0.20 M and the anion charge is 1. "
        "Another cation concentration is 0.050 M and its cation charge is 1. "
        "Find the ionic strength.",
        "Use the Debye-Huckel equation to find the activity coefficient.",
        "The organic concentration is 0.400 M and the aqueous concentration is 0.100 M. "
        "Find the partition coefficient after 3 successive extractions.",
        "The observed specific rotation is 8.50. Find the optical purity.",
        "Use Kirchhoff's law. delta H = -50.0 kJ/mol and T1 = 298 K. Find the enthalpy.",
        "The carbon count is 5.00 and the hydrogen count is 8.00. "
        "Find the index of hydrogen deficiency.",
        "The t2g count is 6.00, the eg count is 0.00, and delta_o is 100.0 kJ/mol. "
        "Find the crystal field stabilization energy with pairing energy 20 kJ/mol.",
    ],
)
def test_a_closeout_law_declines_when_an_input_is_missing_or_extra(question: str) -> None:
    assert extract_chemistry_intent(question) is None


def test_transmittance_outside_zero_to_one_declines() -> None:
    intent = extract_chemistry_intent("The transmittance is 2.00. Find the absorbance.")
    assert intent is not None and intent.chemistry_op == "absorbance_transmittance"
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)


def test_van_der_waals_volume_inside_nb_declines() -> None:
    intent = extract_chemistry_intent(
        "Use the van der Waals equation. n = 1.00 mol, T = 300 K, V = 0.0100 L, "
        "a = 1.00, and b = 0.0500. Find the pressure."
    )
    assert intent is not None and intent.chemistry_op == "van_der_waals_pressure"
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)


def test_the_van_t_hoff_factor_does_not_replace_the_temperature_change() -> None:
    question = "Find the freezing point depression when i=1, Kf=1.86, and molality=0.5"
    intent = extract_chemistry_intent(question)
    assert intent is not None and intent.chemistry_op == "freezing_depression"
