"""A database or Redis that is down or slow answers 503 + Retry-After, not a bare 500.

Pool exhaustion (``sqlalchemy.exc.TimeoutError`` after ``pool_timeout``), a
statement or connect timeout, or a refused connection used to reach the
client as ``500 Internal Server Error`` (text/plain), which clients treat as
a bug rather than something to retry.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from redis import exceptions as redis_exc
from sqlalchemy import exc as sa_exc

from app.exceptions import RedisUnavailableError
from app.main import create_app


def _operational() -> Exception:
    return sa_exc.OperationalError("SELECT 1", {}, Exception("server closed the connection"))


def _interface() -> Exception:
    return sa_exc.InterfaceError("SELECT 1", {}, Exception("connection is closed"))


@pytest.mark.parametrize(
    "make_error, expected_status",
    [
        (lambda: sa_exc.TimeoutError("QueuePool limit of size 20 overflow 10 reached"), 503),
        (lambda: TimeoutError(), 503),
        (_operational, 503),
        (_interface, 503),
        (lambda: ConnectionRefusedError(111, "Connection refused"), 503),
        # redis-py's own errors, reaching a route that didn't map them itself.
        (lambda: redis_exc.ConnectionError("Error 111 connecting to redis:6379"), 503),
        (lambda: redis_exc.TimeoutError("Timeout reading from socket"), 503),
        (lambda: RedisUnavailableError(), 503),
        (lambda: RuntimeError("a real bug"), 500),
    ],
)
async def test_database_unavailable_maps_to_503(make_error, expected_status: int) -> None:
    app = create_app()

    async def boom() -> None:
        raise make_error()

    app.add_api_route("/__test/boom", boom, methods=["GET"])
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get("/__test/boom")
    assert response.status_code == expected_status
    if expected_status == 503:
        assert response.headers.get("retry-after") == "5"
        assert response.json() == {
            "detail": {
                "code": "unavailable",
                "message": "Service temporarily unavailable. Please retry shortly.",
            }
        }


async def test_a_redis_unavailable_message_reaches_the_client() -> None:
    """Same body the routes' own ``redis_unavailable_http_exception`` sends."""
    app = create_app()

    async def boom() -> None:
        raise RedisUnavailableError("Sign-in is unavailable right now.")

    app.add_api_route("/__test/redis", boom, methods=["GET"])
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get("/__test/redis")
    assert response.status_code == 503
    assert response.headers.get("retry-after") == "5"
    assert response.json() == {
        "detail": {"code": "unavailable", "message": "Sign-in is unavailable right now."}
    }
