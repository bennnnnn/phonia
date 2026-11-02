"""Image generation router tests."""

import asyncio
from datetime import datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_settings_dep
from app.gateways.storage_gateway import LocalStorageGateway, PresignedUpload
from app.main import create_app
from app.models.orm import Chat, Message, User
from app.modules.conversation import messages_repository
from app.modules.images import api as images_api
from app.modules.images.schemas import ImageGenerateIn


def _fake_user(*, plan: str = "pro") -> User:
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "test@recall.local"
    user.plan = plan
    return user


def _app_with_user(user: User, *, settings: Settings | None = None):
    from app.core.deps import get_current_user

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: settings or Settings()
    return app


def test_generate_image_refused_when_the_plan_has_none():
    user = _fake_user(plan="free")
    client = TestClient(_app_with_user(user, settings=Settings(daily_image_generations=0)))
    r = client.post(
        "/images/generate",
        headers={"Authorization": "Bearer tok"},
        json={"chat_id": str(uuid4()), "prompt": "a cat"},
    )
    assert r.status_code == 403


@pytest.mark.parametrize("plan, cap", [("free", 3), ("plus", 10), ("pro", 15)])
def test_generate_image_stops_at_each_plans_daily_cap(quota_clock, plan, cap):
    """Free gets a few a day; the endpoint enforces each plan's number."""
    user = _fake_user(plan=plan)
    app = _app_with_user(user, settings=Settings())
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    asyncio.run(fake_redis.set(f"imggen:{user.id}:2026-10-16", cap, ex=60))
    with (
        patch("app.modules.images.generation.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.images.generation.history.get_chat",
            AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.modules.images.generation.quota_service.global_spend_exceeded",
            AsyncMock(return_value=False),
        ),
    ):
        client = TestClient(app)
        r = client.post(
            "/images/generate",
            headers={"Authorization": "Bearer tok"},
            json={"chat_id": str(uuid4()), "prompt": "a cat"},
        )
    assert r.status_code == 429
    assert ("Upgrade" in r.json()["detail"]["message"]) is (plan == "free")


def test_generate_image_quota_exhausted(quota_clock):
    user = _fake_user(plan="pro")
    app = _app_with_user(user, settings=Settings(daily_image_generations_pro=1))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    asyncio.run(fake_redis.set(f"imggen:{user.id}:2026-10-16", 1, ex=60))

    with (
        patch("app.modules.images.generation.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.images.generation.history.get_chat",
            AsyncMock(return_value=MagicMock()),
        ),
    ):
        client = TestClient(app)
        r = client.post(
            "/images/generate",
            headers={"Authorization": "Bearer tok"},
            json={"chat_id": str(uuid4()), "prompt": "a cat"},
        )
    assert r.status_code == 429


def test_generate_image_rejects_oversized_result(quota_clock):
    """BUG FIX: last-line-of-defense size check, matching the
    presign + actual-bytes double-check every normal attachment upload gets."""
    from app.modules.attachments.content import MAX_ATTACHMENT_SIZE

    user = _fake_user(plan="pro")
    chat_id = uuid4()
    app = _app_with_user(user)

    chat = MagicMock(spec=Chat)
    chat.id = chat_id

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * MAX_ATTACHMENT_SIZE

    with (
        patch("app.modules.images.generation.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.images.generation.history.get_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.modules.images.generation.generate_image",
            AsyncMock(return_value=(oversized, "image/png")),
        ),
    ):
        client = TestClient(app)
        r = client.post(
            "/images/generate",
            headers={"Authorization": "Bearer tok"},
            json={"chat_id": str(chat_id), "prompt": "a cat"},
        )
        # Reserved on entry, refunded after the size check rejects it.
        assert asyncio.run(fake_redis.get(f"imggen:{user.id}:2026-10-16")) == "0"
    assert r.status_code == 502


