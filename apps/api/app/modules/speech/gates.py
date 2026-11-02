"""The gates a paid speech request passes before it spends: plan, spend cap, rate, day.

Each raises a ``SpeechRefusedError`` (a ``DomainError``): 403 opens the paywall, 429
says which limit it hit. Callers keep their own order of checks.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import status
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.rate_limit import allow_request_unless_down
from app.exceptions import DomainError
from app.models.orm import User
from app.modules.billing import can_use
from app.modules.billing.entitlements import Feature
from app.services import quota as quota_service
from app.services.quota import counters

# Speech's per-day counters in ``services/quota/counters.COUNTERS``.
SpeechCounter = Literal["speech_tts", "speech_transcription"]

_RATE_WINDOW_SECONDS = 60


class SpeechRefusedError(DomainError):
    """A speech or live talk request refused before it spends."""


def require_plan_feature(user: User, settings: Settings, feature: Feature, message: str) -> None:
    """Refuse a feature the user's plan does not include (403 opens the paywall)."""
    if not can_use(user, feature, settings):
        raise SpeechRefusedError(message, status_code=status.HTTP_403_FORBIDDEN, code="not_in_plan")


async def require_voice_spend_ok(redis: Redis, settings: Settings) -> None:
    """Refuse while the global provider-spend breaker is open."""
    if await quota_service.global_spend_exceeded(redis, settings):
        raise SpeechRefusedError(
            quota_service.VOICE_SPEND_CAP_MESSAGE,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="voice_spend_cap",
        )


async def require_speech_rate(redis: Redis, settings: Settings, key: str, message: str) -> None:
    """At most ``speech_rate_limit_per_minute`` requests a minute under *key* (0 is off).

    A Redis error denies the request (fail closed) with ``RedisUnavailableError``: 503
    unavailable, never ``speech_rate_limited``, which live talk words as the month's
    minutes used up.
    """
    rate_limit = settings.speech_rate_limit_per_minute
    if rate_limit <= 0:
        return
    allowed = await allow_request_unless_down(
        redis, key, limit=rate_limit, window_seconds=_RATE_WINDOW_SECONDS
    )
    if not allowed:
        raise SpeechRefusedError(
            message, status_code=status.HTTP_429_TOO_MANY_REQUESTS, code="speech_rate_limited"
        )


async def reserve_day_or_raise(
    counter: SpeechCounter, redis: Redis, user: User, settings: Settings
) -> date:
    """Take one of today's *counter* slots; 429 with the plan's message at the cap."""
    day = await counters.reserve(counter, redis, user, settings)
    if not day:
        raise SpeechRefusedError(
            counters.limit_message(counter, user),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="daily_limit",
            feature=counter,
        )
    return day


class RefundDayOnFailure:
    """``async with``: give a reserved slot back to its day when the block fails.

    A 429 refusal keeps the slot (a cap refusal is not a failed request); any other
    refusal, error or cancellation refunds it. Without a *day*
    (nothing was reserved) nothing is refunded. The block's exception always
    propagates. A class rather than ``@asynccontextmanager``, whose generator
    would turn a StopAsyncIteration out of Redis into a RuntimeError.
    """

    def __init__(
        self, counter: SpeechCounter, redis: Redis, user_id: UUID, day: date | None
    ) -> None:
        self.counter: SpeechCounter = counter
        self.redis = redis
        self.user_id = user_id
        self.day = day

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object
    ) -> None:
        if exc is None or not self.day:
            return
        # A refusal from the gates or the route (an HTTPException) names its status.
        if getattr(exc, "status_code", None) == status.HTTP_429_TOO_MANY_REQUESTS:
            return
        if not isinstance(exc, asyncio.CancelledError | Exception):
            return
        await counters.refund(self.counter, self.redis, self.user_id, day=self.day)
