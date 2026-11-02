from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.schemas import EmailDraftUpdate
from app.modules.chat.email_fence import format_email_fence_body, rewrite_first_email_fence
from app.modules.chat.service import ChatsError, update_message_email
from app.tests.fakes import redis_mock


def test_email_draft_update_treats_blank_to_as_missing() -> None:
    parsed = EmailDraftUpdate(to="  ", subject="Hi", body="Hello")
    assert parsed.to is None
    assert parsed.subject == "Hi"


def test_format_email_fence_body_matches_mobile_full_text() -> None:
    assert (
        format_email_fence_body(to="a@b.com", subject="Hi", body="Hello")
        == "To: a@b.com\nSubject: Hi\n\nHello"
    )
    assert format_email_fence_body(to=None, subject="Hi", body="Hello") == "Subject: Hi\n\nHello"
    assert format_email_fence_body(to=None, subject=None, body="Hello") == "Hello"


def test_rewrite_first_email_fence_leaves_later_fences() -> None:
    content = (
        "Draft:\n```email\nTo: a@b.com\nSubject: One\n\nFirst\n```\n"
        "```email\nTo: b@c.com\nSubject: Two\n\nSecond\n```\n"
    )
    rewritten = rewrite_first_email_fence(content, to="z@z.com", subject="Short", body="Done")
    assert rewritten is not None
    assert "To: z@z.com" in rewritten
    assert "Subject: Short" in rewritten
    assert "First" not in rewritten
    assert "Subject: Two" in rewritten
    assert "Second" in rewritten


@pytest.mark.asyncio
async def test_update_message_email_rewrites_assistant_fence() -> None:
    session = AsyncMock()
    redis = redis_mock()
    user = MagicMock()
    chat_id = uuid4()
    message_id = uuid4()
    message = MagicMock()
    message.role = "assistant"
    message.content = "Here you go.\n```email\nTo: a@b.com\nSubject: Hi\n\nHello\n```\n"

    async def _update(
        _session: object, msg: MagicMock, content: str, *, commit: bool = True
    ) -> MagicMock:
        msg.content = content
        return msg

    with (
        patch("app.modules.chat.service.get_chat", AsyncMock()),
        patch(
            "app.modules.conversation.messages_repository.get_by_id",
            AsyncMock(return_value=message),
        ),
        patch(
            "app.modules.conversation.messages_repository.update_content",
            AsyncMock(side_effect=_update),
        ) as update,
    ):
        result = await update_message_email(
            session,
            redis,
            user,
            chat_id,
            message_id,
            to="b@c.com",
            subject="Bye",
            body="Shorter",
        )

    update.assert_awaited_once()
    assert "To: b@c.com" in result.content
    assert "Subject: Bye" in result.content
    assert "Shorter" in result.content
    assert "Hello" not in result.content


@pytest.mark.asyncio
async def test_update_message_email_rejects_user_role() -> None:
    message = MagicMock()
    message.role = "user"
    message.content = "```email\nTo: a@b.com\nSubject: Hi\n\nHello\n```\n"
    with (
        patch("app.modules.chat.service.get_chat", AsyncMock()),
        patch(
            "app.modules.conversation.messages_repository.get_by_id",
            AsyncMock(return_value=message),
        ),
        pytest.raises(ChatsError) as exc,
    ):
        await update_message_email(
            AsyncMock(),
            AsyncMock(),
            MagicMock(),
            uuid4(),
            uuid4(),
            to="a@b.com",
            subject="Hi",
            body="Hello",
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_message_email_requires_email_fence() -> None:
    message = MagicMock()
    message.role = "assistant"
    message.content = "No draft here."
    with (
        patch("app.modules.chat.service.get_chat", AsyncMock()),
        patch(
            "app.modules.conversation.messages_repository.get_by_id",
            AsyncMock(return_value=message),
        ),
        pytest.raises(ChatsError) as exc,
    ):
        await update_message_email(
            AsyncMock(),
            AsyncMock(),
            MagicMock(),
            uuid4(),
            uuid4(),
            to="a@b.com",
            subject="Hi",
            body="Hello",
        )
    assert exc.value.status_code == 400
    assert "email draft" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_update_message_email_404_when_missing() -> None:
    with (
        patch("app.modules.chat.service.get_chat", AsyncMock()),
        patch(
            "app.modules.conversation.messages_repository.get_by_id", AsyncMock(return_value=None)
        ),
        patch(
            "app.modules.chat.service.finalize_registry.wait_for_pending_finalize",
            AsyncMock(),
        ),
        pytest.raises(ChatsError) as exc,
    ):
        await update_message_email(
            AsyncMock(),
            AsyncMock(),
            MagicMock(),
            uuid4(),
            uuid4(),
            to="a@b.com",
            subject="Hi",
            body="Hello",
        )
    assert exc.value.status_code == 404
