import io
import zipfile
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.attachments.content import extract_text_details
from app.modules.attachments.content_types import ALLOWED_CONTENT_TYPES, is_image_content_type
from app.modules.attachments.markers import strip_attachment_from_content

_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _build_zip_bytes(names: list[str]) -> bytes:
    """Build an in-memory ZIP archive containing the given (dummy-content) entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name in names:
            archive.writestr(name, "<content/>")
    return buf.getvalue()


def test_allowed_content_types_include_images_and_documents():
    assert "image/jpeg" in ALLOWED_CONTENT_TYPES
    assert "image/heic" not in ALLOWED_CONTENT_TYPES
    assert "application/pdf" in ALLOWED_CONTENT_TYPES
    assert "text/plain" in ALLOWED_CONTENT_TYPES
    # Legacy .doc rejected at presign — no pure-Python parser, so allowing it
    # produces unusable uploads with no RAG.
    assert "application/msword" not in ALLOWED_CONTENT_TYPES


def test_extract_text_details_respects_max_chars():
    """The max_chars parameter caps extracted text — the indexing path uses a
    higher cap than the inline excerpt path."""
    long_text = "x" * 5000
    result = extract_text_details("text/plain", long_text.encode(), max_chars=100)
    assert result is not None
    assert len(result.text) == 100


def test_normalize_content_type():
    from app.modules.attachments.content_types import normalize_content_type

    assert normalize_content_type("image/heic") == "image/heic"
    assert normalize_content_type("image/jpeg; charset=binary") == "image/jpeg"
    assert normalize_content_type("image/jpg") == "image/jpeg"


def test_is_image_content_type():
    assert is_image_content_type("image/png") is True
    assert is_image_content_type("image/heic") is False
    assert is_image_content_type("application/pdf") is False


def test_extract_text_from_plain_text():
    details = extract_text_details("text/plain", b"Hello, Recall.")
    assert details is not None
    assert details.text == "Hello, Recall."


def test_bytes_match_claimed_accepts_word_documents():
    from app.modules.attachments.content_types import bytes_match_claimed

    docx_bytes = _build_zip_bytes(["word/document.xml", "[Content_Types].xml"])
    doc_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32
    assert bytes_match_claimed(_DOCX_CONTENT_TYPE, docx_bytes) is True
    assert bytes_match_claimed("application/msword", doc_bytes) is True
    assert bytes_match_claimed("application/msword", docx_bytes) is False


def test_bytes_match_claimed_rejects_non_docx_zip_family():
    """.xlsx/.pptx/.jar/.apk/plain .zip all share the PK\\x03\\x04 ZIP
    signature but aren't DOCX — a claimed DOCX upload must actually contain
    the word/document.xml marker entry, not just look like a ZIP."""
    from app.modules.attachments.content_types import bytes_match_claimed

    xlsx_bytes = _build_zip_bytes(["xl/workbook.xml", "[Content_Types].xml"])
    pptx_bytes = _build_zip_bytes(["ppt/presentation.xml", "[Content_Types].xml"])
    plain_zip_bytes = _build_zip_bytes(["readme.txt"])

    assert bytes_match_claimed(_DOCX_CONTENT_TYPE, xlsx_bytes) is False
    assert bytes_match_claimed(_DOCX_CONTENT_TYPE, pptx_bytes) is False
    assert bytes_match_claimed(_DOCX_CONTENT_TYPE, plain_zip_bytes) is False


def test_bytes_match_claimed_handles_corrupt_zip_gracefully():
    """A truncated/corrupt buffer that merely starts with the ZIP magic
    bytes must not raise — it should just fail to match DOCX."""
    from app.modules.attachments.content_types import bytes_match_claimed

    corrupt_zip_bytes = b"PK\x03\x04" + b"\x00" * 32
    assert bytes_match_claimed(_DOCX_CONTENT_TYPE, corrupt_zip_bytes) is False


def test_docx_zip_bomb_rejected():
    """An entry larger than MAX_ATTACHMENT_SIZE is treated as a zip bomb —
    not a DOCX match, and text extraction returns None without parsing."""
    from app.modules.attachments.content import MAX_ATTACHMENT_SIZE
    from app.modules.attachments.content_types import _docx_zip_bomb, bytes_match_claimed

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # Highly compressible payload that expands past the per-entry cap.
        archive.writestr("word/document.xml", b"0" * (MAX_ATTACHMENT_SIZE + 1))
        archive.writestr("[Content_Types].xml", b"<Types/>")
    bomb_bytes = buf.getvalue()

    assert _docx_zip_bomb(bomb_bytes) is True
    assert bytes_match_claimed(_DOCX_CONTENT_TYPE, bomb_bytes) is False
    assert extract_text_details(_DOCX_CONTENT_TYPE, bomb_bytes) is None


def test_bytes_match_claimed_rejects_spoofed_image():
    from app.modules.attachments.content_types import bytes_match_claimed

    png_header = b"\x89PNG\r\n\x1a\n" + b"fake"
    assert bytes_match_claimed("image/png", png_header) is True
    assert bytes_match_claimed("image/png", b"#!/bin/bash\n") is False
    assert bytes_match_claimed("text/plain", b"hello") is True
    assert bytes_match_claimed("text/plain", b"hello\x00world") is False
    assert bytes_match_claimed("text/plain", b"\xff\xfe not utf-8") is False
    assert bytes_match_claimed("text/plain", png_header) is False
    assert bytes_match_claimed("application/json", b'{"ok": true}') is True


def test_extract_text_from_pdf_bytes():
    # Minimal PDF with a single empty page — extraction may return None; should not raise.
    minimal_pdf = (
        b"%PDF-1.1\n1 0 obj<<>>endobj\n2 0 obj<< /Length 3>>stream\n \nendstream\n"
        b"endobj\n3 0 obj<< /Type /Catalog /Pages 4 0 R>>endobj\n"
        b"4 0 obj<< /Type /Pages /Kids [5 0 R] /Count 1>>endobj\n"
        b"5 0 obj<< /Type /Page /Parent 4 0 R /MediaBox [0 0 3 3]>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \ntrailer<< /Root 3 0 R /Size 6>>\nstartxref\n0\n%%EOF"
    )
    result = extract_text_details("application/pdf", minimal_pdf)
    assert result is None or isinstance(result.text, str)


def test_extract_text_from_docx_bytes():
    import io

    from docx import Document

    document = Document()
    document.add_paragraph("Hello from a Word document.")
    buf = io.BytesIO()
    document.save(buf)

    result = extract_text_details(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buf.getvalue(),
    )
    assert result is not None
    assert result.text == "Hello from a Word document."


def test_extract_text_from_legacy_doc_returns_none():
    # No pure-Python parser for legacy .doc — must return None, not raise.
    doc_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32
    assert extract_text_details("application/msword", doc_bytes) is None


@pytest.mark.asyncio
async def test_extract_text_details_async_runs_in_a_document_worker(monkeypatch):
    import threading

    from app.modules.attachments.content import ExtractedText, extract_text_details_async

    caller_thread = threading.current_thread()
    seen_thread: dict[str, threading.Thread] = {}

    def spy(content_type: str, data: bytes, **kwargs: object) -> ExtractedText | None:
        seen_thread["thread"] = threading.current_thread()
        return ExtractedText(text="extracted")

    monkeypatch.setattr("app.modules.attachments.text_extract.extract_text_details", spy)

    result = await extract_text_details_async("text/plain", b"hi", Settings())

    assert result is not None
    assert result.text == "extracted"
    assert seen_thread["thread"] is not caller_thread


@pytest.mark.asyncio
async def test_extract_text_details_async_times_out_gracefully(monkeypatch):
    import time

    def slow_extract(content_type: str, data: bytes, **kwargs: object) -> str | None:
        time.sleep(0.5)
        return "should never be returned"

    monkeypatch.setattr("app.modules.attachments.text_extract.extract_text_details", slow_extract)

    from app.modules.attachments.content import extract_text_details_async

    settings = Settings(attachment_extract_timeout_seconds=0.05)
    result = await extract_text_details_async("application/pdf", b"x", settings)

    assert result is None


@pytest.mark.asyncio
async def test_format_attachment_lines_includes_file_ref():
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.attachments.content import format_attachment_lines

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=b"hello")

    lines, is_image = await format_attachment_lines(
        gateway,
        attachment_id="550e8400-e29b-41d4-a716-446655440000",
        content_type="text/plain",
        storage_key="key",
        size_bytes=5,
        settings=Settings(),
    )
    assert is_image is False
    assert lines[0] == "[File: /attachments/550e8400-e29b-41d4-a716-446655440000/file]"
    assert lines[1].startswith("[File (text/plain)]")


@pytest.mark.asyncio
async def test_format_attachment_lines_reuses_preloaded_data():
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.attachments.content import format_attachment_lines

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=b"should-not-read")

    lines, is_image = await format_attachment_lines(
        gateway,
        attachment_id="550e8400-e29b-41d4-a716-446655440000",
        content_type="text/plain",
        storage_key="key",
        size_bytes=5,
        settings=Settings(),
        data=b"hello",
    )
    assert is_image is False
    assert "hello" in lines[1]
    gateway.read_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_format_attachment_lines_gives_honest_error_for_unsupported_type():
    """Legacy .doc passes every validation check but has no parser — the
    user should be told that plainly, not shown a misleading byte-count
    placeholder that implies the content was read."""
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.attachments.content import format_attachment_lines

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32)

    lines, is_image = await format_attachment_lines(
        gateway,
        attachment_id="550e8400-e29b-41d4-a716-446655440000",
        content_type="application/msword",
        storage_key="key",
        size_bytes=40,
        settings=Settings(),
    )
    assert is_image is False
    assert "can't read this file type yet" in lines[1]


@pytest.mark.asyncio
async def test_format_attachment_lines_scanned_pdf_empty_text():
    """Image-only PDFs extract to None — tell the model (and user) honestly
    instead of a misleading byte-count placeholder."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.modules.attachments.content import format_attachment_lines

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=b"%PDF-1.4 empty-ish")

    with patch(
        "app.modules.attachments.content.extract_text_details_async",
        AsyncMock(return_value=None),
    ):
        lines, is_image = await format_attachment_lines(
            gateway,
            attachment_id="550e8400-e29b-41d4-a716-446655440000",
            content_type="application/pdf",
            storage_key="key",
            size_bytes=1200,
            settings=Settings(),
        )
    assert is_image is False
    assert "scanned" in lines[1].lower() or "OCR" in lines[1]
    assert "bytes]" not in lines[1]
    # Turn prepare must not claim OCR already ran.
    assert "did not recover" not in lines[1].lower()
    assert "background" in lines[1].lower()


