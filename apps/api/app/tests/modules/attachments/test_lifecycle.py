"""Attachment lifecycle service tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.attachments import lifecycle as attachment_lifecycle
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
async def test_purge_attachments_for_messages_deletes_bytes_and_rows():
    settings = Settings()
    message_id = uuid4()
    row = MagicMock()
    row.id = uuid4()
    row.storage_key = "user/file"
    session = AsyncMock()
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()
    order: list[str] = []

    async def delete_rows(_session, ids, *, commit=True):
        order.append("rows")
        return 1

    async def delete_bytes(key: str) -> None:
        order.append(f"bytes:{key}")

    gateway.delete_bytes = delete_bytes

    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_for_message_ids",
            AsyncMock(return_value=[row]),
        ),
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_rows",
            side_effect=delete_rows,
        ),
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            return_value=gateway,
        ),
    ):
        deleted = await attachment_lifecycle.purge_attachments_for_messages(
            session, settings, [message_id]
        )

    assert deleted == 1
    assert order == ["rows", "bytes:user/file"]


@pytest.mark.asyncio
async def test_delete_objects_of_deleted_rows_queues_only_the_failed_ones():
    """Account delete's files go after its rows commit: one R2 failure is queued for the
    reaper's retry and never stops the others."""
    deleted_keys: list[str] = []

    async def delete_bytes(key: str) -> None:
        if key == "user/bad":
            raise RuntimeError("r2 down")
        deleted_keys.append(key)

    gateway = MagicMock()
    gateway.delete_bytes = delete_bytes
    gateway.delete_prefix = AsyncMock(return_value=0)
    with (
        patch("app.modules.attachments.lifecycle.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.lifecycle.enqueue_failed_storage_deletes", AsyncMock()
        ) as queued,
    ):
        await attachment_lifecycle.delete_objects_of_deleted_rows(
            Settings(), ["user/ok", "user/bad"]
        )

    assert deleted_keys == ["user/ok"]
    queued.assert_awaited_once_with(["user/bad"])


@pytest.mark.asyncio
async def test_delete_objects_of_deleted_rows_never_raises():
    """No gateway at all (misconfigured storage): every key is queued, nothing raises."""
    with (
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            side_effect=RuntimeError("no storage"),
        ),
        patch(
            "app.modules.attachments.lifecycle.enqueue_failed_storage_deletes", AsyncMock()
        ) as queued,
    ):
        await attachment_lifecycle.delete_objects_of_deleted_rows(Settings(), ["user/a"])

    queued.assert_awaited_once_with(["user/a"])


@pytest.mark.asyncio
async def test_reap_orphan_attachments_skips_rows_linked_after_list():
    """DB-first: the DB unlink check (delete_unlinked_returning) runs BEFORE
    storage deletion, so a row linked between list and delete is NOT reaped
    and its bytes are NOT touched — preserving the linked attachment's
    content. Previously storage was deleted first, which could leave a linked
    attachment with missing file content."""
    settings = Settings()
    orphan_id = uuid4()
    orphan = MagicMock()
    orphan.id = orphan_id
    orphan.storage_key = "user/file"
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()

    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=[orphan]),
        ),
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            AsyncMock(return_value=[]),
        ) as delete_unlinked,
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.lifecycle.retry_pending_storage_deletes",
            AsyncMock(return_value=0),
        ),
    ):
        deleted = await attachment_lifecycle.reap_orphan_attachments(settings)

    assert deleted == 0
    delete_unlinked.assert_awaited_once()
    # DB-first: bytes are NOT deleted when the row was linked after list time.
    gateway.delete_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_reap_orphan_attachments_deletes_db_rows_before_bytes():
    """DB-first: the reaper deletes DB rows (via delete_unlinked_returning)
    BEFORE storage bytes, so a row linked between list and delete time is
    preserved. Storage deletion only runs for rows confirmed still unlinked."""
    settings = Settings()
    orphan = MagicMock()
    orphan.id = uuid4()
    orphan.storage_key = "user/file"
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()
    call_order: list[str] = []

    async def _delete_bytes(key):
        call_order.append("bytes")

    async def _delete_unlinked(session, ids, *, orphan_only):
        assert orphan_only
        call_order.append("db")
        return [orphan.storage_key]

    gateway.delete_bytes = _delete_bytes
    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=[orphan]),
        ),
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            side_effect=_delete_unlinked,
        ),
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.lifecycle.retry_pending_storage_deletes",
            AsyncMock(return_value=0),
        ),
    ):
        deleted = await attachment_lifecycle.reap_orphan_attachments(settings)

    assert deleted == 1
    assert call_order == ["db", "bytes"]


