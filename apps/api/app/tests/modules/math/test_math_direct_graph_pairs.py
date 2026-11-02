"""Complete two-curve plots should reach the first token without another model."""

from __future__ import annotations

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
from app.modules.math.schemas import GraphBlockSpec
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.solving import VerifiedMathBlock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Graph y=x^2 and y=2x on the same graph",
        "Graph y=x^2 and y=2x on the same graph.",
        "Graph y=x^2 and y=2x together?",
        "Plot x^2 and 2x",
        "Please graph y=x^2 and y=2x together",
        "Graph y=x^2 and y=2x from 0 to 5",
        "Graph y=1/x and y=x",
    ],
)
async def test_complete_pair_preserves_both_curves_and_skips_tools_and_visible_model(query: str):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    fence = verified.canonical_fence
    assert len(fence["points"]) >= 2 and len(fence["points2"]) >= 2
    reply = maybe_direct_math_reply(verified, query)
    assert reply == f"```graph\n{json.dumps(fence, separators=(',', ':'))}\n```\n"
    finalized = validate_math_fences(reply, verified=verified)
    assert finalized.count("```graph") == 1
    assert json.loads(finalized.split("```graph\n", 1)[1].split("\n```", 1)[0]) == fence
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="smart-chat",
        prompt_messages=[{"role": "user", "content": query}],
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


def _pair_block(**changes) -> VerifiedMathBlock:
    fence = GraphBlockSpec(
        expr="x**2",
        points=[[-1, 1], [0, 0], [1, 1]],
        expr2="2x",
        variable2="x",
        points2=[[-1, -2], [0, 0], [1, 2]],
    ).model_dump()
    fence.update(changes)
    return VerifiedMathBlock(text="verified", canonical_fence=fence)


@pytest.mark.parametrize(
    "query",
    [
        "Graph y=x^2 and y=2x and explain the curves",
        "Graph y=x^2 and y=2x with steps",
        "Graph y=x^2 and y=2x, hint only",
        "Graph y=x^2 and y=2x and solve x^2=2x",
        "Graph y=x^2 and y=2x and find their intersections",
        "Graph y=x^2 and y=2x and y=3x",
        "Graph y=x^2 and y=2x then tell me a joke",
        "Compare y=x^2 and y=2x",
        "Graph y=x^2 and y=2x for integers",
        "Graph y=x^2 and y=2x from 0 to 5",
        "Graph y=x^2 and y=2x on [0,5]",
        "Graph y=x^2 and y=2x on the same graph from 0 to 5",
        "Graph y=x^2 and y=2x from 0 to 5 from -10 to 10",
        "Graph y=x^2 and y=2x!",
        "Graph y=x^2 and y=3x",
        "Graph y=x^2 and x=2y",
        "Graph y=x^2",
    ],
)
def test_pair_direct_guard_does_not_drop_other_requests_or_changed_math(query: str):
    assert maybe_direct_math_reply(_pair_block(), query) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"points": []},
        {"points2": []},
        {"points2": [[0, 0]]},
        {"expr2": None},
        {"variable2": "t"},
        {"variable": "t"},
    ],
)
def test_incomplete_or_incompatible_pair_cannot_skip_model(changes):
    assert maybe_direct_math_reply(_pair_block(**changes), "Graph y=x^2 and y=2x") is None


def test_pair_with_additional_verified_result_or_image_keeps_model():
    query = "Graph y=x^2 and y=2x"
    pair = _pair_block()
    assert maybe_direct_math_reply(replace(pair, canonical_answer="x = 2"), query) is None
    assert maybe_direct_math_reply(replace(pair, allow_direct=False), query) is None
    assert maybe_direct_math_reply(pair, query, has_image_attachment=True) is None
    assert (
        maybe_direct_math_reply(
            replace(pair, canonical_fences=[{"type": "answer", "content": "x = 2"}]), query
        )
        is None
    )
