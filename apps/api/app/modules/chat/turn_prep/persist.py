"""Save the user's message for a new turn, in one transaction this module owns.

The row, its attachment links and the indexable-attachment read share one session:
they commit together, and a failed write rolls them all back. Once committed, the
turn's documents are queued for indexing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import pool_liveness
from app.core.config import Settings
from app.core.db import SessionLocal
from app.exceptions import ChatBusyError, ChatNotFoundError
from app.models.orm import Chat, User
from app.modules.attachments import rag as attachment_rag
from app.modules.attachments import service as attachments_service
from app.modules.billing import plan as plan_service
from app.modules.chat.context_window import estimate_tokens
from app.modules.chat.model_routing import choice as model_choice
from app.modules.chat.model_routing.route import last_user_turn
from app.modules.chat.turn_prep.mode import _TurnMode, classify_turn_mode
from app.modules.chat.turn_timing import TurnTimingTracker
from app.modules.conversation import history as conversation_history
from app.modules.conversation import service as conversation_service
from app.repositories import users as users_repo


@dataclass(kw_only=True)
class UserTurn:
    """The message one turn saves, and who sends it.

    The caller sets what it has already read; ``persist_user_turn`` reads the rest
    in its session and fills it in. Run beside the prompt build, the persist reads
    ``model`` when it inserts the row, so the row keeps the model the turn has
    settled on by then.
    """

    user_id: UUID
    chat_id: UUID
    message_id: UUID
    # What the model is asked: a camera photo's equation is added to the text.
    content: str
    # What the chat shows: the text and the attachment markers.
    stored_content: str
    attachment_ids: list[UUID] | None
    has_image_attachment: bool
    model_alias: str | None
    recent_messages: list[Any] | None
    lesson_active: bool
    user: User | None = None
    chat: Chat | None = None
    model: str | None = None
    prior_count: int | None = None
    turn_mode: _TurnMode | None = None
    # Models whose provider is failing, as read when the turn loaded (None: not read).
    unhealthy: frozenset[str] | None = None


def turn_model(turn: UserTurn, user: User, settings: Settings) -> str:
    """The model already chosen, else the user's pick for this text.

    A photo sent with this message needs a model that reads it. An earlier photo
    only counts once the prompt build sends it again (``image_model``).
    """
    model = turn.model
    if model is None:
        prior_user, prior_model = last_user_turn(turn.recent_messages)
        model = model_choice.resolve_user_model_override(
            user,
            turn.model_alias,
            turn.content,
            settings,
            prior_user=prior_user,
            prior_model=prior_model,
            lesson_active=turn.lesson_active,
            unhealthy=turn.unhealthy or frozenset(),
        )
    if turn.has_image_attachment and settings.attachments_enabled:
        model = image_model(turn, user, settings, model)
    return model


def image_model(turn: UserTurn, user: User, settings: Settings, routed: str) -> str:
    """The model this turn runs on once it shows the model an image."""
    return plan_service.image_turn_model(
        user,
        settings,
        routed,
        explicit=plan_service.is_explicit_pick(turn.model_alias),
        unhealthy=turn.unhealthy or frozenset(),
    )


async def persist_user_turn(
    turn: UserTurn, settings: Settings, timing: TurnTimingTracker | None
) -> None:
    """Insert the user's row and link its attachments; commit once, or roll back.

    A pooled connection found dead at the first statement saves on a new one
    (``pool_liveness.run_unit``). After the commit, queue the linked documents'
    index jobs (best-effort).
    """
    if timing is not None:
        timing.mark_phase("persist_start")

    async def save(session: AsyncSession) -> list[str]:
        user = await _read_missing(session, turn, settings)
        try:
            indexable = await _insert_and_link(session, turn, user, settings)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        return indexable

    indexable = await pool_liveness.run_unit(SessionLocal, save)
    if timing is not None:
        timing.mark_phase("persist_done")
    await attachments_service.enqueue_index_jobs(
        settings, user_id=turn.user_id, chat_id=turn.chat_id, attachment_ids=indexable
    )


async def _read_missing(session: AsyncSession, turn: UserTurn, settings: Settings) -> User:
    user = turn.user
    if user is None:
        user = await users_repo.get_by_id(session, turn.user_id)
        if user is None:
            raise ChatNotFoundError("User not found.")
        turn.user = user
    chat = turn.chat
    if chat is None:
        chat = await conversation_history.get_chat(session, turn.chat_id, turn.user_id)
        if chat is None:
            raise ChatNotFoundError("Chat not found.")
        turn.chat = chat
    turn.model = turn_model(turn, user, settings)
    if turn.prior_count is None:
        turn.prior_count = await conversation_history.message_count(session, turn.chat_id)
    if turn.turn_mode is None:
        recent = turn.recent_messages
        if recent is None:
            recent = await conversation_history.recent_messages(
                session, turn.chat_id, limit=settings.recent_message_window
            )
        turn.turn_mode = classify_turn_mode(recent, turn.content)
    return user


async def _insert_and_link(
    session: AsyncSession, turn: UserTurn, user: User, settings: Settings
) -> list[str]:
    """The row and its links, uncommitted. Returns the attachment ids to index."""
    message = await conversation_service.create_message(
        session,
        chat_id=turn.chat_id,
        user_id=user.id,
        role="user",
        content=turn.stored_content,
        model=turn.model,
        input_tokens=estimate_tokens(turn.stored_content),
        commit=False,
        message_id=turn.message_id,
    )
    attachment_ids = turn.attachment_ids
    if not attachment_ids or not settings.attachments_enabled:
        return []
    linked = await attachments_service.link_to_message(
        session,
        user_id=user.id,
        attachment_ids=attachment_ids,
        message_id=message.id,
        commit=False,
    )
    if linked != len(set(attachment_ids)):
        raise ChatBusyError("An attached file changed while sending. Please retry shortly.")
    if not settings.attachment_rag_enabled:
        return []
    rows = await attachments_service.get_by_ids(session, attachment_ids, user.id)
    return [str(row.id) for row in rows if attachment_rag.is_indexable_attachment(row)]
