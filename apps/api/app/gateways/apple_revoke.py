"""Revoke a user's Sign in with Apple grant when they delete their account.

App Review guideline 5.1.1(v) asks apps that offer Sign in with Apple to
revoke the user's tokens on account deletion. Nothing Apple issues is stored:
when an Apple-linked user deletes their account, the phone runs Sign in with
Apple once more and sends the fresh authorization code with ``DELETE
/auth/me``. Here that code is exchanged at Apple's token endpoint, using a
client-secret JWT signed (ES256) with the team's Sign in with Apple key, and
the refresh token it returns is revoked.

Best effort by design: a missing key, Apple being slow or down, or a code for
a different Apple ID logs and returns False. It never blocks the delete.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
import jwt
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, apple_revoke_configured
from app.gateways.http_client import get_pooled_client

logger = logging.getLogger(__name__)

APPLE_AUDIENCE = "https://appleid.apple.com"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"
# Apple accepts a client secret valid for up to six months; one request needs minutes.
_CLIENT_SECRET_TTL_SECONDS = 300
_REQUEST_TIMEOUT_SECONDS = 5.0
# Both calls together: the delete answers the phone after this at the latest.
_DEADLINE_SECONDS = 8.0


class _AppleTokens(BaseModel):
    """The fields of Apple's token response used here."""

    refresh_token: str | None = None
    access_token: str | None = None
    id_token: str | None = None


def _private_key(settings: Settings) -> str:
    # Fly secrets and .env files often carry the .p8 newlines as "\n".
    return settings.apple_private_key.strip().replace("\\n", "\n")


def client_secret(settings: Settings, *, now: float | None = None) -> str:
    """The ES256 client-secret JWT Apple's token and revoke endpoints require."""
    issued = int(time.time() if now is None else now)
    return jwt.encode(
        {
            "iss": settings.apple_team_id.strip(),
            "iat": issued,
            "exp": issued + _CLIENT_SECRET_TTL_SECONDS,
            "aud": APPLE_AUDIENCE,
            "sub": settings.apple_client_id.strip(),
        },
        _private_key(settings),
        algorithm="ES256",
        headers={"kid": settings.apple_key_id.strip()},
    )


def _subject(id_token: str | None) -> str | None:
    """The Apple user id in the token response's id_token.

    The token came straight from Apple over TLS in answer to our signed
    request, so its signature is not checked again; only ``sub`` is read.
    """
    if not id_token:
        return None
    try:
        claims = jwt.decode(id_token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) else None


async def _exchange(client: httpx.AsyncClient, settings: Settings, code: str) -> _AppleTokens:
    response = await client.post(
        APPLE_TOKEN_URL,
        data={
            "client_id": settings.apple_client_id.strip(),
            "client_secret": client_secret(settings),
            "code": code,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    return _AppleTokens.model_validate(response.json())


async def _revoke(client: httpx.AsyncClient, settings: Settings, tokens: _AppleTokens) -> None:
    token, hint = (
        (tokens.refresh_token, "refresh_token")
        if tokens.refresh_token
        else (tokens.access_token, "access_token")
    )
    if not token:
        raise ValueError("Apple's token response had no token to revoke")
    response = await client.post(
        APPLE_REVOKE_URL,
        data={
            "client_id": settings.apple_client_id.strip(),
            "client_secret": client_secret(settings),
            "token": token,
            "token_type_hint": hint,
        },
    )
    response.raise_for_status()


async def revoke_authorization_code(settings: Settings, code: str, *, expected_sub: str) -> bool:
    """Revoke the Apple grant behind *code* when it belongs to *expected_sub*.

    True when Apple confirmed the revoke. Never raises.
    """
    if not apple_revoke_configured(settings):
        logger.warning("Apple token revoke skipped: the Sign in with Apple key is not set")
        return False
    client = get_pooled_client(_REQUEST_TIMEOUT_SECONDS)
    try:
        async with asyncio.timeout(_DEADLINE_SECONDS):
            tokens = await _exchange(client, settings, code)
            if _subject(tokens.id_token) != expected_sub:
                # The phone's Apple ID is not the one this account signed in with.
                logger.warning("Apple token revoke skipped: the code is for another Apple ID")
                return False
            await _revoke(client, settings, tokens)
    except (httpx.HTTPError, TimeoutError, ValidationError, ValueError, jwt.PyJWTError) as exc:
        logger.warning("Apple token revoke failed: %s", type(exc).__name__)
        return False
    except Exception:
        # Best effort (module docstring): e.g. a malformed key's parse error
        # must not fail the account delete that called this.
        logger.exception("Apple token revoke failed unexpectedly")
        return False
    logger.info("Apple token revoked on account delete")
    return True
