from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.orm import User
from app.models.schemas import ProductEventBatchIn
from app.modules.analytics import service as analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
async def record_product_events(
    batch: ProductEventBatchIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    try:
        await analytics_service.record_batch(session, user.id, batch)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
