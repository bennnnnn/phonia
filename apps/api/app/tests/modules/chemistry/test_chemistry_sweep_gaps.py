"""Readers for chemistry questions the STEM sweep found routed to physics or maths.

Each was a chemistry question another subject claimed (``stem_corpus/chemistry``):
particles to a mass, an element's share of a compound asked compound first, q = nΔH from a
burnt mass, a colligative point from moles or grams, Dalton's law with labelled or listed
pressures, a plating time, and the grams of solute in a mass-percent solution. Every reader
here answers the whole question or declines; none answers a neighbouring question.
"""

from __future__ import annotations

import pytest

from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.solvers import solve_chemistry
from app.services.subjects.dispatch import detect_subject


def _answer(question: str) -> tuple[str, str]:
    intent = extract_chemistry_intent(question)
    assert intent is not None, question
    return intent.chemistry_op, solve_chemistry(intent).answer


def _closes(question: str, operation: str, answer: str) -> None:
    assert detect_subject(question) == "chemistry", question
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        ("find the mass of 1.20 x 10^24 atoms of iron", "particles_to_mass", "m = 111 g"),
        (
            "What is the mass of 6.022 x 10^23 molecules of water?",
            "particles_to_mass",
            "m = 18.01 g",
        ),
        (
            "What is the mass, in grams, of 2.5 x 10^22 atoms of gold?",
            "particles_to_mass",
            "m = 8.2 g",
        ),
        # Molecules of a diatomic element are its molecules: oxygen is O2.
        (
            "How many grams do 3.01 x 10^23 molecules of oxygen weigh?",
            "particles_to_mass",
            "m = 16.0 g",
        ),
        (
            "How many molecules are in 10 g of CO2?",
            "mass_to_particles",
            "N(CO2) = 1.4 × 10^23 particles",
        ),
        ("How many atoms are in 5.0 g of Fe?", "mass_to_particles", "N(Fe) = 5.4 × 10^22 atoms"),
        # Every atom of the formula, as a mole question counts them.
        (
            "How many atoms are in 10.0 g of CO2?",
            "mass_to_particles",
            "N(CO2) = 4.11 × 10^23 atoms",
        ),
    ],
)
def test_particle_reader_converts_between_a_count_and_a_mass(
    question: str, operation: str, answer: str
) -> None:
    _closes(question, operation, answer)


@pytest.mark.parametrize(
    "question",
    [
        # Atoms of O2 or of water are not one element's atoms.
        "What is the mass of 3.01 x 10^23 atoms of O2?",
        "What is the mass of 3.01 x 10^23 atoms of water?",
        # Iron is not made of molecules.
        "What is the mass of 3.01 x 10^23 molecules of iron?",
        # A second amount is a different question.
        "What is the mass of 2.0 x 10^23 molecules of CO2 and 5 g of water?",
    ],
)
def test_particle_reader_declines_what_the_words_leave_open(question: str) -> None:
    assert extract_chemistry_intent(question) is None


def test_particle_reader_leaves_an_equation_to_stoichiometry() -> None:
    operation, answer = _answer(
        "How many grams of H2O form from 3.01 x 10^23 molecules of H2? 2H2 + O2 -> 2H2O"
    )
    assert (operation, answer) == ("mass_stoichiometry", "m(H2O) = 9.00 g")


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("what % of Fe2O3 is iron", "Fe in Fe2O3 = 69.94%"),
        ("What percent of Fe2O3 is oxygen", "O in Fe2O3 = 30.06%"),
        ("What percentage of the mass of CO2 is oxygen?", "O in CO2 = 72.71%"),
        ("what percentage of CO2 is carbon by mass?", "C in CO2 = 27.29%"),
        ("What is the mass percent of iron in Fe2O3?", "Fe in Fe2O3 = 69.94%"),
    ],
)
def test_percent_composition_reads_the_compound_first(question: str, answer: str) -> None:
    _closes(question, "percent_composition", answer)


@pytest.mark.parametrize(
    "question",
    [
        # A share of the atoms is not a share of the mass.
        "What % of the atoms in Fe2O3 are iron?",
        # Helium is not in CO2.
        "what % of CO2 is helium",
    ],
)
def test_percent_composition_declines_another_basis_or_element(question: str) -> None:
    assert extract_chemistry_intent(question) is None


@pytest.mark.parametrize(
    ("question", "subject"),
    [
        ("what % of 50 is 10", "math"),
        ("what % of CO2 emissions come from cars", "math"),
    ],
)
def test_a_percent_of_a_number_stays_maths(question: str, subject: str) -> None:
    assert detect_subject(question) == subject


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        (
            "How much heat is released when 32.0 g of CH4 burns? ΔH = -890 kJ/mol",
            "reaction_heat_mass",
            "q = -1.78 × 10^3 kJ",
        ),
        # A molar enthalpy of vaporization is the same law: q = nΔH.
        (
            "How much heat is needed to vaporize 36.0 g of water? ΔHvap = 40.7 kJ/mol",
            "reaction_heat_mass",
            "q = 81.3 kJ",
        ),
        (
            "How much heat is released when 3.0 mol of H2 burns? ΔH = -286 kJ/mol",
            "reaction_heat",
            "q = -8.6 × 10^2 kJ",
        ),
    ],
)
def test_reaction_heat_reads_the_amount_burnt(question: str, operation: str, answer: str) -> None:
    _closes(question, operation, answer)


