"""Tests for the worker's tiny /health/ready HTTP server."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core import jobs
from app.worker_health import create_worker_health_app


def test_worker_health_liveness_endpoint():
    client = TestClient(create_worker_health_app())
    with patch("app.worker_health.get_redis_client"):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_worker_health_ready_when_worker_alive_and_redis_up():
    client = TestClient(create_worker_health_app())
    with (
        patch.object(jobs, "is_worker_alive", return_value=True),
        patch(
            "app.worker_health.periodic.started_periodic_unhealthy",
            return_value=[],
        ),
        patch("app.worker_health.get_redis_client") as redis_client,
    ):
        redis_client.return_value.ping = AsyncMock()
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_worker_health_not_ready_when_worker_loop_dead():
    client = TestClient(create_worker_health_app())
    with patch.object(jobs, "is_worker_alive", return_value=False):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert "worker loop" in response.json()["detail"]


def test_worker_health_not_ready_when_redis_unreachable():
    client = TestClient(create_worker_health_app())
    with (
        patch.object(jobs, "is_worker_alive", return_value=True),
        patch(
            "app.worker_health.periodic.started_periodic_unhealthy",
            return_value=[],
        ),
        patch("app.worker_health.get_redis_client") as redis_client,
    ):
        redis_client.return_value.ping = AsyncMock(side_effect=RuntimeError("redis down"))
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "Dependency check failed"


def test_worker_health_not_ready_when_periodic_loop_stale():
    client = TestClient(create_worker_health_app())
    with (
        patch.object(jobs, "is_worker_alive", return_value=True),
        patch(
            "app.worker_health.periodic.started_periodic_unhealthy",
            return_value=["push"],
        ),
    ):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "periodic loop not running: push"
