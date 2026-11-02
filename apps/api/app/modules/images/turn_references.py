"""What an image turn reads back from the chat: its earlier references, and pictures shown.

Both read inside the caller's session and only through repositories.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Attachment, Message
from app.modules.attachments import service as attachments_service
from app.modules.attachments.service import is_image_content_type
from app.modules.conversation import history as chat_history
from app.modules.images.intent import image_reference_ids


async def shown_in_chat(
    session: AsyncSession, chat_id: UUID, sources: list[Attachment]
) -> set[UUID]:
    """References that are already a reply's picture in this chat."""
    shown: set[UUID] = set()
    for source in sources:
        if source.message_id is None:
            continue
        message = await chat_history.message_in_chat(session, source.message_id, chat_id)
        if message is not None and message.role == "assistant":
            shown.add(source.id)
    return shown


async def turn_reference_ids(session: AsyncSession, turn: Message | None) -> list[UUID]:
    """The images a generated turn was made from, to make it again.

    The ones in its bubble come first, then the hidden copies linked to it
    (an edit of the picture above keeps its reference out of the bubble).
    """
    if turn is None:
        return []
    linked = await attachments_service.list_for_message_ids(session, [turn.id])
    hidden = [
        row.id
        for row in sorted(
            linked, key=lambda row: (row.created_at is None, row.created_at, str(row.id))
        )
        if is_image_content_type(row.content_type)
    ]
    return list(dict.fromkeys([*image_reference_ids(turn.content), *hidden]))[:2]
