# ruff: noqa: RUF003 -- comments write the multiplication and minus signs.
"""Readers that answer more of the STEM sweep's chemistry homework, and what each declines.

Every case was worked by hand from the textbook formula; the declines are the neighbouring
questions each reader must not answer (a leftover reactant, water to add, a stated vapor
pressure, a mixed-valence oxide). A verified answer is the right one or there is none.
"""

from __future__ import annotations

import pytest

from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.solvers import solve_chemistry
from app.services.solving import SolveServiceError
from app.services.subjects.dispatch import detect_subject


def _answer(question: str) -> tuple[str, str]:
    intent = extract_chemistry_intent(question)
    assert intent is not None, question
    return intent.chemistry_op, solve_chemistry(intent).answer


def _declines(question: str) -> bool:
    """No verified answer: no reading, or a solver that refuses the reading."""
    intent = extract_chemistry_intent(question)
    if intent is None:
        return True
    try:
        solve_chemistry(intent)
    except SolveServiceError:
        return True
    return False


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        # A compound named in words, and a diatomic element named as its gas.
        ("what is the molar mass of glucose", "molar_mass", "M(C6H12O6) = 180.16 g/mol"),
        ("What is the mass of 2.0 mol of oxygen gas?", "moles_to_mass", "m(O2) = 64 g"),
        ("how many mg is 0.0150 mol of NaOH", "moles_to_mass", "m(NaOH) = 600 mg"),
        # STP is 0 °C and 1 atm.
        ("What is the density of CO2 at STP in g/L?", "gas_density", "d = 1.963 g/L"),
        (
            "What is the molar mass of a gas with a density of 1.25 g/L at STP?",
            "molar_mass_from_density",
            "M = 28.0 g/mol",
        ),
        ("molarity of 0.25 mol KCl in 750 mL of water", "molarity", "c = 0.33 mol/L"),
        (
            "how many mg of KCl are in 15.0 mL of a 0.200 mol/L KCl solution?",
            "solution_mass",
            "m = 224 mg",
        ),
        (
            "What is the mole fraction of water in a solution of 46 g ethanol and 54 g water?",
            "mole_fraction_mass",
            "χ(H2O) = 0.75",
        ),
    ],
)
def test_amount_readers_take_names_units_and_stp(
    question: str, operation: str, answer: str
) -> None:
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("I have 12 M HCl stock. How many mL do I need to make 500 mL of 1.5 M HCl?", "V1 = 63 mL"),
        (
            "A 6.0 M stock solution is diluted. What volume of it is needed to prepare 250 mL "
            "of a 1.5 M solution?",
            "V1 = 63 mL",
        ),
        ("What is the final volume when 50 mL of 2.0 M HCl is diluted to 0.50 M?", "V2 = 200 mL"),
    ],
)
def test_dilution_reads_a_stated_stock_and_a_passive_dilution(question: str, answer: str) -> None:
    assert _answer(question) == ("dilution", answer)


