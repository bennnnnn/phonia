"""Quota edge cases on the chat stream path (Kimi Mediums)."""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat import stream_entry
from app.modules.chat.turn_resources import TurnResources
from app.modules.conversation import chats_repository, messages_repository
from app.tests.fakes import FakeSessionCM, redis_mock
from app.tests.modules.chat.chat_test_support import FakeSessionCM as _FakeSessionCM
from app.tests.modules.chat.chat_test_support import turn_deps


def _pro_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.default_model = "smart-chat"
    user.plan = "pro"
    return user


@contextmanager
def _turn_load():
    chat = MagicMock()
    chat.summary = None
    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=chat)),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[])),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=0)),
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
    ):
        yield


def _deps(**fields):
    """A Pro user on smart-chat with the default daily limit; sessions offline."""
    quota = {"daily_limit_for_user": MagicMock(return_value=100_000), **fields.pop("quota", {})}
    return turn_deps(
        session_factory=_FakeSessionCM,
        model_choice={"resolve_user_model_override": MagicMock(return_value="smart-chat")},
        quota=quota,
        **fields,
    )


def _held_lock():
    """This turn owns its own lock + reservation (the plain message path)."""
    return {"acquire_lock": AsyncMock(return_value="tok"), "release_lock": AsyncMock()}


def _borrowed_resources(deps, redis, user_id, chat_id, reserved: int) -> TurnResources:
    """Resources already held by an outer turn (what regenerate hands down)."""
    return TurnResources(
        deps=deps,
        redis=redis,
        user_id=user_id,
        chat_id=chat_id,
        lock_key=f"chatprep:{chat_id}",
        lock_token="test-token",
        reserved_tokens=reserved,
    )


@pytest.mark.asyncio
async def test_stream_chat_response_refunds_pre_reserved_on_image_gen():
    """Edit reserves before stream_chat_response; image-gen must refund that hold."""
    user = _pro_user()
    chat_id = uuid4()
    redis = redis_mock()
    refund = AsyncMock()
    deps = _deps(quota={"refund_usage": refund})

    with (
        _turn_load(),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=True),
        ),
    ):
        tokens = [
            t
            async for t in stream_entry.stream_chat_response(
                deps,
                redis,
                Settings(),
                user_id=user.id,
                chat_id=chat_id,
                content="draw a cat",
                resources=_borrowed_resources(deps, redis, user.id, chat_id, 500),
                user=user,
                skip_usage_seed=True,
            )
        ]

    assert tokens == []
    refund.assert_awaited_once_with(redis, str(user.id), 500)


@pytest.mark.asyncio
async def test_stream_chat_response_refunds_on_cancelled_error():
    """Hard cancel (CancelledError) must refund — except Exception would miss it."""
    user = _pro_user()
    redis = redis_mock()
    refund = AsyncMock()

    async def boom_stream(*_a, **_k):
        raise asyncio.CancelledError()
        yield  # pragma: no cover — make this an async generator

    deps = _deps(quota={"refund_usage": refund}, locks=_held_lock())
    with (
        _turn_load(),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.chat.stream_entry.prepare_chat_turn",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("app.modules.chat.stream_entry.stream_and_finalize", boom_stream),
        patch("app.modules.chat.turn_resources.reserve_turn_quota", AsyncMock(return_value=250)),
    ):
        with pytest.raises(asyncio.CancelledError):
            async for _ in stream_entry.stream_chat_response(
                deps,
                redis,
                Settings(),
                user_id=user.id,
                chat_id=uuid4(),
                content="hi",
                user=user,
                skip_usage_seed=True,
            ):
                pass

    refund.assert_awaited_once_with(redis, str(user.id), 250)


@pytest.mark.asyncio
async def test_stream_chat_response_reserves_max_output_ceiling():
    user = _pro_user()
    redis = redis_mock()
    reserve = AsyncMock(return_value=3400)

    async def empty_stream(*_a, **_k):
        if False:
            yield ""

    with (
        _turn_load(),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.chat.stream_entry.prepare_chat_turn",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("app.modules.chat.stream_entry.stream_and_finalize", empty_stream),
        patch("app.modules.chat.turn_resources.reserve_turn_quota", reserve),
    ):
        async for _ in stream_entry.stream_chat_response(
            _deps(locks=_held_lock()),
            redis,
            Settings(max_output_tokens=1200),
            user_id=user.id,
            chat_id=uuid4(),
            content="hi",
            user=user,
            skip_usage_seed=True,
        ):
            pass

    # No style-based cap: reserve against the single ceiling (settings.max_output_tokens).
    assert reserve.await_args.kwargs["max_output"] == 1200


