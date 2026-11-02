"""Closed measurement requests emit their existing answer and geometry immediately."""

import json
from collections.abc import AsyncGenerator
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.stream_pipeline import stream_and_finalize
from app.modules.chat.turn_prep.context import StreamContext
from app.modules.math.fence import validate_math_fences
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.answer_fence import mark_server_answer_fences
from app.services.solving import VerifiedMathBlock
from app.services.workout import as_formula_heading

_CASES = [
    ("Find the area of a parallelogram base 8 height 4 side 5", "parallelogram", "32"),
    ("Find the perimeter of a parallelogram base 8 height 4 side 5", "parallelogram", "26"),
    ("Find the area of a trapezoid top 4 bottom 8 height 5", "trapezoid", "30"),
    ("Find the area of a circle radius 3", "circle", "28.27"),
    ("Find the circumference of a circle radius 3", "circle", "18.85"),
    ("Find the diameter of a circle radius 3", "circle", "6"),
    ("Find the area of a circle sector radius 4 angle 90", "sector", "12.5664"),
    ("Find the arc length of a circle sector radius 4 angle 90", "sector", "6.28"),
    ("Please calculate the area of the circle with diameter 6 cm.", "circle", "28.27"),
    ("What is the circumference of a circle with diameter 6 m?", "circle", "18.85"),
    (
        "Find the area of a trapezium with top 4 cm and bottom 8 cm and height 5 cm",
        "trapezoid",
        "30",
    ),
    (
        "Find the area of a trapezoid with bases 3 cm and 5 cm and height 4 cm",
        "trapezoid",
        "16",
    ),
    (
        "Find the area of a parallelogram with base 8 m and height 4 m and side 5 m",
        "parallelogram",
        "32",
    ),
    ("Find the arc length of a sector with radius 4 cm and angle 90 degrees", "sector", "6.28"),
    ("Find the area of a circle sector radius 0.5 m angle 180°", "sector", "0.3927"),
]


def _verified(query: str) -> VerifiedMathBlock:
    intent = extract_math_intent(query)
    assert intent is not None
    result = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert result is not None and result.canonical_fence is not None
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("query,kind,answer", _CASES)
async def test_complete_shape_measurement_emits_without_model(
    query: str, kind: str, answer: str
) -> None:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_answer == answer
    assert verified.canonical_fence["type"] == kind
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None and reply.endswith("```\n")
    assert reply.count("```answer") == 1 and reply.count("```geometry") == 1
    assert (
        "**Given**" in reply
        and "**Formula**" in as_formula_heading(reply)
        and "**Substitution**" in reply
    )
    assert "```geometry" in reply
    finalized = validate_math_fences(reply, verified=verified)
    assert (
        json.loads(finalized.split("```geometry\n", 1)[1].split("\n```", 1)[0])
        == verified.canonical_fence
    )
    assert [part.strip() for part in finalized.split("```") if part.strip()] == [
        part.strip() for part in mark_server_answer_fences(reply).split("```") if part.strip()
    ]
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="smart-chat",
        prompt_messages=[],
        run_title=False,
        user_message_content=query,
        reserved_tokens=100,
        max_output_tokens=1000,
        instant_reply=reply,
        verified_subject=verified,
    )
    with (
        patch("app.modules.chat.stream_pipeline.run_tool_loop_path", AsyncMock()) as tools,
        patch("app.modules.chat.stream_pipeline.run_llm_token_stream") as llm,
    ):
        stream = stream_and_finalize(MagicMock(), MagicMock(), Settings(), ctx, should_cancel=None)
        assert isinstance(stream, AsyncGenerator)
        try:
            assert await anext(stream) == reply
            tools.assert_not_awaited()
            llm.assert_not_called()
        finally:
            await stream.aclose()


@pytest.mark.parametrize("query,kind,answer", _CASES[:8])
@pytest.mark.parametrize(
    "suffix",
    [
        " and explain why",
        ", hint only",
        " with steps",
        " and solve x+1=2",
        " rounded to the nearest 10",
    ],
)
def test_teaching_mixed_and_precision_requests_keep_model(
    query: str, kind: str, answer: str, suffix: str
) -> None:
    assert maybe_direct_math_reply(_verified(query), query + suffix) is None


