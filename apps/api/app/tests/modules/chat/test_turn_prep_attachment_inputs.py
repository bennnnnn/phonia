"""Attachment inputs of a new turn: load, verify once, format, persist markers, camera math.

Every storage, database and vision call is faked; each test pins one path of
``_process_attachments`` the rest of the suite reaches only through ``prepare_chat_turn``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.exceptions import AttachmentValidationError, ChatNotFoundError
from app.modules.chat.turn_prep.attachments import _process_attachments
from app.modules.math.image_extract import camera_math_user_suffix
from app.modules.math.schemas import MathImageExtract
from app.tests.fakes import redis_mock

_EXTRACTED = MathImageExtract(lhs="2*x+3", rhs="7", variables=["x"], found=True)
_SOLVE = "please solve this equation"
_SIGNED_IN = object()


def _row(content_type: str, *, verified: bool = True, reserved: bool = False) -> SimpleNamespace:
    row_id = uuid4()
    created = datetime.now(UTC) if reserved else datetime(2020, 1, 1, tzinfo=UTC)
    return SimpleNamespace(
        id=row_id,
        message_id=None,
        content_type=content_type,
        storage_key=f"user/{row_id}",
        size_bytes=5,
        verified_at=None if not verified else datetime(2026, 8, 1, tzinfo=UTC),
        source="upload",
        library_visible=True,
        created_at=created,
    )


def _lines(gateway: object, **kwargs: Any) -> tuple[list[str], bool]:
    if kwargs["content_type"].startswith("image/"):
        return [f"[Image: /attachments/{kwargs['attachment_id']}/file]"], True
    return [f"[File: /attachments/{kwargs['attachment_id']}/file]"], False


class _Session:
    async def __aenter__(self) -> object:
        return AsyncMock()

    async def __aexit__(self, *_args: object) -> None:
        return None


async def _run(
    rows: list[SimpleNamespace],
    *,
    content: str = "hi",
    ids: list[Any] | None = None,
    user: Any = _SIGNED_IN,
    fakes: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any], list[str]]:
    gateway = object()
    mocks: dict[str, Any] = {
        "get_by_id": AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        "get_by_ids": AsyncMock(return_value=rows),
        "verify": AsyncMock(return_value=(b"verified", None)),
        "purge": AsyncMock(return_value=True),
        "mark_verified": AsyncMock(),
        "format": AsyncMock(side_effect=_lines),
        "read": AsyncMock(return_value=b"downloaded"),
        "extract": AsyncMock(return_value=_EXTRACTED),
        "refund": AsyncMock(),
    }
    mocks.update(fakes or {})
    statuses: list[str] = []
    signed_in: Any = SimpleNamespace(id=uuid4())

    async def on_status(
        phase: str, detail: str | None = None, *, elapsed_ms: int | None = None
    ) -> None:
        statuses.append(phase)

    with (
        patch("app.modules.chat.turn_prep.attachments.SessionLocal", return_value=_Session()),
        patch("app.repositories.users.get_by_id", mocks["get_by_id"]),
        patch("app.modules.attachments.repository.get_by_ids", mocks["get_by_ids"]),
        patch("app.modules.attachments.repository.mark_verified_many", mocks["mark_verified"]),
        patch("app.gateways.storage_gateway.get_storage_gateway", return_value=gateway) as gw,
        patch("app.modules.attachments.content.verify_uploaded_bytes", mocks["verify"]),
        patch("app.modules.attachments.content.purge_invalid_upload", mocks["purge"]),
        patch("app.modules.attachments.content.format_attachment_lines", mocks["format"]),
        patch("app.modules.attachments.content.read_attachment_bytes", mocks["read"]),
        patch("app.modules.math.image_extract.extract_equation_from_image", mocks["extract"]),
        patch("app.services.quota.counters.refund", mocks["refund"]),
    ):
        mocks["gateway"] = gw
        result = await _process_attachments(
            user_id=uuid4(),
            user=signed_in if user is _SIGNED_IN else user,
            content=content,
            attachment_ids=[row.id for row in rows] if ids is None else ids,
            settings=Settings(attachments_enabled=True),
            redis=redis_mock(),
            on_status=on_status,
        )
    mocks["gateway_value"] = gateway
    return result, mocks, statuses


@pytest.mark.asyncio
async def test_flag_off_rejects_ids_and_no_ids_pass_the_text_through() -> None:
    with pytest.raises(AttachmentValidationError, match="temporarily unavailable"):
        await _process_attachments(
            user_id=uuid4(),
            user=None,
            content="hi",
            attachment_ids=[uuid4()],
            settings=Settings(attachments_enabled=False),
            redis=redis_mock(),
            on_status=None,
        )
    result = await _process_attachments(
        user_id=uuid4(),
        user=None,
        content="hi",
        attachment_ids=[],
        settings=Settings(attachments_enabled=True),
        redis=redis_mock(),
        on_status=None,
    )
    assert (result.user, result.user_content, result.content) == (None, "hi", "hi")
    assert result.resolved_attachment_ids is None and result.gateway is None


@pytest.mark.asyncio
async def test_a_missing_user_is_loaded_or_the_turn_fails() -> None:
    row = _row("text/plain")
    loaded = SimpleNamespace(id=uuid4())
    result, mocks, _ = await _run(
        [row], fakes={"get_by_id": AsyncMock(return_value=loaded)}, user=None
    )
    assert result.user is loaded
    assert mocks["get_by_ids"].await_args.args[2] == loaded.id
    with pytest.raises(ChatNotFoundError, match="User not found"):
        await _run([row], fakes={"get_by_id": AsyncMock(return_value=None)}, user=None)


@pytest.mark.asyncio
async def test_repeated_ids_load_once_in_order_and_markers_follow_the_caption() -> None:
    image, document = _row("image/png"), _row("text/plain")
    result, mocks, statuses = await _run(
        [image, document], content="look", ids=[image.id, document.id, image.id]
    )
    assert mocks["get_by_ids"].await_args.args[1] == [image.id, document.id]
    assert result.resolved_attachment_ids == [image.id, document.id]
    assert result.user_content == (
        f"look\n\n[Image: /attachments/{image.id}/file]\n[File: /attachments/{document.id}/file]"
    )
    assert result.content == "look"
    assert result.image_attachments == [("image/png", image.storage_key)]
    assert result.has_image_attachment and result.has_document_attachment
    assert result.gateway is mocks["gateway_value"]
    assert statuses == ["reading_files"]
    mocks["verify"].assert_not_awaited()
    mocks["extract"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_blank_caption_stores_only_the_markers() -> None:
    document = _row("text/plain")
    result, _, _ = await _run([document], content="  ")
    assert result.user_content == f"[File: /attachments/{document.id}/file]"
    assert result.content == "  "


@pytest.mark.asyncio
async def test_camera_math_downloads_once_and_adds_the_equation_to_the_prompt_only() -> None:
    image = _row("image/png")
    result, mocks, statuses = await _run([image], content=_SOLVE)
    mocks["read"].assert_awaited_once_with(mocks["gateway_value"], image.storage_key)
    assert mocks["extract"].await_args.kwargs == {
        "content_type": "image/png",
        "data": b"downloaded",
    }
    assert result.bytes_by_key == {image.storage_key: b"downloaded"}
    assert result.image_math_extract == _EXTRACTED
    assert result.content == f"{_SOLVE}\n\n{camera_math_user_suffix(_EXTRACTED)}"
    assert result.user_content == f"{_SOLVE}\n\n[Image: /attachments/{image.id}/file]"
    assert statuses == ["reading_files", "calculating"]


@pytest.mark.asyncio
async def test_camera_math_reads_the_first_image_from_the_verified_bytes() -> None:
    first, second = _row("image/jpeg", verified=False), _row("image/png", verified=False)
    result, mocks, _ = await _run([first, second], content=_SOLVE)
    mocks["read"].assert_not_awaited()
    assert mocks["extract"].await_args.kwargs == {"content_type": "image/jpeg", "data": b"verified"}
    # Both uploads are marked verified in one statement.
    mocks["mark_verified"].assert_awaited_once()
    assert set(mocks["mark_verified"].await_args.args[1]) == {first.id, second.id}
    assert result.has_document_attachment is False


@pytest.mark.asyncio
async def test_camera_math_download_failure_skips_the_vision_call() -> None:
    image = _row("image/png")
    result, mocks, statuses = await _run(
        [image], content=_SOLVE, fakes={"read": AsyncMock(return_value=None)}
    )
    mocks["extract"].assert_not_awaited()
    assert result.image_math_extract is None and result.content == _SOLVE
    assert result.bytes_by_key == {}
    assert statuses == ["reading_files", "calculating"]


@pytest.mark.asyncio
async def test_camera_math_ocr_failure_keeps_the_caption() -> None:
    image = _row("image/png")
    result, mocks, _ = await _run(
        [image], content=_SOLVE, fakes={"extract": AsyncMock(return_value=None)}
    )
    mocks["extract"].assert_awaited_once()
    assert result.image_math_extract is None and result.content == _SOLVE
    assert result.bytes_by_key == {image.storage_key: b"downloaded"}


@pytest.mark.asyncio
@pytest.mark.parametrize("reserved", [True, False])
async def test_a_failed_verify_purges_and_refunds_only_a_reserved_image(reserved: bool) -> None:
    document = _row("text/plain", verified=False)
    image = _row("image/png", verified=False, reserved=reserved)
    verify = AsyncMock(side_effect=[(b"ok", None), (None, "Upload not found")])
    purge, refund, mark_verified = AsyncMock(return_value=True), AsyncMock(), AsyncMock()
    fakes = {"verify": verify, "purge": purge, "refund": refund, "mark_verified": mark_verified}
    with pytest.raises(AttachmentValidationError, match="Upload not found"):
        await _run([document, image], fakes=fakes)
    # A refused turn marks nothing; the next send checks the good upload again.
    mark_verified.assert_not_awaited()
    assert purge.call_args.kwargs == {"attachment_id": image.id, "storage_key": image.storage_key}
    assert refund.await_count == (1 if reserved else 0)
    assert refund.await_args is None or refund.await_args.args[0] == "image_upload"


@pytest.mark.asyncio
async def test_no_rows_after_reuse_return_before_storage() -> None:
    row = _row("text/plain")
    with patch("app.modules.attachments.reuse.ensure_unlinked_copies", AsyncMock(return_value=[])):
        result, mocks, statuses = await _run([row])
    assert result.resolved_attachment_ids == [] and result.gateway is None
    assert result.user_content == "hi" and statuses == []
    mocks["gateway"].assert_not_called()
