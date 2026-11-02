"""Closed literal solids retain the exact verified quantity without narration."""

import re
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
from app.modules.math.tools.direct_solids import solid_direct_request
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.answer_fence import mark_server_answer_fences
from app.services.solving import VerifiedMathBlock
from app.services.workout import as_formula_heading

_MATRIX = [
    ("cube side 3", "27", "54"),
    ("rectangular prism 2 by 3 by 4", "24", "52"),
    ("cylinder radius 2 height 3", "37.7", "62.83"),
    ("cone radius 3 height 4", "37.7", "75.4"),
    ("sphere radius 2", "33.51", "50.27"),
    ("square pyramid side 6 height 4", "48", "96"),
]


def _verified(query: str) -> VerifiedMathBlock:
    intent = extract_math_intent(query)
    assert intent is not None
    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None
    return verified


@pytest.mark.asyncio
@pytest.mark.parametrize("shape,volume,surface", _MATRIX)
@pytest.mark.parametrize("quantity,power", [("volume", 3), ("surface area", 2)])
async def test_each_closed_solid_emits_one_exact_answer_without_model(
    shape: str, volume: str, surface: str, quantity: str, power: int
) -> None:
    query = f"Find the {quantity} of a {shape}"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None
    expected = rf"{volume if quantity == 'volume' else surface}\ \mathrm{{units}}^{{{power}}}"
    assert verified.canonical_answer == expected
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    assert reply.startswith("**Given**  \n")
    assert all(
        heading in as_formula_heading(reply)
        for heading in ("**Required**", "**Formula**", "**Substitution**", "**Answer**")
    )
    # A measure with π in it is shown rounded, and its card says so.
    rounded = shape.split()[0] in {"cylinder", "cone", "sphere"}
    card = rf"\approx {expected}" if rounded else expected
    assert reply.endswith(f"```answer\n{card}\n```\n")
    assert reply.count("```answer") == 1
    assert (
        validate_math_fences(reply, verified=verified).strip()
        == mark_server_answer_fences(reply).strip()
    )
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


@pytest.mark.parametrize(
    "query,answer",
    [
        ("Please compute the volume of the cube with edge 0.5 m.", r"0.125\ \mathrm{m}^{3}"),
        ("What is the total surface area of a cube side 3 cm?", r"54\ \mathrm{cm}^{2}"),
        ("Find the volume of a cuboid 2 by 3 by 4 cm", r"24\ \mathrm{cm}^{3}"),
        ("Find the volume of a cylinder with radius 2 m and height 3 m", r"37.7\ \mathrm{m}^{3}"),
        ("Find the surface area of a cone radius 3 cm height 4 cm", r"75.4\ \mathrm{cm}^{2}"),
        ("Find the volume of a sphere radius .5 m", r"0.52\ \mathrm{m}^{3}"),
        (
            "Find the surface area of a square pyramid with side 6 cm and height 4 cm",
            r"96\ \mathrm{cm}^{2}",
        ),
    ],
)
def test_units_and_existing_numeric_precision_are_preserved(query: str, answer: str) -> None:
    verified = _verified(query)
    assert verified.canonical_answer == answer
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    assert "**Formula**" in as_formula_heading(reply) and "**Substitution**" in reply
    card = rf"\approx {answer}" if re.search("cylinder|cone|sphere", query) else answer
    assert reply.endswith(f"```answer\n{card}\n```\n")


@pytest.mark.parametrize("shape,volume,surface", _MATRIX)
@pytest.mark.parametrize(
    "suffix",
    [" and explain why", ", hint only", " with steps", " and solve x+1=2", " in terms of pi"],
)
def test_extra_or_teaching_requests_keep_model(
    shape: str, volume: str, surface: str, suffix: str
) -> None:
    query = f"Find the volume of a {shape}"
    assert maybe_direct_math_reply(_verified(query), query + suffix) is None


@pytest.mark.parametrize(
    "query",
    [
        "Find the volume and surface area of a cube side 3",
        "Find twice the volume of a cube side 3",
        "Find the volume of a cube side 3 and side 4",
        "Find the volume of a cube side 3 and a sphere radius 2",
        "Find the volume of a cube side 3 cm in m3",
        "Find the volume of a cube side 3 cm2",
        "Find the volume of a cube side 3!",
        "Find the volume of a cube side 3/2",
        "Find the volume of a cube side nan",
        "Find the volume of a cube side 1000001",
        "Find the volume of a cube side -3",
        "Find the volume of a cube side 0",
        "Find the volume of a rectangular prism 2 by 3 by 4 by 5",
        "Find the volume of a rectangular prism 2 by 3",
        "Find the volume of a rectangular prism 2 m by 3 cm by 4 m",
        "Find the volume of a cylinder radius 2 height 3 and diameter 5",
        "Find the volume of a cylinder radius 2 cm height 3 m",
        "Find the lateral surface area of a cylinder radius 2 height 3",
        "Find the surface area of a cylinder radius 2 height 3 without the top",
        "Find the surface area of an open cylinder radius 2 height 3",
        "Find the volume of a cone radius 3 slant height 4",
        "Find the surface area of a cone radius 3 height 4 without its base",
        "Find the volume of a sphere radius 2 with a hole",
        "Find the volume of a sphere 2",
        "Find the volume of a pyramid side 6 height 4",
        "Find the volume of a triangular pyramid side 6 height 4",
        "Find the volume of a square pyramid side 6 slant height 4",
        "Find the volume of a square pyramid side 6 height 4 offset from the center",
    ],
)
def test_malformed_partial_or_qualified_solids_cannot_use_generic_direct_fallback(
    query: str,
) -> None:
    assert solid_direct_request(query) is False
    assert maybe_direct_math_reply(_verified("Find the volume of a cube side 3"), query) is None


def test_other_math_families_remain_outside_solid_guard() -> None:
    assert solid_direct_request("What is the cube root of 27?") is None
    assert solid_direct_request("Solve x^3=27") is None
    assert solid_direct_request("Find the area of a square side 3") is None


@pytest.mark.parametrize("shape,volume,surface", _MATRIX)
def test_images_and_missing_or_multiple_canonical_answers_keep_model(
    shape: str, volume: str, surface: str
) -> None:
    query = f"Find the volume of a {shape}"
    verified = _verified(query)
    assert maybe_direct_math_reply(verified, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(verified, allow_direct=False), query) is None
    assert maybe_direct_math_reply(replace(verified, canonical_fence=None), query) is None
    assert maybe_direct_math_reply(replace(verified, canonical_answer="different"), query) is None
    assert (
        maybe_direct_math_reply(
            replace(verified, canonical_fences=[{"type": "answer", "content": "extra"}]), query
        )
        is None
    )


def test_complete_literal_request_must_agree_with_extractor_dimensions_unit_and_quantity() -> None:
    from app.modules.math.match.geometry import parse_solid

    query = "Find the volume of a cube side 3 cm"
    actual = parse_solid(query)
    assert actual is not None
    for invalid in (
        replace(actual, side=4),
        replace(actual, unit="m"),
        replace(actual, wants_volume=False, wants_surface_area=True),
    ):
        with patch("app.modules.math.tools.direct_solids.parse_solid", return_value=invalid):
            assert solid_direct_request(query) is False
