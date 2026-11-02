"""Sign in with Apple grants are revoked on account delete; Apple is mocked."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import Settings, apple_revoke_configured
from app.gateways import apple_revoke

_KEY = ec.generate_private_key(ec.SECP256R1())
_PEM = _KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_PUBLIC = _KEY.public_key()


def _settings(**overrides: str) -> Settings:
    configured = Settings(
        apple_client_id="com.recall.app",
        apple_team_id="TEAM123456",
        apple_key_id="KEY1234567",
        apple_private_key=_PEM,
    )
    return configured.model_copy(update=overrides)


def _id_token(sub: str) -> str:
    return jwt.encode(
        {"sub": sub, "aud": "com.recall.app"},
        "the-gateway-does-not-check-this-signature",
        algorithm="HS256",
    )


Handler = Callable[[httpx.Request], httpx.Response]


def _apple(
    monkeypatch: pytest.MonkeyPatch,
    *,
    token: Handler | None = None,
    revoke: Handler | None = None,
) -> list[httpx.Request]:
    """Serve Apple's token and revoke endpoints; returns the requests made."""
    seen: list[httpx.Request] = []

    def default_token(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "id_token": _id_token("apple-sub"),
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url == apple_revoke.APPLE_TOKEN_URL:
            return (token or default_token)(request)
        if request.url == apple_revoke.APPLE_REVOKE_URL:
            return (revoke or (lambda _r: httpx.Response(200)))(request)
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(apple_revoke, "get_pooled_client", lambda _timeout: client)
    return seen


def _form(request: httpx.Request) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(request.content.decode()).items()}


def test_client_secret_is_an_es256_jwt_apple_accepts() -> None:
    secret = apple_revoke.client_secret(_settings(), now=1_700_000_000)
    assert jwt.get_unverified_header(secret) == {"alg": "ES256", "kid": "KEY1234567", "typ": "JWT"}
    claims = jwt.decode(
        secret,
        _PUBLIC,
        algorithms=["ES256"],
        audience="https://appleid.apple.com",
        options={"verify_exp": False},
    )
    assert claims == {
        "iss": "TEAM123456",
        "iat": 1_700_000_000,
        "exp": 1_700_000_300,
        "aud": "https://appleid.apple.com",
        "sub": "com.recall.app",
    }


def test_client_secret_reads_a_key_whose_newlines_are_escaped() -> None:
    escaped = _PEM.strip().replace("\n", "\\n")
    secret = apple_revoke.client_secret(_settings(apple_private_key=escaped))
    jwt.decode(secret, _PUBLIC, algorithms=["ES256"], audience="https://appleid.apple.com")


@pytest.mark.parametrize("unset", ["apple_team_id", "apple_key_id", "apple_private_key"])
def test_revoke_is_configured_only_with_the_whole_key(unset: str) -> None:
    assert apple_revoke_configured(_settings())
    assert not apple_revoke_configured(_settings(**{unset: "  "}))


@pytest.mark.asyncio
async def test_revoke_exchanges_the_code_then_revokes_the_refresh_token(monkeypatch) -> None:
    seen = _apple(monkeypatch)
    revoked = await apple_revoke.revoke_authorization_code(
        _settings(), "code-1", expected_sub="apple-sub"
    )
    assert revoked is True
    assert [str(request.url) for request in seen] == [
        apple_revoke.APPLE_TOKEN_URL,
        apple_revoke.APPLE_REVOKE_URL,
    ]
    exchange, revoke = (_form(request) for request in seen)
    assert exchange["grant_type"] == "authorization_code"
    assert exchange["code"] == "code-1"
    assert exchange["client_id"] == "com.recall.app"
    jwt.decode(
        exchange["client_secret"],
        _PUBLIC,
        algorithms=["ES256"],
        audience="https://appleid.apple.com",
    )
    assert revoke["token"] == "refresh-1"
    assert revoke["token_type_hint"] == "refresh_token"
    assert revoke["client_id"] == "com.recall.app"


@pytest.mark.asyncio
async def test_revoke_falls_back_to_the_access_token(monkeypatch) -> None:
    def token(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"access_token": "access-1", "id_token": _id_token("apple-sub")}
        )

    seen = _apple(monkeypatch, token=token)
    assert await apple_revoke.revoke_authorization_code(
        _settings(), "code-1", expected_sub="apple-sub"
    )
    assert _form(seen[1])["token_type_hint"] == "access_token"


@pytest.mark.asyncio
async def test_a_code_for_another_apple_id_is_not_revoked(monkeypatch, caplog) -> None:
    seen = _apple(monkeypatch)
    with caplog.at_level(logging.WARNING):
        revoked = await apple_revoke.revoke_authorization_code(
            _settings(), "code-1", expected_sub="someone-else"
        )
    assert revoked is False
    assert len(seen) == 1
    assert "another Apple ID" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token, revoke",
    [
        (lambda _r: httpx.Response(400, json={"error": "invalid_grant"}), None),
        (lambda _r: httpx.Response(200, content=b"not json"), None),
        (lambda _r: httpx.Response(200, json={"id_token": _id_token("apple-sub")}), None),
        (None, lambda _r: httpx.Response(503)),
    ],
    ids=["expired-code", "garbage", "no-token", "revoke-down"],
)
async def test_revoke_failures_return_false_and_never_raise(monkeypatch, token, revoke) -> None:
    _apple(monkeypatch, token=token, revoke=revoke)
    assert not await apple_revoke.revoke_authorization_code(
        _settings(), "code-1", expected_sub="apple-sub"
    )


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_a_slow_apple_ends_at_the_deadline(monkeypatch) -> None:
    async def slow(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    monkeypatch.setattr(apple_revoke, "get_pooled_client", lambda _timeout: client)
    monkeypatch.setattr(apple_revoke, "_DEADLINE_SECONDS", 0.2)
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert not await apple_revoke.revoke_authorization_code(
        _settings(), "code-1", expected_sub="apple-sub"
    )
    assert loop.time() - started < 2.0


@pytest.mark.asyncio
async def test_a_malformed_key_fails_soft(monkeypatch) -> None:
    seen = _apple(monkeypatch)
    assert not await apple_revoke.revoke_authorization_code(
        _settings(apple_private_key="-----BEGIN PRIVATE KEY-----\nnope\n-----END PRIVATE KEY-----"),
        "code-1",
        expected_sub="apple-sub",
    )
    assert seen == []


@pytest.mark.asyncio
async def test_revoke_is_skipped_without_the_apple_key(monkeypatch, caplog) -> None:
    seen = _apple(monkeypatch)
    with caplog.at_level(logging.WARNING):
        revoked = await apple_revoke.revoke_authorization_code(
            _settings(apple_private_key=""), "code-1", expected_sub="apple-sub"
        )
    assert revoked is False
    assert seen == []
    assert "not set" in caplog.text
