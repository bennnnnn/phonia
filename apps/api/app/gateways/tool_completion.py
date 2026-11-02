"""Tool-only selection round before the visible stream.

The model must return a complete decision — tool calls with valid JSON
arguments, or the explicit no-tool call alone — before any tool runs. Provider
calls go through ``litellm_gateway``, which re-exports this module, so it is
imported at call time.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from app.core.config import Settings
from app.gateways import mock_llm
from app.gateways.stream_usage import apply_usage

logger = logging.getLogger(__name__)


def _tool_calls_to_jsonable(tool_calls: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for call in tool_calls:
        if isinstance(call, dict):
            out.append(call)
            continue
        fn = getattr(call, "function", None)
        out.append(
            {
                "id": getattr(call, "id", None) or "",
                "type": getattr(call, "type", None) or "function",
                "function": {
                    "name": getattr(fn, "name", None) or "",
                    "arguments": getattr(fn, "arguments", None),
                },
            }
        )
    return out


NO_TOOL_NAME = "recall_no_tool_needed"
_NO_TOOL = {
    "type": "function",
    "function": {
        "name": NO_TOOL_NAME,
        "description": "Select this alone when no available tool is needed for the current turn.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}
_TOOL_SELECTION_INSTRUCTION = (
    "Select tools for the current user request. Do not answer the user or write prose. "
    "Return only the necessary tool calls with complete arguments. "
    f"If no available tool is needed, call {NO_TOOL_NAME} alone with {{}}. "
    "Never combine that decision with another call. Do not invent missing information "
    "or bypass the existing rules for permission and tool use."
)


def _tool_choice_unsupported(exc: Exception) -> bool:
    """Retry only an explicit parameter rejection, never an ambiguous outage."""
    message = str(exc).lower()
    return (
        getattr(exc, "status_code", None) in (400, 422)
        and "tool_choice" in message
        and any(term in message for term in ("unsupported", "not supported", "does not support"))
    )


async def _await_tool_selection(
    completion: Awaitable[Any], should_cancel: Callable[[], bool] | None
) -> Any:
    if should_cancel is None:
        return await completion
    task = asyncio.ensure_future(completion)
    try:
        while True:
            if should_cancel():
                raise asyncio.CancelledError
            done, _ = await asyncio.wait({task}, timeout=0.1)
            if done:
                return task.result()
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task


def _tool_selection_result(
    response: Any, *, tools: list[dict[str, Any]], model_alias: str
) -> dict[str, Any]:
    """Accept a complete decision before exposing any call to the service."""
    from app.gateways import litellm_gateway as gateway

    invalid = gateway.ModelUnavailableError.for_alias(model_alias, code="tool_selection_incomplete")
    choices = getattr(response, "choices", None) or []
    if not choices or getattr(choices[0], "finish_reason", None) not in ("tool_calls", "stop"):
        # Even valid JSON can be a truncated prefix of a multi-call response.
        raise invalid
    message = getattr(choices[0], "message", None)
    calls = _tool_calls_to_jsonable(list(getattr(message, "tool_calls", None) or []))
    if not calls:
        # Prose is not evidence that no tool was needed, even in auto fallback.
        raise invalid
    allowed = {tool["function"]["name"] for tool in tools} | {NO_TOOL_NAME}
    ids: set[str] = set()
    no_tool = False
    for call in calls:
        function = call.get("function")
        if not isinstance(function, dict):
            raise invalid
        name, arguments, call_id = function.get("name"), function.get("arguments"), call.get("id")
        if (
            call.get("type") != "function"
            or not isinstance(name, str)
            or name not in allowed
            or not isinstance(call_id, str)
            or not call_id.strip()
            or call_id in ids
            or not isinstance(arguments, str)
        ):
            raise invalid
        try:
            parsed = json.loads(arguments)
        except (ValueError, TypeError) as exc:
            raise invalid from exc
        if not isinstance(parsed, dict):
            raise invalid
        ids.add(call_id)
        if name == NO_TOOL_NAME:
            if len(calls) != 1 or parsed:
                raise invalid
            no_tool = True
    # Selection prose/reasoning is neither an answer nor useful tool context.
    return {
        "content": None,
        "tool_calls": [] if no_tool else calls,
        "finish_reason": choices[0].finish_reason,
    }


async def complete_with_tools(
    *,
    settings: Settings,
    model_alias: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int,
    usage: dict[str, int] | None = None,
    timeout_seconds: float = 30.0,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Compact tool-only selection; retain the final response and its usage."""
    from app.gateways import litellm_gateway as gateway

    if should_cancel and should_cancel():
        raise asyncio.CancelledError
    if mock_llm.should_mock_llm(settings):
        result = await mock_llm.mock_complete_with_tools(messages=messages, tools=tools)
        return {**result, "content": None, "finish_reason": "stop"}

    route = gateway.resolve_route(model_alias)
    kwargs = gateway._litellm_kwargs(settings, route, latency_sensitive=True, thinking=False)
    if route.model.startswith("openrouter/"):
        # Otherwise OpenRouter may silently ignore an unsupported tool_choice.
        kwargs["extra_body"]["provider"]["require_parameters"] = True
    selection_messages = [
        *messages,
        {"role": "system", "content": _TOOL_SELECTION_INSTRUCTION},
    ]
    try:
        # An explicit unsupported-parameter retry shares this entire deadline.
        async with asyncio.timeout(timeout_seconds):
            for tool_choice in ("required", "auto"):
                try:
                    response = await _await_tool_selection(
                        gateway.acompletion(
                            model=route.model,
                            messages=selection_messages,
                            tools=[*tools, _NO_TOOL],
                            tool_choice=tool_choice,
                            max_tokens=max_tokens,
                            stream=False,
                            **kwargs,
                        ),
                        should_cancel,
                    )
                except Exception as exc:
                    if tool_choice == "required" and _tool_choice_unsupported(exc):
                        logger.info(
                            "Tool choice required unsupported alias=%s; retrying auto", model_alias
                        )
                        continue
                    raise
                # Apply once, including a completed but rejected/truncated
                # decision. No early abort means no lost usage-only trailer.
                apply_usage(usage, response)
                return _tool_selection_result(response, tools=tools, model_alias=model_alias)
    except TimeoutError as exc:
        raise gateway.ModelUnavailableError.for_alias(model_alias) from exc
    except gateway.ModelUnavailableError:
        raise
    except Exception as exc:
        logger.warning(
            "complete_with_tools failed alias=%s type=%s", model_alias, type(exc).__name__
        )
        raise gateway.ModelUnavailableError.for_alias(model_alias) from exc

    raise gateway.ModelUnavailableError.for_alias(model_alias)
