"""A chat turn reserves today's tokens before it runs, and the global cap stops it.

The real Redis quota (fakeredis) backs every test here: the old soft check only
read ``used >= limit``, so thirty chats started at once against the same last
thousand tokens all passed it.
"""

import asyncio
from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.background_tasks import drain_background_tasks
from app.core.config import Settings
from app.core.spend_counter import spend_key
from app.exceptions import QuotaExceededError, RedisUnavailableError, SpendCapReachedError
from app.modules.chat import stream_entry, turn_load, turn_resources
from app.modules.chat.stream_events import error_payload_for_exception
from app.modules.chat.turn_prep import StreamContext
from app.modules.conversation import chats_repository, messages_repository
from app.services import quota as quota_service
from app.services.quota import CHAT_SPEND_CAP_MESSAGE
from app.services.quota import tokens as quota_tokens
from app.tests.modules.chat.chat_test_support import FakeSessionCM, turn_deps

_SETTINGS = Settings(max_output_tokens=1_000)
_LIMIT = 10_000


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.plan = "free"
    return user


def _wanted(content: str = "hi", model: str = "free-chat") -> int:
    return turn_resources.weighted_reserve_tokens(
        content=content, model=model, settings=_SETTINGS, max_output=_SETTINGS.max_output_tokens
    )


def _no_session() -> FakeSessionCM:
    raise AssertionError("reserving a turn's tokens opened a database session")


async def _reserve(fake_redis, user, *, settings: Settings = _SETTINGS) -> int:
    return await turn_resources.reserve_turn_quota(
        turn_deps(session_factory=_no_session),
        fake_redis,
        user=user,
        content="hi",
        model="free-chat",
        settings=settings,
        daily_limit=_LIMIT,
        max_output=settings.max_output_tokens,
    )


async def _used(fake_redis, user) -> int:
    return await quota_service.get_daily_usage(fake_redis, str(user.id))


@pytest.mark.parametrize(
    "used, reserved",
    [
        (0, "wanted"),
        (_LIMIT - 2_000, "wanted"),
        (_LIMIT - 50, 50),
        (_LIMIT - 1, 1),
    ],
)
async def test_reserve_turn_quota_takes_estimate_or_what_is_left(
    fake_redis, used: int, reserved: int | str
) -> None:
    user = _user()
    if used:
        await quota_tokens.record_usage(fake_redis, str(user.id), used)
    expected = _wanted() if reserved == "wanted" else reserved

    got = await _reserve(fake_redis, user)

    assert got == expected
    assert await _used(fake_redis, user) == used + expected


@pytest.mark.parametrize("used", [_LIMIT, _LIMIT + 500])
async def test_reserve_turn_quota_refuses_at_the_limit_without_charging(
    fake_redis, used: int
) -> None:
    user = _user()
    await quota_tokens.record_usage(fake_redis, str(user.id), used)

    with pytest.raises(QuotaExceededError):
        await _reserve(fake_redis, user)

    assert await _used(fake_redis, user) == used


@pytest.mark.parametrize("turns", [2, 30])
async def test_reserve_turn_quota_concurrent_turns_share_one_budget(fake_redis, turns: int) -> None:
    user = _user()
    left = _wanted() + 300
    await quota_tokens.record_usage(fake_redis, str(user.id), _LIMIT - left)

    results = await asyncio.gather(
        *(_reserve(fake_redis, user) for _ in range(turns)), return_exceptions=True
    )

    granted = [r for r in results if isinstance(r, int)]
    refused = [r for r in results if isinstance(r, QuotaExceededError)]
    assert len(granted) + len(refused) == turns
    assert sum(granted) <= left
    assert await _used(fake_redis, user) <= _LIMIT
    assert granted, "the first turn always starts"


