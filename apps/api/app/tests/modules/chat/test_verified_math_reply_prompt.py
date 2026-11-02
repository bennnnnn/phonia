"""Verified solver working must not become an unsolicited tutorial."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.modules.math.response_intent import response_intent_prompt
from app.modules.math.schemas import MathImageExtract
from app.modules.math.tools.prompt import (
    VERIFIED_MATH_REPLY_HINT,
    build_math_augmentation,
)
from app.tests.modules.math.prompt_support import augment_prompt_messages


@pytest.mark.asyncio
async def test_live_inequality_injects_concise_guidance_nearest_result_and_user() -> None:
    query = "Solve x^2 < 4"
    messages = [{"role": "system", "content": "base"}, {"role": "user", "content": query}]
    updated, verified = await augment_prompt_messages(
        messages, query, Settings(math_tools_enabled=True)
    )
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "number_line"
    assert verified.canonical_fence["intervals"] == [
        {"start": -2.0, "end": 2.0, "start_inclusive": False, "end_inclusive": False}
    ]
    assert updated[-1] == messages[-1]
    assert verified.response_intent is not None
    assert updated[-2] == {
        "role": "system",
        "content": (
            f"{verified.text}\n\n{response_intent_prompt(verified.response_intent)}\n"
            f"{VERIFIED_MATH_REPLY_HINT}"
        ),
    }
    assert verified.text.endswith("[END VERIFIED MATH]")
    assert VERIFIED_MATH_REPLY_HINT not in verified.text
    assert "Worked-solution layout" in updated[-2]["content"]
    assert "do not wrap the calculation in prose paragraphs" in updated[-2]["content"]
    assert "repeat the result in equivalent forms" in updated[-2]["content"]


@pytest.mark.parametrize(
    "query",
    [
        "Solve x+1=3 and explain each step",
        "Solve x+1=3 with a proof",
        "Solve x+1=3 and give examples",
        "Solve x+1=3, hint only",
        "Solve x+1=3, just the answer, no steps",
    ],
)
@pytest.mark.asyncio
async def test_reply_guidance_preserves_explicit_teaching_or_brevity_requests(query: str) -> None:
    note, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and note is not None
    assert note.endswith(VERIFIED_MATH_REPLY_HINT)
    assert "If the user requests a derivation, explanation, proof, or examples" in note
    assert "For hints or practice, give a focused hint without revealing the full solution" in note
    assert "Honor explicit requests for just the answer or no steps" in note
    assert "all solution branches, units, constants of integration" in note


@pytest.mark.asyncio
async def test_verified_camera_math_uses_same_result_adjacent_guidance() -> None:
    note, verified = await build_math_augmentation(
        "Solve this inequality",
        Settings(math_tools_enabled=True),
        has_image_attachment=True,
        image_math_extract=MathImageExtract(kind="inequality", lhs="x**2", rhs="4", comparator="<"),
    )
    assert verified is not None and note is not None
    assert verified.response_intent is not None
    assert note == (
        f"{verified.text}\n\n{response_intent_prompt(verified.response_intent)}\n"
        f"{VERIFIED_MATH_REPLY_HINT}"
    )


@pytest.mark.asyncio
async def test_missing_verified_result_keeps_existing_honesty_path() -> None:
    with patch("app.modules.math.tools._build_verified_block_async", AsyncMock(return_value=None)):
        note, verified = await build_math_augmentation(
            "Solve x^2 < 4", Settings(math_tools_enabled=True)
        )
    assert verified is None and note is not None
    assert "a verified result could not be produced" in note
    assert VERIFIED_MATH_REPLY_HINT not in note
