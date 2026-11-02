"""Per-chat Redis prepare/turn lock on stream_chat_response / regenerate."""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core import redis_lock
from app.core.config import Settings
from app.exceptions import ChatBusyError
from app.modules.chat import stream_entry, turn_resources
from app.modules.chat.model_routing import choice as model_choice
from app.modules.chat.stream_events import error_payload_for_exception
from app.modules.conversation import chats_repository, messages_repository
from app.tests.fakes import redis_mock
from app.tests.modules.chat.chat_test_support import FakeSessionCM as _FakeSessionCM
from app.tests.modules.chat.chat_test_support import turn_deps

pytest_plugins = ("app.tests.modules.chat.chat_test_support",)


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.default_model = "free-chat"
    user.plan = "free"
    return user


def _chat() -> MagicMock:
    chat = MagicMock()
    chat.summary = None
    return chat


@contextmanager
def _turn_load():
    chat = _chat()
    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=chat)),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[])),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=0)),
    ):
        yield


def _held_lock_deps(*, acquire, release, refresh=None, **fields):
    """The prepare lock's Redis calls swapped; the turn's own sessions offline."""
    locks = {"acquire_lock": acquire, "release_lock": release}
    if refresh is not None:
        locks["refresh_lock"] = refresh
    return turn_deps(locks=locks, **fields)


def _plan_and_quota():
    return {
        "model_choice": {"resolve_user_model_override": MagicMock(return_value="free-chat")},
        "quota": {"daily_limit_for_user": MagicMock(return_value=100_000)},
    }


@pytest.mark.asyncio
async def test_stream_chat_acquire_fail_skips_prepare_and_raises_busy():
    user = _user()
    redis = redis_mock()
    prepare = AsyncMock()
    wait = AsyncMock()
    release = AsyncMock()
    refund = AsyncMock()
    acquire = AsyncMock(return_value=None)
    deps = _held_lock_deps(acquire=acquire, release=release, quota={"refund_usage": refund})

    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", wait),
        patch("app.modules.chat.stream_entry.prepare_chat_turn", prepare),
    ):
        with pytest.raises(ChatBusyError):
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

    acquire.assert_awaited_once()
    key = acquire.await_args.args[1]
    assert key.startswith("chatprep:")
    assert acquire.await_args.args[2] == turn_resources.CHATPREP_LOCK_TTL_SECONDS
    wait.assert_not_awaited()
    prepare.assert_not_awaited()
    release.assert_not_awaited()
    # Quota is reserved inside the turn_resources block, i.e. only after the
    # lock is held — a busy chat cannot have reserved anything to leak.
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_chat_releases_lock_on_success():
    user = _user()
    redis = redis_mock()
    chat_id = uuid4()
    release = AsyncMock()

    async def fake_stream(*_a, **_k):
        yield "ok"

    acquire = AsyncMock(return_value="tok")
    deps = _held_lock_deps(
        acquire=acquire, release=release, session_factory=_FakeSessionCM, **_plan_and_quota()
    )
    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        _turn_load(),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.chat.stream_entry.prepare_chat_turn",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("app.modules.chat.stream_entry.stream_and_finalize", fake_stream),
        patch("app.modules.chat.turn_resources.reserve_turn_quota", AsyncMock(return_value=100)),
    ):
        tokens = [
            t
            async for t in stream_entry.stream_chat_response(
                deps,
                redis,
                Settings(),
                user_id=user.id,
                chat_id=chat_id,
                content="hi",
                user=user,
                skip_usage_seed=True,
            )
        ]

    assert tokens == ["ok"]
    acquire.assert_awaited_once_with(
        redis, f"chatprep:{chat_id}", turn_resources.CHATPREP_LOCK_TTL_SECONDS
    )
    release.assert_awaited_once_with(redis, f"chatprep:{chat_id}", "tok")


