"""A rectangle's diagonal angle must not be certified as its diagonal length."""

import pytest

from app.core.config import Settings
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,angle,diagonal",
    [
        (
            "Find the angle made by the diagonal with the base of a rectangle 3 by 4",
            53.13,
            5,
        ),
        (
            "Find the angle made by the diagonal with the base of a rectangle 4 by 3",
            36.87,
            5,
        ),
        ("rectangle 8 x 5 cm diagonal angle", 32.01, 9.434),
    ],
)
async def test_diagonal_angle_uses_degree_answer_and_retains_geometry(query, angle, diagonal):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_answer == rf"{angle:g}^\circ"
    fence = verified.canonical_fence
    assert fence["type"] == "rectangle"
    assert fence["show_diagonal"] is True and fence["show_angle"] is True
    assert fence["angle_deg"] == angle
    assert fence["diagonal"] == diagonal
    assert maybe_direct_math_reply(verified, query) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,answer",
    [
        ("Find the diagonal of a rectangle 3 by 4", "5"),
        ("Find the area of a rectangle 3 by 4", "12"),
        ("Find the perimeter of a rectangle 3 by 4", "14"),
    ],
)
async def test_other_rectangle_measurements_keep_their_existing_answers(query, answer):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_answer == answer
    assert verified.canonical_fence["show_angle"] is False
