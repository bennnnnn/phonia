import asyncio
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.stream_entry import stream_chat_response
from app.tests.fakes import redis_mock
from app.tests.modules.chat.chat_test_support import FakeSessionCM, turn_deps


def _deps(*, load_user, load_chat, list_recent):
    return turn_deps(
        session_factory=FakeSessionCM,
        quota={
            "has_daily_usage_key": AsyncMock(return_value=True),
            "daily_limit_for_user": lambda _user, _settings: 100_000,
        },
        users={"get_by_id": load_user},
        chats={"get_by_id": load_chat},
        messages={"list_recent": list_recent, "count_for_chat": AsyncMock(return_value=0)},
        model_choice={"resolve_user_model_override": lambda *_args, **_kwargs: "free-chat"},
    )


def _held_resources() -> SimpleNamespace:
    return SimpleNamespace(
        reserved_tokens=0,
        refund=AsyncMock(),
        lock_key="lock",
        lock_token="token",
    )


@contextmanager
def _photo_turn(resources: SimpleNamespace) -> Iterator[None]:
    """The lock is held, the previous turn is saved, and a photo answers the turn."""

    @asynccontextmanager
    async def turn_resources(*_args, **_kwargs):
        yield resources

    with (
        patch("app.modules.chat.stream_entry.turn_resources", turn_resources),
        patch("app.modules.chat.turn_load.seed_usage_from_db", AsyncMock()),
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        patch(
            "app.modules.chat.turn_intercepts.try_image_lookup_for_turn",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
    ):
        yield


@pytest.mark.asyncio
async def test_history_load_overlaps_account_and_chat_load() -> None:
    """A remote history read must not sit behind the account/chat DB lane.

    The user lookup waits until list_recent has started. The old serial path
    deadlocks here; the parallel path reaches both lanes and completes.
    """
    history_started = asyncio.Event()

    async def load_user(_session, _user_id):
        await asyncio.wait_for(history_started.wait(), timeout=0.5)
        user = MagicMock()
        user.id = uuid4()
        user.plan = "pro"
        user.timezone = "UTC"
        user.default_model = "free-chat"
        user.memory_enabled = True
        return user

    chat = MagicMock()
    chat.id = uuid4()

    async def load_recent(_session, _chat_id, *, limit):
        _ = limit
        history_started.set()
        await asyncio.sleep(0)
        return []

    resources = _held_resources()
    deps = _deps(
        load_user=load_user, load_chat=AsyncMock(return_value=chat), list_recent=load_recent
    )
    with _photo_turn(resources):
        tokens = [
            token
            async for token in stream_chat_response(
                deps,
                redis_mock(),
                Settings(),
                user_id=uuid4(),
                chat_id=chat.id,
                content="What is the capital of France?",
            )
        ]

    assert tokens == []
    assert history_started.is_set()
    resources.refund.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_and_chat_ownership_loads_overlap() -> None:
    """User and chat DB lookups run concurrently on separate sessions."""
    user_started = asyncio.Event()
    chat_started = asyncio.Event()
    user_id = uuid4()
    chat_id = uuid4()

    user = MagicMock()
    user.id = user_id
    user.plan = "pro"
    user.timezone = "UTC"
    user.default_model = "free-chat"
    user.memory_enabled = True

    chat = MagicMock()
    chat.id = chat_id

    async def load_user(_session, _user_id):
        user_started.set()
        await asyncio.wait_for(chat_started.wait(), timeout=0.5)
        return user

    async def load_chat(_session, _chat_id, _user_id):
        chat_started.set()
        await asyncio.wait_for(user_started.wait(), timeout=0.5)
        return chat

    resources = _held_resources()
    deps = _deps(load_user=load_user, load_chat=load_chat, list_recent=AsyncMock(return_value=[]))
    with _photo_turn(resources):
        tokens = [
            token
            async for token in stream_chat_response(
                deps,
                redis_mock(),
                Settings(),
                user_id=user_id,
                chat_id=chat_id,
                content="hi",
            )
        ]

    assert tokens == []
    assert user_started.is_set()
    assert chat_started.is_set()
    resources.refund.assert_awaited_once()


@pytest.mark.asyncio
# A greeting sees what came before it, so a "hi" after a "hi" is noticed; a short
# reply answers the last turn: "no" to "Understood?" must see it.
@pytest.mark.parametrize("content", ["hi", "thanks", "No", "got it", "yes"])
async def test_every_turn_loads_the_recent_window(
    monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    user = MagicMock()
    user.id = uuid4()
    user.plan = "pro"
    user.timezone = "UTC"
    user.default_model = "free-chat"
    user.memory_enabled = True

    chat = MagicMock()
    chat.id = uuid4()

    prior = MagicMock(role="assistant", content="It's good to act even after a delay. Understood?")
    list_recent = AsyncMock(return_value=[prior])

    deps = _deps(
        load_user=AsyncMock(return_value=user),
        load_chat=AsyncMock(return_value=chat),
        list_recent=list_recent,
    )
    with _photo_turn(_held_resources()):
        tokens = [
            token
            async for token in stream_chat_response(
                deps,
                redis_mock(),
                Settings(),
                user_id=user.id,
                chat_id=chat.id,
                content=content,
            )
        ]

    assert tokens == []
    assert list_recent.await_count == 1
