# ruff: noqa: RUF002, RUF003 -- questions are typed with Unicode sub/superscripts and ×.
"""Homework questions that used to get a wrong verified chemistry answer.

Each family is a cause, not one prompt:

- A: Unicode subscripts and superscripts (``H₂SO₄``, ``10⁻³``) cut the formula, so the
  molar mass of H₂SO₄ was the molar mass of H;
- B: a hydrate's water (``CuSO4.5H2O``, ``MgSO4·7H2O``) was dropped;
- C: "how many oxygen atoms" counted every atom, and "moles of oxygen atoms" answered a
  particle count;
- D: a Ka question chemistry could not read went to maths, which "verified" ``x = 55555.6``
  from the ``x`` of ``1.8 x 10^-5``;
- E: display: trailing zeros dropped, round-half-even, configurations without
  superscripts;
- F: routing that sent a chemistry question to maths (an ASCII arrow, ``=`` as an arrow,
  a lowercase ``ph``).

The right outcome is the right number or no verified answer, never a wrong one.
"""

from __future__ import annotations

import math
import re

import pytest

from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.direct import format_direct_chemistry_reply
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.input_text import read_chemistry_text
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.solvers import solve_chemistry
from app.modules.chemistry.solvers.types import ChemistryResult, format_number
from app.services.solving import SolveServiceError
from app.services.subjects.dispatch import detect_subject

_NUMBER = re.compile(r"=\s*(-?\d+(?:\.\d+)?)(?:\s*×\s*10\^(-?\d+))?")


def _solve(question: str) -> ChemistryResult:
    intent = extract_chemistry_intent(question)
    assert intent is not None, question
    return solve_chemistry(intent)


def _value(answer: str) -> float:
    """The last number after ``=`` in an answer, ``2.4 × 10^24`` read whole."""
    matches = list(_NUMBER.finditer(answer.replace("−", "-")))
    assert matches, answer
    mantissa, exponent = matches[-1].groups()
    return float(mantissa) * 10 ** int(exponent or 0)


def _right_or_declined(question: str, expected: float, rel: float = 0.01) -> None:
    """A verified answer, when there is one, is the right number."""
    intent = extract_chemistry_intent(question)
    if intent is None:
        return
    try:
        result = solve_chemistry(intent)
    except SolveServiceError:
        return
    assert math.isclose(_value(result.answer), expected, rel_tol=rel), (question, result.answer)


# --- A: Unicode sub- and superscripts are read as the formula they spell ----------------


@pytest.mark.parametrize(
    ("typed", "read"),
    [
        ("H₂SO₄", "H2SO4"),
        ("Ca(NO₃)₂", "Ca(NO3)2"),
        ("CH₃COOH", "CH3COOH"),
        ("Fe³⁺ + e⁻", "Fe^3+ + e-"),
        ("SO₄²⁻", "SO4^2-"),
        ("1.0 × 10⁻³ M", "1.0 × 10^-3 M"),
        ("CuSO₄·5H₂O", "CuSO4·5H2O"),
        ("CuSO4.5H2O", "CuSO4·5H2O"),
        ("CuSO4 • 5H2O", "CuSO4·5H2O"),
        ("CuSO4*5H2O", "CuSO4·5H2O"),
        ("Na2CO3⋅10H2O", "Na2CO3·10H2O"),
        # A full stop that ends a sentence, a decimal and a product are not hydrate dots.
        ("dissolve NaCl. 5 g is enough", "dissolve NaCl. 5 g is enough"),
        ("pH 4.5 at 25.0 °C", "pH 4.5 at 25.0 °C"),
        ("2 * 3 = 6", "2 * 3 = 6"),
        ("1.8 x 10^-5", "1.8 x 10^-5"),
    ],
)
def test_read_chemistry_text_spells_scripts_and_hydrate_dots_in_ascii(
    typed: str, read: str
) -> None:
    assert read_chemistry_text(typed) == read


