"""A Library keeps at most its plan's total bytes: checked at presign, before any slot is taken."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest

from app.core.config import Settings
from app.models.orm import Attachment
from app.modules.attachments import storage_quota
from app.modules.attachments import upload as attachment_upload
from app.modules.billing.entitlements import allowance
from app.repositories import users
from app.services.quota import counters
from app.tests.fakes import fake_session, make_user

MIB = 1024**2
GIB = 1024**3


def _user(plan: str = "free") -> Any:
    return make_user(plan=plan)


@pytest.mark.parametrize("plan, total", [("free", 400 * MIB), ("plus", GIB), ("pro", 4 * GIB)])
def test_each_plan_has_a_library_total(plan: str, total: int) -> None:
    assert allowance(_user(plan), "library_storage_bytes", Settings()) == total


async def _presign(user: Any, *, stored: int, size: int) -> AsyncMock:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    gateway = MagicMock()
    gateway.presign_upload = AsyncMock(side_effect=RuntimeError("stop after the checks"))
    with (
        patch.object(storage_quota, "stored_bytes", AsyncMock(return_value=stored)),
        patch.object(attachment_upload, "get_storage_gateway", return_value=gateway),
        patch.object(attachment_upload, "get_redis_client", return_value=redis),
    ):
        try:
            await attachment_upload.create_presigned_upload(
                fake_session(), Settings(), user=user, content_type="image/png", size_bytes=size
            )
        except RuntimeError:
            pass
    return gateway.presign_upload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan, stored, size, room",
    [
        ("free", 0, 1024, True),
        ("free", 400 * MIB - 1024, 1024, True),
        ("free", 400 * MIB - 1024, 1025, False),
        ("free", GIB, 1, False),
        ("plus", 500 * MIB, 1024, True),
        ("plus", GIB, 1, False),
        ("pro", 3 * GIB, 1024, True),
        ("pro", 4 * GIB, 1, False),
    ],
)
async def test_presign_checks_the_library_total(
    plan: str, stored: int, size: int, room: bool
) -> None:
    user = _user(plan)
    if room:
        presign = await _presign(user, stored=stored, size=size)
        presign.assert_awaited_once()
        return
    with pytest.raises(attachment_upload.AttachmentUploadError) as refused:
        await _presign(user, stored=stored, size=size)
    assert refused.value.code == "storage_full"
    assert refused.value.status_code == 409


@pytest.mark.asyncio
async def test_a_full_library_takes_no_daily_upload_slot() -> None:
    user = _user()
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch.object(storage_quota, "stored_bytes", AsyncMock(return_value=GIB)),
        patch.object(attachment_upload, "get_redis_client", return_value=redis),
        pytest.raises(attachment_upload.AttachmentUploadError),
    ):
        await attachment_upload.create_presigned_upload(
            fake_session(), Settings(), user=user, content_type="image/png", size_bytes=10
        )
    assert await redis.get(counters.daily_key("imgup", user.id)) is None


@pytest.mark.parametrize("plan, upgrade", [("free", True), ("plus", False), ("pro", False)])
def test_the_full_library_message_offers_an_upgrade_only_on_free(plan: str, upgrade: bool) -> None:
    assert ("upgrade" in storage_quota.storage_full_message(_user(plan))) is upgrade


@pytest.mark.asyncio
async def test_stored_bytes_sums_every_row_of_the_user_only(db_session) -> None:
    async def make_user() -> Any:
        return await users.create(
            db_session,
            email=f"{uuid4()}@example.com",
            name="Library total",
            avatar_url=None,
            google_sub=str(uuid4()),
        )

    owner, other = await make_user(), await make_user()
    assert await storage_quota.stored_bytes(db_session, owner.id) == 0
    rows = [
        # A Library upload, a pending upload, a resend's hidden copy, a reference photo.
        (owner.id, 1_000, "upload", True, datetime.now(UTC)),
        (owner.id, 2_000, "upload", True, None),
        (owner.id, 3_000, "upload", False, datetime.now(UTC)),
        (owner.id, 4_000, "search", True, datetime.now(UTC)),
        (other.id, 9_999, "upload", True, datetime.now(UTC)),
    ]
    for user_id, size, source, visible, verified_at in rows:
        db_session.add(
            Attachment(
                id=uuid4(),
                user_id=user_id,
                storage_key=f"{user_id}/{uuid4()}",
                content_type="image/png",
                size_bytes=size,
                source=source,
                library_visible=visible,
                verified_at=verified_at,
            )
        )
    await db_session.flush()
    assert await storage_quota.stored_bytes(db_session, owner.id) == 10_000
    assert await storage_quota.stored_bytes(db_session, other.id) == 9_999
