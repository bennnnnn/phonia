import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.exceptions import AttachmentValidationError, ChatBusyError
from app.gateways.storage_gateway import LocalStorageGateway
from app.modules.chat.model_routing import choice as model_choice
from app.modules.chat.turn_prep import TurnPromptBundle
from app.modules.chat.turn_prep.request import TurnRequest
from app.modules.conversation import chats_repository, messages_repository
from app.modules.math.schemas import MathImageExtract
from app.tests.fakes import FakeSessionCM, redis_mock
from app.tests.modules.chat.chat_test_support import prompt_bundle


@pytest.mark.asyncio
async def test_a_turns_attached_rows_load_in_a_single_batched_query():
    from app.modules.chat.turn_prep import count_images, load_attachment_rows

    user_id = uuid4()
    attachment_ids = [uuid4(), uuid4(), uuid4()]
    image_row = MagicMock(content_type="image/png")
    pdf_row = MagicMock(content_type="application/pdf")
    session = AsyncMock()

    with patch(
        "app.modules.attachments.repository.get_by_ids",
        AsyncMock(return_value=[image_row, pdf_row]),
    ) as get_by_ids_mock:
        rows = await load_attachment_rows(session, user_id, attachment_ids)

    assert count_images(rows) == 1
    get_by_ids_mock.assert_awaited_once_with(session, attachment_ids, user_id)


