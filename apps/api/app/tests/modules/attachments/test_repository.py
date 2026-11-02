"""Tests for app.modules.attachments.repository."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_create_pending_attachment(fake_session):
    from app.modules.attachments.repository import create_pending

    attachment_id = uuid4()
    row = await create_pending(
        fake_session,
        attachment_id=attachment_id,
        user_id=uuid4(),
        storage_key="uploads/a",
        content_type="image/png",
        size_bytes=128,
    )

    fake_session.add.assert_called_once()
    fake_session.commit.assert_awaited_once()
    assert row.id == attachment_id
    assert row.library_visible is True


@pytest.mark.asyncio
async def test_create_pending_can_hide_from_library(fake_session):
    from app.modules.attachments.repository import create_pending

    row = await create_pending(
        fake_session,
        attachment_id=uuid4(),
        user_id=uuid4(),
        storage_key="lookups/a",
        content_type="image/jpeg",
        size_bytes=64,
        source="search",
        library_visible=False,
        commit=False,
    )

    fake_session.add.assert_called_once()
    fake_session.flush.assert_awaited_once()
    fake_session.commit.assert_not_called()
    assert row.source == "search"
    assert row.library_visible is False


@pytest.mark.asyncio
async def test_insert_verified_clone_hides_from_library(fake_session):
    from datetime import UTC, datetime

    from app.modules.attachments.repository import insert_verified_clone

    src = MagicMock()
    src.user_id = uuid4()
    src.content_type = "image/png"
    src.size_bytes = 12
    src.source = "generated"
    src.original_filename = "cat.png"
    src.verified_at = datetime(2026, 8, 1, tzinfo=UTC)
    new_id = uuid4()

    row = await insert_verified_clone(
        fake_session,
        src=src,
        new_id=new_id,
        storage_key="user/clone",
    )

    fake_session.add.assert_called_once()
    fake_session.flush.assert_awaited_once()
    fake_session.commit.assert_not_called()
    assert row.id == new_id
    assert row.library_visible is False
    assert row.message_id is None
    assert row.storage_key == "user/clone"


@pytest.mark.asyncio
async def test_get_by_id_returns_attachment(fake_session):
    from app.modules.attachments.repository import get_by_id

    mock_row = MagicMock()
    fake_session.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=mock_row)
    )

    result = await get_by_id(fake_session, uuid4(), uuid4())

    assert result is mock_row


@pytest.mark.asyncio
async def test_get_by_ids_returns_empty_list_without_querying(fake_session):
    from app.modules.attachments.repository import get_by_ids

    result = await get_by_ids(fake_session, [], uuid4())

    assert result == []
    fake_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_by_ids_issues_a_single_batched_query(fake_session):
    from app.modules.attachments.repository import get_by_ids

    rows = [MagicMock(), MagicMock()]
    fake_session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    )

    ids = [uuid4(), uuid4(), uuid4()]
    result = await get_by_ids(fake_session, ids, uuid4())

    assert result == rows
    fake_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_for_gallery_images_returns_rows_and_a_cursor(fake_session):
    from app.modules.attachments.repository import list_for_gallery
    from app.repositories.keyset import decode_cursor

    at = datetime(2026, 10, 1, tzinfo=UTC)
    rows = [SimpleNamespace(created_at=at, id=uuid4()) for _ in range(4)]
    fake_session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    )

    result, next_cursor = await list_for_gallery(
        fake_session, uuid4(), category="images", source="generated", limit=3
    )

    assert result == rows[:3]
    # The cursor names the page's last row; the fourth only says a next page exists.
    assert next_cursor is not None
    assert decode_cursor(next_cursor, ids=1) == (at, [rows[2].id])
    fake_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_for_gallery_exact_page_has_no_cursor(fake_session):
    """A full page with no extra row means there is nothing left to fetch."""
    from app.modules.attachments.repository import list_for_gallery

    rows = [MagicMock(), MagicMock(), MagicMock()]
    fake_session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    )

    result, next_cursor = await list_for_gallery(fake_session, uuid4(), category="images", limit=3)

    assert result == rows
    assert next_cursor is None


@pytest.mark.asyncio
async def test_list_for_gallery_files_category(fake_session):
    """category='files' excludes image content types."""
    from app.modules.attachments.repository import list_for_gallery

    rows = [MagicMock()]
    fake_session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    )

    result, next_cursor = await list_for_gallery(fake_session, uuid4(), category="files", limit=30)

    assert result == rows
    assert next_cursor is None
    fake_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_for_gallery_all_no_filters(fake_session):
    """All still lists only the Library archive (upload + generated)."""
    from app.modules.attachments.repository import list_for_gallery

    rows = [MagicMock()]
    fake_session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    )

    result, next_cursor = await list_for_gallery(fake_session, uuid4(), source=None, limit=30)

    assert result == rows
    assert next_cursor is None


@pytest.mark.asyncio
async def test_list_for_gallery_excludes_unverified(fake_session):
    """The gallery query must filter out unverified attachments (verified_at
    IS NULL) — pending/failed rows produce broken download URLs."""
    from sqlalchemy.dialects import postgresql

    from app.modules.attachments.repository import list_for_gallery

    rows = [MagicMock()]
    captured: dict = {}
    fake_session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows))),
        scalars_=MagicMock(),
    )

    async def _capture(stmt):
        captured["stmt"] = stmt
        return MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
        )

    fake_session.execute = _capture
    await list_for_gallery(fake_session, uuid4(), limit=30)

    compiled = captured["stmt"].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "verified_at" in sql
    assert "library_visible" in sql
    assert "IS NOT NULL" in sql.upper() or "is not" in sql.lower()
    assert "message_id is not null" not in sql.lower()


@pytest.mark.asyncio
async def test_list_for_gallery_excludes_search_source(fake_session):
    """Lookup photos (`source='search'`) must not appear in Library All."""
    from sqlalchemy.dialects import postgresql

    from app.modules.attachments.repository import list_for_gallery

    captured: dict = {}

    async def _capture(stmt):
        captured["stmt"] = stmt
        return MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))

    fake_session.execute = _capture
    await list_for_gallery(fake_session, uuid4(), limit=30)

    compiled = captured["stmt"].compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql = str(compiled).lower()
    assert "upload" in sql
    assert "generated" in sql
    assert "search" not in sql


@pytest.mark.asyncio
async def test_list_for_gallery_fetches_one_extra_row_for_the_cursor(fake_session):
    from sqlalchemy.dialects import postgresql

    from app.modules.attachments.repository import list_for_gallery

    captured: dict = {}

    async def _capture(stmt):
        captured["stmt"] = stmt
        return MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))

    fake_session.execute = _capture
    await list_for_gallery(fake_session, uuid4(), limit=30)

    compiled = captured["stmt"].compile(dialect=postgresql.dialect())
    combined = f"{compiled} {compiled.params}"
    assert "31" in combined


@pytest.mark.asyncio
async def test_chat_meta_for_message_ids_skips_empty(fake_session):
    from app.modules.attachments.repository import chat_meta_for_message_ids

    assert await chat_meta_for_message_ids(fake_session, []) == {}
    fake_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_chat_meta_for_message_ids_maps_title(fake_session):
    from app.modules.attachments.repository import chat_meta_for_message_ids

    message_id = uuid4()
    chat_id = uuid4()
    fake_session.execute.return_value = MagicMock(
        all=MagicMock(return_value=[(message_id, chat_id, "Trip")])
    )

    result = await chat_meta_for_message_ids(fake_session, [message_id])

    assert result == {message_id: (chat_id, "Trip")}


def test_sanitize_original_filename():
    from app.modules.attachments.upload import sanitize_original_filename

    assert sanitize_original_filename("notes.pdf") == "notes.pdf"
    assert sanitize_original_filename("folder/../notes.pdf") == "notes.pdf"
    assert sanitize_original_filename("..") is None
    assert sanitize_original_filename("  ") is None
    assert sanitize_original_filename(None) is None


@pytest.mark.asyncio
async def test_list_for_gallery_q_matches_filename_and_prompt(fake_session):
    from sqlalchemy.dialects import postgresql

    from app.modules.attachments.repository import list_for_gallery

    captured: dict = {}

    async def _capture(stmt):
        captured["stmt"] = stmt
        return MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))

    fake_session.execute = _capture
    await list_for_gallery(fake_session, uuid4(), q="100%", limit=30)

    compiled = captured["stmt"].compile(dialect=postgresql.dialect())
    combined = f"{compiled} {compiled.params}".lower()
    assert "original_filename" in combined
    assert "100" in combined
    assert "\\\\%" in combined or "\\%" in combined
    # Generated images are linked to the assistant [Image:] row; search the
    # previous user message in that chat so the draw prompt matches.
    assert "messages" in combined
    assert "role" in combined


@pytest.mark.asyncio
async def test_list_for_gallery_reads_after_the_cursor(fake_session):
    """The next page starts after the last row read, so a delete cannot shift it."""
    from sqlalchemy.dialects import postgresql

    from app.modules.attachments.repository import list_for_gallery
    from app.repositories.keyset import encode_cursor

    captured: dict = {}

    async def _capture(stmt):
        captured["stmt"] = stmt
        return MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))

    fake_session.execute = _capture
    cursor = encode_cursor(datetime(2026, 10, 1, tzinfo=UTC), uuid4())
    await list_for_gallery(fake_session, uuid4(), limit=30, cursor=cursor)

    sql = str(captured["stmt"].compile(dialect=postgresql.dialect()))
    assert "(attachments.created_at, attachments.id) < (" in sql
    assert "OFFSET" not in sql.upper()
