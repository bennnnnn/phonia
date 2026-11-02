"""Tests for Library reuse clones."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.exceptions import AttachmentValidationError
from app.modules.attachments.reuse import ensure_unlinked_copies


@pytest.mark.asyncio
async def test_ensure_unlinked_copies_keeps_unlinked_rows():
    session = AsyncMock()
    row = MagicMock()
    row.message_id = None

    out = await ensure_unlinked_copies(session, Settings(), [row])

    assert out == [row]
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_unlinked_copies_copies_bytes_for_linked_rows():
    session = AsyncMock()
    src = MagicMock()
    src.id = uuid4()
    src.user_id = uuid4()
    src.message_id = uuid4()
    src.storage_key = "user/orig"
    src.content_type = "image/png"
    src.size_bytes = 4
    src.source = "upload"
    src.original_filename = "pic.png"
    src.verified_at = datetime(2026, 8, 1, tzinfo=UTC)

    clone = MagicMock()
    gateway = MagicMock()
    gateway.copy_bytes = AsyncMock(return_value=True)

    with (
        patch(
            "app.modules.attachments.reuse.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.reuse.attachments_repo.insert_verified_clone",
            AsyncMock(return_value=clone),
        ) as insert,
    ):
        out = await ensure_unlinked_copies(session, Settings(), [src])

    assert out == [clone]
    # Copied inside storage under a new key; the bytes never pass through the API.
    new_key = insert.await_args.kwargs["storage_key"]
    gateway.copy_bytes.assert_awaited_once_with("user/orig", new_key)
    assert str(new_key).startswith(f"{src.user_id}/")
    insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_unlinked_copies_raises_when_bytes_missing():
    session = AsyncMock()
    src = MagicMock()
    src.message_id = uuid4()
    src.storage_key = "user/gone"
    gateway = MagicMock()
    gateway.copy_bytes = AsyncMock(return_value=False)

    with (
        patch(
            "app.modules.attachments.reuse.get_storage_gateway",
            return_value=gateway,
        ),
        pytest.raises(AttachmentValidationError),
    ):
        await ensure_unlinked_copies(session, Settings(), [src])


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["insert", "commit", "second_write"])
async def test_clone_failure_rolls_back_and_cleans_every_attempted_object(failure):
    session = AsyncMock()
    src = MagicMock(message_id=uuid4(), storage_key="u/original", user_id=uuid4())
    gateway = MagicMock(copy_bytes=AsyncMock(return_value=True))
    insert = AsyncMock(return_value=MagicMock())
    if failure == "insert":
        insert.side_effect = RuntimeError("insert")
    elif failure == "commit":
        # The first commit ends the caller's read before the copies; the clones' fails.
        session.commit.side_effect = [None, RuntimeError("commit")]
    else:
        gateway.copy_bytes.side_effect = [True, RuntimeError("second_write")]
    with (
        patch("app.modules.attachments.reuse.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.reuse.attachments_repo.insert_verified_clone", insert),
        patch(
            "app.modules.attachments.lifecycle.delete_storage_keys", AsyncMock(return_value=[])
        ) as cleanup,
        pytest.raises(RuntimeError, match=failure),
    ):
        await ensure_unlinked_copies(session, Settings(), [src, src])
    session.rollback.assert_awaited_once()
    attempted_keys = [call.args[1] for call in gateway.copy_bytes.await_args_list]
    assert cleanup.await_args.args[1] == attempted_keys
    assert "u/original" not in attempted_keys
