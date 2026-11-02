"""A next turn must build its context from the committed previous reply."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.exceptions import ChatBusyError
from app.modules.chat import finalize_registry, stream_entry
from app.tests.fakes import redis_mock
from app.tests.modules.chat.chat_test_support import FakeSessionCM, turn_deps


@pytest.mark.asyncio
async def test_next_turn_history_includes_pending_assistant_after_finalize():
    user = MagicMock(id=uuid4(), plan="free")
    chat_id = uuid4()
    chat = MagicMock(project_id=None)
    committed = False
    recent = [
        SimpleNamespace(id=uuid4(), role="user", content="Name a city", model="free-chat"),
        SimpleNamespace(id=uuid4(), role="assistant", content="Paris", model="free-chat"),
    ]

    async def finish_previous_turn(*_args, **_kwargs):
        nonlocal committed
        await asyncio.sleep(0)
        committed = True

    async def read_recent(*_args, **_kwargs):
        return list(recent if committed else recent[:1])

    async def fake_stream(*_args, **_kwargs):
        yield "France"

    prepare = AsyncMock(return_value=MagicMock())
    deps = turn_deps(
        session_factory=FakeSessionCM,
        locks={
            "acquire_lock": AsyncMock(return_value="lock"),
            "refresh_lock": AsyncMock(return_value=True),
            "release_lock": AsyncMock(),
        },
        chats={"get_by_id": AsyncMock(return_value=chat)},
        messages={"list_recent": read_recent},
        quota={"daily_limit_for_user": MagicMock(return_value=100_000)},
        model_choice={"resolve_user_model_override": MagicMock(return_value="free-chat")},
    )
    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", finish_previous_turn),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch("app.modules.chat.turn_resources.reserve_turn_quota", AsyncMock(return_value=100)),
        patch("app.modules.chat.stream_entry.top_up_reserve_for_prompt", AsyncMock()),
        patch("app.modules.chat.stream_entry.prepare_chat_turn", prepare),
        patch("app.modules.chat.stream_entry.await_user_message_persist", AsyncMock()),
        patch("app.modules.chat.stream_entry.stream_and_finalize", fake_stream),
    ):
        tokens = [
            token
            async for token in stream_entry.stream_chat_response(
                deps,
                redis_mock(),
                Settings(_env_file=None),
                user_id=user.id,
                chat_id=chat_id,
                content="Which country is it in?",
                user=user,
                skip_usage_seed=True,
            )
        ]
    assert tokens == ["France"]
    assert prepare.await_args.kwargs["recent_messages"] == recent
    assert prepare.await_args.kwargs["prior_count"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["send", "regenerate"])
@pytest.mark.parametrize("finalize_owner", ["local", "remote"])
async def test_next_turn_rejects_busy_before_reading_uncommitted_history(
    fake_redis, action, finalize_owner
):
    user = MagicMock(id=uuid4(), plan="free")
    chat_id = uuid4()
    gate = asyncio.Event()
    finalize = asyncio.create_task(gate.wait())
    if finalize_owner == "local":
        finalize_registry.register_pending_finalize(chat_id, finalize)
    else:
        await finalize_registry.mark_pending_finalize(fake_redis, chat_id)
    premature_read = AsyncMock(side_effect=AssertionError("read history while finalize is pending"))
    reserve = AsyncMock()
    release = AsyncMock()
    deps = turn_deps(
        session_factory=FakeSessionCM,
        locks={"acquire_lock": AsyncMock(return_value="lock"), "release_lock": release},
        users={"get_by_id": AsyncMock(return_value=user)},
        chats={"get_by_id": AsyncMock(return_value=MagicMock())},
        messages={"list_recent": premature_read},
    )
    try:
        with (
            patch("app.modules.chat.finalize_registry._FINALIZE_WAIT_TIMEOUT_SECONDS", 0.01),
            patch("app.modules.chat.finalize_registry._FINALIZE_POLL_INTERVAL_SECONDS", 0.001),
            patch("app.modules.chat.turn_resources.reserve_turn_quota", reserve),
        ):
            kwargs = {"user_id": user.id, "chat_id": chat_id}
            if action == "send":
                token_stream = stream_entry.stream_chat_response(
                    deps,
                    fake_redis,
                    Settings(_env_file=None),
                    content="next",
                    user=user,
                    skip_usage_seed=True,
                    **kwargs,
                )
            else:
                token_stream = stream_entry.stream_regenerate_response(
                    deps,
                    fake_redis,
                    Settings(_env_file=None),
                    **kwargs,
                )
            with pytest.raises(ChatBusyError):
                _ = [token async for token in token_stream]
            assert not finalize.done()
            premature_read.assert_not_awaited()
            reserve.assert_not_awaited()
            release.assert_awaited_once()
    finally:
        gate.set()
        await finalize
        await finalize_registry.clear_pending_finalize(fake_redis, chat_id)
