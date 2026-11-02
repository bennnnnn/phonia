"""Enqueue transactional emails; ``background/handlers.py`` sends them."""

from uuid import UUID

from redis.asyncio import Redis

from app.core import jobs


async def enqueue_welcome_email(redis: Redis, user_id: UUID) -> None:
    await jobs.enqueue(
        redis,
        "transactional_email",
        {"kind": "welcome", "user_id": str(user_id)},
        dedupe_key=f"welcome:{user_id}",
    )


async def enqueue_purchase_receipt(
    redis: Redis,
    user_id: UUID | str,
    *,
    event_type: str,
    store: str | None = None,
    product_id: str | None = None,
    expiration: str | None = None,
) -> None:
    uid = str(user_id)
    await jobs.enqueue(
        redis,
        "transactional_email",
        {
            "kind": "receipt",
            "user_id": uid,
            "event_type": event_type,
            "store": store,
            "product_id": product_id,
            "expiration": expiration,
        },
        dedupe_key=f"receipt:{uid}:{event_type}:{product_id or ''}",
    )
