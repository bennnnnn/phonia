"""Tests for account deletion + data export."""

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.deps import get_redis
from app.main import create_app


def _fake_user():
    u = MagicMock()
    u.id = uuid4()
    u.email = "t@recall.local"
    u.name = "Tester"
    u.created_at = datetime(2024, 1, 1)
    return u


class _BorrowedSession:
    """Use the test's session without closing it."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_args: object) -> None:
        return None


async def _export(session, user, settings: Settings | None = None) -> dict[str, Any]:
    """The JSON the streamed export (``iter_export_json``) sends, read on the test's session."""
    from app.modules.account import export as export_service

    with patch.object(export_service, "SessionLocal", lambda: _BorrowedSession(session)):
        chunks = [chunk async for chunk in export_service.iter_export_json(user, settings)]
    return json.loads("".join(chunks))


def _app_with_user(user):
    from app.core.deps import get_current_user, get_settings_dep

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    return app


@pytest.fixture(autouse=True)
def _empty_product_events_for_exports():
    with (
        patch(
            "app.modules.account.export.product_events_repo.list_for_user",
            AsyncMock(return_value=[]),
        ) as list_events,
        patch(
            "app.modules.memory.repository.list_areas",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.suggestions_service.list_for_export",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.usage_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.push_tokens_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
    ):
        yield list_events


def test_delete_account_returns_204():
    user = _fake_user()
    app = _app_with_user(user)
    order: list[str] = []

    def step(name: str, result: Any = None) -> AsyncMock:
        def record(*_a: Any, **_k: Any) -> Any:
            order.append(name)
            return result

        return AsyncMock(side_effect=record)

    lifecycle = "app.modules.account.lifecycle"
    with (
        patch(f"{lifecycle}.quota_carryover.save_on_delete", step("carry")),
        patch(f"{lifecycle}.schedule_job", step("backstop_sweep")),
        patch(f"{lifecycle}.users_repo.delete_user", step("delete_rows")),
        patch(f"{lifecycle}.tokens_service.purge_user_sessions", step("purge_sessions")),
        patch(f"{lifecycle}.attachments_service.delete_account_files", step("delete_files")),
        patch(f"{lifecycle}.enqueue", step("sweep")) as enqueue_mock,
    ):
        client = TestClient(app)
        r = client.delete("/auth/me", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 204
    # The usage counters are carried first, while a refusal undoes nothing; the backstop
    # sweep is scheduled before the rows go. Sessions end and files go only once the rows
    # commit: a database failure before that leaves the account whole and signed in.
    # (A cached user row elsewhere is still refused: its token's session is revoked.)
    assert order == [
        "carry",
        "backstop_sweep",
        "delete_rows",
        "purge_sessions",
        "delete_files",
        "sweep",
    ]
    assert enqueue_mock.await_args.args[1] == "storage_sweep"


_UNAVAILABLE = {
    "detail": {
        "code": "unavailable",
        "message": "Service temporarily unavailable. Please retry shortly.",
    }
}


@pytest.mark.parametrize("step", ["carry", "backstop_sweep"])
def test_delete_account_with_redis_failing_is_refused_503_unavailable(step: str) -> None:
    """Redis failing before the rows commit refuses the delete with the shared outage body:
    the phone says Recall is unavailable and to try again. The carry-over was best-effort
    (its failure lost the day's counters, ``security/test_quota_carryover.py``). A refusal
    undoes nothing, sessions included: the retry needs no sign-in."""
    user = _fake_user()
    user.google_sub = "google-sub"
    user.apple_sub = None
    down = AsyncMock(side_effect=RedisConnectionError("Error 111 connecting to redis"))
    zadd = AsyncMock(side_effect=RedisConnectionError("Error 111 connecting to redis"))
    redis = MagicMock(mget=down, set=down, zadd=zadd)
    if step == "backstop_sweep":
        # Nothing used today, so nothing to carry: the backstop is reached.
        redis.mget = AsyncMock(side_effect=lambda keys: [None] * len(keys))
    app = _app_with_user(user)
    app.dependency_overrides[get_redis] = lambda: redis
    purge = AsyncMock()
    with (
        patch("app.modules.account.lifecycle.tokens_service.purge_user_sessions", purge),
        patch("app.modules.account.lifecycle.users_repo.delete_user", AsyncMock()) as delete_user,
    ):
        response = TestClient(app).delete("/auth/me", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 503
    assert response.json() == _UNAVAILABLE
    assert response.headers["retry-after"] == "5"
    assert zadd.await_count == (step == "backstop_sweep")
    purge.assert_not_awaited()
    delete_user.assert_not_awaited()


def test_delete_account_returns_204_when_one_storage_delete_fails():
    """R2 outage on one object must not leave the account wipe unfinished: the rows are
    gone, the failed object is queued for the retry, and the sweep deletes the prefix."""
    user = _fake_user()
    app = _app_with_user(user)

    async def delete_bytes(key: str) -> None:
        if key == "user/bad":
            raise RuntimeError("r2 down")

    gateway = MagicMock()
    gateway.delete_bytes = delete_bytes
    lifecycle = "app.modules.account.lifecycle"
    with (
        patch(f"{lifecycle}.quota_carryover.save_on_delete", AsyncMock()),
        patch(f"{lifecycle}.schedule_job", AsyncMock()),
        patch(f"{lifecycle}.tokens_service.purge_user_sessions", AsyncMock()),
        patch(
            f"{lifecycle}.attachments_service.delete_user_rows",
            AsyncMock(return_value=["user/ok", "user/bad"]),
        ),
        patch(f"{lifecycle}.users_repo.delete_user", AsyncMock()) as delete_user,
        patch("app.modules.attachments.lifecycle.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.lifecycle.delete_thumbnails", AsyncMock(return_value=True)),
        patch(
            "app.modules.attachments.lifecycle.enqueue_failed_storage_deletes", AsyncMock()
        ) as queued,
        patch(f"{lifecycle}.enqueue", AsyncMock()) as sweep,
    ):
        client = TestClient(app)
        r = client.delete("/auth/me", headers={"Authorization": "Bearer tok"})

    assert r.status_code == 204
    delete_user.assert_awaited_once()
    queued.assert_awaited_once_with(["user/bad"])
    sweep.assert_awaited_once()


def test_export_returns_data():
    user = _fake_user()
    app = _app_with_user(user)

    async def fake_iter(_user):
        yield '{"exported_at":"now","export_limits":{},"user":{},"chats":[],"memories":[]}'

    with patch("app.modules.account.api.export_service.iter_export_json", fake_iter):
        client = TestClient(app)
        r = client.get("/auth/me/export", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    assert r.json()["exported_at"] == "now"


def test_export_runs_one_at_a_time_per_user():
    """One account could start dozens of exports at once, each reading ~1M rows."""
    user = _fake_user()
    app = _app_with_user(user)

    async def fake_iter(_user):
        yield "{}"

    with (
        patch("app.modules.account.api.export_service.iter_export_json", fake_iter),
        patch("app.modules.account.api.acquire_lock", AsyncMock(side_effect=["token", None])),
        patch("app.modules.account.api.release_lock", AsyncMock()) as release,
    ):
        client = TestClient(app)
        first = client.get("/auth/me/export", headers={"Authorization": "Bearer tok"})
        second = client.get("/auth/me/export", headers={"Authorization": "Bearer tok"})
    assert first.status_code == 200
    assert second.status_code == 429
    release.assert_awaited_once()


def test_export_is_capped_per_hour():
    user = _fake_user()
    app = _app_with_user(user)

    async def fake_iter(_user):
        yield "{}"

    with patch("app.modules.account.api.export_service.iter_export_json", fake_iter):
        client = TestClient(app)
        codes = [
            client.get("/auth/me/export", headers={"Authorization": "Bearer tok"}).status_code
            for _ in range(4)
        ]
    assert codes == [200, 200, 200, 429]


@pytest.mark.asyncio
async def test_delete_user_deletes_children_then_user():
    from app.repositories import users as users_repo

    session = AsyncMock()
    session.get = AsyncMock(return_value=MagicMock())
    await users_repo.delete_user(session, uuid4())
    # The core tables go before the user row itself, so the delete never fails on an
    # FK to users.id without ON DELETE CASCADE: messages, usage, push tokens, chats.
    # The modules' rows went first (account.lifecycle asks each module). The account
    # lock precedes every delete to match memory writers.
    statements = [call.args[0] for call in session.execute.await_args_list]
    assert len(statements) == 5
    assert statements[0].is_select
    assert str(statements[0]).endswith("FOR UPDATE")
    assert all(statement.is_delete for statement in statements[1:])
    session.delete.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_export_structure(_empty_product_events_for_exports):
    from app.modules.account import export as export_service

    session = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    user.email = "e@x"
    user.name = "n"
    user.created_at = datetime(2024, 1, 1)
    user.ai_data_consent_at = datetime(2026, 10, 19, 12, 30)

    chat = MagicMock()
    chat.id = uuid4()
    chat.title = "T"
    chat.model = "free-chat"
    chat.pinned = False
    chat.created_at = datetime(2024, 1, 1)
    chat.updated_at = datetime(2024, 1, 1)

    msg = MagicMock(role="user", content="hi", model=None, created_at=datetime(2024, 1, 1))
    mem = MagicMock(type="fact", text="x", confidence=None, created_at=datetime(2024, 1, 1))

    todo = MagicMock()
    todo.id = uuid4()
    todo.content = "buy milk"
    todo.topic = "General"
    todo.checked = False
    todo.due_at = None
    todo.chat_id = None
    todo.sort_order = 1
    todo.created_at = datetime(2024, 1, 1)
    todo.updated_at = datetime(2024, 1, 1)

    event = MagicMock()
    event.name = "paywall_viewed"
    event.properties = {"source": "settings"}
    event.platform = "ios"
    event.app_version = "1.0.0"
    event.installation_id = "install-1"
    event.client_at = datetime(2024, 1, 2)
    event.recorded_at = datetime(2024, 1, 2)
    _empty_product_events_for_exports.return_value = [event]

    with (
        patch(
            "app.modules.account.export.chat_history.chats_for_export",
            AsyncMock(return_value=[chat]),
        ),
        patch(
            "app.modules.account.export.chat_history.messages_page",
            AsyncMock(return_value=[msg]),
        ),
        patch(
            "app.modules.memory.repository.list_range",
            AsyncMock(return_value=[mem]),
        ),
        patch(
            "app.modules.account.export.todos_service.list_owned_todos",
            AsyncMock(return_value=[todo]),
        ),
        patch(
            "app.modules.account.export.attachments_service.list_for_user",
            AsyncMock(return_value=[]),
        ),
    ):
        data = await _export(session, user)

    assert data["user"]["email"] == "e@x"
    # The consent record is the user's own data, so the export carries it.
    assert data["user"]["ai_data_consent_at"] == "2026-10-19T12:30:00"
    assert len(data["chats"]) == 1
    assert data["chats"][0]["messages"][0]["content"] == "hi"
    assert len(data["memories"]) == 1
    assert data["todos"][0]["content"] == "buy milk"
    assert "project_id" not in data["todos"][0]
    assert "projects" not in data
    # Nothing hit a cap; the notes say how long attachment links work.
    assert data["truncated"] == []
    assert "10 minutes" in data["notes"][0]
    assert "learning_practice_events" not in data
    assert data["attachments"] == []
    assert data["product_events"][0]["name"] == "paywall_viewed"
    assert data["product_events"][0]["properties"] == {"source": "settings"}
    assert data["export_limits"]["max_chats"] == export_service.EXPORT_MAX_CHATS
    assert (
        data["export_limits"]["max_messages_per_chat"]
        == export_service.EXPORT_MAX_MESSAGES_PER_CHAT
    )
    assert data["export_limits"]["max_todos"] == export_service.EXPORT_MAX_TODOS
    assert data["export_limits"]["max_memories"] == export_service.EXPORT_MAX_MEMORIES
    assert "max_projects" not in data["export_limits"]
    assert data["export_limits"]["max_attachments"] == export_service.EXPORT_MAX_ATTACHMENTS


@pytest.mark.asyncio
async def test_build_export_includes_archived_chats():

    session = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    user.email = "e@x"
    user.name = "n"
    user.created_at = datetime(2024, 1, 1)

    archived = MagicMock()
    archived.id = uuid4()
    archived.title = "Old"
    archived.model = "free-chat"
    archived.pinned = False
    archived.created_at = datetime(2024, 1, 1)
    archived.updated_at = datetime(2024, 1, 1)

    list_chats = AsyncMock(return_value=[archived])
    with (
        patch(
            "app.modules.account.export.chat_history.chats_for_export",
            list_chats,
        ),
        patch(
            "app.modules.account.export.chat_history.messages_page",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.repository.list_range",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.todos_service.list_owned_todos",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.attachments_service.list_for_user",
            AsyncMock(return_value=[]),
        ),
    ):
        data = await _export(session, user)

    assert len(data["chats"]) == 1
    assert data["chats"][0]["title"] == "Old"
    # chat.history's export read includes archived chats (test_chat_history.py).
    list_chats.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_export_pages_messages_per_chat():
    from app.modules.account import export as export_service

    session = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    user.email = "e@x"
    user.name = "n"
    user.created_at = datetime(2024, 1, 1)

    chat = MagicMock()
    chat.id = uuid4()
    chat.title = "T"
    chat.model = "free-chat"
    chat.pinned = False
    chat.created_at = datetime(2024, 1, 1)
    chat.updated_at = datetime(2024, 1, 1)

    page_one = [
        MagicMock(role="user", content="one", model=None, created_at=datetime(2024, 1, 1)),
        MagicMock(
            role="assistant", content="two", model="free-chat", created_at=datetime(2024, 1, 2)
        ),
    ]
    page_two = [
        MagicMock(role="user", content="three", model=None, created_at=datetime(2024, 1, 3)),
    ]

    async def list_range(_session, _chat_id, *, offset, limit):
        if offset == 0:
            return page_one
        if offset == len(page_one):
            return page_two
        return []

    with (
        patch.object(export_service, "EXPORT_MESSAGE_PAGE_SIZE", 2),
        patch(
            "app.modules.account.export.chat_history.chats_for_export",
            AsyncMock(return_value=[chat]),
        ),
        patch(
            "app.modules.account.export.chat_history.messages_page",
            AsyncMock(side_effect=list_range),
        ),
        patch(
            "app.modules.memory.repository.list_range",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.todos_service.list_owned_todos",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.attachments_service.list_for_user",
            AsyncMock(return_value=[]),
        ),
    ):
        data = await _export(session, user)

    contents = [message["content"] for message in data["chats"][0]["messages"]]
    assert contents == ["one", "two", "three"]


@pytest.mark.asyncio
async def test_build_export_pages_memories():
    from app.modules.account import export as export_service

    session = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    user.email = "e@x"
    user.name = "n"
    user.created_at = datetime(2024, 1, 1)

    mem_one = MagicMock(type="fact", text="a", confidence=0.9, created_at=datetime(2024, 1, 1))
    mem_two = MagicMock(type="focus", text="b", confidence=0.8, created_at=datetime(2024, 1, 2))
    mem_three = MagicMock(
        type="profile", text="c", confidence=None, created_at=datetime(2024, 1, 3)
    )

    async def list_memories(_session, _user_id, *, offset, limit, include_superseded=False):
        page = [mem_one, mem_two, mem_three]
        return page[offset : offset + limit]

    with (
        patch.object(export_service, "EXPORT_MEMORY_PAGE_SIZE", 2),
        patch(
            "app.modules.account.export.chat_history.chats_for_export",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.repository.list_range",
            AsyncMock(side_effect=list_memories),
        ),
        patch(
            "app.modules.account.export.todos_service.list_owned_todos",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.attachments_service.list_for_user",
            AsyncMock(return_value=[]),
        ),
    ):
        data = await _export(session, user)

    assert [memory["text"] for memory in data["memories"]] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_build_export_caps_memories():
    from app.modules.account import export as export_service

    session = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    user.email = "e@x"
    user.name = "n"
    user.created_at = datetime(2024, 1, 1)

    mems = [
        MagicMock(type="fact", text="a", confidence=None, created_at=datetime(2024, 1, 1)),
        MagicMock(type="focus", text="b", confidence=None, created_at=datetime(2024, 1, 2)),
        MagicMock(type="profile", text="c", confidence=None, created_at=datetime(2024, 1, 3)),
    ]

    async def list_memories(_session, _user_id, *, offset, limit, include_superseded=False):
        return mems[offset : offset + limit]

    with (
        patch.object(export_service, "EXPORT_MEMORY_PAGE_SIZE", 2),
        patch.object(export_service, "EXPORT_MAX_MEMORIES", 2),
        patch(
            "app.modules.account.export.chat_history.chats_for_export",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.repository.list_range",
            AsyncMock(side_effect=list_memories),
        ),
        patch(
            "app.modules.account.export.todos_service.list_owned_todos",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.attachments_service.list_for_user",
            AsyncMock(return_value=[]),
        ),
    ):
        data = await _export(session, user)

    assert [memory["text"] for memory in data["memories"]] == ["a", "b"]
    # The cap cut the list: the file says so, so a reader knows it is not complete.
    assert data["truncated"] == ["memories"]
    assert any("truncated" in note for note in data["notes"])


@pytest.mark.asyncio
async def test_build_export_includes_attachment_with_presigned_url():

    session = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    user.email = "e@x"
    user.name = "n"
    user.created_at = datetime(2024, 1, 1)

    attachment_id = uuid4()
    message_id = uuid4()
    attachment = MagicMock()
    attachment.id = attachment_id
    attachment.message_id = message_id
    attachment.storage_key = f"{user.id}/{attachment_id}"
    attachment.content_type = "image/png"
    attachment.size_bytes = 1234
    attachment.source = "upload"
    attachment.created_at = datetime(2024, 1, 2)

    gateway = MagicMock()
    gateway.presign_download = AsyncMock(return_value="https://r2.example/signed-image")
    settings = Settings(r2_presign_expiry_seconds=600)

    with (
        patch(
            "app.modules.account.export.chat_history.chats_for_export",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.repository.list_range",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.todos_service.list_owned_todos",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.account.export.attachments_service.list_for_user",
            AsyncMock(return_value=[attachment]),
        ),
        patch(
            "app.modules.account.export.get_storage_gateway",
            return_value=gateway,
        ),
    ):
        data = await _export(session, user, settings)

    assert len(data["attachments"]) == 1
    exported = data["attachments"][0]
    assert exported["id"] == str(attachment_id)
    assert exported["message_id"] == str(message_id)
    assert exported["content_type"] == "image/png"
    assert exported["size_bytes"] == 1234
    assert exported["source"] == "upload"
    assert exported["download_url"] == "https://r2.example/signed-image"
    assert exported["download_url_expires_in_seconds"] == 600
    gateway.presign_download.assert_awaited_once_with(attachment.storage_key)
