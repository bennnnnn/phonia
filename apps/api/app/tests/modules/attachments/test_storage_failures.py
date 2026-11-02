"""Attachment outages must preserve content and retain cleanup work."""

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.gateways.storage_gateway import (
    LocalStorageGateway,
    R2StorageGateway,
    StorageUnavailableError,
)
from app.modules.attachments import content as attachment_content
from app.modules.attachments import lifecycle as attachment_lifecycle
from app.modules.attachments import upload as attachment_upload
from app.modules.attachments import workflow as attachment_workflow


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["AccessDenied", "InternalError", "NoSuchBucket"])
async def test_storage_read_failure_does_not_purge_attachment(code):
    client = MagicMock()
    client.get_object.side_effect = ClientError({"Error": {"Code": code}}, "GetObject")
    with patch("boto3.client", return_value=client):
        gateway = R2StorageGateway(Settings())
    session = AsyncMock()
    with (
        patch.object(attachment_content, "purge_invalid_upload", AsyncMock()) as purge,
        pytest.raises(StorageUnavailableError),
    ):
        await attachment_content.ensure_verified_or_purge(
            gateway, session, attachment_id=uuid4(), content_type="text/plain", storage_key="u/a"
        )
    purge.assert_not_awaited()
    client.delete_object.assert_not_called()
    session.commit.assert_not_awaited()


def _r2(*, failing: frozenset[str] = frozenset()) -> R2StorageGateway:
    """An R2 gateway whose deletes fail for these keys.

    Deletes run on the R2 pool, so they finish in any order: the outcome follows
    the key, never the order of the calls.
    """
    client = MagicMock()

    def delete_object(*, Bucket: str, Key: str) -> None:
        if Key in failing:
            raise RuntimeError("timeout")

    client.delete_object.side_effect = delete_object
    with patch("boto3.client", return_value=client):
        return R2StorageGateway(Settings())


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_a_failed_r2_delete_stays_queued_and_backs_off(fake_redis):
    await attachment_lifecycle.enqueue_failed_storage_deletes([])
    with patch.object(attachment_lifecycle, "get_redis_client", return_value=fake_redis):
        await attachment_lifecycle.enqueue_failed_storage_deletes(["u/ok", "u/retry"])
        with patch.object(
            attachment_lifecycle,
            "get_storage_gateway",
            return_value=_r2(failing=frozenset({"u/retry"})),
        ):
            assert await attachment_lifecycle.retry_pending_storage_deletes(Settings()) == 1
    queued = await fake_redis.zrange(
        attachment_lifecycle.PENDING_STORAGE_DELETE_KEY, 0, -1, withscores=True
    )
    assert [key for key, _due in queued] == ["u/retry"]
    # Not due again for an hour: the next pass leaves it alone.
    assert queued[0][1] > time.time() + 3_000


@pytest.mark.asyncio
async def test_the_pending_delete_queue_is_bounded_and_paged(fake_redis):
    """A plain set had no bound and was read whole every reaper cycle."""
    keys = [f"u/{i}" for i in range(15)]
    with (
        patch.object(attachment_lifecycle, "get_redis_client", return_value=fake_redis),
        patch.object(attachment_lifecycle, "_PENDING_MAX", 10),
        patch.object(attachment_lifecycle, "_PENDING_PAGE", 4),
        patch.object(attachment_lifecycle, "delete_storage_keys", AsyncMock(return_value=[])),
    ):
        await attachment_lifecycle.enqueue_failed_storage_deletes(keys)
        assert await fake_redis.zcard(attachment_lifecycle.PENDING_STORAGE_DELETE_KEY) == 10
        assert await attachment_lifecycle.retry_pending_storage_deletes(Settings()) == 4


@pytest.mark.asyncio
async def test_the_old_pending_set_moves_over(fake_redis):
    await fake_redis.sadd(attachment_lifecycle._LEGACY_PENDING_KEY, "u/old")
    with (
        patch.object(attachment_lifecycle, "get_redis_client", return_value=fake_redis),
        patch.object(attachment_lifecycle, "delete_storage_keys", AsyncMock(return_value=[])),
    ):
        assert await attachment_lifecycle.retry_pending_storage_deletes(Settings()) == 1
    assert not await fake_redis.exists(attachment_lifecycle._LEGACY_PENDING_KEY)


@pytest.mark.asyncio
async def test_invalid_upload_preserves_bytes_when_database_delete_fails():
    gateway = MagicMock(delete_bytes=AsyncMock())
    with (
        patch(
            "app.modules.attachments.repository.delete_rows",
            AsyncMock(side_effect=RuntimeError("db")),
        ),
        pytest.raises(RuntimeError, match="db"),
    ):
        await attachment_content.purge_invalid_upload(
            gateway, AsyncMock(), attachment_id=uuid4(), storage_key="u/file"
        )
    gateway.delete_bytes.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("removed", [[], ["u/file"]])