@pytest.mark.asyncio
async def test_format_attachment_lines_skips_ocr_on_prepare():
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.modules.attachments.content import format_attachment_lines

    extract = AsyncMock(return_value=None)
    with patch(
        "app.modules.attachments.content.extract_text_details_async",
        extract,
    ):
        await format_attachment_lines(
            MagicMock(),
            attachment_id="550e8400-e29b-41d4-a716-446655440000",
            content_type="application/pdf",
            storage_key="key",
            size_bytes=1200,
            settings=Settings(),
            data=b"%PDF-1.4",
        )
    assert extract.await_args.kwargs.get("allow_ocr") is False


def test_unavailable_image_note_forbids_a_placeholder_story():
    from app.modules.attachments.markers import append_image_unavailable_note

    prompt_messages = [{"role": "user", "content": "What?"}]
    append_image_unavailable_note(prompt_messages)
    note = prompt_messages[0]["content"]
    assert "cannot see it" in note
    assert "placeholder" in note
    assert "failed generation" in note


# ── verify_uploaded_bytes: declared size enforcement ──────────────────────


@pytest.mark.asyncio
async def test_verify_uploaded_bytes_rejects_size_mismatch():
    """When declared_size is set, actual bytes must match exactly — a mismatch
    means the client lied at presign time (or the upload was truncated/extended)."""
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.attachments.content import verify_uploaded_bytes

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # 40 bytes
    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=png_bytes)

    _, error = await verify_uploaded_bytes(
        gateway,
        content_type="image/png",
        storage_key="user/key",
        declared_size=128,  # client claimed 128, actual is 40
    )
    assert error is not None
    assert "size" in error.lower()


