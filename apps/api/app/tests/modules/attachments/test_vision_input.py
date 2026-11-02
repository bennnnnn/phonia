"""Photos reach the vision model upright, shrunk, within the turn's byte budget."""

import base64
import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from app.core.config import Settings
from app.modules.attachments import vision_input
from app.modules.attachments.vision_notes import PHOTOS_LEFT_OUT_NOTE, VISION_NOTE


def _image(
    fmt: str, size: tuple[int, int], mode: str = "RGB", *, exif_rotate: bool = False
) -> bytes:
    image = Image.new(mode, size, (10, 120, 200, 0) if mode == "RGBA" else (10, 120, 200))
    buf = io.BytesIO()
    if exif_rotate:
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90° clockwise to display
        image.save(buf, format=fmt, exif=exif)
    else:
        image.save(buf, format=fmt)
    return buf.getvalue()


def _decoded(url: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))


def test_a_large_photo_is_shrunk_to_the_long_edge() -> None:
    mime, data = vision_input.encode_for_vision(
        _image("JPEG", (4000, 3000)), max_edge=2048, max_pixels=16_000_000
    )
    assert mime == "image/jpeg"
    assert Image.open(io.BytesIO(data)).size == (2048, 1536)


def test_a_sideways_phone_photo_is_turned_upright() -> None:
    _mime, data = vision_input.encode_for_vision(
        _image("JPEG", (400, 200), exif_rotate=True), max_edge=2048, max_pixels=0
    )
    assert Image.open(io.BytesIO(data)).size == (200, 400)


@pytest.mark.parametrize("mode, mime", [("RGBA", "image/png"), ("RGB", "image/jpeg")])
def test_transparency_keeps_png(mode: str, mime: str) -> None:
    got, _data = vision_input.encode_for_vision(
        _image("PNG", (50, 50), mode), max_edge=2048, max_pixels=0
    )
    assert got == mime


def _messages(content: Any = "what is this?") -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "earlier"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": content},
    ]


def _gateway(objects: dict[str, bytes]) -> MagicMock:
    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(side_effect=lambda key: objects.get(key))
    return gateway


async def test_injects_photos_into_the_last_user_message_and_frees_their_bytes() -> None:
    messages = _messages()
    cache = {"u/a": _image("JPEG", (3000, 1000))}

    injected = await vision_input.inject_vision_content(
        messages,
        _gateway({}),
        [("image/jpeg", "u/a")],
        settings=Settings(),
        caption="what is this?",
        bytes_by_key=cache,
    )

    assert injected is True
    assert cache == {}
    content = messages[-1]["content"]
    assert content[0] == {"type": "text", "text": f"what is this?\n\n{VISION_NOTE}"}
    assert (
        max(_decoded(content[1]["image_url"]["url"]).size) == Settings().attachment_vision_max_edge
    )
    assert messages[1] == {"role": "user", "content": "earlier"}


async def test_a_photo_past_the_turn_budget_is_left_out_and_the_model_is_told() -> None:
    messages = _messages()
    objects = {"u/a": _image("PNG", (40, 40)), "u/b": _image("JPEG", (1500, 1500))}
    small = len(
        base64.b64encode(
            vision_input.encode_for_vision(objects["u/a"], max_edge=2048, max_pixels=0)[1]
        )
    )

    injected = await vision_input.inject_vision_content(
        messages,
        _gateway(objects),
        [("image/png", "u/a"), ("image/jpeg", "u/b")],
        settings=Settings(attachment_vision_max_turn_bytes=small + 100),
        caption="compare",
    )

    assert injected is True
    content = messages[-1]["content"]
    assert len(content) == 2
    assert content[0]["text"].endswith(f"{VISION_NOTE} {PHOTOS_LEFT_OUT_NOTE}")


async def test_photos_keep_their_order_and_a_missing_one_is_left_out_and_told() -> None:
    messages = _messages()
    objects = {"u/a": _image("PNG", (40, 20)), "u/c": _image("JPEG", (20, 40))}

    injected = await vision_input.inject_vision_content(
        messages,
        _gateway(objects),
        [("image/png", "u/a"), ("image/png", "u/missing"), ("image/jpeg", "u/c")],
        settings=Settings(),
        caption="compare",
    )

    assert injected is True
    content = messages[-1]["content"]
    sizes = [_decoded(part["image_url"]["url"]).size for part in content[1:]]
    assert sizes == [(40, 20), (20, 40)]
    assert content[0]["text"].endswith(f"{VISION_NOTE} {PHOTOS_LEFT_OUT_NOTE}")


async def test_nothing_is_injected_when_no_photo_decodes() -> None:
    messages = _messages()
    before = [dict(message) for message in messages]

    injected = await vision_input.inject_vision_content(
        messages,
        _gateway({"u/a": b"not an image"}),
        [("image/jpeg", "u/a"), ("image/jpeg", "u/missing")],
        settings=Settings(),
        caption="hi",
    )

    assert injected is False
    assert messages == before


@pytest.mark.parametrize(
    "existing, caption, text",
    [
        ("what is this?", "what is this?", "what is this?"),
        ([{"type": "text", "text": "x"}], " describe this ", "describe this"),
        ("", "", "What's in this image?"),
        # Camera maths adds a line the stored message does not have.
        ("solve it", "solve it\nSolve: 2x = 4", "solve it\n\nSolve: 2x = 4"),
    ],
)
def test_vision_prompt_text(existing: Any, caption: str, text: str) -> None:
    assert vision_input.vision_prompt_text(existing, caption) == text
