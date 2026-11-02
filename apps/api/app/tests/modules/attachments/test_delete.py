"""Library item delete — strip the chat marker, drop bytes, no upload refund."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.attachments.workflow import AttachmentWorkflowError, delete_attachment


@pytest.mark.asyncio
async def test_delete_library_attachment_strips_message_and_does_not_refund():
    user = MagicMock()
    user.id = uuid4()
    settings = MagicMock()
    session = AsyncMock()
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id
    row.message_id = uuid4()
    row.storage_key = "user/key"
    message = MagicMock()
    message.content = f"[Image: /attachments/{attachment_id}/file]\nKeep this"

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.workflow.chat_history.message_for_user",
            AsyncMock(return_value=message),
        ),
        patch(
            "app.modules.attachments.workflow.attachments_repo.delete_rows",
            AsyncMock(return_value=1),
        ),
        patch(
            "app.modules.attachments.workflow.delete_storage_keys",
            AsyncMock(return_value=[]),
        ) as storage,
        patch(
            "app.modules.attachments.workflow.enqueue_failed_storage_deletes",
            AsyncMock(),
        ),
        patch(
            "app.modules.attachments.workflow.cancel_pending_upload",
            AsyncMock(),
        ) as cancel,
        patch(
            "app.modules.attachments.workflow.counters.refund",
            AsyncMock(),
        ) as refund,
    ):
        await delete_attachment(session, settings, user, row.id)

    cancel.assert_not_awaited()
    refund.assert_not_awaited()
    assert message.content == "Keep this"
    session.delete.assert_not_called()
    session.commit.assert_awaited_once()
    storage.assert_awaited_once_with(settings, ["user/key"])


@pytest.mark.asyncio
async def test_delete_library_attachment_deletes_empty_message():
    user = MagicMock()
    user.id = uuid4()
    settings = MagicMock()
    session = AsyncMock()
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id
    row.message_id = uuid4()
    row.storage_key = "user/key"
    message = MagicMock()
    message.content = f"[Image: /attachments/{attachment_id}/file]"

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.workflow.chat_history.message_for_user",
            AsyncMock(return_value=message),
        ),
        patch(
            "app.modules.attachments.workflow.attachments_repo.delete_rows",
            AsyncMock(return_value=1),
        ),
        patch(
            "app.modules.attachments.workflow.delete_storage_keys",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.attachments.workflow.enqueue_failed_storage_deletes",
            AsyncMock(),
        ),
    ):
        await delete_attachment(session, settings, user, row.id)

    session.delete.assert_awaited_once_with(message)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_attachment_missing_is_not_found():
    user = MagicMock()
    user.id = uuid4()
    with patch(
        "app.modules.attachments.workflow.attachments_repo.get_by_id",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(AttachmentWorkflowError) as exc_info:
            await delete_attachment(AsyncMock(), MagicMock(), user, uuid4())
    assert exc_info.value.status_code == 404
