"""What other modules read of a user's chats (``chat.history``, audit ARCH-08)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.modules.conversation import chats_repository, history
from app.tests.fakes import fake_session


@pytest.mark.asyncio
async def test_the_export_reads_archived_chats_with_their_summaries() -> None:
    session, user_id = fake_session(), uuid4()
    with patch.object(chats_repository, "list_for_user", AsyncMock(return_value=[])) as read:
        await history.chats_for_export(session, user_id, limit=50)
    read.assert_awaited_once_with(
        session, user_id, limit=50, include_archived=True, with_summary=True
    )
