"""One resistor in series with a parallel group: read, solved and drawn as stated."""

from __future__ import annotations

import pytest

from app.modules.physics import extract_physics_intent
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solver import solve_physics


@pytest.mark.parametrize(
    ("text", "op", "value"),
    [
        (
            "a 4 Ω resistor is in series with a parallel pair of 6 Ω and 12 Ω. "
            "what's the total resistance",
            "series_parallel_resistance",
            8.0,
        ),
        (
            "a 2 Ω resistor in series with two 4 Ω resistors in parallel. total resistance?",
            "series_parallel_resistance",
            4.0,
        ),
        (
            "6 Ω and 3 Ω are in parallel, and that combination is in series with 5 Ω. "
            "total resistance",
            "series_parallel_resistance",
            7.0,
        ),
        (
            "A 4 ohm resistor is in series with a parallel pair of 6 ohm and 3 ohm resistors "
            "across a 12 V battery. Find the current.",
            "series_parallel_current",
            2.0,
        ),
    ],
)
def test_series_parallel_network_is_read_and_solved(text: str, op: str, value: float) -> None:
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent) and intent.physics_op == op
    assert solve_physics(intent).quantities[0].value == pytest.approx(value)


@pytest.mark.parametrize(
    "text",
    [
        # (4 + 6) ∥ 12, not 4 + (6 ∥ 12).
        "A 4 Ω resistor is in series with a 6 Ω resistor, and a 12 Ω resistor is in "
        "parallel with both. Find the total resistance.",
        "A 4 Ω resistor in series with a 6 Ω resistor, both in parallel with a 12 Ω "
        "resistor. Total resistance?",
        "Two resistors, 4 Ω and 6 Ω, are in series with each other and connected in "
        "parallel to 12 Ω. Total resistance?",
        "A 4 Ω and a 6 Ω resistor are in series, and that pair is in parallel with a "
        "12 Ω resistor. Total resistance?",
        # Two in series with the group: not the one-resistor shape.
        "6 Ω and 12 Ω in parallel are in series with 4 Ω and 2 Ω. Find the total resistance.",
        # The current with no supply voltage.
        "A 4 Ω resistor is in series with a parallel pair of 6 Ω and 3 Ω. Find the current.",
    ],
)
def test_another_network_shape_is_declined(text: str) -> None:
    assert extract_physics_intent(text) is None


def test_the_schematic_nests_the_group_inside_the_series_wire() -> None:
    intent = extract_physics_intent(
        "A 4 ohm resistor is in series with a parallel pair of 6 ohm and 3 ohm resistors "
        "across a 12 V battery. Find the current."
    )
    assert intent is not None
    (scene,) = solve_physics(intent).simulation_specs
    circuit = scene.circuit
    assert circuit is not None and circuit.load.series is not None
    single, group = circuit.load.series
    assert single.label == "R₁ = 4 Ω"
    assert group.parallel is not None
    assert [part.label for part in group.parallel] == ["R₂ = 6 Ω", "R₃ = 3 Ω"]
    assert group.label == "2 Ω" and circuit.load.label == "R = 6 Ω"
    assert circuit.source.label == "12 V" and circuit.current == "I = 2 A"
