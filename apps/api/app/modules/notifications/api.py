"""Push-token registration for reminder and nudge notifications (``/users/push-token``)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.exceptions import PushTokenBindError
from app.models.orm import User
from app.models.schemas import PushTokenDeleteIn, PushTokenIn
from app.repositories import push_tokens as push_repo

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def register_push_token(
    body: PushTokenIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    try:
        await push_repo.upsert(
            session,
            user_id=user.id,
            expo_push_token=body.expo_push_token,
            platform=body.platform,
            device_id=body.device_id,
            android_channels=body.android_channels,
        )
    except PushTokenBindError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.message,
        ) from exc


@router.delete("/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_push_token(
    body: PushTokenDeleteIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await push_repo.delete_token(session, user.id, body.expo_push_token)