@pytest.mark.parametrize(
    "question",
    [
        # Water to add is V2 − V1, not either volume.
        "50 mL of 2.0 M HCl is diluted to 0.50 M. How much water was added?",
        "I have 12 M HCl stock. How many mL of water do I add to make 500 mL of 1.5 M HCl?",
        # Two different substances are not one dilution.
        "I have 12 M HCl stock. How many mL do I need to make 500 mL of 1.5 M NaOH?",
        # What can be made from the stock is V2, not V1.
        "How many liters of 0.50 M solution can you make from 50 mL of 2.0 M stock?",
    ],
)
def test_dilution_declines_another_volume(question: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is None or intent.chemistry_op != "dilution"


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        (
            "25.00 mL of HCl is titrated with 0.1000 M NaOH and it takes 32.45 mL to reach the "
            "endpoint. What is the concentration of the HCl?",
            "titration_concentration",
            "C₂ = 0.1298 mol/L",
        ),
        # H2SO4 neutralizes two NaOH, so it takes half the moles.
        (
            "What volume of 0.250 M H2SO4 is needed to neutralize 50.0 mL of 0.100 M NaOH?",
            "titration_volume",
            "V₂ = 10.0 mL",
        ),
        (
            "How many mL of 0.10 M NaOH are needed to neutralize 25 mL of 0.20 M HCl?",
            "titration_volume",
            "V₂ = 50 mL",
        ),
        # Mixing is the titration's reaction: 1.0 mmol of H+ left in 40.0 mL.
        (
            "What is the pH after mixing 25.0 mL of 0.100 M HCl with 15.0 mL of 0.100 M NaOH?",
            "titration_strong",
            "pH = 1.602",
        ),
    ],
)
def test_neutralization_reads_endpoints_volumes_and_mixtures(
    question: str, operation: str, answer: str
) -> None:
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        # Water's own ions: 1.0 × 10^-8 M HCl is pH 6.98, never 8.00.
        ("pH of 1.0 × 10^-8 M HCl", "strong_acid_ph", "pH = 6.98"),
        ("What is the pOH of 1.0e-8 M HCl?", "strong_acid_poh", "pOH = 7.02"),
        ("What is the pH of 2.0e-8 M NaOH?", "strong_base_ph", "pH = 7.04"),
        ("[H+] of a solution with pH 4.75?", "h_from_ph", "[H+] = 1.8 × 10^-5 mol/L"),
        (
            "Calculate [H+] for a solution with a pH of 4.75",
            "h_from_ph",
            "[H+] = 1.8 × 10^-5 mol/L",
        ),
        ("The Kb of NH3 is 1.8 x 10^-5. What is its pKb?", "ka_kb", "pKb = 4.74"),
        (
            "Ka of acetic acid is 1.8 x 10^-5. Find Kb of the acetate ion.",
            "ka_kb",
            "Kb = 5.6 × 10^-10",
        ),
    ],
)
def test_acid_base_readers_take_dilute_solutions_and_stated_constants(
    question: str, operation: str, answer: str
) -> None:
    assert _answer(question) == (operation, answer)


def test_a_ph_of_a_concentration_is_not_a_stated_ph() -> None:
    """ "the pH of 0.01 M HCl" asks the pH; 0.01 is never read as one."""
    assert _answer("What is the pH of 0.01 M HCl?") == ("strong_acid_ph", "pH = 2.00")
    assert extract_chemistry_intent("Find the [OH-] of a solution with pH 4.75") is None


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        (
            "H2 + I2 ⇌ 2HI, Kc = 49. if you start with 0.50 M H2 and 0.50 M I2, what is [HI] "
            "at equilibrium?",
            "ice_equilibrium",
            "x = 0.39\n[H2] = 0.11 mol/L\n[I2] = 0.11 mol/L\n[HI] = 0.78 mol/L",
        ),
        # Δn = −2: Kc = Kp (RT)^2 at 773.15 K.
        (
            "Kp for N2 + 3H2 ⇌ 2NH3 is 1.45 x 10^-5 at 500 °C. Find Kc.",
            "kc_kp",
            "Kc = 0.0584",
        ),
    ],
)
def test_equilibrium_reads_starting_amounts_and_a_stated_k(
    question: str, operation: str, answer: str
) -> None:
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "Given C + O2 → CO2 ΔH = -393.5 kJ and CO + 1/2 O2 → CO2 ΔH = -283.0 kJ, find ΔH "
            "for C + 1/2 O2 → CO",
            "ΔH = -110.5 kJ",
        ),
        (
            "Use Hess's law: C + O2 → CO2, ΔH = -393.5 kJ; CO + ½ O2 → CO2, ΔH = -283.0 kJ. "
            "Find ΔH for C + ½ O2 → CO.",
            "ΔH = -110.5 kJ",
        ),
        ("Given C + O2 -> CO2, ΔH = -393.5 kJ, find ΔH for 2C + 2O2 -> 2CO2", "ΔH = -787.0 kJ"),
    ],
)
def test_hess_combines_written_steps_into_the_asked_reaction(question: str, answer: str) -> None:
    assert _answer(question) == ("hess", answer)


@pytest.mark.parametrize(
    "question",
    [
        # No multiple of these steps makes CO.
        "Given C + O2 → CO2 ΔH = -393.5 kJ and H2 + 1/2 O2 → H2O ΔH = -285.8 kJ, find ΔH for "
        "C + 1/2 O2 → CO",
        # Steps in kJ and kJ/mol are not one sum.
        "Given C + O2 → CO2 ΔH = -393.5 kJ and CO + 1/2 O2 → CO2 ΔH = -283.0 kJ/mol, find ΔH "
        "for C + 1/2 O2 → CO",
    ],
)
def test_hess_declines_steps_that_do_not_make_the_reaction(question: str) -> None:
    assert _declines(question)