async def test_cancel_pending_uses_committed_unlinked_delete_before_storage(removed):
    user = SimpleNamespace(id=uuid4())
    row = SimpleNamespace(
        id=uuid4(),
        message_id=None,
        content_type="text/plain",
        storage_key="u/file",
        source="upload",
        library_visible=True,
        verified_at=None,
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    order = []

    async def delete_rows(*args, **kwargs):
        order.append("db")
        return removed

    async def delete_bytes(key):
        order.append("storage")
        raise StorageUnavailableError("outage")

    with (
        patch.object(attachment_upload.attachments_repo, "get_by_id", AsyncMock(return_value=row)),
        patch.object(attachment_upload.attachments_repo, "delete_unlinked_returning", delete_rows),
        patch.object(
            attachment_lifecycle,
            "get_storage_gateway",
            return_value=MagicMock(delete_bytes=delete_bytes, delete_prefix=AsyncMock()),
        ),
        patch.object(
            attachment_lifecycle, "enqueue_failed_storage_deletes", AsyncMock()
        ) as enqueue,
    ):
        if removed:
            await attachment_upload.cancel_pending_upload(
                AsyncMock(), Settings(), user=user, attachment_id=row.id
            )
            assert order == ["db", "storage"]
            enqueue.assert_awaited_once_with(["u/file"])
        else:
            with pytest.raises(attachment_upload.AttachmentUploadError) as exc:
                await attachment_upload.cancel_pending_upload(
                    AsyncMock(), Settings(), user=user, attachment_id=row.id
                )
            assert exc.value.status_code == 409
            assert order == ["db"]
            enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [b"original", b"replaced", b""])
async def test_verified_local_file_is_immutable_with_idempotent_upload_retry(tmp_path, payload):
    gateway = LocalStorageGateway(tmp_path)
    await gateway.write_bytes("u/retained", b"original")
    user = SimpleNamespace(id=uuid4())
    row = SimpleNamespace(
        id=uuid4(),
        message_id=None,
        content_type="text/plain",
        storage_key="u/retained",
        size_bytes=8,
        verified_at=datetime.now(UTC),
    )

    async def stream():
        yield payload

    with (
        patch.object(
            attachment_workflow.attachments_repo, "get_by_id", AsyncMock(return_value=row)
        ) as get,
        patch.object(attachment_workflow, "get_storage_gateway", return_value=gateway),
        patch.object(attachment_workflow, "purge_invalid_upload", AsyncMock()) as purge,
    ):
        if payload == b"original":
            await attachment_workflow.store_local_upload(
                AsyncMock(), Settings(), user, row.id, stream()
            )
        else:
            with pytest.raises(attachment_workflow.AttachmentWorkflowError) as exc:
                await attachment_workflow.store_local_upload(
                    AsyncMock(), Settings(), user, row.id, stream()
                )
            assert exc.value.status_code == 409
    assert await gateway.read_bytes("u/retained") == b"original"
    assert get.await_args.kwargs["for_update"] is True
    purge.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_confirm_cannot_succeed_before_upload(tmp_path):
    user = SimpleNamespace(id=uuid4())
    row = SimpleNamespace(id=uuid4(), verified_at=None)
    with (
        patch.object(
            attachment_workflow.attachments_repo, "get_by_id", AsyncMock(return_value=row)
        ),
        patch.object(
            attachment_workflow, "get_storage_gateway", return_value=LocalStorageGateway(tmp_path)
        ),
        pytest.raises(attachment_workflow.AttachmentWorkflowError) as exc,
    ):
        await attachment_workflow.confirm_upload(AsyncMock(), Settings(), user, row.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("removed", [0, 1])
async def test_invalid_confirmation_refunds_only_the_call_that_deleted_row(removed):
    user = SimpleNamespace(id=uuid4())
    row = SimpleNamespace(
        id=uuid4(),
        storage_key="u/pending",
        size_bytes=4,
        content_type="image/png",
        source="upload",
        library_visible=True,
        verified_at=None,
        created_at=datetime.now(UTC),
    )
    gateway = MagicMock(read_bytes=AsyncMock(return_value=b"fake"), delete_bytes=AsyncMock())
    with (
        patch.object(
            attachment_workflow.attachments_repo, "get_by_id", AsyncMock(return_value=row)
        ),
        patch.object(
            attachment_workflow.attachments_repo, "delete_rows", AsyncMock(return_value=removed)
        ),
        patch.object(attachment_workflow, "get_storage_gateway", return_value=gateway),
        patch.object(attachment_workflow, "get_redis_client", return_value=AsyncMock()),
        patch.object(attachment_workflow.counters, "refund", AsyncMock()) as refund,
        pytest.raises(attachment_workflow.AttachmentWorkflowError),
    ):
        await attachment_workflow.confirm_upload(AsyncMock(), Settings(), user, row.id)
    assert refund.await_count == removed
    assert gateway.delete_bytes.await_count == removed
