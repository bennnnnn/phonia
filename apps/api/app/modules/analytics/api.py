from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import allow_request_unless_down
from app.core.redis import get_redis_client
from app.exceptions import RateLimitedError
from app.models.orm import User
from app.models.schemas import ProductEventBatchIn
from app.modules.analytics import service as analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Batches a user may post: a batch holds up to 20 events, so these bound one account to
# 400 rows a minute and 20,000 a day. Only the global REST limit (240 requests a minute)
# stood in front of it: about 6.9 million rows a day from one account. The phone sends a
# batch when 20 events wait, 30 s after the first, on backgrounding or with a rare event,
# and drops a batch that fails, so a refused one costs it nothing.
BATCHES_PER_MINUTE = 20
BATCHES_PER_DAY = 1_000
_MINUTE = 60
_DAY = 86_400


async def _require_batch_allowance(user: User) -> None:
    """Count this batch against the user's minute and day; 429 past either."""
    redis = get_redis_client()
    limits = (
        (f"rate:analytics:min:{user.id}", BATCHES_PER_MINUTE, _MINUTE),
        (f"rate:analytics:day:{user.id}", BATCHES_PER_DAY, _DAY),
    )
    for key, limit, window in limits:
        if not await allow_request_unless_down(redis, key, limit=limit, window_seconds=window):
            raise RateLimitedError(
                "Too many analytics events. Try again later.", retry_after_seconds=window
            )


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
async def record_product_events(
    batch: ProductEventBatchIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await _require_batch_allowance(user)
    try:
        await analytics_service.record_batch(session, user.id, batch)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