@pytest.mark.asyncio
async def test_verify_uploaded_bytes_accepts_matching_size():
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.attachments.content import verify_uploaded_bytes

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # 40 bytes
    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=png_bytes)

    data, error = await verify_uploaded_bytes(
        gateway,
        content_type="image/png",
        storage_key="user/key",
        declared_size=len(png_bytes),  # matches
    )
    assert error is None
    assert data == png_bytes


@pytest.mark.asyncio
async def test_verify_uploaded_bytes_skips_size_check_when_declared_size_none():
    """Backward compat: when declared_size is not provided, the size check is skipped."""
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.attachments.content import verify_uploaded_bytes

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=png_bytes)

    data, error = await verify_uploaded_bytes(
        gateway,
        content_type="image/png",
        storage_key="user/key",
        declared_size=None,
    )
    assert error is None
    assert data == png_bytes


def test_resize_image_bytes_shrinks_large_photo():
    from PIL import Image

    from app.modules.attachments.thumbnails import resize_image_bytes

    buf = io.BytesIO()
    Image.new("RGB", (2000, 1500), color=(12, 80, 160)).save(buf, format="JPEG")
    original = buf.getvalue()
    thumb, content_type = resize_image_bytes(original, 80)
    assert content_type == "image/jpeg"
    assert len(thumb) < len(original)
    out = Image.open(io.BytesIO(thumb))
    assert max(out.size) <= 80


