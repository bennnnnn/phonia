"""Original walkthrough wording must reach the matching verified operation."""

import pytest

from app.core.config import Settings
from app.modules.math import tools as math_tools
from app.modules.physics.extractors.forces import _extract_force_intent


@pytest.mark.parametrize(
    "prompt,kind,answer",
    [
        ("Find the area of a square side 3", "square", "9"),
        ("Find the perimeter of a square side 3", "square", "12"),
        ("Find the diagonal of a square side 3", "square", "4.2426"),
        ("Find the critical points of x^3-3x", "calculus", "-1, 1"),
        ("Find the diameter of a circle radius 3", "circle", "6"),
        ("Find the area of a circle diameter 6", "circle", "28.27"),
        ("Find the circumference of a circle diameter 6", "circle", "18.85"),
        (
            "Find the angles of a triangle with sides 3,4,5",
            "triangle_sides",
            r"\approx 36.9°, \approx 53.1°, 90°",
        ),
        ("Find the area of a triangle with sides 3,4,5", "triangle_sides", "6"),
        ("Find the perimeter of a triangle with sides 3,4,5", "triangle_sides", "12"),
        ("Convert 0 C to F", "unit", r"32\ \mathrm{°F}"),
        ("Convert -40 C to F", "unit", r"-40\ \mathrm{°F}"),
        ("Convert 0 C to K", "unit", r"273.15\ \mathrm{K}"),
        ("Convert 32 F to C", "unit", r"0\ \mathrm{°C}"),
        ("Convert -2 m to cm", "unit", r"-200\ \mathrm{cm}"),
    ],
)
def test_walkthrough_operation_is_gated_and_answers_requested_quantity(
    prompt: str, kind: str, answer: str
) -> None:
    assert math_tools.needs_symbolic_math(prompt)
    intent = math_tools.extract_math_intent(prompt)
    assert intent is not None and intent.kind == kind
    block = math_tools._build_verified_block(intent, Settings())
    assert block is not None and block.canonical_answer == answer


@pytest.mark.parametrize(
    "prompt",
    [
        "What is a square?",
        "A perfect square has 4 factors",
        "Our office is on the west side of the town square",
        "Find the critical points of the discussion",
        "The team reached a critical point after 3 meetings",
        "What is average speed?",
        "average speed 100 m in 0 s",
        "average speed 100 m in -20 s",
        "average speed 100 m in 20 s then 50 m",
    ],
)
def test_new_gates_require_supported_numeric_inputs(prompt: str) -> None:
    assert not math_tools.needs_symbolic_math(prompt)


@pytest.mark.parametrize(
    "prompt",
    [
        "Find the force on a 5 kg object.",
        "Find the mass of an object with force 20 N.",
        "Find the force on a 5 kg object with speed 2 m/s.",
        "Find the force on a 5 kg object with acceleration 2 m/s^3.",
    ],
)
def test_new_force_wording_does_not_invent_missing_or_incompatible_measurements(
    prompt: str,
) -> None:
    assert _extract_force_intent(prompt) is None


def test_missing_conversion_destination_does_not_raise() -> None:
    assert math_tools.extract_math_intent("Convert 0 C to ") is None
