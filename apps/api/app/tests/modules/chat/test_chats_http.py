"""/chats over HTTP: list, rename, archive, delete, messages."""

# ── chats ──────────────────────────────────────────────────────────────────────
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import messages_repository as messages_repo
from app.tests.api_support import api_user, app_with_user


def test_create_chat():
    from app.models.orm import Chat

    user = api_user()
    chat = MagicMock(spec=Chat)
    chat.id = uuid4()
    chat.title = None
    chat.model = "free-chat"
    chat.pinned = False
    chat.archived = False
    chat.created_at = datetime(2024, 1, 1)
    chat.updated_at = datetime(2024, 1, 1)

    app = app_with_user(user)
    with patch("app.modules.conversation.chats_repository.create", AsyncMock(return_value=chat)):
        client = TestClient(app)
        r = client.post(
            "/chats", headers={"Authorization": "Bearer tok"}, json={"model": "free-chat"}
        )
    assert r.status_code == 201
    assert r.json()["model"] == "free-chat"
    assert "project_id" not in r.json()
    assert "quiz_mode" not in r.json()


def test_create_chat_ignores_retired_project_id():
    from app.models.orm import Chat

    user = api_user()
    app = app_with_user(user)
    chat = MagicMock(spec=Chat)
    chat.id = uuid4()
    chat.title = None
    chat.model = "free-chat"
    chat.pinned = False
    chat.archived = False
    chat.created_at = datetime(2024, 1, 1)
    chat.updated_at = datetime(2024, 1, 1)

    with patch(
        "app.modules.conversation.chats_repository.create", AsyncMock(return_value=chat)
    ) as create:
        client = TestClient(app)
        response = client.post(
            "/chats",
            headers={"Authorization": "Bearer tok"},
            json={"model": "free-chat", "project_id": str(uuid4())},
        )
    assert response.status_code == 201
    assert "project_id" not in response.json()
    assert "project_id" not in create.await_args.kwargs


