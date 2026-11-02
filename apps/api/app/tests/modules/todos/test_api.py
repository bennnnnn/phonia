"""To-do traversal regressions using real SQL without external services."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.types import DateTime, TypeDecorator

from app.models.orm import TodoItem
from app.modules.todos import api as todos_router
from app.modules.todos import crud
from app.tests.api_support import api_user, app_with_user


class _UTCDateTime(TypeDecorator):
    # Preserve the production timezone-aware bind type while making SQLite
    # return aware datetimes for traversal assertions. SQLAlchemy may cache a
    # compiled expression after this fixture restores the model column type.
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


@pytest.fixture
def page_sql():
    columns = [c for c in TodoItem.__table__.c if isinstance(c.type, DateTime)]
    original_types = [c.type for c in columns]
    for column in columns:
        column.type = _UTCDateTime()
    engine = create_engine("sqlite://")
    TodoItem.__table__.create(engine)
    try:
        with Session(engine, expire_on_commit=False) as sync_session:
            session = AsyncMock(spec=AsyncSession)
            session.execute.side_effect = sync_session.execute
            session.commit.side_effect = sync_session.commit
            session.rollback.side_effect = sync_session.rollback
            user = SimpleNamespace(
                id=uuid4(),
                timezone="UTC",
                push_notifications_enabled=True,
                push_reminders_enabled=True,
                reminder_lead_minutes=10,
                quiet_hours_enabled=False,
                quiet_hours_start_minute=1320,
                quiet_hours_end_minute=420,
            )
            yield sync_session, session, user
    finally:
        engine.dispose()
        for column, original_type in zip(columns, original_types, strict=True):
            column.type = original_type


def _seed(sync_session, owner, *, count=1001):
    timestamp = datetime(2026, 9, 4, tzinfo=UTC)
    rows = [
        TodoItem(
            id=UUID(f"abcdef00-0000-0000-0000-{index:012x}"),
            user_id=owner,
            content=f"Reminder {index}",
            topic="Reminders",
            sort_order=1,
            checked=False,
            due_at=timestamp,
            created_at=timestamp,
            updated_at=timestamp,
        )
        for index in range(1, count + 1)
    ]
    sync_session.add_all(rows)
    sync_session.commit()
    return rows


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["checked", "sort_order", "topic"])
@pytest.mark.parametrize("direction", ["seen_later", "unseen_earlier"])
async def test_traversal_keeps_all_1001_rows_when_mutable_fields_cross_boundary(
    page_sql, field, direction
):
    sync_session, session, user = page_sql
    rows = _seed(sync_session, user.id)
    if direction == "unseen_earlier" and field == "checked":
        for row in rows:
            row.checked = True
        sync_session.commit()
    first, cursor = await crud.list_todos_page(session, user)
    assert len(first) == 1000
    assert cursor is not None
    moving = rows[0] if direction == "seen_later" else rows[-1]
    later = {"checked": True, "sort_order": 2, "topic": "Z"}
    earlier = {"checked": False, "sort_order": 0, "topic": "A"}
    setattr(moving, field, (later if direction == "seen_later" else earlier)[field])
    sync_session.commit()
    second, cursor = await crud.list_todos_page(session, user, cursor=cursor)
    assert cursor is None
    assert [row.id for row in first + second] == [row.id for row in rows]


@pytest.mark.asyncio
async def test_equal_timestamps_and_foreign_cursor_remain_owner_scoped(page_sql):
    sync_session, session, user = page_sql
    rows = _seed(sync_session, user.id, count=4)
    foreign_id = rows[1].id
    rows[1].user_id = uuid4()
    sync_session.commit()
    first, cursor = await crud.list_todos_page(session, user, limit=2)
    assert [row.id for row in first] == [rows[0].id, rows[2].id]
    assert cursor == rows[2].id
    second, cursor = await crud.list_todos_page(session, user, limit=2, cursor=cursor)
    assert [row.id for row in second] == [rows[3].id]
    assert cursor is None
    foreign_cursor_page, _ = await crud.list_todos_page(session, user, cursor=foreign_id)
    assert [row.id for row in foreign_cursor_page] == [rows[2].id, rows[3].id]


@pytest.mark.asyncio
async def test_deleted_cursor_and_seen_rows_do_not_skip_remaining_rows(page_sql):
    sync_session, session, user = page_sql
    rows = _seed(sync_session, user.id, count=4)
    first, cursor = await crud.list_todos_page(session, user, limit=2)
    sync_session.execute(delete(TodoItem).where(TodoItem.id.in_([row.id for row in first])))
    sync_session.commit()
    second, next_cursor = await crud.list_todos_page(session, user, limit=2, cursor=cursor)
    assert [row.id for row in second] == [rows[2].id, rows[3].id]
    assert next_cursor is None  # An exact final page does not require an extra request.


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["delete", "owner"])
async def test_catchup_reloads_original_ids_and_keeps_empty_page_cursor(page_sql, change):
    sync_session, session, user = page_sql
    rows = _seed(sync_session, user.id, count=3)
    user.push_notifications_enabled = False
    rows[0].recurrence_rule = "daily"
    rows[0].due_at = datetime.now(UTC) - timedelta(days=1)
    page_ids = [row.id for row in rows[:2]]
    sync_session.commit()
    advance = crud.advance_schedules_if_current

    async def change_selected_rows_then_advance(db, advances):
        statement = (
            delete(TodoItem) if change == "delete" else update(TodoItem).values(user_id=uuid4())
        )
        sync_session.execute(
            statement.where(TodoItem.id.in_(page_ids)).execution_options(synchronize_session=False)
        )
        # A mutable sort change must not pull the next row into the reload.
        rows[2].topic = "A"
        sync_session.commit()
        return await advance(db, advances)

    with patch.object(crud, "advance_schedules_if_current", change_selected_rows_then_advance):
        first, cursor = await crud.list_todos_page(session, user, limit=2)
    assert first == []
    assert cursor == page_ids[-1]
    second, next_cursor = await crud.list_todos_page(session, user, limit=2, cursor=cursor)
    assert [row.id for row in second] == [rows[2].id]
    assert next_cursor is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "push_enabled, reminders_enabled",
    [(True, True), (False, True), (True, False)],
)
async def test_page_keeps_existing_delivery_owner_policy(page_sql, push_enabled, reminders_enabled):
    sync_session, session, user = page_sql
    row = _seed(sync_session, user.id, count=1)[0]
    due = datetime.now(UTC) - timedelta(days=2)
    row.due_at = due
    row.recurrence_rule = "daily"
    row.notification_sent_at = None
    user.push_notifications_enabled = push_enabled
    user.push_reminders_enabled = reminders_enabled
    sync_session.commit()
    items, cursor = await crud.list_todos_page(session, user)
    assert cursor is None
    # Reminder pushes deliver (and advance) the occurrence only with both switches on.
    if push_enabled and reminders_enabled:
        assert items[0].due_at == due
        session.commit.assert_not_awaited()
    else:
        assert items[0].due_at > datetime.now(UTC)
        sync_session.refresh(row)
        assert items[0].due_at == row.due_at


@pytest.mark.asyncio
async def test_catchup_page_returns_concurrent_reschedule_without_overwriting_it(page_sql):
    sync_session, session, user = page_sql
    row = _seed(sync_session, user.id, count=1)[0]
    row.due_at = datetime.now(UTC) - timedelta(days=2)
    row.recurrence_rule = "daily"
    user.push_notifications_enabled = False
    sync_session.commit()
    new_due = datetime.now(UTC) + timedelta(days=10)
    advance = crud.advance_schedules_if_current

    async def reschedule_then_advance(db, advances):
        sync_session.execute(
            update(TodoItem)
            .where(TodoItem.id == row.id)
            .values(due_at=new_due)
            .execution_options(synchronize_session=False)
        )
        sync_session.commit()
        return await advance(db, advances)

    with patch.object(crud, "advance_schedules_if_current", reschedule_then_advance):
        items, _ = await crud.list_todos_page(session, user)
    assert items[0].due_at == new_due


@pytest.fixture
async def page_client(page_sql):
    _, session, user = page_sql
    app = FastAPI()
    app.include_router(todos_router.router)
    app.dependency_overrides[todos_router.get_current_user] = lambda: user
    app.dependency_overrides[todos_router.get_db] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_page_route_serializes_cursor(page_sql, page_client):
    sync_session, _, user = page_sql
    rows = _seed(sync_session, user.id, count=3)
    response = await page_client.get("/todos/page", params={"limit": 2})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(row.id) for row in rows[:2]]
    cursor = response.json()["next_cursor"]
    assert cursor == str(rows[1].id)
    response = await page_client.get("/todos/page", params={"limit": 2, "cursor": cursor})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(rows[2].id)]
    assert response.json()["next_cursor"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params", [{"cursor": "invalid"}, {"cursor": ""}, {"limit": 0}, {"limit": 1001}]
)
async def test_page_route_rejects_invalid_cursor_and_unbounded_limits(
    page_sql, page_client, params
):
    response = await page_client.get("/todos/page", params=params)
    assert response.status_code == 422
    page_sql[1].execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_page_has_no_cursor(page_client):
    response = await page_client.get("/todos/page")
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None, "older_completed": False}


@pytest.mark.asyncio
async def test_page_leaves_out_older_completed_rows_and_says_they_exist(page_sql, page_client):
    """NET-16: the list is open rows plus the last days' completed ones."""
    sync_session, _, user = page_sql
    now = datetime.now(UTC)
    open_row, recent, old = _seed(sync_session, user.id, count=3)
    recent.checked = True
    recent.updated_at = now - timedelta(days=2)
    old.checked = True
    old.updated_at = now - timedelta(days=90)
    sync_session.commit()

    response = await page_client.get("/todos/page", params={"completed_days": 30})
    assert response.status_code == 200
    body = response.json()
    assert {item["id"] for item in body["items"]} == {str(open_row.id), str(recent.id)}
    assert body["older_completed"] is True

    everything = (await page_client.get("/todos/page")).json()
    assert len(everything["items"]) == 3
    assert everything["older_completed"] is False


