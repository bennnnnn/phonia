"""A chat turn's dependencies: the real modules by default, a fake only where a test swaps one."""

import asyncio
from dataclasses import fields
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core import redis_lock
from app.core.config import Settings
from app.core.db import SessionLocal
from app.gateways import litellm_gateway
from app.models.schemas import ChatMessageRequest
from app.modules import todos, web_search
from app.modules.attachments import lifecycle as attachment_lifecycle
from app.modules.attachments import service as attachments_service
from app.modules.billing import plan
from app.modules.chat.model_routing import choice as model_choice
from app.modules.chat.turn_deps import (
    CONVERSATION_CHATS,
    CONVERSATION_MESSAGES,
    ChatTurnDeps,
    default_deps,
)
from app.modules.conversation import history as conversation_history
from app.modules.conversation import service as conversation_service
from app.modules.images import generation as image_generation
from app.modules.images import search as image_search
from app.repositories import usage, users
from app.services import conversation_reference, quota
from app.services.subjects.registry import subject_adapter
from app.tests.fakes import redis_mock
from app.tests.modules.chat.chat_test_support import turn_deps

_REAL_MODULES = {
    "users": users,
    "chats": CONVERSATION_CHATS,
    "messages": CONVERSATION_MESSAGES,
    "usage": usage,
    "quota": quota,
    "plan": plan,
    "model_choice": model_choice,
    "locks": redis_lock,
    "llm": litellm_gateway,
    "image_generation": image_generation,
    "image_search": image_search,
    "attachments": attachment_lifecycle,
    "attachment_links": attachments_service,
    "references": conversation_reference,
    "web_search": web_search,
    "math_fence": subject_adapter("math").fence,
}


def test_default_deps_wire_the_real_modules() -> None:
    deps = default_deps()
    for name, module in _REAL_MODULES.items():
        assert getattr(deps, name) is module, name
    assert deps.session_factory is SessionLocal
    assert deps.todos.materialize_reminder_fences is todos.materialize_reminder_fences
    # A new field gets its wiring checked here too.
    assert {field.name for field in fields(ChatTurnDeps)} == {
        *_REAL_MODULES,
        "session_factory",
        "todos",
    }


def test_a_turn_reads_and_writes_rows_through_conversations_operations() -> None:
    """Conversation's repositories stay private: chat's store is its public operations."""
    assert CONVERSATION_CHATS.peek_recent_chat is conversation_history.peek_recent_chat
    assert CONVERSATION_CHATS.get_by_id is conversation_history.get_chat
    assert CONVERSATION_CHATS.touch_by_id is conversation_service.touch_chat
    assert CONVERSATION_MESSAGES.create is conversation_service.create_message
    assert CONVERSATION_MESSAGES.list_recent is conversation_history.recent_messages
    assert CONVERSATION_MESSAGES.count_for_chat is conversation_history.message_count
    assert CONVERSATION_MESSAGES.get_by_id is conversation_history.message_in_chat
    assert CONVERSATION_MESSAGES.get_last_user is conversation_history.last_user_message
    assert CONVERSATION_MESSAGES.delete_message is conversation_service.delete_message


def test_turn_deps_swaps_only_the_named_function() -> None:
    refund = AsyncMock()
    deps = turn_deps(quota={"refund_usage": refund})
    assert deps.quota.refund_usage is refund
    assert deps.quota.reserve_usage_up_to is quota.reserve_usage_up_to
    assert quota.refund_usage is not refund
    assert deps.messages is CONVERSATION_MESSAGES


def _captured_stream(captured: dict[str, Any]) -> Any:
    async def fake_stream(*args: Any, **_kwargs: Any) -> Any:
        captured["deps"] = args[0]
        return
        yield  # pragma: no cover - an async generator

    return fake_stream


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["stream_chat_response", "stream_regenerate_response"])
async def test_websocket_turns_run_on_the_default_deps(entry: str) -> None:
    from app.modules.chat import ws_api

    captured: dict[str, Any] = {}
    handle = (
        ws_api._handle_message if entry == "stream_chat_response" else ws_api._handle_regenerate
    )
    with patch(f"app.modules.chat.ws_api.stream_entry.{entry}", _captured_stream(captured)):
        await handle(
            AsyncMock(),
            redis=redis_mock(),
            settings=Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            payload={"type": "message", "content": "hi"},
            client_timezone=None,
            cancel_event=asyncio.Event(),
            emit_status=AsyncMock(),
            emit_reasoning=AsyncMock(),
        )
    assert captured["deps"] == default_deps()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["stream_chat_response", "stream_regenerate_response"])
async def test_sse_turns_run_on_the_default_deps(entry: str) -> None:
    from app.modules.chat import stream_api

    captured: dict[str, Any] = {}
    route = (
        stream_api.stream_message_sse
        if entry == "stream_chat_response"
        else stream_api.stream_regenerate_sse
    )
    request = AsyncMock()
    request.is_disconnected = AsyncMock(return_value=False)
    with patch(f"app.modules.chat.stream_api.stream_entry.{entry}", _captured_stream(captured)):
        response = await route(
            chat_id=uuid4(),
            body=ChatMessageRequest(content="hi"),
            request=request,
            user=MagicMock(id=uuid4()),
            settings=Settings(),
            redis=redis_mock(),
        )
        async for _ in response.body_iterator:
            pass
    assert captured["deps"] == default_deps()