def test_generate_image_success():
    user = _fake_user(plan="pro")
    chat_id = uuid4()
    attachment_id = uuid4()
    app = _app_with_user(user)

    chat = MagicMock(spec=Chat)
    chat.id = chat_id

    user_msg = MagicMock(spec=Message)
    user_msg.id = uuid4()
    user_msg.role = "user"
    user_msg.content = "Generate image: a cat"
    user_msg.model = None
    user_msg.feedback = None
    user_msg.completion = None
    user_msg.created_at = datetime.now()

    assistant_msg = MagicMock(spec=Message)
    assistant_msg.id = uuid4()
    assistant_msg.role = "assistant"
    assistant_msg.content = f"[Image: /attachments/{attachment_id}/file]"
    assistant_msg.model = "image-gen-model"
    assistant_msg.feedback = None
    assistant_msg.completion = None
    assistant_msg.created_at = datetime.now()

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
    gateway.write_bytes = AsyncMock()
    gateway.delete_bytes = AsyncMock()
    add_image = AsyncMock()

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    fake_session = AsyncMock()

    async def _get_db():
        yield fake_session

    from app.core.db import get_db

    app.dependency_overrides[get_db] = _get_db

    with (
        patch("app.modules.images.generation.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.images.generation.history.get_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.modules.images.generation.generate_image",
            AsyncMock(return_value=(b"\x89PNG\r\n", "image/png")),
        ),
        patch("app.modules.images.generation.get_storage_gateway", return_value=gateway),
        patch("app.modules.images.generation.attachments_service.add_server_images", add_image),
        patch.object(
            messages_repository,
            "create",
            AsyncMock(side_effect=[user_msg, assistant_msg]),
        ),
        patch("app.modules.images.generation.bytes_match_claimed", return_value=True),
    ):
        client = TestClient(app)
        r = client.post(
            "/images/generate",
            headers={"Authorization": "Bearer tok"},
            json={"chat_id": str(chat_id), "prompt": "a cat"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    assert "/attachments/" in body["assistant_message"]["content"]
    gateway.write_bytes.assert_awaited_once()
    gateway.delete_bytes.assert_not_called()
    added = add_image.await_args.kwargs
    assert [image.attachment_id for image in added["images"]] == [attachment_id]
    assert (added["label"], added["message_id"]) == ("a cat", assistant_msg.id)


def test_generate_image_passes_original_user_message():
    user = _fake_user(plan="pro")
    chat_id = uuid4()
    app = _app_with_user(user)

    user_msg = MagicMock(spec=Message)
    user_msg.id = uuid4()
    user_msg.role = "user"
    user_msg.content = "create a cat image"
    user_msg.model = None
    user_msg.feedback = None
    user_msg.completion = None
    user_msg.created_at = datetime.now()

    assistant_msg = MagicMock(spec=Message)
    assistant_msg.id = uuid4()
    assistant_msg.role = "assistant"
    assistant_msg.content = "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]"
    assistant_msg.model = "image-gen-model"
    assistant_msg.feedback = None
    assistant_msg.completion = None
    assistant_msg.created_at = datetime.now()

    generate = AsyncMock(return_value=(user_msg, assistant_msg))
    with patch(
        "app.modules.images.api.image_generation_service.generate_for_chat",
        generate,
    ):
        client = TestClient(app)
        r = client.post(
            "/images/generate",
            headers={"Authorization": "Bearer tok"},
            json={
                "chat_id": str(chat_id),
                "prompt": "cat",
                "user_message": "create a cat image",
            },
        )

    assert r.status_code == 200
    assert r.json()["user_message"]["content"] == "create a cat image"
    assert generate.await_args.kwargs["prompt"] == "cat"
    assert generate.await_args.kwargs["user_message_content"] == "create a cat image"


def test_generate_image_deletes_storage_when_persist_fails(quota_clock):
    """A write with no attachment row leaks forever — rollback the object."""
    user = _fake_user(plan="pro")
    chat_id = uuid4()
    attachment_id = uuid4()
    storage_key = f"{user.id}/{attachment_id}"
    app = _app_with_user(user)

    chat = MagicMock(spec=Chat)
    chat.id = chat_id

    gateway = MagicMock(spec=LocalStorageGateway)
    gateway.presign_upload = AsyncMock(
        return_value=PresignedUpload(
            attachment_id=str(attachment_id),
            upload_url=f"/attachments/{attachment_id}/upload",
            storage_key=storage_key,
            headers={"Content-Type": "image/png"},
            api_upload=True,
        )
    )
    gateway.write_bytes = AsyncMock()
    gateway.delete_bytes = AsyncMock()

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    with (
        patch("app.modules.images.generation.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.images.generation.history.get_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.modules.images.generation.generate_image",
            AsyncMock(return_value=(b"\x89PNG\r\n", "image/png")),
        ),
        patch("app.modules.images.generation.get_storage_gateway", return_value=gateway),
        patch.object(
            messages_repository,
            "create",
            AsyncMock(side_effect=RuntimeError("db down")),
        ),
        patch("app.modules.images.generation.bytes_match_claimed", return_value=True),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/images/generate",
            headers={"Authorization": "Bearer tok"},
            json={"chat_id": str(chat_id), "prompt": "a cat"},
        )
        # Reserved once, refunded after persist fail.
        assert asyncio.run(fake_redis.get(f"imggen:{user.id}:2026-10-16")) == "0"
    assert r.status_code == 500
    gateway.write_bytes.assert_awaited_once_with(storage_key, b"\x89PNG\r\n")
    gateway.delete_bytes.assert_awaited_once_with(storage_key)


async def test_generate_image_stops_the_work_when_the_phone_cancels():
    """The phone's Cancel closes the request: the generation is cancelled, which gives
    the day's slot back and deletes anything stored (test_generate_for_chat)."""
    stopped = asyncio.Event()

    async def slow(*_args, **_kwargs):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            stopped.set()
            raise

    class Gone:
        async def is_disconnected(self) -> bool:
            return True

    with patch.object(images_api.image_generation_service, "generate_for_chat", slow):
        response = await images_api.generate_image(
            ImageGenerateIn(chat_id=uuid4(), prompt="a cat"),
            request=cast(Request, Gone()),
            user=_fake_user(),
            settings=Settings(),
        )

    assert response.status_code == 499
    assert stopped.is_set()
