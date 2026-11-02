"""Indexing reads a file only while its owner has consented to outside AI services."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.orm import Attachment
from app.modules.attachments import repository as attachments
from app.repositories import users


@pytest.mark.asyncio
@pytest.mark.parametrize("consented", [True, False])
async def test_the_index_read_needs_the_owners_consent(db_session, consented: bool) -> None:
    user = await users.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Index consent",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    # A consent withdrawn after the turn queued the file.
    user.ai_data_consent_at = datetime.now(UTC) if consented else None
    row = Attachment(
        id=uuid4(),
        user_id=user.id,
        storage_key=f"{user.id}/{uuid4()}",
        content_type="text/plain",
        size_bytes=4,
        source="upload",
        verified_at=datetime.now(UTC),
        library_visible=True,
    )
    db_session.add(row)
    await db_session.flush()

    found = await attachments.get_by_id(db_session, row.id, user.id, owner_consented=True)
    assert (found is not None) is consented
    # The plain read (the Library, a chat send) does not depend on consent.
    assert await attachments.get_by_id(db_session, row.id, user.id) is not None
