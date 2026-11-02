"""A duplicate is a 409, not a 500; ticking a repeating to-do finishes only this occurrence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.todos import crud as todos_crud
from app.modules.todos import repository as todos_repo
from app.modules.todos.recurrence import completed_fields
from app.tests.fakes import fake_session

_CONFLICT = IntegrityError("update", {}, Exception("uq_todo_open_content_due"))
_MONDAY = datetime(2026, 10, 19, 18, 0, tzinfo=UTC)


class _ExpiringUser:
    """A user the session expires on rollback, as SQLAlchemy does: reading it then fails."""

    def __init__(self) -> None:
        self._id = uuid4()
        self.timezone = "UTC"
        self.expired = False

    @property
    def id(self) -> Any:
        if self.expired:
            raise RuntimeError("read an expired user after rollback")
        return self._id


@pytest.mark.asyncio
async def test_a_duplicate_create_returns_the_open_one_without_reading_the_expired_user() -> None:
    session = fake_session()
    user: Any = _ExpiringUser()
    session.rollback = AsyncMock(side_effect=lambda: setattr(user, "expired", True))
    existing = SimpleNamespace(id=uuid4())
    with (
        patch.object(todos_repo, "create", AsyncMock(side_effect=_CONFLICT)),
        patch.object(
            todos_repo, "get_open_dated_duplicate", AsyncMock(return_value=existing)
        ) as lookup,
    ):
        item = await todos_crud.create_todo(
            session, user, content="Call mom", topic=None, chat_id=None, due_at=_MONDAY
        )
    assert item is existing
    assert lookup.await_args is not None and lookup.await_args.args[1] == user._id


@pytest.mark.asyncio
async def test_an_edit_into_a_duplicate_is_a_409_not_a_500() -> None:
    session = fake_session()
    user: Any = SimpleNamespace(id=uuid4(), timezone="UTC")
    item = SimpleNamespace(due_at=_MONDAY, recurrence_rule=None, checked=False)
    with (
        patch.object(todos_repo, "get_by_id", AsyncMock(return_value=item)),
        patch.object(todos_repo, "update", AsyncMock(side_effect=_CONFLICT)),
        pytest.raises(todos_crud.TodosError) as refused,
    ):
        await todos_crud.update_todo(session, user, uuid4(), {"content": "Call mom"})
    assert refused.value.status_code == 409 and refused.value.code == "todo_duplicate"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rule", "written"),
    [
        # A repeating to-do stays open, due a week later: the series goes on.
        ("weekly", {"due_at": _MONDAY + timedelta(days=7)}),
        # A one-off to-do is checked.
        (None, {"checked": True}),
    ],
)
async def test_ticking_a_to_do(rule: str | None, written: dict[str, Any]) -> None:
    session = fake_session()
    user: Any = SimpleNamespace(id=uuid4(), timezone="UTC")
    item = SimpleNamespace(due_at=_MONDAY, recurrence_rule=rule, checked=False)
    update = AsyncMock(return_value=MagicMock())
    with (
        patch.object(todos_repo, "get_by_id", AsyncMock(return_value=item)),
        patch.object(todos_repo, "update", update),
        patch.object(todos_crud, "datetime", MagicMock(now=lambda tz: _MONDAY - timedelta(days=1))),
    ):
        await todos_crud.update_todo(session, user, uuid4(), {"checked": True})
    assert update.await_args is not None and update.await_args.kwargs == written


@pytest.mark.parametrize(
    ("now", "due"),
    [
        # Ticked early: the next occurrence after this one, not this one again.
        (_MONDAY - timedelta(days=2), _MONDAY + timedelta(days=7)),
        # Several missed: the next one after now.
        (_MONDAY + timedelta(days=15), _MONDAY + timedelta(days=21)),
    ],
)
def test_completed_fields_moves_a_repeat_to_its_next_occurrence(
    now: datetime, due: datetime
) -> None:
    fields = completed_fields(
        {"checked": True}, due_at=_MONDAY, rule="weekly", timezone="UTC", now=now
    )
    assert fields == {"due_at": due}


def test_completed_fields_leaves_other_changes_alone() -> None:
    assert completed_fields(
        {"checked": False}, due_at=_MONDAY, rule="weekly", timezone="UTC", now=_MONDAY
    ) == {"checked": False}
    assert completed_fields(
        {"checked": True}, due_at=None, rule=None, timezone="UTC", now=_MONDAY
    ) == {"checked": True}
