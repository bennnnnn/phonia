"""The admin dead-letter queue endpoints."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.tests.api_support import api_user, app_with_user

# ── admin DLQ ─────────────────────────────────────────────────────────────────


def test_admin_dlq_dev_gated_returns_403_in_production():
    user = api_user()
    app = app_with_user(user)  # default Settings has dev_auth_enabled=True, but…

    with patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)):
        client = TestClient(app)
        # Settings() defaults dev_auth_enabled=True; force production behavior.
        from app.core.deps import get_settings_dep

        app.dependency_overrides[get_settings_dep] = lambda: Settings(dev_auth_enabled=False)
        r = client.get("/admin/dlq", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 403


def test_admin_dlq_list_and_replay_in_dev():
    user = api_user()
    app = app_with_user(user)
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True,
        admin_user_ids=str(user.id),
    )

    listed = [
        {
            "id": "1-0",
            "original_id": "0-0",
            "type": "memory",
            "payload": "{}",
            "error": "boom",
            "failed_at": "2026-07-02T00:00:00+00:00",
        }
    ]
    with (
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
        patch("app.routers.admin.jobs.list_dlq", AsyncMock(return_value=listed)),
        patch("app.routers.admin.jobs.replay_dlq", AsyncMock(return_value=1)),
    ):
        client = TestClient(app)
        r_list = client.get("/admin/dlq", headers={"Authorization": "Bearer tok"})
        assert r_list.status_code == 200
        body = r_list.json()
        assert len(body) == 1
        assert body[0]["type"] == "memory"

        r_replay = client.post("/admin/dlq/replay", headers={"Authorization": "Bearer tok"})
        assert r_replay.status_code == 200
        assert r_replay.json()["replayed"] == 1


def test_admin_dlq_denies_non_allowlisted_user_in_dev():
    user = api_user()
    app = app_with_user(user)
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True,
        admin_user_ids=str(uuid4()),
    )

    with patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)):
        client = TestClient(app)
        r = client.get("/admin/dlq", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 403


def test_admin_dlq_denies_when_admin_allowlist_empty():
    user = api_user()
    app = app_with_user(user)
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True,
        admin_user_ids="",
    )

    with patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)):
        client = TestClient(app)
        r = client.get("/admin/dlq", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 403
    assert "ADMIN_USER_IDS" in r.json()["detail"]


def test_admin_dlq_count_is_bounded():
    user = api_user()
    app = app_with_user(user)
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True,
        admin_user_ids=str(user.id),
    )
    with (
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
        patch("app.routers.admin.jobs.list_dlq", AsyncMock(return_value=[])),
        patch("app.routers.admin.jobs.replay_dlq", AsyncMock(return_value=0)),
    ):
        client = TestClient(app)
        headers = {"Authorization": "Bearer tok"}
        assert client.get("/admin/dlq?count=0", headers=headers).status_code == 422
        assert client.get("/admin/dlq?count=1000000", headers=headers).status_code == 422
        assert client.post("/admin/dlq/replay?count=-1", headers=headers).status_code == 422
        assert client.get("/admin/dlq?count=50", headers=headers).status_code == 200


def test_admin_dlq_skips_malformed_entries():
    user = api_user()
    app = app_with_user(user)
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True,
        admin_user_ids=str(user.id),
    )
    listed = [
        {
            "id": "1-0",
            "original_id": "0-0",
            "type": "memory",
            "payload": "{}",
            "error": "boom",
            "failed_at": "2026-07-02T00:00:00+00:00",
        },
        {"id": "2-0", "original_id": "1-0"},
    ]
    with (
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
        patch("app.routers.admin.jobs.list_dlq", AsyncMock(return_value=listed)),
    ):
        client = TestClient(app)
        r = client.get("/admin/dlq", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == "1-0"