@pytest.mark.parametrize(
    "spent_usd, cap_usd, refused",
    [
        (0.0, 1.0, False),
        (0.99, 1.0, False),
        (1.0, 1.0, True),
        (7.5, 1.0, True),
        (500.0, 0.0, False),  # 0 is unlimited (dev, tests)
    ],
)
async def test_reserve_turn_quota_stops_at_the_global_spend_cap(
    fake_redis, spent_usd: float, cap_usd: float, refused: bool
) -> None:
    user = _user()
    await quota_service.record_global_spend(fake_redis, spent_usd)
    settings = Settings(max_output_tokens=1_000, daily_global_spend_usd=cap_usd)

    if refused:
        with pytest.raises(SpendCapReachedError) as caught:
            await _reserve(fake_redis, user, settings=settings)
        assert caught.value.message == CHAT_SPEND_CAP_MESSAGE
        assert await _used(fake_redis, user) == 0
    else:
        assert await _reserve(fake_redis, user, settings=settings) == _wanted()


async def test_reserve_turn_quota_with_the_spend_unreadable_is_unavailable(fake_redis) -> None:
    """Redis down at the spend read: the socket's and SSE's ``unavailable`` frame, nothing
    charged. It read as the cap, so an outage said "Recall is at capacity for today"."""
    user = _user()
    settings = Settings(max_output_tokens=1_000, daily_global_spend_usd=1.0)
    down = AsyncMock(side_effect=RedisConnectionError("Error 111 connecting to redis"))

    with patch.object(fake_redis, "get", down), pytest.raises(RedisUnavailableError) as caught:
        await _reserve(fake_redis, user, settings=settings)

    assert error_payload_for_exception(caught.value)["code"] == "unavailable"
    assert await _used(fake_redis, user) == 0


def test_spend_cap_error_is_a_plain_error_not_the_users_quota() -> None:
    payload = error_payload_for_exception(SpendCapReachedError(CHAT_SPEND_CAP_MESSAGE))

    # quota_exceeded opens the phone's upgrade prompt; upgrading would not help.
    assert payload == {"type": "error", "code": "spend_cap", "message": CHAT_SPEND_CAP_MESSAGE}
    for phrase in ("free limit", "daily limit", "today's limit"):
        assert phrase not in CHAT_SPEND_CAP_MESSAGE.lower()


def _resources(fake_redis, user, reserved: int) -> turn_resources.TurnResources:
    return turn_resources.TurnResources(
        deps=turn_deps(session_factory=FakeSessionCM),
        redis=fake_redis,
        user_id=user.id,
        chat_id=uuid4(),
        lock_key="chatprep:test",
        lock_token="token",
        reserved_tokens=reserved,
    )


def _ctx(user, reserved: int) -> StreamContext:
    return StreamContext(
        user_id=user.id,
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hello"}],
        run_title=False,
        user_message_content="hello",
        reserved_tokens=reserved,
        max_output_tokens=100,
        user=user,
    )


@pytest.mark.parametrize(
    "room_after_start, needed, reserved_after",
    [
        (5_000, 1_500, 1_500),  # room for the whole prompt
        (200, 1_500, 1_200),  # only what is left
        (0, 1_500, 1_000),  # nothing left: the turn keeps running on what it holds
        (5_000, 600, 1_000),  # the prompt is smaller than the start estimate
    ],
)
async def test_top_up_reserve_for_prompt_grows_up_to_what_is_left(
    fake_redis, room_after_start: int, needed: int, reserved_after: int
) -> None:
    user = _user()
    start = 1_000
    await quota_tokens.record_usage(fake_redis, str(user.id), _LIMIT - room_after_start)
    res = _resources(fake_redis, user, start)
    ctx = _ctx(user, start)

    with patch.object(turn_resources, "prompt_weighted_reserve_tokens", return_value=needed):
        await turn_resources.top_up_reserve_for_prompt(
            res, settings=_SETTINGS, ctx=ctx, daily_limit=_LIMIT
        )

    assert res.reserved_tokens == reserved_after
    assert ctx.reserved_tokens == reserved_after
    assert await _used(fake_redis, user) <= _LIMIT