@pytest.mark.asyncio
async def test_rows_the_turn_read_for_its_quota_are_not_read_again():
    """The quota read the attached rows to count images, then the turn read them again
    on a connection of its own before its first token."""
    from app.modules.chat.turn_prep.attachments import _load_turn_attachments

    user = MagicMock(id=uuid4())
    row = MagicMock(id=uuid4(), message_id=None, content_type="image/png")
    reads = AsyncMock(return_value=[row])
    # An unlinked row needs no copy: the turn's session runs nothing at all.
    with patch("app.modules.attachments.repository.get_by_ids", reads):
        _user, rows, ids = await _load_turn_attachments(
            user_id=user.id, user=user, attachment_ids=[row.id], settings=Settings(), rows=[row]
        )
    assert (rows, ids) == ([row], [row.id])
    reads.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_chat_turn_refunds_image_quota_when_r2_bytes_invalid():
    from app.modules.chat.turn_prep import prepare_chat_turn

    user_id = uuid4()
    chat_id = uuid4()
    attachment_id = uuid4()
    user = MagicMock()
    user.id = user_id
    from datetime import UTC, datetime

    row = MagicMock()
    row.source = "upload"
    row.library_visible = True
    row.created_at = datetime.now(UTC)
    row.message_id = None
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    row.size_bytes = 128
    row.verified_at = None

    settings = Settings(attachments_enabled=True)
    redis = redis_mock()
    session = AsyncMock()
    gateway = MagicMock()

    with (
        patch(
            "app.modules.chat.turn_prep.attachments.SessionLocal",
            return_value=FakeSessionCM(session),
        ),
        patch(
            "app.modules.chat.turn_prep.persist.SessionLocal", return_value=FakeSessionCM(session)
        ),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=user)),
        patch(
            "app.modules.attachments.repository.get_by_ids",
            AsyncMock(return_value=[row]),
        ),
        patch(
            "app.gateways.storage_gateway.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.content.verify_uploaded_bytes",
            AsyncMock(return_value=(None, "Uploaded bytes do not match the declared content type")),
        ),
        patch(
            "app.modules.attachments.content.purge_invalid_upload",
            AsyncMock(),
        ),
        patch(
            "app.services.quota.counters.refund",
            AsyncMock(),
        ) as refund_mock,
    ):
        with pytest.raises(AttachmentValidationError):
            await prepare_chat_turn(
                user_id=user_id,
                chat_id=chat_id,
                content="hi",
                model_alias=None,
                settings=settings,
                redis=redis,
                reserved_tokens=100,
                attachment_ids=[attachment_id],
            )

    refund_mock.assert_awaited_once_with("image_upload", redis, user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("linked_count", [1, 0])
async def test_prepare_chat_turn_threads_image_math_extract_to_prompt_context(linked_count):
    """End-to-end coverage for the camera-math OCR block (zero coverage
    before this test): attaching an image + the exact camera trigger
    phrase must invoke extract_equation_from_image and pass the resulting
    structured MathImageExtract through to build_stream_prompt_context as
    image_math_extract — not just discard it after stringifying into the
    free-text content (Phase B item 6 fix)."""
    from app.modules.chat.turn_prep import prepare_chat_turn

    user_id = uuid4()
    chat_id = uuid4()
    attachment_id = uuid4()
    message_id = uuid4()
    camera_prompt = "Solve the math problem in this image step by step."

    user = MagicMock()
    user.id = user_id
    chat = MagicMock()
    chat.id = chat_id

    row = MagicMock()
    row.message_id = None
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    row.size_bytes = 128

    settings = Settings(attachments_enabled=True)
    redis = redis_mock()
    session = AsyncMock()
    gateway = MagicMock(spec=LocalStorageGateway)
    extracted = MathImageExtract(lhs="f(x,2)", rhs="7", variables=["x"], found=True)
    user_message = MagicMock()
    user_message.id = message_id

    captured: dict[str, object] = {}

    async def _fake_build_stream_prompt_context(request: TurnRequest, *_args: object):
        captured["image_math_extract"] = request.image_math_extract
        return prompt_bundle()

    with (
        patch(
            "app.modules.chat.turn_prep.attachments.SessionLocal",
            return_value=FakeSessionCM(session),
        ),
        patch(
            "app.modules.chat.turn_prep.persist.SessionLocal", return_value=FakeSessionCM(session)
        ),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=chat)),
        patch(
            "app.modules.attachments.repository.get_by_ids",
            AsyncMock(return_value=[row]),
        ),
        patch(
            "app.gateways.storage_gateway.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.content.format_attachment_lines",
            AsyncMock(return_value=(["[image attached]"], True)),
        ),
        patch(
            "app.modules.attachments.content.read_attachment_bytes",
            AsyncMock(return_value=b"fake-bytes"),
        ),
        patch(
            "app.modules.attachments.vision_input.inject_vision_content",
            AsyncMock(),
        ),
        patch(
            "app.modules.math.image_extract.extract_equation_from_image",
            AsyncMock(return_value=extracted),
        ) as extract_mock,
        patch.object(
            model_choice,
            "resolve_user_model_override",
            return_value="smart-chat",
        ),
        patch.object(
            messages_repository,
            "count_for_chat",
            AsyncMock(return_value=0),
        ),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[])),
        patch.object(
            messages_repository,
            "create",
            AsyncMock(return_value=user_message),
        ) as create_mock,
        patch(
            "app.modules.attachments.repository.link_to_message",
            AsyncMock(return_value=linked_count),
        ),
        patch(
            "app.modules.chat.turn_prep.prepare.build_stream_prompt_context",
            AsyncMock(side_effect=_fake_build_stream_prompt_context),
        ),
    ):
        if linked_count == 0:
            with pytest.raises(ChatBusyError, match="changed while sending"):
                await prepare_chat_turn(
                    user_id=user_id,
                    chat_id=chat_id,
                    content=camera_prompt,
                    model_alias=None,
                    settings=settings,
                    redis=redis,
                    reserved_tokens=100,
                    attachment_ids=[attachment_id],
                )
            session.rollback.assert_awaited_once()
            session.commit.assert_not_awaited()
            assert create_mock.await_args.kwargs["commit"] is False
            return
        await prepare_chat_turn(
            user_id=user_id,
            chat_id=chat_id,
            content=camera_prompt,
            model_alias=None,
            settings=settings,
            redis=redis,
            reserved_tokens=100,
            attachment_ids=[attachment_id],
        )

    extract_mock.assert_awaited_once()
    assert captured["image_math_extract"] == extracted
    saved = create_mock.await_args.kwargs["content"]
    assert "BEGIN UNTRUSTED" not in saved
    assert "[image attached]" in saved
    assert "Extracted equation" not in saved


