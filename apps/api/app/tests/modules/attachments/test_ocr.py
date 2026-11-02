"""Scanned-PDF OCR: render pages → vision-chat → same extract/RAG path."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pypdf import PdfWriter

from app.core.config import Settings
from app.modules.attachments import ocr as ocr
from app.modules.attachments import pdf_render


def _blank_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _vision_response(text: str) -> MagicMock:
    message = MagicMock()
    message.content = text
    response = MagicMock()
    response.choices = [MagicMock(message=message)]
    return response


def test_render_pdf_pages_returns_jpeg():
    pages, _total = ocr.render_pdf_pages_and_count(_blank_pdf_bytes(), max_pages=2, scale=1.5)
    assert len(pages) == 1
    mime, data = pages[0]
    assert mime == "image/jpeg"
    assert data[:3] == b"\xff\xd8\xff"


def test_render_pdf_pages_and_count_includes_document_length():
    pages, total = ocr.render_pdf_pages_and_count(_blank_pdf_bytes(), max_pages=2, scale=1.5)
    assert len(pages) == 1
    assert total == 1


def test_render_pdf_pages_invalid_bytes_returns_empty():
    assert ocr.render_pdf_pages_and_count(b"not-a-pdf", max_pages=2, scale=1.5)[0] == []


def test_page_text_from_response_skips_empty_marker():
    assert ocr._page_text_from_response(_vision_response("[empty]")) is None
    assert ocr._page_text_from_response(_vision_response("```text\n[empty]\n```")) is None
    assert ocr._page_text_from_response(_vision_response("Homework: 2x + 3 = 7")) == (
        "Homework: 2x + 3 = 7"
    )


@pytest.mark.asyncio
async def test_ocr_scanned_pdf_concatenates_pages():
    settings = Settings(
        attachment_ocr_enabled=True,
        mock_llm_enabled=False,
        openrouter_api_key="test-key",
    )
    rendered = [
        ("image/jpeg", b"\xff\xd8\xffpage1"),
        ("image/jpeg", b"\xff\xd8\xffpage2"),
    ]
    responses = iter(
        [
            _vision_response("Page one text"),
            _vision_response("[empty]"),
        ]
    )

    with (
        patch.object(pdf_render, "render_pdf_pages_and_count", return_value=(rendered, 2)),
        patch(
            "app.gateways.litellm_gateway.vision_completion",
            AsyncMock(side_effect=lambda **_k: next(responses)),
        ) as vision,
    ):
        text = await ocr.ocr_scanned_pdf(settings, b"%PDF-fake")

    assert text is not None
    assert text.text == "Page one text"
    assert text.via_ocr is True
    assert vision.await_count == 2


@pytest.mark.asyncio
async def test_ocr_scanned_pdf_joins_nonempty_pages():
    settings = Settings(
        attachment_ocr_enabled=True,
        mock_llm_enabled=False,
        openrouter_api_key="test-key",
    )
    rendered = [
        ("image/jpeg", b"\xff\xd8\xffa"),
        ("image/jpeg", b"\xff\xd8\xffb"),
    ]
    responses = iter([_vision_response("Heading"), _vision_response("Body paragraph")])
    with (
        patch.object(pdf_render, "render_pdf_pages_and_count", return_value=(rendered, 2)),
        patch(
            "app.gateways.litellm_gateway.vision_completion",
            AsyncMock(side_effect=lambda **_k: next(responses)),
        ),
    ):
        text = await ocr.ocr_scanned_pdf(settings, b"%PDF-fake")
    assert text is not None
    assert text.text == "Heading\n\nBody paragraph"
    assert text.via_ocr is True


@pytest.mark.asyncio
async def test_ocr_scanned_pdf_skips_when_disabled_or_mock():
    disabled = Settings(attachment_ocr_enabled=False, mock_llm_enabled=False)
    mocked = Settings(attachment_ocr_enabled=True, mock_llm_enabled=True)
    with patch("app.gateways.litellm_gateway.vision_completion", AsyncMock()) as vision:
        assert await ocr.ocr_scanned_pdf(disabled, b"%PDF") is None
        assert await ocr.ocr_scanned_pdf(mocked, b"%PDF") is None
    vision.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_async_uses_ocr_when_text_layer_empty(monkeypatch):
    from app.modules.attachments.content import extract_text_details_async

    monkeypatch.setattr(
        "app.modules.attachments.text_extract.extract_text_details",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "app.modules.attachments.ocr.ocr_scanned_pdf",
        AsyncMock(return_value="scanned homework"),
    )
    settings = Settings(attachment_ocr_enabled=True)
    result = await extract_text_details_async("application/pdf", b"%PDF", settings)
    assert result is not None
    assert result.text == "scanned homework"


@pytest.mark.asyncio
async def test_extract_async_skips_ocr_when_disallowed(monkeypatch):
    from app.modules.attachments.content import extract_text_details_async

    monkeypatch.setattr(
        "app.modules.attachments.text_extract.extract_text_details",
        lambda *_a, **_k: None,
    )
    ocr_mock = AsyncMock(return_value="should-not-run")
    monkeypatch.setattr("app.modules.attachments.ocr.ocr_scanned_pdf", ocr_mock)
    settings = Settings(attachment_ocr_enabled=True)
    result = await extract_text_details_async("application/pdf", b"%PDF", settings, allow_ocr=False)
    assert result is None
    ocr_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_async_does_not_ocr_when_text_layer_present(monkeypatch):
    from app.modules.attachments.content import ExtractedText, extract_text_details_async

    monkeypatch.setattr(
        "app.modules.attachments.text_extract.extract_text_details",
        lambda *_a, **_k: ExtractedText(text="selectable text"),
    )
    ocr_mock = AsyncMock(return_value="should-not-run")
    monkeypatch.setattr("app.modules.attachments.ocr.ocr_scanned_pdf", ocr_mock)
    result = await extract_text_details_async(
        "application/pdf", b"%PDF", Settings(attachment_ocr_enabled=True)
    )
    assert result is not None
    assert result.text == "selectable text"
    ocr_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_async_timeout_does_not_ocr(monkeypatch):
    import time

    from app.modules.attachments.content import extract_text_details_async

    def _slow(*_a: object, **_k: object) -> str | None:
        time.sleep(0.5)
        return None

    monkeypatch.setattr("app.modules.attachments.text_extract.extract_text_details", _slow)
    ocr_mock = AsyncMock(return_value="should-not-run")
    monkeypatch.setattr("app.modules.attachments.ocr.ocr_scanned_pdf", ocr_mock)
    settings = Settings(attachment_extract_timeout_seconds=0.05, attachment_ocr_enabled=True)
    result = await extract_text_details_async("application/pdf", b"%PDF", settings)
    assert result is None
    ocr_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_ocr_scanned_pdf_uses_caller_char_cap():
    settings = Settings(
        attachment_ocr_enabled=True,
        mock_llm_enabled=False,
        openrouter_api_key="test-key",
    )
    rendered = [("image/jpeg", b"\xff\xd8\xffpage1")]
    with (
        patch.object(
            pdf_render, "render_pdf_pages_and_count", return_value=(rendered, 40)
        ) as render,
        patch(
            "app.gateways.litellm_gateway.vision_completion",
            AsyncMock(return_value=_vision_response("x" * 50)),
        ),
    ):
        result = await ocr.ocr_scanned_pdf(
            settings,
            b"%PDF-fake",
            max_chars=12,
            max_pages=20,
        )

    assert render.call_args.kwargs["max_pages"] == 20
    assert result is not None
    assert result.text == "x" * 12
    assert result.char_capped is True
    assert result.page_capped is True
    assert result.via_ocr is True


@pytest.mark.asyncio
async def test_extract_async_ocr_index_uses_index_caps(monkeypatch):
    from app.modules.attachments.content import (
        MAX_EXTRACT_CHARS,
        MAX_INDEX_EXTRACT_CHARS,
        extract_text_details_async,
    )

    monkeypatch.setattr(
        "app.modules.attachments.text_extract.extract_text_details",
        lambda *_a, **_k: None,
    )
    captured: dict = {}

    async def _ocr(_settings, _data, *, max_chars=None, max_pages=None):
        captured["max_chars"] = max_chars
        captured["max_pages"] = max_pages
        from app.modules.attachments.content import ExtractedText

        return ExtractedText(text="scanned", via_ocr=True)

    monkeypatch.setattr("app.modules.attachments.ocr.ocr_scanned_pdf", _ocr)
    settings = Settings(attachment_ocr_enabled=True, attachment_ocr_index_max_pages=20)
    result = await extract_text_details_async(
        "application/pdf",
        b"%PDF",
        settings,
        max_chars=MAX_INDEX_EXTRACT_CHARS,
        ocr_max_pages=settings.attachment_ocr_index_max_pages,
    )
    assert result is not None
    assert result.text == "scanned"
    assert captured["max_chars"] == MAX_INDEX_EXTRACT_CHARS
    assert captured["max_pages"] == 20
    assert captured["max_chars"] != MAX_EXTRACT_CHARS