@pytest.mark.asyncio
async def test_reap_orphan_attachments_no_orphans_is_noop():
    settings = Settings()
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()
    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            AsyncMock(),
        ) as delete_unlinked,
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.lifecycle.retry_pending_storage_deletes",
            AsyncMock(return_value=0),
        ),
    ):
        deleted = await attachment_lifecycle.reap_orphan_attachments(settings)

    assert deleted == 0
    delete_unlinked.assert_not_awaited()
    gateway.delete_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_reap_orphan_attachments_refunds_image_upload_quota():
    """Reaping an uploaded image orphan must refund the daily image-upload slot —
    without this, an abandoned presign (never sent/confirmed) permanently
    consumes a slot the user can never get back."""
    settings = Settings()
    user_id = uuid4()
    orphan = MagicMock()
    orphan.id = uuid4()
    orphan.user_id = user_id
    orphan.content_type = "image/png"
    orphan.storage_key = "user/img"
    orphan.source = "upload"
    orphan.library_visible = True
    orphan.verified_at = None
    _now = datetime.now(UTC)
    # Clamp to the start of today: the reservation is keyed to the UTC
    # calendar day, so within an hour of midnight "an hour ago" is
    # yesterday and this would assert the opposite of what it means.
    orphan.created_at = max(
        _now - timedelta(hours=1), _now.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()
    fake_redis = redis_mock()
    refund = AsyncMock()

    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=[orphan]),
        ),
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            AsyncMock(return_value=[orphan.storage_key]),
        ),
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.lifecycle.get_redis_client",
            return_value=fake_redis,
        ),
        patch("app.modules.attachments.lifecycle.counters.refund", refund),
    ):
        deleted = await attachment_lifecycle.reap_orphan_attachments(settings)

    assert deleted == 1
    refund.assert_awaited_once_with("image_upload", fake_redis, user_id)


@pytest.mark.asyncio
async def test_reap_orphan_attachments_passes_pending_grace_to_list():
    settings = Settings(attachment_pending_orphan_hours=1, attachment_orphan_grace_hours=24)
    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=[]),
        ) as list_orphans,
        patch(
            "app.modules.attachments.lifecycle.retry_pending_storage_deletes",
            AsyncMock(return_value=0),
        ),
    ):
        await attachment_lifecycle.reap_orphan_attachments(settings)

    kwargs = list_orphans.await_args.kwargs
    assert kwargs["older_than_hours"] == 24
    assert kwargs["pending_older_than_hours"] == 1


@pytest.mark.asyncio
async def test_reap_orphan_attachments_does_not_refund_generated_reuse_clones():
    """Reaping a generated-image orphan must refund imggen, not imgup."""
    settings = Settings()
    user_id = uuid4()
    orphan = MagicMock()
    orphan.id = uuid4()
    orphan.user_id = user_id
    orphan.content_type = "image/png"
    orphan.storage_key = "user/gen-img"
    orphan.source = "generated"
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()
    fake_redis = redis_mock()
    refund = AsyncMock()

    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=[orphan]),
        ),
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            AsyncMock(return_value=[orphan.storage_key]),
        ),
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.lifecycle.get_redis_client",
            return_value=fake_redis,
        ),
        patch("app.modules.attachments.lifecycle.counters.refund", refund),
    ):
        deleted = await attachment_lifecycle.reap_orphan_attachments(settings)

    assert deleted == 1
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_reap_orphan_attachments_does_not_refund_for_non_image():
    """Non-image orphans (e.g. PDFs) don't consume an image slot, so no refund."""
    settings = Settings()
    user_id = uuid4()
    orphan = MagicMock()
    orphan.id = uuid4()
    orphan.user_id = user_id
    orphan.content_type = "application/pdf"
    orphan.storage_key = "user/doc"
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()
    fake_redis = redis_mock()
    refund_mock = AsyncMock()

    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=[orphan]),
        ),
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            AsyncMock(return_value=[orphan.storage_key]),
        ),
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.lifecycle.get_redis_client",
            return_value=fake_redis,
        ),
        patch(
            "app.modules.attachments.lifecycle.counters.refund",
            refund_mock,
        ),
    ):
        deleted = await attachment_lifecycle.reap_orphan_attachments(settings)

    assert deleted == 1
    refund_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_reap_orphan_attachments_skips_refund_when_row_linked_after_list():
    """If a row gets linked between list and delete, it's NOT reaped and must
    NOT be refunded — the slot is still in use by the linked message."""
    settings = Settings()
    user_id = uuid4()
    orphan = MagicMock()
    orphan.id = uuid4()
    orphan.user_id = user_id
    orphan.content_type = "image/png"
    orphan.storage_key = "user/img"
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()
    fake_redis = redis_mock()
    refund_mock = AsyncMock()

    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=[orphan]),
        ),
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            AsyncMock(return_value=[]),  # row was linked, nothing removed
        ),
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.lifecycle.get_redis_client",
            return_value=fake_redis,
        ),
        patch(
            "app.modules.attachments.lifecycle.counters.refund",
            refund_mock,
        ),
    ):
        deleted = await attachment_lifecycle.reap_orphan_attachments(settings)

    assert deleted == 0
    refund_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_reap_orphan_attachments_continues_when_storage_delete_fails():
    """DB-first: a failed storage delete (for a row already removed from DB)
    is logged and skipped — it does not abort the batch. The DB row is already
    gone; failed objects must remain queued for the next cleanup pass."""
    settings = Settings()
    ok = MagicMock()
    ok.id = uuid4()
    ok.storage_key = "user/ok"
    ok.content_type = "application/pdf"
    bad = MagicMock()
    bad.id = uuid4()
    bad.storage_key = "user/bad"
    bad.content_type = "application/pdf"

    async def delete_bytes(key: str) -> None:
        if key == "user/bad":
            raise RuntimeError("r2 down")

    gateway = MagicMock()
    gateway.delete_bytes = delete_bytes
    gateway.delete_prefix = AsyncMock()

    async def delete_unlinked(_session, ids, *, orphan_only):
        assert orphan_only
        # Both rows confirmed still unlinked at delete time.
        return ["user/ok", "user/bad"]

    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=[ok, bad]),
        ),
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            side_effect=delete_unlinked,
        ),
        patch(
            "app.modules.attachments.lifecycle.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.lifecycle.enqueue_failed_storage_deletes", AsyncMock()
        ) as enqueue,
    ):
        deleted = await attachment_lifecycle.reap_orphan_attachments(settings)

    # Both rows were removed from the DB; the bad storage delete is best-effort.
    assert deleted == 2
    enqueue.assert_awaited_once_with(["user/bad"])


