"""Turns answered without the model: a reference photo.

The photo lookup ("show me an ear", every plan; ``images.lookup_intent``) stores the
reply itself and fills the turn's outcome.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.core.sympy_executor import run_sympy
from app.exceptions import ChatServiceError
from app.models.orm import Message, User
from app.modules.chat.stream_status import StreamStatusFn, StreamStatusPhase, clip_status_detail
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import RegenerateBackup
from app.modules.chat.turn_prep.followups import role_content_dicts
from app.modules.chat.turn_trace import emit_turn_trace
from app.modules.images.lookup_intent import (
    dated_lookup_query,
    extract_image_lookup_query,
    is_reference_subject,
    names_a_drawing,
)
from app.modules.images.search import ImageSearchError
from app.services.subjects.registry import subject_adapter

logger = logging.getLogger(__name__)

_IMAGE_SEARCH_MODEL = "image-search-model"


async def _replace_old_assistant(
    deps: ChatTurnDeps,
    settings: Settings,
    *,
    chat_id: UUID,
    replace_assistant_id: UUID | None,
) -> None:
    """Regenerate swaps the earlier reply only after the new one is stored."""
    if replace_assistant_id is None:
        return
    async with deps.session_factory() as session:
        old = await deps.messages.get_by_id(session, replace_assistant_id, chat_id)
        if old is not None and old.role == "assistant":
            await deps.attachments.purge_attachments_for_messages(session, settings, [old.id])
            await deps.messages.delete_message(session, old)


async def _starting(
    outcome: TurnOutcome | None,
    on_status: StreamStatusFn | None,
    phase: StreamStatusPhase,
    detail: str,
) -> None:
    """A photo is under way. Stop cuts it off as it did (the user's row comes with its
    reply), and its label goes up as the tool loop's does: the typing dots alone sat
    there for the seconds it takes."""
    if outcome is not None:
        outcome.mark_stop_safe()
    if on_status is not None:
        await on_status(phase, clip_status_detail(detail))


def _record(outcome: TurnOutcome | None, message: Message, default_model: str) -> None:
    """A photo is the turn's reply: the turn ends here, and its trace too."""
    if outcome is not None:
        outcome.message_id = str(message.id)
        outcome.final_content = message.content
        outcome.resolved_model = message.model or default_model
    emit_turn_trace(None, outcome=outcome, path="intercept")


async def _chemistry_draws_it(settings: Settings, content: str, recent: Sequence[Any]) -> bool:
    """ "can u show me both" right after a shape answer asks for its molecules, which the
    chemistry card draws: no photo search takes the line.

    The cheap looks come first, on the line and on the chat's last question, so a photo turn
    in any other chat ("show me her") never waits on the pool. A pool that cannot read it
    leaves the line to the photo path and does not decline the turn's other readings.
    """
    followups = subject_adapter("chemistry").followups
    if not settings.chemistry_enabled or not followups.asks_to_see(content, recent):
        return False
    try:
        problem = await run_sympy(
            followups.shown_problem,
            content,
            role_content_dicts(recent),
            timeout=settings.subject_read_timeout_seconds,
        )
    except Exception:
        logger.info("shape follow-up read gave up; the line stays a photo lookup", exc_info=True)
        return False
    return problem is not None


async def _recent_rows(
    deps: ChatTurnDeps,
    settings: Settings,
    *,
    chat_id: UUID,
    recent_messages: list[Any] | None,
    replace_assistant_id: UUID | None,
) -> list[Any]:
    if recent_messages is not None:
        recent = recent_messages
    else:
        async with deps.session_factory() as session:
            recent = await deps.messages.list_recent(
                session, chat_id, limit=settings.recent_message_window
            )
    if replace_assistant_id is not None:
        recent = [row for row in recent if getattr(row, "id", None) != replace_assistant_id]
    return list(recent)


async def _photo_subject_from_chat(
    deps: ChatTurnDeps, settings: Settings, *, content: str, recent: list[Any]
) -> str | None:
    """Who "her" / "it" is in "show me her image", read from the chat; None if unclear."""
    return await deps.references.resolve_reference(
        settings,
        kind="photo",
        request=content,
        turns=deps.references.turns_from_rows(recent),
    )