@pytest.mark.parametrize(
    ("question", "label", "expected"),
    [
        ("what is the molar mass of H₂SO₄", "M(H2SO4)", 98.07),
        ("What is the molar mass of Ca(NO₃)₂?", "M(Ca(NO3)2)", 164.09),
        ("What is the mass of 3.5 mol of H₂SO₄ in grams", "m(H2SO4)", 343.25),
        ("how many grams are in 2.0 mol of CO₂", "m(CO2)", 88.02),
        ("how many moles are in 49 g of H₂SO₄?", "n(H2SO4)", 0.4996),
        ("how many moles are in 54 g of H₂O", "n(H2O)", 2.998),
        ("percent composition of carbon in CO₂", "C in CO2", 27.29),
        ("What is the molarity of 4.9 g H₂SO₄ in 500 mL of solution?", "c", 0.09993),
        ("Find the pH of 0.10 M CH₃COOH, Ka = 1.8 x 10^-5", "pH", 2.875),
        ("What is the pH of a 1.0 × 10⁻³ M HNO₃ solution?", "pH", 3.0),
        (
            "For N₂ + 3H₂ ⇌ 2NH₃, [N₂] = 0.50 M, [H₂] = 0.20 M and [NH₃] = 0.10 M at "
            "equilibrium. Find Kc.",
            "Kc",
            2.5,
        ),
    ],
)
def test_a_unicode_formula_is_read_whole(question: str, label: str, expected: float) -> None:
    result = _solve(question)
    assert result.answer.startswith(label), result.answer
    assert math.isclose(_value(result.answer), expected, rel_tol=0.01), result.answer


@pytest.mark.parametrize(
    ("question", "balanced"),
    [
        ("Balance H₂ + O₂ → H₂O", "2 H2 + O2 -> 2 H2O"),
        ("Balance C₆H₁₂O₆ + O₂ → CO₂ + H₂O", "C6H12O6 + 6 O2 -> 6 CO2 + 6 H2O"),
    ],
)
def test_a_unicode_equation_is_balanced(question: str, balanced: str) -> None:
    assert _solve(question).answer == balanced


def test_a_unicode_stoichiometry_reads_the_typeset_equation() -> None:
    _right_or_declined(
        "How many grams of CO₂ are produced when 10.0 g of C₃H₈ burns completely? "
        "C₃H₈ + 5O₂ → 3CO₂ + 4H₂O",
        29.94,
    )
    assert detect_subject("Balance H₂ + O₂ → H₂O") == "chemistry"


# --- B: a hydrate's water counts ---------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "label", "expected"),
    [
        ("What is the molar mass of CuSO4.5H2O?", "M(CuSO4·5H2O)", 249.68),
        ("molar mass of CuSO₄·5H₂O?", "M(CuSO4·5H2O)", 249.68),
        ("molar mass of MgSO4·7H2O", "M(MgSO4·7H2O)", 246.47),
        ("What is the molar mass of Na2CO3·10H2O?", "M(Na2CO3·10H2O)", 286.14),
        ("how many moles in 10.0 g of CuSO4·5H2O", "n(CuSO4·5H2O)", 0.04005),
    ],
)
def test_b_a_hydrate_keeps_its_water(question: str, label: str, expected: float) -> None:
    result = _solve(question)
    assert result.answer.startswith(label), result.answer
    assert math.isclose(_value(result.answer), expected, rel_tol=0.005), result.answer


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is the molarity of 2.50 g CuSO4·5H2O in 100 mL of solution?", 0.1001),
        ("How many grams are in 0.200 mol of CuSO4.5H2O?", 49.94),
        ("percent composition of oxygen in CuSO4·5H2O", 57.67),
    ],
)
def test_b_no_reader_drops_the_water_of_a_hydrate(question: str, expected: float) -> None:
    _right_or_declined(question, expected)


# --- C: "oxygen atoms" counts the oxygen; "moles of oxygen atoms" is an amount -----------


