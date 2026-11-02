"""What a message asks of images, read with the chat so far: a real photo, a picture, or neither.

The one reader. The chat turn's intercept (``chat/turn_intercepts.py``) and the
phone's composer (``POST /images/intent``) both ask here, so a picture the
composer draws is the picture the chat turn would draw. The word rules live in
``gen_intent.py`` and ``lookup_intent.py``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.db import SessionLocal
from app.modules.conversation import history as chat_history
from app.modules.images.gen_intent import (
    extract_image_gen_prompt,
    has_non_image_subject,
    names_a_diagram,
    stem_subject,
)
from app.modules.images.gen_intent_thread import (
    could_be_image_revision,
    could_be_image_thread_followup,
    extract_image_gen_prompt_from_thread,
    extract_image_revision_prompt,
    image_gen_revision_context,
    is_deictic_subject,
    prior_user_contents_for_image_gen,
)
from app.modules.images.lookup_intent import extract_image_lookup_query, is_reference_subject

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.subjects.dispatch import SubjectName

_IMAGE_MARKER_ID = re.compile(
    r"\[Image: /attachments/([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})/file\]"
)
# Only explicit changes to an attached picture, not questions about it. Anchored, and
# the verb ends at an ASCII word edge: "make it blue" edits, "makeover ideas" does not.
_ATTACHED_EDIT = re.compile(
    r"(?:please\s+)?(?:(?:can|could) you\s+)?"
    r"(?:edit|change|remove|replace|recolor|crop|transform|turn|make)(?![0-9A-Za-z_])",
    re.IGNORECASE,
)
_MAX_ATTACHED_EDIT = 2000


@dataclass(frozen=True)
class ImageGenRequest:
    """A picture to draw. A revision edits a picture the turn starts from."""

    prompt: str
    revision: bool = False
    # The chat's last generated picture, for a revision of it.
    reference_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class ComposerImageIntent:
    """What the composer does with a send: look up a photo, draw a picture, or send it to chat."""

    # The maths, physics or chemistry subject that owns the text (never a picture).
    subject: SubjectName | None
    lookup_query: str | None = None
    request: ImageGenRequest | None = None


def image_reference_ids(content: str) -> list[UUID]:
    """The attachment ids of a message's ``[Image: …]`` markers, at most two."""
    return list(dict.fromkeys(UUID(value) for value in _IMAGE_MARKER_ID.findall(content)))[:2]


def extract_attached_image_edit_prompt(text: str) -> str | None:
    """``make it blue`` over an attached picture edits it; a question about it does not.

    Nor does text made from it: "turn this into a table", "make flashcards from this"
    and "make a caption for this photo" read the photo and answer in words.
    """
    cleaned = text.strip()
    if len(cleaned) > _MAX_ATTACHED_EDIT or _ATTACHED_EDIT.match(cleaned) is None:
        return None
    if has_non_image_subject(cleaned) or names_a_diagram(cleaned):
        return None
    return cleaned


def _could_revise(text: str) -> bool:
    trimmed = text.strip()
    too_long = not trimmed or len(trimmed) > 120 or len(trimmed.split()) > 8
    return not too_long and could_be_image_revision(text)


def reads_thread(text: str, *, revisions: bool = True) -> bool:
    """Whether the chat so far can change what ``text`` asks to draw.

    False lets a caller skip reading the history: ``image_gen_request`` gives the
    same answer with no rows.
    """
    direct = extract_image_gen_prompt(text)
    if direct:
        # "a picture of that car" draws the car named earlier in the chat.
        return is_deictic_subject(direct)
    return could_be_image_thread_followup(text) or (revisions and _could_revise(text))


def _last_reply_image_ids(recent: Sequence[Any]) -> tuple[UUID, ...]:
    for row in reversed(recent):
        if getattr(row, "role", None) == "assistant":
            return tuple(image_reference_ids(getattr(row, "content", "") or ""))
    return ()


