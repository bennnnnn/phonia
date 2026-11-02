"""The pre-stream selector must finish a tool decision before any invocation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.gateways import litellm_gateway as gateway
from app.gateways import tool_completion
from app.gateways.tool_completion import NO_TOOL_NAME

TOOLS = [{"type": "function", "function": {"name": "calendar", "parameters": {}}}]
MESSAGES = [{"role": "user", "content": "Add lunch tomorrow at noon"}]


def _call(name="calendar", arguments='{"action":"create"}', call_id="call_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _response(calls, *, finish_reason="tool_calls", content=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(
                    content=content, reasoning_content="private reasoning", tool_calls=calls
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=17, completion_tokens=9),
    )


async def _complete(**kwargs):
    return await gateway.complete_with_tools(
        settings=Settings(mock_llm_enabled=False, openrouter_api_key="test-only"),
        model_alias="free-chat",
        messages=MESSAGES,
        tools=TOOLS,
        max_tokens=1024,
        **kwargs,
    )


def _asyncio_with(timeout: MagicMock) -> SimpleNamespace:
    """asyncio as tool_completion sees it, with ``timeout`` recorded there alone."""
    names = {name: getattr(asyncio, name) for name in dir(asyncio) if not name.startswith("_")}
    return SimpleNamespace(**{**names, "timeout": timeout})


@pytest.mark.asyncio
async def test_selector_requires_explicit_no_tool_decision_and_retains_usage():
    usage = {"input": 10, "output": 20}
    complete = AsyncMock(return_value=_response([_call(NO_TOOL_NAME, "{}")]))
    timeout = MagicMock(wraps=asyncio.timeout)
    with (
        patch.object(gateway, "acompletion", complete),
        patch.object(tool_completion, "asyncio", _asyncio_with(timeout)),
    ):
        result = await _complete(usage=usage)

    assert result == {"content": None, "tool_calls": [], "finish_reason": "tool_calls"}
    assert usage == {"input": 27, "output": 29}
    request = complete.await_args.kwargs
    assert request["tool_choice"] == "required"
    assert request["stream"] is False
    assert request["max_tokens"] == 1024
    assert request["extra_body"]["provider"] == {"sort": "latency", "require_parameters": True}
    assert request["tools"][:-1] == TOOLS
    assert request["tools"][-1]["function"]["name"] == NO_TOOL_NAME
    assert request["messages"][:-1] == MESSAGES
    assert len(MESSAGES) == len(TOOLS) == 1
    timeout.assert_called_once_with(30.0)


@pytest.mark.asyncio
async def test_selector_preserves_calls_after_prose_and_discards_all_reasoning():
    calls = [_call(), _call(arguments='{"action":"list"}', call_id="call_2")]
    response = _response(calls, content="<think>secret</think>I'll check the calendar.")
    with patch.object(gateway, "acompletion", AsyncMock(return_value=response)):
        result = await _complete()
    assert result["content"] is None
    assert result["tool_calls"] == calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("calls", "finish_reason"),
    [
        ([_call()], "length"),  # Valid JSON is still an incomplete decision.
        ([_call()], "content_filter"),
        ([_call()], None),
        ([], "stop"),  # Prose cannot replace the no-tool sentinel.
        ([_call(arguments='{"action":')], "tool_calls"),
        ([_call(arguments=None)], "tool_calls"),
        ([_call(arguments="[]")], "tool_calls"),
        ([_call(call_id="")], "tool_calls"),
        ([_call(), _call()], "tool_calls"),
        ([_call(name="not_offered")], "tool_calls"),
        ([_call(NO_TOOL_NAME, "{}"), _call(call_id="real")], "tool_calls"),
        ([_call(NO_TOOL_NAME, '{"explanation":"no"}')], "tool_calls"),
    ],
)
async def test_selector_rejects_incomplete_or_ambiguous_decision(calls, finish_reason):
    usage = {}
    complete = AsyncMock(return_value=_response(calls, finish_reason=finish_reason, content="Hi"))
    with patch.object(gateway, "acompletion", complete):
        with pytest.raises(gateway.ModelUnavailableError) as error:
            await _complete(usage=usage)
    assert error.value.code == "tool_selection_incomplete"
    assert usage == {"input": 17, "output": 9}
    complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_selector_handles_litellm_objects_without_defaulting_missing_arguments():
    call = SimpleNamespace(
        id="object_call", type="function", function=SimpleNamespace(name="calendar", arguments="{}")
    )
    with patch.object(gateway, "acompletion", AsyncMock(return_value=_response([call]))):
        result = await _complete()
    assert result["tool_calls"] == [_call(arguments="{}", call_id="object_call")]
    call.function.arguments = None
    with patch.object(gateway, "acompletion", AsyncMock(return_value=_response([call]))):
        with pytest.raises(gateway.ModelUnavailableError):
            await _complete()


class UnsupportedToolChoice(Exception):
    status_code = 400


@pytest.mark.asyncio
async def test_selector_retries_only_explicit_unsupported_choice_with_same_contract():
    complete = AsyncMock(
        side_effect=[
            UnsupportedToolChoice("tool_choice required is not supported"),
            _response([_call(NO_TOOL_NAME, "{}")]),
        ]
    )
    usage = {}
    timeout = MagicMock(wraps=asyncio.timeout)
    with (
        patch.object(gateway, "acompletion", complete),
        patch.object(tool_completion, "asyncio", _asyncio_with(timeout)),
    ):
        result = await _complete(usage=usage)
    first, second = [call.kwargs for call in complete.await_args_list]
    assert first == {**second, "tool_choice": "required"}
    assert second["tool_choice"] == "auto"
    assert result["tool_calls"] == []
    assert usage == {"input": 17, "output": 9}
    timeout.assert_called_once_with(30.0)


@pytest.mark.asyncio
async def test_auto_compatibility_response_still_requires_explicit_decision():
    complete = AsyncMock(
        side_effect=[
            UnsupportedToolChoice("tool_choice unsupported"),
            _response([], finish_reason="stop", content="I did it."),
        ]
    )
    with patch.object(gateway, "acompletion", complete):
        with pytest.raises(gateway.ModelUnavailableError):
            await _complete()
    assert complete.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [RuntimeError("provider down"), UnsupportedToolChoice("invalid request"), TimeoutError()],
)
async def test_selector_does_not_retry_provider_errors(error):
    complete = AsyncMock(side_effect=error)
    with patch.object(gateway, "acompletion", complete):
        with pytest.raises(gateway.ModelUnavailableError):
            await _complete()
    complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_selector_timeout_cancels_pending_provider_request():
    cancelled = asyncio.Event()

    async def blocked(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    complete = AsyncMock(side_effect=blocked)
    with patch.object(gateway, "acompletion", complete):
        with pytest.raises(gateway.ModelUnavailableError):
            await _complete(timeout_seconds=0.01, should_cancel=lambda: False)
    assert cancelled.is_set()
    complete.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("soft", [False, True])
async def test_selector_cancellation_stops_provider_and_propagates(soft):
    started, cancelled, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def blocked(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with patch.object(gateway, "acompletion", AsyncMock(side_effect=blocked)):
        task = asyncio.create_task(_complete(should_cancel=stop.is_set))
        await started.wait()
        if soft:
            stop.set()
        else:
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
    assert cancelled.is_set()
