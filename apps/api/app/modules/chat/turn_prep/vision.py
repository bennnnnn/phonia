"""The images a new turn's prompt carries: this turn's photos, or the user's earlier ones.

A photo sent now is injected from the bytes attachment processing already read. A
follow-up about an earlier photo reads that photo again, so the model looks at it
rather than at its marker, and is told plainly when it is gone. Only the user's own
photos go back in: a picture Recall generated is the model's own work, and sending
it again would move every later turn onto a photo model for nothing.

An earlier photo is read again only while the conversation is still about it: it
was sent in the user's previous message (the reply in between was about it), or
this message names a picture ("the photo", "that screenshot": the image intents'
nouns plus the words people use for a picture they sent). Otherwise every later turn of a chat that once had a
photo downloaded it again and ran on the vision model. A storage outage here
cannot fail the turn: the user's message is already saved, so the turn goes on
without the photo and the model is told it cannot see it.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.core.db import SessionLocal
from app.gateways.storage_gateway import (
    StorageGateway,
    StorageUnavailableError,
    get_storage_gateway,
)
from app.models.orm import User
from app.modules.attachments import content as attachment_content
from app.modules.attachments import markers as attachment_markers
from app.modules.attachments import service as attachments_service
from app.modules.attachments import vision_input
from app.modules.chat.turn_prep.attachments import _AttachmentProcessResult
from app.modules.images.gen_intent import IMAGE_NOUNS

logger = logging.getLogger(__name__)


async def inject_turn_images(
    prompt_messages: list[dict[str, Any]],
    attachments: _AttachmentProcessResult,
    *,
    caption: str,
    settings: Settings,
    user: User,
) -> bool:
    """Put this turn's images, or else the previous turn's, into the last user message.

    Returns True when the previous turn's images went back in: the turn must then
    run on the vision model.
    """
    if (
        attachments.has_image_attachment
        and attachments.image_attachments
        and attachments.gateway is not None
    ):
        await vision_input.inject_vision_content(
            prompt_messages,
            attachments.gateway,
            attachments.image_attachments,
            settings=settings,
            caption=caption,
            bytes_by_key=attachments.bytes_by_key,
        )
        return False
    if attachments.has_image_attachment or not settings.attachments_enabled:
        return False
    return await _inject_prior_images(
        prompt_messages, attachments.gateway, caption=caption, settings=settings, user=user
    )


# The image intents' nouns, plus what people call a picture they sent rather than
# one they want drawn.
_PICTURE_NOUNS = IMAGE_NOUNS | frozenset(
    {
        "photograph",
        "photographs",
        "screenshot",
        "screenshots",
        "snapshot",
        "snapshots",
        "selfie",
        "selfies",
    }
)


def names_a_picture(text: str) -> bool:
    """True when the message refers to a picture by name ("in the photo", "this screenshot?").

    Whole words only, so "photosynthesis" or "epic" do not read as one.
    """
    words = "".join(char if char.isalnum() else " " for char in text.lower()).split()
    return any(word in _PICTURE_NOUNS for word in words)


def _prior_photo_still_in_play(user_turns: list[dict[str, Any]], caption: str) -> bool:
    """The previous user message carried a photo, or this one names a picture."""
    return attachment_markers.previous_user_turn_has_image(user_turns) or names_a_picture(caption)


def _sent_in(prompt_messages: list[dict[str, Any]], uid: Any) -> int | None:
    """The index of the earlier user message whose marker names photo ``uid``."""
    users = [i for i, message in enumerate(prompt_messages) if message.get("role") == "user"]
    for index in reversed(users[:-1]):
        content = prompt_messages[index].get("content")
        if isinstance(content, str) and uid in attachment_markers.image_attachment_ids_from_text(
            content
        ):
            return index
    return None


async def _inject_prior_images(
    prompt_messages: list[dict[str, Any]],
    gateway: StorageGateway | None,
    *,
    caption: str,
    settings: Settings,
    user: User,
) -> bool:
    user_turns = [message for message in prompt_messages if message.get("role") == "user"]
    prior_ids = attachment_markers.prior_image_attachment_ids(user_turns)
    if not prior_ids or not _prior_photo_still_in_play(user_turns, caption):
        return False
    rehydrate_gateway = gateway or get_storage_gateway(settings)
    async with SessionLocal() as session:
        rows = await attachments_service.get_by_ids(session, prior_ids, user.id)
    by_id = {row.id: row for row in rows}
    # Each photo back in the message that sent it: "Smart" after a screenshot is a reply
    # to the answer, and with the photo on it the model described the screenshot again
    # (live chat, 2026-10-25). A question about a photo still sees it.
    groups: dict[int | None, list[tuple[str, str]]] = {}
    for uid in prior_ids:
        row = by_id.get(uid)
        if row is not None and attachment_content.is_image_content_type(row.content_type):
            groups.setdefault(_sent_in(prompt_messages, uid), []).append(
                (row.content_type, row.storage_key)
            )
    images = [image for group in groups.values() for image in group]
    injected = missed = False
    for sent_at, group in groups.items():
        try:
            done = await vision_input.inject_vision_content(
                prompt_messages,
                rehydrate_gateway,
                group,
                settings=settings,
                caption="" if sent_at is not None else caption,
                at_index=sent_at,
            )
        except StorageUnavailableError:
            logger.warning("Earlier photo unreadable: storage unavailable user_id=%s", user.id)
            done = False
        injected = injected or done
        missed = missed or not done
    if not injected or missed or len(images) < len(prior_ids):
        attachment_markers.append_image_unavailable_note(prompt_messages)
    return injected