def image_gen_request(
    text: str, recent: Sequence[Any], *, revisions: bool = True
) -> ImageGenRequest | None:
    """The picture ``text`` asks for, read with the chat's ``recent`` rows (oldest first).

    "Image" after "Dog" draws a dog, and "a picture of that car" the car named before.
    After a generated picture, a short follow-up ("make it blue") edits it; a new
    request ("draw a fox") is a new picture. ``revisions=False`` (a chat with no
    earlier turn) skips the edit reading. None when the text asks for no picture.
    """
    rows = list(recent)
    prompt = extract_image_gen_prompt_from_thread(
        text, prior_user_contents_for_image_gen(rows, text)
    )
    if prompt:
        return ImageGenRequest(prompt)
    if not (revisions and _could_revise(text)):
        return None
    last_image_only, previous_subject = image_gen_revision_context(rows)
    prompt = extract_image_revision_prompt(
        text,
        last_assistant_is_image_only=last_image_only,
        previous_subject=previous_subject,
    )
    if not prompt:
        return None
    return ImageGenRequest(prompt, revision=True, reference_ids=_last_reply_image_ids(rows))


def last_reply_is_generated_image(recent: Sequence[Any]) -> bool:
    """True when the chat's newest reply is a generated picture (not a looked-up photo)."""
    last_image_only, _subject = image_gen_revision_context(list(recent))
    return last_image_only


def photo_lookup_query(text: str, recent: Sequence[Any]) -> str | None:
    """The real photo ``text`` asks for, or None.

    After a generated picture, "show it at night" edits that picture rather than
    searching for "it at night". Who "her" names otherwise is read from the chat later.
    """
    query = extract_image_lookup_query(text)
    if query and is_reference_subject(query) and last_reply_is_generated_image(recent):
        return None
    return query


def composer_image_intent(
    text: str,
    recent: Sequence[Any],
    *,
    image_attached: bool = False,
    image_search: bool = True,
    chemistry_enabled: bool = True,
) -> ComposerImageIntent:
    """The chat turn's own reading of a composer send, before it is sent.

    A photo lookup and a maths, physics or chemistry turn go to chat. With an image
    attached the chat turn never draws, so an edit of that image ("make it blue")
    is the composer's to draw, with the attachment as its reference.
    """
    subject = stem_subject(text, chemistry_enabled=chemistry_enabled)
    request: ImageGenRequest | None
    if image_attached:
        rows = list(recent)
        prompt = extract_image_gen_prompt_from_thread(
            text, prior_user_contents_for_image_gen(rows, text)
        )
        edit = None if prompt else extract_attached_image_edit_prompt(text)
        if prompt:
            request = ImageGenRequest(prompt)
        else:
            request = ImageGenRequest(edit, revision=True) if edit else None
    else:
        query = photo_lookup_query(text, recent) if image_search else None
        if query:
            return ComposerImageIntent(subject, lookup_query=query)
        request = image_gen_request(text, recent)
    return ComposerImageIntent(subject, request=None if subject else request)


async def composer_intent_for_chat(
    settings: Settings,
    *,
    user_id: UUID,
    text: str,
    chat_id: UUID | None,
    image_attached: bool = False,
) -> ComposerImageIntent | None:
    """``composer_image_intent`` over the chat's recent window.

    None when the chat is not the user's. A draft chat with no id yet has no turns.
    """
    recent: list[Any] = []
    if chat_id is not None:
        async with SessionLocal() as session:
            if await chat_history.get_chat(session, chat_id, user_id) is None:
                return None
            recent = await chat_history.recent_messages(
                session, chat_id, limit=settings.recent_message_window
            )
    # The subject is the one reading behind this answer that parses with SymPy; read it in
    # the pool, and ``composer_image_intent`` asks it of this request's readings.
    from app.services.subjects.dispatch import read_subject

    await read_subject(text, settings)
    return composer_image_intent(
        text,
        recent,
        image_attached=image_attached,
        image_search=settings.image_search_enabled,
        chemistry_enabled=settings.chemistry_enabled,
    )