@pytest.mark.asyncio
async def test_page_has_no_older_completed_when_none_exist(page_sql, page_client):
    sync_session, _, user = page_sql
    _seed(sync_session, user.id, count=2)
    body = (await page_client.get("/todos/page", params={"completed_days": 30})).json()
    assert body["older_completed"] is False


@pytest.mark.asyncio
async def test_page_answers_an_unchanged_list_with_304(page_sql, page_client):
    sync_session, _, user = page_sql
    rows = _seed(sync_session, user.id, count=2)
    first = await page_client.get("/todos/page", params={"completed_days": 30})
    etag = first.headers["etag"]
    assert etag.startswith('W/"')

    again = await page_client.get(
        "/todos/page", params={"completed_days": 30}, headers={"If-None-Match": etag}
    )
    assert again.status_code == 304
    assert again.content == b""

    rows[0].content = "Changed"
    sync_session.commit()
    changed = await page_client.get(
        "/todos/page", params={"completed_days": 30}, headers={"If-None-Match": etag}
    )
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag


@pytest.mark.asyncio
async def test_page_carries_each_reminder_instant_and_a_new_etag_when_it_moves(
    page_sql, page_client
):
    """notify_at is what the phone schedules at: the lead time, after quiet hours."""
    sync_session, _, user = page_sql
    dated, undated, done = _seed(sync_session, user.id, count=3)
    dated.due_at = datetime(2026, 9, 4, 23, 30, tzinfo=UTC)
    dated.due_set_at = datetime(2026, 9, 1, tzinfo=UTC)
    undated.due_at = None
    done.checked = True
    sync_session.commit()

    first = await page_client.get("/todos/page")
    notify_at = {item["content"]: item["notify_at"] for item in first.json()["items"]}
    assert notify_at == {
        dated.content: "2026-09-04T23:20:00Z",
        undated.content: None,
        done.content: None,
    }

    # The user turns quiet hours on: the same rows, a new instant, so not a 304.
    user.quiet_hours_enabled = True
    moved = await page_client.get("/todos/page", headers={"If-None-Match": first.headers["etag"]})
    assert moved.status_code == 200
    by_content = {item["content"]: item["notify_at"] for item in moved.json()["items"]}
    assert by_content[dated.content] == "2026-09-05T07:00:00Z"


