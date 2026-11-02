"""Product events past their retention become per-day counts, and the rows go.

Two events were recorded a chat turn and nothing deleted any.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.models.orm import ProductEvent, ProductEventDaily, ProductEventRollupDay
from app.modules.analytics import retention
from app.repositories import users as users_repo

TODAY = date(2026, 10, 20)
_TTFT = {"latency_bucket": "lt500", "transport": "ws", "has_attachment": "no", "sample_rate": "0.2"}


async def _user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


def _event(user_id, recorded_at: datetime, *, platform: str | None = "ios") -> ProductEvent:
    return ProductEvent(
        user_id=user_id,
        name="chat_ttft",
        properties=_TTFT,
        platform=platform,
        app_version="1.0.0",
        recorded_at=recorded_at,
    )


def _settings(**overrides) -> Settings:
    return Settings(
        analytics_event_retention_days=90,
        analytics_retention_delete_batch=2,
        analytics_retention_max_deletes_per_cycle=1_000,
    ).model_copy(update=overrides)


@pytest.fixture
def same_session(db_session):
    """The pass opens its own sessions; here they are the test's savepointed one."""

    @asynccontextmanager
    async def session_local() -> AsyncIterator:
        yield db_session

    with patch.object(retention, "SessionLocal", session_local):
        yield db_session


async def _always() -> bool:
    return True


async def test_old_days_become_counts_and_their_rows_are_deleted(same_session) -> None:
    session = same_session
    alice, bob = await _user(session), await _user(session)
    old_day = datetime(2026, 6, 1, 12, tzinfo=UTC)
    recent = datetime.combine(TODAY - timedelta(days=10), datetime.min.time(), tzinfo=UTC)
    session.add_all(
        [
            _event(alice.id, old_day),
            _event(alice.id, old_day + timedelta(hours=1)),
            _event(bob.id, old_day + timedelta(hours=2)),
            _event(bob.id, old_day + timedelta(hours=3), platform=None),
            _event(alice.id, recent),
        ]
    )
    await session.flush()

    deleted = await retention.run_retention_pass(_settings(), keep_going=_always, today=TODAY)

    assert deleted == 4
    rows = (
        await session.execute(
            select(
                ProductEventDaily.day,
                ProductEventDaily.platform,
                ProductEventDaily.events,
                ProductEventDaily.users,
            ).order_by(ProductEventDaily.platform)
        )
    ).all()
    assert rows == [(date(2026, 6, 1), "", 1, 1), (date(2026, 6, 1), "ios", 3, 2)]
    left = await session.scalar(select(func.count()).select_from(ProductEvent))
    assert left == 1


async def test_a_day_is_counted_once_even_if_its_delete_stopped_halfway(same_session) -> None:
    session = same_session
    user = await _user(session)
    old_day = datetime(2026, 6, 1, 12, tzinfo=UTC)
    session.add_all([_event(user.id, old_day + timedelta(minutes=i)) for i in range(5)])
    await session.flush()
    answers = iter([True, False])

    async def stop_after_one_batch() -> bool:
        return next(answers, False)

    first = await retention.run_retention_pass(
        _settings(), keep_going=stop_after_one_batch, today=TODAY
    )
    second = await retention.run_retention_pass(_settings(), keep_going=_always, today=TODAY)

    assert (first, second) == (2, 3)
    counted = await session.scalar(select(func.sum(ProductEventDaily.events)))
    assert counted == 5
    assert await session.get(ProductEventRollupDay, date(2026, 6, 1)) is not None


async def test_events_inside_the_retention_stay(same_session) -> None:
    session = same_session
    user = await _user(session)
    inside = datetime.combine(TODAY - timedelta(days=89), datetime.min.time(), tzinfo=UTC)
    session.add(_event(user.id, inside))
    await session.flush()

    assert await retention.run_retention_pass(_settings(), keep_going=_always, today=TODAY) == 0
    assert await session.scalar(select(func.count()).select_from(ProductEventDaily)) == 0