@pytest.mark.parametrize(
    "question",
    [
        # ΔH of a written equation is per mole of that reaction: 2H2 is two moles of H2.
        "2H2 + O2 -> 2H2O, ΔH = -572 kJ/mol. How much heat is released when 3.0 mol of H2 burns?",
        "CH4 + 2O2 -> CO2 + 2H2O, ΔH = -890 kJ/mol. How much heat is released when 32.0 g of "
        "CH4 burns?",
        # A second substance leaves open which one the grams are of.
        "How much heat is released when 32.0 g of CH4 burns in O2? ΔH = -890 kJ/mol",
        # A heat in kJ is not a molar enthalpy.
        "How much heat is released when 32.0 g of CH4 burns? ΔH = -890 kJ",
    ],
)
def test_reaction_heat_declines_a_per_mole_it_cannot_place(question: str) -> None:
    assert extract_chemistry_intent(question) is None


def test_an_equation_mole_ratio_never_answers_a_heat_question() -> None:
    """It used to answer "n(H2O) = 3.0 mol" to a question that asks for heat."""
    assert (
        extract_chemistry_intent(
            "2H2 + O2 -> 2H2O. How much heat is released when 3.0 mol of H2 burns?"
        )
        is None
    )
    assert _answer("N2 + 3H2 -> 2NH3. How much NH3 is made from 2.0 mol N2?") == (
        "stoichiometry",
        "n(NH3) = 4.0 mol NH3",
    )


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        (
            "What is the boiling point of a solution made by dissolving 2.00 mol of glucose in "
            "1.00 kg of water? Kb = 0.512 °C/m",
            "solution_boiling_point",
            "Tb = 101.02 °C",
        ),
        (
            "Freezing point of a solution with 10.0 g NaCl in 250 g of water? Kf = 1.86 °C/m",
            "solution_freezing_point",
            "Tf = -2.55 °C",
        ),
        (
            "What is the freezing point of a 0.500 m aqueous NaCl solution? Kf = 1.86 °C/m",
            "solution_freezing_point",
            "Tf = -1.86 °C",
        ),
        # Another solvent's normal boiling point is stated, never assumed.
        (
            "What is the boiling point of a solution of 1.00 mol of solute in 1.00 kg of benzene? "
            "i = 1, Kb = 2.53 °C/m, and the normal boiling point of benzene is 80.1 °C.",
            "solution_boiling_point",
            "Tb = 82.6 °C",
        ),
        (
            "How much does the boiling point rise when 2.00 mol of glucose dissolves in 1.00 kg "
            "of water? Kb = 0.512 °C/m",
            "boiling_elevation",
            "ΔTb = 1.02 °C",
        ),
        (
            "Find the freezing point depression of 0.5 m glucose in water. Kf = 1.86 °C/m.",
            "freezing_depression",
            "ΔTf = 0.93 °C",
        ),
    ],
)
def test_colligative_reader_answers_the_point_or_the_change_asked(
    question: str, operation: str, answer: str
) -> None:
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    "question",
    [
        # "By how much" asks the change, which "raised" does not name: no reading.
        "By how much is the boiling point raised when 2.00 mol of glucose dissolves in 1.00 kg "
        "of water? Kb = 0.512 °C/m",
        # No solvent named, so no normal boiling point to add the change to.
        "What is the boiling point of a 2.00 m glucose solution? Kb = 0.512 °C/m",
        # A stated temperature no input takes.
        "What is the boiling point of a solution of 2.00 mol of glucose in 1.00 kg of water at "
        "25 °C? Kb = 0.512 °C/m",
    ],
)
def test_colligative_reader_declines_a_point_it_cannot_place(question: str) -> None:
    assert extract_chemistry_intent(question) is None


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        (
            "Find the total pressure: P(He) = 0.40 atm, P(Ne) = 0.25 atm, P(Ar) = 0.15 atm",
            "dalton",
            "Ptotal = 0.80 atm",
        ),
        (
            "A mixture has He at 0.40 atm, Ne at 0.25 atm, and Ar at 0.15 atm. what's the "
            "total pressure?",
            "dalton",
            "Ptotal = 0.80 atm",
        ),
        (
            "A mixture of helium at 0.40 atm and neon at 0.25 atm. what is the total pressure?",
            "dalton",
            "Ptotal = 0.65 atm",
        ),
        (
            "A gas mixture has 2.0 mol O2 and 6.0 mol N2 at a total pressure of 4.0 atm. Find "
            "the partial pressure of O2.",
            "partial_pressure",
            "P(O2) = 1.0 atm",
        ),
        (
            "What is the partial pressure of O2 if its mole fraction is 0.25 and the total "
            "pressure is 4.0 atm?",
            "partial_pressure",
            "Pi = 1.0 atm",
        ),
    ],
)
def test_gas_mixture_reader_sums_or_shares_the_pressures(
    question: str, operation: str, answer: str
) -> None:
    _closes(question, operation, answer)


