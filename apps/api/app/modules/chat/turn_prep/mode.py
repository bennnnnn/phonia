from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.modules.chat.clarify_turn import follows_card
from app.modules.chat.turn_prep.reading import subject_of
from app.modules.memory import is_food_or_diet_query
from app.modules.turn_reading.capabilities import is_capabilities_question
from app.modules.turn_reading.personal import (
    is_career_personal_question,
    is_personal_advice_question,
    needs_rich_context,
)
from app.modules.turn_reading.profile_ask import (
    is_profile_fact_question,
    is_profile_recall_pushback,
    profile_question_to_answer,
)
from app.modules.turn_reading.routing import (
    is_broad_self_question,
    is_lightweight_chat_turn,
    is_short_reply,
)
from app.modules.turn_reading.turn import teaching_of
from app.modules.turn_reading.writing import draft_followup
from app.services import day_planning as day_planning_service
from app.services.text_normalize import collapse_ws


def _should_augment_web_and_tools(
    *,
    instant_reply: str | None,
    lightweight: bool,
    minimal_personal: bool,
    day_planning: bool,
    ambiguous_nearby: bool,
    rich_context: bool = True,
    needs_math: bool = False,
    needs_search: bool = False,
    needs_chem: bool = False,
) -> bool:
    """Shared gate for routing-context prefetch and web/tools augmentation.

    Evaluated at both call sites (not cached) so mid-turn ``instant_reply``
    updates still suppress augmentation the same way as before.

    Slim/casual chat (not ``rich_context``) still augments when the turn
    actually needs math, web search, or chemistry — otherwise skip prior
    messages, Tavily/SymPy, and PubChem.
    """
    if not (
        instant_reply is None
        and not lightweight
        and not minimal_personal
        and not day_planning
        and not ambiguous_nearby
    ):
        return False
    return rich_context or needs_math or needs_search or needs_chem


# "I work 9am to 5:30pm with a 45 min lunch. How many hours do I work in a
# 5-day week?" works a number out of the ones it states, and lunch is one of
# them. "How many liters of water should I drink a day?" asks for advice.
_SUM_ASK = re.compile(
    r"\bhow\s+many\s+(?:hours|minutes|mins|seconds|days|weeks|months|years)\b"
    r"|\bhow\s+(?:many|much)\b[^.?!]{0,60}\b(?:left|remain(?:s|ing)?|in\s+total|total"
    r"|altogether|(?:a|per|each)\s+(?:week|month|year))\b"
    r"|\bwhat\s+(?:fraction|percent(?:age)?)\b",
    re.IGNORECASE,
)
_ADVICE_WORD = re.compile(
    r"\b(?:should|recommend\w*|suggest\w*|need|enough|healthy|safe)\b"
    r"|\b(?:is|are)\s+(?:it|that|this|they)\s+(?:ok(?:ay)?|fine|good|bad)\b",
    re.IGNORECASE,
)
_STATED_NUMBER = re.compile(r"\d+(?:[.:]\d+)?")


def _works_out_a_sum(content: str) -> bool:
    """A number asked of at least two the line states, with no advice asked."""
    if _SUM_ASK.search(content) is None or _ADVICE_WORD.search(content) is not None:
        return False
    return len(_STATED_NUMBER.findall(content)) >= 2


def _asks_about_food(content: str) -> bool:
    """Food is the topic, not the props of a problem to solve.

    "A recipe needs 3 cups of flour for 12 cookies. How many cups for 30?" is a
    proportion, and heating 500 g of milk is physics: a subject solver claims
    both. "9am to 5:30pm with a 45 min lunch, how many hours a week?" is a sum
    over the numbers it states. None asks for a pick the user's tastes shape.
    """
    if not is_food_or_diet_query(content):
        return False
    if subject_of(content) is not None:
        return False
    return not _works_out_a_sum(content)


# Why a turn is small talk or not, for its trace line: a greeting or thanks ("social"); a
# short reply that answers the last reply's offer, or a clarify card, though alone it reads
# as small talk; or not small talk at all.
LightReason = Literal["social", "answers_offer", "answers_card", "not_light"]


@dataclass
class _TurnMode:
    lightweight: bool
    rich_context: bool
    minimal_personal: bool
    day_planning: bool
    day_reflection: bool
    advice_memory: bool = False
    # The last reply asked with a clarify card: this turn answers, it never asks.
    after_card: bool = False
    # A yes to the last reply's offer of a reminder: the To-do block loads as for the
    # request it answers (``todos.offer_reply``).
    accepted_offer: bool = False
    lightweight_reason: LightReason = "not_light"


