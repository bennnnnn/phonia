"""Hold back a reminder whose send failed in a way worth waiting out.

The reminder cycles run every minute and resend whatever is still unmarked. That is
right after a send that never reached the provider, and wrong after one that may have
been delivered (a timeout once the request went out: resent at once, it shows twice),
was throttled (a 429 asks for a wait), or failed on the provider's side (a 5xx outage
answered 60 times an hour). Such a send holds its reminder occurrence for a while:
each failure doubles the wait from ``reminder_retry_base_seconds`` up to
``reminder_retry_max_seconds``, never shorter than a wait the provider or the caller
asked for. State lives in Redis (no column), keyed by the to-do and its due time, so a
moved or next recurring reminder starts afresh.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Failures counted per occurrence live as long as a reminder can be sent (48 h overdue).
_ATTEMPTS_TTL_SECONDS = 3 * 24 * 60 * 60


def occurrence_key(todo_id: UUID, due_at: datetime | None) -> str:
    """One reminder occurrence: the to-do at its due time."""
    due = int(due_at.timestamp()) if due_at is not None else 0
    return f"{todo_id}:{due}"


@dataclass(frozen=True)
class SendBackoff:
    """The holds of one channel (``push`` or ``email``)."""

    redis: Redis
    channel: str
    base_seconds: int
    max_seconds: int

    @classmethod
    def for_channel(cls, redis: Redis, settings: Settings, channel: str) -> SendBackoff:
        return cls(
            redis,
            channel,
            max(1, settings.reminder_retry_base_seconds),
            max(1, settings.reminder_retry_max_seconds),
        )

    def _hold_key(self, occurrence: str) -> str:
        return f"phonia:{self.channel}:hold:{occurrence}"

    def _attempts_key(self, occurrence: str) -> str:
        return f"phonia:{self.channel}:attempts:{occurrence}"

    async def held(self, occurrences: Sequence[str]) -> set[str]:
        """The occurrences still waiting out a hold. Redis down: none (the cycle's own
        lock needs Redis, so this only matters for a blip)."""
        if not occurrences:
            return set()
        try:
            values = await self.redis.mget([self._hold_key(o) for o in occurrences])
        except Exception:
            logger.warning("Reminder holds unreadable channel=%s", self.channel, exc_info=True)
            return set()
        return {o for o, value in zip(occurrences, values, strict=True) if value is not None}

    async def hold(self, occurrence: str, *, at_least: float | None = None) -> int:
        """Count one failed send of ``occurrence`` and hold it; the seconds it waits."""
        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                pipe.incr(self._attempts_key(occurrence))
                pipe.expire(self._attempts_key(occurrence), _ATTEMPTS_TTL_SECONDS)
                attempts, _ = await pipe.execute()
            wait = self.wait_after(int(attempts), at_least=at_least)
            await self.redis.set(self._hold_key(occurrence), int(attempts), ex=wait)
        except Exception:
            logger.warning("Reminder hold not recorded channel=%s", self.channel, exc_info=True)
            return 0
        return wait

    def wait_after(self, attempts: int, *, at_least: float | None = None) -> int:
        """Seconds to wait after ``attempts`` failures: doubling, capped, never under
        ``at_least`` (itself capped at a day: a Retry-After is the provider's word)."""
        doubling = self.base_seconds * 2 ** min(max(attempts - 1, 0), 30)
        wait = min(self.max_seconds, doubling)
        if at_least is not None and at_least > 0:
            wait = max(wait, min(math.ceil(at_least), 24 * 60 * 60))
        return max(1, int(wait))