@pytest.mark.asyncio
async def test_stream_chat_releases_lock_when_prepare_fails():
    user = _user()
    redis = redis_mock()
    chat_id = uuid4()
    release = AsyncMock()
    refund = AsyncMock()
    fields = _plan_and_quota()
    fields["quota"]["refund_usage"] = refund
    deps = _held_lock_deps(
        acquire=AsyncMock(return_value="tok"),
        release=release,
        session_factory=_FakeSessionCM,
        **fields,
    )

    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        _turn_load(),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.chat.stream_entry.prepare_chat_turn",
            AsyncMock(side_effect=RuntimeError("prepare boom")),
        ),
        patch("app.modules.chat.turn_resources.reserve_turn_quota", AsyncMock(return_value=100)),
    ):
        with pytest.raises(RuntimeError, match="prepare boom"):
            async for _ in stream_entry.stream_chat_response(
                deps,
                redis,
                Settings(),
                user_id=user.id,
                chat_id=chat_id,
                content="hi",
                user=user,
                skip_usage_seed=True,
            ):
                pass

    release.assert_awaited_once_with(redis, f"chatprep:{chat_id}", "tok")
    refund.assert_awaited_once()


@pytest.mark.asyncio
async def test_regenerate_acquires_chatprep_lock():
    user = _user()
    redis = redis_mock()
    chat_id = uuid4()
    release = AsyncMock()

    fake_chat = MagicMock()
    fake_last = MagicMock()
    fake_last.role = "assistant"
    fake_last.id = uuid4()
    fake_last.content = "prior"
    fake_last.model = "free-chat"
    fake_last_user = MagicMock()
    fake_last_user.role = "user"
    fake_last_user.content = "question"

    async def fake_stream(*_a, **_k):
        yield "regen"

    acquire = AsyncMock(return_value="tok")
    deps = _held_lock_deps(acquire=acquire, release=release, session_factory=_FakeSessionCM)
    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[fake_last_user, fake_last]),
        ),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=2)),
        patch.object(
            model_choice,
            "resolve_user_model_override",
            return_value="free-chat",
        ),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.chat.stream_entry.build_stream_prompt_context",
            AsyncMock(
                return_value=MagicMock(
                    max_out=100,
                    prompt_messages=[],
                    instant_reply=None,
                    search_sources=[],
                    local_places=False,
                    fallback_models=[],
                    geo=MagicMock(),
                    local_tz="UTC",
                    verified_subject=None,
                )
            ),
        ),
        patch(
            "app.modules.chat.turn_resources.reserve_turn_quota",
            AsyncMock(return_value=50),
        ),
        patch(
            "app.modules.chat.stream_entry.stream_context_from_bundle",
            MagicMock(return_value=MagicMock()),
        ),
        patch("app.modules.chat.stream_entry.stream_and_finalize", fake_stream),
    ):
        tokens = [
            t
            async for t in stream_entry.stream_regenerate_response(
                deps,
                redis,
                Settings(),
                user_id=user.id,
                chat_id=chat_id,
            )
        ]

    assert tokens == ["regen"]
    acquire.assert_awaited_once_with(
        redis, f"chatprep:{chat_id}", turn_resources.CHATPREP_LOCK_TTL_SECONDS
    )
    release.assert_awaited_once_with(redis, f"chatprep:{chat_id}", "tok")


def test_chat_busy_error_maps_to_busy_code():
    payload = error_payload_for_exception(ChatBusyError())
    assert payload == {
        "type": "error",
        "code": "busy",
        "message": "Still generating — wait or cancel first.",
    }


