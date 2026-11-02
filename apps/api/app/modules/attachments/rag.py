"""Chunk + embed attachment text; retrieve into chat prompts (pgvector RAG)."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from app.core import presence_cache
from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.sympy_executor import WorkerBusyError
from app.gateways import embedding_gateway
from app.gateways.storage_gateway import get_storage_gateway
from app.models.orm import Attachment
from app.modules.attachments import chunks_repository as chunks_repo
from app.modules.attachments import content as attachment_content_service
from app.modules.attachments import ocr_allowance
from app.modules.attachments import repository as attachments_repo
from app.modules.attachments.content import ExtractedText, ExtractTimeoutError
from app.modules.attachments.content_types import EXTRACTABLE_CONTENT_TYPES
from app.services.chunking import chunk_text
from app.services.prompt_safety import wrap_untrusted

logger = logging.getLogger(__name__)


def _default_coverage_prefix() -> str:
    return (
        f"Indexed file text covers at most the first "
        f"{attachment_content_service.PDF_INDEX_MAX_PAGES} PDF pages and the first "
        f"{attachment_content_service.MAX_INDEX_EXTRACT_CHARS} characters. "
        "The configured chunk budget can reduce coverage further. "
        "A retrieval miss is not proof the answer is absent from unread pages. "
        "Do not invent from outside these excerpts.\n\n"
    )


_RAG_COVERAGE_PREFIX = _default_coverage_prefix()


def _parse_index_coverage(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        max_pages = int(data["max_pages"])
        max_chars = int(data["max_chars"])
    except (KeyError, TypeError, ValueError):
        return None
    if max_pages < 1 or max_chars < 1:
        return None
    return {
        "via_ocr": bool(data.get("via_ocr")),
        "max_pages": max_pages,
        "max_chars": max_chars,
    }


def _coverage_prefix_for(rows: list[Attachment]) -> str:
    parsed = [_parse_index_coverage(getattr(row, "index_coverage_json", None)) for row in rows]
    usable = [item for item in parsed if item is not None]
    if not usable:
        return _RAG_COVERAGE_PREFIX
    max_pages = min(int(item["max_pages"]) for item in usable)
    max_chars = min(int(item["max_chars"]) for item in usable)
    via_ocr = any(bool(item["via_ocr"]) for item in usable)
    pages_bit = f"first {max_pages} OCR'd PDF pages" if via_ocr else f"first {max_pages} PDF pages"
    return (
        f"Indexed file text covers at most the {pages_bit} and the first "
        f"{max_chars} characters. "
        "The configured chunk budget can reduce coverage further. "
        "A retrieval miss is not proof the answer is absent from unread pages. "
        "Do not invent from outside these excerpts.\n\n"
    )


def _index_coverage_payload(details: ExtractedText, settings: Settings) -> dict[str, Any]:
    max_pages = (
        settings.attachment_ocr_index_max_pages
        if details.via_ocr
        else attachment_content_service.PDF_INDEX_MAX_PAGES
    )
    return {
        "via_ocr": details.via_ocr,
        "max_pages": max_pages,
        "max_chars": attachment_content_service.MAX_INDEX_EXTRACT_CHARS,
        "page_capped": details.page_capped,
        "char_capped": details.char_capped,
    }


_RAG_MISS_NOTE = (
    "Indexed excerpts were searched but none matched this question. "
    "That is not proof the answer is absent from unread pages or the rest of "
    "the file. Do not invent from outside the file. If you cannot ground an "
    "answer in the excerpts, say so."
)

# Foreground TTFT path — match memory's live-embed budget.
_RAG_EMBED_TIMEOUT_SECONDS = 2.0


def is_indexable_attachment(row: Attachment) -> bool:
    return (
        not attachment_content_service.is_image_content_type(row.content_type)
        and row.content_type in EXTRACTABLE_CONTENT_TYPES
    )


class AttachmentUnreadableError(Exception):
    """The parse ran past its budget, or its worker died: a retry reads the same file the
    same way. Not retried (three attempts stacked parses of one hostile file)."""


class AttachmentIndexError(Exception):
    """Raised when attachment indexing fails transiently (R2 read, extraction, embedding).

    Distinguished from a legitimate "nothing to index" (image file, empty doc)
    which returns 0. A raised exception lets the worker retry (3 attempts)
    instead of the dedupe key blocking re-enqueue for 24h.
    """


async def _extract_for_index(
    settings: Settings,
    attachment_id: UUID,
    owner_id: UUID,
    storage_key: str,
    content_type: str,
) -> ExtractedText | None:
    """The whole file's text, OCR'd within the owner's allowance when it has no text layer.

    A read failure or a parse past its budget raises :class:`AttachmentIndexError`
    (retried) and gives back an OCR slot no vision call used.
    """
    gateway = get_storage_gateway(settings)
    data = await attachment_content_service.read_attachment_bytes(gateway, storage_key)
    if not data:
        raise AttachmentIndexError(f"Failed to read attachment bytes for {attachment_id}")

    ocr_day = await ocr_allowance.reserve_ocr(settings, owner_id, content_type, attachment_id)
    try:
        details = await attachment_content_service.extract_text_details_async(
            content_type,
            data,
            settings,
            max_chars=attachment_content_service.MAX_INDEX_EXTRACT_CHARS,
            allow_ocr=ocr_day is not None,
            ocr_max_pages=settings.attachment_ocr_index_max_pages,
            timeout_seconds=settings.attachment_index_extract_timeout_seconds,
            raise_on_timeout=True,
        )
    except WorkerBusyError as exc:
        await ocr_allowance.refund_ocr(owner_id, attachment_id, ocr_day)
        raise AttachmentIndexError(f"No document worker free for {attachment_id}") from exc
    except ExtractTimeoutError as exc:
        await ocr_allowance.refund_ocr(owner_id, attachment_id, ocr_day)
        raise AttachmentUnreadableError(f"Could not read {attachment_id} in time") from exc
    await ocr_allowance.release_unused_ocr(owner_id, attachment_id, ocr_day, details)
    if details is not None:
        await ocr_allowance.remember_ocr_text(attachment_id, details)
    return details


async def index_attachment(
    settings: Settings,
    *,
    user_id: UUID,
    attachment_id: UUID,
    chat_id: UUID | None = None,
) -> int:
    """Extract, chunk, embed, and store chunks for one attachment. Returns chunk count.

    Short-lived sessions around the row load and ``replace_chunks`` only — the
    download / extract / embed pipeline runs with no pool checkout held, same
    discipline as ``retrieve_for_prompt``.

    Raises :class:`AttachmentIndexError` for transient failures (R2 read,
    extraction timeout, all-embeddings-failed) so the worker retries instead of
    silently succeeding and blocking re-indexing via the dedupe key.
    """
    if not settings.attachment_rag_enabled:
        return 0

    async with SessionLocal() as session:
        # Indexing OCRs and embeds with outside models: a consent withdrawn after the turn
        # queued the file stops it here.
        row = await attachments_repo.get_by_id(
            session, attachment_id, user_id, owner_consented=True
        )
        if row is None or row.verified_at is None or not is_indexable_attachment(row):
            return 0
        storage_key = row.storage_key
        content_type = row.content_type
        owner_id = row.user_id
        row_id = row.id

    details = await ocr_allowance.recall_ocr_text(row_id)
    if details is None:
        details = await _extract_for_index(settings, row_id, owner_id, storage_key, content_type)
    if details is None or not details.text:
        # Legitimate "no text" — scanned PDF with no OCR, or genuinely empty doc.
        # Not a transient failure; don't raise.
        return 0

    pieces = chunk_text(
        details.text,
        chunk_chars=settings.attachment_rag_chunk_chars,
        overlap=settings.attachment_rag_chunk_overlap,
    )[: settings.attachment_rag_max_chunks_per_file]
    if not pieces:
        return 0

    vectors = await embedding_gateway.embed_many(
        settings, pieces, concurrency=settings.embedding_concurrency
    )
    embedded = list(zip(range(len(pieces)), pieces, vectors, strict=True))

    # Filter out chunks with null embeddings. If ALL failed, raise so the
    # worker retries — storing all-null chunks creates dead rows that
    # has_chunks_for_chat won't find (it requires embedding IS NOT NULL).
    successful: list[tuple[int, str, list[float] | None]] = [
        (idx, piece, vec) for idx, piece, vec in embedded if vec is not None
    ]
    failed_count = len(embedded) - len(successful)
    if failed_count > 0:
        logger.warning(
            "Attachment %s: %d/%d chunk embeddings failed",
            attachment_id,
            failed_count,
            len(embedded),
        )
    if not successful:
        raise AttachmentIndexError(
            f"All {len(embedded)} chunk embeddings failed for {attachment_id}"
        )

    async with SessionLocal() as session:
        stored = await chunks_repo.replace_chunks(
            session,
            user_id=owner_id,
            attachment_id=row_id,
            chat_id=chat_id,
            chunks=successful,
        )
        if stored:
            await attachments_repo.set_index_coverage(
                session,
                attachment_id=row_id,
                user_id=owner_id,
                coverage=_index_coverage_payload(details, settings),
            )
    if stored and chat_id is not None:
        await presence_cache.mark_present(presence_cache.documents_key(chat_id))
    return len(successful) if stored else 0


async def chat_has_document_chunks(user_id: UUID, chat_id: UUID) -> bool:
    """Whether this chat has searchable document chunks (remembered; see presence_cache)."""

    async def probe() -> bool:
        async with SessionLocal() as session:
            return await chunks_repo.has_chunks_for_chat(session, user_id, chat_id)

    return await presence_cache.cached_presence(presence_cache.documents_key(chat_id), probe)


async def retrieve_for_prompt(
    settings: Settings,
    *,
    user_id: UUID,
    chat_id: UUID,
    query: str,
) -> str:
    """Return a system-prompt block of top attachment chunks for this chat, or empty.

    Opens short-lived DB sessions around probe/search only — the embedding HTTP
    call runs with no pool checkout held, so a hung provider cannot stall TTFT
    via connection exhaustion.
    """
    if not settings.attachment_rag_enabled:
        return ""
    query = query.strip()
    if not query:
        return ""

    # Skip paid embed when this chat has no indexed chunks yet.
    try:
        if not await chat_has_document_chunks(user_id, chat_id):
            return ""
    except Exception:
        logger.warning("Attachment RAG chunk probe failed for chat_id=%s", chat_id, exc_info=True)
        return ""

    try:
        query_vec = await embedding_gateway.get_or_embed_query(
            settings,
            user_id,
            query,
            embed_timeout=_RAG_EMBED_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning("Attachment RAG embed failed for chat_id=%s", chat_id, exc_info=True)
        return ""
    if not query_vec:
        return ""

    max_distance = None
    if settings.attachment_rag_min_similarity > 0:
        max_distance = 1.0 - settings.attachment_rag_min_similarity

    # A database or pgvector error here costs the turn its attachment context, never the
    # turn: RAG is best-effort context, like memory and to-dos. (A failed embedding is
    # the empty vector checked above.)
    filenames: dict[UUID, str] = {}
    loaded_files: list[Attachment] = []
    try:
        async with SessionLocal() as search_session:
            rows = await chunks_repo.search_semantic(
                search_session,
                user_id,
                query_vec,
                window=settings.attachment_rag_search_window,
                chat_id=chat_id,
                limit=settings.attachment_rag_chunk_limit,
                max_distance=max_distance,
            )
            att_ids = list({row.attachment_id for row in rows})
            if att_ids:
                loaded_files = await attachments_repo.get_by_ids(search_session, att_ids, user_id)
                filenames = {
                    row.id: (row.original_filename or "").strip() or "attachment"
                    for row in loaded_files
                }
    except Exception:
        logger.warning("Attachment RAG retrieval failed for chat_id=%s", chat_id, exc_info=True)
        return ""

    if not rows:
        return wrap_untrusted("attached documents", _RAG_MISS_NOTE)

    lines = []
    for i, row in enumerate(rows):
        name = filenames.get(row.attachment_id) or "attachment"
        lines.append(f"[{i + 1}] ({name}) {row.text}")
    return wrap_untrusted(
        "attached documents",
        _coverage_prefix_for(loaded_files) + "\n\n".join(lines),
    )