@pytest.mark.asyncio
async def test_prior_count_uses_recent_length_when_window_has_room():
    from app.modules.chat.turn_load import _prior_count_for_window

    count = AsyncMock(return_value=99)
    recent = [MagicMock(), MagicMock()]
    n = await _prior_count_for_window(
        recent,
        window=20,
        count_for_chat=count,
        session=AsyncMock(),
        chat_id=uuid4(),
    )
    assert n == 2
    count.assert_not_awaited()


@pytest.mark.asyncio
async def test_prior_count_queries_when_recent_window_is_full():
    from app.modules.chat.turn_load import _prior_count_for_window

    count = AsyncMock(return_value=40)
    recent = [MagicMock(), MagicMock()]
    n = await _prior_count_for_window(
        recent,
        window=2,
        count_for_chat=count,
        session=AsyncMock(),
        chat_id=uuid4(),
    )
    assert n == 40
    count.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_skips_count_when_recent_window_has_room():
    user = _pro_user()
    redis = redis_mock()
    count = AsyncMock(return_value=99)

    async def fake_stream(*_a, **_k):
        yield "ok"

    chat = MagicMock()
    chat.summary = None
    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=chat)),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[MagicMock()])),
        patch.object(messages_repository, "count_for_chat", count),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.chat.stream_entry.prepare_chat_turn", AsyncMock(return_value=MagicMock())
        ),
        patch("app.modules.chat.stream_entry.stream_and_finalize", fake_stream),
        patch("app.modules.chat.turn_resources.reserve_turn_quota", AsyncMock(return_value=100)),
    ):
        async for _ in stream_entry.stream_chat_response(
            _deps(locks=_held_lock()),
            redis,
            Settings(),
            user_id=user.id,
            chat_id=uuid4(),
            content="hi",
            user=user,
            skip_usage_seed=True,
        ):
            pass

    count.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_counts_when_recent_window_is_full():
    user = _pro_user()
    redis = redis_mock()
    count = AsyncMock(return_value=40)

    async def fake_stream(*_a, **_k):
        yield "ok"

    chat = MagicMock()
    chat.summary = None
    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=chat)),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[MagicMock(), MagicMock()]),
        ),
        patch.object(messages_repository, "count_for_chat", count),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.chat.stream_entry.prepare_chat_turn", AsyncMock(return_value=MagicMock())
        ),
        patch("app.modules.chat.stream_entry.stream_and_finalize", fake_stream),
        patch("app.modules.chat.turn_resources.reserve_turn_quota", AsyncMock(return_value=100)),
    ):
        async for _ in stream_entry.stream_chat_response(
            _deps(locks=_held_lock()),
            redis,
            Settings(recent_message_window=2),
            user_id=user.id,
            chat_id=uuid4(),
            content="What is the capital of France?",
            user=user,
            skip_usage_seed=True,
        ):
            pass

    count.assert_awaited_once()


# ── chat service: quota guard ──────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("used", [100, 101], ids=["at-limit", "over-limit"])
async def test_stream_chat_response_quota_exceeded(fake_redis, used: int) -> None:
    from app.exceptions import QuotaExceededError
    from app.modules import chat as chat_service
    from app.services import quota as quota_service

    user_id = uuid4()
    await fake_redis.set(f"usage:{user_id}:{quota_service.utc_today().isoformat()}", used)
    settings = Settings(daily_token_limit=100)
    fake_user = MagicMock(id=user_id, plan="free", default_model="free-chat")
    # Fail immediately if the guard lets message persistence begin.
    prepare = AsyncMock(side_effect=AssertionError("Over-limit turn reached preparation"))
    deps = turn_deps(
        session_factory=lambda: FakeSessionCM(),
        chats={"get_by_id": AsyncMock(return_value=MagicMock(summary=None))},
        messages={"list_recent": AsyncMock(return_value=[])},
    )
    with (
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        patch("app.modules.chat.stream_entry.prepare_chat_turn", prepare),
    ):
        with pytest.raises(QuotaExceededError):
            async for _t in chat_service.stream_chat_response(
                deps,
                fake_redis,
                settings,
                user_id=user_id,
                chat_id=uuid4(),
                content="hi",
            ):
                pass

    # Refused without a charge: the counter is where it was.
    assert await quota_service.get_daily_usage(fake_redis, str(user_id)) == used
    prepare.assert_not_awaited()
