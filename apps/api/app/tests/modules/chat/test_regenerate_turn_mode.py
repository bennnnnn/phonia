"""A regenerate reads its line against the reply before it, not the reply it redoes.

The regenerate's window still ends with the reply being replaced. Read against it, a
"yes" to "Would you like me to set up that reminder for 7:00 PM?" answered "Setting that
reminder for you now!", so the To-do block never loaded and the redone reply was the
live bug again (2026-10-25).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import fakeredis.aioredis

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.models.orm import Chat, Message, User
from app.modules.chat.turn_deps import default_deps
from app.modules.chat.turn_load import load_regenerate_turn
from app.repositories import users as users_repo

_OFFER = "Would you like me to set up that **Practice** reminder for tomorrow at 7:00 PM?"


async def test_a_regenerated_yes_still_accepts_the_offer() -> None:
    await engine.dispose(close=False)
    now = datetime.now(UTC)
    lines = [
        ("user", "wait you can't do reminders?"),
        ("assistant", _OFFER),
        ("user", "yes"),
        ("assistant", "Setting that reminder for you now!"),
    ]
    async with SessionLocal() as session:
        user = User(email=f"{uuid4()}@example.com", name="Regenerate", google_sub=str(uuid4()))
        session.add(user)
        await session.flush()
        chat = Chat(user_id=user.id, title="Offer")
        session.add(chat)
        await session.flush()
        session.add_all(
            Message(
                chat_id=chat.id,
                user_id=user.id,
                role=role,
                content=content,
                model="free-chat" if role == "assistant" else None,
                created_at=now - timedelta(seconds=len(lines) - index),
            )
            for index, (role, content) in enumerate(lines)
        )
        await session.commit()
        user_id, chat_id = user.id, chat.id
    try:
        turn = await load_regenerate_turn(
            default_deps(),
            fakeredis.aioredis.FakeRedis(decode_responses=True),
            get_settings(),
            user_id=user_id,
            chat_id=chat_id,
            model_alias=None,
        )
        assert turn.content == "yes"
        assert turn.turn_mode.accepted_offer
        assert turn.turn_mode.rich_context
    finally:
        async with SessionLocal() as session:
            await users_repo.delete_user(session, user_id)
        await engine.dispose(close=False)
