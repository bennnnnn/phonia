"""Follow-up questions under an answer, about what the user just asked.

One structured call on ``memory-model`` reads the question and the reply. A
subject problem gets a why, a what-if and a next step; any other real question
gets the next things a person would ask about the same topic. Small talk,
drafts, personal updates and short replies make no call, and every question is
one short line in the user's voice (both rules: ``related_questions``). The
strings are cached in Redis under the assistant message id so reopening the
chat does not call the model again.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.core.background_tasks import create_background_task
from app.core.config import Settings
from app.core.readings import read_off_loop
from app.gateways.litellm_gateway import complete_structured
from app.models.routing_lanes import ROUTING
from app.modules.chat.follow_up_prompts import GENERAL_SYSTEM as _GENERAL_SYSTEM
from app.modules.chat.follow_up_prompts import SUBJECT_SYSTEM as _SYSTEM
from app.modules.chat.related_questions import (
    MAX_QUESTIONS,
    accepted_questions,
    answer_excerpt,
    follow_up_topic,
    topic_anchors,
)
from app.modules.chat.stream_accum import Completion
from app.modules.chat.stream_events import build_related_prompts_event
from app.modules.chat.turn_prep.followups import role_content_dicts
from app.services.problem_followup import message_role_content
from app.services.quota import global_spend_exceeded
from app.services.text_normalize import collapse_ws

logger = logging.getLogger(__name__)

RELATED_PROMPTS_TIMEOUT_SECONDS = 6.0
RELATED_PROMPTS_TTL_SECONDS = 7 * 24 * 60 * 60
_QUESTION_CHARS = 500
# Five short questions in JSON; 256 cut the fifth off.
_CANDIDATE_TOKENS = 384
_KEY = "related_prompts:{message_id}"
_FORGET_BATCH = 500
# The questions shown in one chat, newest first. It names the user, so the account purge
# (``purge_user_redis_keys``) drops it; a deleted chat's expires like its replies' cache.
_SHOWN_KEY = "related_prompts:shown:{user_id}:{chat_id}"
# Three replies' worth, and the user's last few lines: what a new set must not repeat.
_SHOWN_KEPT = 3 * MAX_QUESTIONS
_EARLIER_USER_LINES = 6
_EARLIER_LINE_WORDS = 20


class RelatedQuestions(BaseModel):
    # Asked for five; three are shown, so a weak one is dropped, not a failed call.
    questions: list[str] = Field(default_factory=list, max_length=2 * MAX_QUESTIONS)


async def generate_related_questions(
    settings: Settings,
    question: str,
    answer: str,
    prior: Sequence[Any] | None = None,
    *,
    allow_general: bool = True,
    shown: Sequence[str] = (),
) -> list[str]:
    """Up to three short follow-up questions about what the user asked.

    None repeats what the chat already asked: the user's earlier lines, or the questions
    ``shown`` under earlier replies. A tapped one of those stays on its problem.
    """
    # The subject readers parse with SymPy: read them in the pool, never on the loop.
    topic = await read_off_loop(
        follow_up_topic,
        question,
        answer,
        role_content_dicts(prior or []),
        allow_general=allow_general,
        shown=tuple(shown),
        timeout=settings.subject_read_timeout_seconds,
    )
    if topic is None:
        return []
    kind, problem = topic
    excerpt = answer_excerpt(answer)
    if not excerpt:
        return []
    lines = []
    if kind == "subject":
        if problem is not None and problem != question:
            lines.append(f"Problem:\n{collapse_ws(problem)[:_QUESTION_CHARS]}")
        lines.append(f"Student question:\n{collapse_ws(question)[:_QUESTION_CHARS]}")
        system = _SYSTEM
        anchors = None
    else:
        lines.append(f"Question:\n{collapse_ws(question)[:_QUESTION_CHARS]}")
        system = _GENERAL_SYSTEM
        anchors = topic_anchors(question, answer)
    lines.append(f"Reply:\n{excerpt}")
    earlier = [*_earlier_user_lines(question, problem, prior), *shown]
    if earlier:
        listed = "\n".join(f"- {collapse_ws(line)[:_QUESTION_CHARS]}" for line in earlier)
        lines.append(
            f"Already asked or suggested in this chat (never again, even reworded):\n{listed}"
        )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(lines)},
    ]
    raw = await _ask_for_questions(settings, messages)
    if raw is None:
        return []
    kept = await _accepted(settings, question, raw, problem, anchors, earlier)
    if raw and len(kept) < MAX_QUESTIONS:
        # The filter dropped some (vague, off-topic, a repeat): one more ask, for others.
        have = "\n".join(f"- {q}" for q in kept) or "- (none)"
        retry = [
            *messages,
            {
                "role": "user",
                "content": f"Kept so far:\n{have}\nWrite five different ones, same rules.",
            },
        ]
        more = await _ask_for_questions(settings, retry) or []
        kept = await _accepted(settings, question, [*kept, *more], problem, anchors, earlier)
    # Always three, or none: one or two lines read as a half-finished list.
    return kept if len(kept) == MAX_QUESTIONS else []


async def _accepted(
    settings: Settings,
    question: str,
    raw: list[str],
    problem: str | None,
    anchors: set[str] | None,
    earlier: list[str],
) -> list[str]:
    """``accepted_questions`` in the SymPy pool: it asks each candidate's subject."""
    kept = await read_off_loop(
        accepted_questions,
        question,
        raw,
        problem,
        anchors,
        earlier,
        timeout=settings.subject_read_timeout_seconds,
    )
    return kept or []


