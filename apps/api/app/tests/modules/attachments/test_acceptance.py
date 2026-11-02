"""Unavailable attachment references must fail before saving a text-only turn."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.exceptions import AttachmentValidationError, ChatBusyError
from app.gateways.storage_gateway import LocalStorageGateway, StorageUnavailableError
from app.modules.attachments.quota import has_current_upload_reservation
from app.modules.chat.turn_prep.attachments import _process_attachments
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_missing_or_foreign_requested_ids_fail_before_reuse(partial):
    user = SimpleNamespace(id=uuid4())
    owned = SimpleNamespace(id=uuid4())
    ids = [owned.id, uuid4()] if partial else [uuid4()]
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    with (
        patch("app.modules.chat.turn_prep.attachments.SessionLocal", return_value=context),
        patch(
            "app.modules.attachments.repository.get_by_ids",
            AsyncMock(return_value=[owned] if partial else []),
        ),
        patch("app.modules.attachments.reuse.ensure_unlinked_copies", AsyncMock()) as copies,
        pytest.raises(AttachmentValidationError, match="no longer available"),
    ):
        await _process_attachments(
            user_id=user.id,
            user=user,
            content="keep this",
            attachment_ids=ids,
            settings=Settings(attachments_enabled=True),
            redis=redis_mock(),
            on_status=None,
        )
    copies.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_presign_without_upload_cannot_be_sent(tmp_path):
    user = SimpleNamespace(id=uuid4())
    row = SimpleNamespace(
        id=uuid4(),
        message_id=None,
        verified_at=None,
        source="upload",
        library_visible=True,
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
        storage_key="u/pending",
        size_bytes=5,
        content_type="text/plain",
    )
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    with (
        patch("app.modules.chat.turn_prep.attachments.SessionLocal", return_value=context),
        patch("app.modules.attachments.repository.get_by_ids", AsyncMock(return_value=[row])),
        patch(
            "app.gateways.storage_gateway.get_storage_gateway",
            return_value=LocalStorageGateway(tmp_path),
        ),
        patch("app.modules.attachments.content.purge_invalid_upload", AsyncMock()),
        pytest.raises(AttachmentValidationError, match="Upload not found"),
    ):
        await _process_attachments(
            user_id=user.id,
            user=user,
            content="keep this",
            attachment_ids=[row.id],
            settings=Settings(attachments_enabled=True),
            redis=redis_mock(),
            on_status=None,
        )
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_outage_before_acceptance_is_safe_to_retry():
    user = SimpleNamespace(id=uuid4())
    with (
        patch(
            "app.modules.chat.turn_prep.attachments._process_attachment_inputs",
            AsyncMock(side_effect=StorageUnavailableError("outage")),
        ),
        pytest.raises(ChatBusyError, match="storage is temporarily unavailable"),
    ):
        await _process_attachments(
            user_id=user.id,
            user=user,
            content="keep this",
            attachment_ids=[uuid4()],
            settings=Settings(attachments_enabled=True),
            redis=redis_mock(),
            on_status=None,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"library_visible": False},
        {"verified_at": datetime.now(UTC)},
        {"source": "generated"},
        {"created_at": datetime.now(UTC) - timedelta(days=1)},
    ],
)
def test_reuse_completed_and_previous_day_uploads_cannot_refund_today(change):
    values = dict(
        source="upload", library_visible=True, verified_at=None, created_at=datetime.now(UTC)
    )
    assert has_current_upload_reservation(SimpleNamespace(**values))
    values.update(change)
    assert not has_current_upload_reservation(SimpleNamespace(**values))


def test_hour_old_same_day_upload_still_has_reservation():
    now = datetime.now(UTC)
    # Clamp to the start of today: the reservation is keyed to the UTC
    # calendar day, so within an hour of midnight "an hour ago" is
    # yesterday and this would assert the opposite of what it means.
    earlier_today = max(
        now - timedelta(hours=1), now.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    values = SimpleNamespace(
        source="upload",
        library_visible=True,
        verified_at=None,
        created_at=earlier_today,
    )
    assert has_current_upload_reservation(values)
