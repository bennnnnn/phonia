"""Circuit givens read whole or not at all (2026-10-30, a Grade 10 physics book's circuits,
three of which were certified wrong, then two rounds of adversarial review).

- A value named with "the" may be a resistor stated elsewhere or a new one: a definite
  group whose values are all its own names each one; one sharing a value declines.
- One resistor's share (its p.d., its current) is not the network's total.
- A part's label ("12.6 a) Draw …") is no unit.
- One quantity stated with two values is no single law's given.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.tests.modules.physics.support import answer_number

_SETTINGS = Settings(mock_llm_enabled=True)


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("A 6 Ω and a 6 Ω resistor are connected in series. Find the total resistance.", 12.0),
        (
            "Find the equivalent resistance of the 6 Ω, 6 Ω and 3 Ω resistors connected in "
            "parallel.",
            1.5,
        ),
        (
            "Find the combined resistance of the 2 Ω, 2 Ω and 4 Ω resistors connected in series.",
            8.0,
        ),
        (
            "Find the total resistance of the 5 Ω and 5 Ω resistors joined in series with a "
            "10 Ω resistor.",
            20.0,
        ),
        ("Find the total resistance of the 10 Ω and the 10 Ω resistors in series.", 20.0),
        ("A resistor R of 6 Ω and a 3 Ω resistor are in series. Find the total resistance.", 9.0),
        # One list names each resistor, "the" or not.
        (
            "In the circuit, a 6 Ω resistor and the 6 Ω lamp are connected in series with a "
            "3 Ω resistor. Find the total resistance.",
            15.0,
        ),
        ("A 6 Ω resistor is in series with another 6 Ω resistor. Find the total resistance.", 12.0),
        (
            "A 4 Ω and a 8 Ω resistor are connected in series to a 12 V battery. Find the "
            "current drawn from the battery.",
            1.0,
        ),
        ("A 6 Ω and a 3 Ω resistor are in parallel across 6 V. Find the current.", 3.0),
        # A one-letter unit before ")" with no next part after it is still a unit.
        ("A force of 10 N) acts on a 2 kg mass. Find the acceleration.", 5.0),
        ("A current (2 A) flows through a 6 Ω resistor. Find the voltage.", 12.0),
    ],
)
def test_a_circuit_read_whole_keeps_its_card(text: str, value: float) -> None:
    answer = _answer(text)
    assert answer is not None, text
    assert answer_number(answer) == pytest.approx(value), answer


@pytest.mark.parametrize(
    "text",
    [
        # Certified 200 Ω: "the 50 Ω resistor" of part (c) read as a third resistor.
        "In the circuit the battery has negligible internal resistance. Calculate: a) the "
        "total resistance in the circuit c) the potential difference across the 50 Ω "
        "resistor. [Figure: a 3 V battery with a 50 Ω resistor and a 100 Ω resistor in "
        "series.]",
        # Back-references: counted again they certify 60 Ω.
        "A 10 Ω resistor and a 20 Ω resistor are joined in series. What is the total "
        "resistance of the 10 Ω resistor and the 20 Ω resistor together?",
        # "the 6 Ω" may be another resistor or the one before.
        "A 6 Ω resistor is connected in parallel with the 6 Ω resistor and the 3 Ω resistor "
        "of the circuit. Find the equivalent resistance.",
        # Certified 6 Ω: an unknown R beside "the 3 Ω resistor" named twice.
        "a) What current is flowing round the circuit? b) How great must the p.d. be across "
        "resistor R? c) What is the resistance of resistor R? [Figure: a 48 V battery in "
        "series with a 3 Ω resistor and a resistor R; a voltmeter across the 3 Ω resistor "
        "reads 9 V.]",
        # One resistor's share is not the network's total (certified 150 Ω, 3 A, 5 A).
        "A 50 Ω and a 100 Ω resistor are in series with a 12 V battery. Find the p.d. across "
        "the 50 Ω resistor.",
        "A 50 Ω and a 100 Ω resistor are in series with a 12 V battery. Find the p.d. of the "
        "50 Ω resistor.",
        "A 6 Ω and a 3 Ω resistor are in parallel across 6 V. Find the current through the "
        "3 Ω resistor.",
        "A 6 Ω and a 3 Ω resistor are in parallel across 6 V. What current does the 3 Ω "
        "resistor draw?",
        "A 4 Ω and a 6 Ω resistor are in parallel across 12 V. Find the current in the 6 Ω "
        "resistor.",
        "A 6 Ω and a 3 Ω resistor are in parallel across 6 V. Find the current in each resistor.",
        "A 6 Ω and a 3 Ω resistor are in parallel across 6 V. Find the current through the "
        "second resistor.",
        # Certified 0.952 Ω: "12.6 a) Draw…" read as 12.6 A beside the bulb's 12 V rating,
        # whichever way the next part is labelled.
        "A 12 V light bulb is put under test, with the following results: Current through "
        "bulb (A): 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6 p.d. across bulb (V): 1.4, 2.6, 3.9, 5.5, "
        "7.4, 9.7, 12.6\na) Draw the circuit you would use. b) Work out the resistance R of "
        "the bulb for each set of readings.",
        "A 12 V light bulb is tested: Current (A): 0.4, 0.6, 1.6 p.d. (V): 1.4, 2.6, 12.6 a) "
        "Draw the circuit. (b) Work out the resistance R of the bulb.",
        "A 12 V light bulb is tested: Current (A): 0.4, 0.6, 1.6 p.d. (V): 1.4, 2.6, 12.6 a. "
        "Draw the circuit. b. Work out the resistance R of the bulb.",
        # Third review: a value named again without "the", one resistor's share however
        # worded, and a meter's reading taken for the supply.
        "A 50 Ω and a 100 Ω resistor are in series with a 12 V battery. Find the total "
        "resistance and the p.d. across R1 (50 Ω).",
        "50 Ω and 100 Ω resistors are in series with a 12 V battery. Find the total "
        "resistance. Which resistor, 50 Ω or 100 Ω, has the larger voltage?",
        "A 6 Ω and a 3 Ω resistor are in parallel across 6 V. Find the current in the 3-Ω "
        "resistor.",
        "A 6 Ω and a 3 Ω resistor are in parallel across 6 V. Find the current in the "
        "smaller resistor.",
        "A 6 Ω and a 3 Ω resistor are in parallel across 6 V. Find the current through each.",
        "A voltmeter connected across an 8 Ω resistor in series with a 4 Ω resistor reads "
        "8 V. Find the current.",
        # Two voltages: which one Ohm's law takes is a guess.
        "A 12 V battery is connected to a 4 Ω lamp, and a voltmeter across the lamp reads 10 V. "
        "Find the current.",
    ],
)
def test_a_circuit_read_in_part_declines(text: str) -> None:
    assert _answer(text) is None


# 2026-11-01 retro review: two equal resistors were certified as one. A part named by its
# noun after an article ("a resistor of 10 Ω", "another lamp of resistance 6 Ω") is a new
# part; a series/parallel question whose resistances were not all read never falls back to
# Ohm's law on one of them, and nor do two parts with no wiring stated.
@pytest.mark.parametrize(
    ("text", "value"),
    [
        (
            "A resistor of 10 Ω and another resistor of 10 Ω are connected in parallel across "
            "a 5 V battery. Find the total current.",
            1.0,
        ),
        (
            "A 6 Ω resistor is connected in parallel with a resistor of 6 Ω across a 12 V "
            "battery. Find the current drawn from the battery.",
            4.0,
        ),
        (
            "A bulb of resistance 4 Ω is connected in series with a heater of resistance 4 Ω "
            "across 16 V. Find the current.",
            2.0,
        ),
        (
            "A resistor of 8 Ω is connected in series with a resistor of 8 Ω. Find the total resistance.",
            16.0,
        ),
        (
            "Two resistors of 4 Ω and 12 Ω are connected in parallel across 6 V. What current "
            "does the battery supply?",
            2.0,
        ),
        (
            "A 6 Ω resistor is connected to a 12 V battery. What is the current through the "
            "6 Ω resistor?",
            2.0,
        ),
    ],
)
def test_equal_resistors_named_by_their_noun_are_two(text: str, value: float) -> None:
    answer = _answer(text)
    assert answer is not None and answer_number(answer) == pytest.approx(value)


@pytest.mark.parametrize(
    "text",
    [
        "A 6 Ω resistor and the other 6 Ω resistor are connected in series across 24 V. "
        "Find the current.",
        "A lamp of resistance 6 Ω and another lamp of resistance 6 Ω are connected to a 6 V "
        "supply. Find the current.",
        "A 50 Ω resistor is in series with a 100 Ω resistor across 30 V. Find the p.d. across "
        "the 50 Ω resistor.",
    ],
)
def test_a_part_not_certainly_new_or_unwired_declines(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    "text",
    [
        # Two parts and no wiring stated, named by nouns the reader does not list.
        "An electric kettle of 30 Ω and an electric iron of 30 Ω are connected to a 240 V "
        "supply. Find the current.",
        "A component of 6 Ω and another component of 6 Ω are connected to a 12 V battery. "
        "Find the current.",
        "A 6 Ω resistor and the other 6 Ω resistor are joined end to end across 12 V. Find "
        "the current.",
        # A second part with no value of its own.
        "A 6 Ω resistor is connected in parallel with an identical resistor across 12 V. "
        "Find the total current.",
        "A 6 Ω resistor is connected in series with another resistor of the same value "
        "across 12 V. Find the current.",
        "A lamp of resistance 6 Ω is connected in parallel with a lamp of the same "
        "resistance across 6 V. Find the total current.",
        "A 10 Ω resistor is connected in series with an identical one across a 10 V supply. "
        "Find the current.",
        "A 6 Ω resistor is connected in parallel with a second resistor across 12 V. Find "
        "the total current.",
        # The cell's internal resistance is its own part, even at the resistor's value.
        "A battery of emf 12 V has an internal resistance of 2 Ω. It is connected to a 2 Ω "
        "resistor. Find the power in the 2 Ω resistor.",
        "A cell of emf 1.5 V and internal resistance 0.5 Ω is connected across a 0.5 Ω wire. "
        "Find the current.",
    ],
)
def test_two_parts_not_read_as_one_decline(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("text", "value"),
    [
        (
            "A cell of emf 12 V and internal resistance 2 Ω is connected to a 2 Ω resistor. "
            "Find the current.",
            3.0,
        ),
        (
            "A 6 V battery with internal resistance 3 Ω is connected to a 3 Ω lamp. What "
            "current flows?",
            1.0,
        ),
        # One resistor named again by "the" or "this" in a series question.
        (
            "A 6 Ω resistor is connected in series with a switch and a 12 V battery. Find the "
            "current in the 6 Ω resistor.",
            2.0,
        ),
        (
            "A 6 Ω resistor is connected in series with a 12 V battery. Find the power "
            "dissipated in the 6 Ω resistor.",
            24.0,
        ),
        (
            "A 4 Ω heater is connected in series with a 12 V battery. What current flows "
            "through this 4 Ω heater?",
            3.0,
        ),
        (
            "A current of 2 A flows through a 6 Ω resistor in series with a lamp. Find the "
            "voltage across the 6 Ω resistor.",
            12.0,
        ),
    ],
)
def test_parts_counted_by_their_names_not_their_values(text: str, value: float) -> None:
    answer = _answer(text)
    assert answer is not None and answer_number(answer) == pytest.approx(value)
