"""The laws physics and chemistry share have one implementation: physics'.

A gas law, Q = mcΔT and a half-life are physics catalog laws. A chemistry question routes
to them and reads its answer in its own units: litres and atmospheres, not m³ and Pa.
Chemistry keeps what is chemistry's: Dalton, a partial pressure, a gas over water.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.solvers.solver import CHEMISTRY_SOLVERS
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.direct import maybe_direct_physics_reply
from app.services.solving import VerifiedPhysicsBlock
from app.services.subjects.dispatch import detect_subject

_SETTINGS = Settings(math_tools_enabled=True)


def _physics_block(question: str) -> VerifiedPhysicsBlock:
    intent = extract_physics_intent(question)
    block = None if intent is None else build_verified_physics_block(intent, _SETTINGS)
    assert block is not None, question
    return block


def _physics_answer(question: str) -> str | None:
    intent = extract_physics_intent(question)
    block = None if intent is None else build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("What volume does 2 mol of gas occupy at 300 K and 1 atm?", "49.2 L"),
        ("Find the pressure of 1 mol of gas in 10 L at 273 K.", "2.24 atm"),
        ("A gas at 1 atm and 273 K with 1 mol occupies what volume? PV=nRT", "22.4 L"),
        ("Use ideal gas law PV=nRT: P=2 atm, n=1 mol, T=300 K, find volume", "12.3 L"),
        ("Use Boyle's law: P1 = 2 atm, V1 = 3 L, V2 = 6 L, find P2", "1 atm"),
        ("Use boyle's law: P1 = 2 atm, V1 = 3 L, V2 = 6 L, find P2", "1 atm"),
        ("Use Boyle's law: P1 = 760 mmHg, V1 = 2 L, P2 = 380 mmHg, find V2", "4 L"),
        # 25 °C and 50 °C are read in kelvin: 2 L * 323.15 K / 298.15 K.
        ("Use Charles's law: V1 = 2 L, T1 = 25 °C, T2 = 50 °C, find V2", "2.17 L"),
        (
            "Use the combined gas law: P1 = 1 atm, V1 = 2 L, T1 = 27 °C, "
            "P2 = 202.65 kPa, T2 = 327 °C, find V2",
            "2 L",
        ),
        (
            "Use the combined gas law: P1=1 atm, V1=2 L, T1=300 K, V2=4 L, T2=300 K, find P2",
            "0.5 atm",
        ),
        (
            "How much heat is needed to raise the temperature of 100 g of water by 10 °C? "
            "c = 4.18 J/g°C",
            "4180 J",
        ),
        ("A 100 g sample has a half-life of 5 years. How much remains after 15 years?", "12.5 g"),
        # A latent heat per gram, labelled as a chemistry class labels it.
        ("How much heat is needed to melt 50 g of ice? ΔHfus = 334 J/g", "16700 J"),
        ("How much heat is needed to boil 20 g of water? ΔHvap = 2260 J/g", "45200 J"),
        # Calorimetry: the heat the water gains is the heat the metal loses. In grams and °C
        # the specific heat is per gram and degree.
        (
            "A 50 g piece of metal at 100 °C is dropped into 100 g of water at 20 °C. "
            "The final temperature is 25 °C. Find the specific heat of the metal.",
            "0.558 J/(g·°C)",
        ),
    ],
)
def test_a_shared_law_is_physics_and_answers_in_the_questions_units(
    question: str, answer: str
) -> None:
    assert detect_subject(question) == "physics"
    assert _physics_answer(question) == answer
    assert extract_chemistry_intent(question) is None


@pytest.mark.parametrize(
    "question",
    [
        "Use Boyle's law: P1 = 2, V1 = 3, V2 = 6, find P2",
        "Use Charles's law: V1 = 2 L, T1 = 300, T2 = 600 K, find V2",
    ],
)
def test_a_gas_law_without_a_unit_is_not_verified(question: str) -> None:
    assert _physics_answer(question) is None
    assert extract_chemistry_intent(question) is None


def test_a_gas_stated_in_si_keeps_si() -> None:
    assert _physics_answer("A gas of 2 mol at 300 K occupies 0.05 m^3. Find the pressure.") == (
        "99774 Pa"
    )


def test_chemistry_keeps_no_second_copy_of_a_shared_law() -> None:
    shared = {
        "ideal_gas",
        "boyle",
        "charles",
        "combined_gas",
        "heat",
        "radioactive_decay",
        "decay_constant",
        "exponential_decay",
        "nuclear_activity",
    }
    assert not shared & set(CHEMISTRY_SOLVERS)
    assert {"dalton", "partial_pressure", "gas_over_water"} <= set(CHEMISTRY_SOLVERS)


@pytest.mark.parametrize(
    ("question", "row"),
    [
        # The law answers in the givens' litres; its arithmetic is in SI.
        (
            "Boyle's law: P1 = 100 kPa, V1 = 2 L, P2 = 50 kPa. Find V2.",
            r"V_2 = 0.004\,\mathrm{m³} = 4\,\mathrm{L}",
        ),
        (
            "Find the total capacitance of a 4 µF and a 6 µF capacitor in parallel.",
            r"C = 1 \times 10^{-5}\,\mathrm{F} = 10\,\mathrm{µF}",
        ),
        # A row for a converted answer names its symbol, never a bare "= …".
        (
            "A radioactive isotope has a half-life of 5 days. Find the decay constant.",
            r"\lambda = 1.6 \times 10^{-6}\,\mathrm{1/s} = 0.139\,\mathrm{1/day}",
        ),
    ],
)
def test_the_working_reaches_the_unit_the_answer_is_shown_in(question: str, row: str) -> None:
    assert _physics_block(question).physics_substitutions[-1] == row


@pytest.mark.parametrize("spelling", ["h", "hr", "hrs", "hours"])
def test_every_spelling_of_a_time_unit_gives_one_rate_unit(spelling: str) -> None:
    question = f"A radioactive isotope has a half-life of 5 {spelling}. Find the decay constant."
    assert _physics_answer(question) == "0.139 1/h"


def test_a_given_keeps_its_si_step_when_an_answer_ends_in_the_same_digits() -> None:
    # "4 µF" is not written into the arithmetic: "2.4 µF" only ends with it.
    question = "Find the total capacitance of a 4 µF and a 6 µF capacitor in series."
    reply = maybe_direct_physics_reply(_physics_block(question), question)
    assert reply is not None
    assert r"$C_1 = 4\,\mathrm{µF} \times 10^{-6} = 4 \times 10^{-6}\,\mathrm{F}$" in reply


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        # In kilograms the same law answers per kilogram and kelvin.
        (
            "A 0.2 kg block of copper at 90 °C is placed in 0.5 kg of water at 20 °C. "
            "The equilibrium temperature is 22.4 °C. Find the specific heat capacity of copper.",
            "372 J/(kg·K)",
        ),
        (
            "A 2 kg block absorbs 1000 J and its temperature rises by 10 °C. Find the specific heat.",
            "50 J/(kg·K)",
        ),
        (
            "A 200 g block absorbs 1000 J and its temperature rises by 10 °C. Find the specific heat.",
            "0.5 J/(g·°C)",
        ),
    ],
)
def test_a_specific_heat_is_per_gram_only_when_the_data_are(question: str, answer: str) -> None:
    assert _physics_answer(question) == answer
