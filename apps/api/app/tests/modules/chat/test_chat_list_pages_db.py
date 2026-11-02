"""The drawer's chat list pages past its first 200 chats (code-health audit CLAR-12).

``GET /chats`` read at most 200 chats and said nothing of the rest, so the 201st never
reached the drawer. The first page now names a cursor, and the next pages hold only the
older dated chats: pinned and archived ones came with the first.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.models.orm import Chat
from app.models.schemas import ChatListOut
from app.modules.chat import service as chats_service
from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import messages_repository as messages_repo
from app.repositories import users as users_repo


@pytest.mark.asyncio
async def test_the_chat_list_reads_on_after_its_first_page(db_session):
    user = await users_repo.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Many Chats",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    base = datetime(2026, 1, 5, tzinfo=UTC)
    chats = []
    for index in range(3):
        chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
        await messages_repo.create(
            db_session, chat_id=chat.id, user_id=user.id, role="user", content="hi"
        )
        await db_session.execute(
            update(Chat).where(Chat.id == chat.id).values(updated_at=base + timedelta(days=index))
        )
        chats.append(chat)
    await db_session.commit()

    first = await chats_service.list_chats_grouped(db_session, user, limit=2)
    assert first.next_cursor is not None
    rest = await chats_service.list_chats_grouped(
        db_session, user, limit=2, cursor=first.next_cursor
    )

    def dated(page: ChatListOut) -> list:
        return [
            chat.id
            for group in (page.today, page.yesterday, page.last_7_days, page.this_month)
            for chat in group
        ] + [chat.id for chat in page.older]

    assert dated(first) + dated(rest) == [chat.id for chat in reversed(chats)]
    assert rest.next_cursor is None
    assert rest.pinned == [] and rest.archived == []
