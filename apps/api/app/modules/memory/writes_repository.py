"""Conditional background writes that preserve manual memory changes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.memory.erase as erase
from app.models.orm import Memory, MemoryArea, User
from app.modules.memory.ops import (
    ACTIVE_STATUS,
    MUTED_STATUS,
    SUPERSEDED_STATUS,
    evict_for_cap,
    exact_fact,
    match_fact,
    normalize_memory_text,
)
from app.modules.memory.topics import (
    AREA_SUMMARY_MAX,
    AREA_TITLE_MAX,
    TYPE_DEFAULT_TOPIC,
    clean_area_text,
    is_area,
)


@dataclass(frozen=True)
class MemoryFactWrite:
    op: str
    type: str
    text: str
    confidence: float
    sensitivity: str = "normal"
    importance: float = 0.5
    match_text: str | None = None
    source_chat_id: UUID | None = None
    source_message_id: UUID | None = None
    # Memory document; None keeps a matched fact's topic, or the type's default.
    topic: str | None = None
    # Title and summary for a new area document (``area:<slug>`` topic).
    area_title: str | None = None
    area_summary: str | None = None


async def lock_memory_enabled(session: AsyncSession, user_id: UUID) -> bool:
    """Serialize the short write phase with account toggle/deletion commits."""
    result = await session.execute(
        select(User.memory_enabled).where(User.id == user_id).with_for_update()
    )
    return bool(result.scalar_one_or_none())


def _snapshot_ok(fact: Memory, expected_facts: dict[UUID, str] | None) -> bool:
    if expected_facts is None:
        return True
    prior = expected_facts.get(fact.id)
    return prior is not None and prior == fact.text


async def apply_fact_ops(
    session: AsyncSession,
    user_id: UUID,
    writes: list[MemoryFactWrite],
    expected_facts: dict[UUID, str] | None,
    *,
    active_cap: int,
    applied: list[str] | None = None,
) -> list[UUID]:
    """Apply add/update/supersede/delete/mute. Returns ids whose text changed.

    The caller owns commit and rollback. When ``expected_facts`` is set, a
    late background write is skipped if the matched row's text changed.
    ``applied`` collects the op of every write that took effect.
    """
    if not writes:
        return []
    result = await session.execute(select(Memory).where(Memory.user_id == user_id))
    facts = list(result.scalars().all())
    touched: list[UUID] = []

    for write in writes:
        op = write.op
        clean = normalize_memory_text(write.text) if write.text else ""
        if op == "add":
            if not clean:
                continue
            existing = exact_fact(facts, clean)
            if existing is not None:
                if not _snapshot_ok(existing, expected_facts):
                    continue
                # A muted fact said again stays muted: only the user unmutes it.
                _apply_update(existing, write, clean)
                touched.append(existing.id)
                _note(applied, op)
                continue
            row = Memory(
                user_id=user_id,
                type=write.type,
                topic=_write_topic(write),
                text=clean,
                confidence=write.confidence,
                status=ACTIVE_STATUS,
                sensitivity=write.sensitivity,
                importance=write.importance,
                last_confirmed_at=datetime.now(UTC),
                source_chat_id=write.source_chat_id,
                source_message_id=write.source_message_id,
            )
            session.add(row)
            await session.flush()
            facts.append(row)
            touched.append(row.id)
            _note(applied, op)
            continue

        needle = write.match_text or write.text
        matched = match_fact(facts, memory_type=write.type, match_text=needle) or match_fact(
            facts, memory_type=None, match_text=needle
        )
        if matched is None or not _snapshot_ok(matched, expected_facts):
            continue
        if op == "delete":
            removed = await erase.delete_fact_rows(session, user_id, matched.id)
            facts = [fact for fact in facts if fact.id not in removed]
            _note(applied, op)
            continue
        if op == "mute":
            matched.status = MUTED_STATUS
            await erase.purge_fact_chunks(session, user_id, [matched])
            _note(applied, op)
            continue
        if op == "update":
            if not clean:
                continue
            _apply_update(matched, write, clean)
            touched.append(matched.id)
            _note(applied, op)
            continue
        if op == "supersede":
            if not clean:
                continue
            replacement = Memory(
                user_id=user_id,
                type=write.type,
                # Keep the old fact's document unless the type changed with it.
                topic=write.topic
                or (matched.topic if matched.type == write.type else _write_topic(write)),
                text=clean,
                confidence=write.confidence,
                status=ACTIVE_STATUS,
                sensitivity=write.sensitivity,
                importance=write.importance,
                last_confirmed_at=datetime.now(UTC),
                source_chat_id=write.source_chat_id,
                source_message_id=write.source_message_id,
            )
            session.add(replacement)
            await session.flush()
            matched.status = SUPERSEDED_STATUS
            matched.superseded_at = datetime.now(UTC)
            matched.superseded_by_id = replacement.id
            facts.append(replacement)
            touched.append(replacement.id)
            _note(applied, op)

    # A fact the cap pushes out is deleted, history and all, not kept out of sight.
    for stale in evict_for_cap(facts, active_cap):
        await erase.delete_fact_rows(session, user_id, stale.id, purge=False)
    await _ensure_areas(session, user_id, writes)
    return list(dict.fromkeys(touched))


def _note(applied: list[str] | None, op: str) -> None:
    if applied is not None:
        applied.append(op)


def _write_topic(write: MemoryFactWrite) -> str:
    return write.topic or TYPE_DEFAULT_TOPIC.get(write.type, "notes")


async def _ensure_areas(
    session: AsyncSession, user_id: UUID, writes: list[MemoryFactWrite]
) -> None:
    """Create the title row for each new area a write names. Existing rows stay."""
    wanted: dict[str, tuple[str, str]] = {}
    for write in writes:
        if write.op == "delete" or not write.topic or not is_area(write.topic):
            continue
        title = clean_area_text(write.area_title, limit=AREA_TITLE_MAX)
        if not title or write.topic in wanted:
            continue
        wanted[write.topic] = (title, clean_area_text(write.area_summary, limit=AREA_SUMMARY_MAX))
    for key, (title, summary) in wanted.items():
        await session.execute(
            pg_insert(MemoryArea)
            .values(user_id=user_id, key=key, title=title, summary=summary)
            .on_conflict_do_nothing(index_elements=["user_id", "key"])
        )


def _apply_update(fact: Memory, write: MemoryFactWrite, clean: str) -> None:
    if clean != fact.text:
        fact.embedding = None
        fact.embedding_json = None
        fact.embedding_text_hash = None
    if write.topic and write.topic != fact.topic:
        # The model moved this fact to another document.
        fact.topic = write.topic
        fact.type = write.type
    fact.text = clean
    fact.confidence = write.confidence
    fact.sensitivity = write.sensitivity
    fact.importance = write.importance
    fact.last_confirmed_at = datetime.now(UTC)
    if write.source_chat_id is not None:
        fact.source_chat_id = write.source_chat_id
    if write.source_message_id is not None:
        fact.source_message_id = write.source_message_id
    fact.updated_at = datetime.now(UTC)


async def update_embedding_if_current(
    session: AsyncSession,
    user_id: UUID,
    memory_id: UUID,
    text: str,
    embedding: list[float],
    embedding_text_hash: str,
    *,
    commit: bool = True,
) -> None:
    await session.execute(
        update(Memory)
        .where(Memory.id == memory_id, Memory.user_id == user_id, Memory.text == text)
        .values(
            embedding=embedding,
            # The JSON copy is no longer read; clearing it frees the row's ~34 KB.
            embedding_json=None,
            embedding_text_hash=embedding_text_hash,
        )
        .execution_options(synchronize_session=False)
    )
    if commit:
        await session.commit()
