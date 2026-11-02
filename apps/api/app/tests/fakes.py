"""Fakes the API tests share, each true to the contract it stands in for.

Copied fakes drifted (code-health audit TEST-07): a bare ``AsyncMock()`` session
turns the synchronous ``AsyncSession.add`` into a coroutine nobody awaits, so a
test passes even if the code wrongly awaits it, and an unspecced user reads every
column as truthy. These are specced against the real classes. Redis is the
``fake_redis`` fixture (fakeredis), or ``redis_mock()`` when a test scripts replies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.orm import User


def empty_result() -> MagicMock:
    """A ``Result`` with no rows, as an empty table answers; its readers are synchronous."""
    result = MagicMock()
    result.all.return_value = []
    result.first.return_value = None
    result.one_or_none.return_value = None
    result.scalar.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    return result


def fake_session(**attributes: Any) -> AsyncMock:
    """An ``AsyncSession`` over empty tables: its async methods are awaitable, ``add`` and
    friends are not, and a query answers no rows unless the test sets ``execute``."""
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = empty_result()
    session.scalar.return_value = None
    session.scalars.return_value = empty_result().scalars.return_value
    for name, value in attributes.items():
        setattr(session, name, value)
    return session


class FakeSessionCM:
    """``async with SessionLocal() as session`` over a fake session (a new one unless given)."""

    def __init__(self, session: Any | None = None) -> None:
        self.session = session if session is not None else fake_session()

    def __call__(self, *_args: Any, **_kwargs: Any) -> FakeSessionCM:
        """Stands in for the ``SessionLocal`` factory too: calling it opens the same session."""
        return self

    async def __aenter__(self) -> Any:
        return self.session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _QueuedPipeline:
    """redis-py's pipeline: commands queue synchronously and run on ``await execute()``."""

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self._queued: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, command: str) -> Any:
        def queue(*args: Any, **kwargs: Any) -> _QueuedPipeline:
            self._queued.append((command, args, kwargs))
            return self

        return queue

    async def execute(self) -> list[Any]:
        """Each queued command answered by the mock's own method, so scripted replies apply."""
        queued, self._queued = self._queued, []
        return [
            await getattr(self._redis, command)(*args, **kwargs) for command, args, kwargs in queued
        ]

    async def __aenter__(self) -> _QueuedPipeline:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def _mget_nothing(keys: Any, *more: Any) -> list[None]:
    return [None] * (1 + len(more) if isinstance(keys, str) else len(keys))


def redis_mock(**replies: Any) -> AsyncMock:
    """A Redis client for tests that script replies: ``redis_mock(get=None)``, or set
    ``redis.get.return_value`` later.

    A bare ``AsyncMock()`` made the synchronous ``pipeline()`` a coroutine nobody
    awaited. Here it queues, as redis-py's does. Prefer the ``fake_redis`` fixture
    (fakeredis) when the code reads back what it wrote.
    """
    redis = AsyncMock()
    redis.pipeline = MagicMock(side_effect=lambda *_args, **_kwargs: _QueuedPipeline(redis))
    # An empty Redis answers MGET with one None per key, as redis-py's does; a bare mock
    # answered an empty MagicMock, which no caller could pair with its keys.
    if "mget" not in replies:
        redis.mget = AsyncMock(side_effect=_mget_nothing)
    for command, reply in replies.items():
        getattr(redis, command).return_value = reply
    return redis


def make_user(**columns: Any) -> MagicMock:
    """A ``User`` whose columns the app reads hold real values; any can be overridden."""
    user = MagicMock(spec=User)
    defaults: dict[str, Any] = {
        "id": uuid4(),
        "email": "user@example.com",
        "name": "Test User",
        "plan": "free",
        "locale": "en",
        "timezone": "UTC",
        "memory_enabled": True,
        "memory_include_sensitive": False,
        "memory_edited_at": None,
        "follow_up_suggestions_enabled": True,
        "web_search_enabled": True,
        "location_enabled": False,
        "location": None,
        "response_tone": "casual",
        "emoji_use": "some",
        "push_notifications_enabled": False,
        "push_reminders_enabled": True,
        "email_reminders_enabled": False,
        "quiet_hours_enabled": False,
        "quiet_hours_start_minute": 1320,
        "quiet_hours_end_minute": 420,
        "ai_data_consent_at": datetime(2026, 1, 1, tzinfo=UTC),
        "custom_instructions": None,
        "reminder_lead_minutes": None,
    }
    for name, value in {**defaults, **columns}.items():
        setattr(user, name, value)
    return user


def isolated_settings(**overrides: Any) -> Settings:
    """``Settings`` from the test's overrides and defaults alone, never a developer's ``.env``."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]
