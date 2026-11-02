"""The drawer reads every pin on each open, so an account keeps a bounded number."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.models.orm import Chat, Message
from app.modules.chat import service as chats_service
from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import service as conversation_service
from app.repositories import users as users_repo

_CAP = 3


async def _user_with_chats(session, count: int):
    user = await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Pins",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    chats = [Chat(user_id=user.id, title=f"c{n}") for n in range(count)]
    session.add_all(chats)
    await session.flush()
    session.add_all(
        Message(chat_id=chat.id, user_id=user.id, role="user", content="hi") for chat in chats
    )
    await session.commit()
    return user, chats


@pytest.fixture
def small_cap():
    with (
        patch.object(chats_repo, "MAX_PINNED_CHATS", _CAP),
        patch.object(conversation_service, "MAX_PINNED_CHATS", _CAP),
    ):
        yield


@pytest.mark.asyncio
async def test_pinning_past_the_cap_is_refused_with_its_code(db_session, small_cap):
    user, chats = await _user_with_chats(db_session, _CAP + 1)
    user_id, chat_ids = user.id, [chat.id for chat in chats]
    for chat_id in chat_ids[:_CAP]:
        await chats_service.pin_chat(db_session, user, chat_id, pinned=True)

    with pytest.raises(chats_service.PinLimitError) as refused:
        await chats_service.pin_chat(db_session, user, chat_ids[_CAP], pinned=True)

    assert refused.value.status_code == 409
    assert refused.value.code == "pin_limit"
    assert refused.value.fields == {"limit": _CAP}
    pinned = await chats_repo.list_pinned(db_session, user_id)
    assert {chat.id for chat in pinned} == set(chat_ids[:_CAP])


@pytest.mark.asyncio
async def test_a_pinned_chat_pins_again_and_unpinning_frees_a_place(db_session, small_cap):
    user, chats = await _user_with_chats(db_session, _CAP + 1)
    for chat in chats[:_CAP]:
        await chats_service.pin_chat(db_session, user, chat.id, pinned=True)

    # Pinning a chat already pinned is not one more.
    await chats_service.pin_chat(db_session, user, chats[0].id, pinned=True)
    await chats_service.pin_chat(db_session, user, chats[0].id, pinned=False)
    await chats_service.pin_chat(db_session, user, chats[_CAP].id, pinned=True)

    pinned = await chats_repo.list_pinned(db_session, user.id)
    assert len(pinned) == _CAP
