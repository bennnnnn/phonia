"""Integration: math tools wired into chat augment path."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.solving import VERIFIED_MATH_BEGIN
from app.tests.modules.chat.chat_test_support import augment_subject


@pytest.mark.asyncio
async def test_augment_subject_injects_math_for_solve() -> None:
    settings = Settings(web_search_enabled=False, math_tools_enabled=True)
    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "Solve x^2 + 2 = 6"},
    ]

    updated, verified_math = await augment_subject(messages, "Solve x^2 + 2 = 6", settings)

    assert len(updated) == 3
    assert updated[1]["role"] == "system"
    assert VERIFIED_MATH_BEGIN in updated[1]["content"]
    assert "SymPy" not in updated[1]["content"]
    assert verified_math is not None
    assert verified_math.canonical_fence is not None
    assert verified_math.canonical_fence["type"] == "answer"
    assert "x" in verified_math.canonical_fence["content"]
