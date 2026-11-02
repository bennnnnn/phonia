"""Background job: index an attachment into pgvector chunks for RAG."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.core import jobs
from app.core.config import Settings
from app.core.redis import get_redis_client
from app.modules.attachments import rag as attachment_rag
from app.services import quota as quota_service

logger = logging.getLogger(__name__)

INDEX_JOB = "attachment_index"


def index_dedupe_key(attachment_id: str, chat_id: UUID) -> str:
    """One index run per file per chat; a Library file sent to another chat runs again."""
    return f"{INDEX_JOB}:{attachment_id}:{chat_id}"


async def enqueue_index_jobs(
    settings: Settings, *, user_id: UUID, chat_id: UUID, attachment_ids: list[str]
) -> None:
    """Index a turn's documents once its user message (and their links) committed.

    Not after the reply: a turn that ends without reply text (an error, a stop,
    an intercept) still gets its files indexed. Indexing embeds and may OCR, so
    the global spend cap skips it like the other background LLM jobs. Never
    raises: the user's message is already saved.
    """
    if not attachment_ids or not settings.attachment_rag_enabled:
        return
    try:
        redis = get_redis_client()
        if await quota_service.global_spend_exceeded(redis, settings):
            logger.warning("skipping attachment index: global spend cap user_id=%s", user_id)
            return
        # Each file is queued whatever happens to the others.
        results = await asyncio.gather(
            *(
                jobs.enqueue(
                    redis,
                    INDEX_JOB,
                    {
                        "attachment_id": attachment_id,
                        "user_id": str(user_id),
                        "chat_id": str(chat_id),
                    },
                    dedupe_key=index_dedupe_key(attachment_id, chat_id),
                )
                for attachment_id in attachment_ids
            ),
            return_exceptions=True,
        )
        for attachment_id, result in zip(attachment_ids, results, strict=True):
            if isinstance(result, Exception):
                logger.warning(
                    "Attachment index not queued attachment_id=%s", attachment_id, exc_info=result
                )
    except Exception:
        logger.exception("Attachment index enqueue failed chat_id=%s", chat_id)


async def index_attachment_job(settings: Settings, payload: dict[str, Any]) -> None:
    """Best-effort — never raises into the chat path (jobs runner catches)."""
    if not settings.attachment_rag_enabled:
        return
    try:
        attachment_id = UUID(str(payload["attachment_id"]))
        user_id = UUID(str(payload["user_id"]))
        chat_raw = payload.get("chat_id")
        chat_id = UUID(str(chat_raw)) if chat_raw else None
    except (KeyError, TypeError, ValueError):
        logger.warning("attachment_index job missing ids payload=%s", payload)
        return

    try:
        count = await attachment_rag.index_attachment(
            settings,
            user_id=user_id,
            attachment_id=attachment_id,
            chat_id=chat_id,
        )
    except attachment_rag.AttachmentUnreadableError as exc:
        # Dead-lettered, not retried: the same file would time out the same way.
        raise jobs.JobDiscardError(str(exc)) from exc
    if count:
        logger.info(
            "Indexed attachment_id=%s chunks=%s chat_id=%s",
            attachment_id,
            count,
            chat_id,
        )