@pytest.mark.asyncio
async def test_sweep_user_storage_deletes_user_prefix():
    user_id = uuid4()
    gateway = MagicMock()
    gateway.delete_prefix = AsyncMock(return_value=3)
    with patch(
        "app.modules.attachments.lifecycle.get_storage_gateway",
        return_value=gateway,
    ):
        deleted = await attachment_lifecycle.sweep_user_storage(Settings(), user_id)
    assert deleted == 3
    gateway.delete_prefix.assert_awaited_once_with(f"{user_id}/")


def _orphans(count: int) -> list[MagicMock]:
    rows = []
    for index in range(count):
        row = MagicMock()
        row.id = uuid4()
        row.storage_key = f"user/file-{index}-{uuid4()}"
        row.content_type = "application/pdf"
        rows.append(row)
    return rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("batches", "expected_lists", "expected_reaped"),
    [
        # Full batches go on until a short one: a backlog drains in one cycle.
        ([2, 2, 1], 3, 5),
        # The cycle's cap holds even when every batch is full.
        ([2, 2, 2, 2], 3, 6),
    ],
)
async def test_reap_orphan_attachments_runs_batches_while_they_are_full(
    batches: list[int], expected_lists: int, expected_reaped: int
):
    settings = Settings(attachment_orphan_reap_limit=2, attachment_orphan_reap_batches_per_cycle=3)
    lists = [_orphans(count) for count in batches]
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()

    async def _delete_unlinked(session, ids, *, orphan_only):
        rows = next(batch for batch in lists if batch and batch[0].id in ids)
        return [row.storage_key for row in rows]

    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(side_effect=lists),
        ) as list_orphans,
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            side_effect=_delete_unlinked,
        ),
        patch("app.modules.attachments.lifecycle.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.lifecycle.retry_pending_storage_deletes",
            AsyncMock(return_value=0),
        ),
    ):
        reaped = await attachment_lifecycle.reap_orphan_attachments(settings)

    assert list_orphans.await_count == expected_lists
    assert reaped == expected_reaped


@pytest.mark.asyncio
async def test_reap_orphan_attachments_stops_when_a_full_batch_removes_nothing():
    settings = Settings(attachment_orphan_reap_limit=2, attachment_orphan_reap_batches_per_cycle=5)
    with (
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.list_orphans",
            AsyncMock(return_value=_orphans(2)),
        ) as list_orphans,
        patch(
            "app.modules.attachments.lifecycle.attachments_repo.delete_unlinked_returning",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.attachments.lifecycle.retry_pending_storage_deletes",
            AsyncMock(return_value=0),
        ),
    ):
        reaped = await attachment_lifecycle.reap_orphan_attachments(settings)

    assert reaped == 0
    assert list_orphans.await_count == 1


@pytest.mark.asyncio
async def test_a_failed_thumbnail_delete_is_queued_for_the_retry():
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()
    gateway.delete_prefix = AsyncMock(side_effect=RuntimeError("r2 down"))
    with (
        patch("app.modules.attachments.lifecycle.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.lifecycle.enqueue_failed_storage_deletes", AsyncMock()
        ) as enqueue,
    ):
        failed = await attachment_lifecycle.delete_storage_keys(Settings(), ["u/a", "u/b"])

    # The objects went; their thumbnails did not, so both keys wait for the retry.
    assert failed == []
    enqueue.assert_awaited_once_with(["u/a", "u/b"])