@pytest.mark.parametrize(
    ("question", "label", "expected"),
    [
        ("how many oxygen atoms are in 2.0 mol of CO2", "N(O)", 2.409e24),
        ("how many hydrogen atoms are in 0.50 mol of H2O", "N(H)", 6.022e23),
        ("How many O atoms are in 0.25 mol of H2SO4?", "N(O)", 6.022e23),
        ("How many carbon atoms are in 1.5 mol of C6H12O6?", "N(C)", 5.420e24),
        ("How many H atoms are in 3.0 mol of NH3?", "N(H)", 5.420e24),
        ("how many atoms of oxygen are in 2.0 mol of CO2", "N(O)", 2.409e24),
        ("how many moles of oxygen atoms are in 2.0 mol of H2SO4", "n(O)", 8.0),
        ("How many moles of H atoms are in 0.50 mol of CH4?", "n(H)", 2.0),
        # Every atom, and molecules, are unchanged.
        ("how many atoms are in 2.0 mol of CO2", "N(CO2)", 3.613e24),
        ("how many molecules are in 2.0 mol of CO2", "N(CO2)", 1.204e24),
    ],
)
def test_c_the_element_word_selects_its_atoms(question: str, label: str, expected: float) -> None:
    result = _solve(question)
    assert result.answer.startswith(label), result.answer
    assert math.isclose(_value(result.answer), expected, rel_tol=0.01), result.answer


def test_c_moles_of_atoms_answer_in_moles() -> None:
    result = _solve("how many moles of oxygen atoms are in 2.0 mol of H2SO4")
    assert result.answer == "n(O) = 8.0 mol"


def test_c_the_atom_count_is_explained_not_a_bare_multiplier() -> None:
    result = _solve("how many oxygen atoms are in 2.0 mol of CO2")
    assert any(row == "O atoms per CO2 = 2" for row in result.given), result.given
    assert not any(row.endswith("(2)") for row in result.substitution), result.substitution


@pytest.mark.parametrize(
    "question",
    [
        "how many sodium atoms are in 2.0 mol of CO2",
        "how many oxygen molecules are in 2.0 mol of CO2",
        "how many moles of nitrogen atoms are in 1.0 mol of H2O",
    ],
)
def test_c_an_element_the_formula_does_not_hold_is_not_answered(question: str) -> None:
    intent = extract_chemistry_intent(question)
    if intent is None:
        return
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)


# --- D: a Ka question is chemistry's, never a maths "x = 55555.6" -------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Find the pH of 0.10 M CH₃COOH, Ka = 1.8 x 10^-5",
        "whats the ph of 0.10 M acetic acid, Ka = 1.8 x 10^-5",
        "percent ionization of 0.10 M acetic acid, Ka = 1.8 x 10^-5",
        "Ka = 1.8 x 10^-5. find the pH of 0.10 M CH₃COOH",
        "What is the pOH of 0.20 M NH3, Kb = 1.8 x 10^-5?",
        "Kb = 1.8 x 10^-5 for NH3. Find [OH-] in 0.15 M NH3.",
    ],
)
def test_d_a_ka_question_is_never_maths(question: str) -> None:
    assert detect_subject(question) == "chemistry"


@pytest.mark.parametrize(
    ("question", "expected", "rel"),
    [
        ("whats the ph of 0.10 M acetic acid, Ka = 1.8 x 10^-5", 2.875, 0.01),
        ("Find the pH of 0.10 M CH₃COOH, Ka = 1.8 x 10^-5", 2.875, 0.01),
        ("Ka = 1.8 x 10^-5. find the pH of 0.10 M CH₃COOH", 2.875, 0.01),
        # 1.333% to the two figures of 0.10 M and 1.8 × 10^-5 is 1.3%.
        ("percent ionization of 0.10 M acetic acid, Ka = 1.8 x 10^-5", 1.333, 0.03),
    ],
)
def test_d_a_ka_question_is_right_or_unverified(question: str, expected: float, rel: float) -> None:
    _right_or_declined(question, expected, rel)


@pytest.mark.parametrize(
    "question",
    [
        "solve 2x + 3 = 7",
        "x^2 - 5x + 6 = 0",
        "simplify (x + 1)^2",
        "solve for x: x^2 / (0.10 - x) = 1.8e-5",
        "solve 2x + 3 = 7 and 3x - 1 = 5",
    ],
)
def test_d_maths_stays_maths(question: str) -> None:
    assert detect_subject(question) == "math"


# --- E: display --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "figures", "shown"),
    [
        (62.5, 2, "63"),
        (0.125, 2, "0.13"),
        (2.675, 3, "2.68"),
        (1.005, 3, "1.01"),
        (-62.5, 2, "-63"),
        (9.995, 3, "10.0"),
        (0.0105, 2, "0.011"),
    ],
)
def test_e_answers_round_half_up_as_a_class_does(value: float, figures: int, shown: str) -> None:
    assert format_number(value, significant=figures, keep_zeros=True) == shown


