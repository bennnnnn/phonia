from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import access_tokens, user_cache
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.redis import get_redis_client
from app.core.unavailable import RETRY_AFTER_SECONDS, unavailable_detail
from app.exceptions import AuthenticationError, RedisUnavailableError
from app.models.orm import User
from app.repositories import users as users_repo

security = HTTPBearer()


def redis_unavailable_http_exception(exc: RedisUnavailableError) -> HTTPException:
    """Map Redis outage to 503 + Retry-After, with the app's unavailable body (core/unavailable)."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=unavailable_detail(exc.message),
        headers={"Retry-After": RETRY_AFTER_SECONDS},
    )


async def get_settings_dep() -> Settings:
    return get_settings()


async def get_redis() -> Redis:
    """The Redis client. Async, so FastAPI resolves it on the loop, not in a worker thread."""
    return get_redis_client()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_db),
) -> User:
    try:
        access = await access_tokens.check_access(redis, credentials.credentials, settings)
    except RedisUnavailableError as exc:
        raise redis_unavailable_http_exception(exc) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    # This process's copy of the row, when it is still the current one (core/user_cache.py).
    cached = user_cache.cached_user(access.user_id, access.user_generation)
    if isinstance(cached, User):
        # Attach the cached row to this request so updates commit.
        return await session.merge(cached, load=False)
    if cached is not None:
        return cached

    user = await users_repo.get_by_id(session, access.user_id)
    # End the read now. FastAPI closes the request's session only after the response is sent,
    # so an SSE reply or a slow upload kept this connection idle in transaction throughout.
    # Nothing else has used the session yet, and expire_on_commit=False keeps the row loaded.
    await session.commit()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    user_cache.remember_user(user, access.user_generation)
    return user