@pytest.mark.parametrize(
    "used_before, actual, used_after",
    [
        (0, 300, 300),  # a short answer gives the rest back
        (0, 4_000, 4_000),  # a long one is charged past its estimate
        (_LIMIT - 500, 9_000, _LIMIT),  # never past the limit (finalize clips)
    ],
)
async def test_turn_reservation_settles_to_actual_usage(
    fake_redis, used_before: int, actual: int, used_after: int
) -> None:
    user = _user()
    if used_before:
        await quota_tokens.record_usage(fake_redis, str(user.id), used_before)
    reserved = await _reserve(fake_redis, user)

    # What finalize_stream_turn_db does with ctx.reserved_tokens.
    await quota_service.adjust_usage(fake_redis, str(user.id), reserved, actual, daily_limit=_LIMIT)

    assert await _used(fake_redis, user) == used_after


@pytest.mark.parametrize("failure", [RuntimeError("provider"), asyncio.CancelledError()])
async def test_turn_resources_refund_the_reservation_when_a_turn_fails(
    fake_redis, failure: BaseException
) -> None:
    user = _user()
    deps = turn_deps(
        session_factory=FakeSessionCM,
        locks={"acquire_lock": AsyncMock(return_value="tok"), "release_lock": AsyncMock()},
    )

    with pytest.raises(type(failure)):
        async with turn_resources.turn_resources(
            deps, fake_redis, user_id=user.id, chat_id=uuid4()
        ) as res:
            await res.reserve(
                user=user,
                content="hi",
                model="free-chat",
                settings=_SETTINGS,
                daily_limit=_LIMIT,
                max_output=_SETTINGS.max_output_tokens,
            )
            assert await _used(fake_redis, user) == _wanted()
            raise failure

    assert await _used(fake_redis, user) == 0


def _spend_read_down(fake_redis):
    """Redis fails at the day's spend read; every other read is as it is."""
    read = fake_redis.get

    async def get(key: str):
        if key == spend_key():
            raise RedisConnectionError("Error 111 connecting to redis")
        return await read(key)

    return patch.object(fake_redis, "get", AsyncMock(side_effect=get))


@pytest.mark.parametrize(
    "spend, refusal, code",
    [("capped", SpendCapReachedError, "spend_cap"), ("down", RedisUnavailableError, "unavailable")],
)
async def test_stream_chat_response_at_spend_cap_never_prepares_the_turn(
    fake_redis, spend: str, refusal: type[Exception], code: str
) -> None:
    user = _user()
    user.default_model = "free-chat"
    prepare = AsyncMock()
    release = AsyncMock()
    deps = turn_deps(
        session_factory=FakeSessionCM,
        model_choice={"resolve_user_model_override": MagicMock(return_value="free-chat")},
        locks={"acquire_lock": AsyncMock(return_value="tok"), "release_lock": release},
    )
    if spend == "capped":
        await quota_service.record_global_spend(fake_redis, 2.0)
    chat = MagicMock()
    chat.summary = None

    with (
        _spend_read_down(fake_redis) if spend == "down" else nullcontext(),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=chat)),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[])),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=0)),
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch("app.modules.chat.stream_entry.prepare_chat_turn", prepare),
        pytest.raises(refusal) as caught,
    ):
        async for _ in stream_entry.stream_chat_response(
            deps,
            fake_redis,
            Settings(daily_global_spend_usd=1.0),
            user_id=user.id,
            chat_id=uuid4(),
            content="hello there, explain entropy",
            user=user,
            skip_usage_seed=True,
        ):
            pass

    # The socket's and SSE's error frame: an outage said "at capacity for today".
    assert error_payload_for_exception(caught.value)["code"] == code
    prepare.assert_not_awaited()
    release.assert_awaited_once()
    assert await _used(fake_redis, user) == 0


