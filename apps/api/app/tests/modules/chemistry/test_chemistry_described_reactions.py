"""A reaction told in words is read through its balanced equation, or declines.

Live failure (2026-10-25): "how much water do i get if i burn like 4g of h2" got no verified
answer, and the free model wrote 4.5 g, 35.7 g and 36 g in one reply. Its follow-up "ok back
to the first one. what if i only had 16g of o2" (O2 limits the water to 18 g) was answered as
another question.
"""

from __future__ import annotations

import pytest

from app.modules.chat.continuation_subject import effective_presentation_subject
from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.extractors.described import (
    burn_products,
    described_reaction,
    written_reaction_question,
)
from app.modules.chemistry.followup import chemistry_followup_problem
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.species_words import lowercase_formula, substance_mentions

_BURN_H2 = "Ok so chem hw. how much water do i get if i burn like 4g of h2"
_BURN_CH4 = "how much oxygen is needed to burn 16 g of methane"


def _answer(question: str) -> str | None:
    intent = extract_chemistry_intent(question)
    verified = None if intent is None else build_verified_chemistry(intent)
    return None if verified is None else verified.result.answer


def _recent(*problems: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for problem in problems:
        turns.extend((("user", problem), ("assistant", "Here is the working.")))
    return turns


@pytest.mark.parametrize(
    ("question", "equation", "answer"),
    [
        (_BURN_H2, "2 H2 + O2 -> 2 H2O", "m(H2O) = 36 g"),
        ("how much water do i get if i burn 4 g of hydrogen", "2 H2 + O2 -> 2 H2O", "36 g"),
        ("how many grams of water form when 4 g of H2 burns in oxygen", "2 H2 + O2", "36 g"),
        ("4 g of H2 reacts with excess O2. what mass of water is produced?", "2 H2", "36 g"),
        ("how many grams of CO2 are made when 10.0 g of propane burns", "3 CO2", "29.9 g"),
        (_BURN_CH4, "CH4 + 2 O2 -> CO2 + 2 H2O", "m(O2) = 64 g"),
        ("how many grams of co2 form when 18.0 g of glucose burns", "6 CO2", "26.4 g"),
        ("how much MgO forms when 2.4 g of magnesium burns in air", "2 Mg + O2", "4.0 g"),
        ("how much Fe2O3 forms when 5.6 g of iron burns", "4 Fe + 3 O2 -> 2 Fe2O3", "8.0 g"),
        ("how many grams of NH3 form when 28 g of N2 reacts with excess H2", "N2 + 3 H2", "34 g"),
        (
            "how many grams of NaCl form when 4.6 g of sodium reacts with excess chlorine",
            "",
            "12 g",
        ),
        ("how many moles of water form when 2 mol of h2 burns", "2 H2 + O2", "2.0 mol"),
        ("how many grams of H2 must burn to make 36 g of water", "2 H2", "m(H2) = 4.0 g"),
        ("how much water if 3.0 g of hydrogen and 16.0 g of oxygen react", "", "= O2; 18 g"),
        ("4 g of H2 and 16 g of O2 react. Which is the limiting reagent?", "", "= O2; 18 g"),
        (
            "If 4.0 g of H2 reacts with 16.0 g of O2 to make water, which is the limiting "
            "reagent and how many grams of water form?",
            "2 H2 + O2 -> 2 H2O",
            # 4.0 g limits the answer to two figures.
            "Limiting reagent = O2; 18 g H2O",
        ),
        ("how many grams of NH3 can be made from 28 g of nitrogen and 6 g of hydrogen", "", "H2"),
        ("2 g of hydrogen combines with oxygen, how much water", "", "m(H2O) = 18 g"),
        (
            "When 10.0 g of N2 reacts with excess H2, 10.0 g of NH3 forms. What is the percent "
            "yield?",
            "N2 + 3 H2 -> 2 NH3",
            "82.2%",
        ),
    ],
)
def test_a_reaction_told_in_words_is_read_as_its_balanced_equation(
    question: str, equation: str, answer: str
) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is not None and intent.kind == "stoichiometry"
    assert equation in (intent.equation or "")
    assert answer in (_answer(question) or "")
    assert is_chemistry_question(question)


@pytest.mark.parametrize(
    "question",
    [
        # The other product is not named, and a product is never guessed.
        "How many grams of H2 form when 6.5 g of Zn reacts with HCl?",
        "How many grams of AgCl precipitate when 50.0 mL of 0.100 M AgNO3 reacts with excess NaCl?",
        "how many grams of water form when 4.0 g of HCl reacts with NaOH",
        # Incomplete combustion: CH4 + O2 -> CO alone does not balance.
        "how much CO2 is made when 12 g of methane burns to make carbon monoxide",
        # A compound the tables do not name, or an oxide with two charges.
        "how much water forms when 3.4 g of hydrogen peroxide decomposes and burns",
        "how much iron oxide forms when 5.6 g of iron burns",
        # A heat, not an amount, is asked.
        "if I burn 10 g of h2 how much heat is released",
        # No amount.
        "how much water forms when hydrogen burns",
    ],
)
def test_a_reaction_it_cannot_close_declines(question: str) -> None:
    assert _answer(question) is None


@pytest.mark.parametrize(
    "text",
    [
        "i burned my hand on the stove, how do i treat it",
        "burn 500 calories a day",
        "how many calories does burning 4 g of fat release",
        "how much water should I drink if I burn 600 calories running",
        "water and oil don't react, why?",
        "hydrogen bonding in water",
        "what happens when sodium reacts with water",
        "my car burns 5 g of fuel per km, how much CO2 is that",
        "how much bread can be made from 500 g of flour and 300 g of water",
        "the candle burned for 3 hours, how much wax is left",
    ],
)
def test_burning_and_reacting_in_everyday_words_is_not_stoichiometry(text: str) -> None:
    assert described_reaction(text) is None
    assert extract_chemistry_intent(text) is None
    assert not is_chemistry_question(text)


def test_an_arrow_between_things_that_are_not_substances_is_not_a_reaction() -> None:
    text = "Plan A -> B, how much will it cost for 4 g of gold?"
    assert written_reaction_question(text) is None
    assert not is_chemistry_question(text)


def test_an_essay_about_combustion_is_never_solved() -> None:
    essay = "write an essay about combustion in car engines"
    assert described_reaction(essay) is None
    assert extract_chemistry_intent(essay) is None


@pytest.mark.parametrize(
    ("fuel", "products"),
    [
        ("CH4", ("CO2", "H2O")),
        ("C2H5OH", ("CO2", "H2O")),
        ("H2", ("H2O",)),
        ("C", ("CO2",)),
        ("S", ("SO2",)),
        ("Mg", ("MgO",)),
        ("Fe", None),
        ("Na", None),
        ("NH3", None),
        ("H2O", None),
    ],
)
def test_what_a_fuel_burns_to(fuel: str, products: tuple[str, ...] | None) -> None:
    assert burn_products(fuel) == products


@pytest.mark.parametrize(
    ("token", "formula"),
    [
        ("h2", "H2"),
        ("o2", "O2"),
        ("co2", "CO2"),
        ("ch4", "CH4"),
        ("nh3", "NH3"),
        ("c3h8", "C3H8"),
        ("h2o", "H2O"),
        ("fe2o3", "Fe2O3"),
        ("cuso4", "CuSO4"),
        ("ca(oh)2", "Ca(OH)2"),
        ("c2h5oh", "C2H5OH"),
        # No digit, or two school readings, or none: a word, not a formula.
        ("co", None),
        ("hf", None),
        ("caco3", None),
        ("h1n1", None),
        ("mp3", None),
        ("b2b", None),
        ("covid19", None),
        ("f150", None),
    ],
)
def test_a_lowercase_formula_is_read_only_when_one_substance_fits(
    token: str, formula: str | None
) -> None:
    assert lowercase_formula(token) == formula


@pytest.mark.parametrize(
    ("text", "formulas"),
    [
        ("burn like 4g of h2 for water", ["H2", "H2O"]),
        ("2.4 g of magnesium makes magnesium oxide", ["Mg", "MgO"]),
        ("iron(III) oxide from iron", ["Fe2O3", "Fe"]),
        ("12 g of C burns", ["C"]),
        ("If I burn it at 25 C", []),
        ("hydrogen bonding in water", ["H2O"]),
        ("hydrogen peroxide", None),
        ("iron oxide", None),
    ],
)
def test_substances_named_in_words(text: str, formulas: list[str] | None) -> None:
    mentions = substance_mentions(text)
    found = None if mentions is None else [mention.formula for mention in mentions]
    assert found == formulas


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("What mass of CO2 is produced from 10.0 g of C3H8? C3H8 + 5O2 -> 3CO2 + 4H2O", "29.9 g"),
        ("C3H8 + 5O2 -> 3CO2 + 4H2O. Find the mass of CO2 produced from 10.0 g of C3H8.", "29.9 g"),
        # A head that names only the substance asks in the unit the amount is given in.
        ("2H2 + O2 -> 2H2O. how much H2O from 4 g of H2?", "m(H2O) = 36 g"),
        ("N2 + 3H2 -> 2NH3. How much NH3 is made from 2.0 mol N2?", "4.0 mol"),
        # Its substances named in words or lowercase beside the written equation.
        ("2H2 + O2 -> 2H2O how much water from 4g of h2", "m(H2O) = 36 g"),
        ("2H2 + O2 -> 2H2O. how many grams of water from 4 g of hydrogen?", "m(H2O) = 36 g"),
        ("C3H8 + 5O2 -> 3CO2 + 4H2O. what mass of co2 from 10.0 g of propane", "29.9 g"),
    ],
)
def test_a_written_equation_answers_what_mass_and_how_much(question: str, answer: str) -> None:
    assert is_chemistry_question(question)
    assert answer in (_answer(question) or "")


