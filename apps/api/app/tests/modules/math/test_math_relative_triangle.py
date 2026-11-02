import copy

import pytest

from app.core.config import Settings
from app.modules.math.fence import validate_math_fences
from app.modules.math.match.literal_geometry import literal_triangle_angles_draw
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.direct_geometry import can_direct_triangle_angles
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.asyncio
@pytest.mark.parametrize("angles", ["30,60,90", "120,40,20", "60,60,60"])
async def test_angles_only_draw_uses_relative_diagram_without_area(angles):
    query = f"Draw a triangle with angles {angles}"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None
    spec = verified.canonical_fence
    assert spec is not None and spec["relative_lengths"] is True
    assert spec["area"] is None and spec["perimeter"] is None
    assert "area" not in spec["labels"]
    assert verified.canonical_answer is None
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None and reply.startswith("```geometry\n")
    assert "```answer" not in reply and "verified math" not in reply
    finalized = validate_math_fences(reply, verified=verified)
    assert "```answer" not in finalized
    assert finalized.count("```geometry") == 1
    assert maybe_direct_math_reply(verified, query, has_image_attachment=True) is None
    for suffix in [" and explain why", " and find its area", " and draw a circle", " with side 5"]:
        assert maybe_direct_math_reply(verified, query + suffix) is None
    changed = copy.deepcopy(spec)
    changed["relative_lengths"] = False
    assert not can_direct_triangle_angles(query, [changed])
    changed["relative_lengths"] = True
    changed["c"] = 99
    assert not can_direct_triangle_angles(query, [changed])


@pytest.mark.asyncio
async def test_unitless_sss_measurements_keep_determined_area():
    query = "Find the area of a triangle with sides 3,4,5"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_answer == "6"
    assert verified.canonical_fence["relative_lengths"] is False
    assert verified.canonical_fence["area"] == 6


@pytest.mark.asyncio
async def test_non_draw_angle_question_retains_its_canonical_answer():
    query = "Find the angles of a triangle with angles 30,60,90"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_answer == "30°, 60°, 90°"
    assert verified.canonical_fence["relative_lengths"] is True
    assert literal_triangle_angles_draw(query) is None
    assert maybe_direct_math_reply(verified, query) is None


@pytest.mark.parametrize(
    "query",
    [
        "Draw a triangle with angles 30,60,90 and find its area",
        "Draw a triangle with angles 30,60,90 and explain why",
        "Draw a triangle with angles 30,60,90 with side 5",
        "Draw a triangle with angles 30,60,90,20",
        "Draw a triangle with angles 30,,60,90",
        "Draw a triangle with angles -30,60,150",
        "Draw a triangle with angles 0,90,90",
        "Draw a triangle with angles 60,60,70",
        "Draw a triangle with angles 90,90,90",
    ],
)
def test_whole_draw_grammar_rejects_extra_clauses_and_invalid_angles(query):
    assert literal_triangle_angles_draw(query) is None