_DUE_AT = "2026-08-30T18:00:00Z"

# ── todos router ────────────────────────────────────────────────────────────


def test_create_todo():
    from fastapi.testclient import TestClient

    tid = uuid4()
    now = datetime.now(UTC)
    todo_mock = MagicMock()
    todo_mock.id = tid
    todo_mock.content = "Test todo"
    todo_mock.topic = "General"
    todo_mock.checked = False
    todo_mock.due_at = None
    todo_mock.sort_order = None
    todo_mock.chat_id = None
    todo_mock.created_at = now
    todo_mock.updated_at = now

    user = api_user()
    app = app_with_user(user)
    with (
        patch("app.modules.todos.crud.todos_repo.create", AsyncMock(return_value=todo_mock)),
    ):
        client = TestClient(app)
        r = client.post(
            "/todos",
            headers={"Authorization": "Bearer tok"},
            json={"content": "Test todo", "due_at": _DUE_AT},
        )
    assert r.status_code == 201
    assert r.json()["content"] == "Test todo"


def test_create_todo_with_chat_id():
    from fastapi.testclient import TestClient

    tid = uuid4()
    cid = uuid4()
    now = datetime.now(UTC)
    todo_mock = MagicMock()
    todo_mock.id = tid
    todo_mock.content = "From chat"
    todo_mock.topic = "General"
    todo_mock.checked = False
    todo_mock.due_at = None
    todo_mock.sort_order = None
    todo_mock.chat_id = cid
    todo_mock.created_at = now
    todo_mock.updated_at = now

    user = api_user()
    app = app_with_user(user)
    # The router now verifies chat ownership before linking a todo to it
    # (cross-user FK guard). Mock the chat lookup so the owned-chat path
    # reaches todo creation.
    chat_mock = MagicMock()
    chat_mock.id = cid
    chat_mock.user_id = user.id
    with (
        patch("app.modules.todos.crud.todos_repo.create", AsyncMock(return_value=todo_mock)),
        patch("app.modules.todos.crud.chat_history.get_chat", AsyncMock(return_value=chat_mock)),
    ):
        client = TestClient(app)
        r = client.post(
            "/todos",
            headers={"Authorization": "Bearer tok"},
            json={"content": "From chat", "chat_id": str(cid), "due_at": _DUE_AT},
        )
    assert r.status_code == 201


