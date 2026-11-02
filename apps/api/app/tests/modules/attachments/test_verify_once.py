"""Confirm checks an upload once: a HEAD first, never again once verified, one at a time."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.redis import get_redis_client
from app.modules.attachments import verify as attachment_verify
from app.modules.attachments import workflow as attachment_workflow
from app.modules.attachments.content import MAX_ATTACHMENT_SIZE
from app.tests.fakes import fake_session, make_user

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 24


def _row(*, verified: bool = False, size: int = len(PNG)) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        storage_key="u/pending",
        size_bytes=size,
        content_type="image/png",
        source="upload",
        library_visible=True,
        verified_at=datetime.now(UTC) if verified else None,
        created_at=datetime.now(UTC),
        message_id=None,
    )


def _gateway(*, size: int | None = len(PNG), data: bytes = PNG) -> MagicMock:
    return MagicMock(
        object_size=AsyncMock(return_value=size),
        read_bytes=AsyncMock(return_value=data),
        delete_bytes=AsyncMock(),
    )


async def _confirm(row: Any, gateway: MagicMock, **repo: Any) -> None:
    user = make_user()
    with (
        patch.object(
            attachment_workflow.attachments_repo,
            "get_by_id",
            repo.get("get_by_id", AsyncMock(return_value=row)),
        ),
        patch.object(
            attachment_workflow.attachments_repo,
            "mark_verified",
            repo.get("mark_verified", AsyncMock()),
        ),
        patch.object(
            attachment_workflow.attachments_repo,
            "delete_rows",
            repo.get("delete_rows", AsyncMock(return_value=1)),
        ),
        patch.object(attachment_workflow, "get_storage_gateway", return_value=gateway),
        patch.object(attachment_workflow.counters, "refund", AsyncMock()),
    ):
        await attachment_workflow.confirm_upload(fake_session(), Settings(), user, row.id)


@pytest.mark.asyncio
async def test_confirm_of_a_verified_upload_reads_nothing_from_storage() -> None:
    gateway = _gateway()
    await _confirm(_row(verified=True), gateway)
    gateway.object_size.assert_not_awaited()
    gateway.read_bytes.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored, error",
    [
        (None, "Upload not found"),
        (0, "Upload not found"),
        (MAX_ATTACHMENT_SIZE + 1, "Invalid upload size"),
        (len(PNG) + 1, "Uploaded size does not match the declared size"),
    ],
)
async def test_confirm_refuses_a_bad_size_from_the_head_without_downloading(
    stored: int | None, error: str
) -> None:
    gateway = _gateway(size=stored)
    with pytest.raises(attachment_workflow.AttachmentWorkflowError) as refused:
        await _confirm(_row(), gateway)
    assert refused.value.message == error
    assert refused.value.status_code == 400
    gateway.read_bytes.assert_not_awaited()
    gateway.delete_bytes.assert_awaited_once_with("u/pending")


@pytest.mark.asyncio
async def test_confirm_with_a_matching_head_checks_the_bytes_and_marks_verified() -> None:
    gateway = _gateway()
    mark_verified = AsyncMock()
    row = _row()
    await _confirm(row, gateway, mark_verified=mark_verified)
    gateway.read_bytes.assert_awaited_once_with("u/pending")
    mark_verified.assert_awaited_once()


@pytest.mark.asyncio
async def test_parallel_confirms_of_one_upload_download_it_once() -> None:
    row = _row()
    state: dict[str, datetime | None] = {"verified_at": None}

    async def get_by_id(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(**{**vars(row), "verified_at": state["verified_at"]})

    async def mark_verified(*_args: Any, **_kwargs: Any) -> None:
        state["verified_at"] = datetime.now(UTC)

    async def slow_read(_key: str) -> bytes:
        await asyncio.sleep(0.3)
        return PNG

    gateway = _gateway()
    gateway.read_bytes = AsyncMock(side_effect=slow_read)
    user = make_user()
    with (
        patch.object(attachment_workflow.attachments_repo, "get_by_id", get_by_id),
        patch.object(attachment_workflow.attachments_repo, "mark_verified", mark_verified),
        patch.object(attachment_workflow, "get_storage_gateway", return_value=gateway),
        patch.object(attachment_verify, "POLL_SECONDS", 0.02),
    ):
        await asyncio.gather(
            *(
                attachment_workflow.confirm_upload(fake_session(), Settings(), user, row.id)
                for _ in range(5)
            )
        )
    assert gateway.read_bytes.await_count == 1
    assert gateway.object_size.await_count == 1


@pytest.mark.asyncio
async def test_confirm_while_another_check_holds_the_lock_asks_to_retry() -> None:
    row = _row()
    await get_redis_client().set(attachment_verify.lock_key(row.id), "peer", ex=60)
    gateway = _gateway()
    with (
        patch.object(attachment_verify, "WAIT_SECONDS", 0.05),
        patch.object(attachment_verify, "POLL_SECONDS", 0.01),
        pytest.raises(attachment_workflow.AttachmentWorkflowError) as refused,
    ):
        await _confirm(row, gateway)
    assert refused.value.status_code == 409
    assert refused.value.code == "upload_verifying"
    gateway.object_size.assert_not_awaited()
    gateway.read_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_releases_the_lock_after_a_storage_outage() -> None:
    from app.gateways.storage_gateway import StorageUnavailableError

    row = _row()
    gateway = _gateway()
    gateway.read_bytes = AsyncMock(side_effect=StorageUnavailableError("outage"))
    with pytest.raises(StorageUnavailableError):
        await _confirm(row, gateway)
    assert await get_redis_client().get(attachment_verify.lock_key(row.id)) is None


def test_lock_outlives_the_longest_check_storage_allows() -> None:
    settings = Settings(r2_call_deadline_seconds=30.0)
    assert attachment_verify._lock_ttl_seconds(settings) > 4 * 30
