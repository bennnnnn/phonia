"""A turn's photos reach the model: this turn's, or an earlier one read again while
the chat is still about it."""

import base64
import io
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from PIL import Image

from app.core.config import Settings
from app.gateways.storage_gateway import StorageUnavailableError
from app.modules.chat.prompt_constants.visuals import IMAGE_GEN_UNAVAILABLE_HINT
from app.modules.chat.turn_prep.attachments import _AttachmentProcessResult
from app.modules.chat.turn_prep.vision import inject_turn_images
from app.tests.modules.chat.chat_test_support import FakeSessionCM

_MODULE = "app.modules.chat.turn_prep.vision"
_ON = Settings(attachments_enabled=True)


def _png(colour: str) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (4, 4), {"red": (255, 0, 0), "blue": (0, 0, 255)}[colour]).save(
        out, format="PNG"
    )
    return out.getvalue()


def _colour(part) -> str:
    """The colour of a sent photo: it is re-encoded, so its bytes differ from the upload."""
    data = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
    with Image.open(io.BytesIO(data)) as image:
        pixel = image.convert("RGB").getpixel((0, 0))
    assert isinstance(pixel, tuple)
    return "red" if pixel[0] > pixel[2] else "blue"


def _attachments(*, images: list[tuple[str, str]] | None = None, gateway=None):
    return _AttachmentProcessResult(
        user=None,
        user_content="",
        content="",
        has_image_attachment=bool(images),
        has_document_attachment=False,
        image_attachments=images or [],
        image_math_extract=None,
        gateway=gateway,
        bytes_by_key={key: _png("red") for _type, key in images or []},
    )


def _earlier(*ids):
    markers = "\n".join(f"[Image: /attachments/{uid}/file]" for uid in ids)
    return [
        {"role": "user", "content": f"What is this?\n\n{markers}"},
        {"role": "assistant", "content": "A cell."},
        {"role": "user", "content": "what colour is it?"},
    ]


def _two_turns_ago(uid, caption):
    return [
        *_earlier(uid),
        {"role": "assistant", "content": "Green."},
        {"role": "user", "content": caption},
    ]


def _row(uid, content_type="image/png"):
    return SimpleNamespace(id=uid, content_type=content_type, storage_key=f"key-{uid}")


async def _run(
    messages, attachments, rows, *, settings=_ON, byte_map=None, caption="what colour is it?"
):
    user = SimpleNamespace(id=uuid4())
    lookup = AsyncMock(return_value=rows)
    gateway = SimpleNamespace(
        read_bytes=AsyncMock(side_effect=lambda key: (byte_map or {}).get(key))
    )
    with (
        patch(f"{_MODULE}.SessionLocal", FakeSessionCM),
        patch(f"{_MODULE}.attachments_service.get_by_ids", lookup),
        patch(f"{_MODULE}.get_storage_gateway", return_value=gateway) as storage,
    ):
        needs_vision = await inject_turn_images(
            messages, attachments, caption=caption, settings=settings, user=user
        )
    return needs_vision, lookup, storage, user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caption, read_again",
    [
        ("and in the photo, what is the dark spot?", True),
        ("what does the error in that screenshot say?", True),
        ("Is the PICTURE upside down?", True),
        ("can you crop the photograph's left edge?", True),
        # Picture words inside other words, and ordinary follow-ups, leave it out.
        ("thanks! now explain photosynthesis", False),
        ("imagine a cell twice that size", False),
        ("that was an epic answer", False),
        ("what do cells eat?", False),
    ],
)
async def test_a_photo_from_further_back_is_read_again_only_when_named(caption, read_again):
    uid = uuid4()
    messages = _two_turns_ago(uid, caption)
    needs_vision, lookup, _storage, _user = await _run(
        messages,
        _attachments(),
        [_row(uid)],
        byte_map={f"key-{uid}": _png("red")},
        caption=caption,
    )
    assert needs_vision is read_again
    assert lookup.await_count == int(read_again)
    if not read_again:
        assert messages[-1]["content"] == caption