def test_create_todo_empty_content_fails():
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    client = TestClient(app)
    r = client.post(
        "/todos",
        headers={"Authorization": "Bearer tok"},
        json={"content": ""},
    )
    assert r.status_code == 422


def test_create_todo_with_other_users_chat_id_rejected():
    from fastapi.testclient import TestClient

    cid = uuid4()
    user = api_user()
    app = app_with_user(user)
    # chats_repo.get_by_id returns None → the chat doesn't belong to this user
    # (or doesn't exist). The cross-user FK guard must reject with 400 rather
    # than silently linking the todo to a foreign chat.
    with patch("app.modules.todos.crud.chat_history.get_chat", AsyncMock(return_value=None)):
        client = TestClient(app)
        r = client.post(
            "/todos",
            headers={"Authorization": "Bearer tok"},
            json={"content": "x", "chat_id": str(cid), "due_at": _DUE_AT},
        )
    assert r.status_code == 400
    assert "Chat not found" in r.json()["detail"]["message"]


def test_create_todo_with_unowned_chat_id_404s():
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    with patch("app.modules.todos.crud.chat_history.get_chat", AsyncMock(return_value=None)):
        client = TestClient(app)
        r = client.post(
            "/todos",
            headers={"Authorization": "Bearer tok"},
            json={"content": "x", "chat_id": str(uuid4()), "due_at": _DUE_AT},
        )
    assert r.status_code == 400


