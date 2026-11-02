from datetime import date
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import UsageDaily


async def list_for_user(session: AsyncSession, user_id: UUID, *, limit: int) -> list[UsageDaily]:
    """Daily token totals, oldest first (data export)."""
    result = await session.execute(
        select(UsageDaily)
        .where(UsageDaily.user_id == user_id)
        .order_by(UsageDaily.date.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_for_date(session: AsyncSession, user_id: UUID, day: date) -> UsageDaily | None:
    return await session.get(UsageDaily, {"user_id": user_id, "date": day})


class DayTotals(NamedTuple):
    input_tokens: int
    output_tokens: int


async def add_tokens(
    session: AsyncSession,
    user_id: UUID,
    day: date,
    *,
    input_tokens: int,
    output_tokens: int,
    est_cost_usd: float = 0.0,
    commit: bool = True,
) -> DayTotals:
    """Atomically increment daily usage (safe under concurrent finalizes).

    The upsert returns the day's totals itself: the SELECT that used to follow it sat
    inside the commit that holds a turn's ``done``, and its caller ignored the row.
    """
    stmt = pg_insert(UsageDaily).values(
        user_id=user_id,
        date=day,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        est_cost_usd=est_cost_usd,
    )
    upsert = stmt.on_conflict_do_update(
        index_elements=[UsageDaily.user_id, UsageDaily.date],
        set_={
            "input_tokens": UsageDaily.input_tokens + stmt.excluded.input_tokens,
            "output_tokens": UsageDaily.output_tokens + stmt.excluded.output_tokens,
            "est_cost_usd": UsageDaily.est_cost_usd + stmt.excluded.est_cost_usd,
        },
    ).returning(UsageDaily.input_tokens, UsageDaily.output_tokens)
    row = (await session.execute(upsert)).one()
    if commit:
        await session.commit()
    else:
        await session.flush()
    return DayTotals(int(row[0]), int(row[1]))


async def get_total_for_date(session: AsyncSession, user_id: UUID, day: date) -> int:
    result = await session.execute(
        select(UsageDaily).where(UsageDaily.user_id == user_id, UsageDaily.date == day)
    )
    usage = result.scalar_one_or_none()
    if not usage:
        return 0
    return usage.input_tokens + usage.output_tokens


async def reset_for_date(session: AsyncSession, user_id: UUID, day: date) -> None:
    """Zero out the daily usage row for a user/day (dev support).

    L9: reset_today_usage must clear both Redis and DB so the UI shows 0
    after reset. Deleting the row (vs zeroing) keeps the upsert path simple.
    """
    from sqlalchemy import delete as sa_delete

    await session.execute(
        sa_delete(UsageDaily).where(UsageDaily.user_id == user_id, UsageDaily.date == day)
    )
    await session.commit()


async def delete_before(session: AsyncSession, day: date, *, limit: int) -> int:
    """Delete up to ``limit`` daily usage rows older than ``day``; quota reads today's only."""
    old = select(UsageDaily.user_id, UsageDaily.date).where(UsageDaily.date < day).limit(limit)
    result = await session.execute(
        delete(UsageDaily).where(tuple_(UsageDaily.user_id, UsageDaily.date).in_(old))
    )
    return int(getattr(result, "rowcount", 0) or 0)
