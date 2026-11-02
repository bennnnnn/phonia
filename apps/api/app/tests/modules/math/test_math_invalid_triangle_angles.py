"""Invalid angle triples must never fall back to a default triangle."""

import pytest

from app.core.config import Settings
from app.modules.math.match.geometry import triangle_angles_signal
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "angles",
    [
        "60,60,70",
        "0,90,90",
        "-30,60,150",
        "30,,60,90",
        "30, ,60,90",
        "30..60,90",
        "30/60,90",
        "0,30,60,90",
        "30,60,90,20",
        "180,0,0",
    ],
)
async def test_invalid_explicit_angles_do_not_certify_a_default_drawing(angles: str):
    query = f"Draw a triangle with angles {angles}"
    assert triangle_angles_signal(query) is None
    assert extract_math_intent(query) is None
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "angles",
    [
        "30,60,90",
        "120,40,20",
        "60,60,60",
        "30, 60 and 90",
        "30°, 60°, 90°",
        "A=30, B=60, C=90",
        "A=30; B=60; C=90",
    ],
)
@pytest.mark.parametrize(
    "prefix", ["Draw a triangle with angles", "Find the angles of a triangle with angles"]
)
async def test_valid_angle_drawings_and_questions_remain_verified(prefix: str, angles: str):
    query = f"{prefix} {angles}"
    intent = extract_math_intent(query)
    assert intent is not None and intent.kind == "triangle_sides"
    assert intent.triangle_relative_lengths is True
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_fence["relative_lengths"] is True


def test_generic_draw_and_base_height_examples_keep_existing_behavior():
    for query in ["Draw a triangle", "Draw a triangle and label its angles"]:
        intent = extract_math_intent(query)
        assert intent is not None and intent.kind == "triangle"
    intent = extract_math_intent("Find the area of a triangle base 3 height 4")
    assert intent is not None and intent.kind == "triangle"


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", ["area", "perimeter", "area and perimeter"])
async def test_angle_only_measurements_are_undetermined_not_relative_numeric_answers(quantity):
    query = f"Find {quantity} of triangle with angles 30,60,90"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_answer is None
    assert verified.canonical_fence["relative_lengths"] is True
    assert verified.canonical_fence["area"] is None
    assert verified.canonical_fence["perimeter"] is None
    assert "physical lengths, area and perimeter are undetermined" in verified.text
