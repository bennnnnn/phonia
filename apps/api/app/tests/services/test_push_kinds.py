"""Reminder pushes have their own switch under the master one."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.tests.services import push_cycle_support as push_cycle


def _where_sql(session: AsyncMock) -> str:
    """The first query the processor ran, as Postgres SQL."""
    statement = session.execute.await_args_list[0].args[0]
    return str(statement.compile(dialect=postgresql.dialect()))


def _empty_session() -> AsyncMock:
    session = AsyncMock()
    rows = MagicMock(all=MagicMock(return_value=[]))
    rows.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=rows)
    return session


@pytest.mark.asyncio
async def test_reminder_pushes_need_their_own_switch() -> None:
    session = _empty_session()
    assert await push_cycle.process_todo_reminders(session) == []
    sql = _where_sql(session)
    assert "users.push_notifications_enabled IS true" in sql
    assert "users.push_reminders_enabled IS true" in sql
