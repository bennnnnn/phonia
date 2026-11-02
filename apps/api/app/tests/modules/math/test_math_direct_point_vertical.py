"""Literal point and vertical plots need no additional model after verification."""

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
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.answer_fence import mark_server_answer_fences
from app.services.solving import VerifiedMathBlock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Plot the point (2,3)",
        "Mark point (-2,3.5)",
        "Please graph the point (0,0).",
        "Plot x=4",
        "Graph x=-3",
        "Graph the line x=0",
    ],
)
async def test_literal_plot_preserves_canonical_data_and_reaches_first_token_without_model(query):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None and reply.endswith("```\n")
    assert reply.count("```graph") == 1
    assert reply.count("```answer") == (1 if verified.canonical_answer else 0)
    finalized = validate_math_fences(reply, verified=verified)
    assert (
        json.loads(finalized.split("```graph\n", 1)[1].split("\n```", 1)[0])
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


def _point_block(**changes) -> VerifiedMathBlock:
    graph = GraphBlockSpec(expr="(2, 3)", points=[[2, 3]], x_min=-3, x_max=7).model_dump()
    graph.update(changes)
    # Extraction read "Plot the point (2,3)" and nothing else; the block is bound to it.
    return VerifiedMathBlock(
        text="verified",
        canonical_fence=graph,
        canonical_answer="(2, 3)",
        plot_point=(2.0, 3.0),
        direct_request_text="Plot the point (2,3)",
    )


def _vertical_block(**changes) -> VerifiedMathBlock:
    graph = GraphBlockSpec(type="vertical", expr="x = 4", x=4, y_min=-10, y_max=10).model_dump()
    graph.update(changes)
    return VerifiedMathBlock(text="verified", canonical_fence=graph)


@pytest.mark.parametrize(
    "query",
    [
        "Plot the point (2,3) and explain the coordinates",
        "Plot the point (2,3), hint only",
        "Plot the point (2,3) with steps",
        "Plot the point (2,3) and (4,5)",
        "Plot the point (2,3) and graph y=x",
        "Plot the point (2,3) from 0 to 10",
        "Plot the point (2,3) in polar coordinates",
        "Plot the point (3,2)",
        "Plot the point (2.3)",
        "Plot the point (2,3",
        "Plot the point (2,1+2)",
        "Plot the point (2,nan)",
        "Plot the point (2,inf)",
    ],
)
def test_point_guard_preserves_full_request_and_literal_coordinates(query):
    # Read from this request, no literal point is carried; and the block built
    # for "Plot the point (2,3)" is never reused for it.
    intent = extract_math_intent(query)
    assert intent is None or intent.plot_point in (None, (3.0, 2.0))
    assert maybe_direct_math_reply(_point_block(), query) is None


def test_point_block_skips_model_only_for_the_request_it_read():
    assert maybe_direct_math_reply(_point_block(), "Plot the point (2,3)") is not None
    assert maybe_direct_math_reply(_point_block(), "  Plot the point   (2,3) ") is not None
    unbound = replace(_point_block(), direct_request_text=None)
    assert maybe_direct_math_reply(unbound, "Plot the point (2,3)") is None
    unread = replace(_point_block(), plot_point=None)
    assert maybe_direct_math_reply(unread, "Plot the point (2,3)") is None


@pytest.mark.parametrize(
    "query",
    [
        "Plot x=4 and explain why it is vertical",
        "Plot x=4, hint only",
        "Plot x=4 with steps",
        "Plot x=4 and x=5",
        "Plot x=4 and solve x+1=3",
        "Plot x=4 for -2<=y<=2",
        "Plot x=4 from -2 to 2",
        "Plot x=4 on [-10,10]",
        "Plot x=4!",
        "Plot x=2+2",
        "Plot x=5",
        "Plot y=4",
        "Plot x=nan",
        "Plot x=inf",
    ],
)
def test_vertical_guard_preserves_clauses_ranges_and_constant(query):
    assert maybe_direct_math_reply(_vertical_block(), query) is None


@pytest.mark.parametrize(
    "changes",
    [{"points": []}, {"points": [[2, 3], [4, 5]]}, {"expr": "(3,2)"}, {"points": [[2, None]]}],
)
def test_incomplete_or_inconsistent_point_cannot_skip_model(changes):
    assert maybe_direct_math_reply(_point_block(**changes), "Plot the point (2,3)") is None


@pytest.mark.parametrize(
    "changes",
    [
        {"x": None},
        {"y_min": None},
        {"y_max": -10},
        {"x": True},
        {"expr": "x = 9"},
        {"expr": "y = 4"},
        {"expr": None},
    ],
)
def test_incomplete_vertical_cannot_skip_model(changes):
    assert maybe_direct_math_reply(_vertical_block(**changes), "Plot x=4") is None


@pytest.mark.parametrize("point", [True, False])
def test_plot_keeps_camera_extra_answers_and_disabled_direct_guard(point):
    block = _point_block() if point else _vertical_block()
    query = "Plot the point (2,3)" if point else "Plot x=4"
    assert maybe_direct_math_reply(block, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(block, allow_direct=False), query) is None
    assert (
        maybe_direct_math_reply(replace(block, canonical_answer="unrelated answer"), query) is None
    )
    assert (
        maybe_direct_math_reply(
            replace(block, canonical_fences=[{"type": "answer", "content": "another answer"}]),
            query,
        )
        is None
    )
