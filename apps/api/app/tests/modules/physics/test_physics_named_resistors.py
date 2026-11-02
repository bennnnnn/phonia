"""Resistors named in the question ("R1 = 10 Ω") read like the same question without names."""

from __future__ import annotations

import pytest

from app.modules.physics import extract_physics_intent
from app.modules.physics.extractors.circuit_patterns import without_resistor_names


@pytest.mark.parametrize(
    ("text", "op", "params"),
    [
        (
            "R1 = 10 ohm is in series with R2 = 20 ohm across a 12 V battery, find the current",
            "series_current",
            {"R1": 10.0, "R2": 20.0, "V": 12.0},
        ),
        (
            "R1 = 10 ohm and R2 = 20 ohm are in series across a 12 V battery. Find the current.",
            "series_current",
            {"R1": 10.0, "R2": 20.0, "V": 12.0},
        ),
        (
            "R1=10Ω, R2=20Ω in parallel. Find the total resistance.",
            "parallel_resistance",
            {"R1": 10.0, "R2": 20.0},
        ),
        (
            "R_1 = 5 Ω and R_2 = 5 Ω are in parallel. What is the equivalent resistance?",
            "parallel_resistance",
            {"R1": 5.0, "R2": 5.0},
        ),
        (
            # The label's digit is not a value: three resistors, not six.
            "R1 = 10, R2 = 20 and R3 = 30 ohms are in series. Find the total resistance.",
            "series_resistance",
            {"R1": 10.0, "R2": 20.0, "R3": 30.0},
        ),
        (
            "R1 = 4 Ω is in series with a parallel pair of R2 = 6 Ω and R3 = 3 Ω. "
            "A 12 V battery drives the circuit. Find the current.",
            "series_parallel_current",
            {"R1": 4.0, "R2": 6.0, "R3": 3.0, "V": 12.0},
        ),
        (
            "R1 = 10 ohm is in series with a parallel combination of R2 = 20 ohm and "
            "R3 = 20 ohm. Find the equivalent resistance",
            "series_parallel_resistance",
            {"R1": 10.0, "R2": 20.0, "R3": 20.0},
        ),
    ],
)
def test_named_resistors_read_as_the_network(text: str, op: str, params: dict[str, float]) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == op
    assert intent.physics_params == params


@pytest.mark.parametrize(
    "text",
    [
        # Wired by name: which resistors are in the network is the reading.
        "R1 = 10 Ω, R2 = 20 Ω and R3 = 30 Ω. R1 and R2 are in series. Find the total resistance.",
        # A branch current asked by name, not the total.
        "R1 = 10 Ω and R2 = 20 Ω are in parallel across 12 V. Find the current through R2.",
        # One name for two resistors.
        "R1 = 10 Ω and R1 = 20 Ω are in series. Find the total resistance.",
        "R1 = 10 is my router's setting, is that normal?",
    ],
)
def test_a_network_wired_by_name_is_declined(text: str) -> None:
    assert extract_physics_intent(text) is None


@pytest.mark.parametrize(
    ("text", "unnamed"),
    [
        ("R1 = 10 Ω and R2 = 20 Ω", "10 Ω and 20 Ω"),
        ("R_{1}=5Ω", "5Ω"),
        ("a 10 Ω resistor", "a 10 Ω resistor"),
        ("R1 = 10 Ω and R2 = 20 Ω; the current through R2?", None),
        ("R1 = 10 Ω and R1 = 20 Ω", None),
    ],
)
def test_without_resistor_names(text: str, unnamed: str | None) -> None:
    assert without_resistor_names(text) == unnamed
