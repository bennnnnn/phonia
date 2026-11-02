from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.orm import Chat, Memory, Message
from app.modules.memory import crud, history_scan, locks
from app.modules.memory.extraction_workflow import extract_history_chat
from app.modules.memory.schemas import MemoryFactUpdateResult
from app.repositories import users as users_repo


def _user(**kwargs):
    defaults = {"id": uuid4(), "memory_enabled": True, "memory_history_scanned_at": None}
    return SimpleNamespace(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_request_history_scan_queues_once(fake_redis):
    user = _user()
    enqueue = AsyncMock()
    with patch("app.modules.memory.history_scan.jobs.enqueue", enqueue):
        first = await history_scan.request_history_scan(fake_redis, user)
        second = await history_scan.request_history_scan(fake_redis, user)

    assert (first, second) == (True, True)
    enqueue.assert_awaited_once()
    assert enqueue.await_args.args[1:] == ("memory_history_scan", {"user_id": str(user.id)})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user",
    [
        _user(memory_enabled=False),
        _user(memory_history_scanned_at=datetime(2026, 9, 1, tzinfo=UTC)),
    ],
)
async def test_request_history_scan_skips_when_off_or_done(fake_redis, user):
    enqueue = AsyncMock()
    with patch("app.modules.memory.history_scan.jobs.enqueue", enqueue):
        assert await history_scan.request_history_scan(fake_redis, user) is False
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_history_scan_waits_while_missed_chats_are_held(fake_redis):
    user = _user()
    await fake_redis.set(f"memory:history_scan:{user.id}", "retry", ex=60)
    enqueue = AsyncMock()
    with patch("app.modules.memory.history_scan.jobs.enqueue", enqueue):
        assert await history_scan.request_history_scan(fake_redis, user) is False
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_history_scan_can_queue_again_after_a_failed_enqueue(fake_redis):
    user = _user()
    enqueue = AsyncMock(side_effect=[RuntimeError("redis stream down"), None])
    with patch("app.modules.memory.history_scan.jobs.enqueue", enqueue):
        assert await history_scan.request_history_scan(fake_redis, user) is False
        assert await history_scan.request_history_scan(fake_redis, user) is True
    assert enqueue.await_count == 2


async def _make_user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