@pytest.mark.parametrize(
    ("prior", "line", "answer"),
    [
        (_BURN_H2, "ok back to the first one. what if i only had 16g of o2", "= O2; 18 g H2O"),
        (_BURN_H2, "what if i only had 16g of o2", "= O2; 18 g H2O"),
        (_BURN_H2, "what about 10 g instead", "m(H2O) = 89 g"),
        (_BURN_H2, "what if it was 10 g of h2", "m(H2O) = 89 g"),
        (_BURN_H2, "and 2 mol of h2?", "m(H2O) = 36 g"),
        (_BURN_H2, "and how much o2 do i need", "m(O2) = 32 g"),
        (_BURN_H2, "how much oxygen is needed", "m(O2) = 32 g"),
        (_BURN_CH4, "what about the co2", "m(CO2) = 44 g"),
        (_BURN_CH4, "and how many grams of water", "m(H2O) = 36 g"),
        (_BURN_CH4, "what if it was 8 g of ch4", "m(O2) = 32 g"),
        (
            "2H2 + O2 -> 2H2O. 4 g of H2 and 16 g of O2, how many grams of water?",
            "what about 8 g of o2",
            "= O2; 9.0 g H2O",
        ),
    ],
)
def test_a_follow_up_changes_the_reaction_it_names(prior: str, line: str, answer: str) -> None:
    problem = chemistry_followup_problem(line, _recent(prior))
    assert problem is not None
    assert answer in (_answer(problem) or "")


def test_a_follow_up_finds_the_reaction_two_exchanges_back() -> None:
    recent = _recent(_BURN_H2, "whats a mole again")
    problem = chemistry_followup_problem(
        "ok back to the first one. what if i only had 16g of o2", recent
    )
    assert problem is not None
    assert "18 g H2O" in (_answer(problem) or "")
    assert effective_presentation_subject("what if i only had 16g of o2", recent) == "chemistry"


@pytest.mark.parametrize(
    "line",
    [
        "what if i only had 16 dollars",
        "is co2 bad for the planet?",
        "how much co2 does a car emit per year",
        "and 2 g of sugar in my coffee?",
        "co2",
        # The amount asked is the amount stated.
        "and the h2?",
    ],
)
def test_a_line_that_only_sounds_like_a_reaction_follow_up_declines(line: str) -> None:
    assert chemistry_followup_problem(line, _recent(_BURN_H2)) is None