def _earlier_user_lines(
    question: str, problem: str | None, prior: Sequence[Any] | None
) -> list[str]:
    """The user's last few short lines before this one, newest first: what they asked.
    Not the problem the turn follows up (a what-if on it is the point), nor a pasted
    passage, whose every topic would read as asked."""
    lines: list[str] = []
    for message in reversed(prior or ()):
        role, content = message_role_content(message)
        if role != "user" or not content or not content.strip():
            continue
        if content in (question, problem) or len(content.split()) > _EARLIER_LINE_WORDS:
            continue
        lines.append(content)
        if len(lines) == _EARLIER_USER_LINES:
            break
    return lines


async def _ask_for_questions(
    settings: Settings, messages: list[dict[str, str]]
) -> list[str] | None:
    """The model's candidate questions, or None when the call failed or timed out."""
    try:
        parsed = await asyncio.wait_for(
            complete_structured(
                settings=settings,
                model_alias=ROUTING.background,
                messages=messages,
                schema=RelatedQuestions,
                max_tokens=_CANDIDATE_TOKENS,
                timeout_seconds=RELATED_PROMPTS_TIMEOUT_SECONDS,
                allow_fallback=False,
            ),
            timeout=RELATED_PROMPTS_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("Related questions timed out")
        return None
    except Exception:
        logger.warning("Related questions failed", exc_info=True)
        return None
    return None if parsed is None else list(parsed.questions)


def _cache_key(message_id: str) -> str:
    return _KEY.format(message_id=message_id)


async def store_related_prompts(redis: Redis, message_id: str, prompts: list[str]) -> None:
    await redis.set(
        _cache_key(message_id),
        json.dumps(prompts),
        ex=RELATED_PROMPTS_TTL_SECONDS,
    )


async def forget_related_prompts(redis: Redis, message_ids: Sequence[str]) -> int:
    """Drop cached questions for these replies. Returns how many keys went."""
    removed = 0
    keys = [_cache_key(message_id) for message_id in message_ids]
    for start in range(0, len(keys), _FORGET_BATCH):
        removed += int(await redis.unlink(*keys[start : start + _FORGET_BATCH]) or 0)
    return removed


async def shown_in_chat(redis: Redis, user_id: str, chat_id: str) -> list[str]:
    """The questions shown under this chat's last replies, newest first."""
    try:
        raw = await redis.get(_SHOWN_KEY.format(user_id=user_id, chat_id=chat_id))
        data = json.loads(raw) if isinstance(raw, (str, bytes)) and raw else []
    except Exception:
        logger.warning("Shown follow-ups read failed", exc_info=True)
        return []
    return [item for item in data if isinstance(item, str)] if isinstance(data, list) else []


async def load_related_prompts(redis: Redis, message_id: str) -> list[str]:
    """Cached questions for one assistant message. A miss does not call the model."""
    try:
        raw = await redis.get(_cache_key(message_id))
    except Exception:
        logger.warning("Related questions cache read failed", exc_info=True)
        return []
    if not isinstance(raw, str) or not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    prompts = [item.strip() for item in data if isinstance(item, str) and item.strip()]
    return prompts[:MAX_QUESTIONS]


async def _related_prompts_event(
    redis: Redis,
    settings: Settings,
    *,
    message_id: str,
    question: str,
    answer: str,
    prior: Sequence[Any] | None = None,
    allow_general: bool = True,
    chat: tuple[str, str] | None = None,
) -> dict[str, Any] | None:
    if await global_spend_exceeded(redis, settings):
        return None
    shown = await shown_in_chat(redis, *chat) if chat is not None else []
    prompts = await generate_related_questions(
        settings, question, answer, prior, allow_general=allow_general, shown=shown
    )
    if not prompts:
        return None
    try:
        # One round trip: the reply's questions, and the chat's record of what it showed.
        async with redis.pipeline(transaction=False) as pipe:
            pipe.set(_cache_key(message_id), json.dumps(prompts), ex=RELATED_PROMPTS_TTL_SECONDS)
            if chat is not None:
                user_id, chat_id = chat
                pipe.set(
                    _SHOWN_KEY.format(user_id=user_id, chat_id=chat_id),
                    json.dumps([*prompts, *shown][:_SHOWN_KEPT]),
                    ex=RELATED_PROMPTS_TTL_SECONDS,
                )
            await pipe.execute()
    except Exception:
        logger.warning("Related questions cache write failed", exc_info=True)
    return build_related_prompts_event(message_id, prompts)


def _read_by_the_turn(question: str, prior: Sequence[Any] | None) -> bool:
    """Whether ``follow_up_topic`` can run on the loop: the subjects it asks are readings
    the turn already made in the pool. It asks them of each line with its blanks
    collapsed, and the turn read the lines as written, so a line with a break or a run of
    blanks would be read again here (38 ms for a 4,000-character problem pasted over
    many lines). Such a turn's topic is read with its questions, in the pool."""
    lines = [question]
    for message in prior or ():
        role, content = message_role_content(message)
        if role == "user" and content:
            lines.append(content)
    return all(collapse_ws(line) == line for line in lines)


def schedule_related_prompts(
    redis: Redis,
    settings: Settings,
    *,
    message_id: str,
    question: str,
    answer: str,
    prior: Sequence[Any] | None = None,
    allow_general: bool = True,
    completion: Completion | None = None,
    chat: tuple[str, str] | None = None,
) -> asyncio.Task[dict[str, Any] | None] | None:
    """Start the model call without waiting. The transport sends the event after done.

    ``prior`` is the turn's recent window, which ties a "why?" to its problem.
    ``chat`` (user id, chat id) keeps the questions shown in it, so none comes back.
    ``allow_general`` is off for a turn that was never a question (a greeting,
    an instant reply); subject follow-ups do not depend on it. A reply that was
    stopped or cut off (``completion``) gets none.
    """
    if completion not in (None, "complete") or not collapse_ws(answer):
        return None
    # The questions the chat showed are read with the questions: until then any line may
    # be a tapped one, so a line on a topic of its own is not judged here.
    if _read_by_the_turn(question, prior) and (
        follow_up_topic(question, answer, prior, allow_general=allow_general, shown=None) is None
    ):
        return None
    return create_background_task(
        _related_prompts_event(
            redis,
            settings,
            message_id=message_id,
            question=question,
            answer=answer,
            prior=prior,
            allow_general=allow_general,
            chat=chat,
        ),
        name="related_prompts",
    )
