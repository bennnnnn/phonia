"""Shared per-user chat action throttle (WS + SSE)."""

from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

from app.core.rate_limit import allow_request_unless_down

# Same budget as the WebSocket per-message limiter — both transports count
# toward one 30/min/user bucket so SSE is not a bypass.
CHAT_MSG_RATE_LIMIT = 30
CHAT_MSG_WINDOW_SECONDS = 60


async def allow_chat_message(redis: Redis, user_id: UUID) -> bool:
    """False when the user has exceeded the chat-action rate limit.

    Redis down raises ``RedisUnavailableError``: SSE answers 503, the socket its
    ``unavailable`` frame, never the limit's "Too many chat requests".
    """
    return await allow_request_unless_down(
        redis,
        f"rate:chat:msg:{user_id}",
        limit=CHAT_MSG_RATE_LIMIT,
        window_seconds=CHAT_MSG_WINDOW_SECONDS,
    )
