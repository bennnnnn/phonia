from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.attachments.content import ExtractedText
from app.modules.attachments.rag import index_attachment, retrieve_for_prompt
from app.services.chunking import chunk_text


def _session_cm():
    @asynccontextmanager
    async def _cm(*_args, **_kwargs):
        yield MagicMock()

    return _cm


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_single_chunk():
    assert chunk_text("hello world", chunk_chars=100) == ["hello world"]


def test_chunk_text_overlaps():
    text = "a" * 50 + "b" * 50 + "c" * 50
    chunks = chunk_text(text, chunk_chars=60, overlap=10)
    assert len(chunks) >= 2
    assert all(len(c) <= 60 for c in chunks)
    # Overlap means consecutive chunks share content
    assert chunks[0][-5:] in chunks[1] or chunks[0][-10:][:5] in chunks[1]


def test_chunk_text_terminates_when_overlap_meets_or_exceeds_chunk_size():
    """A misconfigured overlap >= chunk_chars must not spin forever — `start`
    has to strictly advance every iteration regardless of the configured
    overlap. This test itself is the regression check: it would hang the
    whole suite if the guard regressed."""
    text = "".join(chr(ord("a") + (i % 26)) for i in range(500))
    chunks = chunk_text(text, chunk_chars=60, overlap=60)
    # Bounded and non-degenerate: strictly fewer chunks than characters (a
    # stalled `start` would instead spin until something else killed the
    # process), and the final chunk actually reaches the end of the input —
    # proof `start` advanced all the way through rather than looping on the
    # same window forever.
    assert 0 < len(chunks) < len(text)
    assert chunks[-1].endswith(text[-1])


@pytest.mark.asyncio
async def test_retrieve_for_prompt_includes_filename_and_page():
    settings = Settings(mock_llm_enabled=True, attachment_rag_enabled=True)
    att_id = uuid4()
    chunk = MagicMock()
    chunk.attachment_id = att_id
    chunk.text = "[page 3] hello from notes"
    file_row = MagicMock()
    file_row.id = att_id
    file_row.original_filename = "notes.pdf"
    file_row.index_coverage_json = None

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.chunks_repo.has_chunks_for_chat",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.get_or_embed_query",
            AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "app.modules.attachments.rag.chunks_repo.search_semantic",
            AsyncMock(return_value=[chunk]),
        ),
        patch(
            "app.modules.attachments.rag.attachments_repo.get_by_ids",
            AsyncMock(return_value=[file_row]),
        ),
        patch("app.modules.attachments.rag.chunks_repo.EMBEDDING_DIM", 1536),
    ):
        block = await retrieve_for_prompt(
            settings=settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            query="summarize page 3",
        )

    assert "(notes.pdf)" in block
    assert "[page 3] hello from notes" in block
    assert "first 500 PDF pages" in block


@pytest.mark.asyncio
async def test_retrieve_for_prompt_miss_is_not_not_in_file():
    settings = Settings(mock_llm_enabled=True, attachment_rag_enabled=True)

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.chunks_repo.has_chunks_for_chat",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.get_or_embed_query",
            AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "app.modules.attachments.rag.chunks_repo.search_semantic",
            AsyncMock(return_value=[]),
        ),
        patch("app.modules.attachments.rag.chunks_repo.EMBEDDING_DIM", 1536),
    ):
        block = await retrieve_for_prompt(
            settings=settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            query="what is on page 30?",
        )

    assert "none matched" in block.lower()
    assert "not proof" in block.lower()
    assert "Do not invent" in block


@pytest.mark.asyncio
async def test_retrieve_for_prompt_degrades_on_db_error_instead_of_raising():
    """BUG FIX: a pgvector/DB-level error in search_semantic used to have no
    catch anywhere in this call chain and would propagate up to fail the
    whole chat turn. RAG is best-effort context, same as memory/todos/
    projects — it must degrade to no-context instead."""
    settings = Settings(mock_llm_enabled=True)
    user_id = uuid4()
    chat_id = uuid4()

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.chunks_repo.has_chunks_for_chat",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.embed_text",
            AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "app.modules.attachments.rag.chunks_repo.search_semantic",
            AsyncMock(side_effect=RuntimeError("db exploded")),
        ),
        patch("app.modules.attachments.rag.chunks_repo.EMBEDDING_DIM", 1536),
    ):
        block = await retrieve_for_prompt(
            settings=settings,
            user_id=user_id,
            chat_id=chat_id,
            query="what does the attached PDF say?",
        )

    assert block == ""


