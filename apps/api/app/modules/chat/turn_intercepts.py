"""Turns answered without the model: a reference photo, or a generated image.

The photo lookup ("show me an ear", free and Pro) is checked before image
generation (Pro): see ``images.lookup_intent`` for why the two never compete for
the same words. Either one stores the reply itself and fills the turn's outcome.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.core.sympy_executor import run_sympy
from app.exceptions import ChatServiceError, SpendCapReachedError, TurnRefusedError
from app.models.orm import Message, User
from app.modules.attachments.markers import strip_attachment_from_content
from app.modules.chat.reply_language import line_language
from app.modules.chat.stream_status import StreamStatusFn, StreamStatusPhase, clip_status_detail
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import RegenerateBackup
from app.modules.chat.turn_prep.clauses import request_body
from app.modules.chat.turn_prep.followups import role_content_dicts
from app.modules.chat.turn_trace import emit_turn_trace
from app.modules.images.gen_intent import extract_image_gen_prompt, stem_subject_claims
from app.modules.images.generation import ImageGenerationError
from app.modules.images.intent import (
    image_gen_request,
    last_reply_is_generated_image,
    reads_thread,
)
from app.modules.images.lookup_intent import (
    dated_lookup_query,
    extract_image_lookup_query,
    is_reference_subject,
    names_a_drawing,
)
from app.modules.images.reply_picture import ReplyPicture
from app.modules.images.search import ImageSearchError
from app.services.subjects.registry import subject_adapter

logger = logging.getLogger(__name__)

_IMAGE_SEARCH_MODEL = "image-search-model"
_IMAGE_GEN_MODEL = "image-gen-model"


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
    """A photo or a picture is under way. Stop cuts it off as it did (the user's row
    comes with its reply), and its label goes up as the tool loop's does: the typing
    dots alone sat there for the seconds it takes."""
    if outcome is not None:
        outcome.mark_stop_safe()
    if on_status is not None:
        await on_status(phase, clip_status_detail(detail))


def _record(outcome: TurnOutcome | None, message: Message, default_model: str) -> None:
    """A photo or a picture is the turn's reply: the turn ends here, and its trace too."""
    if outcome is not None:
        outcome.message_id = str(message.id)
        outcome.final_content = message.content
        outcome.resolved_model = message.model or default_model
    emit_turn_trace(None, outcome=outcome, path="intercept")


async def _image_gen_prompt(
    deps: ChatTurnDeps,
    *,
    chat_id: UUID,
    content: str,
    create_user_message: bool,
    skip_revision_lookup: bool,
    recent_messages: list[Any] | None,
) -> tuple[str | None, list[UUID] | None]:
    """The prompt to draw, and the earlier picture an edit starts from.

    Read by ``images.intent``, which the phone's composer asks too. History is
    read only when it can change the answer.
    """
    revisions = not skip_revision_lookup
    recent: list[Any] = []
    if reads_thread(content, revisions=revisions):
        if recent_messages is not None:
            recent = recent_messages
        else:
            async with deps.session_factory() as session:
                recent = await deps.messages.list_recent(session, chat_id, limit=20)
    request = image_gen_request(content, recent, revisions=revisions)
    if request is None:
        return None, None
    # Regenerate draws again from the references the turn was first made from.
    reference_ids = (
        list(request.reference_ids) if request.revision and create_user_message else None
    )
    return request.prompt, reference_ids


async def try_image_gen_for_turn(
    deps: ChatTurnDeps,
    settings: Settings,
    *,
    user: User,
    chat_id: UUID,
    content: str,
    outcome: TurnOutcome | None,
    create_user_message: bool,
    replace_assistant_id: UUID | None = None,
    skip_revision_lookup: bool = False,
    recent_messages: list[Any] | None = None,
    on_status: StreamStatusFn | None = None,
) -> bool:
    if not deps.plan.can_use(user, "image_generation", settings):
        return False
    if stem_subject_claims(content, chemistry_enabled=settings.chemistry_enabled):
        return False
    image_prompt, reference_ids = await _image_gen_prompt(
        deps,
        chat_id=chat_id,
        content=content,
        create_user_message=create_user_message,
        skip_revision_lookup=skip_revision_lookup,
        recent_messages=recent_messages,
    )
    if not image_prompt:
        return False
    await _starting(outcome, on_status, "image_gen", image_prompt)
    try:
        _user_msg, asst_msg = await deps.image_generation.generate_for_chat(
            settings,
            user=user,
            chat_id=chat_id,
            prompt=image_prompt,
            user_message_content=(content.strip() if create_user_message else None),
            create_user_message=create_user_message,
            reference_attachment_ids=reference_ids,
        )
    except ImageGenerationError as exc:
        if exc.code == "spend_cap":
            # The picture's own line on the phone, not "new messages are paused for everyone".
            raise SpendCapReachedError(exc.message, feature="image_generation") from exc
        if exc.status_code in (403, 404):
            return False
        if exc.code in ("daily_limit", "content_blocked"):
            # The picture's own limit or the provider's refusal: said as such, not as
            # the user's chat quota being spent.
            raise TurnRefusedError(exc.message, code=exc.code, feature="image_generation") from exc
        raise ChatServiceError(exc.detail) from exc

    await _replace_old_assistant(
        deps, settings, chat_id=chat_id, replace_assistant_id=replace_assistant_id
    )
    _record(outcome, asst_msg, _IMAGE_GEN_MODEL)
    return True