async def _run_prepare_chat_turn_with_caption(caption: str) -> AsyncMock:
    """Shared harness for the camera-caption-edit regression tests below —
    identical to test_prepare_chat_turn_threads_image_math_extract_to_prompt_context's
    setup, parametrized only on the sent caption text. Returns the mocked
    extract_equation_from_image so callers can assert whether OCR ran."""
    from app.modules.chat.turn_prep import prepare_chat_turn

    user_id = uuid4()
    chat_id = uuid4()
    attachment_id = uuid4()
    message_id = uuid4()

    user = MagicMock()
    user.id = user_id
    chat = MagicMock()
    chat.id = chat_id

    row = MagicMock()
    row.message_id = None
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/key"
    row.size_bytes = 128

    settings = Settings(attachments_enabled=True)
    redis = redis_mock()
    session = AsyncMock()
    gateway = MagicMock(spec=LocalStorageGateway)
    extracted = MathImageExtract(lhs="2*x+3", rhs="7", variables=["x"], found=True)
    user_message = MagicMock()
    user_message.id = message_id

    async def _fake_build_stream_prompt_context(*_args: object, **kwargs: object):
        return prompt_bundle()

    with (
        patch(
            "app.modules.chat.turn_prep.attachments.SessionLocal",
            return_value=FakeSessionCM(session),
        ),
        patch(
            "app.modules.chat.turn_prep.persist.SessionLocal", return_value=FakeSessionCM(session)
        ),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=chat)),
        patch(
            "app.modules.attachments.repository.get_by_ids",
            AsyncMock(return_value=[row]),
        ),
        patch(
            "app.gateways.storage_gateway.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.content.format_attachment_lines",
            AsyncMock(return_value=(["[image attached]"], True)),
        ),
        patch(
            "app.modules.attachments.content.read_attachment_bytes",
            AsyncMock(return_value=b"fake-bytes"),
        ),
        patch(
            "app.modules.attachments.vision_input.inject_vision_content",
            AsyncMock(),
        ),
        patch(
            "app.modules.math.image_extract.extract_equation_from_image",
            AsyncMock(return_value=extracted),
        ) as extract_mock,
        patch.object(
            model_choice,
            "resolve_user_model_override",
            return_value="smart-chat",
        ),
        patch.object(
            messages_repository,
            "count_for_chat",
            AsyncMock(return_value=0),
        ),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[])),
        patch.object(
            messages_repository,
            "create",
            AsyncMock(return_value=user_message),
        ),
        patch(
            "app.modules.attachments.repository.link_to_message",
            AsyncMock(return_value=1),
        ),
        patch(
            "app.modules.chat.turn_prep.prepare.build_stream_prompt_context",
            AsyncMock(side_effect=_fake_build_stream_prompt_context),
        ),
    ):
        await prepare_chat_turn(
            user_id=user_id,
            chat_id=chat_id,
            content=caption,
            model_alias=None,
            settings=settings,
            redis=redis,
            reserved_tokens=100,
            attachment_ids=[attachment_id],
        )

    return extract_mock