@pytest.mark.parametrize(
    "question",
    [
        # A stated total is not the asked one.
        "He at 0.40 atm and Ne at 0.25 atm are at a total pressure of 0.65 atm. Find the "
        "total pressure.",
        # A pressure no gas owns.
        "He at 0.40 atm and Ne at 0.25 atm sit in a 1.0 atm room. What is the total pressure?",
        # Tanks named by letters are not gases.
        "Tank C at 2 atm and tank B at 3 atm, what is the total pressure if connected?",
        # One gas's moles are missing.
        "A mixture has 2.0 mol O2 and some N2 at a total pressure of 4.0 atm. Find the partial "
        "pressure of O2.",
    ],
)
def test_gas_mixture_reader_declines_a_pressure_it_cannot_place(question: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is None or intent.chemistry_op not in {"dalton", "partial_pressure"}


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "How long does it take to plate 5.00 g of silver with a current of 2.50 A?",
            "t = 1.79 × 10^3 s",
        ),
        (
            "How long does electroplating 2.00 g of copper take at 1.50 A?",
            "t = 4.05 × 10^3 s",
        ),
    ],
)
def test_plating_time_is_faradays_law(question: str, answer: str) -> None:
    _closes(question, "electrolysis_time", answer)


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "How many grams of NaCl are needed to make 500 g of a 5.0% by mass solution?",
            "m(solute) = 25 g",
        ),
        (
            "What mass of glucose is in 250 g of a 10.0% (w/w) glucose solution?",
            "m(solute) = 25.0 g",
        ),
        (
            "How many grams of KCl are needed to prepare 2.00 kg of a 3.00% by mass KCl solution?",
            "m(solute) = 60.0 g",
        ),
    ],
)
def test_percent_solute_reader_finds_the_solute_mass(question: str, answer: str) -> None:
    _closes(question, "solute_mass_from_percent", answer)


@pytest.mark.parametrize(
    "question",
    [
        # The water of the same solution is the rest of it, 475 g.
        "How many grams of water are needed to make 500 g of a 5.0% by mass NaCl solution?",
        # A mass/volume percent is grams per 100 mL, not of the solution's grams.
        "How many grams of NaCl are in 500 g of a 5.0% (w/v) NaCl solution?",
        # The named solution is of another solute.
        "How many grams of KCl are in 500 g of a 5.0% by mass NaCl solution?",
    ],
)
def test_percent_solute_reader_declines_another_mass(question: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is None or intent.chemistry_op != "solute_mass_from_percent"


@pytest.mark.parametrize(
    ("question", "operation", "answer"),
    [
        ("pH of 0.0025 M HCl", "strong_acid_ph", "pH = 2.60"),
        ("pH of 0.15 M NH3 (Kb = 1.8e-5)", "weak_base_ph", "pH = 11.21"),
        ("osmotic pressure of 0.10 M glucose at 25 °C?", "osmotic_pressure", "Π = 2.4 atm"),
        (
            "theoretical yield was 25.0 g but I only got 21.3 g. percent yield?",
            "percent_yield",
            "Percent yield = 85.2%",
        ),
    ],
)
def test_a_question_with_no_verb_asks_for_what_it_names(
    question: str, operation: str, answer: str
) -> None:
    assert _answer(question) == (operation, answer)


@pytest.mark.parametrize(
    "question",
    [
        # A statement of a value is not a question about it.
        "The pH of 0.01 M HCl is 2.",
        "the pool ph is 7.8, is that too high?",
        # Two sentences and no question mark: nothing asked.
        "Glucose is 0.10 M. The tank is at 25 °C.",
    ],
)
def test_a_statement_with_no_verb_is_not_read_as_a_question(question: str) -> None:
    assert extract_chemistry_intent(question) is None


@pytest.mark.parametrize(
    ("question", "chemistry"),
    [
        ("find the mass of 1.20 x 10^24 atoms of iron", True),
        ("How many molecules are in 10 g of CO2?", True),
        ("what % of Fe2O3 is iron", True),
        ("Find the total pressure: P(He) = 0.40 atm, P(Ne) = 0.25 atm", True),
        ("How many grams of NaCl are needed to make 500 g of a 5.0% by mass solution?", True),
        # Look-alikes: a probability, a battery, a recipe and a tank are not chemistry.
        ("P(A) = 0.3 and P(B) = 0.5, find P(A or B)", False),
        ("my phone has 10^6 molecules of patience left lol", False),
        ("remind me to buy NaCl and 2 L of milk", False),
        ("Tank C at 2 atm and tank B at 3 atm, what is the total pressure if connected?", False),
    ],
)
def test_chemistry_gate_reads_the_new_cues_and_not_their_look_alikes(
    question: str, chemistry: bool
) -> None:
    assert is_chemistry_question(question) is chemistry
