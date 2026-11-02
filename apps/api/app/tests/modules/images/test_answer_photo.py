"""A real photo above an answer: the search starts while the reply streams."""

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways.image_search_gateway import ImageSearchHit
from app.gateways.storage_gateway import PresignedUpload, UnconfiguredStorageGateway
from app.modules.images import answer_photo
from app.modules.images.answer_photo import AnswerPhoto, strip_photo_fences
from app.modules.images.search import photos_for_answer

PHOTO_ID = uuid4()
REPLY = "```photo\nEthiopia location map\n```\n\nEthiopia lies in the Horn of Africa."


def _photo(found=None):
    finder = AsyncMock(return_value=[PHOTO_ID] if found is None else found)
    patcher = patch.object(answer_photo.image_search, "photos_for_answer", finder)
    return finder, patcher


@pytest.mark.asyncio
async def test_search_starts_once_the_photo_fence_closes():
    finder, patcher = _photo()
    with patcher:
        photo = AnswerPhoto(Settings(), MagicMock())
        photo.feed("```photo\nEthiopia loc")
        await asyncio.sleep(0)
        finder.assert_not_awaited()
        photo.feed("```photo\nEthiopia location map\n```\n\nEthi")
        photo.feed(REPLY)
        await asyncio.sleep(0)
        assert not photo.watching
        finder.assert_awaited_once()
        assert finder.await_args.kwargs["query"] == "Ethiopia location map"


@pytest.mark.asyncio
async def test_the_fence_becomes_the_photo_marker():
    _, patcher = _photo()
    with patcher:
        photo = AnswerPhoto(Settings(), MagicMock())
        photo.feed(REPLY)
        content, ids = await photo.attach(REPLY)
    assert ids == [PHOTO_ID]
    assert content == (
        f"[Image: /attachments/{PHOTO_ID}/file]\n\nEthiopia lies in the Horn of Africa."
    )


@pytest.mark.asyncio
async def test_no_photo_found_drops_the_fence():
    _, patcher = _photo(found=[])
    with patcher:
        photo = AnswerPhoto(Settings(), MagicMock())
        content, ids = await photo.attach(REPLY)
    assert ids == []
    assert content == "Ethiopia lies in the Horn of Africa."


@pytest.mark.asyncio
async def test_a_slow_photo_does_not_hold_the_reply(monkeypatch):
    monkeypatch.setattr(answer_photo, "_WAIT_SECONDS", 0.01)

    async def slow(*_args, **_kwargs):
        await asyncio.sleep(1)
        return [PHOTO_ID]

    with patch.object(answer_photo.image_search, "photos_for_answer", slow):
        photo = AnswerPhoto(Settings(), MagicMock())
        photo.feed(REPLY)
        content, ids = await photo.attach(REPLY)
        task = photo._task
        assert task is not None
        # Stopped, not left to store a photo nothing links (it cost a lookup).
        await asyncio.sleep(0)
        assert task.cancelled()
    assert ids == []
    assert "```photo" not in content


@pytest.mark.asyncio
async def test_a_late_fence_is_still_searched_when_the_reply_ends():
    finder, patcher = _photo()
    late = "Ethiopia lies in the Horn of Africa. " * 20 + "\n\n```photo\nEthiopia map\n```"
    with patcher:
        photo = AnswerPhoto(Settings(), MagicMock())
        photo.feed(late)
        assert not photo.watching
        finder.assert_not_awaited()
        content, ids = await photo.attach(late)
    assert ids == [PHOTO_ID]
    assert content.startswith("Ethiopia lies")
    assert content.endswith(f"[Image: /attachments/{PHOTO_ID}/file]")


@pytest.mark.asyncio
async def test_a_reply_without_a_fence_is_left_alone():
    finder, patcher = _photo()
    with patcher:
        photo = AnswerPhoto(Settings(), MagicMock())
        photo.feed("Recursion is a function calling itself. " * 30)
        content, ids = await photo.attach("Recursion is a function calling itself.")
    finder.assert_not_awaited()
    assert (content, ids) == ("Recursion is a function calling itself.", [])


def test_strip_photo_fences():
    assert strip_photo_fences(REPLY) == "Ethiopia lies in the Horn of Africa."
    assert strip_photo_fences("No fence here.") == "No fence here."


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32
_HIT = ImageSearchHit(
    image_url="https://example.org/ethiopia.png",
    description="Ethiopia map",
    source_url="https://example.org/ethiopia",
    source_title="Ethiopia",
)


