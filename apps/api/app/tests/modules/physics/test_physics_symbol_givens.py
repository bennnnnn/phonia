"""Worksheet symbol givens ("F = 20 N, m = 5 kg, find a") are physics."""

from __future__ import annotations

import pytest

from app.modules.physics import extract_physics_intent, is_symbol_givens_request, needs_physics
from app.modules.physics.symbol_givens import symbol_givens_requests
from app.services.subjects.dispatch import detect_subject


@pytest.mark.parametrize(
    ("text", "operation"),
    [
        ("F = 20 N, m = 5 kg, find a", "net_force"),
        ("m = 5 kg, F = 20 N. Find a.", "net_force"),
        ("F=20N, m=5kg. Find a.", "net_force"),
        ("v = 20 m/s, t = 4 s, find d", "rate_distance"),
        ("u = 0, a = 2 m/s^2, t = 5 s, find v", "suvat_velocity"),
        ("V = 12 V, R = 4 ohm, find I", "current"),
        ("Given: m = 2 kg, v = 3 m/s. Find KE", "kinetic_energy"),
    ],
)
def test_symbol_givens_bind_the_law_they_state(text: str, operation: str) -> None:
    assert needs_physics(text)
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == operation
    assert detect_subject(text) == "physics"


def test_symbol_givens_name_each_quantity_by_its_unit() -> None:
    assert symbol_givens_requests("P = 200 W, t = 10 s, find E") == [
        "Given a power of 200 W and a time of 10 s, find the energy."
    ]
    # ``P`` in kilopascals is a pressure, not a power.
    assert symbol_givens_requests("P = 101 kPa, A = 2 m^2, find F") == [
        "Given a pressure of 101 kPa and an area of 2 m^2, find the force."
    ]


def test_unbound_symbol_givens_stay_physics_not_algebra() -> None:
    """No catalog law gives work from power, but W and s are not unknowns."""
    text = "P = 200 W, t = 10 s, find W"
    assert is_symbol_givens_request(text)
    assert detect_subject(text) == "physics"


@pytest.mark.parametrize(
    "text",
    [
        "x = 5, y = 3, find x",
        "a = 3, b = 4, find c",
        "F = 20, m = 5, find a",
        "F = 20 N, m = 5 kg, find a and explain why",
        "F = 20 N, m = 5 kg, find a, then graph it",
        "F = 20 N, F = 30 N, find a",
        "P = 200 kg, t = 10 s, find E",
    ],
)
def test_lines_that_are_not_closed_symbol_givens_are_left_alone(text: str) -> None:
    assert not is_symbol_givens_request(text)
