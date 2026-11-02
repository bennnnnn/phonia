"""Image generation request and response models."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.schemas.text import UserText
from app.services.solving import SubjectName

if TYPE_CHECKING:
    from app.models.schemas.chats import MessageOut


class ImageGenerateIn(BaseModel):
    chat_id: UUID
    prompt: UserText = Field(min_length=1, max_length=2000)
    user_message: UserText | None = Field(default=None, max_length=2000)
    aspect_ratio: UserText | None = Field(default=None, max_length=16)
    reference_attachment_ids: list[UUID] = Field(default_factory=list, max_length=2)


class ImageGenerateOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut


class ImageIntentIn(BaseModel):
    """A composer send, before it is sent. Phones before ES-05 send ``text`` alone."""

    text: str = Field(min_length=1, max_length=2000)
    # The chat it goes to; the server reads that chat's recent turns. None is a
    # draft chat with no turns yet.
    chat_id: UUID | None = None
    # An image is queued with the text, so "make it blue" edits that image.
    image_attached: bool = False


class ImageIntentOut(BaseModel):
    """How the composer sends a turn, read the way the chat turn reads it.

    ``generate_prompt`` set: draw it from the composer (``POST /images/generate``),
    with the attached image, or else ``reference_attachment_ids``, as the picture
    an edit starts from. Unset: an ordinary chat send. Phones before ES-05 read
    only ``subject`` and draw their own reading unless it is set.
    """

    # The maths, physics or chemistry subject that owns the text: never a picture.
    subject: SubjectName | None
    # A real photo the chat turn looks up ("show me an ear"); sent as chat.
    lookup_query: str | None = None
    generate_prompt: str | None = None
    # The prompt edits a picture: the chat's last generated one, or the attached one.
    revision: bool = False
    reference_attachment_ids: list[UUID] = Field(default_factory=list)
