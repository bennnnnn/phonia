"""Counted circuit parts: one value stated for several parts is that value in each.

"Two resistors, each with a resistance of 10 Ω, in parallel across 5 V" verified 0.5 A,
the current of one resistor (2026-10-31). Every way of saying the count reads the same, and
a count the question leaves unclear declines instead of reading one part.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.extractors.counted_parts import counted_items
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    return None if block is None else block.canonical_answer


@pytest.mark.parametrize(
    "text,answer",
    [
        (
            "Two resistors, each with a resistance of 10 Ω, are connected in parallel across "
            "5 V. What is the total current?",
            "1 A",
        ),
        (
            "Two resistors of 10 Ω each are connected in parallel across a 5 V battery. "
            "Find the total current.",
            "1 A",
        ),
        (
            "Each of the two resistors has a resistance of 10 Ω. They are connected in parallel "
            "to a 5 V supply. What is the current from the supply?",
            "1 A",
        ),
        ("Two 10-ohm resistors are connected in series across 12 V. Find the current.", "0.6 A"),
        ("Two 10 Ω resistors are connected in parallel across 5 V. Find the total current.", "1 A"),
        (
            "Three identical resistors of 6 Ω are connected in series. What is the total "
            "resistance?",
            "18 Ω",
        ),
        (
            "Three resistors, each 4 Ω, are connected in parallel. Find the equivalent resistance.",
            "1.33 Ω",
        ),
        (
            "A 4 Ω resistor is in series with two resistors of 6 Ω each in parallel. Find the "
            "total resistance.",
            "7 Ω",
        ),
        # The items named a few words after the value (retro review, 2026-11-01).
        (
            "Two 10 Ω carbon resistors are connected in parallel across 5 V. Find the total "
            "current.",
            "1 A",
        ),
        ("Two 4 Ω coils are joined in series across 16 V. Find the current.", "2 A"),
    ],
)
def test_a_value_stated_for_counted_resistors_is_in_each(text: str, answer: str) -> None:
    assert _verified_answer(text) == answer


@pytest.mark.parametrize(
    "text",
    [
        # One value, two resistors, and "each" unsaid: 10 Ω each, or in all?
        "Two resistors of 10 Ω are connected in parallel across 5 V. What is the total current?",
        # "Each", but not how many.
        "Resistors of 10 Ω each are connected in parallel across 5 V. Find the total current.",
        # How they are wired is not said.
        "Two resistors, each 10 Ω, are connected to a 5 V battery. What is the current?",
        # No reader takes the power of a network: it must not take one resistor's.
        "Two resistors, each of 10 Ω, are in series with a 12 V battery. Find the power "
        "dissipated.",
        # Cells, capacitors and lamps: no reader combines them, so none reads one of them.
        "Two 1.5 V cells in series are connected to a 3 Ω resistor. What is the current?",
        "A pair of 1.5 V cells powers a 3 Ω lamp. What is the current?",
        "Two capacitors of 10 µF each are charged to 12 V. Find the energy stored.",
        "Two 60 W bulbs are left on for 5 hours. How much electrical energy do they use?",
        # Read as one item before the retro review (2026-11-01): the items named a few words
        # on, a count above twelve or a dozen, or "of" a value for parts other than resistors.
        "Two 100 W electric bulbs are used for 5 hours. Find the energy consumed in kWh.",
        "Two 2 kW electric heaters run for 3 hours. How much energy do they use in kWh?",
        "Two 1.5 V dry cells are connected in series to a 3 Ω bulb. Find the current.",
        "Two 60 W ceiling fans are switched on for 4 hours. Find the energy in kWh.",
        "A family uses three 40 W tube lights for 6 hours a day. Find the energy used in kWh.",
        "Fifteen 40 W bulbs are used for 2 hours. Find the energy consumed in kWh.",
        "A dozen 60 W bulbs are used for 5 hours. Find the energy consumed in kWh.",
        "A house has two fans of 75 W each used for 10 h. Find the energy consumed in kWh.",
        "Two heaters of 2 kW are used for 3 hours. Find the energy used in kWh.",
        "Two lamps of 6 Ω are connected in parallel across 6 V. Find the total current.",
    ],
)
def test_a_counted_part_a_reader_cannot_account_for_declines(text: str) -> None:
    assert _verified_answer(text) is None


@pytest.mark.parametrize(
    "text,answer",
    [
        # A count of something that is not a part.
        (
            "A 10 Ω resistor is connected across 5 V. What is the current through each of the "
            "two wires?",
            "0.5 A",
        ),
        # Counted parts with no value of their own: the values are the circuit's.
        (
            "Two bulbs are connected in parallel to a 12 V battery and draw 2 A in total. What "
            "is the total resistance?",
            "6 Ω",
        ),
        # Every counted resistor's value stated.
        (
            "Two resistors of 4 Ω and 6 Ω are connected in series across 10 V. Find the current.",
            "1 A",
        ),
        (
            "Three resistors of 2, 3 and 6 ohms are connected in parallel. Find the total "
            "resistance.",
            "1 Ω",
        ),
    ],
)
def test_counts_that_name_no_shared_value_read_as_before(text: str, answer: str) -> None:
    assert _verified_answer(text) == answer


@pytest.mark.parametrize(
    "text,items",
    [
        ("each of the two resistors is 10 Ω", [("resistors", 2, [(10.0, "Ω")])]),
        ("two resistors of 10 Ω each", [("resistors", 2, [(10.0, "Ω")])]),
        ("three identical resistors of 6 ohms", [("resistors", 3, [(6.0, "ohms")])]),
        ("two 500 mΩ resistors", [("resistors", 2, [(500.0, "mΩ")])]),
        ("two 5 kg blocks", [("blocks", 2, [(5.0, "kg")])]),
        ("two heaters each rated 2 kW", [("heaters", 2, [(2.0, "kW")])]),
        ("both capacitors are 5 µF", [("capacitors", 2, [])]),
        ("two resistors of 4 Ω and 6 Ω", [("resistors", 2, [])]),
        ("resistors of 10 Ω each", [("", None, [(10.0, "Ω")])]),
        ("Each resistor is 10 Ω. Two of them are in parallel.", [("of them", 2, [(10.0, "Ω")])]),
        # A rate is no item: "3 hours each day".
        ("a 100 W bulb is on for 3 hours each day for 2 days", []),
        # "each are connected across 12 V": 12 V is the supply's, not each lamp's.
        ("two lamps of 6 Ω each are connected across 12 V", [("lamps", 2, [(6.0, "Ω")])]),
        ("the 2 Ω and 3 Ω resistors", []),
        ("two 100 W electric bulbs", [("bulbs", 2, [(100.0, "W")])]),
        ("three 40 W tube lights", [("lights", 3, [(40.0, "W")])]),
        ("fifteen 40 W bulbs", [("bulbs", 15, [(40.0, "W")])]),
        ("a dozen 60 W bulbs", [("bulbs", 12, [(60.0, "W")])]),
        ("half a dozen 60 W bulbs", [("bulbs", 6, [(60.0, "W")])]),
        # A verb or a preposition is no part of the items' name.
        ("two 4 Ω in series", []),
    ],
)
def test_counted_items_reads_the_count_and_the_value_for_each(
    text: str, items: list[tuple[str, int | None, list[tuple[float, str]]]]
) -> None:
    read = [
        (item.noun, item.count, [(given.value, given.unit) for given in item.each])
        for item in counted_items(text)
    ]
    assert read == items
