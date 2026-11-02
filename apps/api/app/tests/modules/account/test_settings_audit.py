"""Router tests for Settings UX audit endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.deps import get_redis
from app.tests.api_support import api_user, app_with_user


def test_me_includes_sign_in_provider():
    user = api_user(google_sub="google-abc")
    client = TestClient(app_with_user(user))
    r = client.get("/auth/me", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    assert r.json()["sign_in_provider"] == "google"
    assert r.json()["quiet_hours_enabled"] is False


def test_me_dev_sign_in_provider():
    user = api_user(google_sub="dev:dev@recall.local")
    client = TestClient(app_with_user(user))
    r = client.get("/auth/me", headers={"Authorization": "Bearer tok"})
    assert r.json()["sign_in_provider"] == "dev"


def test_me_apple_sign_in_provider():
    user = api_user(google_sub=None, apple_sub="apple.sub")
    client = TestClient(app_with_user(user))
    r = client.get("/auth/me", headers={"Authorization": "Bearer tok"})
    assert r.json()["sign_in_provider"] == "apple"


def test_patch_quiet_hours():
    user = api_user()
    updated = api_user()
    updated.quiet_hours_enabled = True
    updated.quiet_hours_start_minute = 1320
    updated.quiet_hours_end_minute = 420
    app = app_with_user(user)
    with patch(
        "app.modules.account.lifecycle.users_repo.update",
        AsyncMock(return_value=updated),
    ):
        client = TestClient(app)
        r = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={
                "quiet_hours_enabled": True,
                "quiet_hours_start_minute": 1320,
                "quiet_hours_end_minute": 420,
            },
        )
    assert r.status_code == 200
    assert r.json()["quiet_hours_enabled"] is True


def test_archive_all_chats():
    user = api_user()
    app = app_with_user(user)
    with patch(
        "app.modules.chat.api.chats_service.archive_all_chats",
        AsyncMock(return_value=3),
    ) as archive:
        client = TestClient(app)
        r = client.post("/chats/archive-all", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 204
    archive.assert_awaited_once()


def test_delete_all_chats():
    user = api_user()
    app = app_with_user(user)
    with patch(
        "app.modules.chat.api.chats_service.delete_all_chats",
        AsyncMock(return_value=2),
    ) as delete:
        client = TestClient(app)
        r = client.delete("/chats", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 204
    delete.assert_awaited_once()


def test_delete_all_memories():
    user = api_user()
    app = app_with_user(user)
    with patch(
        "app.modules.memory.crud.delete_all_memories",
        AsyncMock(return_value=5),
    ) as clear:
        client = TestClient(app)
        r = client.delete("/memories", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 204
    clear.assert_awaited_once()


def test_list_sessions():
    user = api_user()
    app = app_with_user(user)
    app.dependency_overrides[get_redis] = lambda: AsyncMock()
    rows = [
        {
            "id": str(uuid4()),
            "device_label": "iPhone",
            "platform": "ios",
            "created_at": datetime(2026, 1, 1).isoformat(),
            "last_seen_at": datetime(2026, 1, 2).isoformat(),
            "current": True,
        }
    ]
    with patch(
        "app.modules.account.api.tokens_service.list_sessions",
        AsyncMock(return_value=rows),
    ):
        client = TestClient(app)
        r = client.get("/auth/sessions", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    assert r.json()["sessions"][0]["device_label"] == "iPhone"
    assert r.json()["sessions"][0]["current"] is True


def test_list_sessions_answers_an_unchanged_list_with_304():
    user = api_user()
    app = app_with_user(user)
    app.dependency_overrides[get_redis] = lambda: AsyncMock()
    row = {
        "id": str(uuid4()),
        "device_label": "iPhone",
        "platform": "ios",
        "created_at": datetime(2026, 1, 1).isoformat(),
        "last_seen_at": datetime(2026, 1, 2).isoformat(),
        "current": True,
    }
    rows = [row]
    headers = {"Authorization": "Bearer tok"}
    with patch(
        "app.modules.account.api.tokens_service.list_sessions",
        AsyncMock(side_effect=lambda *_a, **_k: [dict(r) for r in rows]),
    ):
        client = TestClient(app)
        first = client.get("/auth/sessions", headers=headers)
        etag = first.headers["etag"]
        again = client.get("/auth/sessions", headers={**headers, "If-None-Match": etag})
        # The device refreshed its token: last seen moved, so the list is sent again.
        row["last_seen_at"] = datetime(2026, 1, 3).isoformat()
        moved = client.get("/auth/sessions", headers={**headers, "If-None-Match": etag})
    assert first.status_code == 200
    assert first.headers["cache-control"] == "private, no-cache"
    assert again.status_code == 304
    assert again.content == b""
    assert moved.status_code == 200
    assert moved.json()["sessions"][0]["last_seen_at"].startswith("2026-01-03")


def test_revoke_current_session_rejected():
    user = api_user()
    app = app_with_user(user)
    app.dependency_overrides[get_redis] = lambda: AsyncMock()
    from app.modules.account.tokens import CurrentSessionError

    with (
        patch(
            "app.modules.account.api.tokens_service.session_id_from_access_token",
            return_value="sid-1",
        ),
        patch(
            "app.modules.account.api.tokens_service.revoke_session",
            AsyncMock(side_effect=CurrentSessionError("Cannot revoke the current session")),
        ),
    ):
        client = TestClient(app)
        r = client.delete("/auth/sessions/sid-1", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 400


def test_logout_all():
    user = api_user()
    app = app_with_user(user)
    app.dependency_overrides[get_redis] = lambda: AsyncMock()
    with (
        patch(
            "app.modules.account.api.tokens_service.purge_user_sessions",
            AsyncMock(),
        ) as purge,
        patch(
            "app.modules.account.api.tokens_service.revoke_access_token",
            AsyncMock(),
        ),
    ):
        client = TestClient(app)
        r = client.post("/auth/logout-all", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 204
    purge.assert_awaited_once()


def test_patch_tone_keeps_stored_ids():
    user = api_user()
    updated = api_user(response_tone="funny")
    app = app_with_user(user)
    with patch(
        "app.modules.account.lifecycle.users_repo.update",
        AsyncMock(return_value=updated),
    ):
        client = TestClient(app)
        r = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={"response_tone": "funny"},
        )
    assert r.status_code == 200
    assert r.json()["response_tone"] == "funny"