@pytest.mark.asyncio
async def test_turn_resources_refreshes_lock_while_held():
    redis = redis_mock()
    refresh = AsyncMock()
    release = AsyncMock()

    deps = _held_lock_deps(acquire=AsyncMock(return_value="tok"), release=release, refresh=refresh)
    with patch.object(turn_resources, "CHATPREP_LOCK_REFRESH_INTERVAL_SECONDS", 0.05):
        async with turn_resources.turn_resources(deps, redis, user_id=uuid4(), chat_id=uuid4()):
            # Wait for the refreshes rather than a fixed sleep, so a busy CI runner
            # that delays the refresh task does not fail the test.
            for _ in range(100):
                if refresh.await_count >= 2:
                    break
                await asyncio.sleep(0.02)

    assert refresh.await_count >= 2
    release.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_loop_survives_redis_errors_and_a_lost_lock():
    """The loop used to die on its first Redis exception, so one blip ended the
    lock's heartbeat for the rest of the turn."""
    redis = redis_mock()
    refresh = AsyncMock(
        side_effect=[RedisConnectionError("blip"), False, RedisTimeoutError("slow"), True, True]
    )
    deps = _held_lock_deps(
        acquire=AsyncMock(return_value="tok"), release=AsyncMock(), refresh=refresh
    )
    with patch.object(turn_resources, "CHATPREP_LOCK_REFRESH_INTERVAL_SECONDS", 0.01):
        async with turn_resources.turn_resources(deps, redis, user_id=uuid4(), chat_id=uuid4()):
            for _ in range(200):
                if refresh.await_count >= 4:
                    break
                await asyncio.sleep(0.01)

    assert refresh.await_count >= 4


@pytest.mark.asyncio
async def test_lock_redis_errors_never_cut_the_stream_or_skip_its_save(stream_offline_io):
    """Regression: a refresh error mid-stream closed stream_and_finalize at a yield
    (the reply the phone saw was never saved), and a release error turned a saved
    turn into an error frame with no ``done``."""
    from app.modules.chat.turn_outcome import TurnOutcome
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**_kwargs):
        for index in range(5):
            yield f"tok{index} "
            await asyncio.sleep(0.01)

    finalize = AsyncMock()
    refresh = AsyncMock(side_effect=RedisConnectionError("Upstash blip"))
    release = AsyncMock(side_effect=RedisConnectionError("Upstash blip"))
    deps = turn_deps(
        session_factory=_FakeSessionCM,
        locks={
            "acquire_lock": AsyncMock(return_value="tok"),
            "refresh_lock": refresh,
            "release_lock": redis_lock.release_lock,
        },
    )
    redis = redis_mock()
    redis.eval = release
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=0,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )
    outcome = TurnOutcome()
    with (
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)),
        patch("app.services.model_health.record_samples", AsyncMock()),
        patch.object(turn_resources, "CHATPREP_LOCK_REFRESH_INTERVAL_SECONDS", 0.005),
    ):
        async with turn_resources.turn_resources(
            deps, redis, user_id=ctx.user_id, chat_id=ctx.chat_id
        ) as res:
            tokens = [
                token
                async for token in stream_entry.stream_and_finalize(
                    deps,
                    redis,
                    Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
                    ctx,
                    should_cancel=None,
                    outcome=outcome,
                    resources=res,
                )
            ]
        assert outcome.finalize_db_task is not None
        await outcome.finalize_db_task

    assert tokens == [f"tok{index} " for index in range(5)]
    assert refresh.await_count >= 1
    release.assert_awaited()
    finalize.assert_awaited_once()
    assert outcome.message_id is not None


@pytest.mark.asyncio
async def test_a_turn_handed_to_finalize_is_not_refunded_on_a_later_escape(stream_offline_io):
    """Finalize settles the reservation (actual usage, or its own refund). An
    exception escaping turn_resources afterwards must not refund it a second time."""
    from app.modules.chat.turn_outcome import TurnOutcome
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**_kwargs):
        yield "reply"

    refund = AsyncMock()
    deps = turn_deps(
        session_factory=_FakeSessionCM,
        locks={"acquire_lock": AsyncMock(return_value="tok"), "release_lock": AsyncMock()},
        quota={"refund_usage": refund},
    )
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=500,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )
    with (
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", AsyncMock()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)),
        patch("app.services.model_health.record_samples", AsyncMock()),
    ):
        with pytest.raises(RuntimeError, match="after the save"):
            async with turn_resources.turn_resources(
                deps, AsyncMock(), user_id=ctx.user_id, chat_id=ctx.chat_id
            ) as res:
                res.reserved_tokens = 500
                async for _ in stream_entry.stream_and_finalize(
                    deps,
                    AsyncMock(),
                    Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
                    ctx,
                    should_cancel=None,
                    outcome=TurnOutcome(),
                    resources=res,
                ):
                    pass
                raise RuntimeError("after the save")

    refund.assert_not_awaited()


