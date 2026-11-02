"""Tests for chat's chats repository with mocked AsyncSession."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.conversation.chats_repository import RECENCY_BUCKETS, group_by_recency


@pytest.mark.asyncio
async def test_create_chat(fake_session):
    """create should add, commit, refresh, and return the chat."""
    from app.modules.conversation.chats_repository import create

    await create(fake_session, user_id=uuid4(), model="free-chat")

    fake_session.add.assert_called_once()
    fake_session.commit.assert_awaited_once()
    fake_session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_id_returns_chat(fake_session):
    """get_by_id should return a chat via scalar_one_or_none."""
    from app.modules.conversation.chats_repository import get_by_id

    mock_chat = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_chat
    fake_session.execute.return_value = mock_result

    result = await get_by_id(fake_session, uuid4(), uuid4())

    assert result is mock_chat


@pytest.mark.asyncio
async def test_list_for_user_returns_chats(fake_session):
    """list_for_user should return a list of chats with messages."""
    from app.modules.conversation.chats_repository import list_for_user

    mock_chat = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_chat]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    fake_session.execute.return_value = mock_result

    result = await list_for_user(fake_session, uuid4())

    assert result == [mock_chat]


@pytest.mark.asyncio
async def test_set_title(fake_session):
    """set_title should update title, commit, and refresh."""
    from app.modules.conversation.chats_repository import set_title

    mock_chat = MagicMock()

    _ = await set_title(fake_session, mock_chat, "New Title")

    assert mock_chat.title == "New Title"
    fake_session.commit.assert_awaited_once()
    fake_session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_pinned(fake_session):
    """set_pinned commits and refreshes the returned database state."""
    from app.modules.conversation.chats_repository import set_pinned

    mock_chat = MagicMock()

    _ = await set_pinned(fake_session, mock_chat, True)

    fake_session.execute.assert_awaited_once()
    fake_session.commit.assert_awaited_once()
    fake_session.refresh.assert_awaited_once()


def test_group_by_recency_last_7_days():
    """Chats from 2-7 days ago land in last_7_days."""
    from datetime import timedelta

    from app.modules.conversation.chats_repository import group_by_recency

    now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)
    chat = MagicMock()
    chat.updated_at = now - timedelta(days=4)

    result = group_by_recency([chat], now=now)

    assert result["today"] == []
    assert result["yesterday"] == []
    assert len(result["last_7_days"]) == 1


def test_group_by_recency_this_month():
    """Chats from earlier this month (but not last 7 days) land in this_month."""
    from datetime import timedelta

    from app.modules.conversation.chats_repository import group_by_recency

    now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)
    chat = MagicMock()
    chat.updated_at = now - timedelta(days=10)

    result = group_by_recency([chat], now=now)

    assert len(result["this_month"]) == 1


def test_group_by_recency_mixed():
    """Chats from different time periods should be split correctly."""
    from app.modules.conversation.chats_repository import group_by_recency

    now = datetime(2026, 6, 28, 15, 0, 0, tzinfo=UTC)
    today_chat = MagicMock()
    today_chat.updated_at = now
    yesterday_chat = MagicMock()
    yesterday_chat.updated_at = now - timedelta(hours=20)
    old_chat = MagicMock()
    old_chat.updated_at = now - timedelta(days=7)

    result = group_by_recency([today_chat, yesterday_chat, old_chat], now=now)

    assert len(result["today"]) == 1
    assert len(result["yesterday"]) == 1
    assert len(result["last_7_days"]) == 1


def test_group_by_recency_uses_user_timezone():
    """Local yesterday must not appear under Today when UTC date already rolled forward."""
    from app.modules.conversation.chats_repository import group_by_recency

    # Sunday 2pm in Los Angeles
    now = datetime(2026, 6, 28, 21, 0, 0, tzinfo=UTC)
    # Saturday 11pm in Los Angeles (Sunday 06:00 UTC — UTC would call this "today")
    chat = MagicMock()
    chat.updated_at = datetime(2026, 6, 28, 6, 0, 0, tzinfo=UTC)

    utc_groups = group_by_recency([chat], now=now)
    la_groups = group_by_recency([chat], user_timezone="America/Los_Angeles", now=now)

    assert len(utc_groups["today"]) == 1
    assert utc_groups["yesterday"] == []
    assert len(la_groups["yesterday"]) == 1
    assert la_groups["today"] == []


def test_recent_chat_cache_forgets_chats_nobody_reads_again(monkeypatch):
    """A created chat used to stay in the process for good: its entry left only
    when that same chat was read again after the TTL, so the cache grew by one
    chat (about 1.5 KB) per chat ever created."""
    import time

    from app.models.orm import Chat
    from app.modules.conversation import chats_repository as chats_repo

    chats_repo._chat_cache.clear()
    now = [time.monotonic()]
    monkeypatch.setattr(chats_repo._chat_cache, "clock", lambda: now[0])
    for _ in range(50):
        chats_repo._remember_chat(Chat(id=uuid4(), user_id=uuid4(), model="auto"))
    now[0] += chats_repo._CHAT_CACHE_TTL_SECONDS + 1
    fresh = Chat(id=uuid4(), user_id=uuid4(), model="auto")
    chats_repo._remember_chat(fresh)

    assert len(chats_repo._chat_cache) == 1
    assert chats_repo.peek_recent_chat(fresh.id, fresh.user_id) is fresh
    assert chats_repo.peek_recent_chat(fresh.id, uuid4()) is None
    chats_repo._chat_cache.clear()


# ── group_by_recency: pure-function O(n) grouper ─────────────────────────────


def _chat(updated_at: datetime):
    c = MagicMock()
    c.updated_at = updated_at
    return c


def test_group_by_recency_today():
    now = datetime.now(UTC)
    chat = _chat(now)
    groups = group_by_recency([chat])
    assert len(groups["today"]) == 1
    assert groups["yesterday"] == []
    assert groups["last_7_days"] == []
    assert groups["this_month"] == []
    assert groups["older"] == []


def test_group_by_recency_older():
    from datetime import timedelta

    now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)
    old = now - timedelta(days=20)
    chat = _chat(old)
    groups = group_by_recency([chat], now=now)
    assert groups["today"] == []
    assert groups["older"] == [chat]


def test_group_by_recency_empty():
    groups = group_by_recency([])
    assert groups == {key: [] for key in RECENCY_BUCKETS}


def test_group_by_recency_naive_datetime():
    """Naive datetimes (no tzinfo) must be handled without raising."""
    naive = datetime(2024, 1, 1, 12, 0, 0)  # no tzinfo
    chat = _chat(naive)
    groups = group_by_recency([chat])  # should not raise
    assert isinstance(groups, dict)
