"""Background job: index chat turns into pgvector chunks for history RAG."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.modules.conversation import history_rag as chat_history_rag
from app.modules.memory.switch import memory_switch_on

logger = logging.getLogger(__name__)


async def index_message_job(settings: Settings, payload: dict[str, Any]) -> None:
    """Best-effort — never raises into the chat path (jobs runner catches)."""
    if not settings.chat_history_rag_enabled:
        return
    try:
        user_id = UUID(str(payload["user_id"]))
        chat_id = UUID(str(payload["chat_id"]))
        assistant_message_id = UUID(str(payload["assistant_message_id"]))
    except (KeyError, TypeError, ValueError):
        logger.warning("message_index job missing ids payload=%s", payload)
        return

    count = await chat_history_rag.index_turn_messages(
        settings,
        user_id=user_id,
        chat_id=chat_id,
        assistant_message_id=assistant_message_id,
        memory_on=memory_switch_on,
    )
    if count:
        logger.info(
            "Indexed chat-history chunks=%s chat_id=%s assistant_message_id=%s",
            count,
            chat_id,
            assistant_message_id,
        )