async def _chemistry_draws_it(settings: Settings, content: str, recent: Sequence[Any]) -> bool:
    """ "can u show me both" right after a shape answer asks for its molecules, which the
    chemistry card draws: neither a photo search nor a generated picture takes the line.

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
    """Who "her" / "it" is in "show me her image", read from the chat; None if unclear.

    After a generated picture, "show it at night" edits that picture: the
    image-generation intercept owns it, so this returns None.
    """
    if last_reply_is_generated_image(recent):
        return None
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


def reply_picture_prompt(content: str, settings: Settings) -> str | None:
    """What to draw for the picture part of a multi-part message, if it has one."""
    from app.modules.chat.turn_prep.reading import plan_of

    plan = plan_of(content, settings)
    asked = plan.of_kind("image") if plan.multi else ()
    return extract_image_gen_prompt(request_body(asked[0].text)) if asked else None


def start_reply_picture(
    deps: ChatTurnDeps, settings: Settings, *, user: User, chat_id: UUID, content: str
) -> ReplyPicture | None:
    """The picture one part of a multi-part message asks for, drawn beside the answer.

    "Draw a cat wearing a hat and also explain what a black hole is": the intercept
    above declines the whole line, so the model answers the rest while this draws.
    """
    prompt = reply_picture_prompt(content, settings)
    if not prompt:
        return None
    # The line saying why not is in the reply's language, which follows the message. The
    # picture part is only recognised in English ("draw …"), so a message no language
    # plainly claims gets an English reply, and an English line under it.
    language = line_language(content, "en")
    if not settings.image_generation_enabled:
        return ReplyPicture.refused(prompt, "not_available", language)
    if not deps.plan.can_use(user, "image_generation", settings):
        return ReplyPicture.refused(prompt, "not_in_plan", language)
    return ReplyPicture.start(
        settings, user=user, chat_id=chat_id, prompt=prompt, language=language
    )


async def intercept_new_turn(
    deps: ChatTurnDeps,
    settings: Settings,
    *,
    user: User,
    chat_id: UUID,
    content: str,
    outcome: TurnOutcome | None,
    recent_messages: list[Any],
    prior_count: int,
    misses: set[str] | None = None,
    on_status: StreamStatusFn | None = None,
) -> bool:
    """A new message answered by a photo or a picture; True when one stored the reply.

    A lookup that ran and found nothing is added to ``misses`` ("photo").
    """
    if await _chemistry_draws_it(settings, content, recent_messages):
        # Drawn by the chemistry card: no photo, no generated picture, no photo tool.
        if misses is not None:
            misses.add("photo")
        return False
    if await try_image_lookup_for_turn(
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
    ):
        return True
    # A photo was asked for and none came back: the model answers in words. A
    # drawing would pass for a photo, and "show me a picture of Albert
    # Einstein" drew a real person.
    if settings.image_search_enabled and extract_image_lookup_query(content):
        return False
    return await try_image_gen_for_turn(
        deps,
        settings,
        user=user,
        chat_id=chat_id,
        content=content,
        outcome=outcome,
        create_user_message=True,
        skip_revision_lookup=prior_count == 0,
        recent_messages=recent_messages,
        on_status=on_status,
    )


def _image_regenerate_content(
    deps: ChatTurnDeps, content: str, backup: RegenerateBackup | None
) -> str:
    """Regenerate the recorded input, not the latest generated output.

    Edit wording need not contain "image" or satisfy short-revision heuristics.
    The persisted assistant model establishes intent.
    """
    if backup is None or backup.model != _IMAGE_GEN_MODEL:
        return content
    for ref_id in deps.image_generation.image_reference_ids(content):
        content = strip_attachment_from_content(content, ref_id)
    return f"Generate image: {content}"


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
    """Regenerating a photo or a picture makes another; True when one replaced the reply.

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
    if backup is not None and backup.model == _IMAGE_SEARCH_MODEL:
        if await try_image_lookup_for_turn(
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
        ):
            return True
    return await try_image_gen_for_turn(
        deps,
        settings,
        user=user,
        chat_id=chat_id,
        content=_image_regenerate_content(deps, content, backup),
        outcome=outcome,
        create_user_message=False,
        replace_assistant_id=replace_id,
        on_status=on_status,
    )