def test_strip_attachment_from_content_removes_image_marker():
    attachment_id = uuid4()
    other = uuid4()
    content = (
        f"Look at this.\n"
        f"[Image: /attachments/{attachment_id}/file]\n"
        f"[Image: /attachments/{other}/file]"
    )
    stripped = strip_attachment_from_content(content, attachment_id)
    assert str(attachment_id) not in stripped
    assert str(other) in stripped
    assert "Look at this." in stripped


def test_strip_attachment_from_content_keeps_caption_before_file():
    attachment_id = uuid4()
    content = (
        "Please summarize\n\n"
        f"[File: /attachments/{attachment_id}/file]\n"
        "[File (application/pdf)]\n"
        "Invoice for March\n"
        "[BEGIN UNTRUSTED CONTENT]\n"
        "secret\n"
    )
    assert strip_attachment_from_content(content, attachment_id) == "Please summarize"


def test_strip_attachment_from_content_drops_file_only_message():
    attachment_id = uuid4()
    content = (
        f"[File: /attachments/{attachment_id}/file]\n[File (application/pdf)]\nInvoice for March\n"
    )
    assert strip_attachment_from_content(content, attachment_id) == ""


def test_strip_attachment_from_content_empty_means_delete_message():
    attachment_id = uuid4()
    content = f"[Image: /attachments/{attachment_id}/file]"
    assert strip_attachment_from_content(content, attachment_id) == ""


def test_file_excerpt_limit_note_names_caps():
    from app.modules.attachments.content import file_excerpt_limit_note

    assert file_excerpt_limit_note(char_capped=False, page_capped=False) is None
    note = file_excerpt_limit_note(char_capped=True, page_capped=True)
    assert note is not None
    assert "25 pages" in note
    assert "12000" in note
    assert "unread" in note


