"""The one memory line a lesson chat keeps: "Learning Python: reached Lesson 3, ...".

Extraction reads only what the user says, so what was taught would never reach
memory. A new chat's "teach me python" reads this line to offer picking up
where the learner stopped. It is an ordinary fact: shown on the Memory page,
editable and deletable. A chat finds its line again by source chat and the
heading before the colon, and rewrites it in place after each lesson.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.core.config import Settings
from app.core.db import SessionLocal
from app.modules.memory import repository as memories_repo
from app.modules.memory.apply import apply_memory_facts
from app.modules.memory.locks import acquire_memory_write_lock, release_memory_write_lock
from app.modules.memory.ops import is_active_memory, normalize_memory_text
from app.modules.memory.switch import memory_switch_on
from app.modules.memory.topics import fact_topic, topic_memory_type
from app.modules.memory.writes_repository import MemoryFactWrite
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)

LEARNING_TOPIC = "goals"


def _heading(text: str) -> str:
    return normalize_memory_text(text).split(":", 1)[0].casefold()


async def record_learning_progress(
    settings: Settings,
    *,
    user_id: UUID,
    chat_id: UUID,
    text: str,
    started_at: datetime | None,
) -> Literal["skipped_lock"] | None:
    """Add or rewrite this chat's learning line. Best-effort; never raises.

    A hand edit to memory after the lessons began (the user may have deleted
    this line) stops a new line being added, as the history scan does.
    """
    clean = normalize_memory_text(text)
    if not clean:
        return None
    try:
        lock_token = await acquire_memory_write_lock(user_id)
        if not lock_token:
            return "skipped_lock"
        try:
            async with SessionLocal() as session:
                user = await users_repo.get_by_id(session, user_id)
                if user is None or not memory_switch_on(user):
                    return None
                facts = await memories_repo.list_for_user(
                    session, user_id, include_muted=True, include_superseded=False
                )
            current = next(
                (
                    fact
                    for fact in facts
                    if fact.source_chat_id == chat_id and _heading(fact.text) == _heading(clean)
                ),
                None,
            )
            if current is not None:
                # Muted by the user, or already says this.
                if not is_active_memory(current) or normalize_memory_text(current.text) == clean:
                    return None
                write = MemoryFactWrite(
                    op="update",
                    type=current.type,
                    text=clean,
                    confidence=1.0,
                    match_text=current.text,
                    topic=fact_topic(current),
                    source_chat_id=chat_id,
                )
                expected = {current.id: current.text}
            else:
                edited_at = user.memory_edited_at
                if edited_at and started_at and edited_at > started_at:
                    return None
                write = MemoryFactWrite(
                    op="add",
                    type=topic_memory_type(LEARNING_TOPIC),
                    text=clean,
                    confidence=1.0,
                    topic=LEARNING_TOPIC,
                    source_chat_id=chat_id,
                )
                expected = {}
            await apply_memory_facts(
                settings,
                user_id=user_id,
                writes=[write],
                session_factory=SessionLocal,
                expected_facts=expected,
            )
        finally:
            await release_memory_write_lock(user_id, lock_token)
    except Exception:
        logger.exception("learning progress write failed user_id=%s", user_id)
    return None