@pytest.mark.parametrize("borrowed", [True, False])
@pytest.mark.asyncio
async def test_turn_resources_refreshes_only_a_lock_it_took(borrowed):
    """A borrowed lock is the outer turn's to refresh. At a zero interval a refresh
    loop runs within a few turns of the event loop, no clock involved; the owned
    lock is the control that shows those turns are enough."""
    redis = redis_mock()
    refresh = AsyncMock()
    chat_id = uuid4()
    deps = _held_lock_deps(
        acquire=AsyncMock(return_value="tok"), release=AsyncMock(), refresh=refresh
    )
    outer = turn_resources.TurnResources(
        deps=deps,
        redis=redis,
        user_id=uuid4(),
        chat_id=chat_id,
        lock_key=f"chatprep:{chat_id}",
        lock_token="outer",
        reserved_tokens=10,
    )

    with patch.object(turn_resources, "CHATPREP_LOCK_REFRESH_INTERVAL_SECONDS", 0):
        async with turn_resources.turn_resources(
            deps,
            redis,
            user_id=outer.user_id,
            chat_id=chat_id,
            borrowed=outer if borrowed else None,
        ):
            for _ in range(5):
                await asyncio.sleep(0)

    assert (refresh.await_count > 0) is not borrowed


@pytest.mark.asyncio
async def test_top_up_reserve_for_prompt_adds_delta():
    user = _user()
    redis = redis_mock()
    reserve = AsyncMock(return_value=30)
    res = turn_resources.TurnResources(
        deps=turn_deps(quota={"reserve_usage_up_to": reserve}),
        redis=redis,
        user_id=user.id,
        chat_id=uuid4(),
        lock_key="k",
        lock_token="t",
        reserved_tokens=10,
    )
    ctx = MagicMock()
    ctx.prompt_messages = [{"role": "user", "content": "hello"}]
    ctx.model = "free-chat"
    ctx.max_output_tokens = 50
    ctx.user = user
    ctx.reserved_tokens = 10

    with patch("app.modules.chat.turn_resources.prompt_weighted_reserve_tokens", return_value=40):
        await turn_resources.top_up_reserve_for_prompt(
            res, settings=Settings(), ctx=ctx, daily_limit=100
        )

    reserve.assert_awaited_once()
    assert reserve.await_args.args[2] == 30
    assert res.reserved_tokens == 40
    assert ctx.reserved_tokens == 40


@pytest.mark.asyncio
async def test_top_up_reserve_for_prompt_keeps_the_turn_when_no_more_fits():
    """The turn already holds a reservation; a top-up that cannot grow never refuses."""
    user = _user()
    redis = redis_mock()
    res = turn_resources.TurnResources(
        deps=turn_deps(quota={"reserve_usage_up_to": AsyncMock(return_value=0)}),
        redis=redis,
        user_id=user.id,
        chat_id=uuid4(),
        lock_key="k",
        lock_token="t",
        reserved_tokens=10,
    )
    ctx = MagicMock()
    ctx.prompt_messages = [{"role": "user", "content": "hello"}]
    ctx.model = "free-chat"
    ctx.max_output_tokens = 50
    ctx.user = user
    ctx.reserved_tokens = 10

    with patch("app.modules.chat.turn_resources.prompt_weighted_reserve_tokens", return_value=40):
        await turn_resources.top_up_reserve_for_prompt(
            res, settings=Settings(), ctx=ctx, daily_limit=100
        )

    assert res.reserved_tokens == 10
    assert ctx.reserved_tokens == 10
