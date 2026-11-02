"""Restore the current saved image input when regenerating its assistant answer."""

from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.core.db import SessionLocal
from app.gateways.storage_gateway import get_storage_gateway
from app.modules.attachments import content as attachment_content
from app.modules.attachments import markers as attachment_markers
from app.modules.attachments import service as attachments_service
from app.modules.attachments import vision_input


async def inject_regenerated_image_content(
    prompt_messages: list[dict[str, Any]],
    *,
    settings: Settings,
    user_id: UUID,
    attachment_ids: list[UUID],
) -> bool:
    """Read existing owned bytes without relinking, cloning, or running OCR again."""
    if not settings.attachments_enabled or not attachment_ids:
        return False
    current = next((msg for msg in reversed(prompt_messages) if msg.get("role") == "user"), None)
    if current is None or not isinstance(current.get("content"), str):
        return False
    # Preserve prompt-history safety wrapping on any adjacent file excerpts.
    caption = current["content"]
    ids = list(dict.fromkeys(attachment_ids))
    async with SessionLocal() as session:
        rows = await attachments_service.get_by_ids(session, ids, user_id)
    by_id = {row.id: row for row in rows}
    images = [
        (row.content_type, row.storage_key)
        for uid in ids
        if (row := by_id.get(uid)) is not None
        and attachment_content.is_image_content_type(row.content_type)
    ]
    injected = False
    if images:
        injected = await vision_input.inject_vision_content(
            prompt_messages,
            get_storage_gateway(settings),
            images,
            settings=settings,
            caption=caption,
        )
    loaded: dict[str, Any] = next(
        (msg for msg in reversed(prompt_messages) if msg.get("role") == "user"), {}
    )
    content = loaded.get("content")
    image_count = (
        sum(isinstance(part, dict) and part.get("type") == "image_url" for part in content)
        if isinstance(content, list)
        else 0
    )
    if image_count < len(ids):
        attachment_markers.append_image_unavailable_note(prompt_messages)
    return injected