def test_update_todo():
    from fastapi.testclient import TestClient

    tid = uuid4()
    now = datetime.now(UTC)
    todo_mock = MagicMock()
    todo_mock.id = tid
    todo_mock.content = "Updated"
    todo_mock.topic = "General"
    todo_mock.checked = True
    todo_mock.due_at = None
    todo_mock.chat_id = None
    todo_mock.created_at = now
    todo_mock.updated_at = now

    user = api_user()
    app = app_with_user(user)
    with (
        patch("app.modules.todos.crud.todos_repo.get_by_id", AsyncMock(return_value=todo_mock)),
        patch("app.modules.todos.crud.todos_repo.update", AsyncMock(return_value=todo_mock)),
    ):
        client = TestClient(app)
        r = client.patch(
            f"/todos/{tid}",
            headers={"Authorization": "Bearer tok"},
            json={"checked": True},
        )
    assert r.status_code == 200
    assert r.json()["checked"] is True


def test_update_todo_not_found():
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    with patch("app.modules.todos.crud.todos_repo.get_by_id", AsyncMock(return_value=None)):
        client = TestClient(app)
        r = client.patch(
            f"/todos/{uuid4()}",
            headers={"Authorization": "Bearer tok"},
            json={"checked": True},
        )
    assert r.status_code == 404


def test_delete_todo():
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    with patch("app.modules.todos.crud.todos_repo.delete_by_id", AsyncMock(return_value=True)):
        client = TestClient(app)
        r = client.delete(
            f"/todos/{uuid4()}",
            headers={"Authorization": "Bearer tok"},
        )
    assert r.status_code == 204


def test_delete_todo_not_found():
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    with patch("app.modules.todos.crud.todos_repo.delete_by_id", AsyncMock(return_value=False)):
        client = TestClient(app)
        r = client.delete(
            f"/todos/{uuid4()}",
            headers={"Authorization": "Bearer tok"},
        )
    assert r.status_code == 404


# ── todos router: due_at normalization ─────────────────────────────────────


def test_create_todo_normalizes_naive_due_at_to_user_timezone():
    """A naive due_at from the client must be interpreted in the user's
    timezone, not server time. Without normalization, a naive "9am" is
    stored as 9am UTC and reminders fire at the wrong wall-clock hour for
    any user not on UTC.
    """
    from fastapi.testclient import TestClient

    tid = uuid4()
    now = datetime.now(UTC)
    todo_mock = MagicMock()
    todo_mock.id = tid
    todo_mock.content = "Test"
    todo_mock.topic = "General"
    todo_mock.checked = False
    todo_mock.due_at = None
    todo_mock.sort_order = None
    todo_mock.chat_id = None
    todo_mock.created_at = now
    todo_mock.updated_at = now

    # User in America/New_York (UTC-5 in EST).
    user = api_user(timezone="America/New_York")
    app = app_with_user(user)
    create_mock = AsyncMock(return_value=todo_mock)
    with (
        patch("app.modules.todos.crud.todos_repo.create", create_mock),
    ):
        client = TestClient(app)
        # Naive 9:00 — should be interpreted as 9:00 America/New_York -> 14:00 UTC.
        r = client.post(
            "/todos",
            headers={"Authorization": "Bearer tok"},
            json={"content": "Test", "due_at": "2025-01-15T09:00:00"},
        )
    assert r.status_code == 201
    # The repo must receive a tz-aware UTC datetime.
    due_at = create_mock.await_args.kwargs["due_at"]
    assert due_at is not None
    assert due_at.tzinfo is not None
    # 9:00 EST (UTC-5) = 14:00 UTC.
    assert due_at.hour == 14


