"""Attachment router tests."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_settings_dep
from app.gateways.storage_gateway import (
    LocalStorageGateway,
    PresignedUpload,
    UnconfiguredStorageGateway,
)
from app.main import create_app
from app.models.orm import User
from app.services.quota import counters
from app.tests.fakes import redis_mock


def _fake_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid4()
    u.email = "test@recall.local"
    return u


def _app_with_user(user: User):
    from app.core.deps import get_current_user

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    return app


def _app_with_user_attachments_disabled(user: User):
    from app.core.deps import get_current_user

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(attachments_enabled=False)
    return app


def test_presign_upload_rejects_bad_content_type():
    user = _fake_user()
    client = TestClient(_app_with_user(user))
    r = client.post(
        "/attachments/presign",
        headers={"Authorization": "Bearer tok"},
        json={"content_type": "application/x-msdownload", "size_bytes": 100},
    )
    assert r.status_code == 400


def test_presign_upload_success():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.presign_upload = AsyncMock(
        return_value=PresignedUpload(
            attachment_id=str(attachment_id),
            upload_url=f"/attachments/{attachment_id}/upload",
            storage_key=f"{user.id}/{attachment_id}",
            headers={"Content-Type": "image/png"},
            api_upload=True,
        )
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    with (
        patch("app.modules.attachments.upload.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.upload.attachments_repo.create_pending", AsyncMock()),
        patch("app.modules.attachments.upload.get_redis_client", return_value=fake_redis),
    ):
        client = TestClient(app)
        r = client.post(
            "/attachments/presign",
            headers={"Authorization": "Bearer tok"},
            json={"content_type": "image/png", "size_bytes": 128},
        )

    assert r.status_code == 200
    assert r.json()["attachment_id"] == str(attachment_id)


def test_presign_upload_stores_sanitized_filename():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.presign_upload = AsyncMock(
        return_value=PresignedUpload(
            attachment_id=str(attachment_id),
            upload_url=f"/attachments/{attachment_id}/upload",
            storage_key=f"{user.id}/{attachment_id}",
            headers={"Content-Type": "application/pdf"},
            api_upload=True,
        )
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    create_pending = AsyncMock()

    with (
        patch("app.modules.attachments.upload.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.upload.attachments_repo.create_pending", create_pending),
        patch("app.modules.attachments.upload.get_redis_client", return_value=fake_redis),
    ):
        client = TestClient(app)
        r = client.post(
            "/attachments/presign",
            headers={"Authorization": "Bearer tok"},
            json={
                "content_type": "application/pdf",
                "size_bytes": 128,
                "filename": "folder/notes.pdf",
            },
        )

    assert r.status_code == 200
    assert create_pending.await_args.kwargs["original_filename"] == "notes.pdf"


def test_presign_upload_returns_503_when_storage_unconfigured():
    user = _fake_user()
    app = _app_with_user(user)
    fake_redis = redis_mock()
    fake_redis.incrby = AsyncMock(return_value=1)
    fake_redis.expire = AsyncMock()

    with (
        patch(
            "app.modules.attachments.upload.get_storage_gateway",
            return_value=UnconfiguredStorageGateway(),
        ),
        patch("app.modules.attachments.upload.get_redis_client", return_value=fake_redis),
    ):
        client = TestClient(app)
        r = client.post(
            "/attachments/presign",
            headers={"Authorization": "Bearer tok"},
            json={"content_type": "image/png", "size_bytes": 128},
        )

    assert r.status_code == 503
    fake_redis.incrby.assert_not_called()


def test_presign_upload_refunds_image_quota_when_presign_fails(quota_clock):
    """Storage failing after UTC midnight gives the slot back to the day it was taken."""
    user = _fake_user()
    app = _app_with_user(user)

    async def storage_down_after_midnight(**_kwargs):
        quota_clock.day = quota_clock.next_day
        raise RuntimeError("storage down")

    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.presign_upload = AsyncMock(side_effect=storage_down_after_midnight)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    with (
        patch("app.modules.attachments.upload.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.upload.get_redis_client", return_value=fake_redis),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/attachments/presign",
            headers={"Authorization": "Bearer tok"},
            json={"content_type": "image/png", "size_bytes": 128},
        )
        keys = [f"imgup:{user.id}:2026-10-{n}" for n in (16, 17)]
        assert asyncio.run(fake_redis.mget(keys)) == ["0", None]

    assert r.status_code == 500


def test_presign_upload_refunds_image_quota_when_create_pending_fails(quota_clock):
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.presign_upload = AsyncMock(
        return_value=PresignedUpload(
            attachment_id=str(attachment_id),
            upload_url=f"/attachments/{attachment_id}/upload",
            storage_key=f"{user.id}/{attachment_id}",
            headers={"Content-Type": "image/png"},
            api_upload=True,
        )
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    refund_mock = AsyncMock()

    with (
        patch("app.modules.attachments.upload.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.upload.attachments_repo.create_pending",
            AsyncMock(side_effect=RuntimeError("db error")),
        ),
        patch("app.modules.attachments.upload.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.attachments.upload.counters.refund",
            refund_mock,
        ),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/attachments/presign",
            headers={"Authorization": "Bearer tok"},
            json={"content_type": "image/png", "size_bytes": 128},
        )

    assert r.status_code == 500
    refund_mock.assert_awaited_once_with("image_upload", fake_redis, user.id, day=quota_clock.day)


def test_presign_upload_refunds_a_document_slot_when_the_row_fails():
    """A document takes a daily slot of its own, given back when the upload fails."""
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.presign_upload = AsyncMock(
        return_value=PresignedUpload(
            attachment_id=str(attachment_id),
            upload_url=f"/attachments/{attachment_id}/upload",
            storage_key=f"{user.id}/{attachment_id}",
            headers={"Content-Type": "application/pdf"},
            api_upload=True,
        )
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    refund_mock = AsyncMock()

    with (
        patch("app.modules.attachments.upload.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.upload.attachments_repo.create_pending",
            AsyncMock(side_effect=RuntimeError("db error")),
        ),
        patch("app.modules.attachments.upload.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.attachments.upload.counters.refund",
            refund_mock,
        ),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/attachments/presign",
            headers={"Authorization": "Bearer tok"},
            json={"content_type": "application/pdf", "size_bytes": 128},
        )

    assert r.status_code == 500
    refund_mock.assert_awaited_once()
    assert refund_mock.await_args.args[0] == "document_upload"


def test_cancel_pending_upload_refunds_image_quota():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    from datetime import UTC, datetime

    row = MagicMock()
    row.source = "upload"
    row.library_visible = True
    row.verified_at = None
    row.created_at = datetime.now(UTC)
    row.id = attachment_id
    from datetime import UTC, datetime

    row.message_id = None
    row.source = "upload"
    row.library_visible = True
    row.verified_at = None
    row.created_at = datetime.now(UTC)
    row.content_type = "image/png"
    row.storage_key = "user/key"

    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()
    fake_redis = redis_mock()
    refund_mock = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.upload.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.upload.attachments_repo.delete_unlinked_returning",
            AsyncMock(return_value=["user/key"]),
        ),
        patch("app.modules.attachments.lifecycle.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.upload.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.attachments.upload.counters.refund",
            refund_mock,
        ),
    ):
        client = TestClient(app)
        r = client.delete(
            f"/attachments/{attachment_id}",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 204
    refund_mock.assert_awaited_once_with("image_upload", fake_redis, user.id)


def test_confirm_storage_outage_returns_retryable_503_without_purging():
    from app.gateways.storage_gateway import StorageUnavailableError

    user = _fake_user()
    attachment_id = uuid4()
    row = MagicMock(id=attachment_id, content_type="text/plain", storage_key="u/a", size_bytes=4)
    gateway = MagicMock(read_bytes=AsyncMock(side_effect=StorageUnavailableError("outage")))
    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.content.purge_invalid_upload", AsyncMock()) as purge,
    ):
        response = TestClient(_app_with_user(user)).post(
            f"/attachments/{attachment_id}/confirm", headers={"Authorization": "Bearer tok"}
        )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    purge.assert_not_awaited()


def test_confirm_upload_rejects_spoofed_r2_bytes():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    from datetime import UTC, datetime

    row = MagicMock()
    row.source = "upload"
    row.library_visible = True
    row.verified_at = None
    row.created_at = datetime.now(UTC)
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    row.size_bytes = 128

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=b"not-a-png")
    gateway.delete_bytes = AsyncMock()
    fake_redis = redis_mock()
    refund_mock = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.workflow.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.attachments.workflow.counters.refund",
            refund_mock,
        ),
        patch(
            "app.modules.attachments.workflow.attachments_repo.delete_rows",
            AsyncMock(return_value=1),
        ) as delete_rows,
    ):
        client = TestClient(app)
        r = client.post(
            f"/attachments/{attachment_id}/confirm",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 400
    gateway.delete_bytes.assert_awaited_once_with("user/key")
    delete_rows.assert_awaited_once()
    refund_mock.assert_awaited_once_with("image_upload", fake_redis, user.id)


def test_confirm_upload_accepts_valid_r2_bytes():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"x" * 10
    row.size_bytes = len(png_bytes)  # actual bytes must match declared size

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=png_bytes)
    gateway.delete_bytes = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.repository.mark_verified",
            AsyncMock(),
        ),
    ):
        client = TestClient(app)
        r = client.post(
            f"/attachments/{attachment_id}/confirm",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 204


def test_confirm_upload_noop_for_local_backend():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id

    gateway = MagicMock(spec=LocalStorageGateway)

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(app)
        r = client.post(
            f"/attachments/{attachment_id}/confirm",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 204


def test_presign_upload_rejects_image_over_daily_limit(quota_clock):
    user = _fake_user()
    app = _app_with_user(user)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    key = f"imgup:{user.id}:2026-10-16"
    cap = counters.limit("image_upload", user, Settings())
    asyncio.run(fake_redis.set(key, cap, ex=60))

    with patch("app.modules.attachments.upload.get_redis_client", return_value=fake_redis):
        client = TestClient(app)
        r = client.post(
            "/attachments/presign",
            headers={"Authorization": "Bearer tok"},
            json={"content_type": "image/png", "size_bytes": 128},
        )
        assert asyncio.run(fake_redis.get(key)) == str(cap)

    assert r.status_code == 429


def test_upload_rejects_bytes_not_matching_claimed_content_type():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    from datetime import UTC, datetime

    row = MagicMock()
    row.source = "upload"
    row.library_visible = True
    row.verified_at = None
    row.created_at = datetime.now(UTC)
    row.verified_at = None
    row.id = attachment_id
    row.message_id = None
    row.content_type = "image/png"
    row.storage_key = f"{user.id}/{attachment_id}"
    row.size_bytes = 20
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.write_bytes = AsyncMock()
    gateway.delete_bytes = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.workflow.get_redis_client", return_value=AsyncMock()),
        patch(
            "app.modules.attachments.workflow.counters.refund",
            AsyncMock(),
        ) as refund_mock,
        patch(
            "app.modules.attachments.repository.delete_rows",
            AsyncMock(return_value=1),
        ) as delete_rows,
    ):
        client = TestClient(app)
        r = client.put(
            f"/attachments/{attachment_id}/upload",
            headers={"Authorization": "Bearer tok"},
            content=b"#!/bin/sh\nrm -rf /\n",
        )

    assert r.status_code == 400
    gateway.write_bytes.assert_not_awaited()
    delete_rows.assert_awaited_once()
    refund_mock.assert_awaited_once()


def test_upload_accepts_bytes_matching_claimed_content_type():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.verified_at = None
    row.id = attachment_id
    row.message_id = None
    row.content_type = "image/png"
    row.storage_key = f"{user.id}/{attachment_id}"
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.write_bytes = AsyncMock()

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    row.size_bytes = len(png_bytes)  # actual bytes must match declared size

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.workflow.attachments_repo.mark_verified",
            AsyncMock(),
        ) as mark_verified,
    ):
        client = TestClient(app)
        r = client.put(
            f"/attachments/{attachment_id}/upload",
            headers={"Authorization": "Bearer tok"},
            content=png_bytes,
        )

    assert r.status_code == 204
    gateway.write_bytes.assert_awaited_once()
    mark_verified.assert_awaited_once()


def test_upload_rejects_body_larger_than_declared_size_without_writing():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.verified_at = None
    row.id = attachment_id
    row.message_id = None
    row.content_type = "image/png"
    row.storage_key = f"{user.id}/{attachment_id}"
    row.size_bytes = 8
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.write_bytes = AsyncMock()
    gateway.delete_bytes = AsyncMock()

    png_prefix = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.workflow.get_redis_client", return_value=AsyncMock()),
        patch(
            "app.modules.attachments.workflow.counters.refund",
            AsyncMock(),
        ),
        patch(
            "app.modules.attachments.repository.delete_rows",
            AsyncMock(return_value=1),
        ),
    ):
        client = TestClient(app)
        r = client.put(
            f"/attachments/{attachment_id}/upload",
            headers={"Authorization": "Bearer tok"},
            content=png_prefix,
        )

    assert r.status_code == 400
    gateway.write_bytes.assert_not_awaited()


def test_serve_file_rejects_spoofed_r2_bytes():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    from datetime import UTC, datetime

    row = MagicMock()
    row.source = "upload"
    row.library_visible = True
    row.verified_at = None
    row.created_at = datetime.now(UTC)
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    row.verified_at = None

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=b"not-a-png")
    gateway.delete_bytes = AsyncMock()
    fake_redis = redis_mock()
    refund_mock = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.workflow.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.attachments.workflow.counters.refund",
            refund_mock,
        ),
        patch(
            "app.modules.attachments.workflow.attachments_repo.delete_rows",
            AsyncMock(return_value=1),
        ),
    ):
        client = TestClient(app)
        r = client.get(
            f"/attachments/{attachment_id}/file",
            headers={"Authorization": "Bearer tok"},
            follow_redirects=False,
        )

    assert r.status_code == 400
    gateway.delete_bytes.assert_awaited_once_with("user/key")
    refund_mock.assert_awaited_once_with("image_upload", fake_redis, user.id)


def test_serve_file_local_backend_sets_nosniff_header(tmp_path):
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    local_path = tmp_path / "attachment.png"
    local_path.write_bytes(png_bytes)

    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.resolve_local_path = MagicMock(return_value=local_path)

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(app)
        r = client.get(
            f"/attachments/{attachment_id}/file",
            headers={"Authorization": "Bearer tok"},
            follow_redirects=False,
        )

    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "private, max-age=86400"


def test_serve_file_missing_local_drops_row():
    """A verified row with no bytes must 404 and delete the gallery leftover."""
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    row.size_bytes = 40
    row.verified_at = datetime(2026, 8, 1)

    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.resolve_local_path = MagicMock(return_value=None)
    delete_rows = AsyncMock(return_value=1)

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.workflow.attachments_repo.delete_rows",
            delete_rows,
        ),
    ):
        client = TestClient(app)
        r = client.get(
            f"/attachments/{attachment_id}/file",
            headers={"Authorization": "Bearer tok"},
            follow_redirects=False,
        )

    assert r.status_code == 404
    assert r.json()["detail"]["message"] == "File missing"
    delete_rows.assert_awaited_once()


def test_serve_file_r2_redirect_sets_nosniff_header():
    """R2/S3 redirect responses must carry X-Content-Type-Options: nosniff as
    defense-in-depth (the local-backend path already sets it on FileResponse)."""
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    row.size_bytes = 40
    row.verified_at = None

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=png_bytes)
    gateway.delete_bytes = AsyncMock()
    gateway.presign_download = AsyncMock(return_value="https://r2.example/signed")

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.repository.mark_verified",
            AsyncMock(),
        ),
    ):
        client = TestClient(app)
        r = client.get(
            f"/attachments/{attachment_id}/file",
            headers={"Authorization": "Bearer tok"},
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["location"] == "https://r2.example/signed"


def test_upload_rejects_size_mismatch_with_declared_size():
    """PUT /upload must reject when actual bytes != row.size_bytes (declared at presign)."""
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    from datetime import UTC, datetime

    row = MagicMock()
    row.source = "upload"
    row.library_visible = True
    row.verified_at = None
    row.created_at = datetime.now(UTC)
    row.verified_at = None
    row.id = attachment_id
    row.message_id = None
    row.content_type = "image/png"
    row.storage_key = f"{user.id}/{attachment_id}"
    row.size_bytes = 128  # declared 128
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.write_bytes = AsyncMock()
    gateway.delete_bytes = AsyncMock()

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # actual 40, declared 128

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.workflow.get_redis_client", return_value=AsyncMock()),
        patch(
            "app.modules.attachments.workflow.counters.refund",
            AsyncMock(),
        ) as refund_mock,
        patch(
            "app.modules.attachments.repository.delete_rows",
            AsyncMock(return_value=1),
        ) as delete_rows,
    ):
        client = TestClient(app)
        r = client.put(
            f"/attachments/{attachment_id}/upload",
            headers={"Authorization": "Bearer tok"},
            content=png_bytes,
        )

    assert r.status_code == 400
    assert "size" in r.json()["detail"]["message"].lower()
    gateway.write_bytes.assert_not_awaited()
    delete_rows.assert_awaited_once()
    refund_mock.assert_awaited_once()


def test_download_url_rejects_spoofed_r2_bytes():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    from datetime import UTC, datetime

    row = MagicMock()
    row.source = "upload"
    row.library_visible = True
    row.verified_at = None
    row.created_at = datetime.now(UTC)
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    row.verified_at = None

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=b"not-a-png")
    gateway.delete_bytes = AsyncMock()
    fake_redis = redis_mock()
    refund_mock = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.workflow.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.attachments.workflow.counters.refund",
            refund_mock,
        ),
        patch(
            "app.modules.attachments.workflow.attachments_repo.delete_rows",
            AsyncMock(return_value=1),
        ),
    ):
        client = TestClient(app)
        r = client.get(
            f"/attachments/{attachment_id}/url",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 400
    gateway.delete_bytes.assert_awaited_once_with("user/key")
    refund_mock.assert_awaited_once_with("image_upload", fake_redis, user.id)


def test_download_url_local_backend():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id
    row.content_type = "image/png"
    row.size_bytes = 128
    row.storage_key = "key"
    row.created_at = datetime(2024, 1, 1)
    row.original_filename = "lease-notes.png"

    gateway = MagicMock(spec=LocalStorageGateway)

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(app)
        r = client.get(
            f"/attachments/{attachment_id}/url",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 200
    assert r.json()["download_url"] == f"/attachments/{attachment_id}/file"
    assert r.json()["indexed"] is True
    # The phone names a reopened file from this; its message holds only the link.
    assert r.json()["original_filename"] == "lease-notes.png"


def test_upload_accepts_docx_bytes_matching_claimed_type():
    import io
    import zipfile

    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.verified_at = None
    row.id = attachment_id
    row.message_id = None
    row.content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    row.storage_key = f"{user.id}/{attachment_id}"
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.write_bytes = AsyncMock()
    docx_buf = io.BytesIO()
    with zipfile.ZipFile(docx_buf, "w") as archive:
        archive.writestr("word/document.xml", "<content/>")
        archive.writestr("[Content_Types].xml", "<content/>")
    docx_bytes = docx_buf.getvalue()
    row.size_bytes = len(docx_bytes)  # actual bytes must match declared size

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.workflow.attachments_repo.mark_verified", AsyncMock()),
    ):
        client = TestClient(app)
        r = client.put(
            f"/attachments/{attachment_id}/upload",
            headers={"Authorization": "Bearer tok"},
            content=docx_bytes,
        )

    assert r.status_code == 204
    gateway.write_bytes.assert_awaited_once()


def test_upload_rejects_already_linked_attachment():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.verified_at = None
    row.id = attachment_id
    row.message_id = uuid4()
    row.content_type = "image/png"
    row.storage_key = f"{user.id}/{attachment_id}"
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.write_bytes = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(app)
        r = client.put(
            f"/attachments/{attachment_id}/upload",
            headers={"Authorization": "Bearer tok"},
            content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        )

    assert r.status_code == 409
    gateway.write_bytes.assert_not_awaited()


def test_upload_r2_backend_returns_501_before_refund():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.verified_at = None
    row.id = attachment_id
    row.message_id = None
    row.content_type = "image/png"
    row.size_bytes = 4
    gateway = MagicMock()
    refund_mock = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.workflow.counters.refund",
            refund_mock,
        ),
    ):
        client = TestClient(app)
        r = client.put(
            f"/attachments/{attachment_id}/upload",
            headers={"Authorization": "Bearer tok"},
            content=b"nope",
        )

    assert r.status_code == 501
    refund_mock.assert_not_awaited()


def test_serve_file_skips_download_when_already_verified():
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    row.size_bytes = 40
    row.verified_at = datetime(2026, 8, 1)

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock()
    gateway.presign_download = AsyncMock(return_value="https://r2.example/signed")

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(app)
        r = client.get(
            f"/attachments/{attachment_id}/file",
            headers={"Authorization": "Bearer tok"},
            follow_redirects=False,
        )

    assert r.status_code == 302
    gateway.read_bytes.assert_not_awaited()
    gateway.presign_download.assert_awaited_once()


# ── attachments_enabled feature-flag guard ────────────────────────────────────


def test_presign_rejected_when_attachments_disabled():
    user = _fake_user()
    app = _app_with_user_attachments_disabled(user)
    client = TestClient(app)
    r = client.post(
        "/attachments/presign",
        headers={"Authorization": "Bearer tok"},
        json={"content_type": "image/png", "size_bytes": 128},
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "Attachments are disabled"


def test_upload_rejected_when_attachments_disabled():
    user = _fake_user()
    app = _app_with_user_attachments_disabled(user)
    attachment_id = uuid4()
    client = TestClient(app)
    r = client.put(
        f"/attachments/{attachment_id}/upload",
        headers={"Authorization": "Bearer tok"},
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "Attachments are disabled"


def test_confirm_rejected_when_attachments_disabled():
    user = _fake_user()
    app = _app_with_user_attachments_disabled(user)
    attachment_id = uuid4()
    client = TestClient(app)
    r = client.post(
        f"/attachments/{attachment_id}/confirm",
        headers={"Authorization": "Bearer tok"},
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "Attachments are disabled"


def test_cancel_still_allowed_when_attachments_disabled():
    """Cancel (delete) and read endpoints stay open when the flag is off so
    pending uploads can be cleaned up and existing attachments retrieved after
    a flag flip."""
    user = _fake_user()
    app = _app_with_user_attachments_disabled(user)
    attachment_id = uuid4()
    row = MagicMock()
    row.id = attachment_id
    row.message_id = None
    row.content_type = "image/png"
    row.storage_key = "user/key"
    gateway = MagicMock()
    gateway.delete_bytes = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.upload.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.upload.attachments_repo.delete_unlinked_returning",
            AsyncMock(return_value=["user/key"]),
        ),
        patch("app.modules.attachments.upload.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.upload.get_redis_client", return_value=AsyncMock()),
        patch(
            "app.modules.attachments.upload.counters.refund",
            AsyncMock(),
        ),
    ):
        client = TestClient(app)
        r = client.delete(
            f"/attachments/{attachment_id}",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 204


# --- GET /attachments (gallery list) ---


def _attachment_row(
    *,
    attachment_id=None,
    content_type="image/png",
    size_bytes=1024,
    source="generated",
    storage_key="user/key",
    created_at=None,
):
    row = MagicMock()
    row.id = attachment_id or uuid4()
    row.content_type = content_type
    row.size_bytes = size_bytes
    row.source = source
    row.storage_key = storage_key
    row.created_at = created_at or datetime(2026, 1, 1, 12, 0, 0)
    row.verified_at = datetime(2026, 1, 1, 12, 0, 0)
    row.message_id = None
    row.original_filename = None
    return row


def test_list_attachments_returns_images():
    """GET /attachments returns image attachments with download URLs."""
    user = _fake_user()
    row1 = _attachment_row(source="generated")
    row2 = _attachment_row(source="upload")
    gateway = MagicMock()
    gateway.presign_download = AsyncMock(side_effect=["url1", "url2"])

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.list_for_gallery",
            AsyncMock(return_value=([row1, row2], None)),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(_app_with_user(user))
        r = client.get("/attachments", headers={"Authorization": "Bearer tok"})

    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is None
    assert body["items"][0]["source"] == "generated"
    assert body["items"][0]["download_url"] == f"/attachments/{row1.id}/file"
    assert body["items"][1]["source"] == "upload"
    gateway.presign_download.assert_not_called()
    assert body["items"][0]["chat_id"] is None


def test_list_attachments_includes_chat_id():
    """Linked attachments expose the originating chat for Open chat."""
    user = _fake_user()
    message_id = uuid4()
    chat_id = uuid4()
    row = _attachment_row(source="generated")
    row.message_id = message_id
    gateway = MagicMock()
    gateway.presign_download = AsyncMock(return_value="url1")

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.list_for_gallery",
            AsyncMock(return_value=([row], None)),
        ),
        patch(
            "app.modules.attachments.workflow.attachments_repo.chat_meta_for_message_ids",
            AsyncMock(return_value={message_id: (chat_id, "Trip")}),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(_app_with_user(user))
        r = client.get("/attachments", headers={"Authorization": "Bearer tok"})

    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["chat_id"] == str(chat_id)
    assert item["message_id"] == str(message_id)
    assert item["chat_title"] == "Trip"


def test_list_attachments_source_filter():
    """GET /attachments?source=generated is forwarded to the gallery query."""
    user = _fake_user()
    row = _attachment_row(source="generated")
    gateway = MagicMock()
    gateway.presign_download = AsyncMock(return_value="url1")
    mock_list = AsyncMock(return_value=([row], None))
    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.list_for_gallery",
            mock_list,
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(_app_with_user(user))
        r = client.get(
            "/attachments?category=images&source=generated",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 200
    _, kwargs = mock_list.call_args
    assert kwargs.get("category") == "images"
    assert kwargs.get("source") == "generated"


def test_list_attachments_passes_the_cursor_and_returns_the_next():
    """GET /attachments?cursor=… reads the next page; the answer says where the one after starts."""
    user = _fake_user()
    row = _attachment_row(source="upload")
    mock_list = AsyncMock(return_value=([row], "next-page"))
    with (
        patch("app.modules.attachments.workflow.attachments_repo.list_for_gallery", mock_list),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=MagicMock()),
    ):
        client = TestClient(_app_with_user(user))
        r = client.get("/attachments?cursor=this-page", headers={"Authorization": "Bearer tok"})

    assert r.status_code == 200
    assert r.json()["next_cursor"] == "next-page"
    assert mock_list.call_args.kwargs["cursor"] == "this-page"


def test_list_attachments_refuses_a_cursor_it_did_not_write():
    user = _fake_user()
    client = TestClient(_app_with_user(user))
    r = client.get("/attachments?cursor=not-ours", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_cursor"


def test_list_attachments_rejects_search_source():
    """Lookup photos are chat-only; Library cannot filter to source=search."""
    user = _fake_user()
    client = TestClient(_app_with_user(user))
    r = client.get(
        "/attachments?source=search",
        headers={"Authorization": "Bearer tok"},
    )
    assert r.status_code == 422


def test_list_attachments_q_filter():
    """GET /attachments?q= is forwarded after stripping."""
    user = _fake_user()
    row = _attachment_row()
    gateway = MagicMock()
    gateway.presign_download = AsyncMock(return_value="url1")
    mock_list = AsyncMock(return_value=([row], None))
    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.list_for_gallery",
            mock_list,
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(_app_with_user(user))
        r = client.get(
            "/attachments?q=%20cat%20",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 200
    _, kwargs = mock_list.call_args
    assert kwargs.get("q") == "cat"


def test_list_attachments_category_filter():
    """GET /attachments?category=files filters to non-image attachments."""
    user = _fake_user()
    row = _attachment_row(content_type="application/pdf", source="upload")
    gateway = MagicMock()
    gateway.presign_download = AsyncMock(return_value="url1")

    mock_list = AsyncMock(return_value=([row], None))
    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.list_for_gallery",
            mock_list,
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(_app_with_user(user))
        r = client.get(
            "/attachments?category=files",
            headers={"Authorization": "Bearer tok"},
        )

    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    _, kwargs = mock_list.call_args
    assert kwargs.get("category") == "files"


def test_list_attachments_local_backend():
    """Local storage backend returns /attachments/{id}/file as download_url."""
    user = _fake_user()
    row = _attachment_row()
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.resolve_local_path.return_value = Path("/recall-present.png")

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.list_for_gallery",
            AsyncMock(return_value=([row], None)),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(_app_with_user(user))
        r = client.get("/attachments", headers={"Authorization": "Bearer tok"})

    assert r.status_code == 200
    assert r.json()["items"][0]["download_url"] == f"/attachments/{row.id}/file"


def test_list_attachments_omits_local_rows_whose_blob_is_gone():
    """Gallery listed Neon rows whose /tmp blobs were gone, then each /file 404'd."""
    user = _fake_user()
    gone = _attachment_row()
    gone.storage_key = "user/gone"
    present = _attachment_row()
    present.storage_key = "user/present"
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.resolve_local_path.side_effect = lambda key: (
        None if key == "user/gone" else Path("/recall-present.png")
    )
    delete_rows = AsyncMock(return_value=1)

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.list_for_gallery",
            AsyncMock(return_value=([gone, present], None)),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.workflow.attachments_repo.delete_rows",
            delete_rows,
        ),
    ):
        client = TestClient(_app_with_user(user))
        r = client.get("/attachments", headers={"Authorization": "Bearer tok"})

    assert r.status_code == 200
    items = r.json()["items"]
    assert [item["id"] for item in items] == [str(present.id)]
    delete_rows.assert_awaited_once()
    assert delete_rows.await_args.args[1] == [gone.id]


