from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.modules.search import repository as search_repo
from app.repositories.keyset import encode_cursor


def _title_row(*, chat_id, title: str, created_at: datetime):
    row = MagicMock()
    row.match_type = "title"
    row.message_id = None
    row.chat_id = chat_id
    row.chat_title = title
    row.content = title
    row.role = "chat"
    row.created_at = created_at
    return row


def _message_row(*, message_id, chat_id, title: str, content: str, created_at: datetime):
    row = MagicMock()
    row.match_type = "message"
    row.message_id = message_id
    row.chat_id = chat_id
    row.chat_title = title
    row.content = content
    row.role = "user"
    row.created_at = created_at
    return row


@pytest.mark.asyncio
async def test_search_includes_title_only_match():
    user_id = uuid4()
    chat_id = uuid4()
    session = AsyncMock()
    page_result = MagicMock()
    page_result.all.return_value = [
        _title_row(chat_id=chat_id, title="Trip planning", created_at=datetime.now(UTC))
    ]
    session.execute = AsyncMock(return_value=page_result)

    results, next_cursor = await search_repo.search_conversations(session, user_id, "trip")

    assert next_cursor is None
    assert len(results) == 1
    assert results[0]["match_type"] == "title"
    assert results[0]["chat_id"] == chat_id
    assert results[0]["message_id"] is None


@pytest.mark.asyncio
async def test_search_pages_the_merged_union_once():
    """The cursor and limit apply to the union, not to title and message streams
    separately; nothing counts every hit, and nothing skips by offset."""
    session = AsyncMock()
    page_result = MagicMock()
    page_result.all.return_value = []
    session.execute = AsyncMock(return_value=page_result)
    cursor = encode_cursor(datetime(2026, 9, 4, tzinfo=UTC), uuid4(), uuid4())

    results, next_cursor = await search_repo.search_conversations(
        session, uuid4(), "trip", limit=20, cursor=cursor
    )

    assert results == []
    assert next_cursor is None
    session.execute.assert_awaited_once()
    sql = str(session.execute.await_args.args[0]).lower()
    assert "union all" in sql
    assert sql.count("limit") == 1
    assert "offset" not in sql
    assert "(search_hits.created_at, search_hits.chat_id, coalesce(" in sql
    assert "count(" not in sql


@pytest.mark.asyncio
async def test_search_reads_one_row_past_the_page_for_the_cursor():
    now = datetime.now(UTC)
    page = MagicMock()
    page.all.return_value = [
        _message_row(
            message_id=uuid4(), chat_id=uuid4(), title="Trip", content="trip notes", created_at=now
        ),
        _title_row(chat_id=uuid4(), title="Trip planning", created_at=now),
    ]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=page)

    results, next_cursor = await search_repo.search_conversations(session, uuid4(), "trip", limit=1)

    assert [row["match_type"] for row in results] == ["message"]
    first = page.all.return_value[0]
    assert next_cursor == encode_cursor(now, first.chat_id, first.message_id)


# ── search repository snippet ───────────────────────────────────────────────


def test_search_snippet_exact_match():
    from app.modules.search.repository import _snippet

    content = "The quick brown fox jumps over the lazy dog"
    result = _snippet(content, "fox", 120)
    assert "fox" in result


def test_search_snippet_no_match():
    from app.modules.search.repository import _snippet

    content = "Hello world"
    result = _snippet(content, "zzz", 120)
    assert len(result) <= 120


def test_search_snippet_truncation():
    from app.modules.search.repository import _snippet

    content = "a" * 300 + "needle" + "b" * 300
    result = _snippet(content, "needle", 120)
    assert "needle" in result
    # Expect at most: 40 (prefix) + len(query) + 80 (suffix) + 2 (… markers) ≈ 128
    assert len(result) <= 130
