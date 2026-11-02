"""Conversation metadata regressions; SQL uses only an in-memory SQLite table."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.orm import Chat, Message
from app.models.schemas import ChatOut, SearchResultItem
from app.modules.chat import service as chats_service
from app.modules.chat import titles as topic
from app.modules.conversation import chats_repository as chats_repo


@pytest.fixture
def metadata_session():
    """Run the actual ORM statements locally without a network/database dependency."""
    engine = create_engine("sqlite://")
    Chat.__table__.create(engine)
    Message.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as sync_session:
        session = AsyncMock(spec=AsyncSession)
        session.execute.side_effect = sync_session.execute
        session.get.side_effect = sync_session.get
        session.commit.side_effect = sync_session.commit
        session.refresh.side_effect = sync_session.refresh
        yield sync_session, session
    engine.dispose()


@pytest.mark.asyncio
async def test_topic_preserves_manual_rename_after_stale_read(metadata_session):
    sync_session, session = metadata_session
    owner_id = uuid4()
    chat = Chat(user_id=owner_id, model="auto", title=None)
    sync_session.add(chat)
    sync_session.commit()
    chat_id = chat.id

    # A title worker has loaded the empty title; a separate rename commits before
    # it writes. Keep the worker's ORM identity stale, as two requests would be.
    sync_session.execute(
        update(Chat)
        .where(Chat.id == chat_id)
        .values(title="My chosen title")
        .execution_options(synchronize_session=False)
    )
    sync_session.commit()
    assert chat.title is None
    session.__aenter__.return_value = session
    with (
        patch.object(topic, "SessionLocal", return_value=session),
        patch.object(topic, "generate_title", AsyncMock(return_value="Generated title")),
    ):
        applied = await topic.generate_chat_title(
            Settings(), chat_id, "User question", "Assistant answer", user_id=owner_id
        )
    assert applied is False

    sync_session.expire_all()
    assert sync_session.get(Chat, chat_id).title == "My chosen title"


@pytest.mark.asyncio
async def test_pinned_chat_stays_visible_past_recent_list_limit(metadata_session):
    sync_session, session = metadata_session
    owner_id = uuid4()
    now = datetime.now(UTC)
    pinned = Chat(user_id=owner_id, pinned=True, updated_at=now - timedelta(days=30))
    recent = Chat(user_id=owner_id, updated_at=now)
    sync_session.add_all([pinned, recent])
    sync_session.flush()
    sync_session.add_all(
        [
            Message(chat_id=chat.id, user_id=owner_id, role="user", content="hello")
            for chat in [pinned, recent]
        ]
    )
    sync_session.commit()

    result = await chats_repo.list_for_user(session, owner_id, limit=1)

    assert [chat.id for chat in result] == [pinned.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["empty", "blank", "titled", "other_owner", "deleted"])
async def test_generated_title_write_respects_current_row(metadata_session, state):
    sync_session, session = metadata_session
    owner_id = uuid4()
    chat = Chat(user_id=owner_id, title="" if state == "blank" else None)
    if state == "titled":
        chat.title = "User title"
    sync_session.add(chat)
    sync_session.commit()
    chat_id = chat.id
    if state == "deleted":
        sync_session.delete(chat)
        sync_session.commit()

    applied = await chats_repo.set_title_if_empty(
        session,
        chat_id,
        "Generated title",
        user_id=uuid4() if state == "other_owner" else owner_id,
        commit=False,
    )

    assert applied is (state in {"empty", "blank"})
    session.commit.assert_not_awaited()
    sync_session.expire_all()
    persisted = sync_session.get(Chat, chat_id)
    if state == "deleted":
        assert persisted is None
    elif state == "titled":
        assert persisted.title == "User title"
    elif state == "other_owner":
        assert persisted.title is None
    else:
        assert persisted.title == "Generated title"


@pytest.mark.asyncio
async def test_archive_clears_pin_committed_after_stale_read(metadata_session):
    sync_session, session = metadata_session
    chat = Chat(user_id=uuid4(), pinned=False)
    sync_session.add(chat)
    sync_session.commit()
    sync_session.execute(
        update(Chat)
        .where(Chat.id == chat.id)
        .values(pinned=True)
        .execution_options(synchronize_session=False)
    )
    sync_session.commit()
    assert chat.pinned is False

    archived = await chats_repo.set_archived(session, chat, True)

    assert archived.archived is True
    assert archived.pinned is False


@pytest.mark.asyncio
async def test_pin_does_not_repin_concurrently_archived_chat(metadata_session):
    sync_session, session = metadata_session
    chat = Chat(user_id=uuid4(), pinned=False, archived=False)
    sync_session.add(chat)
    sync_session.commit()
    sync_session.execute(
        update(Chat)
        .where(Chat.id == chat.id)
        .values(archived=True)
        .execution_options(synchronize_session=False)
    )
    sync_session.commit()
    assert chat.archived is False

    result = await chats_repo.set_pinned(session, chat, True)

    assert result.archived is True
    assert result.pinned is False


@pytest.mark.asyncio
async def test_pin_service_rejects_archived_chat(metadata_session):
    sync_session, session = metadata_session
    chat = Chat(user_id=uuid4(), archived=True, pinned=False)
    sync_session.add(chat)
    sync_session.commit()
    user = MagicMock(id=chat.user_id)

    with pytest.raises(chats_service.ChatsError) as exc:
        await chats_service.pin_chat(session, user, chat.id, pinned=True)

    assert exc.value.status_code == 409
    assert chat.pinned is False
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pin_service_reports_concurrent_archive(metadata_session):
    sync_session, session = metadata_session
    chat = Chat(user_id=uuid4(), archived=False, pinned=False)
    sync_session.add(chat)
    sync_session.commit()
    user = MagicMock(id=chat.user_id)
    sync_session.execute(
        update(Chat)
        .where(Chat.id == chat.id)
        .values(archived=True)
        .execution_options(synchronize_session=False)
    )
    sync_session.commit()
    assert chat.archived is False

    with pytest.raises(chats_service.ChatsError) as exc:
        await chats_service.pin_chat(session, user, chat.id, pinned=True)

    assert exc.value.status_code == 409
    assert chat.archived is True
    assert chat.pinned is False


@pytest.mark.asyncio
async def test_pin_unpin_archive_and_unarchive(metadata_session):
    sync_session, session = metadata_session
    chat = Chat(user_id=uuid4(), archived=False, pinned=False)
    sync_session.add(chat)
    sync_session.commit()

    await chats_repo.set_pinned(session, chat, True)
    assert chat.pinned is True
    await chats_repo.set_pinned(session, chat, False)
    assert chat.pinned is False
    await chats_repo.set_pinned(session, chat, True)
    await chats_repo.set_archived(session, chat, True)
    assert chat.archived is True
    assert chat.pinned is False
    await chats_repo.set_archived(session, chat, False)
    assert chat.archived is False
    assert chat.pinned is False


@pytest.mark.parametrize("title", ["AI", "A", "Chat", "New chat"])
def test_manual_title_survives_chat_and_search_responses(title):
    now = datetime.now(UTC)
    chat_id = uuid4()
    chat = ChatOut(id=chat_id, title=title, model="auto", created_at=now, updated_at=now)
    result = SearchResultItem(
        chat_id=chat_id, chat_title=title, content="hello", role="user", created_at=now
    )

    assert chat.title == title
    assert result.chat_title == title