def test_create_todo_accepts_plain_undated_item():
    """A plain To-do is valid without a date."""
    from fastapi.testclient import TestClient

    tid = uuid4()
    now = datetime.now(UTC)
    todo_mock = MagicMock()
    todo_mock.id = tid
    todo_mock.content = "Test"
    todo_mock.topic = "General"
    todo_mock.checked = False
    todo_mock.due_at = None
    todo_mock.recurrence_rule = None
    todo_mock.sort_order = None
    todo_mock.chat_id = None
    todo_mock.created_at = now
    todo_mock.updated_at = now
    user = api_user()
    app = app_with_user(user)
    create_mock = AsyncMock(return_value=todo_mock)
    with (
        patch("app.modules.todos.crud.todos_repo.create", create_mock),
    ):
        client = TestClient(app)
        r = client.post(
            "/todos",
            headers={"Authorization": "Bearer tok"},
            json={"content": "Test"},
        )
    assert r.status_code == 201
    assert create_mock.await_args.kwargs["due_at"] is None
    assert create_mock.await_args.kwargs["topic"] == "General"


def test_update_todo_can_clear_due_at_and_repeat():
    from fastapi.testclient import TestClient

    tid = uuid4()
    now = datetime.now(UTC)
    todo_mock = MagicMock()
    todo_mock.id = tid
    todo_mock.content = "Test"
    todo_mock.topic = "General"
    todo_mock.checked = False
    todo_mock.due_at = now
    todo_mock.recurrence_rule = "weekly"
    todo_mock.sort_order = None
    todo_mock.chat_id = None
    todo_mock.created_at = now
    todo_mock.updated_at = now

    user = api_user()
    app = app_with_user(user)
    updated_mock = MagicMock()
    updated_mock.id = tid
    updated_mock.content = "Test"
    updated_mock.topic = "General"
    updated_mock.checked = False
    updated_mock.due_at = None
    updated_mock.recurrence_rule = None
    updated_mock.sort_order = None
    updated_mock.chat_id = None
    updated_mock.created_at = now
    updated_mock.updated_at = now
    update_mock = AsyncMock(return_value=updated_mock)
    with (
        patch("app.modules.todos.crud.todos_repo.get_by_id", AsyncMock(return_value=todo_mock)),
        patch("app.modules.todos.crud.todos_repo.update", update_mock),
    ):
        client = TestClient(app)
        r = client.patch(
            f"/todos/{tid}",
            headers={"Authorization": "Bearer tok"},
            json={"due_at": None},
        )
    assert r.status_code == 200
    assert update_mock.await_args.kwargs["due_at"] is None
    assert update_mock.await_args.kwargs["recurrence_rule"] is None


def test_update_todo_normalizes_naive_due_at():
    """PATCH /todos/{id} must also normalize a naive due_at to the user's timezone."""
    from fastapi.testclient import TestClient

    tid = uuid4()
    now = datetime.now(UTC)
    todo_mock = MagicMock()
    todo_mock.id = tid
    todo_mock.content = "Updated"
    todo_mock.topic = "General"
    todo_mock.checked = False
    todo_mock.due_at = None
    todo_mock.chat_id = None
    todo_mock.created_at = now
    todo_mock.updated_at = now

    user = api_user(timezone="Asia/Tokyo")  # UTC+9
    app = app_with_user(user)
    update_mock = AsyncMock(return_value=todo_mock)
    with (
        patch("app.modules.todos.crud.todos_repo.get_by_id", AsyncMock(return_value=todo_mock)),
        patch("app.modules.todos.crud.todos_repo.update", update_mock),
    ):
        client = TestClient(app)
        # Naive 9:00 — should be interpreted as 9:00 Asia/Tokyo -> 0:00 UTC.
        r = client.patch(
            f"/todos/{tid}",
            headers={"Authorization": "Bearer tok"},
            json={"due_at": "2025-01-15T09:00:00"},
        )
    assert r.status_code == 200
    due_at = update_mock.await_args.kwargs["due_at"]
    assert due_at is not None
    assert due_at.tzinfo is not None
    # 9:00 JST (UTC+9) = 0:00 UTC.
    assert due_at.hour == 0


def test_projects_routes_are_gone():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert client.get("/projects").status_code == 404
    assert client.post("/projects", json={"title": "Spanish"}).status_code == 404
