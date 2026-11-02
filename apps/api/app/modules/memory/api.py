from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.consent import get_consented_user
from app.core.db import get_db
from app.core.deps import get_current_user, get_settings_dep
from app.core.etag import conditional_json
from app.core.rate_limit import allow_request_unless_down
from app.core.redis import get_redis_client
from app.exceptions import DomainError
from app.models.orm import Memory, User
from app.modules.memory import crud, enqueue_policy, history_scan
from app.modules.memory import documents as documents_service
from app.modules.memory import instruct as instruct_service
from app.modules.memory.schemas import (
    MemoryDocumentOut,
    MemoryDocumentsOut,
    MemoryInstructIn,
    MemoryInstructOut,
    MemoryOut,
    MemoryUpdate,
)
from app.modules.memory.topics import parse_topic
from app.services import quota as quota_service

router = APIRouter(prefix="/memories", tags=["memories"])

# Direct edits call the model; this bounds them per user per hour.
_INSTRUCT_PER_HOUR = 30


def _fact_out(fact: Memory, titles: dict[UUID, str]) -> MemoryOut:
    item = MemoryOut.model_validate(fact)
    title = titles.get(fact.source_chat_id) if fact.source_chat_id else None
    return item.model_copy(update={"source_chat_title": title}) if title else item


def _document_out(
    document: documents_service.MemoryDocument, titles: dict[UUID, str]
) -> MemoryDocumentOut:
    return MemoryDocumentOut(
        key=document.key,
        group=document.group,
        title=document.title,
        summary=document.summary,
        updated_at=document.updated_at,
        facts=[_fact_out(fact, titles) for fact in document.facts],
    )


async def _documents_out(session: AsyncSession, user: User) -> list[MemoryDocumentOut]:
    """Every page, each fact with the chat it was learned in (M12)."""
    documents = await documents_service.list_documents(session, user.id)
    titles = await enqueue_policy.source_chat_titles(
        session, [fact for document in documents for fact in document.facts]
    )
    return [_document_out(document, titles) for document in documents]


@router.get("", response_model=list[MemoryOut])
async def list_memories(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MemoryOut]:
    memories = await enqueue_policy.list_user_memories(
        session,
        get_redis_client(),
        user,
    )
    titles = await enqueue_policy.source_chat_titles(session, memories)
    return [_fact_out(memory, titles) for memory in memories]


@router.get("/documents", response_model=MemoryDocumentsOut)
async def list_memory_documents(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    documents = await _documents_out(session, user)
    scanning = await history_scan.request_history_scan(get_redis_client(), user)
    # Every visit and scan poll reads the pages: unchanged ones cost a 304 (core/etag.py).
    return conditional_json(request, MemoryDocumentsOut(documents=documents, scanning=scanning))


@router.delete("/documents/{topic}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_document(
    topic: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    key = parse_topic(topic)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    deleted = await crud.delete_memory_document(session, user.id, key)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")


@router.post("/instruct", response_model=MemoryInstructOut)
async def instruct_memory(
    body: MemoryInstructIn,
    # The instruction is read by an outside model: only with AI data consent.
    user: User = Depends(get_consented_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> MemoryInstructOut:
    redis = get_redis_client()
    # Coded refusals, so the phone says which (code-health audit CLAR-08).
    if await quota_service.global_spend_exceeded(redis, settings):
        # Its own code: by status alone it was "unavailable", the code of an outage.
        raise DomainError(
            "Memory editing is paused right now — try again later.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="memory_spend_cap",
        )
    if not await allow_request_unless_down(
        redis, f"memory_instruct:{user.id}", limit=_INSTRUCT_PER_HOUR, window_seconds=3600
    ):
        raise DomainError(
            "Too many memory edits — try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    outcome = await instruct_service.apply_memory_instruction(
        settings,
        user_id=user.id,
        instruction=body.instruction.strip(),
        focus_topic=body.topic,
    )
    return MemoryInstructOut(
        reply=outcome.reply,
        applied=outcome.applied,
        dropped=outcome.dropped,
        documents=await _documents_out(session, user),
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_memories(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await crud.delete_all_memories(session, user.id)


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: UUID,
    body: MemoryUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> MemoryOut:
    updated = await crud.update_memory(
        session, settings, user.id, memory_id, body.text, status=body.status
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return MemoryOut.model_validate(updated)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    deleted = await crud.delete_memory(session, user.id, memory_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
