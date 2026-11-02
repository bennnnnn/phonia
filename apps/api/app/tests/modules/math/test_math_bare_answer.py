""" "x = 6" alone is an answer with no problem: the reply asks what it answers.

It got a verified card repeating x = 6: the fallback extractor read it as an
equation to solve.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.modules.math.tools.bare_answer import BARE_ANSWER_NOTE, bare_answer
from app.tests.modules.math.prompt_support import augment_prompt_messages


@pytest.mark.parametrize(
    "text, expected",
    [
        ("x = 6", True),
        ("x=6", True),
        ("y = -2.5.", True),
        ("x = 3/4", True),
        ("x = 6 and y = 2", False),
        ("2x = 6", False),
        ("x = y + 1", False),
        ("check my answer: x = 6", False),
    ],
)
def test_bare_answer_reads_a_lone_value(text: str, expected: bool) -> None:
    assert bare_answer(text) is expected


@pytest.mark.asyncio
async def test_a_bare_answer_gets_no_verified_card() -> None:
    messages: list[dict[str, Any]] = [{"role": "user", "content": "x = 6"}]
    extract = AsyncMock()
    with patch("app.modules.math.tools.prompt.llm_extract_math_intent", extract):
        prepared, verified = await augment_prompt_messages(
            messages, "x = 6", Settings(math_tools_enabled=True)
        )
    assert verified is None
    extract.assert_not_awaited()
    assert BARE_ANSWER_NOTE in prepared[-2]["content"]
    assert "ask which problem it is the answer to" in BARE_ANSWER_NOTE
