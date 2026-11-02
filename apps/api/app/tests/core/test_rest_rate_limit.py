from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.requests import Request

from app.core.config import Settings
from app.core.rest_rate_limit import _client_key
from app.main import create_app
from app.tests.fakes import redis_mock


def test_client_key_uses_user_from_bearer():
    settings = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    from app.core.access_tokens import create_access_token

    user_id = uuid4()
    token = create_access_token(user_id, settings)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/chats",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "client": ("127.0.0.1", 1234),
    }
    request = Request(scope)
    assert _client_key(request, settings) == f"user:{user_id}"


def test_client_key_falls_back_to_ip():
    settings = Settings()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/chats",
        "headers": [],
        "client": ("10.0.0.5", 1234),
    }
    request = Request(scope)
    assert _client_key(request, settings) == "ip:10.0.0.5"


def test_middleware_skips_health_when_rate_limited():
    with (
        patch("app.core.rest_rate_limit.get_redis_client", return_value=AsyncMock()),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=False)),
    ):
        client = TestClient(create_app())
        assert client.get("/health").status_code == 200


def test_middleware_returns_429_when_over_limit():
    settings = Settings(
        cors_origins="http://localhost:8081",
        rest_rate_limit_per_minute=60,
        jwt_secret="test-secret-32-chars-long-enough!!",
    )
    with (
        patch("app.main.get_settings", return_value=settings),
        patch("app.core.rest_rate_limit.get_settings", return_value=settings),
        patch("app.core.rest_rate_limit.get_redis_client", return_value=AsyncMock()),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=False)),
    ):
        client = TestClient(create_app())
        response = client.get(
            "/openapi.json",
            headers={"Origin": "http://localhost:8081"},
        )
    assert response.status_code == 429
    # The shared coded body: the phone switches on the code, as for every refusal. The
    # English alone (no code) read as "Couldn't reach the server" in a chat and as the
    # generic sign-in failure on dev login.
    assert response.json() == {
        "detail": {"code": "rate_limited", "message": "Too many requests. Please slow down."}
    }
    assert response.headers.get("retry-after") == "60"
    # CORS must wrap rate-limit so browsers see a real 429, not a network error.
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8081"


def test_middleware_skips_when_limit_disabled():
    with patch("app.core.config.get_settings", return_value=Settings(rest_rate_limit_per_minute=0)):
        client = TestClient(create_app())
        assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize(
    "error", [RuntimeError("redis down"), RedisConnectionError("Error 111 connecting")]
)
def test_middleware_fails_closed_with_503_when_redis_check_fails(error: Exception) -> None:
    # A Redis outage must not let the rate limiter silently disappear — that
    # would expose every protected endpoint to unbounded traffic. Fail closed,
    # as every route does while Redis is down: 503 unavailable, Retry-After 5.
    # It was 429 "Rate limit unavailable", which the phone reads as a limit.
    broken = redis_mock()
    # The limiter counts in a pipeline: its INCR is what fails.
    broken.incr.side_effect = error
    with patch("app.core.rest_rate_limit.get_redis_client", return_value=broken):
        client = TestClient(create_app())
        response = client.get("/openapi.json")
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "unavailable",
            "message": "Service temporarily unavailable. Please retry shortly.",
        }
    }
    assert response.headers.get("retry-after") == "5"


def test_middleware_still_answers_429_over_the_limit_with_redis_up() -> None:
    """A real limit hit stays a 429: only an outage is a 503."""
    redis = redis_mock()
    redis.incr.return_value = 1_000_000  # this minute's count, past any limit
    with patch("app.core.rest_rate_limit.get_redis_client", return_value=redis):
        response = TestClient(create_app()).get("/openapi.json")
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "rate_limited"
    assert response.headers.get("retry-after") == "60"


def test_client_key_falls_back_to_ip_on_invalid_bearer():
    settings = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/chats",
        "headers": [(b"authorization", b"Bearer not-a-jwt")],
        "client": ("10.0.0.5", 1234),
    }
    request = Request(scope)
    assert _client_key(request, settings) == "ip:10.0.0.5"
