"""What a lesson chat has taught so far, as one memory line.

Read from the chat itself: the subject from its first "teach me", the topics
from each ``### Lesson N: <topic>`` heading. Built by the ``lesson_progress``
job after a lesson reply; memory owns the write
(``modules/memory/learning_progress.py``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Chat
from app.modules.conversation import history as conversation_history
from app.modules.turn_reading.lesson_flow import lesson_step, lesson_titles, teach_subject
from app.modules.turn_reading.teaching import is_teaching_request

# A long course still finds its first "teach me" and every lesson heading.
LESSON_HISTORY_LIMIT = 300
_COVERED_MAX = 8
_TOPIC_MAX_CHARS = 60


@dataclass(frozen=True)
class LessonProgress:
    text: str
    started_at: datetime | None


def lesson_progress(messages: Sequence[Any], *, title: str | None) -> LessonProgress | None:
    """The learning line for an oldest-first chat, or None when it taught no lesson."""
    subject: str | None = None
    topics: list[str] = []
    latest: tuple[int, str] | None = None
    started_at: datetime | None = None
    for message in messages:
        content = getattr(message, "content", None)
        if not isinstance(content, str):
            continue
        role = getattr(message, "role", None)
        if role == "user" and subject is None and is_teaching_request(content):
            subject = teach_subject(content)
        elif role == "assistant" and lesson_step(content) is not None:
            for number, topic in lesson_titles(content):
                topic = topic[:_TOPIC_MAX_CHARS].strip()
                latest = (number, topic)
                if topic not in topics:
                    topics.append(topic)
            started_at = started_at or getattr(message, "created_at", None)
    subject = subject or (title or "").strip() or None
    if latest is None or subject is None:
        return None
    number, topic = latest
    where = f' (chat "{title.strip()}")' if title and title.strip() else ""
    covered = "; ".join(topics[-_COVERED_MAX:])
    return LessonProgress(
        text=f"Learning {subject}: reached Lesson {number}, {topic}{where}. Covered: {covered}",
        started_at=started_at,
    )


async def load_lesson_progress(
    session: AsyncSession, *, user_id: UUID, chat_id: UUID
) -> LessonProgress | None:
    chat = await session.get(Chat, chat_id)
    if chat is None or chat.user_id != user_id:
        return None
    messages = await conversation_history.recent_messages(
        session, chat_id, limit=LESSON_HISTORY_LIMIT
    )
    return lesson_progress(messages, title=chat.title)
