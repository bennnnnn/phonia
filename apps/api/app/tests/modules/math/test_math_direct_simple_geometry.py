"""Whole literal square/triangle measurements preserve canonical results without a model."""

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
    ("Find the area of a square side 3 cm", "square", "9"),
    ("Find the perimeter of a square side 3", "square", "12"),
    ("Find the diagonal of a square side 3", "square", "4.2426"),
    ("Please compute the area of the square with side 2.5 m.", "square", "6.25"),
    ("Find the area of a triangle base 3 height 4", "triangle", "6"),
    ("What is the area of a triangle with base 3 cm and height 4 cm?", "triangle", "6"),
    ("Find the area of a right triangle legs 3 and 4", "right_triangle", "6"),
    ("Find the perimeter of a right triangle legs 3 and 4", "right_triangle", "12"),
    ("Find the hypotenuse of a right triangle legs 3 and 4", "right_triangle", "5"),
    ("Compute the hypotenuse of a right triangle with legs 3 m and 4 m", "right_triangle", "5"),
    ("Find the area of a triangle with sides 3,4,5", "triangle_sides", "6"),
    ("Find the perimeter of a triangle with sides 3,4,5", "triangle_sides", "12"),
    ("Find the area of a triangle with sides 3 cm, 4 cm, and 5 cm", "triangle_sides", "6"),
]


def _verified(query: str) -> VerifiedMathBlock:
    intent = extract_math_intent(query)
    assert intent is not None
    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    return verified


@pytest.mark.asyncio
@pytest.mark.parametrize("query,kind,answer", _CASES)
async def test_complete_geometry_reaches_first_token_without_model(
    query: str, kind: str, answer: str
) -> None:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == kind
    assert verified.canonical_answer == answer
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


@pytest.mark.parametrize("query,kind,answer", _CASES)
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
def test_extra_or_teaching_requests_keep_model_path(
    query: str, kind: str, answer: str, suffix: str
) -> None:
    verified = _verified(query)
    assert maybe_direct_math_reply(verified, query.rstrip(".?") + suffix) is None


@pytest.mark.parametrize(
    "query,bad_query",
    [
        (_CASES[0][0], "Find the area and perimeter of a square side 3 cm"),
        (_CASES[0][0], "Find the area of a square side 3 cm and a square side 4 cm"),
        (_CASES[0][0], "Find the area of a square side 3 cm by 4 cm"),
        (_CASES[0][0], "Find the area of a square side 4 cm"),
        (_CASES[0][0], "Find the area of a square side 3 m"),
        (_CASES[0][0], "Find the area of a square side -3 cm"),
        (_CASES[0][0], "Find the area of a square side 0 cm"),
        (_CASES[0][0], "Find the area of a square side nan cm"),
        (_CASES[0][0], "Find the area of a square side 3! cm"),
        (_CASES[4][0], "Find the area of a triangle base 3 height 4 and base 5"),
        (_CASES[4][0], "Find the perimeter of a triangle base 3 height 4"),
        (_CASES[4][0], "Find the area of a right triangle legs 3 and 4"),
        (_CASES[4][0], "Find the area of a triangle base 4 height 3"),
        (_CASES[6][0], "Find the area of a right triangle legs 3 and 4 and 5"),
        (_CASES[6][0], "Find the area and hypotenuse of a right triangle legs 3 and 4"),
        (_CASES[6][0], "Find the area of a right triangle legs 4 and 3"),
        (_CASES[8][0], "Find the area of a right triangle legs 3 and 4"),
        (_CASES[10][0], "Find the area of a triangle with sides 3,4,5,6"),
        (_CASES[10][0], "Find the area of a triangle with sides 3,4,6"),
        (_CASES[10][0], "Find the area of a triangle with sides 4,3,5"),
        (_CASES[10][0], "Find the area of a triangle with sides 3,,4,5"),
        (_CASES[10][0], "Find the area of a triangle with angles 3,4,5"),
        (_CASES[10][0], "Find the area of a triangle with sides 3 m,4 cm,5 m"),
    ],
)
def test_single_shape_kind_literals_units_and_quantity_must_match(
    query: str, bad_query: str
) -> None:
    assert maybe_direct_math_reply(_verified(query), bad_query) is None


@pytest.mark.parametrize("query,kind,answer", _CASES)
def test_missing_inconsistent_and_extra_canonical_results_keep_model(
    query: str, kind: str, answer: str
) -> None:
    verified = _verified(query)
    assert verified.canonical_fence is not None
    quantity = query.lower().split(" of ", 1)[0].split()[-1]
    for change in (
        {quantity: None},
        {quantity: True},
        {quantity: 999},
        {"unit": "km"},
        {"type": "rectangle"},
    ):
        invalid = replace(verified, canonical_fence={**verified.canonical_fence, **change})
        assert maybe_direct_math_reply(invalid, query) is None
    assert maybe_direct_math_reply(verified, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(verified, allow_direct=False), query) is None
    assert maybe_direct_math_reply(replace(verified, canonical_answer="999"), query) is None
    assert (
        maybe_direct_math_reply(
            replace(verified, canonical_fences=[{"type": "answer", "content": "extra"}]), query
        )
        is None
    )


@pytest.mark.parametrize(
    "quantities",
    ["area", "perimeter", "diagonal", "area and perimeter", "area and perimeter and diagonal"],
)
def test_square_diagram_only_shows_requested_measurements(quantities: str) -> None:
    query = f"Find the {quantities} of a square side 3"
    verified = _verified(query)
    assert verified.canonical_fence is not None
    for quantity in ("area", "perimeter", "diagonal"):
        assert verified.canonical_fence[f"show_{quantity}"] is (quantity in quantities)
    if " and " in quantities:
        assert maybe_direct_math_reply(verified, query) is None


def test_draw_only_square_keeps_existing_illustration_flags() -> None:
    verified = _verified("Draw a square")
    assert verified.canonical_fence is not None
    assert not any(
        verified.canonical_fence[f"show_{quantity}"]
        for quantity in ("area", "perimeter", "diagonal")
    )
    reply = maybe_direct_math_reply(verified, "Draw a square")
    assert reply is not None and reply.startswith("```geometry\n")
    assert "```answer" not in reply


def test_labeling_a_hypotenuse_does_not_attach_unsolicited_answer() -> None:
    query = "Draw a right triangle with legs 3 and 4. Label the sides including the hypotenuse."
    assert _verified(query).canonical_answer is None


def test_explicit_multi_measure_right_triangle_keeps_existing_answer_priority_and_model() -> None:
    query = "Find the area, perimeter and hypotenuse of a right triangle legs 3 and 4"
    verified = _verified(query)
    assert verified.canonical_answer == "12"
    assert maybe_direct_math_reply(verified, query) is None


@pytest.mark.parametrize(
    "query",
    [
        "Find the angle between the hypotenuse and base of a right triangle legs 3 and 4",
        "Find twice the hypotenuse of a right triangle legs 3 and 4",
        "Find the square of the hypotenuse of a right triangle legs 3 and 4",
        "Find the hypotenuse of a right triangle legs 3 and 4 and double it",
        "Find the hypotenuse of a right triangle legs 3 and 4 with steps",
    ],
)
def test_hypotenuse_reference_or_extra_request_does_not_certify_its_length(query: str) -> None:
    if extract_math_intent(query) is None:
        return  # "twice the hypotenuse", "double it": a measure through another is declined
    verified = _verified(query)
    assert verified.canonical_answer is None
    assert maybe_direct_math_reply(verified, query) is None