@pytest.mark.asyncio
async def test_prepare_chat_turn_ocr_survives_edited_camera_caption():
    """BUG FIX regression: the OCR trigger used to require the sent text to
    be byte-for-byte identical to the preset camera caption. A user who
    edits the pre-filled composer text (adds/removes a word, autocorrect
    touches punctuation) must still get the verified OCR path as long as the
    edited caption still reads as a math ask."""
    extract_mock = await _run_prepare_chat_turn_with_caption("please solve this equation for me")
    extract_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_chat_turn_ocr_skipped_for_unrelated_caption():
    """The looser trigger must not fire vision OCR on every image attachment
    — an unrelated caption (no math keyword, not the exact camera prompt)
    should not spend a vision call on an equation that likely isn't there."""
    extract_mock = await _run_prepare_chat_turn_with_caption("here's a photo of my dog")
    extract_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caption",
    [
        "Solve the physics problem in this image step by step.",
        "Solve the biology problem in this image step by step.",
    ],
)
async def test_subject_scanners_do_not_run_math_specific_ocr(caption: str):
    """An explicit non-math scanner tab must keep the image on its vision path."""
    extract_mock = await _run_prepare_chat_turn_with_caption(caption)
    extract_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_chat_turn_skips_ocr_when_student_confirmed_reading():
    """A scanner-confirmed reading must not be overwritten by a second vision call."""
    extract_mock = await _run_prepare_chat_turn_with_caption(
        "Solve the math problem in this image step by step.\n\nI read this as: 2*x+7 = 15"
    )
    extract_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("caption", "math_reads"),
    [
        ("Solve the math problem in this image step by step.\n\nI read this as: 2*x+7 = 15", True),
        # Physics verifies its own confirmed reading; math must not claim it.
        (
            "Solve the physics problem in this image step by step.\n\n"
            "I read this as: A ball is dropped from 20 m. Find its speed.",
            False,
        ),
    ],
)
async def test_a_confirmed_reading_is_read_as_math_only_from_the_math_scanner(
    caption: str, math_reads: bool
):
    with patch("app.modules.math.ocr.extract_from_confirmed_reading", return_value=None) as read:
        extract_mock = await _run_prepare_chat_turn_with_caption(caption)
    assert read.called is math_reads
    extract_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_attachments_reuses_verified_bytes_for_format():
    """R2 verify downloads once; format must not re-read the same object."""
    from app.modules.chat.turn_prep.attachments import _process_attachments

    user_id = uuid4()
    attachment_id = uuid4()
    user = MagicMock()
    user.id = user_id
    row = MagicMock()
    row.message_id = None
    row.id = attachment_id
    row.content_type = "text/plain"
    row.storage_key = "user/doc.txt"
    row.size_bytes = 5
    row.verified_at = None
    payload = b"hello"

    settings = Settings(attachments_enabled=True)
    redis = redis_mock()
    session = AsyncMock()
    gateway = MagicMock()  # not LocalStorageGateway → R2 verify path

    format_mock = AsyncMock(return_value=(["[File: x]"], False))
    with (
        patch(
            "app.modules.chat.turn_prep.attachments.SessionLocal",
            return_value=FakeSessionCM(session),
        ),
        patch("app.modules.attachments.repository.get_by_ids", AsyncMock(return_value=[row])),
        patch(
            "app.gateways.storage_gateway.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.content.verify_uploaded_bytes",
            AsyncMock(return_value=(payload, None)),
        ) as verify_mock,
        patch(
            "app.modules.attachments.content.format_attachment_lines",
            format_mock,
        ),
        patch(
            "app.modules.attachments.content.read_attachment_bytes",
            AsyncMock(return_value=b"should-not-read"),
        ) as read_mock,
    ):
        result = await _process_attachments(
            user_id=user_id,
            user=user,
            content="hi",
            attachment_ids=[attachment_id],
            settings=settings,
            redis=redis,
            on_status=None,
        )

    verify_mock.assert_awaited_once()
    assert format_mock.await_args.kwargs["data"] == payload
    # A document's bytes are dropped once its excerpt is taken; only images keep theirs.
    assert row.storage_key not in result.bytes_by_key
    read_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_attachments_skips_verify_when_already_verified():
    from datetime import UTC, datetime

    from app.modules.chat.turn_prep.attachments import _process_attachments

    user_id = uuid4()
    attachment_id = uuid4()
    user = MagicMock()
    user.id = user_id
    row = MagicMock()
    row.message_id = None
    row.id = attachment_id
    row.content_type = "text/plain"
    row.storage_key = "user/doc.txt"
    row.size_bytes = 5
    row.verified_at = datetime(2026, 8, 1, tzinfo=UTC)

    settings = Settings(attachments_enabled=True)
    redis = redis_mock()
    session = AsyncMock()
    gateway = MagicMock()

    with (
        patch(
            "app.modules.chat.turn_prep.attachments.SessionLocal",
            return_value=FakeSessionCM(session),
        ),
        patch("app.modules.attachments.repository.get_by_ids", AsyncMock(return_value=[row])),
        patch(
            "app.gateways.storage_gateway.get_storage_gateway",
            return_value=gateway,
        ),
        patch(
            "app.modules.attachments.content.verify_uploaded_bytes",
            AsyncMock(return_value=(b"hello", None)),
        ) as verify_mock,
        patch(
            "app.modules.attachments.content.format_attachment_lines",
            AsyncMock(return_value=(["[File: x]"], False)),
        ),
        patch(
            "app.modules.attachments.content.read_attachment_bytes",
            AsyncMock(return_value=b"hello"),
        ),
    ):
        await _process_attachments(
            user_id=user_id,
            user=user,
            content="hi",
            attachment_ids=[attachment_id],
            settings=settings,
            redis=redis,
            on_status=None,
        )

    verify_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_attachments_image_only_does_not_flag_document():
    """An image-only attachment must not force rich context — images use
    vision injection (runs regardless of rich_context), and RAG is gated by
    rich_context. Forcing rich for an image turn triggers status theater +
    heavy prompt building for a plain vision QA turn."""
    from datetime import UTC, datetime

    from app.modules.chat.turn_prep.attachments import _process_attachments

    user_id = uuid4()
    attachment_id = uuid4()
    user = MagicMock()
    user.id = user_id
    row = MagicMock()
    row.message_id = None
    row.id = attachment_id
    row.content_type = "image/png"
    row.storage_key = "user/photo.png"
    row.size_bytes = 5
    row.verified_at = datetime(2026, 8, 1, tzinfo=UTC)

    settings = Settings(attachments_enabled=True)
    redis = redis_mock()
    session = AsyncMock()
    gateway = MagicMock()

    with (
        patch(
            "app.modules.chat.turn_prep.attachments.SessionLocal",
            return_value=FakeSessionCM(session),
        ),
        patch("app.modules.attachments.repository.get_by_ids", AsyncMock(return_value=[row])),
        patch("app.gateways.storage_gateway.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.content.format_attachment_lines",
            AsyncMock(return_value=(["[Image: photo.png]"], True)),
        ),
    ):
        result = await _process_attachments(
            user_id=user_id,
            user=user,
            content="what's in this photo?",
            attachment_ids=[attachment_id],
            settings=settings,
            redis=redis,
            on_status=None,
        )

    assert result.has_image_attachment is True
    assert result.has_document_attachment is False
    assert result.resolved_attachment_ids == [attachment_id]


