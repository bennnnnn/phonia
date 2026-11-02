"""Tests for paginated message listing."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.modules.conversation import messages_repository as messages_repo


def _msg(content: str, created_at: int):
    m = MagicMock()
    m.content = content
    m.created_at = created_at
    return m


@pytest.mark.asyncio
async def test_list_page_initial_returns_newest_chronological():
    session = AsyncMock()
    rows = [_msg("b", 2), _msg("a", 1)]
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)

    msgs, has_more = await messages_repo.list_page(session, uuid4(), limit=2)
    assert [m.content for m in msgs] == ["a", "b"]
    assert has_more is False


@pytest.mark.asyncio
async def test_list_page_initial_has_more_when_extra_row():
    session = AsyncMock()
    rows = [_msg("c", 3), _msg("b", 2), _msg("a", 1)]
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)

    msgs, has_more = await messages_repo.list_page(session, uuid4(), limit=2)
    assert [m.content for m in msgs] == ["b", "c"]
    assert has_more is True


@pytest.mark.asyncio
async def test_list_page_before_orders_by_created_at_and_id():
    """Same-timestamp pages must use id as a stable cursor tiebreaker."""
    session = AsyncMock()
    anchor_id = uuid4()
    anchor = MagicMock()
    anchor.id = anchor_id
    anchor.created_at = 5
    ref = MagicMock()
    ref.scalar_one_or_none.return_value = anchor
    page = MagicMock()
    page.scalars.return_value.all.return_value = [_msg("older", 5)]
    session.execute = AsyncMock(side_effect=[ref, page])

    await messages_repo.list_page(session, uuid4(), limit=10, before_id=anchor_id)

    second_stmt = session.execute.await_args_list[1].args[0]
    compiled = str(second_stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "created_at" in compiled.lower()
    assert "id" in compiled.lower()
    assert len(second_stmt._order_by_clauses) == 2