async def try_image_lookup_for_turn(
    deps: ChatTurnDeps,
    settings: Settings,
    *,
    user: User,
    chat_id: UUID,
    content: str,
    outcome: TurnOutcome | None,
    create_user_message: bool,
    replace_assistant_id: UUID | None = None,
    recent_messages: list[Any] | None = None,
    misses: set[str] | None = None,
    on_status: StreamStatusFn | None = None,
) -> bool:
    """Deterministic reference-photo lookup intercept ("show me an ear").

    Failures that aren't quota-related fall through to a normal model answer
    instead of erroring the turn (a missing photo is not worth breaking chat).
    A search that ran and found no photo adds "photo" to ``misses``, so the
    turn's tool loop does not search again.
    """
    if not settings.image_search_enabled:
        return False
    query = extract_image_lookup_query(content)
    if not query:
        return False
    if is_reference_subject(query):
        recent = await _recent_rows(
            deps,
            settings,
            chat_id=chat_id,
            recent_messages=recent_messages,
            replace_assistant_id=replace_assistant_id,
        )
        query = await _photo_subject_from_chat(deps, settings, content=content, recent=recent)
        if query and names_a_drawing(query):
            # "Water and carbon dioxide molecules": drawn by the app, so the tool loop
            # offers no photo search either.
            if misses is not None:
                misses.add("photo")
            return False
        if not query:
            return False
    query = dated_lookup_query(query, datetime.now(UTC).year)
    await _starting(outcome, on_status, "finding_photo", query)
    try:
        _user_msg, asst_msg = await deps.image_search.search_and_attach_for_chat(
            settings,
            user=user,
            chat_id=chat_id,
            query=query,
            user_message_content=(content.strip() if create_user_message else None),
            create_user_message=create_user_message,
        )
    except ImageSearchError as exc:
        # At the photo cap (or the spend cap) the turn is answered in words instead.
        if exc.status_code in (404, 429, 502, 503):
            if misses is not None:
                misses.add("photo")
            return False
        raise ChatServiceError(exc.detail) from exc

    await _replace_old_assistant(
        deps, settings, chat_id=chat_id, replace_assistant_id=replace_assistant_id
    )
    _record(outcome, asst_msg, _IMAGE_SEARCH_MODEL)
    return True


async def intercept_new_turn(
    deps: ChatTurnDeps,
    settings: Settings,
    *,
    user: User,
    chat_id: UUID,
    content: str,
    outcome: TurnOutcome | None,
    recent_messages: list[Any],
    misses: set[str] | None = None,
    on_status: StreamStatusFn | None = None,
) -> bool:
    """A new message answered by a photo; True when one stored the reply.

    A lookup that ran and found nothing is added to ``misses`` ("photo").
    """
    if await _chemistry_draws_it(settings, content, recent_messages):
        # Drawn by the chemistry card: no photo, no photo tool.
        if misses is not None:
            misses.add("photo")
        return False
    return await try_image_lookup_for_turn(
        deps,
        settings,
        user=user,
        chat_id=chat_id,
        content=content,
        outcome=outcome,
        create_user_message=True,
        recent_messages=recent_messages,
        misses=misses,
        on_status=on_status,
    )


async def intercept_regenerate(
    deps: ChatTurnDeps,
    settings: Settings,
    *,
    user: User,
    chat_id: UUID,
    content: str,
    backup: RegenerateBackup | None,
    outcome: TurnOutcome | None,
    misses: set[str] | None = None,
    on_status: StreamStatusFn | None = None,
) -> bool:
    """Regenerating a photo looks up another; True when one replaced the reply.

    A lookup that ran and found nothing is added to ``misses`` ("photo").
    """
    replace_id = backup.message_id if backup is not None else None
    if subject_adapter("chemistry").followups.asks_to_see(content):
        recent = await _recent_rows(
            deps, settings, chat_id=chat_id, recent_messages=None, replace_assistant_id=replace_id
        )
        if await _chemistry_draws_it(settings, content, recent):
            if misses is not None:
                misses.add("photo")
            return False
    if backup is None or backup.model != _IMAGE_SEARCH_MODEL:
        return False
    return await try_image_lookup_for_turn(
        deps,
        settings,
        user=user,
        chat_id=chat_id,
        content=content,
        outcome=outcome,
        create_user_message=False,
        replace_assistant_id=replace_id,
        misses=misses,
        on_status=on_status,
    )