@pytest.mark.asyncio
async def test_retrieve_for_prompt_skips_embed_when_no_chunks():
    settings = Settings(mock_llm_enabled=True)
    embed_mock = AsyncMock(return_value=[0.1] * 1536)

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.chunks_repo.has_chunks_for_chat",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.embed_text",
            embed_mock,
        ),
    ):
        block = await retrieve_for_prompt(
            settings=settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            query="what does the attached PDF say?",
        )

    assert block == ""
    embed_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_for_prompt_times_out_hung_embed():
    settings = Settings(mock_llm_enabled=True)

    async def _hang(_settings, _text):
        import asyncio

        await asyncio.sleep(10)
        return [0.1] * 1536

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.chunks_repo.has_chunks_for_chat",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.embed_text",
            _hang,
        ),
        patch(
            "app.modules.attachments.rag._RAG_EMBED_TIMEOUT_SECONDS",
            0.05,
        ),
    ):
        block = await retrieve_for_prompt(
            settings=settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            query="what does the attached PDF say?",
        )

    assert block == ""


@pytest.mark.asyncio
async def test_index_attachment_uses_short_lived_sessions():
    """Download/extract/embed must not hold the SessionLocal opened to load the row."""
    settings = Settings(attachment_rag_enabled=True, mock_llm_enabled=True)
    row = MagicMock()
    row.id = uuid4()
    row.user_id = uuid4()
    row.storage_key = "user/doc"
    row.content_type = "text/plain"
    open_count = 0
    live = 0
    max_live = 0

    @asynccontextmanager
    async def _cm(*_args, **_kwargs):
        nonlocal open_count, live, max_live
        open_count += 1
        live += 1
        max_live = max(max_live, live)
        try:
            yield MagicMock()
        finally:
            live -= 1

    extract_called = False

    async def _extract(*_args, **_kwargs):
        nonlocal extract_called
        extract_called = True
        assert live == 0
        return ExtractedText(text="hello from the attachment")

    with (
        patch("app.modules.attachments.rag.SessionLocal", _cm),
        patch(
            "app.modules.attachments.rag.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.read_attachment_bytes",
            AsyncMock(return_value=b"hello from the attachment"),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.extract_text_details_async",
            _extract,
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.embed_text",
            AsyncMock(return_value=[0.1] * 8),
        ),
        patch(
            "app.modules.attachments.rag.chunks_repo.replace_chunks",
            AsyncMock(),
        ) as replace_mock,
        patch(
            "app.modules.attachments.rag.attachments_repo.set_index_coverage",
            AsyncMock(),
        ),
    ):
        count = await index_attachment(
            settings,
            user_id=row.user_id,
            attachment_id=row.id,
            chat_id=uuid4(),
        )

    assert extract_called is True
    assert count == 1
    assert open_count == 2
    assert max_live == 1
    replace_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_index_attachment_raises_on_storage_read_failure():
    """A failed R2 read is a transient error — index_attachment must raise so
    the worker retries, not silently return 0 (which the dedupe key would
    block from re-enqueue for 24h)."""
    from app.modules.attachments.rag import AttachmentIndexError

    settings = Settings(attachment_rag_enabled=True, mock_llm_enabled=True)
    row = MagicMock()
    row.id = uuid4()
    row.user_id = uuid4()
    row.storage_key = "user/doc"
    row.content_type = "text/plain"

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.read_attachment_bytes",
            AsyncMock(return_value=b""),  # empty = read failure
        ),
    ):
        with pytest.raises(AttachmentIndexError):
            await index_attachment(
                settings,
                user_id=row.user_id,
                attachment_id=row.id,
                chat_id=uuid4(),
            )


