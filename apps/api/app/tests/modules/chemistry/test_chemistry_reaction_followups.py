"""A reaction follow-up reaches back only past lines with no number in them.

Review (2026-10-25): the follow-up walked back six user lines, so a heat problem in between was
hijacked ("what about 100 g of water" became the methane needed, 44.5 g), a change of a change
lost the O2 (71 g), and "back to the first one" with two reactions took the wrong one. A list
of units then missed "50 grams", "2 moles", "1 liter" and "$2", so any number now stops the
walk; the live chat's "back to the first one", past "is it 4.5 or 36??", goes to the model.
"""

from __future__ import annotations

import pytest

from app.modules.chat.turn_prep.followups import resolve_subject_followup
from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.followup import chemistry_followup_problem

_BURN_H2 = "Ok so chem hw. how much water do i get if i burn like 4g of h2"
# The student's chat, in order, before the follow-up.
_LIVE_CHAT = (
    _BURN_H2,
    "Wait so its 4.5 or 36?? I'm confused",
    "Ok and the o2 how much of that",
    "Why is water bent tho, co2 isnt",
    "Can u show me both",
    "lol no the molecules",
)


def _answer(problem: str | None) -> str | None:
    intent = None if problem is None else extract_chemistry_intent(problem)
    verified = None if intent is None else build_verified_chemistry(intent)
    return None if verified is None else verified.result.answer


def _recent(*lines: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for line in lines:
        turns.extend((("user", line), ("assistant", "Here is the working.")))
    return turns


def _resolved(lines: tuple[str, ...], line: str) -> str | None:
    messages = [{"role": role, "content": text} for role, text in _recent(*lines)]
    messages.append({"role": "user", "content": line})
    return resolve_subject_followup(line, messages).chemistry


def test_the_live_chats_follow_up_past_numbers_goes_to_the_model() -> None:
    line = "Ok back to the first one. what if i only had 16g of o2"
    assert chemistry_followup_problem(line, _recent(*_LIVE_CHAT)) is None
    assert _resolved(_LIVE_CHAT, line) is None
    # Asked right after the problem, the same line verifies.
    problem = chemistry_followup_problem(line, _recent(_BURN_H2))
    assert "Limiting reagent = O2; 18 g H2O" in (_answer(problem) or "")


@pytest.mark.parametrize(
    ("lines", "line"),
    [
        # A heat problem in between is the problem now.
        (
            (
                "how much methane burns to make 36 g of water",
                "How much heat is needed to raise 50 g of water by 10 °C? (c=4.18)",
            ),
            "what about 100 g of water",
        ),
        (
            (
                "how much methane burns to make 36 g of water",
                "how much heat to warm 50 g of water by 10 C",
            ),
            "what if it was 100 g of water",
        ),
        (
            (
                "how much water do i get if i burn 4 g of h2",
                "how much heat to warm 50 g of water by 10 C",
            ),
            "and how much oxygen",
        ),
        (
            ("how much co2 from burning 180 g of glucose", "how many calories in 10 g of glucose"),
            "what about 20 g of glucose",
        ),
        (
            (
                "2H2 + O2 -> 2H2O. how many grams of H2O from 4 g of H2?",
                "CaCO3 -> CaO + CO2. how many grams of CO2 from 50 g of CaCO3?",
            ),
            "and how much o2 do i need",
        ),
        # Units written out, money and number words: any number is a problem of its own.
        (
            (
                "how much methane burns to make 36 g of water",
                "how much heat is needed to raise 50 grams of water by 10 degrees",
            ),
            "what about 100 grams of water",
        ),
        (
            (
                "how much methane burns to make 36 g of water",
                "what is the molarity of 2 moles of nacl in 1 liter of water",
            ),
            "what about 100 g of water",
        ),
        (
            (
                "how much methane burns to make 36 g of water",
                "how much energy to boil 2 kilograms of water",
            ),
            "what about 100 g of water",
        ),
        (
            (
                "how much methane burns to make 36 g of water",
                "a bottle of water costs $2, how much for 5 bottles",
            ),
            "what about 100 g of water",
        ),
        (
            (
                "how much methane burns to make 36 g of water",
                "how much heat to warm fifty grams of water by ten degrees",
            ),
            "what about 100 g of water",
        ),
        (
            (
                "how much water do i get if i burn 4 g of h2",
                "how many molecules are in 2 moles of h2",
            ),
            "what about 10 g of h2",
        ),
        (
            (
                "how much water do i get if i burn 4 g of h2",
                "how many molecules are in 2 moles of h2",
            ),
            "what if it was 3 mol of h2",
        ),
        # A change of a change: the follow-up before holds a number.
        ((_BURN_H2, "what if i only had 16g of o2"), "what if i had 8 g of h2"),
        ((_BURN_H2, "what if i only had 16g of o2"), "and what if it was 2 g of h2"),
        # "The first one" with two reactions that hold O2.
        (
            (
                "how much water do i get if i burn 4 g of h2",
                "how much co2 from burning 16 g of methane",
            ),
            "ok back to the first one. what if i only had 16g of o2",
        ),
        # A reactant asked as made.
        ((_BURN_H2,), "how much oxygen is made"),
    ],
)
def test_a_follow_up_does_not_reach_past_a_problem_in_between(
    lines: tuple[str, ...], line: str
) -> None:
    assert chemistry_followup_problem(line, _recent(*lines)) is None
    assert _resolved(lines, line) is None


def test_an_amount_of_the_last_problems_substance_changes_that_problem() -> None:
    """Asked of the moles question in between, not of the reaction before it."""
    lines = ("how much water do i get if i burn 4 g of h2", "How many moles are in 10 g of H2?")
    problem = chemistry_followup_problem("what about 20 g of H2?", _recent(*lines))
    assert problem == "How many moles are in 20 g of H2?"
    assert "n(H2) = 9.9 mol" in (_answer(problem) or "")


@pytest.mark.parametrize("between", ["whats a mole again", "lol ok", "wait im confused"])
def test_lines_with_no_number_are_passed(between: str) -> None:
    lines = (_BURN_H2, between)
    problem = chemistry_followup_problem(
        "ok back to the first one. what if i only had 16g of o2", _recent(*lines)
    )
    assert "18 g H2O" in (_answer(problem) or "")
