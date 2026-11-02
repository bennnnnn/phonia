"""/memories over HTTP."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.tests.api_support import api_user, app_with_user

# ── memories ───────────────────────────────────────────────────────────────────


def test_list_memories_empty():
    user = api_user()
    app = app_with_user(user)
    with patch(
        "app.modules.memory.enqueue_policy.memories_repo.list_for_user",
        AsyncMock(return_value=[]),
    ):
        client = TestClient(app)
        r = client.get("/memories", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_memories_skips_consolidation_scan_when_already_locked():
    """BUG FIX (perf): GET /memories runs on every plain list load. Once a
    consolidation job is already queued/locked for this user, a repeat load
    must not re-run facts_need_consolidation's text scan over every
    memory fact — it should short-circuit on the cheap lock check."""
    import fakeredis.aioredis

    user = api_user()
    app = app_with_user(user)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    def _messy_memory() -> MagicMock:
        m = MagicMock()
        m.id = uuid4()
        m.type = "profile"
        m.topic = "profile"
        m.text = "User's name is Bini. User's name is Binalfew. User is a developer."
        m.confidence = 0.9
        m.status = "active"
        m.sensitivity = "normal"
        m.importance = None
        m.last_confirmed_at = datetime(2024, 1, 1)
        m.source_chat_id = None
        m.source_chat_title = None
        m.source_message_id = None
        m.created_at = datetime(2024, 1, 1)
        m.updated_at = datetime(2024, 1, 1)
        return m

    with (
        patch("app.modules.memory.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.memory.enqueue_policy.memories_repo.list_for_user",
            AsyncMock(side_effect=lambda *a, **kw: [_messy_memory()]),
        ),
        patch("app.modules.memory.enqueue_policy.jobs.enqueue", AsyncMock()) as enqueue_job,
        patch(
            "app.modules.memory.consolidation.facts_need_consolidation",
            wraps=lambda memories: True,
        ) as scan_mock,
    ):
        client = TestClient(app)
        r1 = client.get("/memories", headers={"Authorization": "Bearer tok"})
        r2 = client.get("/memories", headers={"Authorization": "Bearer tok"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    # Second load found the lock already held and skipped the scan entirely.
    scan_mock.assert_called_once()
    enqueue_job.assert_awaited_once()


def test_delete_memory_not_found():
    user = api_user()
    app = app_with_user(user)
    with patch("app.modules.memory.crud.delete_memory", AsyncMock(return_value=False)):
        client = TestClient(app)
        r = client.delete(f"/memories/{uuid4()}", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 404


def test_update_memory_ok():
    user = api_user()
    app = app_with_user(user)
    memory_id = uuid4()
    updated = MagicMock()
    updated.id = memory_id
    updated.type = "fact"
    updated.topic = "interests"
    updated.text = "As of 2026-07-20: Likes hiking"
    updated.confidence = 0.9
    updated.status = "active"
    updated.sensitivity = "normal"
    updated.importance = None
    updated.last_confirmed_at = datetime(2026, 7, 20)
    updated.source_chat_id = None
    updated.source_chat_title = None
    updated.source_message_id = None
    updated.created_at = datetime(2026, 1, 1)
    updated.updated_at = datetime(2026, 7, 20)
    with patch(
        "app.modules.memory.crud.update_memory",
        AsyncMock(return_value=updated),
    ) as update:
        client = TestClient(app)
        r = client.patch(
            f"/memories/{memory_id}",
            headers={"Authorization": "Bearer tok"},
            json={"text": "Likes hiking"},
        )
    assert r.status_code == 200
    assert r.json()["text"] == "As of 2026-07-20: Likes hiking"
    assert r.json()["topic"] == "interests"
    update.assert_awaited_once()


def test_update_memory_not_found():
    user = api_user()
    app = app_with_user(user)
    with patch("app.modules.memory.crud.update_memory", AsyncMock(return_value=None)):
        client = TestClient(app)
        r = client.patch(
            f"/memories/{uuid4()}",
            headers={"Authorization": "Bearer tok"},
            json={"text": "Likes hiking"},
        )
    assert r.status_code == 404


def test_delete_memory_ok():
    user = api_user()
    app = app_with_user(user)
    with patch("app.modules.memory.crud.delete_memory", AsyncMock(return_value=True)):
        client = TestClient(app)
        r = client.delete(f"/memories/{uuid4()}", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 204


def test_delete_memory_write_lock_busy_returns_409_not_404():
    """A background extraction/consolidation pass holds the memory write
    lock — the router must surface this as a distinct, retryable 409, not
    the same 404 it uses for "no such memory"."""
    from app.modules.memory import locks

    user = api_user()
    app = app_with_user(user)
    with patch(
        "app.modules.memory.crud.delete_memory",
        AsyncMock(side_effect=locks.MemoryWriteLockBusyError(user.id)),
    ):
        client = TestClient(app)
        r = client.delete(f"/memories/{uuid4()}", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 409
