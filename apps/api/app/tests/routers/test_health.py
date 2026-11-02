import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
async def test_health_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_ready_ok():
    from unittest.mock import AsyncMock, patch

    transport = ASGITransport(app=app)
    with (
        patch("app.routers.health.SessionLocal") as session_local,
        patch("app.routers.health.get_redis_client") as get_redis,
    ):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session_local.return_value = session
        redis = redis_mock()
        redis.ping = AsyncMock()
        get_redis.return_value = redis

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "redis": "ok"}


@pytest.mark.asyncio
async def test_health_ready_ok_when_redis_degraded():
    from unittest.mock import AsyncMock, patch

    transport = ASGITransport(app=app)
    with (
        patch("app.routers.health.SessionLocal") as session_local,
        patch("app.routers.health.get_redis_client") as get_redis,
    ):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session_local.return_value = session
        get_redis.side_effect = RuntimeError("redis down")

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "redis": "degraded"}


@pytest.mark.asyncio
async def test_health_ready_fails_when_db_unavailable():
    from unittest.mock import patch

    transport = ASGITransport(app=app)
    with patch("app.routers.health.SessionLocal") as session_local:
        session_local.side_effect = RuntimeError("db down")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
    assert response.status_code == 503
