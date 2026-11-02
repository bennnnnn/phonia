"""Thumbnails round up to a few stored sizes, are made once, and go with their object."""

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from app.core.config import Settings
from app.modules.attachments import thumbnails


def _png(side: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (side, side), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


class _Store:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = dict(objects)
        self.reads: list[str] = []

    async def read_bytes(self, key: str) -> bytes | None:
        self.reads.append(key)
        return self.objects.get(key)

    async def write_bytes(self, key: str, data: bytes) -> None:
        self.objects[key] = data


@pytest.mark.parametrize(
    "width, edge",
    [(None, None), (0, None), (-5, None), (1, 64), (64, 64), (65, 128), (300, 384), (9000, 512)],
)
def test_thumbnail_edge_rounds_up_to_a_stored_size(width: int | None, edge: int | None) -> None:
    assert thumbnails.thumbnail_edge(width) == edge


def test_thumbnails_live_under_their_object() -> None:
    assert thumbnails.thumbnail_key("u/k", 128) == "u/k.thumbs/w128"
    assert thumbnails.thumbnail_key("u/k", 128).startswith(thumbnails.thumbnail_prefix("u/k"))


async def test_a_thumbnail_is_made_once_then_read_from_storage() -> None:
    store = _Store({"u/k": _png(600)})

    first = await thumbnails.thumbnail_bytes(store, Settings(), "u/k", 128)  # type: ignore[arg-type]
    store.reads.clear()
    second = await thumbnails.thumbnail_bytes(store, Settings(), "u/k", 128)  # type: ignore[arg-type]

    assert first is not None and second == first
    assert first[1] == "image/jpeg"
    assert max(Image.open(io.BytesIO(first[0])).size) == 128
    assert store.reads == ["u/k.thumbs/w128"]  # the original is not downloaded again


async def test_a_missing_image_has_no_thumbnail() -> None:
    store = _Store({})
    assert await thumbnails.thumbnail_bytes(store, Settings(), "u/gone", 64) is None  # type: ignore[arg-type]


async def test_a_failed_thumbnail_store_still_answers() -> None:
    store = _Store({"u/k": _png(100)})
    store.write_bytes = AsyncMock(side_effect=OSError("disk full"))  # type: ignore[method-assign]

    thumb = await thumbnails.thumbnail_bytes(store, Settings(), "u/k", 64)  # type: ignore[arg-type]

    assert thumb is not None


async def test_delete_thumbnails_is_best_effort() -> None:
    gateway = MagicMock()
    gateway.delete_prefix = AsyncMock(side_effect=RuntimeError("storage down"))

    await thumbnails.delete_thumbnails(gateway, "u/k")

    gateway.delete_prefix.assert_awaited_once_with("u/k.thumbs/")
