"""User text that reaches Postgres is storable: no NUL, no lone surrogate.

A NUL in a chat message used to pass validation, stream a whole reply and then
fail the background user-row insert, so the turn was never charged.
"""

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.core.deps import get_current_user
from app.main import create_app
from app.models.schemas import (
    AppleAuthRequest,
    ChatMessageRequest,
    ChatRename,
    EmailDraftUpdate,
    PushTokenIn,
    UserUpdate,
)
from app.models.schemas.text import NUL_REJECTED_MESSAGE, storable_text
from app.modules.attachments.schemas import AttachmentPresignIn
from app.modules.chat.stream_api import require_chat_rate_limit
from app.modules.images.schemas import ImageGenerateIn
from app.modules.memory.schemas import MemoryInstructIn, MemoryUpdate
from app.modules.speech.realtime import RealtimePersistIn, RealtimeToolIn
from app.modules.todos.schemas import TodoCreate, TodoUpdate

_CHAT = str(uuid4())
_CALL = "call-12345678"

# (schema, the field under test, the rest of a valid body)
PERSISTED_TEXT_FIELDS: list[tuple[type[BaseModel], str, dict[str, Any]]] = [
    (ChatMessageRequest, "content", {}),
    (ChatMessageRequest, "client_location", {"content": "hi"}),
    (ChatRename, "title", {}),
    (EmailDraftUpdate, "body", {}),
    (EmailDraftUpdate, "subject", {}),
    (UserUpdate, "custom_instructions", {}),
    (UserUpdate, "job", {}),
    (UserUpdate, "location", {}),
    (AppleAuthRequest, "name", {"id_token": "tok"}),
    (PushTokenIn, "device_id", {"expo_push_token": "ExponentPushToken[x]", "platform": "ios"}),
    (TodoCreate, "content", {}),
    (TodoCreate, "topic", {"content": "call mum"}),
    (TodoUpdate, "content", {}),
    (MemoryUpdate, "text", {}),
    (MemoryInstructIn, "instruction", {}),
    (ImageGenerateIn, "prompt", {"chat_id": _CHAT}),
    (ImageGenerateIn, "user_message", {"chat_id": _CHAT, "prompt": "a cat"}),
    (AttachmentPresignIn, "filename", {"content_type": "application/pdf", "size_bytes": 10}),
    (RealtimePersistIn, "user_text", {"chat_id": _CHAT, "call_id": _CALL}),
    (RealtimePersistIn, "assistant_text", {"chat_id": _CHAT, "call_id": _CALL, "user_text": "hi"}),
    (
        RealtimeToolIn,
        "query",
        {"chat_id": _CHAT, "call_id": _CALL, "turn_id": "t1", "name": "web_search"},
    ),
]


def _field_ids(case: tuple[type[BaseModel], str, dict[str, Any]]) -> str:
    return f"{case[0].__name__}.{case[1]}"


@pytest.mark.parametrize(
    "value, stored",
    [
        ("plain words", "plain words"),
        ("emoji 😀 stays", "emoji 😀 stays"),
        ("tab\tand\nnewline", "tab\tand\nnewline"),
        ("cut emoji \ud83d", "cut emoji �"),
        ("\ude00 low half", "� low half"),
        ("", ""),
    ],
)
def test_storable_text_keeps_text_and_replaces_lone_surrogates(value: str, stored: str) -> None:
    assert storable_text(value) == stored
    stored.encode("utf-8")


@pytest.mark.parametrize("value", ["\x00", "hello\x00world", "trailing\x00"])
def test_storable_text_rejects_nul(value: str) -> None:
    with pytest.raises(ValueError, match="null character"):
        storable_text(value)


@pytest.mark.parametrize("case", PERSISTED_TEXT_FIELDS, ids=_field_ids)
def test_request_schema_rejects_nul_in_persisted_text(
    case: tuple[type[BaseModel], str, dict[str, Any]],
) -> None:
    schema, field, rest = case
    with pytest.raises(ValidationError) as caught:
        schema.model_validate({**rest, field: "remember\x00this"})
    errors = caught.value.errors()
    assert errors[0]["loc"][0] == field
    assert NUL_REJECTED_MESSAGE in errors[0]["msg"]


@pytest.mark.parametrize("case", PERSISTED_TEXT_FIELDS, ids=_field_ids)
def test_request_schema_stores_lone_surrogate_as_replacement(
    case: tuple[type[BaseModel], str, dict[str, Any]],
) -> None:
    schema, field, rest = case
    parsed = schema.model_validate({**rest, field: "half an emoji \ud83d"})
    value = getattr(parsed, field)
    assert value.endswith("�")
    value.encode("utf-8")


@pytest.mark.parametrize(
    "page_text, excerpt",
    [
        ("Invoice\x00 total\x00", "[page 1] Invoice total"),
        ("\x00\x00", None),  # nothing left: no text layer
        ("plain", "[page 1] plain"),
    ],
)
def test_pdf_excerpt_drops_nul_before_it_reaches_the_user_bubble(
    page_text: str, excerpt: str | None
) -> None:
    """A document's excerpt is saved in the user's message, so it must be storable too."""
    from unittest.mock import MagicMock, patch

    from app.modules.attachments.content import extract_text_details

    page = MagicMock()
    page.extract_text.return_value = page_text
    reader = MagicMock()
    reader.pages = [page]
    with patch("pypdf.PdfReader", return_value=reader):
        details = extract_text_details("application/pdf", b"%PDF-1.7")

    assert (details.text if details else None) == excerpt


def test_chat_stream_rejects_nul_with_422_before_any_turn() -> None:
    app = create_app()
    user = AsyncMock()
    user.id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_chat_rate_limit] = lambda: AsyncMock()
    client = TestClient(app)

    response = client.post(
        f"/chats/{uuid4()}/messages/stream",
        headers={"Authorization": "Bearer tok", "Content-Type": "application/json"},
        content=b'{"content": "free tokens\\u0000please"}',
    )

    assert response.status_code == 422
    assert NUL_REJECTED_MESSAGE in response.text
