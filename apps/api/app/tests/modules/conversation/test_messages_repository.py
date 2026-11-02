"""Tests for chat's messages repository with mocked AsyncSession."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_create_message(fake_session):
    """create should add, commit, refresh, and return the message."""
    from app.modules.conversation.messages_repository import create

    chat_id = uuid4()
    user_id = uuid4()

    _ = await create(
        fake_session,
        chat_id=chat_id,
        user_id=user_id,
        role="user",
        content="Hello",
        model="free-chat",
    )

    fake_session.add.assert_called_once()
    fake_session.commit.assert_awaited_once()
    fake_session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_count_for_chat(fake_session):
    """count_for_chat should return the count of messages."""
    from app.modules.conversation.messages_repository import count_for_chat

    chat_id = uuid4()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 5
    fake_session.execute.return_value = mock_result

    result = await count_for_chat(fake_session, chat_id)

    assert result == 5
    fake_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_last_user(fake_session):
    """get_last_user should return the most recent user message."""
    from app.modules.conversation.messages_repository import get_last_user

    chat_id = uuid4()
    mock_message = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_message
    fake_session.execute.return_value = mock_result

    result = await get_last_user(fake_session, chat_id)

    assert result is mock_message
    fake_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_feedback(fake_session):
    """set_feedback should update the feedback field of a message."""
    from app.modules.conversation.messages_repository import set_feedback

    msg_id = uuid4()
    chat_id = uuid4()
    mock_message = MagicMock(role="assistant")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_message
    fake_session.execute.return_value = mock_result

    result = await set_feedback(fake_session, msg_id, chat_id, "like")

    assert result is mock_message
    assert mock_message.feedback == "like"
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_feedback_leaves_a_user_message_unrated(fake_session):
    """Only a reply is rated: a user message comes back unchanged and nothing is written."""
    from app.modules.conversation.messages_repository import set_feedback

    mock_message = MagicMock(role="user", feedback=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_message
    fake_session.execute.return_value = mock_result

    result = await set_feedback(fake_session, uuid4(), uuid4(), "up")

    assert result is mock_message
    assert mock_message.feedback is None
    fake_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_rating_a_user_message_is_refused(fake_session, fake_redis):
    from app.modules.chat.service import ChatsError, set_message_feedback

    message = MagicMock(role="user", feedback=None)
    result = MagicMock()
    result.scalar_one_or_none.return_value = message
    fake_session.execute.return_value = result

    with pytest.raises(ChatsError) as refused:
        await set_message_feedback(
            fake_session, fake_redis, MagicMock(id=uuid4()), uuid4(), uuid4(), "up"
        )
    assert refused.value.status_code == 422
    assert message.feedback is None


@pytest.mark.asyncio
async def test_update_content(fake_session):
    from app.modules.conversation.messages_repository import update_content

    mock_message = MagicMock()
    result = await update_content(fake_session, mock_message, "new body")

    assert result is mock_message
    assert mock_message.content == "new body"
    fake_session.commit.assert_awaited_once()
    fake_session.refresh.assert_awaited_once_with(mock_message)


@pytest.mark.asyncio
async def test_list_user_contents_since_sql_is_user_only():
    from sqlalchemy.dialects import postgresql

    from app.modules.conversation.messages_repository import list_user_contents_since

    session = AsyncMock()
    captured: dict = {}

    async def _capture(stmt):
        captured["stmt"] = stmt
        result = MagicMock()
        result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
        return result

    session.execute = _capture
    await list_user_contents_since(session, uuid4(), limit=12)

    compiled = captured["stmt"].compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()
    assert "role" in sql
    assert "user" in sql


# ── messages.count_for_chat — SQL scalar path ─────────────────────────────────


@pytest.mark.asyncio
async def test_count_for_chat_uses_scalar():
    from unittest.mock import MagicMock

    from app.modules.conversation import messages_repository as messages_repo

    session = AsyncMock()
    # scalar_one is a sync call on the execute result
    result_mock = MagicMock()
    result_mock.scalar_one.return_value = 42
    session.execute.return_value = result_mock

    count = await messages_repo.count_for_chat(session, uuid4())

    assert count == 42
    session.execute.assert_awaited_once()
    result_mock.scalar_one.assert_called_once()
