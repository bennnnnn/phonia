"""Extract and persist atomic memory facts from a chat transcript."""

import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import SessionLocal
from app.models.orm import User
from app.modules.memory import llm as memory_llm
from app.modules.memory import repository as memories_repo
from app.modules.memory.apply import apply_memory_facts
from app.modules.memory.commands import is_explicit_forget_command
from app.modules.memory.extract_backlog import (
    clear_failed_extract_passes,
    exchange_before_unread,
    expand_memory_extract_transcript,
    history_chat_transcript,
    note_failed_extract_pass,
    stamp_extract_cursor,
)
from app.modules.memory.fact_quality import FactView
from app.modules.memory.locks import acquire_memory_write_lock, release_memory_write_lock
from app.modules.memory.pass_writes import (
    Asks,
    MemorySnapshot,
    compose_writes,
    without_reset_requests,
)
from app.modules.memory.schemas import MemoryFactOp
from app.modules.memory.switch import memory_switch_on
from app.modules.memory.text import is_memory_candidate
from app.modules.memory.topics import (
    fact_topic,
)
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)

# ``skipped_lock``: memory was busy, retry after a backoff. ``model_failed``: the
# model gave no usable answer, so these lines were not read.
ExtractOutcome = Literal["skipped_lock", "model_failed"] | None


async def load_memory_snapshot(
    session: AsyncSession,
    user_id: UUID,
) -> MemorySnapshot:
    user = await users_repo.get_by_id(session, user_id)
    if user is None or not memory_switch_on(user):
        return MemorySnapshot(
            memory_enabled=False,
            include_sensitive=False,
            existing_facts={},
            prompt_facts=[],
            prompt_areas=[],
        )
    return await _snapshot(session, user)


async def _snapshot(session: AsyncSession, user: User, *, facts: bool = True) -> MemorySnapshot:
    """What the pass reads of the user's memory; ``facts`` False leaves the saved facts
    and areas unread (lines no pass sends to the model need neither)."""
    existing = (
        await memories_repo.list_for_user(
            session, user.id, include_muted=False, include_superseded=False
        )
        if facts
        else []
    )
    areas = await memories_repo.list_areas(session, user.id) if facts else []
    return MemorySnapshot(
        memory_enabled=True,
        include_sensitive=user.memory_include_sensitive,
        existing_facts={memory.id: memory.text for memory in existing},
        # No id: an op names the fact it changes by its text (``match_text``), and a
        # row id cost the prompt about 28 tokens a fact.
        prompt_facts=[
            {
                "type": memory.type,
                "topic": fact_topic(memory),
                "text": memory.text,
            }
            for memory in existing
        ],
        prompt_areas=[
            {"topic": area.key, "title": area.title, "summary": area.summary} for area in areas
        ],
        edited_at=user.memory_edited_at,
        profile_name=user.name,
        active_facts=tuple(
            FactView(
                text=memory.text,
                confirmed_at=memory.last_confirmed_at,
            )
            for memory in existing
        ),
        user_timezone=user.timezone,
    )


async def extract_and_store_memories(
    settings: Settings,
    *,
    user_id: UUID,
    chat_id: UUID,
    transcript: str,
) -> ExtractOutcome:
    """Learn from a chat's unread user lines (``transcript`` is the fallback)."""
    return await _extract_pass(
        settings, user_id=user_id, chat_id=chat_id, transcript=transcript, from_history=False
    )


async def extract_history_chat(
    settings: Settings, *, user_id: UUID, chat_id: UUID
) -> ExtractOutcome:
    """Learn from one past chat's recent user lines, for the history scan.

    Old lines only fill gaps: saved facts may be newer, so none is changed or
    removed. Lines from before the user's last hand edit are not read, so the
    pass cannot bring back what they removed. The chat's live cursor and retry
    count are left alone.
    """
    return await _extract_pass(
        settings, user_id=user_id, chat_id=chat_id, transcript="", from_history=True
    )


async def _extract_pass(
    settings: Settings,
    *,
    user_id: UUID,
    chat_id: UUID,
    transcript: str,
    from_history: bool,
) -> ExtractOutcome:
    try:
        lock_token = await acquire_memory_write_lock(user_id)
        if not lock_token:
            logger.info(
                "Memory extraction skipped: write lock held for user_id=%s",
                user_id,
            )
            return "skipped_lock"
        try:
            return await _locked_pass(
                settings,
                user_id=user_id,
                chat_id=chat_id,
                transcript=transcript,
                from_history=from_history,
            )
        finally:
            await release_memory_write_lock(user_id, lock_token)
    except Exception:
        logger.exception("Memory extraction failed for user_id=%s", user_id)
        raise


@dataclass(frozen=True)
class _PassInput:
    """What a pass reads under the write lock: the snapshot and the unread user lines."""

    snapshot: MemorySnapshot
    lines: str
    # Where the live cursor moves once these lines are read; None for the history scan.
    cursor: str | None
    # The exchange before these lines, read for a "forget that"; else empty.
    earlier: str = ""


