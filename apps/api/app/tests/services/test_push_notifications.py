from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.notifications import push as push_service
from app.modules.todos import due_reminders
from app.tests.fakes import make_user
from app.tests.services import push_cycle_support as push_cycle


def test_android_channel_follows_push_type():
    assert push_service.android_channel_id({"type": "todo_reminder"}) == "recall-reminders"
    assert push_service.android_channel_id({"type": "digest"}) == "recall-reminders"


def test_channel_id_stays_off_until_the_install_opts_in():
    legacy = MagicMock(platform="android", android_channels=None)
    assert push_service.channel_id_for_token(legacy, {"type": "todo_reminder"}) is None
    opted_in = MagicMock(platform="android", android_channels="split")
    assert (
        push_service.channel_id_for_token(opted_in, {"type": "todo_reminder"}) == "recall-reminders"
    )
    tone = MagicMock(platform="android", android_channels="tone")
    assert (
        push_service.channel_id_for_token(tone, {"type": "todo_reminder"}) == "recall-reminders-v2"
    )
    ios = MagicMock(platform="ios", android_channels="split")
    assert push_service.channel_id_for_token(ios, {"type": "todo_reminder"}) is None


@pytest.mark.asyncio
async def test_process_todo_reminders_due_soon():
    session = AsyncMock()
    user_id = uuid4()
    now = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)

    todo = MagicMock()
    todo.user_id = user_id
    todo.id = uuid4()
    todo.content = "Call dentist"
    todo.due_at = now + timedelta(minutes=5)
    todo.due_set_at = now - timedelta(hours=1)
    todo.notification_sent_at = None
    todo.checked = False

    user = make_user()
    user.push_notifications_enabled = True
    user.reminder_lead_minutes = 10

    token = MagicMock()
    token.user_id = user_id
    token.expo_push_token = "ExponentPushToken[abc]"
    token.platform = "android"
    token.android_channels = "split"

    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[(todo, user)])))

    with patch.object(
        push_service.push_repo,
        "list_for_users",
        AsyncMock(return_value=[token]),
    ):
        messages = await push_cycle.process_todo_reminders(session, now=now)

    assert len(messages) == 1
    assert messages[0].message["title"] == "Reminder"
    assert messages[0].message["body"] == "Call dentist"
    assert messages[0].message["data"]["todo_id"] == str(todo.id)
    assert messages[0].message["channelId"] == "recall-reminders"
    assert messages[0].message["sound"] == "recall_notify.wav"
    session.commit.assert_not_awaited()
    assert todo.notification_sent_at is None


@pytest.mark.asyncio
async def test_process_todo_reminders_skips_quiet_hours():
    session = AsyncMock()
    user_id = uuid4()
    now = datetime(2026, 6, 28, 23, 0, tzinfo=UTC)

    todo = MagicMock()
    todo.user_id = user_id
    todo.id = uuid4()
    todo.content = "Call dentist"
    todo.due_at = now + timedelta(minutes=5)
    todo.due_set_at = now - timedelta(hours=1)
    todo.notification_sent_at = None
    todo.checked = False

    user = make_user()
    user.push_notifications_enabled = True
    user.reminder_lead_minutes = 10
    user.quiet_hours_enabled = True
    user.quiet_hours_start_minute = 1320
    user.quiet_hours_end_minute = 420
    user.timezone = "UTC"

    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[(todo, user)])))

    with patch.object(
        push_service.push_repo,
        "list_for_users",
        AsyncMock(return_value=[]),
    ):
        messages = await push_cycle.process_todo_reminders(session, now=now)

    assert messages == []
    assert todo.notification_sent_at is None


@pytest.mark.asyncio
async def test_process_todo_reminders_respects_user_lead():
    session = AsyncMock()
    user_id = uuid4()
    now = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)

    todo = MagicMock()
    todo.user_id = user_id
    todo.id = uuid4()
    todo.content = "Stretch"
    todo.due_at = now + timedelta(minutes=20)
    todo.due_set_at = now - timedelta(hours=1)
    todo.notification_sent_at = None
    todo.checked = False

    user = make_user()
    user.push_notifications_enabled = True
    user.reminder_lead_minutes = 5

    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[(todo, user)])))

    with patch.object(
        push_service.push_repo,
        "list_for_users",
        AsyncMock(return_value=[]),
    ):
        messages = await push_cycle.process_todo_reminders(session, now=now)

    assert messages == []
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_log_aged_unsent_reminders_warns_when_count_positive(caplog):
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=4)
    with caplog.at_level("WARNING", logger="app.modules.notifications.push"):
        count = await push_service.log_aged_unsent_reminders(
            session, now=datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
        )
    assert count == 4
    assert "Aged unsent reminders count=4" in caplog.text
    assert "older_than_hours=48" in caplog.text


@pytest.mark.asyncio
async def test_log_aged_unsent_reminders_silent_when_none():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=0)
    count = await push_service.log_aged_unsent_reminders(session)
    assert count == 0


@pytest.mark.asyncio
async def test_process_todo_reminders_logs_when_user_has_no_token(caplog):
    session = AsyncMock()
    user_id = uuid4()
    now = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)

    todo = MagicMock()
    todo.user_id = user_id
    todo.id = uuid4()
    todo.content = "Call dentist"
    todo.due_at = now + timedelta(minutes=5)
    todo.due_set_at = now - timedelta(hours=1)
    todo.notification_sent_at = None
    todo.recurrence_rule = None
    todo.checked = False

    user = make_user()
    user.push_notifications_enabled = True
    user.reminder_lead_minutes = 10
    user.timezone = "UTC"

    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[(todo, user)])))

    with (
        patch.object(
            push_service.push_repo,
            "list_for_users",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            due_reminders,
            "advance_past_recurring",
            AsyncMock(return_value=False),
        ) as advance,
        caplog.at_level("DEBUG", logger="app.modules.notifications.push"),
    ):
        messages = await push_cycle.process_todo_reminders(session, now=now)

    assert messages == []
    advance.assert_not_awaited()
    # Not a WARNING per to-do every minute for 48h (the scan leaves such users out).
    assert not [r for r in caplog.records if r.levelname == "WARNING"]
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_todo_reminders_advances_tokenless_overdue_recurring():
    session = AsyncMock()
    user_id = uuid4()
    now = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)

    todo = MagicMock()
    todo.user_id = user_id
    todo.id = uuid4()
    todo.content = "Standup"
    todo.due_at = now - timedelta(minutes=5)
    todo.due_set_at = now - timedelta(hours=1)
    todo.notification_sent_at = None
    todo.recurrence_rule = "daily"
    todo.checked = False

    user = make_user()
    user.push_notifications_enabled = True
    user.reminder_lead_minutes = 10
    user.timezone = "UTC"

    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[(todo, user)])))

    with (
        patch.object(
            push_service.push_repo,
            "list_for_users",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            due_reminders,
            "advance_past_recurring",
            AsyncMock(return_value=True),
        ) as advance,
    ):
        messages = await push_cycle.process_todo_reminders(session, now=now)

    assert messages == []
    advance.assert_awaited_once()
    assert advance.await_args.args[1] == [todo]
    assert advance.await_args.kwargs["timezone"] == "UTC"
    assert advance.await_args.kwargs["now"] == now


@pytest.mark.asyncio
async def test_process_todo_reminders_skips_when_push_disabled():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    messages = await push_cycle.process_todo_reminders(session)
    assert messages == []
