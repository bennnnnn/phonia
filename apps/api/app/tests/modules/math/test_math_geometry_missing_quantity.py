"""Dimensions describe a shape; they do not choose a measurement to solve."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.fence import validate_math_fences
from app.modules.math.tools import _build_verified_block, extract_math_intent
from app.modules.math.tools.direct import maybe_direct_math_reply

_SETTINGS = Settings(math_tools_enabled=True)


@pytest.mark.parametrize(
    "query,kind,choice",
    [
        ("a rectangle 4 by 5", "rectangle", "area, perimeter, or diagonal"),
        ("a square with side 4", "square", "area, perimeter, or diagonal"),
        ("a triangle base 3 height 4", "triangle", "area"),
        ("a right triangle with legs 3 and 4", "right_triangle", "hypotenuse"),
        ("a triangle with sides 3, 4, 5", "triangle_sides", "area, perimeter, or angles"),
        ("a circle radius 3", "circle", "area, circumference, or diameter"),
        ("a circle diameter 6", "circle", "area, circumference, or diameter"),
        (
            "a parallelogram base 5 height 3 side 4",
            "parallelogram",
            "area or perimeter",
        ),
        ("a trapezoid top 3 bottom 5 height 4", "trapezoid", "area"),
        ("a sector radius 3 angle 60 degrees", "sector", "area or arc length"),
        ("a cube side 3", "solid", "volume or surface area"),
        ("a sphere radius 2", "solid", "volume or surface area"),
    ],
)
def test_dimensions_without_requested_quantity_ask_one_clarification(
    query: str, kind: str, choice: str
) -> None:
    intent = extract_math_intent(query)
    assert intent is not None and intent.kind == kind
    verified = _build_verified_block(intent, _SETTINGS)
    assert verified is not None
    assert verified.canonical_answer is None

    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    assert "not what to calculate" in reply
    assert choice in reply
    assert "```answer" not in reply
    assert validate_math_fences(reply, verified=verified) == reply.rstrip()


def test_explicit_draw_is_a_diagram_without_an_invented_measurement() -> None:
    query = "Draw a square with side 4"
    intent = extract_math_intent(query)
    assert intent is not None and intent.kind == "square"
    verified = _build_verified_block(intent, _SETTINGS)
    assert verified is not None and verified.canonical_answer is None

    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    assert reply.startswith("```geometry\n")
    assert "```answer" not in reply
    assert '"side":4.0' in reply


@pytest.mark.parametrize(
    "query,answer",
    [
        ("Find the area of a square side 4", "16"),
        ("Find the area of a triangle base 3 height 4", "6"),
        ("Find the area of a trapezoid top 3 bottom 5 height 4", "16"),
        ("Find the area of a parallelogram base 5 height 3 side 4", "15"),
        ("Find the arc length of a sector radius 3 angle 60 degrees", "3.14"),
        ("Find the volume of a cube side 3", r"27\ \mathrm{units}^{3}"),
    ],
)
def test_explicit_quantity_still_returns_the_requested_measure(query: str, answer: str) -> None:
    intent = extract_math_intent(query)
    assert intent is not None
    verified = _build_verified_block(intent, _SETTINGS)
    assert verified is not None and verified.canonical_answer == answer
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None and "```answer" in reply


@pytest.mark.parametrize(
    "query",
    [
        "What is a square with side 4?",
        "a square with side 4 and tell me a joke",
        "a square with side 4 + 2",
    ],
)
def test_definition_mixed_and_transformed_requests_keep_the_language_path(query: str) -> None:
    intent = extract_math_intent(query)
    if intent is None:
        return
    verified = _build_verified_block(intent, _SETTINGS)
    assert verified is not None
    assert maybe_direct_math_reply(verified, query) is None


@pytest.mark.parametrize(
    "query",
    [
        "Draw a square and a circle",
        "Draw a square with side 4 and side 5",
        "a square with side 4 and a circle radius 2",
    ],
)
def test_multiple_shapes_or_conflicting_dimensions_keep_the_language_path(query: str) -> None:
    intent = extract_math_intent(query)
    assert intent is not None
    verified = _build_verified_block(intent, _SETTINGS)
    assert verified is not None
    assert maybe_direct_math_reply(verified, query) is None
