"""Account delete and "delete all chats" delete in bounded, id-batched statements."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.orm import Chat, Message
from app.modules.conversation import chats_repository as chats_repo
from app.repositories import batch_delete
from app.repositories import users as users_repo


async def _user_with_chats(session, *, chats: int, messages_each: int):
    user = await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Batch",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    for _ in range(chats):
        chat = Chat(user_id=user.id, title="t")
        session.add(chat)
        await session.flush()
        session.add_all(
            Message(chat_id=chat.id, user_id=user.id, role="user", content="m")
            for _ in range(messages_each)
        )
    await session.commit()
    return user


def _small_batches():
    """Two rows a statement, so a few rows take several."""
    kwdefaults = batch_delete.delete_in_batches.__kwdefaults__
    assert kwdefaults is not None
    return patch.dict(kwdefaults, {"batch": 2})


async def _count(session, model, user_id) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(model).where(model.user_id == user_id))
        or 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [1, 3, 7, 1000])
async def test_delete_in_batches_deletes_every_selected_row_and_no_other(db_session, batch):
    user = await _user_with_chats(db_session, chats=2, messages_each=5)
    keep = await _user_with_chats(db_session, chats=1, messages_each=4)

    deleted = await batch_delete.delete_in_batches(
        db_session, Message.id, select(Message.id).where(Message.user_id == user.id), batch=batch
    )

    assert deleted == 10
    assert await _count(db_session, Message, user.id) == 0
    assert await _count(db_session, Message, keep.id) == 4


@pytest.mark.asyncio
async def test_delete_all_chats_goes_in_batches(db_session):
    user = await _user_with_chats(db_session, chats=5, messages_each=3)
    keep = await _user_with_chats(db_session, chats=1, messages_each=2)

    with _small_batches():
        count = await chats_repo.delete_all_for_user(db_session, user.id)

    assert count == 5
    assert await _count(db_session, Chat, user.id) == 0
    assert await _count(db_session, Message, user.id) == 0
    assert await _count(db_session, Chat, keep.id) == 1
    assert await _count(db_session, Message, keep.id) == 2


@pytest.mark.asyncio
async def test_account_rows_delete_in_batches(db_session):
    user = await _user_with_chats(db_session, chats=4, messages_each=3)
    keep = await _user_with_chats(db_session, chats=1, messages_each=2)
    user_id = user.id

    with _small_batches():
        await users_repo.delete_user(db_session, user_id)

    assert await users_repo.get_by_id(db_session, user_id) is None
    assert await _count(db_session, Chat, user_id) == 0
    assert await _count(db_session, Message, user_id) == 0
    assert await _count(db_session, Message, keep.id) == 2