def _turn_needs_rich_context(
    content: str,
    *,
    day_planning: bool,
    day_reflection: bool,
) -> bool:
    """Opt-in personal/tool context — default casual chat stays slim."""
    from app.modules import todos as todos_service

    if needs_rich_context(
        content,
        day_planning=day_planning,
        day_reflection=day_reflection,
    ):
        return True
    if todos_service.query_implies_todos(content):
        return True
    return False


def prior_user_texts(recent: Sequence[Any], content: str) -> list[str]:
    """User lines among the last eight messages before this turn. The current line may
    already be stored."""
    users = [
        message.content
        for message in recent[-8:]
        if message.role == "user" and isinstance(message.content, str)
    ]
    if users and collapse_ws(users[-1]) == collapse_ws(content):
        users = users[:-1]
    return users


# A draft three exchanges back is the one a follow-up changes.
_DRAFT_HISTORY = 6


def _continues_a_draft(recent: Sequence[Any], content: str) -> bool:
    """ "Email" or "make it shorter" after a draft, or what it says after "what should it say?"."""
    prior = [
        (message.role, message.content)
        for message in recent[-(_DRAFT_HISTORY + 1) :]
        if message.role in {"user", "assistant"} and isinstance(message.content, str)
    ]
    # The current line may already be stored.
    if prior and prior[-1][0] == "user" and collapse_ws(prior[-1][1]) == collapse_ws(content):
        prior = prior[:-1]
    return draft_followup(content, prior) is not None


def _last_assistant(recent: Sequence[Any]) -> str | None:
    for message in reversed(recent):
        if message.role == "assistant" and isinstance(message.content, str):
            return message.content
    return None


def classify_turn_mode(recent: Sequence[Any], content: str) -> _TurnMode:
    """Classify lightweight/rich-context/day-planning modes for a turn.

    ``recent`` is the window the turn already loaded, oldest first: a short reply
    ("yes", "no") is read against the last assistant line in it, and a draft follow-up
    against the drafts in it. Each of those used to read the messages again.
    """
    from app.modules import todos as todos_service

    minimal_personal = is_broad_self_question(content)
    day_planning = day_planning_service.is_day_planning_question(content)
    day_reflection = day_planning_service.is_day_reflection_question(content)
    prior_assistant = _last_assistant(recent) if is_short_reply(content) else None
    # After a clarify card the message answers it: the whole request, never small talk.
    after_card = follows_card(_last_assistant(recent))
    lightweight_reason = _light_reason(
        content, prior_assistant=prior_assistant, after_card=after_card
    )
    lightweight = lightweight_reason == "social"
    profile_followup = False
    if is_profile_recall_pushback(content):
        prior_users = prior_user_texts(recent, content)
        profile_followup = profile_question_to_answer(content, prior_users) is not None
    # "Yes" to "Want me to set that reminder?" is the reminder request, and so is any
    # message right after a reminder card ("Did u remove it?", "move it to 7").
    accepted_offer = todos_service.accepted_offer_in(
        content, recent
    ) is not None or todos_service.follows_reminder_card(recent)
    rich_context = (
        after_card
        or accepted_offer
        or _turn_needs_rich_context(
            content,
            day_planning=day_planning,
            day_reflection=day_reflection,
        )
    )
    if not rich_context and not lightweight:
        # A change to a draft needs what the draft had: memory for names, and
        # the profile it is signed with. A slim turn signed it "[Your Name]".
        rich_context = _continues_a_draft(recent, content)
    advice_memory = (
        (
            is_personal_advice_question(content)
            or _asks_about_food(content)
            or is_capabilities_question(content)
            or teaching_of(content)
            or is_career_personal_question(content)
            or is_profile_fact_question(content)
            or profile_followup
        )
        and not day_planning
        and not day_reflection
        and not lightweight
    )
    return _TurnMode(
        lightweight=lightweight,
        rich_context=rich_context,
        minimal_personal=minimal_personal,
        day_planning=day_planning,
        day_reflection=day_reflection,
        advice_memory=advice_memory,
        after_card=after_card,
        accepted_offer=accepted_offer,
        lightweight_reason=lightweight_reason,
    )


def _light_reason(content: str, *, prior_assistant: str | None, after_card: bool) -> LightReason:
    """Small talk on its own, then in the turn's place: after a clarify card the message
    answers it, and a short reply to an offer is the answer, not a greeting."""
    if not is_lightweight_chat_turn(content):
        return "not_light"
    if after_card:
        return "answers_card"
    if not is_lightweight_chat_turn(content, prior_assistant=prior_assistant):
        return "answers_offer"
    return "social"