def test_e_dilution_rounds_62_5_up() -> None:
    result = _solve("How many mL of 12 M HCl are needed to make 500 mL of 1.5 M HCl?")
    assert result.answer.endswith("= 63 mL"), result.answer


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Calculate the percent by mass of nitrogen in NH4NO3.", "N in NH4NO3 = 35.00%"),
        ("What is the percent composition of oxygen in MgO?", "O in MgO = 39.70%"),
    ],
)
def test_e_a_formula_only_percent_keeps_its_trailing_zeros(question: str, answer: str) -> None:
    assert _solve(question).answer == answer


def test_e_an_electron_configuration_is_shown_with_superscripts() -> None:
    intent = extract_chemistry_intent("electron configuration of sulfur")
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    assert verified.result.answer == "S: [Ne] 3s^2 3p^4"
    reply = format_direct_chemistry_reply(verified)
    assert "3s² 3p⁴" in reply
    assert "3s2" not in reply


# --- F: routing that sent chemistry to maths ---------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "How many moles of O2 react with 3.0 mol of CH4 in CH4 + 2O2 -> CO2 + 2H2O?",
        "How many grams of H2O form from 4.0 g of H2 and 40.0 g of O2? 2H2 + O2 -> 2H2O",
        "How many grams of water are produced in 2H2 + O2 -> 2H2O?",
        "Al + HCl = AlCl3 + H2 balance pls",
        "whats the ph of 0.0025 M HCl",
        "percent by mass of N in NH4NO3?",
        "M1 = 12 M, M2 = 1.5 M, V2 = 500 mL. Find V1.",
        "Find the cell potential of a Zn/Cu cell with [Zn2+] = 1.0 M and [Cu2+] = 0.010 M at 25 °C",
    ],
)
def test_f_a_chemistry_question_is_not_routed_to_maths(question: str) -> None:
    assert detect_subject(question) == "chemistry"


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Al + HCl = AlCl3 + H2 balance pls", "2 Al + 6 HCl -> 2 AlCl3 + 3 H2"),
        ("balance Fe + O2 = Fe2O3", "4 Fe + 3 O2 -> 2 Fe2O3"),
    ],
)
def test_f_an_equals_sign_is_the_arrow_of_an_equation_to_balance(
    question: str, answer: str
) -> None:
    assert _solve(question).answer == answer


@pytest.mark.parametrize(
    ("question", "label", "expected"),
    [
        ("whats the ph of 0.0025 M HCl", "pH", 2.602),
        ("what is the ph of a 0.050 M NaOH solution", "pH", 12.70),
        ("percent by mass of N in NH4NO3?", "N in NH4NO3", 35.0),
        # Both concentrations labelled in M name a dilution without the word "dilute".
        ("M1 = 12 M, M2 = 1.5 M, V2 = 500 mL. Find V1.", "V1", 62.5),
    ],
)
def test_f_lowercase_ph_percent_by_mass_and_labelled_dilution_are_read(
    question: str, label: str, expected: float
) -> None:
    result = _solve(question)
    assert result.answer.startswith(label), result.answer
    assert math.isclose(_value(result.answer), expected, rel_tol=0.01), result.answer


@pytest.mark.parametrize(
    "text",
    [
        "our team has great chemistry this season",
        "the room is 12 x 10 ft, how much paint do I need",
        "H2O2 hair bleach tips",
        "call me back, my ph is 0412 555 123",
        "PH is the country code for the Philippines",
        "Balance my week: work = gym + sleep",
        "rent = 1200 + 400 utilities, balance it",
        "version 2.5 of the app crashes on Android",
        "I have 3 M followers and want 5 M by May",
        "Dear Ms. Smith, thanks for the 2.0 update",
        "my NaCl lab got a 4.5/5, happy with that",
        "M1 = 2 kg, M2 = 3 kg, V2 = 5 m/s. Find V1.",
        "solve x² - 5x + 6 = 0",
    ],
)
def test_lookalikes_stay_out_of_chemistry(text: str) -> None:
    assert not is_chemistry_question(text), text
    assert detect_subject(text) != "chemistry", text


def test_a_pool_ph_is_chemistry() -> None:
    assert detect_subject("the pool ph is 7.8, is that too high?") == "chemistry"
