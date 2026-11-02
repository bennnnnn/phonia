"""A reaction question is answered only when every word of its ask is a known phrase.

Review (2026-10-25) of reactions told in words: "how many atoms of oxygen are needed to burn 4 g
of h2" was verified as 6.0e23 O2 molecules (the O atoms are 1.2e24); incomplete
combustion was verified as complete; H2O2 from burning hydrogen, H2 from burning methane, and
SO3 from burning sulfur were verified; "4 g of h2 burns in 100 g of air" ignored the air; "How
many H2O molecules form" was answered in grams; drinking and breathing questions were claimed;
and "mass" next to an arrow made maths lines chemistry. Each declines now, or routes as before.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways.pubchem_gateway import PubChemResult
from app.modules.chemistry import context as chemistry_context
from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.context import build_chemistry_augmentation
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.request import is_chemistry_question
from app.services.subjects.dispatch import detect_subject


def _answer(question: str) -> str | None:
    intent = extract_chemistry_intent(question)
    verified = None if intent is None else build_verified_chemistry(intent)
    return None if verified is None else verified.result.answer


@pytest.mark.parametrize(
    "question",
    [
        # Atoms of an element are not its molecules.
        "how many atoms of oxygen are needed to burn 4 g of h2",
        "how many atoms of oxygen react with 4 g of hydrogen when it burns",
        "how many atoms of chlorine react with 23 g of sodium to make sodium chloride",
        "how many atoms of oxygen in the water from burning 4 g of h2",
        "2H2 + O2 -> 2H2O. how many atoms of oxygen react with 4 g of H2?",
        "2H2 + O2 -> 2H2O. How many atoms of O2 react with 4 g of H2?",
        # A burning the question says is not complete.
        "how much co2 from incomplete combustion of 16 g of methane",
        "how much CO2 forms when 16 g of methane burns in limited oxygen",
        "how much CO2 if 12 g of carbon burns in insufficient oxygen",
        "how much co2 forms when 16 g of methane burns incompletely",
        "how much co2 from the partial combustion of 44 g of propane",
        # Every word of a product list is a substance: "co" is not read.
        "how much co2 forms when 16 g of ch4 reacts with o2 to make co2 and co",
        # A fuel the table knows makes its own oxides and nothing else.
        "how much h2o2 is made from burning 4 g of h2",
        "how much h2 and co2 from burning 16 g of methane",
        "how much co2 and h2 from burning 16 g of methane",
        "how much so3 from burning 32 g of sulfur",
        "how much CO from burning 12 g of carbon",
        # An amount of something no table names.
        "how much water forms when 4 g of h2 burns in 100 g of air",
        # A unit no chain answers in.
        "how much water in ml do i get if i burn 4 g of h2",
        "how much water in kg if i burn 4000 g of h2",
        "how much co2 in kg from burning 16 g of methane",
        "2H2 + O2 -> 2H2O. How much H2O in liters forms from 4 g of H2?",
        # A reactant asked as made.
        "how much oxygen is made when 4 g of h2 burns",
        "how many grams of oxygen are produced when 4 g of h2 burns",
        # Two asks, or an ask the grammar does not know.
        "how much co2 if i burn 4 g of ch4 and how much water",
        "how much co2 is left over after burning 16 g of methane",
    ],
)
def test_a_reaction_question_it_cannot_read_whole_declines(question: str) -> None:
    assert _answer(question) is None


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("2H2 + O2 -> 2H2O. How many H2O molecules form from 4 g of H2?", "1.2 × 10^24"),
        ("how many water molecules form when i burn 4 g of h2", "N(H2O) = 1.2 × 10^24"),
        ("how many h2o molecules do i get if i burn 4 g of h2", "N(H2O) = 1.2 × 10^24"),
        ("N2 + 3H2 -> 2NH3. How many NH3 molecules from 28 g of N2?", "N(NH3) = 1.2 × 10^24"),
        ("how many molecules of oxygen are needed to burn 4 g of h2", "N(O2) = 6.0 × 10^23"),
        # Main's mole answers stay moles.
        ("2H2 + O2 -> 2H2O. How many H2O form from 4 g of H2?", "n(H2O) = 2.0 mol"),
        ("N2 + 3H2 -> 2NH3. How much NH3 is made from 2.0 mol N2?", "n(NH3) = 4.0 mol"),
        ("how many moles of O2 are needed to burn 3.0 mol of CH4? CH4 + 2O2 → CO2 + 2H2O", "6.0"),
        # The oxide a non-table fuel burns to, named.
        ("how much NO2 forms when 14 g of N2 reacts with O2", "m(NO2) = 46 g"),
        ("how much SO3 forms when 64 g of SO2 reacts with O2", "m(SO3) = 80 g"),
        # Known asks and the substances they ask.
        ("how much oxygen do i need to burn 16 g methane", "m(O2) = 64 g"),
        ("OK so how much water do i get if i burn 4 g of h2", "m(H2O) = 36 g"),
        ("how much water vapour forms when 1 mol of methane burns", "n(H2O) = 2.0 mol"),
    ],
)
def test_a_reaction_question_read_whole_is_answered(question: str, answer: str) -> None:
    assert answer in (_answer(question) or "")


@pytest.mark.parametrize(
    "text",
    [
        "how much water do i need to drink if i burn 200 g of sugar running",
        "if I burn 100 g of glucose on a run how much water should i drink",
        "how much oxygen do i need to breathe to burn 100 g of glucose",
        "how much co2 do i exhale if i burn 100 g of glucose",
    ],
)
def test_what_the_body_drinks_or_breathes_is_not_a_reaction(text: str) -> None:
    assert extract_chemistry_intent(text) is None
    assert not is_chemistry_question(text)
    assert detect_subject(text) is None


@pytest.mark.parametrize(
    ("text", "subject"),
    [
        ("if the mass doubles, F -> 2F, what happens to the acceleration", "math"),
        ("map each point P -> 2P, what is the mass of the region", "math"),
        ("S -> 2S when the mass is scaled, find the new area", "math"),
        ("N -> 2N, how does the mass change", "math"),
        ("C -> C2 mass ratio in a graph", "math"),
        ("the center of mass of a triangle with vertices A -> B -> C", None),
    ],
)
def test_mass_beside_an_arrow_is_not_chemistry(text: str, subject: str | None) -> None:
    assert not is_chemistry_question(text)
    assert detect_subject(text) == subject


@pytest.mark.asyncio
async def test_the_gate_of_a_lookup_is_read_off_the_event_loop() -> None:
    """``build_chemistry_augmentation`` asked the gate on the event loop (Golden Rule 7)."""
    on_loop: list[bool] = []
    gate = chemistry_context.is_chemistry_question

    def watched(content: str) -> bool:
        try:
            asyncio.get_running_loop()
            on_loop.append(True)
        except RuntimeError:
            on_loop.append(False)
        return gate(content)

    lookup = AsyncMock(return_value=PubChemResult(compound=None, error="not found"))
    with (
        patch.object(chemistry_context, "is_chemistry_question", watched),
        patch("app.modules.chemistry.context.pubchem_gateway.lookup_by_name", lookup),
    ):
        await build_chemistry_augmentation("what is caffeine", Settings())
    assert on_loop == [False]
    lookup.assert_awaited_once()
