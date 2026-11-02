"""Closed inequality requests display one answer and its verified number line."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.core.config import Settings
from app.modules.math.fence import validate_math_fences
from app.modules.math.schemas import GraphBlockSpec, NumberLineInterval
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.answer_fence import mark_server_answer_fences
from app.services.solving import VerifiedMathBlock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Solve x^2 < 4",
        "Please solve x^2 < 4.",
        "Solve $x^2 < 4$",
        "Solve x^2 <= 4",
        "Solve x^2 > 4",
        "Solve x > 3",
        "Solve -2 < x <= 2",
        "Solve 1/x > 0",
        "Solve |x-2| < 5",
        "Solve |x-2| <= 5",
        "Solve |x-2| > 5",
    ],
)
async def test_whole_inequality_returns_only_one_answer_and_verified_number_line(query: str):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "number_line"
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    expected = (
        f"```answer\n{verified.canonical_answer}\n```\n\n"
        f"```graph\n{json.dumps(verified.canonical_fence, separators=(',', ':'))}\n```\n"
    )
    # A quadratic shows its working first; the answer and number line still close it.
    assert reply.endswith(expected)
    working = reply[: -len(expected)]
    assert not working or (working.startswith("**Given**") and "**1." in working)
    assert reply.endswith("```\n")
    GraphBlockSpec.model_validate(verified.canonical_fence)
    finalized = validate_math_fences(reply, verified=verified)
    assert finalized.count("```answer") == finalized.count("```graph") == 1
    # Finalization normalizes spacing between fences, without changing data.
    assert [part.strip() for part in finalized.split("```") if part.strip()] == [
        part.strip() for part in mark_server_answer_fences(reply).split("```") if part.strip()
    ]


def _verified_inequality() -> VerifiedMathBlock:
    return VerifiedMathBlock(
        text="verified",
        canonical_answer=r"-2 < x \wedge x < 2",
        canonical_fence=GraphBlockSpec(
            type="number_line",
            expr="x^2 < 4",
            intervals=[NumberLineInterval(start=-2, end=2)],
        ).model_dump(),
    )


@pytest.mark.parametrize(
    "query",
    [
        "Solve x^2 < 4 and explain each step",
        "Solve x^2 < 4 with steps",
        "Solve x^2 < 4, hint only",
        "Give me a hint to solve x^2 < 4",
        "Prove the solution of x^2 < 4",
        "Solve x^2 < 4 and give examples",
        "Solve x^2 < 4 and solve x+1=3",
        "Solve x^2 < 4 and 2+2",
        "Solve x^2 < 4; tell me a joke",
        "Solve x^2 < 4 over the integers",
        "Solve x^2 < 4 for x > 0",
        "Solve x^2 < 4 on [0,1]",
        "Solve x^2 < 4 from 0 to 1",
        "Solve x^2 < 4 for y",
        "Solve x^2 < 4!",
        "Solve x^2 <= 4",
        "Solve x^2 < 40",
        "Solve x^2 < 4 or x > 5",
    ],
)
def test_additional_requests_or_changed_math_cannot_use_partial_certification(query: str):
    assert maybe_direct_math_reply(_verified_inequality(), query) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"allow_direct": False},
        {"canonical_answer": None},
        {"canonical_answer": "x" * 401},
        {"canonical_fences": [{"type": "answer", "content": "another answer"}]},
    ],
)
def test_extra_or_missing_canonical_results_stay_on_model_path(changes):
    assert (
        maybe_direct_math_reply(replace(_verified_inequality(), **changes), "Solve x^2 < 4") is None
    )


def test_camera_inequality_keeps_existing_image_path():
    assert (
        maybe_direct_math_reply(_verified_inequality(), "Solve x^2 < 4", has_image_attachment=True)
        is None
    )


@pytest.mark.parametrize(
    "query",
    [
        "Solve |x-2| < 5 and explain each step",
        "Solve |x-2| < 5, hint only",
        "Solve |x-2| < 5 with proof",
        "Solve |x-2| < 5 and 2+2",
        "Solve |x-2| < 5 and |x+1| > 2",
        "Solve |x-2| < 5 over the integers",
        "Solve |x-2| < 5 for x > 0",
        "Solve |x-2| <= 5",
        "Solve |x-2| > 5",
        "Solve |x-2| < 6",
        "Solve |x-2| < 5!",
        "Solve |x-2 < 5",
        "Solve ||x-2| < 5",
    ],
)
def test_absolute_value_matching_preserves_requests_boundaries_and_unpaired_bars(query: str):
    block = VerifiedMathBlock(
        text="verified",
        canonical_answer=r"-3 < x \wedge x < 7",
        canonical_fence=GraphBlockSpec(
            type="number_line",
            expr="Abs(x-2) < 5",
            intervals=[NumberLineInterval(start=-3, end=7)],
        ).model_dump(),
    )
    assert maybe_direct_math_reply(block, query) is None