def test_list_attachments_empty():
    """GET /attachments returns empty list when user has no images."""
    user = _fake_user()
    gateway = MagicMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.list_for_gallery",
            AsyncMock(return_value=([], None)),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
    ):
        client = TestClient(_app_with_user(user))
        r = client.get("/attachments", headers={"Authorization": "Bearer tok"})

    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["next_cursor"] is None


def test_put_upload_empty_body_purges_row_and_refunds_quota():
    """An empty PUT body must purge the DB row and refund image quota —
    previously it returned 400 without cleanup, leaving an orphaned row until
    the 24h reaper and consuming a daily image slot forever."""
    user = _fake_user()
    app = _app_with_user(user)
    attachment_id = uuid4()
    from datetime import UTC, datetime

    row = MagicMock()
    row.source = "upload"
    row.library_visible = True
    row.verified_at = None
    row.created_at = datetime.now(UTC)
    row.verified_at = None
    row.id = attachment_id
    row.message_id = None
    row.content_type = "image/png"
    row.storage_key = f"{user.id}/{attachment_id}"
    row.size_bytes = 128
    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.delete_bytes = AsyncMock()

    with (
        patch(
            "app.modules.attachments.workflow.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch("app.modules.attachments.workflow.get_storage_gateway", return_value=gateway),
        patch("app.modules.attachments.workflow.get_redis_client", return_value=AsyncMock()),
        patch(
            "app.modules.attachments.workflow.counters.refund",
            AsyncMock(),
        ) as refund_mock,
        patch(
            "app.modules.attachments.repository.delete_rows",
            AsyncMock(return_value=1),
        ) as delete_rows,
    ):
        client = TestClient(app)
        r = client.put(
            f"/attachments/{attachment_id}/upload",
            headers={"Authorization": "Bearer tok"},
            content=b"",
        )

    assert r.status_code == 400
    assert "size" in r.json()["detail"]["message"].lower()
    gateway.delete_bytes.assert_awaited_once()
    delete_rows.assert_awaited_once()
    refund_mock.assert_awaited_once()


def test_presign_rejects_legacy_doc():
    """Legacy .doc (application/msword) must be rejected at presign — it has
    no pure-Python parser, so allowing it produces unusable uploads with no RAG."""
    user = _fake_user()
    client = TestClient(_app_with_user(user))
    r = client.post(
        "/attachments/presign",
        headers={"Authorization": "Bearer tok"},
        json={"content_type": "application/msword", "size_bytes": 100},
    )
    assert r.status_code == 400