@pytest.mark.parametrize(
    "case,bad_query",
    [
        (0, "Find the area of a parallelogram base 8 height 4 side 5 and base 6"),
        (0, "Find the area of a parallelogram base 8 height 4 side 6"),
        (0, "Find the area of a parallelogram base 8 height 4"),
        (0, "Find the area and perimeter of a parallelogram base 8 height 4 side 5"),
        (0, "Find twice the area of a parallelogram base 8 height 4 side 5"),
        (0, "Find the area of a parallelogram base 8 m height 4 cm side 5 m"),
        (2, "Find the perimeter of a trapezoid top 4 bottom 8 height 5"),
        (2, "Find the area of a trapezoid top 4 bottom 8 height 5 and height 6"),
        (2, "Find the area of a trapezoid top 8 bottom 4 height 5"),
        (3, "Find the area of a circle radius 3 and circle radius 4"),
        (3, "Find the area of a circle radius 3 and diameter 5"),
        (3, "Find the area of a circle radius 3 m"),
        (3, "Find the area of a circle diameter 3"),
        (3, "Find the area of a circle radius 3!"),
        (3, "Find the area of a circle radius 3/2"),
        (3, "Find the area of a circle radius -3"),
        (3, "Find the area of a circle radius 0"),
        (3, "Find the area of a circle radius nan"),
        (3, "Find the area of a circle radius 1000001"),
        (3, "Find the perimeter of a circle radius 3"),
        (5, "Find the area of a circle radius 3"),
        (6, "Find the area of a circle sector radius 4 angle 90 radians"),
        (6, "Find the area of a circle sector radius 4 angle 90 and angle 60"),
        (6, "Find the area of a circle sector radius 4 angle 90 cm"),
        (6, "Find the area of a circle sector radius 4 angle 361"),
        (6, "Find the area of a circle sector radius 4 angle 90 and perimeter"),
        (6, "Find the perimeter of a circle sector radius 4 angle 90"),
        (6, "Find the area of a circle sector radius 4 angle 90 and use pi=3"),
    ],
)
def test_entire_literal_request_must_match_one_canonical_measure(case: int, bad_query: str) -> None:
    assert maybe_direct_math_reply(_verified(_CASES[case][0]), bad_query) is None


@pytest.mark.parametrize("query,kind,answer", _CASES[:8])
def test_canonical_mismatch_image_and_extra_results_keep_model(
    query: str, kind: str, answer: str
) -> None:
    verified = _verified(query)
    assert verified.canonical_fence is not None
    quantity = query.split(" of ", 1)[0].removeprefix("Find the ").replace(" ", "_")
    dimension = {
        "parallelogram": "base",
        "trapezoid": "top",
        "circle": "radius",
        "sector": "angle_deg",
    }[kind]
    for change in (
        {quantity: None},
        {quantity: True},
        {quantity: 999},
        {dimension: 999},
        {dimension: float("inf")},
        {"unit": "km"},
        {"show_angle": True} if kind in {"parallelogram", "trapezoid"} else {"radius": None},
    ):
        assert (
            maybe_direct_math_reply(
                replace(verified, canonical_fence={**verified.canonical_fence, **change}), query
            )
            is None
        )
    assert maybe_direct_math_reply(verified, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(verified, allow_direct=False), query) is None
    assert maybe_direct_math_reply(replace(verified, canonical_answer="999"), query) is None
    assert (
        maybe_direct_math_reply(
            replace(verified, canonical_fences=[{"type": "answer", "content": "extra"}]), query
        )
        is None
    )


def test_circle_flags_must_match_requested_quantity_and_supplied_dimension() -> None:
    query = _CASES[3][0]
    verified = _verified(query)
    assert verified.canonical_fence is not None
    for flag, value in (
        ("show_area", False),
        ("show_circumference", True),
        ("show_diameter", True),
    ):
        assert (
            maybe_direct_math_reply(
                replace(verified, canonical_fence={**verified.canonical_fence, flag: value}), query
            )
            is None
        )


def test_parallelogram_side_cannot_be_shorter_than_height() -> None:
    query = "Find the area of a parallelogram base 8 height 4 side 3"
    verified = _verified(_CASES[0][0])
    assert verified.canonical_fence is not None
    invalid = replace(verified, canonical_fence={**verified.canonical_fence, "side": 3})
    assert maybe_direct_math_reply(invalid, query) is None


def test_sector_angle_must_not_silently_lose_a_length_unit() -> None:
    query = "Find the area of a circle sector radius 4 cm angle 90 cm"
    assert maybe_direct_math_reply(_verified(query), query) is None


def test_literal_leading_decimal_must_match_verified_radius() -> None:
    query = "Find the area of a circle sector radius .5 m angle 180°"
    verified = _verified(query.replace(".5", "5"))
    assert maybe_direct_math_reply(verified, query) is None