@pytest.mark.asyncio
async def test_index_attachment_filters_null_embeddings_and_raises_on_all_fail():
    """When some chunks embed and some fail, store only the successful ones.
    When ALL fail, raise so the worker retries instead of storing dead rows."""
    from app.modules.attachments.rag import AttachmentIndexError

    settings = Settings(attachment_rag_enabled=True, mock_llm_enabled=True)
    row = MagicMock()
    row.id = uuid4()
    row.user_id = uuid4()
    row.storage_key = "user/doc"
    row.content_type = "text/plain"

    # Two chunks: first embeds, second fails (None)
    embed_results = iter([[0.1] * 1536, None])

    async def _embed(_settings, texts, *, concurrency):
        return [next(embed_results) for _ in texts]

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.read_attachment_bytes",
            AsyncMock(return_value=b"chunk one. chunk two."),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.extract_text_details_async",
            AsyncMock(return_value=ExtractedText(text="chunk one. chunk two.")),
        ),
        patch(
            "app.modules.attachments.rag.ocr_allowance.recall_ocr_text",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.embed_many",
            _embed,
        ),
        patch(
            "app.modules.attachments.rag.chunks_repo.replace_chunks",
            AsyncMock(),
        ) as replace_mock,
        patch(
            "app.modules.attachments.rag.attachments_repo.set_index_coverage",
            AsyncMock(),
        ),
    ):
        count = await index_attachment(
            settings,
            user_id=row.user_id,
            attachment_id=row.id,
            chat_id=uuid4(),
        )

    # Only the successful chunk is stored
    assert count == 1
    stored_chunks = replace_mock.call_args.kwargs["chunks"]
    assert len(stored_chunks) == 1
    assert stored_chunks[0][2] is not None

    # Now test all-fail → raises
    embed_results_all_fail = iter([None, None])

    async def _embed_all_fail(_settings, texts, *, concurrency):
        return [next(embed_results_all_fail) for _ in texts]

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.read_attachment_bytes",
            AsyncMock(return_value=b"chunk one. chunk two."),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.extract_text_details_async",
            AsyncMock(return_value=ExtractedText(text="chunk one. chunk two.")),
        ),
        patch(
            "app.modules.attachments.rag.ocr_allowance.recall_ocr_text",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.embed_many",
            _embed_all_fail,
        ),
        patch(
            "app.modules.attachments.rag.chunks_repo.replace_chunks",
            AsyncMock(),
        ),
    ):
        with pytest.raises(AttachmentIndexError):
            await index_attachment(
                settings,
                user_id=row.user_id,
                attachment_id=row.id,
                chat_id=uuid4(),
            )


@pytest.mark.asyncio
async def test_index_attachment_embeds_under_shared_concurrency_in_chunk_order():
    """Chunks embed under the shared ``embedding_concurrency`` (the gateway caps requests in
    flight) and are stored in chunk order, with the failed chunk dropped (not a dead null row)."""
    settings = Settings(
        attachment_rag_enabled=True,
        attachment_rag_chunk_chars=40,
        attachment_rag_chunk_overlap=0,
        embedding_concurrency=3,
    )
    row = MagicMock()
    row.id = uuid4()
    row.user_id = uuid4()
    row.storage_key = "user/doc"
    row.content_type = "text/plain"
    text = " ".join(
        f"Section {index} of the lease covers notice and deposits." for index in range(4)
    )
    pieces = chunk_text(text, chunk_chars=40, overlap=0)
    assert len(pieces) > 3
    seen: dict = {}

    async def _embed_many(_settings, texts, *, concurrency):
        seen["texts"], seen["concurrency"] = texts, concurrency
        return [None if piece == pieces[2] else [float(len(piece))] for piece in texts]

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.read_attachment_bytes",
            AsyncMock(return_value=text.encode()),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.extract_text_details_async",
            AsyncMock(return_value=ExtractedText(text=text)),
        ),
        patch(
            "app.modules.attachments.rag.ocr_allowance.recall_ocr_text",
            AsyncMock(return_value=None),
        ),
        patch("app.modules.attachments.rag.embedding_gateway.embed_many", _embed_many),
        patch(
            "app.modules.attachments.rag.chunks_repo.replace_chunks",
            AsyncMock(return_value=True),
        ) as replace_mock,
        patch(
            "app.modules.attachments.rag.attachments_repo.set_index_coverage",
            AsyncMock(),
        ),
    ):
        count = await index_attachment(
            settings, user_id=row.user_id, attachment_id=row.id, chat_id=uuid4()
        )

    assert seen == {"texts": pieces, "concurrency": 3}
    assert count == len(pieces) - 1
    assert replace_mock.call_args.kwargs["chunks"] == [
        (index, piece, [float(len(piece))]) for index, piece in enumerate(pieces) if index != 2
    ]