def test_formation_enthalpies_listed_by_species() -> None:
    question = (
        "Calculate ΔH°rxn for CH4 + 2O2 → CO2 + 2H2O(l) using ΔHf values: CH4 = -74.8, "
        "CO2 = -393.5, H2O(l) = -285.8 kJ/mol"
    )
    assert _answer(question) == ("formation_enthalpy", "ΔH° = -890.3 kJ/mol")
    # A missing compound's value is never taken as zero.
    assert _declines(
        "Calculate ΔH°rxn for CH4 + 2O2 → CO2 + 2H2O(l) using ΔHf values: CH4 = -74.8, "
        "CO2 = -393.5 kJ/mol"
    )


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        (
            "how many moles of O2 are needed to burn 3.0 mol of CH4? CH4 + 2O2 → CO2 + 2H2O",
            "mass_stoichiometry",
            "n(O2) = 6.0 mol",
        ),
        (
            "How many grams of KClO3 are needed to produce 3.2 g of O2? 2KClO3 → 2KCl + 3O2",
            "mass_stoichiometry",
            "m(KClO3) = 8.2 g",
        ),
        # Both reactants weighed: whichever runs out first decides.
        (
            "How many grams of H2O form from 4.0 g of H2 and 40.0 g of O2? 2H2 + O2 -> 2H2O",
            "limiting_mass",
            "Limiting reagent = H2; 36 g H2O",
        ),
        (
            "In the reaction CaCO3 → CaO + CO2, heating 50.0 g of CaCO3 gave 25.0 g of CaO. "
            "What is the percent yield?",
            "reaction_percent_yield",
            "Percent yield = 89.2%",
        ),
    ],
)
def test_stoichiometry_reads_reactants_asked_and_yields(
    question: str, operation: str, answer: str
) -> None:
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    "question",
    [
        # What is left of a reactant is not the amount that reacts.
        "2H2 + O2 -> 2H2O. 4.0 g of H2 reacts with excess O2. How many grams of O2 remain?",
        # A second reactant not said to be in excess leaves the theoretical yield open.
        "2H2 + O2 -> 2H2O. 4.0 g of H2 gave 30.0 g of H2O. What is the percent yield?",
        # More product than the reaction can make.
        "In CaCO3 → CaO + CO2, 50.0 g of CaCO3 gave 30.0 g of CaO. Find the percent yield.",
    ],
)
def test_stoichiometry_declines_a_leftover_or_an_open_yield(question: str) -> None:
    assert _declines(question)


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        # Water's vapor pressure at 25 °C is 23.76 mmHg.
        (
            "A gas is collected over water at 25 °C and 755 mmHg total pressure. What is the "
            "pressure of the dry gas?",
            "gas_over_water",
            "Pdry = 731 mmHg",
        ),
        (
            "E°cell for a cell with Ag+/Ag (0.80 V) and Cu2+/Cu (0.34 V)?",
            "cell_potential",
            "E°cell = 0.46 V",
        ),
        # Q = [Zn2+] / [Cu2+] = 100.
        (
            "Find the cell potential of a Zn/Cu cell with [Zn2+] = 1.0 M and [Cu2+] = 0.010 M at "
            "25 °C",
            "galvanic_nernst",
            "E = 1.04 V",
        ),
        # Q = [Cu2+] / [Ag+]^2 = 100.
        (
            "Find the cell potential of an Ag/Cu cell with [Ag+] = 0.10 M and [Cu2+] = 1.0 M",
            "galvanic_nernst",
            "E = 0.40 V",
        ),
    ],
)
def test_gas_and_cell_readers(question: str, operation: str, answer: str) -> None:
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    "question",
    [
        # A stated vapor pressure is a value the table reading would ignore.
        "A gas is collected over water at 25 °C and 755 mmHg. The vapor pressure of water is "
        "24 mmHg. Find the pressure of the dry gas.",
        # An electrolytic cell is driven, so the higher couple is not its cathode by default.
        "What is the voltage of an electrolytic cell with Ag+/Ag (0.80 V) and Cu2+/Cu (0.34 V)?",
        # Cu+ is not the table's copper ion.
        "Find the cell potential of a Zn/Cu cell with [Zn2+] = 1.0 M and [Cu+] = 0.010 M",
        # The stated pressure is the dry gas's and the total is asked: the reverse question.
        "What is the total pressure of a gas collected over water at 25 °C if the dry gas is at "
        "731 mmHg?",
    ],
)
def test_gas_and_cell_readers_decline_values_they_cannot_place(question: str) -> None:
    assert _declines(question)


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        (
            "first order rxn, k = 1.5e-3 s-1, initial conc 0.80 M. what is the concentration "
            "after 10 min?",
            "first_order_concentration",
            "[A]ₜ = 0.33 mol/L",
        ),
        # 75% gone leaves 25%: t = ln(4) / k.
        (
            "k = 0.0450 s^-1 for a first-order reaction. how long until 75% of the reactant is "
            "gone",
            "first_order_time",
            "t = 30.8 s",
        ),
        (
            "The rate constant of a first-order reaction is 0.0450 s^-1. How long does it take "
            "for the concentration to fall to 25% of its initial value?",
            "first_order_time",
            "t = 31 s",
        ),
        (
            "A first-order reaction has k = 0.10 min^-1. How long until 25% has reacted?",
            "first_order_time",
            "t = 2.9 min",
        ),
    ],
)
def test_first_order_readers(question: str, operation: str, answer: str) -> None:
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    "question",
    [
        # No rate constant.
        "how long does it take a first order reaction to drop to 25% of the start?",
        # Two percentages leave the fraction open.
        "A first-order reaction has k = 0.10 min^-1. How long until 25% remains and 50% is gone?",
    ],
)
def test_first_order_time_declines_without_one_fraction_and_k(question: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is None or intent.chemistry_op != "first_order_time"


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        (
            "what is the shape of an NH3 molecule",
            "vsepr",
            "geometry: trigonal pyramidal, 107°\npolarity: polar\nhybridization: sp3\n"
            "central formal charge: 0\nelectron geometry: tetrahedral, ideal angle 109.5°",
        ),
        ("balence NaOH + H2SO4 → Na2SO4 + H2O", "balance", "2 NaOH + H2SO4 -> Na2SO4 + 2 H2O"),
        (
            "a 2.50 g sample has 1.00 g Ca, 0.300 g C and 1.20 g O. what is the empirical formula",
            "empirical_formula",
            "CaCO3",
        ),
        (
            "A compound contains 2.4 g carbon and 0.6 g hydrogen. Find the empirical formula.",
            "empirical_formula",
            "CH3",
        ),
        (
            "how many valence electrons does nitrogen have",
            "valence_electrons",
            "N: 5 valence electrons",
        ),
        (
            "how many valence electrons are in SO4^2-",
            "valence_electrons",
            "SO4^2-: 32 valence electrons",
        ),
        ("what is the formula for iron(III) oxide", "ionic_formula", "iron(III) oxide: Fe2O3"),
        (
            "What is the formula of ammonium phosphate",
            "ionic_formula",
            "ammonium phosphate: (NH4)3PO4",
        ),
        ("name of CuO", "ionic_name", "CuO: copper(II) oxide"),
    ],
)
def test_structure_and_formula_readers(question: str, operation: str, answer: str) -> None:
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    "question",
    [
        # The masses do not add up to the sample.
        "a 3.00 g sample has 1.00 g Ca, 0.300 g C and 1.20 g O. what is the empirical formula",
        # A transition metal's valence electrons are not its group number.
        "how many valence electrons does iron have",
        # A molecular compound and a mixed-valence oxide are not salts of the ion table.
        "What is the name of CO2?",
        "What is the name of Fe3O4?",
        # A hydrate and a crystal structure are not the salt the name ends with.
        "what is the formula of calcium nitrate tetrahydrate?",
        "what is the name of the NaCl crystal structure",
    ],
)
def test_structure_and_formula_readers_decline_off_their_tables(question: str) -> None:
    assert _declines(question)


@pytest.mark.parametrize(
    ("question", "subject"),
    [
        ("What's the name of Fe2(SO4)3?", "chemistry"),
        ("what is the formula for iron(III) oxide", "chemistry"),
        (
            "A gas is collected over water at 25 °C and 755 mmHg total pressure. Dry gas pressure?",
            "chemistry",
        ),
        ("E°cell for a cell with Ag+/Ag (0.80 V) and Cu2+/Cu (0.34 V)?", "chemistry"),
        ("3 M Company stock rose 2% today.", None),
        ("what's the formula for success?", None),
    ],
)
def test_new_cues_route_chemistry_and_not_their_look_alikes(
    question: str, subject: str | None
) -> None:
    assert detect_subject(question) == subject
