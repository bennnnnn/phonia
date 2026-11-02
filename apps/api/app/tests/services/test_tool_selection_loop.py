from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways import litellm_gateway
from app.gateways.litellm_gateway import ModelUnavailableError
from app.gateways.mcp import registry as mcp_registry
from app.modules.chat.tool_loop import rounds
from app.tests.tool_context import tool_context


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [0, 300])
async def test_tool_selection_uses_own_budget_and_preserves_visible_cap(budget):
    settings = Settings(mcp_tool_loop_probe_max_tokens=budget, max_output_tokens=8192)
    complete = AsyncMock(return_value={"content": None, "tool_calls": [], "finish_reason": "stop"})
    with patch.object(litellm_gateway, "complete_with_tools", complete):
        await rounds._run_rounds(
            settings=settings,
            messages=[{"role": "user", "content": "Solve this"}],
            usage={},
            tools=[],
            ctx=tool_context(),
            on_status=None,
            should_cancel=None,
        )
    assert complete.await_args.kwargs["max_tokens"] == max(1, budget)
    assert complete.await_args.kwargs["model_alias"] == "gpt-6-luna"
    assert settings.max_output_tokens == 8192


@pytest.mark.asyncio
async def test_truncated_complete_json_never_invokes_a_tool():
    call = {
        "id": "calendar_1",
        "type": "function",
        "function": {"name": "calendar", "arguments": '{"action":"create"}'},
    }
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="length",
                message=SimpleNamespace(content="I have created it", tool_calls=[call]),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=50, completion_tokens=1024),
    )
    usage = {}
    messages = [{"role": "user", "content": "Create an event"}]
    invoke = AsyncMock()
    with (
        patch.object(litellm_gateway, "acompletion", AsyncMock(return_value=response)),
        patch.object(mcp_registry, "invoke_validated", invoke),
    ):
        out, verified, terminal, hits = await rounds._run_rounds(
            settings=Settings(mock_llm_enabled=False, openrouter_api_key="test-only"),
            messages=messages,
            usage=usage,
            tools=[{"type": "function", "function": {"name": "calendar"}}],
            ctx=tool_context(),
            on_status=None,
            should_cancel=None,
        )
    invoke.assert_not_awaited()
    assert out == [*messages, rounds._tool_selection_unavailable_message()]
    # The cut-off decision was asked once more, of the second selector; both bill.
    assert usage == {"input": 100, "output": 2048}
    assert verified is terminal is None
    assert hits == []


@pytest.mark.asyncio
async def test_cancel_after_selection_prevents_invocation_and_failure_context():
    stopped = False

    async def complete(**kwargs):
        nonlocal stopped
        stopped = True
        return {"tool_calls": [{"id": "c", "function": {"name": "calendar"}}]}

    messages = [{"role": "user", "content": "Create an event"}]
    invoke = AsyncMock()
    with (
        patch.object(litellm_gateway, "complete_with_tools", complete),
        patch.object(mcp_registry, "invoke_validated", invoke),
    ):
        out, *_ = await rounds._run_rounds(
            settings=Settings(),
            messages=messages,
            usage={},
            tools=[],
            ctx=tool_context(),
            on_status=None,
            should_cancel=lambda: stopped,
        )
    invoke.assert_not_awaited()
    assert out == messages


def _unavailable(alias: str, *, timed_out: bool = False) -> Exception:
    error = ModelUnavailableError("down", failed_alias=alias)
    if timed_out:
        error.__cause__ = TimeoutError()
    return error


_WEB_SEARCH_CALL = {
    "id": "c1",
    "type": "function",
    "function": {"name": "web_search", "arguments": '{"query": "lisbon weather"}'},
}


async def _select(complete: AsyncMock) -> tuple[list[dict], AsyncMock]:
    messages = [{"role": "user", "content": "weather in lisbon"}]
    invoke = AsyncMock(return_value=SimpleNamespace(name="web_search", content="Sunny", data=None))
    with (
        patch.object(litellm_gateway, "complete_with_tools", complete),
        patch.object(mcp_registry, "invoke_validated", invoke),
    ):
        out, *_ = await rounds._run_rounds(
            settings=Settings(),
            messages=messages,
            usage={},
            tools=[{"type": "function", "function": {"name": "web_search"}}],
            ctx=tool_context(),
            on_status=None,
            should_cancel=None,
        )
    return out, invoke


@pytest.mark.asyncio
async def test_a_failed_tool_selector_is_retried_once_on_the_next():
    """V10.1: GPT-6 Luna's provider fails; the second selector picks the tool."""
    complete = AsyncMock(
        side_effect=[
            _unavailable("gpt-6-luna"),
            {"content": None, "tool_calls": [_WEB_SEARCH_CALL], "finish_reason": "tool_calls"},
        ]
    )
    out, invoke = await _select(complete)
    assert [call.kwargs["model_alias"] for call in complete.await_args_list] == [
        "gpt-6-luna",
        "free-chat",
    ]
    invoke.assert_awaited_once()
    assert rounds._tool_selection_unavailable_message() not in out


@pytest.mark.asyncio
async def test_both_tool_selectors_failing_says_no_actions_were_performed():
    complete = AsyncMock(side_effect=[_unavailable("gpt-6-luna"), RuntimeError("boom")])
    out, invoke = await _select(complete)
    assert complete.await_count == 2
    invoke.assert_not_awaited()
    assert out[-1] == rounds._tool_selection_unavailable_message()


@pytest.mark.asyncio
async def test_a_timed_out_tool_selector_is_not_asked_twice():
    """A timeout spent the selection budget: the reply streams without tools."""
    complete = AsyncMock(side_effect=[_unavailable("gpt-6-luna", timed_out=True)])
    out, invoke = await _select(complete)
    complete.assert_awaited_once()
    invoke.assert_not_awaited()
    assert out[-1] == rounds._tool_selection_unavailable_message()
