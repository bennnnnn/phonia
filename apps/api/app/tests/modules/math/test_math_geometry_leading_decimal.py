"""Leading decimal points must survive the shared geometry number scan."""

import pytest

from app.core.config import Settings
from app.modules.math import match as mtm
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.parametrize(
    "text,expected",
    [
        ("radius .5", 0.5),
        ("radius -.5", -0.5),
        ("radius +.5", 0.5),
        ("radius 0.5", 0.5),
        ("radius -0.5", -0.5),
        ("radius 5", 5.0),
        ("radius 5.25", 5.25),
        ("radius=.5 cm", 0.5),
        ("radius is .5 m", 0.5),
        ("radius .05", 0.05),
    ],
)
def test_number_after_preserves_decimal_value_and_sign(text: str, expected: float) -> None:
    assert mtm.number_after(text, "radius") == expected


def test_shared_multi_number_scan_preserves_leading_decimals() -> None:
    assert mtm.two_numbers_after("legs .3 and .4", "legs") == (0.3, 0.4)
    assert mtm.two_numbers_after("values -.3 and .4", "values") == (-0.3, 0.4)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,kind,answer,fields",
    [
        (
            "Find the area of a circle sector radius .5 m angle 180°",
            "sector",
            "0.3927",
            {"radius": 0.5, "angle_deg": 180.0},
        ),
        (
            "Find the arc length of a circle sector radius .5 m angle 180 degrees",
            "sector",
            "1.57",
            {"radius": 0.5, "angle_deg": 180.0},
        ),
        (
            "Find the area of a circle radius .5 m",
            "circle",
            "0.79",
            {"radius": 0.5},
        ),
        (
            "Find the area of a circle diameter .5 m",
            "circle",
            "0.2",
            {"radius": 0.25, "diameter": 0.5},
        ),
        (
            "Find the area of a square side .5 m",
            "square",
            "0.25",
            {"side": 0.5},
        ),
        (
            "Find the area of a triangle base .3 m height .4 m",
            "triangle",
            "0.06",
            {"base": 0.3, "height": 0.4},
        ),
        (
            "Find the area of a parallelogram base .8 m height .4 m side .5 m",
            "parallelogram",
            "0.32",
            {"base": 0.8, "height": 0.4, "side": 0.5},
        ),
        (
            "Find the area of a trapezoid top .4 m bottom .8 m height .5 m",
            "trapezoid",
            "0.3",
            {"top": 0.4, "bottom": 0.8, "height": 0.5},
        ),
        (
            "Find the perimeter of a triangle with sides .3 m, .4 m, .5 m",
            "triangle_sides",
            "1.2",
            {"a": 0.3, "b": 0.4, "c": 0.5},
        ),
    ],
)
async def test_geometry_augmentation_certifies_original_decimal_dimensions(
    query: str, kind: str, answer: str, fields: dict[str, float]
) -> None:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == kind
    assert verified.canonical_fence["unit"] == "m"
    assert verified.canonical_answer == answer
    for field, value in fields.items():
        assert verified.canonical_fence[field] == value


@pytest.mark.parametrize(
    "query",
    [
        "Find the area of a circle sector radius -.5 angle 90",
        "Find the area of a circle radius -.5",
        "Find the area of a square side -.5",
        "Find the area of a parallelogram base -.8 height .4 side .5",
    ],
)
def test_negative_decimal_dimension_cannot_become_positive_verified_geometry(query: str) -> None:
    # Read with its sign or not read at all: never a positive verified measure.
    intent = extract_math_intent(query)
    assert (
        intent is None or _build_verified_block(intent, Settings(math_tools_enabled=True)) is None
    )
