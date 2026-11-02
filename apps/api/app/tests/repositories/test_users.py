"""Tests for app.repositories.users with mocked AsyncSession."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_get_by_id_returns_user(fake_session):
    """get_by_id should return the user from session.get."""
    from app.repositories.users import get_by_id

    user_id = uuid4()
    fake_user = MagicMock()
    fake_session.get.return_value = fake_user

    result = await get_by_id(fake_session, user_id)

    assert result is fake_user
    fake_session.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_id_returns_none(fake_session):
    """get_by_id should return None when user does not exist."""
    from app.repositories.users import get_by_id

    fake_session.get.return_value = None

    result = await get_by_id(fake_session, uuid4())

    assert result is None


async def test_refresh_for_update_locks_and_reloads_profile(fake_session):
    from app.repositories.users import refresh_for_update

    user = MagicMock()
    await refresh_for_update(fake_session, user)
    fake_session.refresh.assert_awaited_once_with(user, with_for_update=True)


@pytest.mark.asyncio
async def test_create_user(fake_session):
    """create should add, commit, refresh, and return the user."""
    from app.repositories.users import create

    await create(
        fake_session,
        google_sub="sub123",
        email="test@example.com",
        name="Test",
        avatar_url=None,
    )

    fake_session.add.assert_called_once()
    fake_session.commit.assert_awaited_once()
    fake_session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_applies_explicit_none():
    """Explicit None must clear nullable fields (omit key to leave unchanged)."""
    from app.repositories.users import update

    session = AsyncMock(spec=AsyncSession)
    user = MagicMock()
    user.custom_instructions = "keep me"
    user.location = "Seattle"
    user.name = "Ada"

    await update(session, user, custom_instructions=None, location=None)

    assert user.custom_instructions is None
    assert user.location is None
    assert user.name == "Ada"
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_delete_user_deletes_all_related(fake_session):
    """delete_user should delete messages, memories, usage, chats, and the user."""
    from app.repositories.users import delete_user

    user_id = uuid4()
    fake_user = MagicMock()
    fake_session.get.return_value = fake_user

    fake_session.execute.return_value = MagicMock(spec=CursorResult)

    await delete_user(fake_session, user_id)

    # Background memory writes lock User before Memory. Taking a Memory lock
    # before the User lock here can deadlock an account deletion against them.
    first_statement = fake_session.execute.await_args_list[0].args[0]
    compiled = first_statement.compile(dialect=postgresql.dialect())
    assert str(compiled).startswith("SELECT users.id")
    assert "WHERE users.id =" in str(compiled)
    assert str(compiled).endswith("FOR UPDATE")
    assert list(compiled.params.values()) == [user_id]

    # Account lock, related-row deletes, then user delete and commit.
    assert fake_session.execute.await_count >= 4
    fake_session.delete.assert_awaited_once_with(fake_user)
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_ids_by_plan_pages_by_id(fake_session):
    from app.repositories.users import list_ids_by_plan

    first = uuid4()
    second = uuid4()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [first, second]
    fake_session.execute.return_value = result

    ids = await list_ids_by_plan(fake_session, plan="pro", after_id=first, limit=25)

    assert ids == [first, second]
    stmt = fake_session.execute.await_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "users.plan" in sql
    assert "users.id >" in sql
