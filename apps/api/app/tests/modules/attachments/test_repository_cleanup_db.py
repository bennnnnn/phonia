"""Cleanup predicates must protect rows that changed after the reaper's snapshot."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.orm import Attachment
from app.modules.attachments import repository as attachments
from app.repositories import users


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verified,visible,linked,removed",
    [
        (False, True, False, True),  # an upload that never finished
        (True, True, True, False),  # a Library item whose chat was deleted
        (True, True, False, True),  # confirmed, but no message ever linked it
        (True, False, True, True),  # a hidden send-clone whose chat is gone
    ],
)
async def test_reaper_rechecks_current_library_state(
    db_session, verified, visible, linked, removed
):
    user = await users.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Cleanup test",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    row = Attachment(
        id=uuid4(),
        user_id=user.id,
        storage_key=f"{user.id}/{uuid4()}",
        content_type="text/plain",
        size_bytes=4,
        source="upload",
        verified_at=datetime.now(UTC) if verified else None,
        linked_at=datetime.now(UTC) if linked else None,
        library_visible=visible,
    )
    db_session.add(row)
    await db_session.flush()
    result = await attachments.delete_unlinked_returning(db_session, [row.id], orphan_only=True)
    assert result == ([row.storage_key] if removed else [])
    assert (
        await db_session.scalar(select(Attachment.id).where(Attachment.id == row.id)) is None
    ) is removed
