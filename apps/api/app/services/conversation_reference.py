"""Read what a follow-up points at: "do a search", "show me her image".

Web search and the photo lookup both act on a subject the user named earlier.
A bare "do a search" after a chat about a name, or "show me her image" after
"she was born in Arles", needs that subject spelled out before Tavily sees it.
One cheap structured call reads the last few turns and returns it, or null
when the conversation does not say. Best effort: any failure returns None and
the caller keeps its deterministic fallback.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from app.core.config import Settings
from app.core.redis import get_redis_client
from app.gateways import litellm_gateway, mock_llm
from app.models.routing_lanes import ROUTING
from app.models.schemas import ConversationReference
from app.services import quota as quota_service
from app.services.text_normalize import collapse_ws

logger = logging.getLogger(__name__)

ReferenceKind = Literal["search", "photo"]
Turn = tuple[str, str]

_MAX_TURNS = 6
_MAX_TURN_CHARS = 400
_IMAGE_MARKER = "[Image:"

_INSTRUCTIONS: dict[ReferenceKind, str] = {
    "search": (
        "The user wants a live web search. Write the one search query that finds what "
        "they want, using the conversation to fill in who or what they mean: a name, "
        "a place, the claim they doubt. 3 to 10 words, the way a person types into a "
        "search engine. Keep names, places and dates. No quotes, no 'search for'. "
        'Return ONLY JSON: {"text": "query"}. If the conversation does not say what '
        'to search, return {"text": null}.'
    ),
    "photo": (
        "The user wants a real photo. Name exactly what to photograph, using the "
        "conversation to resolve words like her, him, it, them or that: a person's "
        "full name, a place, an animal, an object. 1 to 8 words. Keep details the "
        "user gave, such as 'at night' or 'in red'. "
        'Return ONLY JSON: {"text": "subject"}. If the conversation does not say '
        "who or what, or what they mean is something the app draws rather than a photo "
        "(a molecule or chemical structure, a formula or equation, a graph, a diagram), "
        'return {"text": null}.'
    ),
}


def turns_from_prompt(messages: Iterable[dict[str, Any]]) -> list[Turn]:
    """User and assistant turns from prompt messages; system blocks are dropped."""
    turns: list[Turn] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            turns.append((role, content))
    return turns


def turns_from_rows(rows: Iterable[Any]) -> list[Turn]:
    """User and assistant turns from stored message rows, oldest first."""
    turns: list[Turn] = []
    for row in rows:
        role = str(getattr(row, "role", "") or "")
        content = getattr(row, "content", None)
        if role in {"user", "assistant"} and isinstance(content, str):
            turns.append((role, content))
    return turns


def _render_turn(role: str, content: str) -> str | None:
    text = content.strip()
    if not text:
        return None
    if text.startswith(_IMAGE_MARKER):
        text = "(showed an image)"
    text = collapse_ws(text)
    if len(text) > _MAX_TURN_CHARS:
        text = f"{text[:_MAX_TURN_CHARS]}…"
    return f"{'User' if role == 'user' else 'Assistant'}: {text}"


def _conversation(turns: Sequence[Turn], request: str) -> list[str]:
    """The last turns before *request*; the request itself is passed separately."""
    trimmed = list(turns)
    if trimmed and trimmed[-1][0] == "user" and collapse_ws(trimmed[-1][1]) == collapse_ws(request):
        trimmed = trimmed[:-1]
    lines = [_render_turn(role, content) for role, content in trimmed[-_MAX_TURNS:]]
    return [line for line in lines if line]


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = collapse_ws(text).strip(" \"'“”.?!")
    if not cleaned or cleaned.lower() in {"null", "none", "unknown"}:
        return None
    return cleaned


async def resolve_reference(
    settings: Settings,
    *,
    kind: ReferenceKind,
    request: str,
    turns: Sequence[Turn],
) -> str | None:
    """The search query or photo subject *request* means, or None."""
    lines = _conversation(turns, request)
    if not lines:
        return None
    budget = settings.reference_resolve_timeout_seconds
    if budget <= 0:
        return None
    if mock_llm.should_mock_llm(settings):
        return None
    try:
        async with asyncio.timeout(budget):
            redis = get_redis_client()
            if await quota_service.global_spend_exceeded(redis, settings):
                return None
            result = await litellm_gateway.complete_structured(
                settings=settings,
                model_alias=ROUTING.background,
                messages=[
                    {"role": "system", "content": _INSTRUCTIONS[kind]},
                    {
                        "role": "user",
                        "content": (
                            "Conversation:\n"
                            + "\n".join(lines)
                            + f"\n\nLatest message: {collapse_ws(request)[:300]}"
                        ),
                    },
                ],
                schema=ConversationReference,
                max_tokens=48,
                timeout_seconds=budget,
                allow_fallback=False,
            )
    except TimeoutError:
        logger.debug("Reference resolver exceeded its budget kind=%s", kind)
        return None
    except Exception:
        logger.warning("Reference resolver failed kind=%s", kind, exc_info=True)
        return None
    # The gateway adds this call's cost to the global spend.
    return _clean(result.text) if result is not None else None
