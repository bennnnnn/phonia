"""Profile photos share attachment storage without becoming Library/chat items."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.config import Settings
from app.models.orm import Attachment, User
from app.modules.account import lifecycle as account_lifecycle
from app.modules.account import service as auth
from app.modules.attachments import repository as attachments
from app.repositories import users
from app.tests.fakes import redis_mock


async def _user(session) -> User:
    return await users.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Before",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


async def _photo(session, user: User) -> Attachment:
    row = Attachment(
        id=uuid4(),
        user_id=user.id,
        storage_key=f"{user.id}/{uuid4()}",
        content_type="image/jpeg",
        size_bytes=1024,
        source="upload",
        verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC) - timedelta(days=4),
        library_visible=True,
    )
    session.add(row)
    await session.commit()
    return row


async def test_saved_photo_is_private_persistent_and_not_a_chat_attachment(db_session):
    user = await _user(db_session)
    photo = await _photo(db_session, user)
    await account_lifecycle.update_account(
        db_session,
        user,
        Settings(_env_file=None),
        {"name": "After", "avatar_url": f"/attachments/{photo.id}/file"},
    )
    user_id, photo_id = user.id, photo.id
    db_session.expire_all()
    saved = await db_session.get(User, user_id)
    assert saved.name == "After"
    assert saved.avatar_url == f"/attachments/{photo_id}/file"
    gallery, _ = await attachments.list_for_gallery(db_session, saved.id)
    assert photo_id not in {row.id for row in gallery}
    assert await attachments.get_by_id(db_session, photo_id, uuid4()) is None
    orphans = await attachments.list_orphans(db_session, older_than_hours=24)
    assert photo_id not in {row.id for row in orphans}
    assert await attachments.delete_unlinked_returning(db_session, [photo_id]) == []
    assert (
        await attachments.delete_unlinked_returning(db_session, [photo_id], orphan_only=True) == []
    )
    assert (
        await attachments.link_to_message(
            db_session, user_id=saved.id, attachment_ids=[photo_id], message_id=uuid4()
        )
        == 0
    )
    assert (
        await db_session.scalar(select(Attachment.id).where(Attachment.id == photo_id)) == photo_id
    )


async def test_replaced_photo_can_be_reaped_without_deleting_current_photo(db_session):
    user = await _user(db_session)
    first = await _photo(db_session, user)
    second = await _photo(db_session, user)
    for photo in (first, second):
        await account_lifecycle.update_account(
            db_session,
            user,
            Settings(_env_file=None),
            {"avatar_url": f"/attachments/{photo.id}/file"},
        )
    orphans = await attachments.list_orphans(db_session, older_than_hours=24)
    assert first.id in {row.id for row in orphans}
    assert second.id not in {row.id for row in orphans}
    assert await attachments.delete_unlinked_returning(
        db_session, [first.id, second.id], orphan_only=True
    ) == [first.storage_key]


async def test_profile_rejects_another_users_photo_without_partial_name_save(db_session):
    owner = await _user(db_session)
    stranger = await _user(db_session)
    photo = await _photo(db_session, owner)
    stranger_id = stranger.id
    with pytest.raises(ValueError, match="uploaded photo"):
        await account_lifecycle.update_account(
            db_session,
            stranger,
            Settings(_env_file=None),
            {"name": "Bad update", "avatar_url": f"/attachments/{photo.id}/file"},
        )
    saved = await db_session.get(User, stranger_id)
    assert saved.name == "Before"
    assert saved.avatar_url is None


@pytest.mark.parametrize("provider", ["google", "apple"])
async def test_provider_login_refreshes_profile_saved_after_identity_lookup(db_session, provider):
    user = await _user(db_session)
    photo = await _photo(db_session, user)
    avatar_url = f"/attachments/{photo.id}/file"
    # Leave the identity-map user stale, as if another request saved after
    # login's initial lookup but before its provider-field update.
    await db_session.execute(
        update(User)
        .where(User.id == user.id)
        .values(name="Saved profile name", avatar_url=avatar_url)
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    assert user.name == "Before"
    assert user.avatar_url is None
    payload = {
        "sub": "login-profile-test",
        "email": user.email,
        "name": "Provider name",
        "picture": "https://example.com/new-provider.jpg",
        "email_verified": True,
    }
    with (
        patch.object(auth, f"verify_{provider}_id_token", AsyncMock(return_value=payload)),
        patch.object(auth.users_repo, f"get_by_{provider}_sub", AsyncMock(return_value=user)),
        patch.object(auth.tokens_service, "issue_token_pair", AsyncMock(return_value=("a", "r"))),
    ):
        if provider == "google":
            result = await auth.login_with_google(
                db_session, Settings(_env_file=None), "id", redis_mock()
            )
        else:
            result = await auth.login_with_apple(
                db_session, Settings(_env_file=None), "id", redis_mock(), name="Provider name"
            )
    assert result.user.name == "Saved profile name"
    assert result.user.avatar_url == avatar_url