def test_list_chats():
    user = api_user()
    app = app_with_user(user)
    empty_list: list = []

    with (
        patch(
            "app.modules.conversation.chats_repository.list_recent_page",
            AsyncMock(return_value=(empty_list, None)),
        ),
        patch("app.modules.conversation.chats_repository.list_pinned", AsyncMock(return_value=[])),
        patch(
            "app.modules.conversation.chats_repository.list_archived_page",
            AsyncMock(return_value=(empty_list, None)),
        ),
    ):
        client = TestClient(app)
        r = client.get("/chats", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    assert r.json() == {
        "pinned": [],
        "today": [],
        "yesterday": [],
        "last_7_days": [],
        "this_month": [],
        "older": [],
        "archived": [],
        "next_cursor": None,
        "archived_next_cursor": None,
    }


def test_list_chats_answers_an_unchanged_list_with_304():
    """NET-16: the phone sends back the list's ETag and gets no body when nothing changed."""
    user = api_user()
    app = app_with_user(user)
    with (
        patch(
            "app.modules.conversation.chats_repository.list_recent_page",
            AsyncMock(return_value=([], None)),
        ),
        patch("app.modules.conversation.chats_repository.list_pinned", AsyncMock(return_value=[])),
        patch(
            "app.modules.conversation.chats_repository.list_archived_page",
            AsyncMock(return_value=([], None)),
        ),
    ):
        client = TestClient(app)
        first = client.get("/chats", headers={"Authorization": "Bearer tok"})
        again = client.get(
            "/chats",
            headers={"Authorization": "Bearer tok", "If-None-Match": first.headers["etag"]},
        )
    assert first.status_code == 200
    assert again.status_code == 304
    assert again.content == b""


def test_list_chats_never_overlaps_ops_on_one_session():
    """The dated page and the pinned + archived queries run concurrently, and an AsyncSession can
    only run one operation at a time (asyncpg raises InterfaceError on
    overlap) — so each concurrent query must get its own session. Simulate
    asyncpg's guard: mark a session busy across a yield point and record a
    violation if a second operation lands on it while busy."""
    import asyncio

    user = api_user()
    app = app_with_user(user)
    busy: set[int] = set()
    violations: list[str] = []

    def tracked(name: str, result: object):
        async def impl(s, *args, **kwargs):
            sid = id(s)
            if sid in busy:
                violations.append(name)
            busy.add(sid)
            await asyncio.sleep(0)  # yield so gathered queries interleave
            busy.discard(sid)
            return result

        return impl

    with (
        patch(
            "app.modules.conversation.chats_repository.list_recent_page",
            AsyncMock(side_effect=tracked("dated", ([], None))),
        ),
        patch(
            "app.modules.conversation.chats_repository.list_pinned",
            AsyncMock(side_effect=tracked("pinned", [])),
        ),
        patch(
            "app.modules.conversation.chats_repository.list_archived_page",
            AsyncMock(side_effect=tracked("archived", ([], None))),
        ),
    ):
        client = TestClient(app)
        r = client.get("/chats", headers={"Authorization": "Bearer tok"})

    assert r.status_code == 200
    assert violations == []


def test_get_chat_not_found():
    user = api_user()
    app = app_with_user(user)
    with patch("app.modules.conversation.chats_repository.get_by_id", AsyncMock(return_value=None)):
        client = TestClient(app)
        r = client.get(f"/chats/{uuid4()}", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 404


def test_list_messages_enqueues_topic_backfill():
    import fakeredis.aioredis

    from app.core.deps import get_redis
    from app.models.orm import Chat, Message

    user = api_user()
    app = app_with_user(user)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    chat_id = uuid4()
    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    chat.title = None

    user_msg = MagicMock(spec=Message)
    user_msg.role = "user"
    user_msg.content = "Explain Rust ownership"
    user_msg.id = uuid4()
    user_msg.model = "free-chat"
    user_msg.feedback = None
    user_msg.completion = None
    user_msg.recalled = False
    user_msg.memory_hints = None
    user_msg.context_summarized = None
    user_msg.search_sources = None
    user_msg.created_at = datetime(2024, 1, 1)

    asst_msg = MagicMock(spec=Message)
    asst_msg.role = "assistant"
    asst_msg.content = "Rust ownership prevents data races."
    asst_msg.id = uuid4()
    asst_msg.model = "free-chat"
    asst_msg.feedback = None
    asst_msg.completion = None
    asst_msg.recalled = False
    asst_msg.memory_hints = None
    asst_msg.context_summarized = None
    asst_msg.search_sources = None
    asst_msg.created_at = datetime(2024, 1, 1)

    with (
        patch("app.modules.conversation.chats_repository.get_by_id", AsyncMock(return_value=chat)),
        patch(
            "app.modules.conversation.messages_repository.list_page",
            AsyncMock(return_value=([user_msg, asst_msg], False)),
        ),
        patch("app.modules.chat.service.jobs.enqueue", AsyncMock()) as enqueue_job,
    ):
        client = TestClient(app)
        r = client.get(f"/chats/{chat_id}/messages", headers={"Authorization": "Bearer tok"})
        r2 = client.get(
            f"/chats/{chat_id}/messages",
            headers={"Authorization": "Bearer tok", "If-None-Match": r.headers["etag"]},
        )

    assert r.status_code == 200
    # The same page again: no body (NET-16).
    assert r2.status_code == 304
    enqueue_job.assert_awaited_once()
    assert enqueue_job.call_args.args[1] == "topic"
    # The first reply's title job's key: one title call however many pages are read.
    assert enqueue_job.call_args.kwargs["dedupe_key"] == f"topic:{chat_id}"
    payload = enqueue_job.call_args.args[2]
    assert payload["user_id"] == str(user.id)
    assert payload["user_message"] == user_msg.content
    assert payload["assistant_message"] == asst_msg.content


def test_patch_message_email_rewrites_via_service():
    from app.models.orm import Message

    user = api_user()
    app = app_with_user(user)
    chat_id = uuid4()
    message_id = uuid4()
    asst_msg = MagicMock(spec=Message)
    asst_msg.id = message_id
    asst_msg.role = "assistant"
    asst_msg.content = "```email\nTo: a@b.com\nSubject: Hi\n\nShorter\n```"
    asst_msg.model = "free-chat"
    asst_msg.feedback = None
    asst_msg.completion = None
    asst_msg.created_at = datetime(2024, 1, 1)

    with patch(
        "app.modules.chat.service.update_message_email",
        AsyncMock(return_value=asst_msg),
    ) as update:
        client = TestClient(app)
        r = client.patch(
            f"/chats/{chat_id}/messages/{message_id}/email",
            headers={"Authorization": "Bearer tok"},
            json={"to": "a@b.com", "subject": "Hi", "body": "Shorter"},
        )

    assert r.status_code == 200
    assert r.json()["content"].startswith("```email")
    update.assert_awaited_once()


def test_rename_chat_rejects_blank_title():
    user = api_user()
    app = app_with_user(user)
    chat_id = uuid4()
    chat = MagicMock()
    chat.id = chat_id

    with patch("app.modules.conversation.chats_repository.get_by_id", AsyncMock(return_value=chat)):
        client = TestClient(app)
        r = client.patch(
            f"/chats/{chat_id}",
            headers={"Authorization": "Bearer tok"},
            json={"title": '   "'},
        )
    assert r.status_code == 400


def test_today_usage():
    import fakeredis.aioredis

    from app.core.deps import get_redis

    user = api_user()
    app = app_with_user(user)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    with patch("app.modules.chat.service.usage_repo.get_for_date", AsyncMock(return_value=None)):
        client = TestClient(app)
        r = client.get("/chats/usage/today", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    data = r.json()
    assert "remaining" in data
    assert "used_tokens" in data
    assert data["remaining"] == data["daily_limit"] - data["used_tokens"]
    assert data["context_token_budget"] == 16_000
    assert data["recent_message_window"] == 20


def test_today_usage_falls_back_to_db_total_when_redis_flushed():
    """After a Redis flush, the usage display must not reset to zero — it
    reconciles against the DB-recorded total so users see real consumption."""
    import fakeredis.aioredis

    from app.core.deps import get_redis

    user = api_user()
    app = app_with_user(user)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    db_usage = MagicMock()
    db_usage.input_tokens = 8_000
    db_usage.output_tokens = 4_000

    with patch(
        "app.modules.chat.service.usage_repo.get_for_date", AsyncMock(return_value=db_usage)
    ):
        client = TestClient(app)
        r = client.get("/chats/usage/today", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    data = r.json()
    # Redis is empty (0); DB total (12_000) wins via the max() reconciliation.
    assert data["used_tokens"] == 12_000
    assert data["input_tokens"] == 8_000
    assert data["output_tokens"] == 4_000
    assert data["remaining"] == data["daily_limit"] - 12_000


# ── delete_chat router ────────────────────────────────────────────────────────


def _app_with_user(user):
    from app.core.deps import get_current_user, get_settings_dep
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    return app


def test_router_delete_chat_204():
    from fastapi.testclient import TestClient

    user = MagicMock()
    user.id = uuid4()
    app = _app_with_user(user)

    with patch("app.modules.chat.service.delete_chat", AsyncMock(return_value=None)):
        client = TestClient(app)
        r = client.delete(f"/chats/{uuid4()}", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 204


def test_router_delete_chat_404():
    from fastapi.testclient import TestClient

    user = MagicMock()
    user.id = uuid4()
    app = _app_with_user(user)

    with patch("app.modules.conversation.chats_repository.get_by_id", AsyncMock(return_value=None)):
        client = TestClient(app)
        r = client.delete(f"/chats/{uuid4()}", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("messages", "deleted"), [(0, True), (1, False)])
async def test_delete_if_empty_keeps_a_chat_with_messages(messages: int, deleted: bool):
    """The phone drops an unused draft in one request (code-health audit NET-13)."""
    from app.modules.chat import service as chats_service

    chat = MagicMock()
    session = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    with (
        patch.object(chats_repo, "get_by_id", AsyncMock(return_value=chat)),
        patch.object(chats_repo, "forget_chat"),
        patch.object(messages_repo, "count_for_chat", AsyncMock(return_value=messages)),
    ):
        await chats_service.delete_chat(session, user, uuid4(), settings=Settings(), if_empty=True)
    assert session.delete.await_count == (1 if deleted else 0)


def test_router_passes_if_empty():
    from fastapi.testclient import TestClient

    user = MagicMock()
    user.id = uuid4()
    app = _app_with_user(user)

    with patch("app.modules.chat.service.delete_chat", AsyncMock(return_value=None)) as delete:
        client = TestClient(app)
        r = client.delete(
            f"/chats/{uuid4()}?if_empty=true", headers={"Authorization": "Bearer tok"}
        )
    assert r.status_code == 204
    assert delete.await_args.kwargs["if_empty"] is True


@pytest.mark.asyncio
async def test_delete_chat_keeps_library_attachments():
    """Chat delete must not purge Library files — only the conversation."""
    from app.models.orm import User
    from app.modules.chat import service as chats_service

    user = MagicMock(spec=User)
    user.id = uuid4()
    chat = MagicMock()
    chat.id = uuid4()
    session = AsyncMock()
    settings = Settings()

    with (
        patch.object(chats_repo, "get_by_id", AsyncMock(return_value=chat)),
        patch(
            "app.modules.attachments.lifecycle.detach_attachments_for_messages",
            AsyncMock(return_value=["user/file"]),
        ) as detach_mock,
        patch(
            "app.modules.attachments.lifecycle.delete_storage_keys",
            AsyncMock(return_value=[]),
        ) as delete_keys,
        patch(
            "app.modules.attachments.lifecycle.enqueue_failed_storage_deletes",
            AsyncMock(),
        ) as enqueue,
    ):
        await chats_service.delete_chat(session, user, chat.id, settings=settings)

    detach_mock.assert_not_awaited()
    session.delete.assert_called_once_with(chat)
    session.commit.assert_awaited_once()
    delete_keys.assert_not_awaited()
    enqueue.assert_not_awaited()


def test_archived_chats_page_by_cursor_past_the_drawer():
    """GET /chats/archived reads on from the drawer's ``archived_next_cursor``."""
    user = api_user()
    app = app_with_user(user)
    page = AsyncMock(return_value=([], "next-page"))
    with patch.object(chats_repo, "list_archived_page", page):
        client = TestClient(app)
        r = client.get(
            "/chats/archived?cursor=abc&limit=20", headers={"Authorization": "Bearer tok"}
        )
    assert r.status_code == 200
    assert r.json() == {"items": [], "next_cursor": "next-page"}
    assert page.await_args.kwargs == {"limit": 20, "cursor": "abc"}


def test_bulk_chats_runs_one_request_and_caps_the_selection():
    """One request for the whole selection (it was one per chat, past the rate limit)."""
    from app.modules.chat import service as chats_service

    user = api_user()
    app = app_with_user(user)
    ids = [str(uuid4()) for _ in range(3)]
    bulk = AsyncMock(return_value=[ids[0], ids[1]])
    with patch.object(chats_service, "bulk_chats", bulk):
        client = TestClient(app)
        ok = client.post(
            "/chats/bulk",
            json={"action": "archive", "chat_ids": ids},
            headers={"Authorization": "Bearer tok"},
        )
        too_many = client.post(
            "/chats/bulk",
            json={"action": "delete", "chat_ids": [str(uuid4()) for _ in range(201)]},
            headers={"Authorization": "Bearer tok"},
        )
        wrong = client.post(
            "/chats/bulk",
            json={"action": "pin", "chat_ids": ids},
            headers={"Authorization": "Bearer tok"},
        )
    assert ok.status_code == 200
    assert ok.json() == {"changed": ids[:2]}
    assert bulk.await_args.kwargs["action"] == "archive"
    assert [str(i) for i in bulk.await_args.kwargs["chat_ids"]] == ids
    assert (too_many.status_code, wrong.status_code) == (422, 422)
