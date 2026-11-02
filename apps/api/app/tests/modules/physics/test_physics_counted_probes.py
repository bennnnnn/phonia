"""Counted items: one value stated for several items is that value in each.

Every probe of the review of PR #2172 (2026-10-31), through the real subject path
(build_subject_augmentation, no model call), with the card it must give or None for a
decline. A count whose items a solve reads once ("two 5 kg blocks" weighed as one) declines; a resistor network repeats the value ("two 500 mΩ resistors" in series are 1 Ω).
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.subjects.dispatch import build_subject_augmentation

PROBES: list[tuple[str, str | None]] = [
    (
        "Two resistors, each with a resistance of 10 Ω, are connected in parallel across 5 V. What is the total current?",
        "1 A",
    ),
    (
        "Two 10 Ω resistors are connected in series with a 5 Ω resistor across 25 V. Find the current.",
        None,
    ),
    (
        "Two 10 Ω resistors are connected in series with a 5 Ω resistor. Find the total resistance.",
        None,
    ),
    (
        "Two 10 Ω resistors in parallel are in series with a 5 Ω resistor. Find the total resistance.",
        "10 Ω",
    ),
    (
        "A 5 Ω resistor is in series with two 10 Ω resistors in parallel. Find the total resistance.",
        "10 Ω",
    ),
    (
        "A 5 Ω resistor is in series with two resistors in parallel, each 10 Ω. Find the total resistance.",
        "10 Ω",
    ),
    (
        "Two resistors, each 10 Ω, in parallel, are in series with a 5 Ω resistor across 10 V. Find the current.",
        "1 A",
    ),
    (
        "Three identical bulbs each rated 60 W are switched on for 2 hours. How much energy do they use?",
        None,
    ),
    (
        "Three identical bulbs each rated 60 W are connected to a 240 V supply. Find the total current.",
        None,
    ),
    (
        "Each of the resistors has 4 Ω. They are connected in parallel across 12 V. Find the total current.",
        None,
    ),
    (
        "Each of the resistors has a resistance of 4 Ω. They are connected in series. Find the total resistance.",
        None,
    ),
    ("A pair of 6 Ω resistors are connected in parallel. Find the equivalent resistance.", "3 Ω"),
    (
        "A pair of resistors, each 6 Ω, are connected in parallel across 6 V. Find the total current.",
        "2 A",
    ),
    (
        "Both resistors are 10 Ω and are connected in parallel across 5 V. Find the total current.",
        None,
    ),
    (
        "Both resistors have a resistance of 10 Ω. They are connected in series across 10 V. Find the current.",
        None,
    ),
    (
        "The two resistors are each 10 Ω and are connected in parallel across 5 V. Find the total current.",
        "1 A",
    ),
    ("Twelve 6 Ω resistors are connected in parallel. Find the equivalent resistance.", None),
    ("Five 2 Ω resistors are connected in series across 20 V. Find the current.", "2 A"),
    (
        "Six resistors of 12 Ω each are connected in parallel. Find the equivalent resistance.",
        "2 Ω",
    ),
    ("10 resistors of 10 Ω each are connected in parallel. Find the equivalent resistance.", None),
    (
        "2 resistors of 10 Ω each are connected in parallel across 5 V. Find the total current.",
        "1 A",
    ),
    (
        "3 identical 9 Ω resistors are connected in parallel across 6 V. Find the total current.",
        "2 A",
    ),
    (
        "Two resistors, one 10 Ω and one 20 Ω, are connected in series across 30 V. Find the current.",
        "1 A",
    ),
    ("Two resistors, 10 Ω and 20 Ω, are in parallel. Find the equivalent resistance.", "6.67 Ω"),
    (
        "Two resistors of 10 Ω and 20 Ω each are connected in parallel. Find the equivalent resistance.",
        None,
    ),
    (
        "Two resistors, R1 = 10 Ω and R2 = 20 Ω, each rated 2 W, are connected in series across 12 V. Find the current.",
        "0.4 A",
    ),
    (
        "Two resistors of 10 Ω each cost $3 and are connected in parallel across 5 V. Find the total current.",
        None,
    ),
    (
        "Each resistor is 10 Ω. Two of them are connected in parallel across 5 V. Find the total current.",
        "1 A",
    ),
    (
        "Two 10 Ω resistors and three 20 Ω resistors are connected in series. Find the total resistance.",
        None,
    ),
    (
        "Two 10 Ω resistors and three 20 Ω resistors are connected in series across 80 V. Find the current.",
        None,
    ),
    (
        "Two 10 Ω resistors and a 20 Ω resistor are connected in series. Find the total resistance.",
        None,
    ),
    (
        "Two resistors, each 10 Ω, and a 5 Ω resistor are connected in series across 25 V. Find the current.",
        None,
    ),
    (
        "Each of the three resistors in the circuit has a resistance of 6 Ω. Two are in parallel and the combination is in series with the third. Find the total resistance.",
        None,
    ),
    (
        "Three resistors, each 6 Ω: one is in series with the other two, which are in parallel. Find the total resistance.",
        None,
    ),
    (
        "Four 10 Ω resistors are connected so that two are in series and two are in parallel. Find the total resistance.",
        None,
    ),
    (
        "Two 10 Ω resistors are connected in parallel across 5 V. Find the current through each resistor.",
        None,
    ),
    ("Two 10 Ω resistors are connected in parallel across 5 V. Find the current.", "1 A"),
    ("Two capacitors, each 10 µF, are connected in series. Find the equivalent capacitance.", None),
    ("Two 10 µF capacitors are connected in parallel. Find the total capacitance.", None),
    (
        "Two capacitors of 10 µF each are connected in series across 12 V. Find the total charge.",
        None,
    ),
    ("Three 1.5 V cells are connected in series. What is the total emf?", None),
    ("Two 6 V batteries are connected in series to a 4 Ω resistor. Find the current.", None),
    (
        "A 12 V battery has two cells. A 6 Ω resistor is connected across it. Find the current.",
        "2 A",
    ),
    (
        "Two bulbs, each of resistance 6 Ω, are connected in parallel across a 12 V supply. Find the total current.",
        "4 A",
    ),
    ("Two 6 Ω lamps are connected in parallel across 12 V. Find the total current.", "4 A"),
    (
        "Two identical wires, each of resistance 4 Ω, are connected in parallel across 2 V. Find the total current.",
        "1 A",
    ),
    (
        "Two heaters, each of resistance 20 Ω, are connected in parallel to a 240 V supply. Find the total current.",
        "24 A",
    ),
    (
        "Two identical resistors are connected in parallel. The equivalent resistance is 5 Ω. What is the resistance of each?",
        None,
    ),
    (
        "Two resistors of 10 Ω are connected in parallel across 5 V. What is the total current?",
        None,
    ),
    (
        "Two 10 Ω resistors are connected in parallel across a 5 V battery. What is the power dissipated?",
        None,
    ),
    ("Two 100 W bulbs are used for 3 hours. Find the energy used in kWh.", None),
    (
        "A 100 W bulb is used for 3 hours each day. Find the energy used in 2 days.",
        "2.16 × 10⁶ J (0.6 kWh)",
    ),
    ("A 60 W bulb and two 40 W bulbs are on for 5 hours. Find the energy used.", None),
    ("Two 1.5 V cells in series are connected to a 3 Ω resistor. What is the current?", None),
    ("A 10 Ω resistor is connected across 5 V. What is the current?", "0.5 A"),
    ("Two resistors of 4 Ω and 6 Ω are connected in series across 10 V. Find the current.", "1 A"),
    ("Seven resistors of 3 Ω each are connected in series. Find the total resistance.", None),
    ("Eleven 11 Ω resistors are connected in parallel. Find the equivalent resistance.", None),
    ("two 4.7 kΩ resistors are connected in parallel. Find the equivalent resistance.", "2350 Ω"),
    ("Two resistors, each 2 kΩ, are connected in series across 8 V. Find the current.", "0.002 A"),
    (
        "Two 10 Ω resistors in parallel and a 20 Ω resistor in parallel with them across 10 V. Find the total current.",
        None,
    ),
    (
        "Two resistors in parallel have values 10 Ω each; a third resistor of 5 Ω is in series with them. Find the total resistance.",
        None,
    ),
    (
        "Two resistors of 2 kΩ each are connected in parallel. Find the equivalent resistance.",
        "1000 Ω",
    ),
    ("Three 1 kΩ resistors are connected in series. Find the total resistance.", "3000 Ω"),
    ("Two 1 MΩ resistors are connected in series. Find the total resistance.", "2 × 10⁶ Ω"),
    (
        "Two resistors of 2 kΩ each are connected in series across 8 V. Find the total current.",
        "0.002 A",
    ),
    ("Two 2 kΩ resistors are connected in series across 8 V. Find the current.", "0.002 A"),
    ("Two 500 mΩ resistors are connected in series. Find the total resistance.", "1 Ω"),
    (
        "Three resistors, each 3 kΩ, are connected in parallel. Find the equivalent resistance.",
        "1000 Ω",
    ),
    (
        "Both resistors are 10 Ω each and are connected in parallel across 5 V. Find the total current.",
        "1 A",
    ),
    (
        "Two resistors are connected in parallel across 6 V. Each has a resistance of 3 Ω. Find the total current.",
        "4 A",
    ),
    (
        "Two resistors are connected in parallel across 6 V. Each resistor is 3 Ω. Find the total current.",
        "4 A",
    ),
    ("There are two resistors in parallel across 6 V, each of 3 Ω. Find the total current.", "4 A"),
    ("Two resistors are joined in series. Each one is 5 Ω. Find the total resistance.", "10 Ω"),
    (
        "Two cells of emf 1.5 V each are connected in series to a 3 Ω resistor. Find the current.",
        None,
    ),
    (
        "Two identical cells, each of emf 1.5 V, are in series with a 3 Ω resistor. Find the current.",
        None,
    ),
    ("Two 1.5-volt cells in series drive a 3 Ω resistor. Find the current.", None),
    (
        "Two capacitors, each of capacitance 4 µF, are connected in parallel to 6 V. Find the total charge.",
        None,
    ),
    ("Two 2 µF capacitors in parallel are charged to 10 V. Find the energy stored.", None),
    ("Two bulbs rated 60 W each are switched on for 3 hours. Find the energy used.", None),
    ("Two lamps each have a power of 60 W and are on for 3 h. Find the total energy.", None),
    ("Two heaters each rated 2 kW are used for 3 hours. Find the energy used.", None),
    ("Two kettles, each 2 kW, run for 30 minutes. How much energy do they use?", None),
    ("Three motors each rated 500 W run for 2 hours. Find the energy used.", None),
    (
        "Two springs, each of stiffness 100 N/m, are connected in parallel. Find the effective spring constant.",
        None,
    ),
    (
        "Two identical springs of spring constant 200 N/m are connected in series. Find the effective spring constant.",
        None,
    ),
    ("Two charges of 3 µC each are placed 0.5 m apart. Find the force between them.", "0.324 N"),
    (
        "Two masses of 2 kg each are placed 1 m apart. Find the gravitational force between them.",
        "2.67 × 10⁻¹⁰ N",
    ),
    (
        "Two boxes, each of mass 10 kg, are pushed together with a force of 40 N. Find the acceleration.",
        None,
    ),
    ("Two 5 kg blocks are stacked on a table. Find their total weight.", None),
    (
        "Two bulbs, each of resistance 6 Ω, are connected in series across 12 V. Find the current.",
        "1 A",
    ),
    (
        "Two identical lamps of resistance 6 Ω each are connected in parallel across 12 V. Find the total current.",
        "4 A",
    ),
    (
        "Two coils, each of resistance 8 Ω, are connected in parallel across 4 V. Find the total current.",
        "1 A",
    ),
    (
        "Each of the two bulbs has a resistance of 6 Ω. They are connected in parallel across 12 V. Find the total current.",
        "4 A",
    ),
    (
        "Two 10 Ω resistors are connected in parallel and the pair is placed across a 5 V supply. Find the current.",
        "1 A",
    ),
    (
        "Two resistors, each with a resistance of 10 Ω, are connected in parallel across 5 V. What is the total resistance?",
        "5 Ω",
    ),
    (
        "Two resistors with a resistance of 10 Ω are connected in parallel across 5 V. What is the total current?",
        None,
    ),
    ("the two 10 Ω resistors are in parallel across 5 V. Find the total current.", "1 A"),
    (
        "One of the two resistors is 10 Ω and the other is 20 Ω; they are in series across 30 V. Find the current.",
        "1 A",
    ),
    ("A 10 Ω resistor and two others are in series across 30 V. Find the current.", None),
    ("Two resistors are connected in series across 30 V. One is 10 Ω. Find the current.", None),
    (
        "Two of the three resistors are 10 Ω and they are connected in parallel across 5 V. Find the total current.",
        None,
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("text", "answer"), PROBES, ids=[text[:60] for text, _ in PROBES])
async def test_a_counted_item_is_read_once_per_item(
    thread_sympy_executor: None, text: str, answer: str | None
) -> None:
    settings = Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)
    verified = (await build_subject_augmentation(text, settings)).verified
    assert getattr(verified, "canonical_answer", None) == answer
