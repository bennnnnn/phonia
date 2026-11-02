"""Vector reads rank in Postgres, per user, without loading a vector into Python.

Memory recall loaded every fact with two copies of its 1536-dim vector (~50 KB a fact)
and ranked them on the event loop. The chunk searches leaned on global HNSW indexes,
which filter by user only after the scan: a user's own snippets came back empty once
other users' rows filled the 40 candidates.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.orm import Memory, Message, MessageChunk
from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import chunks_repository as chunks_repo
from app.modules.memory import repository as memories_repo
from app.modules.memory.erase import purge_fact_chunks
from app.modules.memory.selection import select_memories_semantic
from app.repositories import users as users_repo

DIM = 1536


def _vector(seed: int) -> list[float]:
    rng = random.Random(seed)  # noqa: S311 - reproducible test vectors
    return [rng.uniform(-1, 1) for _ in range(DIM)]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


async def _user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


async def test_memory_similarity_is_computed_in_sql_and_matches_python(db_session) -> None:
    user = await _user(db_session)
    vectors = {"Hikes every weekend": _vector(1), "Codes in Rust": _vector(2)}
    for text, vector in vectors.items():
        db_session.add(Memory(user_id=user.id, type="fact", text=text, embedding=vector))
    db_session.add(Memory(user_id=user.id, type="fact", text="No vector yet"))
    await db_session.flush()
    db_session.expunge_all()
    query = _vector(3)

    scored = await memories_repo.list_scored_for_user(db_session, user.id, query)

    by_text = {memory.text: score for memory, score in scored}
    assert by_text["No vector yet"] is None
    for text, vector in vectors.items():
        score = by_text[text]
        assert score is not None
        assert score == pytest.approx(_cosine(query, vector), abs=1e-5)
    # Neither vector copy travelled with the rows.
    for memory, _score in scored:
        assert "embedding" not in vars(memory)
        assert "embedding_json" not in vars(memory)


async def test_memory_selection_ranks_the_sql_scores(db_session) -> None:
    user = await _user(db_session)
    query = _vector(10)
    near = [value + 0.05 * noise for value, noise in zip(query, _vector(11), strict=True)]
    db_session.add_all(
        [
            Memory(user_id=user.id, type="fact", text="Near the question", embedding=near),
            Memory(user_id=user.id, type="fact", text="Far from it", embedding=_vector(12)),
        ]
    )
    await db_session.flush()

    scored = await memories_repo.list_scored_for_user(db_session, user.id, query)
    selected = select_memories_semantic(
        scored, Settings(memory_min_confidence=0.0, memory_min_similarity=0.35)
    )

    assert [memory.text for memory in selected] == ["Near the question"]


async def _chat_with_message(session, user_id):
    chat = await chats_repo.create(session, user_id=user_id, model="free-chat")
    message = Message(chat_id=chat.id, user_id=user_id, role="user", content="m")
    session.add(message)
    await session.flush()
    return chat, message


def _chunk(user_id, chat_id, message_id, index, vector, *, created_at) -> MessageChunk:
    return MessageChunk(
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        role="user",
        chunk_index=index,
        text=f"chunk {index}",
        embedding=vector,
        created_at=created_at,
    )


async def test_a_search_returns_only_the_asking_users_chunks(db_session) -> None:
    alice, bob = await _user(db_session), await _user(db_session)
    query = _vector(20)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for owner in (alice, bob):
        chat, message = await _chat_with_message(db_session, owner.id)
        for index in range(30):
            vector = query if owner is bob else _vector(100 + index)
            db_session.add(
                _chunk(
                    owner.id,
                    chat.id,
                    message.id,
                    index,
                    vector,
                    created_at=base + timedelta(minutes=index),
                )
            )
    await db_session.flush()

    rows = await chunks_repo.search_semantic(db_session, alice.id, query, window=100, limit=6)

    assert len(rows) == 6
    assert {row.user_id for row in rows} == {alice.id}


async def test_a_search_reads_only_the_newest_window(db_session) -> None:
    user = await _user(db_session)
    chat, message = await _chat_with_message(db_session, user.id)
    query = _vector(30)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # The oldest chunk matches the question exactly; it is outside a window of 5.
    db_session.add(_chunk(user.id, chat.id, message.id, 0, query, created_at=base))
    for index in range(1, 6):
        db_session.add(
            _chunk(
                user.id,
                chat.id,
                message.id,
                index,
                _vector(200 + index),
                created_at=base + timedelta(days=index),
            )
        )
    await db_session.flush()

    rows = await chunks_repo.search_semantic(db_session, user.id, query, window=5, limit=6)

    assert [row.chunk_index for row in rows if row.chunk_index == 0] == []
    assert len(rows) == 5


async def test_chunks_beyond_the_search_window_are_deleted(db_session) -> None:
    user, other = await _user(db_session), await _user(db_session)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for owner in (user, other):
        chat, message = await _chat_with_message(db_session, owner.id)
        for index in range(8):
            db_session.add(
                _chunk(
                    owner.id,
                    chat.id,
                    message.id,
                    index,
                    _vector(300 + index),
                    created_at=base + timedelta(days=index),
                )
            )
    await db_session.flush()

    await chunks_repo.prune_beyond_window(db_session, user.id, window=5)

    kept = await db_session.execute(
        select(MessageChunk.user_id, MessageChunk.chunk_index).order_by(MessageChunk.chunk_index)
    )
    rows = kept.all()
    # The user's newest five stay; another user's chunks are not touched.
    assert sorted(i for owner, i in rows if owner == user.id) == [3, 4, 5, 6, 7]
    assert len([i for owner, i in rows if owner == other.id]) == 8


async def test_chunks_are_stored_without_the_json_copy(db_session) -> None:
    user = await _user(db_session)
    chat, message = await _chat_with_message(db_session, user.id)

    await chunks_repo.replace_chunks_of_messages(
        db_session,
        user_id=user.id,
        messages=[(message.id, chat.id, "user", [(0, "hello", _vector(40))])],
    )

    stored = (
        await db_session.execute(
            select(MessageChunk.embedding_json, MessageChunk.embedding.isnot(None)).where(
                MessageChunk.message_id == message.id
            )
        )
    ).one()
    assert stored == (None, True)


async def test_forgetting_a_fact_drops_the_snippets_that_repeat_it(db_session) -> None:
    user = await _user(db_session)
    chat, message = await _chat_with_message(db_session, user.id)
    fact_vector = _vector(50)
    fact = Memory(user_id=user.id, type="fact", text="User lives in Lisbon", embedding=fact_vector)
    db_session.add(fact)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    db_session.add(_chunk(user.id, chat.id, message.id, 0, fact_vector, created_at=base))
    db_session.add(_chunk(user.id, chat.id, message.id, 1, _vector(51), created_at=base))
    await db_session.flush()
    db_session.expunge_all()
    loaded = await memories_repo.get_by_id(db_session, user.id, fact.id)
    assert loaded is not None

    await purge_fact_chunks(db_session, user.id, [loaded])

    left = (
        await db_session.execute(
            select(MessageChunk.chunk_index).where(MessageChunk.user_id == user.id)
        )
    ).scalars()
    assert list(left) == [1]


async def test_a_turns_messages_replace_their_chunks_in_one_delete_and_one_insert(
    db_session,
) -> None:
    from sqlalchemy import event

    user = await _user(db_session)
    chat, asked = await _chat_with_message(db_session, user.id)
    _, kept = await _chat_with_message(db_session, user.id)
    reply = Message(chat_id=chat.id, user_id=user.id, role="assistant", content="r")
    db_session.add(reply)
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _chunk(user.id, chat.id, asked.id, 0, _vector(1), created_at=now),
            _chunk(user.id, chat.id, asked.id, 1, _vector(2), created_at=now),
            _chunk(user.id, kept.chat_id, kept.id, 0, _vector(3), created_at=now),
        ]
    )
    await db_session.flush()
    statements: list[str] = []
    engine = db_session.bind.sync_engine

    def seen(_conn, _cursor, statement, *_args) -> None:
        statements.append(statement.split()[0])

    event.listen(engine, "before_cursor_execute", seen)
    try:
        await chunks_repo.replace_chunks_of_messages(
            db_session,
            user_id=user.id,
            messages=[
                (asked.id, chat.id, "user", [(0, "asked", _vector(4))]),
                (reply.id, chat.id, "assistant", [(0, "one", _vector(5)), (1, "two", None)]),
            ],
        )
    finally:
        event.remove(engine, "before_cursor_execute", seen)

    assert statements == ["DELETE", "INSERT"]
    stored = await db_session.execute(
        select(MessageChunk.message_id, MessageChunk.text).where(MessageChunk.user_id == user.id)
    )
    assert sorted((str(m), t) for m, t in stored.all()) == sorted(
        [
            (str(asked.id), "asked"),
            (str(reply.id), "one"),
            (str(reply.id), "two"),
            (str(kept.id), "chunk 0"),
        ]
    )
