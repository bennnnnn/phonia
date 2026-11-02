"""Complete rectangle measurements can emit the verified answer and diagram immediately."""

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,answer,unit",
    [
        ("Find the area of a rectangle 3 by 4", "12", "units"),
        ("a rectangle area with sides 4, 5", "20", "units"),
        ("Find the perimeter of a rectangle 3 cm by 4 cm", "14", "cm"),
        ("Find the diagonal of a rectangle 3 by 4 m", "5", "m"),
        ("Please calculate the area of the rectangle 2.5 x 4 m.", "10", "m"),
        ("What is the perimeter of a rectangle 2 by 5 feet?", "14", "ft"),
    ],
)
async def test_rectangle_streams_one_answer_and_exact_diagram_without_model(
    query: str, answer: str, unit: str
) -> None:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_answer == answer
    assert verified.canonical_fence["unit"] == unit
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None and reply.endswith("```\n")
    assert reply.count("```answer") == 1 and reply.count("```geometry") == 1
    assert "**Given**" in reply
    assert "**Required**" in reply
    assert "**Formula**" in as_formula_heading(reply)
    assert "**Substitution**" in reply
    assert "```geometry" in reply
    finalized = validate_math_fences(reply, verified=verified)
    assert (
        json.loads(finalized.split("```geometry\n", 1)[1].split("\n```", 1)[0])
        == verified.canonical_fence
    )
    assert [p.strip() for p in finalized.split("```") if p.strip()] == [
        p.strip() for p in mark_server_answer_fences(reply).split("```") if p.strip()
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


def _rectangle(**changes: object) -> VerifiedMathBlock:
    spec: dict[str, object] = {
        "type": "rectangle",
        "width": 3.0,
        "height": 4.0,
        "unit": "units",
        "show_area": True,
        "show_perimeter": False,
        "show_diagonal": False,
        "show_angle": False,
        "area": 12.0,
    }
    spec.update(changes)
    return VerifiedMathBlock(text="verified", canonical_fence=spec, canonical_answer="12")


@pytest.mark.parametrize(
    "query",
    [
        "Find the area of a rectangle 3 by 4 and explain why",
        "Find the area of a rectangle 3 by 4, hint only",
        "Find the area of a rectangle 3 by 4 with steps",
        "Prove the area of a rectangle 3 by 4",
        "Find the area and perimeter of a rectangle 3 by 4",
        "Find the area of a rectangle 3 by 4 and a circle radius 2",
        "Find the area of a rectangle 3 by 4 by 5",
        "Find the area of a rectangle 3 by 4 and 5 by 6",
        "Find the area of a rectangle 4 by 3",
        "Find the area of a rectangle -3 by 4",
        "Find the area of a rectangle 0 by 4",
        "Find the area of a rectangle nan by 4",
        "Find the area of a rectangle 3 by 2+2",
        "Find the area of a rectangle 3 by 4!",
        "Find the area of a rectangle 3 by 4 cm",
        "Find the area of a rectangle 3 m by 4 cm",
        "Find the perimeter of a rectangle 3 by 4",
        "Find the area of a rectangle 3 by 4 rounded to the nearest 10",
    ],
)
def test_rectangle_direct_requires_complete_literal_request(query: str) -> None:
    assert maybe_direct_math_reply(_rectangle(), query) is None


def test_draw_rectangle_returns_only_the_diagram() -> None:
    intent = extract_math_intent("Draw a rectangle")
    assert intent is not None
    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None
    reply = maybe_direct_math_reply(verified, "Draw a rectangle")
    assert reply is not None and reply.startswith("```geometry\n")
    assert "```answer" not in reply


@pytest.mark.parametrize(
    "changes",
    [
        {"width": 4},
        {"height": 3},
        {"unit": "cm"},
        {"show_angle": True},
        {"show_diagonal": True},
        {"show_perimeter": True},
        {"show_area": False},
        {"area": 13},
        {"area": True},
        {"type": "square"},
    ],
)
def test_inconsistent_rectangle_spec_cannot_skip_model(changes: dict[str, object]) -> None:
    assert (
        maybe_direct_math_reply(_rectangle(**changes), "Find the area of a rectangle 3 by 4")
        is None
    )


def test_rectangle_preserves_camera_disabled_direct_and_additional_results() -> None:
    block = _rectangle()
    query = "Find the area of a rectangle 3 by 4"
    assert maybe_direct_math_reply(block, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(block, allow_direct=False), query) is None
    assert maybe_direct_math_reply(replace(block, canonical_answer="13"), query) is None
    assert (
        maybe_direct_math_reply(
            replace(block, canonical_fences=[{"type": "answer", "content": "another result"}]),
            query,
        )
        is None
    )