class _Reuse:
    """Hand the test's session to code that opens its own sessions."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return None


@pytest.fixture
def scan_env(db_session, fake_redis):
    """Run the scan against the test database and an in-memory Redis."""
    with (
        patch("app.modules.memory.history_scan.SessionLocal", lambda: _Reuse(db_session)),
        patch("app.modules.memory.history_scan.get_redis_client", lambda: fake_redis),
        patch("app.core.jobs.LOCK_RETRY_BACKOFF_S", 0),
    ):
        yield fake_redis


async def _chats_with_lines(session, user, count: int) -> list[Chat]:
    """``count`` chats with one user line each, newest first."""
    now = datetime.now(UTC)
    chats = [
        Chat(user_id=user.id, title=f"Chat {index}", updated_at=now - timedelta(days=index))
        for index in range(count)
    ]
    session.add_all(chats)
    await session.flush()
    session.add_all(
        [
            Message(chat_id=chat.id, user_id=user.id, role="user", content="I run every morning")
            for chat in chats
        ]
    )
    await session.flush()
    return chats


@pytest.mark.asyncio
async def test_a_finished_scan_retires_every_cached_copy_of_the_user(
    db_session, scan_env, user_generation_redis
):
    """A copy still saying "not scanned" would ask for the scan again (core/user_cache)."""
    from app.core import user_cache

    user = await _make_user(db_session)
    key = user_cache.generation_key(user.id)
    assert await user_generation_redis.get(key) is None

    with patch("app.modules.memory.history_scan.extract_history_chat", AsyncMock()):
        await history_scan.scan_recent_chats(Settings(), user_id=user.id)

    assert await user_generation_redis.get(key) is not None


@pytest.mark.asyncio
async def test_a_scan_asked_for_a_stamped_user_publishes_again(
    db_session, scan_env, user_generation_redis
):
    """A copy that still says "not scanned" asked, or the stamp's publish failed and
    the job is retried: either way the copies are retired and nothing is read."""
    from app.core import user_cache

    user = await _make_user(db_session)
    user.memory_history_scanned_at = datetime.now(UTC)
    await db_session.flush()
    await scan_env.set(f"memory:history_scan:{user.id}", "queued")
    extract = AsyncMock()

    with patch("app.modules.memory.history_scan.extract_history_chat", extract):
        await history_scan.scan_recent_chats(Settings(), user_id=user.id)

    assert await user_generation_redis.get(user_cache.generation_key(user.id)) is not None
    assert await scan_env.keys("memory:history_scan*") == []
    extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_scan_reads_recent_chats_with_user_lines_once(db_session, scan_env):
    user = await _make_user(db_session)
    talk = Chat(user_id=user.id, title="Recall app")
    other = Chat(user_id=user.id, title="Spanish notes")
    empty = Chat(user_id=user.id, title="Nothing yet")
    db_session.add_all([talk, other, empty])
    await db_session.flush()
    db_session.add_all(
        [
            Message(
                chat_id=talk.id,
                user_id=user.id,
                role="user",
                content="I'm building Recall with Expo",
            ),
            Message(chat_id=talk.id, user_id=user.id, role="assistant", content="Nice!"),
            Message(chat_id=other.id, user_id=user.id, role="user", content="hola"),
        ]
    )
    await db_session.flush()

    extract = AsyncMock(return_value=None)
    with patch("app.modules.memory.history_scan.extract_history_chat", extract):
        await history_scan.scan_recent_chats(Settings(), user_id=user.id)
        await history_scan.scan_recent_chats(Settings(), user_id=user.id)

    assert {call.kwargs["chat_id"] for call in extract.await_args_list} == {talk.id, other.id}
    assert extract.await_count == 2
    await db_session.refresh(user)
    assert user.memory_history_scanned_at is not None
    assert await scan_env.keys("memory:history_scan*") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "miss",
    [RuntimeError("provider down"), "model_failed", "skipped_lock"],
)
async def test_scan_tries_only_the_missed_chat_again(db_session, scan_env, miss):
    user = await _make_user(db_session)
    newer, older = await _chats_with_lines(db_session, user, 2)
    first_pass = [miss] * (3 if miss == "skipped_lock" else 1) + [None]
    extract = AsyncMock(side_effect=first_pass)
    with patch("app.modules.memory.history_scan.extract_history_chat", extract):
        await history_scan.scan_recent_chats(Settings(), user_id=user.id)

    # The pass is not done: the missed chat waits, and the screen stops "scanning".
    await db_session.refresh(user)
    assert user.memory_history_scanned_at is None
    enqueue = AsyncMock()
    with patch("app.modules.memory.history_scan.jobs.enqueue", enqueue):
        assert await history_scan.request_history_scan(scan_env, user) is False
    enqueue.assert_not_awaited()

    retry = AsyncMock(return_value=None)
    with patch("app.modules.memory.history_scan.extract_history_chat", retry):
        await history_scan.scan_recent_chats(Settings(), user_id=user.id)

    assert [call.kwargs["chat_id"] for call in extract.await_args_list][-1] == older.id
    retry.assert_awaited_once()
    assert retry.await_args.kwargs["chat_id"] == newer.id
    await db_session.refresh(user)
    assert user.memory_history_scanned_at is not None


@pytest.mark.asyncio
async def test_scan_counts_as_done_after_three_passes_that_miss_chats(db_session, scan_env):
    user = await _make_user(db_session)
    await _chats_with_lines(db_session, user, 1)
    extract = AsyncMock(side_effect=RuntimeError("provider down"))
    with patch("app.modules.memory.history_scan.extract_history_chat", extract):
        for _ in range(3):
            await history_scan.scan_recent_chats(Settings(), user_id=user.id)

    assert extract.await_count == 3
    await db_session.refresh(user)
    assert user.memory_history_scanned_at is not None
    assert await scan_env.keys("memory:history_scan*") == []


@pytest.mark.asyncio
async def test_history_pass_cannot_bring_back_a_fact_the_user_deleted(db_session, fake_redis):
    user = await _make_user(db_session)
    chat = Chat(user_id=user.id, title="Recall app")
    db_session.add(chat)
    await db_session.flush()
    db_session.add(
        Message(
            chat_id=chat.id,
            user_id=user.id,
            role="user",
            content="I'm building Recall with Expo",
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )
    fact = Memory(user_id=user.id, type="project", text="User is building Recall with Expo")
    db_session.add(fact)
    await db_session.flush()

    with (
        patch.object(locks, "acquire_memory_write_lock", AsyncMock(return_value="t")),
        patch.object(locks, "release_memory_write_lock", AsyncMock()),
    ):
        assert await crud.delete_memory(db_session, user.id, fact.id) is True
    await db_session.refresh(user)
    assert user.memory_edited_at is not None
    # Said after the delete, so still worth reading.
    db_session.add(
        Message(
            chat_id=chat.id,
            user_id=user.id,
            role="user",
            content="I run every morning",
            created_at=user.memory_edited_at + timedelta(minutes=1),
        )
    )
    await db_session.flush()

    revise = AsyncMock(return_value=MemoryFactUpdateResult(ops=[]))
    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", lambda: _Reuse(db_session)),
        patch(
            "app.modules.memory.extraction_workflow.acquire_memory_write_lock",
            AsyncMock(return_value="t"),
        ),
        patch("app.modules.memory.extraction_workflow.release_memory_write_lock", AsyncMock()),
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", revise),
    ):
        outcome = await extract_history_chat(Settings(), user_id=user.id, chat_id=chat.id)

    assert outcome is None
    assert revise.await_args.args[1] == "User: I run every morning"
    rows = await db_session.execute(select(Memory).where(Memory.user_id == user.id))
    assert rows.scalars().all() == []
