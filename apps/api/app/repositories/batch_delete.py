"""Deletes in bounded, id-batched statements.

An account delete or "delete all chats" removed a heavy account's messages in one
statement, which could run past the database command timeout and then fail the same
way on every retry. Each statement here deletes at most ``batch`` rows picked by id, so
no single one grows with the account; the caller's transaction still makes the whole
delete commit or roll back as one.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Select, delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

DELETE_BATCH = 1000


async def delete_in_batches(
    session: AsyncSession,
    id_column: InstrumentedAttribute[Any],
    ids: Select[Any],
    *,
    batch: int = DELETE_BATCH,
) -> int:
    """Delete the rows ``ids`` selects (one id column), ``batch`` at a time; the count.

    No commit: the caller owns the transaction. The session's identity map is not
    synchronized, so callers delete rows they have not loaded.
    """
    table = id_column.class_
    deleted = 0
    while True:
        result = cast(
            CursorResult[Any],
            await session.execute(
                delete(table)
                .where(id_column.in_(ids.limit(batch)))
                .execution_options(synchronize_session=False)
            ),
        )
        count = int(result.rowcount or 0)
        deleted += count
        if count < batch:
            return deleted
