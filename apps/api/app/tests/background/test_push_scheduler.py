"""The push cycle: pages of due reminders, one Expo request at a time, marked as it goes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis
import pytest

from app.background import push_scheduler
from app.core.config import Settings
from app.gateways import expo_push_gateway
from app.gateways.expo_push_gateway import HoldReason, PushHold, PushSendResult
from app.modules.notifications.push import OutboundPush, PushPage
from app.tests.fakes import FakeSessionCM


def test_push_lock_outlives_one_expo_request():
    """Refreshed before each request, so it only has to outlast one."""
    assert push_scheduler.LOCK_TTL_SECONDS > 2 * expo_push_gateway.EXPO_TIMEOUT_SECONDS


def _messages(count: int) -> list[OutboundPush]:
    return [OutboundPush(message={"to": f"ExponentPushToken[{i}]"}) for i in range(count)]


def _lock(*refreshes: bool) -> MagicMock:
    lock = MagicMock()
    lock.refresh = AsyncMock(side_effect=list(refreshes))
    return lock


async def _cycle(
    pages: list[PushPage],
    lock: MagicMock,
    *,
    settings: Settings | None = None,
    redis: object | None = None,
    holds: list[PushHold | None] | None = None,
    throttled: bool = False,
) -> list[str]:
    order: list[str] = []
    page_iter = iter(pages)

    async def collect(
        session: object, *, now: datetime, after: object, ttl_seconds: int | None
    ) -> PushPage:
        order.append(f"collect after={after}")
        return next(page_iter)

    async def dispatch(items: list[OutboundPush], settings: Settings) -> PushSendResult:
        order.append(f"dispatch {len(items)}")
        if throttled:
            hold = PushHold(HoldReason.THROTTLED, 60.0)
            return PushSendResult([], [False] * len(items), [], [hold] * len(items), True)
        if holds is not None:
            return PushSendResult([], [False] * len(items), holds=holds[: len(items)])
        return PushSendResult([], [True] * len(items))

    async def finalize(session: object, items: list[OutboundPush], delivered: list[bool]):
        order.append(f"mark {len(items)}")

    notifications = "app.background.push_scheduler.push_notifications"
    with (
        patch("app.background.push_scheduler.SessionLocal", FakeSessionCM()),
        patch(
            "app.background.push_scheduler.get_redis_client",
            return_value=redis or fakeredis.aioredis.FakeRedis(decode_responses=True),
        ),
        patch(f"{notifications}.log_aged_unsent_reminders", AsyncMock()),
        patch("app.background.push_scheduler.advance_recurring_without_device", AsyncMock()),
        patch(f"{notifications}.collect_push_page", collect),
        patch(f"{notifications}.dispatch_expo", dispatch),
        patch(f"{notifications}.finalize_push_deliveries", finalize),
    ):
        await push_scheduler._push_cycle(settings or Settings(push_enabled=True), lock)
    return order


@pytest.mark.asyncio
async def test_each_expo_request_is_marked_before_the_next_one_goes():
    """Marking only after the whole batch let a stopped worker or a lost lock resend."""
    order = await _cycle(
        [PushPage(messages=_messages(250), next_after=None)], _lock(True, True, True)
    )
    assert order == [
        "collect after=None",
        "dispatch 100",
        "mark 100",
        "dispatch 100",
        "mark 100",
        "dispatch 50",
        "mark 50",
    ]


@pytest.mark.asyncio
async def test_a_cycle_that_lost_its_lock_stops_sending():
    """A peer that took the lock would send the same to-dos again."""
    order = await _cycle([PushPage(messages=_messages(250), next_after=None)], _lock(True, False))
    assert order == ["collect after=None", "dispatch 100", "mark 100"]


@pytest.mark.asyncio
async def test_a_throttled_request_stops_the_cycle():
    """After a 429 the cycle sent the next chunks and pages anyway."""
    key = (datetime(2026, 10, 20, 9, 0, tzinfo=UTC), uuid4())
    pages = [
        PushPage(messages=_messages(250), next_after=key),
        PushPage(messages=_messages(1), next_after=None),
    ]
    order = await _cycle(pages, _lock(True, True, True, True), throttled=True)
    assert order == ["collect after=None", "dispatch 100", "mark 100"]


@pytest.mark.asyncio
async def test_the_cycle_reads_page_after_page():
    key = (datetime(2026, 10, 20, 9, 0, tzinfo=UTC), uuid4())
    pages = [
        PushPage(messages=_messages(1), next_after=key),
        PushPage(messages=_messages(1), next_after=None),
    ]
    order = await _cycle(pages, _lock(True, True))
    assert order == [
        "collect after=None",
        "dispatch 1",
        "mark 1",
        f"collect after={key}",
        "dispatch 1",
        "mark 1",
    ]


@pytest.mark.asyncio
async def test_an_empty_page_sends_nothing():
    order = await _cycle([PushPage(messages=[], next_after=None)], _lock())
    assert order == ["collect after=None"]


@pytest.mark.asyncio
async def test_receipts_are_polled_by_their_own_cycle():
    poll = AsyncMock()
    with (
        patch("app.background.push_scheduler.SessionLocal", FakeSessionCM()),
        patch("app.background.push_scheduler.get_redis_client", return_value=AsyncMock()),
        patch("app.background.push_scheduler.push_notifications.poll_deferred_push_receipts", poll),
    ):
        await push_scheduler._receipts_cycle(Settings(push_enabled=True), MagicMock())
    poll.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(("budget", "pages_read"), [(60, 25), (0, 1)])
async def test_the_cycle_reads_pages_while_its_budget_lasts(budget: int, pages_read: int):
    """It stopped at 20 pages (10,000 reminders a minute) whatever the backlog."""
    key = (datetime(2026, 10, 20, 9, 0, tzinfo=UTC), uuid4())
    pages = [PushPage(messages=_messages(1), next_after=key) for _ in range(24)]
    pages.append(PushPage(messages=_messages(1), next_after=None))
    settings = Settings(push_enabled=True, reminder_cycle_budget_seconds=budget)
    order = await _cycle(pages, _lock(*[True] * 25), settings=settings)
    assert sum(step.startswith("collect") for step in order) == pages_read


def _reminder_messages(count: int) -> list[OutboundPush]:
    todos = []
    for _ in range(count):
        todo = MagicMock()
        todo.id = uuid4()
        todo.due_at = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
        todos.append(todo)
    return [
        OutboundPush(message={"to": f"ExponentPushToken[{i}]"}, todos=[todo])
        for i, todo in enumerate(todos)
    ]


@pytest.mark.asyncio
async def test_a_push_expo_may_have_accepted_is_not_resent_next_minute():
    """A read timeout after the request went out: resent next minute, it showed twice."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    messages = _reminder_messages(2)
    holds = [PushHold(HoldReason.AMBIGUOUS), None]  # the second never reached Expo
    first = await _cycle(
        [PushPage(messages=messages, next_after=None)], _lock(True), redis=redis, holds=holds
    )
    second = await _cycle(
        [PushPage(messages=messages, next_after=None)], _lock(True), redis=redis, holds=[None]
    )
    assert first == ["collect after=None", "dispatch 2", "mark 2"]
    assert second == ["collect after=None", "dispatch 1", "mark 1"]
    held = [key async for key in redis.scan_iter("phonia:push:hold:*")]
    assert len(held) == 1
    assert await redis.ttl(held[0]) > 14 * 60  # push_ambiguous_hold_seconds
