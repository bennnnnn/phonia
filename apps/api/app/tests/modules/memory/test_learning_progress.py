from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.orm import Chat, Memory
from app.modules.memory import learning_progress
from app.repositories import users as users_repo

LINE = 'Learning Python: reached Lesson 1, Variables (chat "Python"). Covered: Variables'
NEXT = 'Learning Python: reached Lesson 2, Lists (chat "Python"). Covered: Variables; Lists'


class _Reuse:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return None


@pytest.fixture
def env(db_session):
    with (
        patch.object(learning_progress, "SessionLocal", lambda: _Reuse(db_session)),
        patch.object(learning_progress, "acquire_memory_write_lock", AsyncMock(return_value="t")),
        patch.object(learning_progress, "release_memory_write_lock", AsyncMock()),
    ):
        yield db_session


async def _user_and_chat(session, **user_fields):
    user = await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    for key, value in user_fields.items():
        setattr(user, key, value)
    chat = Chat(user_id=user.id, title="Python")
    session.add(chat)
    await session.flush()
    return user, chat


async def _lines(session, user_id):
    rows = await session.execute(select(Memory).where(Memory.user_id == user_id))
    return [(m.text, m.topic, m.status) for m in rows.scalars()]


async def _record(user, chat, text, started_at=None):
    return await learning_progress.record_learning_progress(
        Settings(semantic_memory_enabled=False),
        user_id=user.id,
        chat_id=chat.id,
        text=text,
        started_at=started_at,
    )


@pytest.mark.asyncio
async def test_adds_one_line_then_rewrites_it_in_place(env):
    user, chat = await _user_and_chat(env)
    await _record(user, chat, LINE)
    await _record(user, chat, NEXT)
    assert await _lines(env, user.id) == [(NEXT, "goals", "active")]


@pytest.mark.asyncio
async def test_a_hand_edit_after_the_lessons_began_keeps_it_out(env):
    started = datetime.now(UTC) - timedelta(days=2)
    user, chat = await _user_and_chat(env, memory_edited_at=started + timedelta(days=1))
    await _record(user, chat, LINE, started_at=started)
    assert await _lines(env, user.id) == []


@pytest.mark.asyncio
async def test_memory_off_writes_nothing(env):
    user, chat = await _user_and_chat(env, memory_enabled=False)
    await _record(user, chat, LINE)
    assert await _lines(env, user.id) == []


@pytest.mark.asyncio
async def test_a_muted_line_stays_as_the_user_left_it(env):
    user, chat = await _user_and_chat(env)
    await _record(user, chat, LINE)
    row = (await env.execute(select(Memory).where(Memory.user_id == user.id))).scalar_one()
    row.status = "muted"
    await env.flush()
    await _record(user, chat, NEXT)
    assert await _lines(env, user.id) == [(LINE, "goals", "muted")]


@pytest.mark.asyncio
async def test_a_busy_memory_asks_for_a_retry(env):
    user, chat = await _user_and_chat(env)
    with patch.object(learning_progress, "acquire_memory_write_lock", AsyncMock(return_value=None)):
        assert await _record(user, chat, LINE) == "skipped_lock"
