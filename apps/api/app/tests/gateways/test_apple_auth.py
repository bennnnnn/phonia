"""Tests for Sign in with Apple token verification."""

import hashlib
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.exceptions import AuthenticationError
from app.gateways import apple_auth
from app.gateways.apple_auth import verify_apple_id_token
from app.gateways.signing_keys import REFETCH_INTERVAL_SECONDS

RAW_NONCE = "raw-nonce-from-the-app"
_UNSET: Any = object()


def _make_apple_token(
    *,
    sub: str = "apple-user-1",
    email: str = "user@privaterelay.appleid.com",
    nonce: Any = _UNSET,
    exp: Any = _UNSET,
) -> tuple[str, str, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public_key)
    import json

    kid = "test-kid"
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": "https://appleid.apple.com",
        "aud": "com.recall.app",
        "sub": sub,
        "email": email,
        "email_verified": True,
        "iat": now,
        "exp": now + 600 if exp is _UNSET else exp,
        # The app passes SHA-256(raw nonce) to Apple; Apple echoes it here.
        "nonce": hashlib.sha256(RAW_NONCE.encode()).hexdigest() if nonce is _UNSET else nonce,
    }
    token = jwt.encode(
        {key: value for key, value in claims.items() if value is not None},
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )
    return token, kid, json.loads(jwk)


def _jwks(kid: str, jwk: dict[str, Any]) -> dict[str, Any]:
    return {"keys": [{**jwk, "kid": kid, "alg": "RS256", "use": "sig"}]}


@pytest.mark.asyncio
async def test_verify_apple_id_token_accepts_valid_token():
    token, kid, jwk = _make_apple_token()
    settings = Settings(apple_client_id="com.recall.app")

    with patch(
        "app.gateways.apple_auth._fetch_apple_jwks", AsyncMock(return_value=_jwks(kid, jwk))
    ):
        payload = await verify_apple_id_token(token, settings, nonce=RAW_NONCE)

    assert payload["sub"] == "apple-user-1"
    assert payload["email"] == "user@privaterelay.appleid.com"


@pytest.mark.asyncio
async def test_verify_apple_id_token_rejects_wrong_audience():
    token, kid, jwk = _make_apple_token()
    settings = Settings(apple_client_id="com.other.app")

    with (
        patch("app.gateways.apple_auth._fetch_apple_jwks", AsyncMock(return_value=_jwks(kid, jwk))),
        pytest.raises(AuthenticationError, match="Invalid Apple ID token"),
    ):
        await verify_apple_id_token(token, settings, nonce=RAW_NONCE)


@pytest.mark.parametrize(
    "token_nonce, sent_nonce",
    [
        # A token replayed from another sign-in carries that sign-in's nonce.
        ("sha256-of-some-other-nonce", RAW_NONCE),
        # The app sent no nonce, or the token was minted without one.
        (_UNSET, None),
        (_UNSET, ""),
        (None, RAW_NONCE),
        # The raw value itself must not be accepted in place of its hash.
        (RAW_NONCE, RAW_NONCE),
    ],
)
@pytest.mark.asyncio
async def test_verify_apple_id_token_rejects_a_token_not_bound_to_this_sign_in(
    token_nonce, sent_nonce
):
    token, kid, jwk = _make_apple_token(nonce=token_nonce)
    settings = Settings(apple_client_id="com.recall.app")

    with (
        patch("app.gateways.apple_auth._fetch_apple_jwks", AsyncMock(return_value=_jwks(kid, jwk))),
        pytest.raises(AuthenticationError, match="Invalid Apple ID token"),
    ):
        await verify_apple_id_token(token, settings, nonce=sent_nonce)


@pytest.mark.parametrize("exp", [None, 1_000])
@pytest.mark.asyncio
async def test_verify_apple_id_token_rejects_missing_or_past_expiry(exp):
    token, kid, jwk = _make_apple_token(exp=exp)
    settings = Settings(apple_client_id="com.recall.app")

    with (
        patch("app.gateways.apple_auth._fetch_apple_jwks", AsyncMock(return_value=_jwks(kid, jwk))),
        pytest.raises(AuthenticationError, match="Invalid Apple ID token"),
    ):
        await verify_apple_id_token(token, settings, nonce=RAW_NONCE)


@pytest.mark.asyncio
async def test_verify_apple_id_token_requires_server_config():
    settings = Settings(apple_client_id="")
    with pytest.raises(AuthenticationError, match="not configured"):
        await verify_apple_id_token("bad.token.here", settings, nonce=RAW_NONCE)


@pytest.mark.asyncio
async def test_public_key_for_kid_refetches_jwks_on_kid_miss(monkeypatch: pytest.MonkeyPatch):
    import time

    import app.gateways.apple_auth as apple_auth

    _, kid, jwk = _make_apple_token()
    jwks = {"keys": [{**jwk, "kid": kid, "alg": "RS256", "use": "sig"}]}
    monkeypatch.setattr(apple_auth, "_jwks_cache", {"keys": []})
    monkeypatch.setattr(apple_auth, "_jwks_fetched_at", time.time())

    with patch(
        "app.gateways.apple_auth._fetch_apple_jwks",
        AsyncMock(side_effect=[{"keys": []}, jwks]),
    ) as fetch:
        key = await apple_auth._public_key_for_kid(kid)

    assert key is not None
    assert fetch.call_count == 2
    # Second call is a forced refresh, not a second reliance on the stale cache.
    fetch.assert_any_call(force_refresh=True)