@pytest.mark.asyncio
async def test_process_attachments_document_flags_document():
    """A document attachment flags has_document_attachment so the turn
    forces rich context (doc RAG is gated by rich_context)."""
    from datetime import UTC, datetime

    from app.modules.chat.turn_prep.attachments import _process_attachments

    user_id = uuid4()
    attachment_id = uuid4()
    user = MagicMock()
    user.id = user_id
    row = MagicMock()
    row.message_id = None
    row.id = attachment_id
    row.content_type = "text/plain"
    row.storage_key = "user/notes.txt"
    row.size_bytes = 5
    row.verified_at = datetime(2026, 8, 1, tzinfo=UTC)

    settings = Settings(attachments_enabled=True)
    redis = redis_mock()
    session = AsyncMock()
    gateway = MagicMock()

    with (
        patch(
            "app.modules.chat.turn_prep.attachments.SessionLocal",
            return_value=FakeSessionCM(session),
        ),
        patch("app.modules.attachments.repository.get_by_ids", AsyncMock(return_value=[row])),
        patch("app.gateways.storage_gateway.get_storage_gateway", return_value=gateway),
        patch(
            "app.modules.attachments.content.format_attachment_lines",
            AsyncMock(return_value=(["[File: notes.txt]"], False)),
        ),
    ):
        result = await _process_attachments(
            user_id=user_id,
            user=user,
            content="summarize this",
            attachment_ids=[attachment_id],
            settings=settings,
            redis=redis,
            on_status=None,
        )

    assert result.has_image_attachment is False
    assert result.has_document_attachment is True


def _prompt_bundle() -> TurnPromptBundle:
    return prompt_bundle(lightweight=True, rich_context=False)


@pytest.mark.asyncio
async def test_prepare_overlap_returns_before_persist_commit():
    """Prompt-ready must not wait on the Neon user-row commit."""
    from app.modules.chat.turn_prep import prepare_chat_turn
    from app.modules.chat.turn_prep.mode import _TurnMode

    persist_hold = asyncio.Event()
    create_started = asyncio.Event()

    async def slow_create(*_a: object, **kwargs: object) -> MagicMock:
        create_started.set()
        await persist_hold.wait()
        msg = MagicMock()
        msg.id = kwargs.get("message_id")
        return msg

    user = MagicMock()
    user.id = uuid4()
    chat = MagicMock()
    chat.id = uuid4()
    chat.summary = None
    mode = _TurnMode(
        lightweight=True,
        rich_context=False,
        minimal_personal=False,
        day_planning=False,
        day_reflection=False,
    )

    with (
        patch("app.modules.chat.turn_prep.persist.SessionLocal", return_value=FakeSessionCM()),
        patch.object(messages_repository, "create", side_effect=slow_create),
        patch(
            "app.modules.chat.turn_prep.prepare.build_stream_prompt_context",
            AsyncMock(return_value=_prompt_bundle()),
        ),
    ):
        ctx = await asyncio.wait_for(
            prepare_chat_turn(
                user_id=user.id,
                chat_id=chat.id,
                content="hi",
                model_alias=None,
                settings=Settings(),
                redis=redis_mock(),
                reserved_tokens=100,
                user=user,
                chat=chat,
                turn_mode=mode,
                prior_count=0,
                recent_messages=[],
                resolved_model="free-chat",
            ),
            timeout=2,
        )
        await asyncio.wait_for(create_started.wait(), timeout=2)
        persist = ctx.user_message_persist
        assert persist is not None
        assert persist.done() is False
        persist_hold.set()
        await persist

    assert ctx.user_message_persist is persist


@pytest.mark.asyncio
async def test_await_user_message_persist_clears_the_task_once():
    from app.modules.chat.turn_prep import StreamContext, await_user_message_persist

    saved: list[bool] = []

    async def persist() -> None:
        saved.append(True)

    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=10,
        max_output_tokens=50,
        user_message_persist=asyncio.create_task(persist()),
    )
    await await_user_message_persist(ctx)
    assert ctx.user_message_persist is None
    await await_user_message_persist(ctx)
    assert saved == [True]
