from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.modules.attachments.chunks_repository import replace_chunks


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["deleted_chat", "deleted_file", "unverified", "moved_chat"])
async def test_late_index_does_not_replace_chunks_for_a_changed_attachment(state):
    user_id, attachment_id, chat_id = uuid4(), uuid4(), uuid4()
    row = SimpleNamespace(verified_at=object(), message_id=uuid4())
    values = [chat_id, row, chat_id]
    if state == "deleted_chat":
        values = [None]
    elif state == "deleted_file":
        values = [chat_id, None]
    elif state == "unverified":
        row.verified_at = None
    else:
        values[-1] = uuid4()
    session = AsyncMock()
    session.scalar.side_effect = values
    session.add = MagicMock()

    stored = await replace_chunks(
        session,
        user_id=user_id,
        attachment_id=attachment_id,
        chat_id=chat_id,
        chunks=[(0, "stale text", [0.1] * 1536)],
    )

    assert stored is False
    session.execute.assert_not_awaited()
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_index_locks_parent_before_attachment_and_replaces_once():
    from sqlalchemy.dialects import postgresql

    user_id, attachment_id, chat_id = uuid4(), uuid4(), uuid4()
    session = AsyncMock()
    session.scalar.side_effect = [
        chat_id,
        SimpleNamespace(verified_at=object(), message_id=uuid4()),
        chat_id,
    ]
    session.add = MagicMock()

    assert (
        await replace_chunks(
            session,
            user_id=user_id,
            attachment_id=attachment_id,
            chat_id=chat_id,
            chunks=[(0, "current text", [0.1] * 1536)],
        )
        is True
    )

    statements = [
        str(call.args[0].compile(dialect=postgresql.dialect()))
        for call in session.scalar.call_args_list
    ]
    assert "FOR KEY SHARE" in statements[0]
    assert "chats.user_id" in statements[0]
    assert "FOR UPDATE" in statements[1]
    assert "attachments.user_id" in statements[1]
    session.add.assert_called_once()
    session.commit.assert_awaited_once()
