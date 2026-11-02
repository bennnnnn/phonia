from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BeforeValidator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.orm import User
from app.models.schemas import SearchResultItem
from app.models.schemas.page import Page
from app.modules.search import service as search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=Page[SearchResultItem])
async def search(
    # Three characters: a trigram index cannot narrow a shorter substring.
    q: Annotated[str, Query(min_length=3, max_length=200), BeforeValidator(str.strip)],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=300),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Page[SearchResultItem]:
    results, next_cursor = await search_service.search_conversations(
        session, user.id, query=q, limit=limit, cursor=cursor
    )
    return Page(
        items=[SearchResultItem.model_validate(r) for r in results],
        next_cursor=next_cursor,
    )
