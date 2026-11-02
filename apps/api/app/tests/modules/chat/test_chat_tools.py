from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.services.solving import VerifiedMathBlock


@pytest.mark.asyncio
async def test_augment_subject_injects_math_block_only_once():
    """End-to-end regression for the duplicate verified-block injection bug:
    with the tool loop off, a math-intent turn must get exactly one
    verified-math system message, not two."""
    from app.tests.modules.chat.chat_test_support import augment_subject

    settings = Settings(
        math_tools_enabled=True,
        mcp_tool_loop_enabled=False,
        web_search_enabled=False,
    )
    user_text = "differentiate x^2"
    messages = [{"role": "system", "content": "base"}, {"role": "user", "content": user_text}]

    fake_block = VerifiedMathBlock(text="Verified (SymPy): d/dx(x^2) = 2x. Do NOT recompute.")

    with patch(
        "app.modules.math.tools._build_verified_block_async",
        AsyncMock(return_value=fake_block),
    ):
        updated, verified_math = await augment_subject(
            messages,
            user_text,
            settings,
        )

    matches = [m for m in updated if fake_block.text in m.get("content", "")]
    assert len(matches) == 1
    assert verified_math is not None and verified_math.text == fake_block.text


def test_owned_tool_loop_defaults_on():
    assert Settings().mcp_tool_loop_enabled is True


@pytest.mark.asyncio
async def test_augment_subject_keeps_math_when_tool_loop_on():
    """Enabling the loop must not skip heuristic SymPy — homework cannot
    wait on the model choosing the sympy tool."""
    from app.tests.modules.chat.chat_test_support import augment_subject

    settings = Settings(
        math_tools_enabled=True,
        mcp_tool_loop_enabled=True,
        web_search_enabled=False,
    )
    user_text = "differentiate x^2"
    messages = [{"role": "system", "content": "base"}, {"role": "user", "content": user_text}]
    fake_block = VerifiedMathBlock(text="Verified (SymPy): d/dx(x^2) = 2x. Do NOT recompute.")

    with patch(
        "app.modules.math.tools._build_verified_block_async",
        AsyncMock(return_value=fake_block),
    ):
        updated, verified_math = await augment_subject(
            messages,
            user_text,
            settings,
        )

    matches = [m for m in updated if fake_block.text in m.get("content", "")]
    assert len(matches) == 1
    assert verified_math is not None and verified_math.text == fake_block.text
