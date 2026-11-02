"""The local upload reads its body before it locks the row (no lock held while streaming)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways.storage_gateway import LocalStorageGateway
from app.modules.attachments import workflow as attachment_workflow
from app.tests.fakes import fake_session, make_user

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 24


def _row(*, verified: bool = False, linked: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        storage_key="u/pending",
        size_bytes=len(PNG),
        content_type="image/png",
        source="upload",
        library_visible=True,
        verified_at=datetime.now(UTC) if verified else None,
        created_at=datetime.now(UTC),
        message_id=uuid4() if linked else None,
    )


async def _store(row: Any, tmp_path: Path, events: list[str], **repo: Any) -> None:
    async def stream() -> AsyncIterator[bytes]:
        events.append("body read")
        yield PNG

    async def get_by_id(*_args: Any, for_update: bool = False, **_kwargs: Any) -> Any:
        events.append("row locked" if for_update else "row read")
        return row

    session = fake_session(commit=AsyncMock(side_effect=lambda: events.append("commit")))
    with (
        patch.object(attachment_workflow.attachments_repo, "get_by_id", get_by_id),
        patch.object(
            attachment_workflow.attachments_repo,
            "mark_verified",
            repo.get("mark_verified", AsyncMock()),
        ),
        patch.object(
            attachment_workflow,
            "get_storage_gateway",
            return_value=LocalStorageGateway(tmp_path),
        ),
    ):
        await attachment_workflow.store_local_upload(
            session, Settings(), make_user(), row.id, stream()
        )


@pytest.mark.asyncio
async def test_local_upload_streams_the_body_before_taking_the_row_lock(tmp_path: Path) -> None:
    events: list[str] = []
    mark_verified = AsyncMock()
    await _store(_row(), tmp_path, events, mark_verified=mark_verified)
    # The first read's transaction ends before the body; the lock comes after it.
    assert events == ["row read", "commit", "body read", "row locked"]
    assert (tmp_path / "u" / "pending").read_bytes() == PNG
    mark_verified.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_upload_to_a_linked_row_is_refused_before_the_body(tmp_path: Path) -> None:
    events: list[str] = []
    with pytest.raises(attachment_workflow.AttachmentWorkflowError) as refused:
        await _store(_row(linked=True), tmp_path, events)
    assert refused.value.status_code == 409
    assert "body read" not in events


@pytest.mark.asyncio
async def test_local_upload_rechecks_the_row_under_the_lock(tmp_path: Path) -> None:
    """A row another upload verified meanwhile is not written twice."""
    first = _row()
    verified = SimpleNamespace(**{**vars(first), "verified_at": datetime.now(UTC)})
    calls = iter([first, verified])

    async def get_by_id(*_args: Any, **_kwargs: Any) -> Any:
        return next(calls)

    async def stream() -> AsyncIterator[bytes]:
        yield PNG

    gateway = LocalStorageGateway(tmp_path)
    await gateway.write_bytes("u/pending", PNG)
    mark_verified = AsyncMock()
    with (
        patch.object(attachment_workflow.attachments_repo, "get_by_id", get_by_id),
        patch.object(attachment_workflow.attachments_repo, "mark_verified", mark_verified),
        patch.object(attachment_workflow, "get_storage_gateway", return_value=gateway),
    ):
        # Same bytes as the stored upload: an idempotent retry, not an error.
        await attachment_workflow.store_local_upload(
            fake_session(), Settings(), make_user(), first.id, stream()
        )
    mark_verified.assert_not_awaited()
