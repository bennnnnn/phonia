"""Dev/staging admin endpoints for the background-job DLQ.

Gated by ``dev_auth_enabled`` so they're unavailable in production over HTTP.
For production ops, use ``scripts/replay_dlq.py`` instead.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from app.core import jobs
from app.core.config import Settings
from app.core.deps import get_current_user, get_redis, get_settings_dep
from app.models.orm import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class DlqEntry(BaseModel):
    id: str
    original_id: str
    type: str
    payload: str
    error: str
    failed_at: str


class DlqReplayResult(BaseModel):
    replayed: int


def _require_dev(settings: Settings) -> None:
    if not settings.dev_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin endpoints are dev-only. Use scripts/replay_dlq.py in production.",
        )


def _require_admin(user: User, settings: Settings) -> None:
    _require_dev(settings)
    allowed = {value.strip() for value in settings.admin_user_ids.split(",") if value.strip()}
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is not configured. Set ADMIN_USER_IDS.",
        )
    if str(user.id) not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )


@router.get("/dlq", response_model=list[DlqEntry])
async def list_dlq(
    count: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
) -> list[DlqEntry]:
    _require_admin(user, settings)
    entries = await jobs.list_dlq(redis, count=count)
    parsed: list[DlqEntry] = []
    for entry in entries:
        try:
            parsed.append(DlqEntry.model_validate(entry))
        except ValidationError:
            logger.warning(
                "Skipping malformed DLQ entry id=%s",
                entry.get("id") if isinstance(entry, dict) else None,
                exc_info=True,
            )
    return parsed


@router.post("/dlq/replay", response_model=DlqReplayResult)
async def replay_dlq(
    count: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
) -> DlqReplayResult:
    _require_admin(user, settings)
    replayed = await jobs.replay_dlq(redis, count=count, delete=True)
    return DlqReplayResult(replayed=replayed)
