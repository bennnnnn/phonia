"""How often ``POST /auth/refresh`` may run: per account, with a looser per-IP backstop.

It was 60 a minute per IP. Behind carrier-grade NAT thousands of phones share one public
address, each refreshing about once an hour (an access token lasts 60 minutes), so a busy
address was refused for everyone behind it. The budget that matters is the account's,
read from the refresh token itself; the address keeps a limit only against floods.

* **Per account, 10 a minute.** A phone refreshes once an hour, one refresh at a time
  (the client shares one in flight), so even five signed-in devices that all wake in the
  same minute and each retry once stay under it. A client stuck in a loop stops at 10.
* **Per IP, 600 a minute.** 36,000 hourly refreshes from one address: a large NAT pool at
  ten times its average rate, while one host still gets no more than ten tries a second.
  The global REST limit (240 a minute per unsigned IP) skips this route for that reason.

A token that names no live session (expired, rotated, made up) is counted under a hash
of itself: the raw token never becomes a Redis key or a log line.

Both fail closed: while Redis is down no refresh goes through. They raise
``RedisUnavailableError``, which the app answers 503 + Retry-After 5 as for every other
request then. It was 429 + Retry-After 60: the phone took the outage for a limit, live
talk said the month's minutes were used up, and requests that needed a refresh kept
failing for up to a minute after Redis was back.
"""

from __future__ import annotations

import hashlib

from fastapi import Request
from redis.asyncio import Redis

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.rate_limit import allow_request_unless_down
from app.modules.account import tokens as tokens_service

PER_ACCOUNT_LIMIT = 10
PER_IP_LIMIT = 600
WINDOW_SECONDS = 60


async def address_allowed(redis: Redis, request: Request, settings: Settings) -> bool:
    """Counts a refresh from this address: False past ``PER_IP_LIMIT`` this minute."""
    return await allow_request_unless_down(
        redis,
        f"rate:auth:refresh:ip:{client_ip(request, settings)}",
        limit=PER_IP_LIMIT,
        window_seconds=WINDOW_SECONDS,
    )


async def account_allowed(redis: Redis, refresh_token: str) -> bool:
    """Counts a refresh for the token's account: False past ``PER_ACCOUNT_LIMIT`` this minute."""
    user_id = await tokens_service.refresh_token_user(redis, refresh_token)
    if user_id is not None:
        subject = f"user:{user_id}"
    else:
        subject = f"token:{hashlib.sha256(refresh_token.encode()).hexdigest()[:32]}"
    return await allow_request_unless_down(
        redis,
        f"rate:auth:refresh:{subject}",
        limit=PER_ACCOUNT_LIMIT,
        window_seconds=WINDOW_SECONDS,
    )