def test_extract_text_details_flags_char_cap():
    from app.modules.attachments.content import extract_text_details

    details = extract_text_details("text/plain", ("x" * 50).encode(), max_chars=10)
    assert details is not None
    assert details.char_capped is True
    assert details.page_capped is False
    assert len(details.text) == 10


def test_docx_tables_keep_row_alignment():
    from docx import Document

    document = Document()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Score"
    table.cell(1, 0).text = "Ada"
    table.cell(1, 1).text = "12"
    buf = io.BytesIO()
    document.save(buf)
    result = extract_text_details(_DOCX_CONTENT_TYPE, buf.getvalue())
    assert result is not None
    assert "| Name | Score |" in result.text
    assert "| Ada | 12 |" in result.text


def test_prior_image_attachment_ids_skips_current_user_turn():
    from app.modules.attachments.markers import prior_image_attachment_ids

    first = uuid4()
    messages = [
        {"role": "user", "content": f"[Image: /attachments/{first}/file]"},
        {"role": "assistant", "content": "a street sign"},
        {"role": "user", "content": "what does the tiny label say?"},
    ]
    assert prior_image_attachment_ids(messages) == [first]


def test_prior_image_attachment_ids_newest_first_with_cap():
    from app.modules.attachments.markers import prior_image_attachment_ids

    older = uuid4()
    newer = uuid4()
    extra = uuid4()
    messages = [
        {"role": "user", "content": f"[Image: /attachments/{older}/file]"},
        {"role": "assistant", "content": "first"},
        {
            "role": "user",
            "content": (f"[Image: /attachments/{newer}/file]\n[Image: /attachments/{extra}/file]"),
        },
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "the second one"},
    ]
    assert prior_image_attachment_ids(messages, limit=2) == [newer, extra]


@pytest.mark.asyncio
async def test_format_attachment_lines_discloses_truncated_excerpt():
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.modules.attachments.content import ExtractedText, format_attachment_lines

    gateway = MagicMock()
    gateway.read_bytes = AsyncMock(return_value=b"hello")
    details = ExtractedText(text="hello", char_capped=True, page_capped=True)
    with patch(
        "app.modules.attachments.content.extract_text_details_async",
        AsyncMock(return_value=details),
    ):
        lines, is_image = await format_attachment_lines(
            gateway,
            attachment_id="550e8400-e29b-41d4-a716-446655440000",
            content_type="application/pdf",
            storage_key="key",
            size_bytes=5,
            settings=Settings(),
            data=b"hello",
        )
    assert is_image is False
    assert "[File note:" in lines[1]
    assert "25 pages" in lines[1]
    assert "hello" in lines[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["slow", "busy"])
async def test_a_file_not_read_in_time_is_not_called_a_scan(failure: str) -> None:
    """A parse past the turn's budget (or no free worker) is a slow file, not a scanned PDF."""
    import time
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.core.sympy_executor import WorkerBusyError
    from app.modules.attachments.content import format_attachment_lines

    def slow_parse(*_args: object, **_kwargs: object) -> None:
        time.sleep(1)

    async def busy(*_args: object, **_kwargs: object) -> None:
        raise WorkerBusyError("no document worker free")

    target = (
        patch("app.modules.attachments.text_extract.extract_text_details", slow_parse)
        if failure == "slow"
        else patch("app.modules.attachments.content.run_document", busy)
    )
    with target:
        lines, _is_image = await format_attachment_lines(
            MagicMock(read_bytes=AsyncMock()),
            attachment_id="550e8400-e29b-41d4-a716-446655440000",
            content_type="application/pdf",
            storage_key="key",
            size_bytes=5,
            settings=Settings(attachment_extract_timeout_seconds=0.1),
            data=b"%PDF-1.4",
        )

    assert "could not read it in time" in lines[1]
    assert "scanned" not in lines[1]
