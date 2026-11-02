"""A turn whose pooled connection died unnoticed still loads and saves (pool_liveness.run_unit).

The pool trusts a connection used moments ago. When the server ended it and asyncpg
has not read the close yet, the next statement on it fails. The turn's reads, the
save of its message and the save of its reply each run once more on a new
connection instead of failing the turn. These run on the app's own engine and the
test Postgres, where ``pg_terminate_backend`` ends the pool's connection.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import asyncpg
import fakeredis.aioredis
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from app.core import pool_liveness
from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.models.orm import Chat, Message, User
from app.modules.chat.turn_deps import default_deps
from app.modules.chat.turn_load import load_new_turn, load_regenerate_turn
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.chat.turn_prep.persist import UserTurn, persist_user_turn
from app.modules.chat.turn_settle import finalize_stream_turn_db
from app.modules.chat.turn_timing import TurnTimingTracker
from app.repositories import users as users_repo

_RETRIED = "running it again"


@dataclass
class _Seeded:
    user: User
    chat: Chat


@pytest.fixture
async def seeded() -> AsyncIterator[_Seeded]:
    """A user and a chat holding one exchange, committed for the pool to read."""
    await engine.dispose(close=False)
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        user = User(email=f"{uuid4()}@example.com", name="Dead Pool", google_sub=str(uuid4()))
        session.add(user)
        await session.flush()
        chat = Chat(user_id=user.id, title="Pooled")
        session.add(chat)
        await session.flush()
        session.add_all(
            [
                Message(
                    chat_id=chat.id,
                    user_id=user.id,
                    role="user",
                    content="What is 2 + 2?",
                    created_at=now - timedelta(seconds=2),
                ),
                Message(
                    chat_id=chat.id,
                    user_id=user.id,
                    role="assistant",
                    content="4",
                    model="free-chat",
                    created_at=now - timedelta(seconds=1),
                ),
            ]
        )
        await session.commit()
    try:
        yield _Seeded(user=user, chat=chat)
    finally:
        async with SessionLocal() as session:
            await users_repo.delete_user(session, user.id)
        await engine.dispose(close=False)


@pytest.fixture
async def redis() -> AsyncIterator[Any]:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


async def _pool_holds_a_dead_connection(monkeypatch: pytest.MonkeyPatch) -> int:
    """The pool's only connection lost its backend, and its next checkout cannot tell."""
    await engine.dispose(close=False)
    async with engine.connect() as conn:
        pid = int((await conn.execute(text("SELECT pg_backend_pid()"))).scalar_one())
        driver = (await conn.get_raw_connection()).driver_connection
        assert driver is not None
    dsn = make_url(get_settings().database_url).set(drivername="postgresql")
    killer = await asyncpg.connect(dsn.render_as_string(hide_password=False))
    try:
        await killer.execute("SELECT pg_terminate_backend($1)", pid)
    finally:
        await killer.close()
    for _ in range(100):
        if driver.is_closed():
            break
        await asyncio.sleep(0.01)
    # As if the close were still on its way: the checkout trusts the connection.
    monkeypatch.setattr(pool_liveness, "server_closed", lambda _driver: False)
    return pid


async def test_a_turn_loads_when_its_pooled_connection_died_unnoticed(
    seeded: _Seeded, redis: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _pool_holds_a_dead_connection(monkeypatch)

    turn = await load_new_turn(
        default_deps(),
        redis,
        get_settings(),
        TurnTimingTracker(),
        user_id=seeded.user.id,
        chat_id=seeded.chat.id,
        content="And what is 3 + 3?",
        model_alias=None,
        user=None,
        chat=None,
        skip_usage_seed=True,
    )

    assert turn.user.id == seeded.user.id
    assert turn.chat.id == seeded.chat.id
    assert [m.content for m in turn.recent] == ["What is 2 + 2?", "4"]
    assert _RETRIED in caplog.text


async def test_a_regenerate_loads_when_its_pooled_connection_died_unnoticed(
    seeded: _Seeded, redis: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _pool_holds_a_dead_connection(monkeypatch)

    turn = await load_regenerate_turn(
        default_deps(),
        redis,
        get_settings(),
        user_id=seeded.user.id,
        chat_id=seeded.chat.id,
        model_alias=None,
    )

    assert turn.content == "What is 2 + 2?"
    assert turn.backup is not None and turn.backup.content == "4"
    assert _RETRIED in caplog.text


async def test_the_message_saves_when_its_pooled_connection_died_unnoticed(
    seeded: _Seeded, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _pool_holds_a_dead_connection(monkeypatch)
    message_id = uuid4()

    await persist_user_turn(
        UserTurn(
            user_id=seeded.user.id,
            chat_id=seeded.chat.id,
            message_id=message_id,
            content="And what is 3 + 3?",
            stored_content="And what is 3 + 3?",
            attachment_ids=None,
            has_image_attachment=False,
            model_alias=None,
            recent_messages=None,
            lesson_active=False,
        ),
        get_settings(),
        None,
    )

    async with SessionLocal() as session:
        saved = await session.scalar(select(Message.content).where(Message.id == message_id))
    assert saved == "And what is 3 + 3?"
    assert _RETRIED in caplog.text


async def test_the_reply_saves_when_its_pooled_connection_died_unnoticed(
    seeded: _Seeded, redis: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _pool_holds_a_dead_connection(monkeypatch)
    reply_id = uuid4()
    ctx = StreamContext(
        user_id=seeded.user.id,
        chat_id=seeded.chat.id,
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "And what is 3 + 3?"}],
        run_title=False,
        user_message_content="And what is 3 + 3?",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
        user=seeded.user,
        assistant_message_id=reply_id,
    )

    await finalize_stream_turn_db(
        default_deps(), redis, get_settings(), ctx, "6", {"input": 10, "output": 1}, TurnOutcome()
    )

    async with SessionLocal() as session:
        saved = await session.scalar(select(Message.content).where(Message.id == reply_id))
    assert saved == "6"
    assert _RETRIED in caplog.text