async def _locked_pass(
    settings: Settings,
    *,
    user_id: UUID,
    chat_id: UUID,
    transcript: str,
    from_history: bool,
) -> ExtractOutcome:
    """One pass under the user's write lock: read, ask the model, write, move the cursor."""
    read = await _read_pass_input(user_id, chat_id, transcript, from_history=from_history)
    if read is None:
        return None
    if not read.lines.strip():
        await _stamp(user_id, chat_id, read.cursor)
        return None
    asks = Asks.of(read.lines)
    if _small_talk(read.lines, asks):
        # Small talk only: nothing to learn, but the lines are read. Moving
        # the cursor keeps a run of "ok"s from hiding every later line.
        await _stamp(user_id, chat_id, read.cursor)
        logger.info("memory_extract_yield user_id=%s applied=0 skipped=candidate", user_id)
        return None
    ops, outcome, advance = await _ask_model(
        settings, read, user_id=user_id, chat_id=chat_id, from_history=from_history
    )
    writes, skipped = compose_writes(
        read.snapshot,
        read.lines,
        asks,
        ops,
        chat_id=chat_id,
        from_history=from_history,
        min_confidence=settings.memory_min_confidence,
        earlier=read.earlier,
    )
    if writes:
        await apply_memory_facts(
            settings,
            user_id=user_id,
            writes=writes,
            session_factory=SessionLocal,
            memories=memories_repo,
            # A history add that matches a saved fact leaves it as it is.
            expected_facts={} if from_history else read.snapshot.existing_facts,
            manual_edit=(asks.forget or asks.mute or asks.correction) and not from_history,
        )
        logger.info(
            "memory_extract_yield user_id=%s applied=%s skipped=%s", user_id, len(writes), skipped
        )
    else:
        logger.info("memory_extract_yield user_id=%s applied=0 skipped=empty", user_id)
    if advance:
        await _stamp(user_id, chat_id, read.cursor)
    return outcome


def _small_talk(lines: str, asks: Asks) -> bool:
    """Lines with nothing to learn: the pass moves past them without the model."""
    return not asks.remember and not asks.forget and not is_memory_candidate(lines)


async def _read_pass_input(
    user_id: UUID, chat_id: UUID, transcript: str, *, from_history: bool
) -> _PassInput | None:
    """The snapshot and the lines to read; None when memory is off.

    The saved facts are read only for lines the model will see: a "thanks" or an "ok"
    read the user's every fact (up to 150) and area for nothing.
    """
    async with SessionLocal() as session:
        user = await users_repo.get_by_id(session, user_id)
        if user is None or not memory_switch_on(user):
            return None
        cursor: str | None = None
        earlier = ""
        if from_history:
            # Read under the write lock, so a hand edit cannot land
            # between this cut-off and the writes below.
            lines = await history_chat_transcript(
                session, chat_id, newer_than=user.memory_edited_at
            )
        else:
            lines, cursor = await expand_memory_extract_transcript(
                session,
                user_id=user_id,
                chat_id=chat_id,
                fallback_transcript=transcript,
            )
            if is_explicit_forget_command(lines):
                earlier = await exchange_before_unread(session, user_id=user_id, chat_id=chat_id)
        lines = without_reset_requests(lines)
        facts = bool(lines.strip()) and not _small_talk(lines, Asks.of(lines))
        snapshot = await _snapshot(session, user, facts=facts)
    return _PassInput(snapshot=snapshot, lines=lines, cursor=cursor, earlier=earlier)


async def _ask_model(
    settings: Settings, read: _PassInput, *, user_id: UUID, chat_id: UUID, from_history: bool
) -> tuple[list[MemoryFactOp], ExtractOutcome, bool]:
    """The model's ops, the pass outcome, and whether the cursor may move past these lines."""
    result = await memory_llm.revise_memory_facts(
        settings,
        read.lines,
        existing_facts=read.snapshot.prompt_facts,
        existing_areas=read.snapshot.prompt_areas,
        from_history=from_history,
        earlier=read.earlier,
        # An earlier chat's "next Friday" was said on another day: no date places it.
        today=None if from_history else memory_llm.local_today(read.snapshot.user_timezone),
    )
    if result is not None:
        if not from_history:
            await clear_failed_extract_passes(user_id, chat_id)
        return result.ops, None, True
    # Provider error, timeout or unreadable JSON. Keep the cursor so the
    # next turn retries these lines, up to FAILED_PASS_LIMIT times.
    advance = False if from_history else await note_failed_extract_pass(user_id, chat_id)
    logger.warning(
        "memory_extract_model_failed user_id=%s chat_id=%s moving_on=%s",
        user_id,
        chat_id,
        advance,
    )
    return [], "model_failed", advance


async def _stamp(user_id: UUID, chat_id: UUID, cursor: str | None) -> None:
    """Move the chat's live cursor past the lines just read (none for the history scan)."""
    if cursor:
        await stamp_extract_cursor(user_id, chat_id, cursor)