async def test_regenerate_reads_back_a_lost_usage_counter_in_its_load_session(fake_redis) -> None:
    """Redis lost today's counter: the regenerate's one load session reads it back.

    The reservation used to open a second session for it, after the load closed.
    """
    user = _user()
    asked = MagicMock(role="user", content="explain entropy", model="free-chat", id=uuid4())
    last = MagicMock(role="assistant", content="old answer", model="free-chat", id=uuid4())
    sessions: list[object] = []

    def counting_session() -> FakeSessionCM:
        sessions.append(object())
        return FakeSessionCM()

    deps = turn_deps(
        session_factory=counting_session,
        users={"get_by_id": AsyncMock(return_value=user)},
        chats={"get_by_id": AsyncMock(return_value=MagicMock(summary=None))},
        messages={
            "list_recent": AsyncMock(return_value=[asked, last]),
            "count_for_chat": AsyncMock(return_value=2),
        },
        model_choice={"resolve_regenerate_model": MagicMock(return_value="free-chat")},
    )
    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        patch(
            "app.modules.chat.turn_settle.usage_repo.get_total_for_date",
            AsyncMock(return_value=4_321),
        ),
    ):
        await turn_load.load_regenerate_turn(
            deps, fake_redis, _SETTINGS, user_id=user.id, chat_id=uuid4(), model_alias=None
        )
        reserved = await _reserve(fake_redis, user)

    assert len(sessions) == 1
    assert await _used(fake_redis, user) == 4_321 + reserved


def _slow_after(call):
    """``call`` whose reply takes a moment after Redis applied it, as on a network."""

    async def slow(*args, **kwargs):
        result = await call(*args, **kwargs)
        await asyncio.sleep(0.05)
        return result

    return slow


def _slow_before(call):
    """``call`` that takes a moment to reach Redis: a cancel can land before it does."""

    async def slow(*args, **kwargs):
        await asyncio.sleep(0.05)
        return await call(*args, **kwargs)

    return slow


@pytest.mark.parametrize("stopped_in", ["reserve", "top_up", "refund"])
async def test_a_stop_while_redis_answers_leaks_no_reserved_tokens(
    fake_redis, stopped_in: str
) -> None:
    """Regression: a Stop that cancelled the turn while Redis granted its tokens left
    the grant in the day's total with no turn holding it; nothing refunded it."""
    user = _user()
    quota: dict[str, object] = {}
    if stopped_in in ("reserve", "top_up"):
        quota["reserve_usage_up_to"] = _slow_after(quota_service.reserve_usage_up_to)
    else:
        quota["refund_usage"] = _slow_before(quota_service.refund_usage)
    deps = turn_deps(
        session_factory=FakeSessionCM,
        locks={"acquire_lock": AsyncMock(return_value="tok"), "release_lock": AsyncMock()},
        quota=quota,
    )
    waiting = asyncio.Event()

    async def turn() -> None:
        async with turn_resources.turn_resources(
            deps, fake_redis, user_id=user.id, chat_id=uuid4()
        ) as res:
            if stopped_in == "reserve":
                waiting.set()
            await res.reserve(
                user=user,
                content="hi",
                model="free-chat",
                settings=_SETTINGS,
                daily_limit=_LIMIT,
                max_output=_SETTINGS.max_output_tokens,
            )
            if stopped_in == "top_up":
                waiting.set()
                with patch.object(
                    turn_resources, "prompt_weighted_reserve_tokens", return_value=5_000
                ):
                    await turn_resources.top_up_reserve_for_prompt(
                        res, settings=_SETTINGS, ctx=_ctx(user, 0), daily_limit=_LIMIT
                    )
            if stopped_in == "refund":
                waiting.set()
                await res.refund()

    running = asyncio.create_task(turn())
    await waiting.wait()
    await asyncio.sleep(0.01)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    await drain_background_tasks()

    assert await _used(fake_redis, user) == 0
