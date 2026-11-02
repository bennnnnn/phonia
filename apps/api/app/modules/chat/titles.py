"""Shared helpers for chat title validation, display, and LLM generation."""

import asyncio
import logging
from uuid import UUID

from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.validation import BORING_CHAT_TITLES as BORING_CHAT_TITLES
from app.core.validation import normalize_chat_title as normalize_chat_title
from app.core.validation import normalize_stored_chat_title, unwrap_chat_title
from app.gateways import litellm_gateway, mock_llm
from app.models.routing_lanes import ROUTING
from app.modules.conversation import service as conversation_service

GREETING_CHAT_TITLE = "Greeting"


def title_job_key(chat_id: UUID) -> str:
    """The ``topic`` job's dedupe key: one title per chat, however many ask for it."""
    return f"topic:{chat_id}"


# Exact first-line openers after unwrap + casefold. Longer first messages
# still go to title-model (e.g. "good morning, help me with physics").
_CASUAL_OPENERS = frozenset(
    {
        "hi",
        "hii",
        "hello",
        "hello hello",
        "hey",
        "hey there",
        "hi there",
        "hello there",
        "yo",
        "hiya",
        "howdy",
        "sup",
        "gm",
        "good morning",
        "good afternoon",
        "good evening",
        "good night",
        "morning",
        "evening",
        "thanks",
        "thank you",
        "what's up",
        "whats up",
        "how are you",
        "how's it going",
        "hows it going",
        "hey recall",
        "hi recall",
    }
)

_logger = logging.getLogger(__name__)


def needs_generated_title(title: str | None) -> bool:
    """True when the chat still needs the topic job (empty or a placeholder)."""
    cleaned = unwrap_chat_title(title or "")
    if not cleaned:
        return True
    return cleaned.casefold() in BORING_CHAT_TITLES


def sanitize_manual_chat_title(raw: str) -> str | None:
    """User-chosen title — allow boring labels; trim quotes and enforce length."""
    return normalize_stored_chat_title(raw)


def is_casual_opener(user_message: str) -> bool:
    line = unwrap_chat_title(user_message.strip().split("\n", 1)[0]).casefold()
    return bool(line) and line in _CASUAL_OPENERS


def finalize_generated_title(raw: str | None, user_message: str) -> str | None:
    """Greetings get a topic label; otherwise keep a normalized model title."""
    if is_casual_opener(user_message):
        return GREETING_CHAT_TITLE
    return normalize_chat_title(raw)


async def generate_title(
    settings: Settings,
    user_message: str,
    assistant_message: str,
) -> str | None:
    if is_casual_opener(user_message):
        return GREETING_CHAT_TITLE

    if mock_llm.should_mock_llm(settings):
        return finalize_generated_title(
            await mock_llm.mock_title(user_message),
            user_message,
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You title conversations in 3-6 words. Reply with ONLY the title. "
                "Plain text only — no markdown, no asterisks, no quotes. "
                "Never copy the user's message verbatim. "
                "Never use generic labels like 'New chat', 'Untitled', or 'Chat'. "
                "Keep times, dates and numbers exactly as written (4:14 AM, 3.5%, 300k). "
                "Greetings (hi, hello, good morning) get a short topic label such as Greeting."
            ),
        },
        {"role": "user", "content": user_message[:300]},
        {"role": "assistant", "content": assistant_message[:300]},
        {"role": "user", "content": "Title?"},
    ]
    raw = await litellm_gateway.complete_text(
        settings=settings,
        model_alias=ROUTING.titles,
        messages=messages,
        max_tokens=20,
    )
    if raw is None:
        return None
    return finalize_generated_title(raw, user_message)


async def generate_chat_title(
    settings: Settings,
    chat_id: UUID,
    user_message: str,
    assistant_message: str,
    *,
    user_id: UUID,
) -> bool:
    """Title the chat from its first exchange (the ``topic`` job); True when one applied.

    False (nothing usable, or the chat already has a title) leaves the job not done,
    so a later request may try again; the caller says so to the queue.
    """
    if not user_message.strip() or not assistant_message.strip():
        return False
    try:
        title = await asyncio.wait_for(
            generate_title(settings, user_message, assistant_message),
            timeout=15.0,
        )
        title = normalize_chat_title(title)
        if not title:
            return False
        async with SessionLocal() as session:
            applied = await conversation_service.set_title_if_empty(
                session, chat_id, title, user_id=user_id, commit=False
            )
            await session.commit()
        return applied
    except Exception:
        _logger.exception("Topic generation failed for chat_id=%s", chat_id)
        raise
