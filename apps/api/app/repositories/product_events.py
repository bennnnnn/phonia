from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import ProductEvent, ProductEventDaily, ProductEventRollupDay


async def create_batch(
    session: AsyncSession,
    events: Sequence[ProductEvent],
    *,
    commit: bool = True,
) -> None:
    session.add_all(events)
    if commit:
        await session.commit()
    else:
        await session.flush()


async def list_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
) -> list[ProductEvent]:
    result = await session.execute(
        select(ProductEvent)
        .where(ProductEvent.user_id == user_id)
        .order_by(ProductEvent.recorded_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


async def oldest_day(session: AsyncSession, names: Sequence[str]) -> date | None:
    """The UTC day of the oldest event, read through ``(name, recorded_at)`` per name."""
    oldest: datetime | None = None
    for name in names:
        found = await session.scalar(
            select(func.min(ProductEvent.recorded_at)).where(ProductEvent.name == name)
        )
        if found is not None and (oldest is None or found < oldest):
            oldest = found
    return None if oldest is None else oldest.astimezone(UTC).date()


async def is_rolled_up(session: AsyncSession, day: date) -> bool:
    return await session.get(ProductEventRollupDay, day) is not None


async def roll_up_day(session: AsyncSession, day: date, names: Sequence[str]) -> None:
    """Count ``day``'s events by bucket into ``product_event_daily`` and mark the day; no commit.

    Run once per day (the marker says it ran): a re-run after some rows were deleted
    would count fewer.
    """
    start, end = _day_bounds(day)
    platform = func.coalesce(ProductEvent.platform, "")
    app_version = func.coalesce(ProductEvent.app_version, "")
    counts = (
        select(
            literal(day).label("day"),
            ProductEvent.name,
            platform.label("platform"),
            app_version.label("app_version"),
            ProductEvent.properties,
            func.count().label("events"),
            func.count(func.distinct(ProductEvent.user_id)).label("users"),
        )
        .where(
            ProductEvent.name.in_(list(names)),
            ProductEvent.recorded_at >= start,
            ProductEvent.recorded_at < end,
        )
        .group_by(ProductEvent.name, platform, app_version, ProductEvent.properties)
    )
    await session.execute(
        pg_insert(ProductEventDaily)
        .from_select(
            ["day", "name", "platform", "app_version", "properties", "events", "users"], counts
        )
        .on_conflict_do_nothing()
    )
    await session.execute(pg_insert(ProductEventRollupDay).values(day=day).on_conflict_do_nothing())


async def delete_day_batch(
    session: AsyncSession, day: date, names: Sequence[str], *, limit: int
) -> int:
    """Delete up to ``limit`` of ``day``'s events; returns how many. No commit."""
    start, end = _day_bounds(day)
    batch = (
        select(ProductEvent.id)
        .where(
            ProductEvent.name.in_(list(names)),
            ProductEvent.recorded_at >= start,
            ProductEvent.recorded_at < end,
        )
        .limit(limit)
    )
    result = cast(
        CursorResult[Any],
        await session.execute(delete(ProductEvent).where(ProductEvent.id.in_(batch))),
    )
    return int(result.rowcount or 0)
