"""How often sign-in may run: Google and Apple per identity, with a looser per-IP backstop.

It was 30 a minute per IP for each provider, and the global REST limit (240 a minute per
unsigned IP) came first: behind one carrier NAT address the 31st person to sign in with
Google in a minute was refused. The budget that matters is the person's, read from the
verified token; the address keeps a limit only against floods. Token refresh does the
same (``refresh_limit.py``).

* **Per identity, 10 a minute.** Counted for the verified provider identity (provider +
  subject), after the token verifies and before an account is read or a session made.
  A person signs in by hand, once per device: five devices that each retry once stay
  under it. A client stuck in a loop, or a Google ID token replayed from many addresses
  (it lives an hour), mints at most 10 sessions a minute. Only a valid token for that
  identity spends it, so no one can lock another person out.
* **Per IP, 600 a minute, before the token is verified**, as refresh's. Twenty times the
  old limit: a lecture hall on one campus address, or a crowded carrier address at a
  launch peak, signs in within the minute. It was 300 while each Google verify fetched
  Google's certs; with provider keys kept per process (``gateways/signing_keys.py``) a
  verify costs about 0.08 ms of CPU on sign-in's two threads per machine
  (``core/blocking.py``), and a made-up key id at most one fetch per 30 s. A body that
  fails validation never gets that far. The global REST limit skips these two routes.
* **Dev login, 30 a minute per IP**, unchanged and still under the global limit: it
  verifies no token, so there is no identity to key on (the email is the caller's
  choice), and it answers loopback callers only, where no carrier NAT sits.

An identity is counted under an HMAC of it (the JWT secret, as quota carry-over does):
the raw subject never becomes a Redis key or a log line.

Each limit fails closed: while Redis is down no sign-in goes through. It raises
``RedisUnavailableError``, answered 503 ``sign_in_unavailable`` (``signin_refusals.py``):
the 429 it answered told people who had tried once that they had tried too often.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Request
from redis.asyncio import Redis

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.rate_limit import allow_request_unless_down
from app.modules.account.email_authority import SignInProvider

PER_IDENTITY_LIMIT = 10
PER_IP_LIMIT = 600
DEV_PER_IP_LIMIT = 30
WINDOW_SECONDS = 60


class SignInLimitedError(Exception):
    """This identity signed in ``PER_IDENTITY_LIMIT`` times this minute: the API answers 429."""


async def address_allowed(redis: Redis, request: Request, settings: Settings) -> bool:
    """Counts a Google or Apple sign-in from this address: False past ``PER_IP_LIMIT``."""
    return await allow_request_unless_down(
        redis,
        f"rate:auth:signin:ip:{client_ip(request, settings)}",
        limit=PER_IP_LIMIT,
        window_seconds=WINDOW_SECONDS,
    )


async def dev_address_allowed(redis: Redis, request: Request, settings: Settings) -> bool:
    """Counts a dev login from this address: False past ``DEV_PER_IP_LIMIT``."""
    return await allow_request_unless_down(
        redis,
        f"rate:auth:dev:{client_ip(request, settings)}",
        limit=DEV_PER_IP_LIMIT,
        window_seconds=WINDOW_SECONDS,
    )


def identity_key(settings: Settings, provider: SignInProvider, subject: str) -> str:
    """The identity's counter: an HMAC of provider and subject, never the subject itself."""
    digest = hmac.new(
        settings.jwt_secret.encode(),
        f"sign-in-limit:{provider}:{subject}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"rate:auth:signin:{provider}:{digest[:32]}"


async def require_identity(
    redis: Redis, settings: Settings, provider: SignInProvider, subject: str
) -> None:
    """Counts a sign-in for a verified identity; raises ``SignInLimitedError`` past the limit."""
    allowed = await allow_request_unless_down(
        redis,
        identity_key(settings, provider, subject),
        limit=PER_IDENTITY_LIMIT,
        window_seconds=WINDOW_SECONDS,
    )
    if not allowed:
        raise SignInLimitedError()
