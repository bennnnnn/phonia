"""A loan, card or savings question: the money module's block and card for this turn.

It runs beside the rest of the prompt's preparation. One request of a multi-part
message may be the money one; the first part that reads as money is used. A part may
also change the chat's last money request ("what if i only do 3 years instead"), which
the user's earlier lines in the turn's window give, each in the parts its own turn read
(their plans are read in the pool with the message, ``reading``); the server works that
one too.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from redis.asyncio import Redis

from app.core.aio import gather_or_cancel
from app.core.config import Settings
from app.core.readings import kept_reading
from app.modules import todos as todos_service
from app.modules.chat.prompt_inject import inject_before_last_user
from app.modules.chat.turn_prep.instant import settings_card
from app.modules.chat.turn_prep.intents import plan_turn
from app.modules.chat.turn_prep.mode import prior_user_texts
from app.modules.chat.turn_prep.request import TurnIdentity, TurnRequest
from app.modules.turn_reading.plan import TurnPlan
from app.services.subjects.registry import MONEY

if TYPE_CHECKING:
    from app.services.subjects.registry import MoneyTurn


async def money_turn(
    request: TurnRequest,
    identity: TurnIdentity,
    settings: Settings,
    redis: Redis,
    plan: TurnPlan,
) -> MoneyTurn | None:
    if not settings.money_enabled or request.has_image_attachment:
        return None
    recent = request.recent_messages or []
    earlier = [
        _parts(line, settings.chemistry_enabled)
        for line in prior_user_texts(recent, request.content)
    ]
    last_reply = next(
        (
            message.content
            for message in reversed(recent)
            if message.role == "assistant" and isinstance(message.content, str)
        ),
        "",
    )
    for text in plan.texts() if plan.multi else (request.content,):
        turn = await MONEY.prepare(
            text,
            settings,
            redis,
            user=identity.user,
            location=identity.geo.user_location,
            earlier=earlier,
            last_reply=last_reply,
        )
        if turn is not None:
            return replace(turn, multi=plan.multi)
    # A reminder or to-do line is the to-do path's, whatever money words it holds.
    if todos_service.query_implies_todos(request.content):
        return None
    return await MONEY.prepare_standing(
        request.content,
        settings,
        redis,
        user=identity.user,
        location=identity.geo.user_location,
        earlier=earlier,
        last_reply=last_reply,
    )


def _parts(line: str, chemistry_enabled: bool) -> tuple[str, ...]:
    """An earlier line in the parts its own turn read it in, from the plan the pool made
    with the message (``reading``). A line the pool did not plan (an older one, one with no
    text) has no parts: it ends the money run, and it is never planned here, on the loop
    (golden rule 7)."""
    plan = kept_reading(plan_turn, line, chemistry_enabled=chemistry_enabled)
    if plan is None:
        return ()
    return plan.texts() if plan.multi else (line,)


def with_money_block(
    prompt_messages: list[dict[str, str]], turn: MoneyTurn | None
) -> list[dict[str, str]]:
    """The prompt with the money block before the last user message."""
    if turn is None:
        return prompt_messages
    return inject_before_last_user(prompt_messages, turn.block)


async def server_parts(
    request: TurnRequest, identity: TurnIdentity, settings: Settings, redis: Redis, plan: TurnPlan
) -> tuple[str | None, MoneyTurn | None]:
    """The server's own parts of the reply: a multi-part settings card, a money card."""
    card, money = await gather_or_cancel(
        settings_card(identity, settings, redis, plan),
        money_turn(request, identity, settings, redis, plan),
    )
    return card, money
