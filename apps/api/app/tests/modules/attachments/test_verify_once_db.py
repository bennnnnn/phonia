"""A confirm that waited for a peer's check reads the row the peer left, not its own copy.

The session keeps the rows it loaded (``expire_on_commit=False``), so the re-read after
the lock returned the stale, unverified row and the waiting confirm downloaded again.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.models.orm import Attachment
from app.modules.attachments import verify as attachment_verify
from app.repositories import users

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 24


@pytest.mark.asyncio
async def test_two_concurrent_confirms_download_the_upload_once(db_session: Any) -> None:
    user = await users.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Verify test",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    row = Attachment(
        id=uuid4(),
        user_id=user.id,
        storage_key=f"{user.id}/{uuid4()}",
        content_type="image/png",
        size_bytes=len(PNG),
        source="upload",
        library_visible=True,
    )
    db_session.add(row)
    await db_session.flush()

    async def slow_read(_key: str) -> bytes:
        await asyncio.sleep(0.3)
        return PNG

    async def mark_verified_elsewhere(session: Any, attachment_id: UUID, **_: Any) -> None:
        # As another process's session writes it: this session's loaded row is left as it was.
        await session.execute(
            text("UPDATE attachments SET verified_at = now() WHERE id = :id"),
            {"id": attachment_id},
        )
        await session.commit()

    gateway = MagicMock(
        object_size=AsyncMock(return_value=len(PNG)),
        read_bytes=AsyncMock(side_effect=slow_read),
        delete_bytes=AsyncMock(),
    )
    with (
        patch(
            "app.modules.attachments.repository.mark_verified",
            AsyncMock(side_effect=mark_verified_elsewhere),
        ),
        patch.object(attachment_verify, "POLL_SECONDS", 0.02),
    ):
        results = await asyncio.gather(
            *(
                attachment_verify.verify_upload_once(db_session, Settings(), gateway, row, user.id)
                for _ in range(2)
            )
        )

    assert all(result.error is None and not result.busy for result in results)
    assert gateway.read_bytes.await_count == 1
    assert gateway.object_size.await_count == 1