@pytest.mark.asyncio
async def test_index_attachment_uses_higher_extraction_cap_for_indexing():
    """Indexing uses MAX_INDEX_EXTRACT_CHARS (200k), not the inline excerpt cap."""
    settings = Settings(attachment_rag_enabled=True, mock_llm_enabled=True)
    row = MagicMock()
    row.id = uuid4()
    row.user_id = uuid4()
    row.storage_key = "user/doc"
    row.content_type = "text/plain"

    captured: dict = {}

    async def _extract(_ct, _data, _settings, *, max_chars=12000, ocr_max_pages=None, **_k):
        captured["max_chars"] = max_chars
        captured["ocr_max_pages"] = ocr_max_pages
        return ExtractedText(text="text content")

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.read_attachment_bytes",
            AsyncMock(return_value=b"text content"),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.extract_text_details_async",
            _extract,
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.embed_text",
            AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "app.modules.attachments.rag.chunks_repo.replace_chunks",
            AsyncMock(),
        ),
        patch(
            "app.modules.attachments.rag.attachments_repo.set_index_coverage",
            AsyncMock(),
        ) as coverage_mock,
    ):
        await index_attachment(
            settings,
            user_id=row.user_id,
            attachment_id=row.id,
            chat_id=uuid4(),
        )

    from app.modules.attachments.content import MAX_INDEX_EXTRACT_CHARS

    assert captured["max_chars"] == MAX_INDEX_EXTRACT_CHARS
    assert captured["ocr_max_pages"] == settings.attachment_ocr_index_max_pages
    assert MAX_INDEX_EXTRACT_CHARS > 12000
    coverage_mock.assert_awaited_once()
    payload = coverage_mock.await_args.kwargs["coverage"]
    assert payload["via_ocr"] is False
    assert payload["max_chars"] == MAX_INDEX_EXTRACT_CHARS
    assert payload["max_pages"] == 500


@pytest.mark.asyncio
async def test_index_attachment_stores_ocr_coverage():
    settings = Settings(attachment_rag_enabled=True, mock_llm_enabled=True)
    row = MagicMock()
    row.id = uuid4()
    row.user_id = uuid4()
    row.storage_key = "user/scan"
    row.content_type = "application/pdf"

    async def _extract(*_a, **_k):
        return ExtractedText(text="scanned homework", via_ocr=True, page_capped=True)

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.attachments_repo.get_by_id",
            AsyncMock(return_value=row),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.read_attachment_bytes",
            AsyncMock(return_value=b"%PDF"),
        ),
        patch(
            "app.modules.attachments.rag.ocr_allowance.reserve_ocr",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.attachments.rag.attachment_content_service.extract_text_details_async",
            _extract,
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.embed_text",
            AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "app.modules.attachments.rag.chunks_repo.replace_chunks",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.attachments.rag.attachments_repo.set_index_coverage",
            AsyncMock(),
        ) as coverage_mock,
    ):
        count = await index_attachment(
            settings,
            user_id=row.user_id,
            attachment_id=row.id,
            chat_id=uuid4(),
        )

    assert count == 1
    payload = coverage_mock.await_args.kwargs["coverage"]
    assert payload["via_ocr"] is True
    assert payload["max_pages"] == settings.attachment_ocr_index_max_pages
    assert payload["page_capped"] is True


@pytest.mark.asyncio
async def test_retrieve_for_prompt_uses_stored_ocr_coverage():
    settings = Settings(mock_llm_enabled=True, attachment_rag_enabled=True)
    att_id = uuid4()
    chunk = MagicMock()
    chunk.attachment_id = att_id
    chunk.text = "scanned homework"
    file_row = MagicMock()
    file_row.id = att_id
    file_row.original_filename = "scan.pdf"
    file_row.index_coverage_json = (
        '{"via_ocr": true, "max_pages": 20, "max_chars": 200000, '
        '"page_capped": true, "char_capped": false}'
    )

    with (
        patch("app.modules.attachments.rag.SessionLocal", _session_cm()),
        patch(
            "app.modules.attachments.rag.chunks_repo.has_chunks_for_chat",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.attachments.rag.embedding_gateway.get_or_embed_query",
            AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "app.modules.attachments.rag.chunks_repo.search_semantic",
            AsyncMock(return_value=[chunk]),
        ),
        patch(
            "app.modules.attachments.rag.attachments_repo.get_by_ids",
            AsyncMock(return_value=[file_row]),
        ),
        patch("app.modules.attachments.rag.chunks_repo.EMBEDDING_DIM", 1536),
    ):
        block = await retrieve_for_prompt(
            settings=settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            query="what does the scan say?",
        )

    assert "first 20 OCR'd PDF pages" in block
    assert "200000" in block
    assert "first 500 PDF pages" not in block
