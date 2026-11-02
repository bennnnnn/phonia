from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.notifications import reminder_email as reminder_emails
from app.modules.todos.occurrences import TodoEmailSnapshot
from app.tests.fakes import make_user


@pytest.fixture
def email_write():
    with patch.object(
        reminder_emails, "mark_reminder_emailed", AsyncMock(return_value=True)
    ) as write:
        yield write


def _settings(**kwargs: object) -> Settings:
    s = Settings()
    for key, value in kwargs.items():
        setattr(s, key, value)
    return s


def _user(*, email_reminders: bool = True, email: str = "u@test.local") -> MagicMock:
    return make_user(
        email=email,
        name="Ada",
        email_reminders_enabled=email_reminders,
        reminder_lead_minutes=10,
    )


def _todo(*, due_at: datetime, user_id=None) -> MagicMock:
    todo = MagicMock()
    todo.id = uuid4()
    todo.user_id = user_id or uuid4()
    todo.content = "Call mom"
    todo.due_at = due_at
    # Set well before its lead window, so the lead time applies.
    todo.due_set_at = due_at - timedelta(hours=2)
    todo.checked = False
    todo.email_sent_at = None
    todo.recurrence_rule = None
    return todo


@pytest.mark.asyncio
async def test_process_todo_reminder_emails_sends_and_marks(email_write):
    now = datetime.now(UTC)
    user = _user()
    todo = _todo(due_at=now + timedelta(minutes=5), user_id=user.id)
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(todo, user)]
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    with patch(
        "app.modules.notifications.reminder_email.tx_email.send_todo_reminder",
        AsyncMock(return_value=True),
    ) as send:
        count = await reminder_emails.process_todo_reminder_emails(session, _settings(), now=now)

    assert count == 1
    email_write.assert_awaited_once_with(session, TodoEmailSnapshot.from_todo(todo), sent_at=now)
    send.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_todo_reminder_emails_isolates_one_todo_failure(email_write):
    """BUG FIX (was cycle-fatal): one bad row must not prevent other users'
    todo reminder emails from being sent in the same cycle."""
    now = datetime.now(UTC)
    good_user_1 = _user()
    bad_user = _user()
    good_user_2 = _user()
    good_todo_1 = _todo(due_at=now + timedelta(minutes=5), user_id=good_user_1.id)
    bad_todo = _todo(due_at=now + timedelta(minutes=5), user_id=bad_user.id)
    good_todo_2 = _todo(due_at=now + timedelta(minutes=5), user_id=good_user_2.id)

    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [
        (good_todo_1, good_user_1),
        (bad_todo, bad_user),
        (good_todo_2, good_user_2),
    ]
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    async def fake_send(settings, user, *, title, content):
        if user.id == bad_user.id:
            raise RuntimeError("boom: send failed")
        return True

    with patch(
        "app.modules.notifications.reminder_email.tx_email.send_todo_reminder",
        AsyncMock(side_effect=fake_send),
    ):
        count = await reminder_emails.process_todo_reminder_emails(session, _settings(), now=now)

    assert count == 2
    assert [call.args[1].id for call in email_write.await_args_list] == [
        good_todo_1.id,
        good_todo_2.id,
    ]
    assert session.rollback.await_count == 2


@pytest.mark.asyncio
async def test_process_todo_reminder_emails_localizes_title(email_write):
    now = datetime.now(UTC)
    user = _user()
    user.locale = "es"
    todo = _todo(due_at=now + timedelta(minutes=5), user_id=user.id)
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(todo, user)]
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    with patch(
        "app.modules.notifications.reminder_email.tx_email.send_todo_reminder",
        AsyncMock(return_value=True),
    ) as send:
        await reminder_emails.process_todo_reminder_emails(session, _settings(), now=now)

    send.assert_awaited_once()
    assert send.await_args.kwargs["title"] == "Recordatorio"


@pytest.mark.asyncio
async def test_process_todo_reminder_emails_skips_when_opted_out():
    now = datetime.now(UTC)
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    count = await reminder_emails.process_todo_reminder_emails(session, _settings(), now=now)
    assert count == 0
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_process_todo_reminder_emails_skips_quiet_hours():
    now = datetime(2026, 6, 28, 23, 0, tzinfo=UTC)
    user = _user()
    user.quiet_hours_enabled = True
    user.quiet_hours_start_minute = 1320
    user.quiet_hours_end_minute = 420
    user.timezone = "UTC"
    todo = _todo(due_at=now + timedelta(minutes=5), user_id=user.id)
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(todo, user)]
    session.execute = AsyncMock(return_value=result)

    with patch(
        "app.modules.notifications.reminder_email.tx_email.send_todo_reminder",
        AsyncMock(return_value=True),
    ) as send:
        count = await reminder_emails.process_todo_reminder_emails(session, _settings(), now=now)

    assert count == 0
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_email_reminder_cycle_respects_kill_switch():
    session = AsyncMock()
    count = await reminder_emails.run_email_reminder_cycle(
        session, _settings(email_reminders_scheduler_enabled=False)
    )
    assert count == 0


@pytest.mark.asyncio
async def test_a_cycle_that_lost_its_lock_stops_sending(email_write):
    """The fixed 600 s hold, never refreshed, let a peer take the lock and send again."""
    now = datetime.now(UTC)
    rows = []
    for _ in range(3):
        user = _user()
        rows.append((_todo(due_at=now + timedelta(minutes=5), user_id=user.id), user))
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    keep_lock = AsyncMock(side_effect=[True, False, True])

    with patch(
        "app.modules.notifications.reminder_email.tx_email.send_todo_reminder",
        AsyncMock(return_value=True),
    ) as send:
        count = await reminder_emails.process_todo_reminder_emails(
            session, _settings(), now=now, keep_lock=keep_lock
        )

    assert count == 1
    send.assert_awaited_once()