def _gateway():
    gateway = AsyncMock()
    gateway.presign_upload = AsyncMock(
        side_effect=lambda **kw: PresignedUpload(
            attachment_id=str(uuid4()),
            upload_url="https://upload",
            storage_key=f"{kw['user_id']}/{uuid4()}",
            headers={},
        )
    )
    return gateway


def _lookup_patches(gateway, *, reserve=True, hits=(_HIT,)):
    response = MagicMock(status_code=200, headers={"content-type": "image/png"}, content=PNG_BYTES)
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return {
        "storage": patch("app.modules.images.search.get_storage_gateway", return_value=gateway),
        "redis": patch("app.modules.images.search.get_redis_client", return_value=AsyncMock()),
        "spend_cap": patch(
            "app.modules.images.search.quota_service.global_spend_exceeded",
            AsyncMock(return_value=False),
        ),
        "reserve": patch(
            "app.modules.images.search.counters.reserve",
            AsyncMock(return_value=reserve),
        ),
        "search": patch(
            "app.modules.images.search.image_search_gateway.search_images",
            AsyncMock(return_value=list(hits)),
        ),
        "client": patch("app.gateways.safe_fetch.fetch_client", return_value=client),
        "fetch": patch(
            "app.modules.images.search.safe_fetch.fetch_safely", AsyncMock(return_value=response)
        ),
        "add_rows": patch(
            "app.modules.images.search.attachments_service.add_server_images", AsyncMock()
        ),
        "spend": patch("app.modules.images.search.quota_service.record_global_spend", AsyncMock()),
        "refund": patch("app.modules.images.search.counters.refund", AsyncMock()),
    }


def _entered(stack: ExitStack, patches: dict) -> dict:
    return {name: stack.enter_context(patcher) for name, patcher in patches.items()}


@pytest.mark.asyncio
async def test_photos_for_answer_stores_one_unlinked_photo():
    gateway = _gateway()
    settings = Settings(image_search_enabled=True, image_search_max_results=3)
    with ExitStack() as stack:
        mocks = _entered(stack, _lookup_patches(gateway))
        ids = await photos_for_answer(
            settings, user=MagicMock(id=uuid4(), plan="free"), query="Ethiopia  map"
        )
    assert len(ids) == 1
    gateway.write_bytes.assert_awaited_once()
    added = mocks["add_rows"].await_args.kwargs
    assert [image.attachment_id for image in added["images"]] == ids
    assert (added["label"], added["message_id"], added["in_library"]) == (
        "Ethiopia map",
        None,
        False,
    )
    mocks["refund"].assert_not_awaited()


@pytest.mark.asyncio
async def test_photos_for_answer_is_quiet_when_nothing_is_found():
    gateway = _gateway()
    with ExitStack() as stack:
        mocks = _entered(stack, _lookup_patches(gateway, hits=()))
        ids = await photos_for_answer(
            Settings(image_search_enabled=True), user=MagicMock(id=uuid4()), query="nothing"
        )
    assert ids == []
    mocks["refund"].assert_awaited_once()
    mocks["add_rows"].assert_not_awaited()


@pytest.mark.asyncio
async def test_photos_for_answer_skips_a_spent_daily_limit():
    gateway = _gateway()
    with ExitStack() as stack:
        mocks = _entered(stack, _lookup_patches(gateway, reserve=False))
        ids = await photos_for_answer(
            Settings(image_search_enabled=True), user=MagicMock(id=uuid4()), query="capybara"
        )
    assert ids == []
    mocks["search"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings",
    [Settings(image_search_enabled=False), Settings(attachments_enabled=False)],
)
async def test_photos_for_answer_does_nothing_when_off(settings):
    with patch("app.modules.images.search.get_redis_client") as redis:
        assert await photos_for_answer(settings, user=MagicMock(), query="capybara") == []
    redis.assert_not_called()


@pytest.mark.asyncio
async def test_photos_for_answer_needs_storage():
    with (
        patch(
            "app.modules.images.search.get_storage_gateway",
            return_value=UnconfiguredStorageGateway(),
        ),
        patch("app.modules.images.search.get_redis_client") as redis,
    ):
        ids = await photos_for_answer(
            Settings(image_search_enabled=True), user=MagicMock(), query="capybara"
        )
    assert ids == []
    redis.assert_not_called()
