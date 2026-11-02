"""The reminder pass writes in its caller's transaction and never ends it (audit ARCH-07).

Live talk saves a voice turn's two messages and its reminders in one session. The
to-do writes used to commit that session midway, and a reminder that hit the open
duplicate index rolled the whole turn back: the messages were gone, the refresh after
the final commit raised, and the spoken turn never reached the chat. Now each write
has its own savepoint and the caller commits.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.core.config import Settings
from app.models.orm import Message, TodoItem
from app.modules import todos as todos_service
from app.modules.conversation import chats_repository as chats_repo
from app.modules.speech.live_talk import persist_live_talk_turn
from app.repositories import users as users_repo
from app.tests.fakes import FakeSessionCM, redis_mock


async def _user_with_a_saved_reminder(session, *, due: datetime, errands: int = 500):
    user = await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Voice User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    user.timezone = "UTC"
    # The pass reads 500 open to-dos, ordered by topic: these come first, so the
    # saved "Call mom" is past the snapshot and only the unique index sees it.
    session.add_all(
        TodoItem(user_id=user.id, content=f"Errand {n}", topic="Aaa errands", checked=False)
        for n in range(errands)
    )
    session.add(
        TodoItem(user_id=user.id, content="Call mom", topic="Reminders", checked=False, due_at=due)
    )
    await session.flush()
    return user


def _reminder_reply(due: datetime) -> str:
    return (
        "Sure, I'll remind you.\n\n"
        f'```reminder\n{{"title": "Call mom", "due_at": "{due.isoformat()}"}}\n```'
    )


@pytest.mark.asyncio
async def test_a_voice_reminder_that_hits_a_saved_duplicate_keeps_the_voice_turn(db_session):
    due = (datetime.now(UTC) + timedelta(days=30)).replace(hour=17, minute=0, second=0)
    due = due.replace(microsecond=0)
    user = await _user_with_a_saved_reminder(db_session, due=due)
    chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")

    with (
        patch("app.modules.speech.live_talk.SessionLocal", FakeSessionCM(db_session)),
        patch("app.core.jobs.enqueue", AsyncMock()),
    ):
        user_message, assistant_message = await persist_live_talk_turn(
            user=user,
            chat_id=chat.id,
            user_text="remind me to call mom at 5pm",
            assistant_text=_reminder_reply(due),
            untitled=False,
            settings=Settings(_env_file=None),
            redis=redis_mock(),
            enqueue_jobs=False,
        )

    assert user_message is not None and assistant_message is not None
    roles = (
        await db_session.scalars(
            select(Message.role).where(Message.chat_id == chat.id).order_by(Message.created_at)
        )
    ).all()
    assert sorted(roles) == ["assistant", "user"]
    assert "Call mom" in assistant_message.content
    calls = await db_session.scalar(
        select(func.count())
        .select_from(TodoItem)
        .where(TodoItem.user_id == user.id, TodoItem.content == "Call mom")
    )
    assert calls == 1


async def _call_mom(session, user_id) -> list[TodoItem]:
    return list(
        (
            await session.scalars(
                select(TodoItem).where(TodoItem.user_id == user_id, TodoItem.content == "Call mom")
            )
        ).all()
    )


@pytest.mark.parametrize(
    ("user_text", "reply", "errands"),
    [
        # A new reminder, then the duplicate of the saved one past the snapshot.
        ("remind me to water the plants at 6pm", "new", 500),
        ("remind me to call mom at 5pm", "duplicate", 500),
        # Changes the user says: the action path, and the spoken move.
        ("mark call mom as done", "Done.", 0),
        ("delete the call mom reminder", "Deleted.", 0),
        ("move call mom to 6pm", "Moved.", 0),
    ],
)
@pytest.mark.asyncio
async def test_the_reminder_pass_never_commits_or_rolls_back_its_callers_session(
    db_session, user_text, reply, errands
):
    due = (datetime.now(UTC) + timedelta(days=30)).replace(hour=17, minute=0, second=0)
    due = due.replace(microsecond=0)
    user = await _user_with_a_saved_reminder(db_session, due=due, errands=errands)
    chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
    kind = reply
    if reply == "new":
        reply = _reminder_reply(due + timedelta(hours=1)).replace("Call mom", "Water the plants")
    elif reply == "duplicate":
        reply = _reminder_reply(due)

    commit = AsyncMock(side_effect=AssertionError("the reminder pass committed"))
    rollback = AsyncMock(side_effect=AssertionError("the reminder pass rolled back"))
    with patch.object(db_session, "commit", commit), patch.object(db_session, "rollback", rollback):
        await todos_service.materialize_reminder_fences(
            db_session,
            user_id=user.id,
            chat_id=chat.id,
            assistant_text=reply,
            user_timezone="UTC",
            user_text=user_text,
            prior_assistant="Your reminders: Call mom.",
        )

    commit.assert_not_awaited()
    rollback.assert_not_awaited()
    # The writes happened, in the caller's open transaction.
    saved = await _call_mom(db_session, user.id)
    if kind == "new":
        assert await db_session.scalar(
            select(func.count())
            .select_from(TodoItem)
            .where(TodoItem.user_id == user.id, TodoItem.content == "Water the plants")
        )
    elif kind == "duplicate":
        assert len(saved) == 1
    elif kind == "Done.":
        assert [row.checked for row in saved] == [True]
    elif kind == "Deleted.":
        assert saved == []
    else:
        assert [row.due_at.hour for row in saved if row.due_at] == [18]


@pytest.mark.asyncio
async def test_a_reminder_pass_that_fails_in_the_database_keeps_the_voice_turn(db_session):
    user = await _user_with_a_saved_reminder(db_session, due=datetime.now(UTC), errands=0)
    chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")

    async def broken_pass(session, **_kwargs):
        await session.execute(text("SELECT 1 / 0"))  # aborts the transaction it runs in

    with (
        patch("app.modules.speech.live_talk.SessionLocal", FakeSessionCM(db_session)),
        patch(
            "app.modules.speech.live_talk.todos_service.materialize_reminder_fences", broken_pass
        ),
    ):
        user_message, assistant_message = await persist_live_talk_turn(
            user=user,
            chat_id=chat.id,
            user_text="remind me to call mom at 5pm",
            assistant_text="Sure.",
            untitled=False,
            settings=Settings(_env_file=None),
            redis=redis_mock(),
            enqueue_jobs=False,
        )

    assert user_message is not None and assistant_message is not None
    count = await db_session.scalar(
        select(func.count()).select_from(Message).where(Message.chat_id == chat.id)
    )
    assert count == 2


# The files the reminder pass runs (``materialize_reminder_fences`` and what it calls).
# ``crud`` and the tap's ``proposals.confirm`` own their sessions and stay out.
_PASS_FILES = (
    "reminder_fences.py",
    "reminder_writes.py",
    "actions.py",
    "spoken_apply.py",
    "spoken_add.py",
    "spoken_change.py",
)
_WRITES = frozenset({"create", "update", "delete_by_id"})


def test_no_write_in_the_reminder_pass_ends_the_transaction() -> None:
    root = Path(todos_service.__file__).parent
    found: list[str] = []
    for name in _PASS_FILES:
        for node in ast.walk(ast.parse((root / name).read_text())):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            where = f"{name}:{node.lineno}"
            if node.func.attr in {"commit", "rollback"}:
                found.append(f"{where} {node.func.attr}()")
            elif node.func.attr in _WRITES and ast.unparse(node.func.value) == "todos_repo":
                passed = {k.arg: ast.unparse(k.value) for k in node.keywords}
                if passed.get("commit") != "False":
                    found.append(f"{where} todos_repo.{node.func.attr} without commit=False")
    assert found == []
