"""Natural-language geometry has no implicit centimetre scale."""

import pytest

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import RectangleGeometryInput, TriangleGeometryInput
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,kind",
    [
        ("Find the area of a rectangle 3 by 4", "rectangle"),
        ("Find the area of a square side 3", "square"),
        ("Find the area of a triangle base 3 height 4", "triangle"),
        ("Find the area of a right triangle legs 3 and 4", "right_triangle"),
        ("Find the area of a triangle with sides 3,4,5", "triangle_sides"),
        ("Draw a triangle with angles 30,60,90", "triangle_sides"),
        ("Find the area of a trapezoid top 4 bottom 8 height 5", "trapezoid"),
        ("Find the area of a parallelogram base 8 height 4 side 5", "parallelogram"),
        ("Find the area of a circle radius 3", "circle"),
        ("Find the area of a circle sector radius 4 angle 90 degrees", "sector"),
    ],
)
async def test_geometry_without_length_units_uses_generic_units(query: str, kind: str) -> None:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    fence = verified.canonical_fence
    assert fence["type"] == kind
    assert fence["unit"] == "units"
    if query == "Find the area of a triangle with sides 3,4,5":
        assert verified.canonical_answer == "6"
    assert " cm" not in verified.text
    assert all("cm" not in label for label in fence["labels"].values())


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["cm", "m", "feet", "in"])
@pytest.mark.parametrize(
    "query",
    [
        "Find the area of a rectangle 3 {unit} by 4 {unit}",
        "Find the area of a rectangle 3 by 4 {unit}",
        "Find the area of a square side 3 {unit}",
        "Find the area of a triangle base 3 {unit} height 4 {unit}",
        "Find the area of a circle radius 3 {unit}",
        "Find the area of a circle sector radius 4 {unit} angle 90 degrees",
    ],
)
async def test_geometry_preserves_printed_common_length_unit(query: str, unit: str) -> None:
    _, verified = await build_math_augmentation(
        query.format(unit=unit), Settings(math_tools_enabled=True)
    )
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_fence["unit"] == ("ft" if unit == "feet" else unit)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Find the area of a rectangle 3 m by 4 cm",
        "Find the area of a triangle base 3 m height 4 cm",
        "Find the area of a rectangle 3 by 4 parsecs",
        "Find the area of a triangle base 3 m/s height 4 m/s",
        "Find the area of a circle radius 3 in the plane",
        "Find the area of a rectangle 3 by 4 in meters",
        "Find the area of a rectangle 3 by 4 in units of meters",
        "Find the area of a rectangle 3 by 4 cm2",
        "Find the area of a rectangle 3 by 4 cm / s",
        "Find the area of a rectangle 3 by 4 cm ^ 2",
        "Find the area of a rectangle 3 by 4 cm²",
    ],
)
async def test_geometry_does_not_certify_mixed_or_unsupported_length_scales(query: str) -> None:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is None


def test_public_structured_geometry_schema_keeps_legacy_default_unit() -> None:
    assert math_solve.rectangle_geometry(RectangleGeometryInput(width=3, height=4)).unit == "cm"
    assert math_solve.triangle_geometry(TriangleGeometryInput(base=3, height=4)).unit == "cm"


@pytest.mark.asyncio
async def test_base_height_triangle_does_not_claim_unknown_angles_or_equal_legs() -> None:
    _, verified = await build_math_augmentation(
        "Find the area of a triangle base 3 height 4", Settings(math_tools_enabled=True)
    )
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_answer == "6"
    assert verified.canonical_fence["show_altitude"] is True
    assert verified.canonical_fence["show_angle"] is False
    assert verified.canonical_fence["show_ticks"] is False
