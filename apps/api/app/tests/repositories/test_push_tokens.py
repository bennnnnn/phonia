"""Tests for app.repositories.push_tokens."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_list_for_users_returns_empty_without_querying(fake_session):
    from app.repositories.push_tokens import list_for_users

    result = await list_for_users(fake_session, [])

    assert result == []
    fake_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_list_for_users_issues_a_single_batched_query(fake_session):
    from app.repositories.push_tokens import list_for_users

    tokens = [MagicMock(), MagicMock()]
    fake_session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=tokens)))
    )

    result = await list_for_users(fake_session, [uuid4(), uuid4()])

    assert result == tokens
    fake_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_push_tokens_upsert_and_delete(fake_session):
    from app.repositories import push_tokens as repo

    user_id = uuid4()
    token = "ExponentPushToken[abc]"
    existing = MagicMock()
    existing.user_id = user_id
    existing.device_id = None
    fake_session.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=existing)
    )

    updated = await repo.upsert(
        fake_session,
        user_id=user_id,
        expo_push_token=token,
        platform="ios",
        device_id="device-1",
    )
    assert updated.user_id == user_id
    fake_session.commit.assert_awaited()

    fake_session.execute.return_value = MagicMock(rowcount=1)
    assert await repo.delete_token(fake_session, user_id, token) is True
    assert await repo.delete_by_token(fake_session, token) == 1

    fake_session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[existing])))
    )
    rows = await repo.list_for_user(fake_session, user_id)
    assert rows == [existing]
