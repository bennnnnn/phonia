"""Tests for app.modules.todos.repository."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _todo(todo_id, *, sort_order=None, topic="General"):
    item = MagicMock()
    item.id = todo_id
    item.sort_order = sort_order
    item.topic = topic
    return item


# ── todos repository ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_todos_repo_create():
    from app.modules.todos.repository import create

    todo_mock = MagicMock()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    with (
        patch("app.modules.todos.repository.next_sort_order", AsyncMock(return_value=1)),
        patch("app.modules.todos.repository.TodoItem", return_value=todo_mock),
    ):
        result = await create(session, user_id=uuid4(), content="Task 1")
    assert result is todo_mock
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_todos_repo_create_commit_false_flushes_without_commit():
    from app.modules.todos.repository import create

    todo_mock = MagicMock()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    with (
        patch("app.modules.todos.repository.next_sort_order", AsyncMock(return_value=1)),
        patch("app.modules.todos.repository.TodoItem", return_value=todo_mock),
    ):
        result = await create(session, user_id=uuid4(), content="Task 1", commit=False)
    assert result is todo_mock
    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_todos_repo_update_unchecks():
    from app.modules.todos.repository import update

    todo = MagicMock()
    todo.checked = True
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    updated = await update(session, todo, checked=False)
    assert updated.checked is False
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_todos_repo_delete_not_found():
    from app.modules.todos.repository import delete_by_id

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    session.execute = AsyncMock(return_value=mock_result)

    result = await delete_by_id(session, uuid4(), uuid4())
    assert result is False