@pytest.mark.asyncio
async def test_fetch_apple_jwks_uses_cache_within_ttl(monkeypatch: pytest.MonkeyPatch):
    import time

    import app.gateways.apple_auth as apple_auth

    cached = {"keys": [{"kid": "cached"}]}
    monkeypatch.setattr(apple_auth, "_jwks_cache", cached)
    monkeypatch.setattr(apple_auth, "_jwks_fetched_at", time.time())

    with patch("app.gateways.apple_auth.get_pooled_client") as mock_client_cls:
        result = await apple_auth._fetch_apple_jwks()

    assert result is cached
    mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_apple_jwks_force_refresh_bypasses_cache(monkeypatch: pytest.MonkeyPatch):
    import time

    import app.gateways.apple_auth as apple_auth

    monkeypatch.setattr(apple_auth, "_jwks_cache", {"keys": [{"kid": "stale"}]})
    monkeypatch.setattr(apple_auth, "_jwks_fetched_at", time.time() - REFETCH_INTERVAL_SECONDS - 1)

    fresh = {"keys": [{"kid": "fresh"}]}
    client_instance = AsyncMock()
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: fresh
    client_instance.get = AsyncMock(return_value=response)

    with patch("app.gateways.apple_auth.get_pooled_client") as mock_client_cls:
        mock_client_cls.return_value = client_instance
        result = await apple_auth._fetch_apple_jwks(force_refresh=True)

    assert result == fresh
    client_instance.get.assert_awaited_once_with(apple_auth.APPLE_JWKS_URL)


class _AppleKeysReply:
    """Apple's keys endpoint answering ``status`` with ``body``."""

    def __init__(self, status: int, body: str) -> None:
        self._reply = httpx.Response(status, text=body, request=httpx.Request("GET", "https://k"))

    def raise_for_status(self) -> None:
        self._reply.raise_for_status()

    def json(self) -> Any:
        return self._reply.json()


@pytest.mark.parametrize(
    "fetch",
    [
        AsyncMock(side_effect=httpx.ConnectError("down")),
        AsyncMock(return_value=_AppleKeysReply(502, "Bad gateway")),
        AsyncMock(return_value=_AppleKeysReply(200, "<html>maintenance</html>")),
    ],
    ids=["network", "status", "not json"],
)
@pytest.mark.asyncio
async def test_unreachable_apple_keys_are_unavailable_not_an_invalid_token(
    monkeypatch: pytest.MonkeyPatch, fetch: AsyncMock
):
    """It answered 401 "Invalid Apple ID token" while Apple was out of reach (a bad body: 500)."""
    import app.gateways.apple_auth as apple_auth

    token, _kid, _jwk = _make_apple_token()
    monkeypatch.setattr(apple_auth, "_jwks_cache", None)
    client = AsyncMock(get=fetch)

    with (
        patch("app.gateways.apple_auth.get_pooled_client", return_value=client),
        pytest.raises(apple_auth.AppleAuthUnavailableError) as caught,
    ):
        await verify_apple_id_token(token, Settings(apple_client_id="com.recall.app"), nonce="n")
    assert caught.value.code == "apple_unavailable"


def _apple_keys(*jwks: dict[str, Any]) -> AsyncMock:
    """Apple's keys endpoint on the pooled client: ``get`` answers ``jwks``."""
    reply = AsyncMock()
    reply.raise_for_status = lambda: None
    reply.json = lambda: {"keys": list(jwks)}
    return AsyncMock(get=AsyncMock(return_value=reply))


@pytest.mark.asyncio
async def test_100_junk_tokens_naming_unknown_key_ids_fetch_apples_keys_once():
    """Each forced a refetch: 100 junk tokens made 101 fetches of Apple's keys."""
    _token, kid, jwk = _make_apple_token()
    client = _apple_keys(_jwks(kid, jwk)["keys"][0])
    settings = Settings(apple_client_id="com.recall.app")
    junk = [
        jwt.encode(
            {"sub": "x"},
            "not-apples-key-but-thirty-two-bytes-long",
            headers={"kid": f"made-up-{n}"},
        )
        for n in range(100)
    ]
    with patch("app.gateways.apple_auth.get_pooled_client", return_value=client):
        for token in junk:
            with pytest.raises(AuthenticationError, match="signing key not found"):
                await verify_apple_id_token(token, settings, nonce=RAW_NONCE)
    assert client.get.await_count == 1


@pytest.mark.parametrize(
    "fetched_seconds_ago, fetches", [(1, 0), (REFETCH_INTERVAL_SECONDS + 1, 1)]
)
@pytest.mark.asyncio
async def test_a_key_apple_rotated_in_is_fetched_once_the_interval_has_passed(
    monkeypatch: pytest.MonkeyPatch, fetched_seconds_ago: float, fetches: int
):
    import time

    token, kid, jwk = _make_apple_token()
    monkeypatch.setattr(apple_auth, "_jwks_cache", {"keys": [{"kid": "older-key"}]})
    monkeypatch.setattr(apple_auth, "_jwks_fetched_at", time.time() - fetched_seconds_ago)
    client = _apple_keys(_jwks(kid, jwk)["keys"][0])
    settings = Settings(apple_client_id="com.recall.app")
    with patch("app.gateways.apple_auth.get_pooled_client", return_value=client):
        if fetches:
            payload = await verify_apple_id_token(token, settings, nonce=RAW_NONCE)
            assert payload["sub"] == "apple-user-1"
        else:
            with pytest.raises(AuthenticationError, match="signing key not found"):
                await verify_apple_id_token(token, settings, nonce=RAW_NONCE)
    assert client.get.await_count == fetches