def _photo_parts(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message["content"]
    assert isinstance(content, list)
    return [part for part in content if part["type"] == "image_url"]


def _photo_message(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """The user message the photos were put back on."""
    return next(
        message
        for message in reversed(messages)
        if message.get("role") == "user" and isinstance(message.get("content"), list)
    )


@pytest.mark.asyncio
async def test_storage_outage_on_an_earlier_photo_names_it_and_keeps_the_turn():
    uid = uuid4()
    messages = _earlier(uid)
    outage = AsyncMock(side_effect=StorageUnavailableError("down"))
    with patch(f"{_MODULE}.vision_input.inject_vision_content", outage):
        needs_vision, *_ = await _run(messages, _attachments(), [_row(uid)])
    assert needs_vision is False
    assert "not available to look at again" in str(messages[-1]["content"])  # safety phrase


@pytest.mark.asyncio
async def test_an_earlier_photo_is_read_again_and_asks_for_the_vision_model():
    first, second = uuid4(), uuid4()
    messages = _earlier(first, second)
    needs_vision, lookup, _storage, user = await _run(
        messages,
        _attachments(),
        [_row(second), _row(first)],
        byte_map={f"key-{first}": _png("red"), f"key-{second}": _png("blue")},
    )
    assert needs_vision is True
    assert lookup.await_args.args[1:] == ([first, second], user.id)
    sent = _photo_message(messages)
    parts = [part for part in sent["content"] if part["type"] == "image_url"]
    assert [_colour(part) for part in parts] == ["red", "blue"]
    assert IMAGE_GEN_UNAVAILABLE_HINT not in str(sent["content"])
    # Back on the message that sent them: "Smart" after a screenshot described it again
    # when the photo rode on the new message (live chat, 2026-10-25).
    assert sent is not messages[-1]
    assert isinstance(messages[-1]["content"], str)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing", "document", "unreadable", "one_of_two_missing"])
async def test_an_earlier_photo_that_is_gone_is_named_not_guessed(kind):
    kept, gone = uuid4(), uuid4()
    ids = [kept, gone] if kind == "one_of_two_missing" else [gone]
    rows = {
        "missing": [],
        "document": [_row(gone, "application/pdf")],
        "unreadable": [_row(gone)],
        "one_of_two_missing": [_row(kept)],
    }[kind]
    messages = _earlier(*ids)
    needs_vision, *_ = await _run(
        messages, _attachments(), rows, byte_map={f"key-{kept}": _png("red")}
    )
    assert needs_vision is (kind == "one_of_two_missing")
    assert "not available to look at again" in str(messages[-1]["content"])  # safety phrase


@pytest.mark.asyncio
async def test_this_turns_photo_uses_the_bytes_already_read_and_skips_the_earlier_one():
    earlier = uuid4()
    gateway = MagicMock()
    messages = _earlier(earlier)
    needs_vision, lookup, storage, _user = await _run(
        messages, _attachments(images=[("image/png", "now")], gateway=gateway), [_row(earlier)]
    )
    assert needs_vision is False
    lookup.assert_not_awaited()
    storage.assert_not_called()
    image = next(part for part in messages[-1]["content"] if part["type"] == "image_url")
    assert _colour(image) == "red"


@pytest.mark.asyncio
@pytest.mark.parametrize("earlier", [False, True])
async def test_a_photo_turn_says_what_to_do_with_an_unreadable_photo(earlier):
    """A blurry or cropped photo gets "what I can't read" and a request for a better one."""
    from app.modules.attachments.vision_notes import IMAGE_REAL_NOTE, UNCLEAR_IMAGE_NOTE

    uid = uuid4()
    if earlier:
        messages = _earlier(uid)
        attachments = _attachments()
    else:
        messages = _earlier()
        attachments = _attachments(images=[("image/png", "now")], gateway=MagicMock())
    await _run(messages, attachments, [_row(uid)], byte_map={f"key-{uid}": _png("red")})
    text = _photo_message(messages)["content"][0]["text"]
    assert IMAGE_REAL_NOTE in text and UNCLEAR_IMAGE_NOTE in text
    assert "ask for a clearer photo instead of guessing" in UNCLEAR_IMAGE_NOTE  # safety phrase
    assert "say what you cannot make out" in UNCLEAR_IMAGE_NOTE  # safety phrase


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_no_earlier_photo_or_attachments_off_does_no_work(enabled):
    messages = _earlier(uuid4()) if not enabled else _earlier()
    before = [dict(message) for message in messages]
    needs_vision, lookup, storage, _user = await _run(
        messages, _attachments(), [], settings=Settings(attachments_enabled=enabled)
    )
    assert needs_vision is False
    lookup.assert_not_awaited()
    storage.assert_not_called()
    assert messages == before


@pytest.mark.asyncio
async def test_photos_from_two_messages_each_go_back_to_their_own() -> None:
    """Review: photo A in one message and B in a later one both landed on the later one."""
    first, second = uuid4(), uuid4()
    messages = [
        {"role": "user", "content": f"look\n\n[Image: /attachments/{first}/file]"},
        {"role": "assistant", "content": "A red square."},
        {"role": "user", "content": f"and this\n\n[Image: /attachments/{second}/file]"},
        {"role": "assistant", "content": "A blue square."},
        {"role": "user", "content": "compare the two photos"},
    ]
    needs_vision, *_ = await _run(
        messages,
        _attachments(),
        [_row(first), _row(second)],
        byte_map={f"key-{first}": _png("red"), f"key-{second}": _png("blue")},
    )
    assert needs_vision is True
    colours = [
        [_colour(part) for part in _photo_parts(message)] for message in (messages[0], messages[2])
    ]
    assert colours == [["red"], ["blue"]]
    assert messages[-1]["content"] == "compare the two photos"
