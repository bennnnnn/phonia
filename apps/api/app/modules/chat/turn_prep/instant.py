"""Replies the server writes itself, so the turn never calls a model.

A recurring-pay estimate, what a bare algebra expression ("3x") means, the local time
or date, where the user is, a fact from their profile, a settings change to confirm, a
to-do change asked in another language (chat only reads them there: the To-do button),
and the "location not set" answer to a nearby question that has no place to search from.
"""

from __future__ import annotations

import logging
from typing import Any

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.db import SessionLocal
from app.modules import memory as memory_service
from app.modules import todos as todos_service
from app.modules import web_search as web_search_service
from app.modules.account import profile as profile_service
from app.modules.account import settings_proposal as settings_proposal_service
from app.modules.account.settings_intent import extract_settings_changes
from app.modules.chat import recurring_pay as recurring_pay_service
from app.modules.chat.turn_prep.clauses import request_body
from app.modules.chat.turn_prep.followups import SubjectFollowup
from app.modules.chat.turn_prep.request import ClientGeoContext, TurnIdentity, TurnRequest
from app.modules.memory.profile_reply import reply_for_profile_question
from app.modules.memory.switch import memory_switch_on
from app.modules.turn_reading.plan import TurnPlan
from app.modules.turn_reading.profile_ask import profile_question_to_answer
from app.services import time_context as time_context_service
from app.services.subjects.registry import subject_adapter
from app.services.text_normalize import collapse_ws

logger = logging.getLogger(__name__)

_MEMORY_IN_SETTINGS = {
    "clear": "You can delete everything Recall has saved about you in Settings → Memory.",
    "off": "You can turn memory off in Settings → Memory.",
}


def recurring_pay_reply(request: TurnRequest, local_tz: str) -> str | None:
    """A recurring-pay estimate, fully owned by local date arithmetic.

    Checked before any prompt work: building memory/RAG context and probing model
    health for a reply that never calls a model added about a second before the
    first token. A photo goes to vision instead.
    """
    if request.has_image_attachment:
        return None
    return recurring_pay_service.maybe_recurring_pay_reply(request.content, local_tz)


async def resolve_instant_reply(
    request: TurnRequest,
    identity: TurnIdentity,
    settings: Settings,
    redis: Redis,
    plan: TurnPlan | None = None,
) -> str | None:
    """Phase A: runs beside the prompt build and the fallback-model health read.

    A message with several requests has none: the clock or a settings card would
    stand in for the reply and drop the rest ("switch to dark mode, and also what is
    the capital of France?"). Its settings card goes under the reply (``settings_card``).
    """
    if plan is not None and plan.multi:
        return None
    content = request.content
    earlier = _earlier_user_texts(request.recent_messages, content)
    todo_screen = todos_service.todo_screen_reply(
        content,
        prior_user=earlier[-1] if earlier else None,
        prior_assistant=_last_recent_assistant_content(request.recent_messages),
        locale=identity.user.locale,
    )
    if todo_screen is not None:
        return todo_screen
    # "3x" alone was answered "3 times 3 is 9": what it means, an example, what to ask next.
    if not request.has_image_attachment:
        expression = subject_adapter("math").instant_reply(
            content, prior_reply=_last_recent_assistant_content(request.recent_messages)
        )
        if expression is not None:
            return expression
    # Time/location answers are CPU-only. Skip year/date/time instant-replies
    # when a photo is attached — vision should see it.
    if not request.has_image_attachment:
        now_reply = time_context_service.maybe_local_now_reply(
            content, identity.local_tz, identity.user.locale
        )
        if now_reply is not None:
            return now_reply
    if time_context_service.is_location_question(content):
        return time_context_service.format_location_answer(
            identity.geo.user_location, identity.local_tz
        )
    asked = profile_question_to_answer(
        content, _earlier_user_texts(request.recent_messages, content)
    )
    if asked:
        return await _profile_reply(asked, identity)
    # "Forget everything you know about me": chat changes no setting but the theme;
    # it says where, and never claims a wipe the model cannot do.
    reset = memory_service.memory_reset_request(content)
    if reset is not None:
        return _MEMORY_IN_SETTINGS[reset]
    settings_changes = extract_settings_changes(
        content,
        prior_assistant=_last_recent_assistant_content(request.recent_messages),
    )
    if not settings_changes:
        return None
    return await settings_proposal_service.materialize_settings_reply(
        redis, identity.user, settings_changes
    )


async def settings_card(
    identity: TurnIdentity, settings: Settings, redis: Redis, plan: TurnPlan | None
) -> str | None:
    """The settings card for the settings part of a multi-part message, under its reply.

    "Switch to dark mode and tell me a joke": the model tells the joke, and the
    card the user taps switches the theme, as a lone "switch to dark mode" does.
    """
    if plan is None or not plan.multi:
        return None
    changes = [
        change
        for part in plan.of_kind("settings")
        for change in extract_settings_changes(request_body(part.text))
    ]
    if not changes:
        return None
    return await settings_proposal_service.materialize_settings_reply(redis, identity.user, changes)


async def _profile_reply(asked: str, identity: TurnIdentity) -> str | None:
    """A saved profile detail, said without the model.

    Memory off: the model answers, from this chat or by saying memory is off. A failed
    read is not "I don't have that saved"; the model path says memory didn't load.
    """
    user = identity.user
    if not memory_switch_on(user):
        return None
    try:
        async with SessionLocal() as session:
            facts = await memory_service.active_fact_texts(session, user.id)
    except Exception:
        logger.warning("Profile reply memory read failed user_id=%s", user.id, exc_info=True)
        return None
    return reply_for_profile_question(
        asked,
        facts,
        location=profile_service.user_location_label(user),
    )


def location_not_set_reply(
    content: str, geo: ClientGeoContext, followup: SubjectFollowup
) -> str | None:
    """A nearby question with no location to search from, answered without the model.

    A question that names its own place ("best restaurant in DC") needs no location,
    and "how far does it go?" after a physics problem asks about the car, not the user.
    """
    if (
        geo.geo_query
        and not geo.has_geo_fix
        and not followup.found
        and not web_search_service.names_its_place(content)
    ):
        return web_search_service.format_location_not_set_answer()
    return None


def _earlier_user_texts(recent_messages: list[Any] | None, content: str) -> list[str]:
    texts = [
        message.content
        for message in recent_messages or []
        if getattr(message, "role", None) == "user"
        and isinstance(getattr(message, "content", None), str)
    ]
    if texts and collapse_ws(texts[-1]) == collapse_ws(content):
        texts = texts[:-1]
    return texts


def _last_recent_assistant_content(recent_messages: list[Any] | None) -> str | None:
    if not recent_messages:
        return None
    for message in reversed(recent_messages):
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)
        if role == "assistant" and isinstance(content, str) and content.strip():
            return content.strip()
    return None
