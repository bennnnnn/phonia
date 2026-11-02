"""An angle-only measurement asks for scale; it never inherits a relative area."""

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
from app.modules.math.tools.direct import can_direct_verified_math_reply, maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.solving import VerifiedMathBlock


def _verified(query: str) -> VerifiedMathBlock:
    intent = extract_math_intent(query)
    assert intent is not None
    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    return verified


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", ["area", "perimeter"])
@pytest.mark.parametrize("angles", ["30,60,90", "120,40,20", "60,60,60"])
async def test_complete_aaa_measurement_gives_missing_scale_without_numeric_answer(
    quantity: str, angles: str
) -> None:
    query = f"Find the {quantity} of a triangle with angles {angles}"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_answer is None
    assert can_direct_verified_math_reply(verified, query) is True
    reply = maybe_direct_math_reply(verified, query)
    assert (
        reply == f"The {quantity} cannot be determined from angles alone. What is one side length?"
    )
    finalized = validate_math_fences(reply, verified=verified)
    assert finalized.startswith(reply)
    assert "```answer" not in finalized
    assert finalized.count("```geometry") == 1
    diagram = json.loads(finalized.split("```geometry\n", 1)[1].split("\n```", 1)[0])
    assert diagram["relative_lengths"] is True
    assert diagram["area"] is None and diagram["perimeter"] is None
    assert "area" not in diagram["labels"] and "perimeter" not in diagram["labels"]


@pytest.mark.parametrize(
    "query",
    [
        "Please find the area of a triangle with angles 30, 60, 90 degrees.",
        "What is the area of the triangle with angles 30,60,90?",
        "Calculate area of triangle with angles 30,60,90",
    ],
)
def test_complete_polite_measurements_keep_the_same_missing_size_answer(query: str) -> None:
    assert maybe_direct_math_reply(_verified(query), query) == (
        "The area cannot be determined from angles alone. What is one side length?"
    )


@pytest.mark.parametrize(
    "query",
    [
        "Find the area of a triangle with angles 30,60,90 and side 5",
        "Find the area of a triangle with angles 30,60,90 and explain why",
        "Find the area of a triangle with angles 30,60,90, hint only",
        "Find the area of a triangle with angles 30,60,90 with steps",
        "Find the area of a triangle with angles 30,60,90 and solve x+1=2",
        "Find the area and perimeter of a triangle with angles 30,60,90",
        "Find twice the area of a triangle with angles 30,60,90",
        "Find the area of a spherical triangle with angles 30,60,90",
        "Find the area of a triangle with angles 30,,60,90",
        "Find the area of a triangle with angles 30,60,90,20",
        "Find the area of a triangle with angles 60,60,70",
        "Find the area of a triangle with angles 0,90,90",
        "Find the area of a triangle with angles -30,60,150",
        "Find the area of a triangle with angles 30,60,90 radians",
        "Find the area of a triangle with angles 60,60,60",
    ],
)
def test_extra_invalid_or_mismatched_requests_retain_model_path(query: str) -> None:
    original = "Find the area of a triangle with angles 30,60,90"
    assert maybe_direct_math_reply(_verified(original), query) is None


def test_image_disabled_or_nonrelative_canonical_result_cannot_take_shortcut() -> None:
    query = "Find the area of a triangle with angles 30,60,90"
    verified = _verified(query)
    assert maybe_direct_math_reply(verified, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(verified, allow_direct=False), query) is None
    assert maybe_direct_math_reply(replace(verified, canonical_answer="1"), query) is None
    assert verified.canonical_fence is not None
    for change in (
        {"relative_lengths": False},
        {"unit": "cm"},
        {"area": 1},
        {"perimeter": 2},
        {"c": 99},
    ):
        changed = replace(verified, canonical_fence={**verified.canonical_fence, **change})
        assert maybe_direct_math_reply(changed, query) is None
    extra = replace(verified, canonical_fences=[{"type": "answer", "content": "1"}])
    assert maybe_direct_math_reply(extra, query) is None


def test_known_side_measurement_still_returns_determined_area() -> None:
    query = "Find the area of a triangle with sides 3,4,5"
    reply = maybe_direct_math_reply(_verified(query), query)
    assert reply is not None
    assert reply.startswith("**Given**  \n")
    assert "**Heron's formula**  \n" in reply and "— Heron" not in reply
    assert "**Substitution**" in reply
    assert "```answer\n6\\ \\mathrm{units}^{2}\n```" in reply
    assert "cannot be determined" not in reply


@pytest.mark.asyncio
async def test_missing_scale_reply_skips_tool_selection_and_model_stream() -> None:
    query = "Find the area of a triangle with angles 30,60,90"
    verified = _verified(query)
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
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
