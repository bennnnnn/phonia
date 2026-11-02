"""The last math instructions honor the request on every production prompt path."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways.mcp.base import ToolResult
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.chat.tool_loop import run_tool_rounds
from app.modules.math.reply_policy import MATH_INTENT_HINT, MATH_REPLY_POLICY, MATH_TUTORING_HINT
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import needs_symbolic_math
from app.services.workout import (
    MATH_WORKOUT_PROMPT_RULE,
    PHYSICS_WORKOUT_PROMPT_SHORT,
    SELF_CHECK_PROMPT_RULE,
    WORKOUT_PROMPT_RULE,
)
from app.tests.modules.math.prompt_support import augment_prompt_messages


def _messages(query: str, *, compact: bool = False) -> list[dict[str, Any]]:
    hints = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=compact,
    )
    return [{"role": "system", "content": "\n\n".join(hints)}, {"role": "user", "content": query}]


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize(
    "query",
    [
        "Draw a triangle with angles 60,60,70",
        "Solve x^2 < 4",
        "Solve x+1=3 and explain each step",
        "Solve x+1=3, hint only",
    ],
)
def test_detected_math_policy_is_last_after_actual_style_and_tutoring_hints(
    compact: bool, query: str
) -> None:
    assert needs_symbolic_math(query)
    content = _messages(query, compact=compact)[0]["content"]
    assert content.endswith(MATH_REPLY_POLICY)
    if not compact:
        assert content.index(MATH_TUTORING_HINT) < content.index(MATH_REPLY_POLICY)
    assert "say you're working it out and show the steps" not in content
    assert "is stuck after a hint, or has a deadline" not in content


@pytest.mark.asyncio
async def test_detected_but_unextractable_problem_has_final_local_clarification_guidance() -> None:
    query = "Draw a triangle with angles 60,60,70"
    assert needs_symbolic_math(query) and extract_math_intent(query) is None
    initial = _messages(query)
    with (
        patch("app.modules.math.tools._build_verified_block_async", AsyncMock()) as solve,
        patch(
            "app.modules.math.tools.prompt.llm_extract_math_intent",
            AsyncMock(return_value=None),
        ),
    ):
        prepared, verified = await augment_prompt_messages(
            initial, query, Settings(math_tools_enabled=True)
        )
    solve.assert_not_awaited()
    assert verified is None
    assert prepared[-1] == initial[-1]
    assert prepared[-2]["role"] == "system"
    assert prepared[-2]["content"].endswith(MATH_REPLY_POLICY)
    assert "No verified solver result is available" in prepared[-2]["content"]
    assert "ask at most one necessary clarification question" in prepared[-2]["content"]
    assert "Do not assume missing dimensions" in prepared[-2]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Solve x+1=3",
        "Solve x+1=3 with a proof",
        "Solve x+1=3, hint only",
    ],
)
async def test_verified_result_keeps_request_aware_policy_after_the_solver_work(query: str) -> None:
    prepared, verified = await augment_prompt_messages(
        _messages(query), query, Settings(math_tools_enabled=True)
    )
    assert verified is not None
    content = prepared[-2]["content"]
    assert content.startswith(verified.text)
    assert content.endswith(MATH_REPLY_POLICY)
    assert MATH_REPLY_POLICY not in verified.text
    assert "If the user requests a derivation, explanation, proof, or examples" in content
    assert (
        "For hints or practice, give a focused hint without revealing the full solution" in content
    )
    assert prepared[-1]["content"] == query


@pytest.mark.asyncio
async def test_failed_solver_ends_with_concise_guidance_and_preserves_honesty() -> None:
    query = "Solve x^2 < 4"
    with patch("app.modules.math.tools._build_verified_block_async", AsyncMock(return_value=None)):
        prepared, verified = await augment_prompt_messages(
            _messages(query), query, Settings(math_tools_enabled=True)
        )
    assert verified is None
    content = prepared[-2]["content"]
    assert "Do NOT claim the answer was verified" in content
    assert "show your work" not in content
    # Unverified working checks itself before its Answer.
    assert content.endswith(f"{MATH_REPLY_POLICY} {SELF_CHECK_PROMPT_RULE}")


@pytest.mark.asyncio
async def test_unreadable_camera_extract_ends_with_same_policy() -> None:
    query = "Solve the math in this image"
    with patch("app.modules.math.tools.prompt.extract_math_intent", return_value=None):
        prepared, verified = await augment_prompt_messages(
            _messages(query), query, Settings(math_tools_enabled=True), has_image_attachment=True
        )
    assert verified is None
    assert "Never invent measures" in prepared[-2]["content"]
    assert "then explain carefully" not in prepared[-2]["content"]
    assert prepared[-2]["content"].endswith(MATH_REPLY_POLICY)


_TOOLS = [{"type": "function", "function": {"name": "sympy", "parameters": {"type": "object"}}}]


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_tool_math_guidance_follows_actual_results_before_visible_answer(
    success: bool,
) -> None:
    query = "Solve x+1=3"
    initial = _messages(query)
    tool_content = (
        "Detailed solver work with several intermediate steps"
        if success
        else "Unsupported expression"
    )
    complete = AsyncMock(
        return_value={
            "tool_calls": [
                {
                    "id": "math1",
                    "type": "function",
                    "function": {
                        "name": "sympy",
                        "arguments": '{"action":"solve","lhs":"x+1","rhs":"3"}',
                    },
                }
            ]
        }
    )
    result = ToolResult(
        name="sympy",
        content=tool_content,
        data={"canonical_fence": {"type": "answer", "content": "x=2"}, "canonical_answer": "x=2"}
        if success
        else {},
    )
    with (
        patch("app.modules.chat.tool_loop.rounds._tools_for_user", return_value=_TOOLS),
        patch("app.modules.chat.tool_loop.rounds.litellm_gateway.complete_with_tools", complete),
        patch(
            "app.modules.chat.tool_loop.calls.mcp_registry.invoke_validated",
            AsyncMock(return_value=result),
        ),
    ):
        prepared, verified, _, _ = await run_tool_rounds(
            settings=Settings(mcp_tool_loop_enabled=True, web_search_enabled=False),
            messages=initial,
            usage={},
        )
    complete.assert_awaited_once()
    assert prepared[-2] == {"role": "tool", "tool_call_id": "math1", "content": tool_content}
    assert prepared[-1] == {"role": "system", "content": MATH_REPLY_POLICY}
    assert (verified is not None) is success
    if verified is not None:
        assert verified.canonical_answer == "x=2" and MATH_REPLY_POLICY not in verified.text


@pytest.mark.asyncio
async def test_cancelled_unanswered_math_round_does_not_inject_guidance() -> None:
    initial = _messages("Solve x+1=3")
    cancelled = False

    async def invoke(*_args: object) -> ToolResult:
        nonlocal cancelled
        cancelled = True
        return ToolResult(name="sympy", content="partial")

    complete = AsyncMock(
        return_value={
            "tool_calls": [
                {"id": str(i), "type": "function", "function": {"name": "sympy", "arguments": "{}"}}
                for i in range(2)
            ]
        }
    )
    with (
        patch("app.modules.chat.tool_loop.rounds._tools_for_user", return_value=_TOOLS),
        patch("app.modules.chat.tool_loop.rounds.litellm_gateway.complete_with_tools", complete),
        patch("app.modules.chat.tool_loop.calls.mcp_registry.invoke_validated", side_effect=invoke),
    ):
        prepared, _, _, _ = await run_tool_rounds(
            settings=Settings(mcp_tool_loop_enabled=True, web_search_enabled=False),
            messages=initial,
            usage={},
            should_cancel=lambda: cancelled,
        )
    assert prepared == initial


@pytest.mark.asyncio
async def test_prior_math_tool_call_does_not_add_guidance_to_unrelated_current_turn() -> None:
    initial: list[dict[str, Any]] = [
        {"role": "user", "content": "Solve x+1=3"},
        {"role": "assistant", "tool_calls": [{"id": "old", "function": {"name": "sympy"}}]},
        {"role": "tool", "tool_call_id": "old", "content": "x=2"},
        {"role": "user", "content": "Hello"},
    ]
    with (
        patch("app.modules.chat.tool_loop.rounds._tools_for_user", return_value=_TOOLS),
        patch(
            "app.modules.chat.tool_loop.rounds.litellm_gateway.complete_with_tools",
            AsyncMock(return_value={}),
        ),
    ):
        prepared, _, _, _ = await run_tool_rounds(
            settings=Settings(mcp_tool_loop_enabled=True, web_search_enabled=False),
            messages=initial,
            usage={},
        )
    assert prepared == initial


@pytest.mark.asyncio
async def test_nonmath_augmentation_remains_unchanged() -> None:
    query = "Hello"
    initial = _messages(query)
    prepared, verified = await augment_prompt_messages(
        initial, query, Settings(math_tools_enabled=True)
    )
    assert prepared == initial and verified is None
    assert all(MATH_REPLY_POLICY not in message["content"] for message in prepared)


def test_math_prompts_number_each_move() -> None:
    """A maths reply the model writes numbers its moves, as the verified lesson does.

    The policy states the layout; the maths pack, always closed by the policy, does
    not repeat it (about 460 tokens a maths turn)."""
    prompt = MATH_REPLY_POLICY
    assert MATH_WORKOUT_PROMPT_RULE in prompt
    assert MATH_WORKOUT_PROMPT_RULE not in MATH_INTENT_HINT
    assert "`**1. Subtract 4 from both sides** — Subtraction property of equality`" in prompt
    assert "never a **Steps** heading" in prompt
    assert "`$4x + 4 - 4 = 0 - 4$`, then `$4x = -4$`" in prompt
    assert PHYSICS_WORKOUT_PROMPT_SHORT not in prompt


def test_physics_and_chemistry_keep_the_move_as_a_note() -> None:
    assert "No numbered steps" in WORKOUT_PROMPT_RULE
    assert "`$2x = 8$ — subtract 3 from both sides`" in WORKOUT_PROMPT_RULE
