"""A reminder send that failed for now waits, doubling, before its next try."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.notifications.send_backoff import SendBackoff, occurrence_key


def _backoff(redis: Any) -> SendBackoff:
    return SendBackoff.for_channel(
        redis, Settings(reminder_retry_base_seconds=60, reminder_retry_max_seconds=3600), "push"
    )


@pytest.mark.parametrize(
    ("attempts", "at_least", "wait"),
    [
        (1, None, 60),
        (2, None, 120),
        (3, None, 240),
        (7, None, 3600),  # capped
        (40, None, 3600),
        (1, 900, 900),  # an ambiguous push's floor
        (3, 30, 240),  # a short Retry-After never shortens the back-off
        (1, 10**9, 24 * 60 * 60),  # a Retry-After is capped at a day
    ],
)
def test_wait_after(attempts: int, at_least: float | None, wait: int) -> None:
    assert _backoff(None).wait_after(attempts, at_least=at_least) == wait


async def test_a_held_occurrence_is_reported_until_its_hold_runs_out(fake_redis: Any) -> None:
    backoff = _backoff(fake_redis)
    due = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    held, free = occurrence_key(uuid4(), due), occurrence_key(uuid4(), due)

    assert await backoff.hold(held) == 60
    assert await backoff.hold(held) == 120  # the second failure doubles it
    assert await backoff.held([held, free]) == {held}
    assert 60 < await fake_redis.ttl(f"recall:push:hold:{held}") <= 120

    await fake_redis.delete(f"recall:push:hold:{held}")
    assert await backoff.held([held, free]) == set()


async def test_redis_down_holds_nothing_and_never_raises() -> None:
    class Down:
        async def mget(self, *_a: Any) -> list[Any]:
            raise ConnectionError("down")

        def pipeline(self, **_kw: Any) -> Any:
            raise ConnectionError("down")

    backoff = _backoff(Down())
    assert await backoff.held(["a"]) == set()
    assert await backoff.hold("a") == 0


def test_a_moved_reminder_is_a_new_occurrence() -> None:
    todo = uuid4()
    first = occurrence_key(todo, datetime(2026, 11, 2, 9, 0, tzinfo=UTC))
    moved = occurrence_key(todo, datetime(2026, 11, 3, 9, 0, tzinfo=UTC))
    assert first != moved
