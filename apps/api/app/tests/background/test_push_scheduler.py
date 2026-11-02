"""The push cycle: pages of due reminders, one Expo request at a time, marked as it goes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.background import push_scheduler
from app.core.config import Settings
from app.gateways import expo_push_gateway
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


async def _cycle(pages: list[PushPage], lock: MagicMock) -> list[str]:
    order: list[str] = []
    page_iter = iter(pages)

    async def collect(session: object, *, now: datetime, after: object) -> PushPage:
        order.append(f"collect after={after}")
        return next(page_iter)

    async def dispatch(items: list[OutboundPush], settings: Settings):
        order.append(f"dispatch {len(items)}")
        return [True] * len(items), [], []

    async def finalize(session: object, items: list[OutboundPush], delivered: list[bool]):
        order.append(f"mark {len(items)}")

    notifications = "app.background.push_scheduler.push_notifications"
    with (
        patch("app.background.push_scheduler.SessionLocal", FakeSessionCM()),
        patch("app.background.push_scheduler.get_redis_client", return_value=AsyncMock()),
        patch(f"{notifications}.log_aged_unsent_reminders", AsyncMock()),
        patch("app.background.push_scheduler.advance_recurring_without_device", AsyncMock()),
        patch(f"{notifications}.collect_push_page", collect),
        patch(f"{notifications}.dispatch_expo", dispatch),
        patch(f"{notifications}.finalize_push_deliveries", finalize),
    ):
        await push_scheduler._push_cycle(Settings(push_enabled=True), lock)
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
