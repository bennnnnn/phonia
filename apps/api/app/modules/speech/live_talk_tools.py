"""Read-only, bounded Live Talk lookups using the same memory/search services as chat."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.db import SessionLocal
from app.gateways.mcp.base import ToolContext
from app.models.orm import User
from app.modules import memory as memory_service
from app.modules.account import profile as profile_service
from app.modules.memory.switch import memory_switch_on
from app.modules.turn_reading.routing import is_lightweight_chat_turn
from app.modules.web_search import TurnTavilyBudget, WebSearchAdapter
from app.services.prompt_safety import wrap_untrusted

logger = logging.getLogger(__name__)
_TTL = 2 * 60 * 60


def _key(user_id: UUID, call_id: str, turn_id: str, name: str) -> str:
    digest = hashlib.sha256(f"{call_id}:{turn_id}:{name}".encode()).hexdigest()
    return f"live_tool:{user_id}:{digest}"


async def execute_tool(
    settings: Settings,
    redis: Redis,
    *,
    user: User,
    call_id: str,
    turn_id: str,
    name: str,
    query: str,
) -> dict[str, Any]:
    if name not in {"memory_lookup", "web_search"}:
        return {"content": "This action is not available in voice."}
    settings = profile_service.settings_for_user(settings, user)
    if name == "memory_lookup" and not memory_switch_on(user):
        return {"content": "Memory is disabled. Do not use saved personal details."}
    # One reservation per tool per utterance, including retries and concurrent
    # function calls. Unknown IDs cannot bypass daily search quotas/rate limits.
    key = _key(user.id, call_id, turn_id, name)
    try:
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)
        if not await redis.set(key + ":reserved", "1", nx=True, ex=_TTL):
            return {"content": "This lookup is already running or was attempted. Do not repeat it."}
    except Exception:
        logger.warning("Live talk tool reservation failed name=%s", name, exc_info=True)
        return {"content": "Lookup unavailable. Do not guess or claim it succeeded."}
    result: dict[str, Any]
    try:
        async with asyncio.timeout(12):
            if name == "memory_lookup":
                if not memory_switch_on(user):
                    result = {"content": "Memory is disabled. Do not use saved personal details."}
                else:
                    async with SessionLocal() as session:
                        memory = await memory_service.get_memory_block(
                            session,
                            user,
                            settings,
                            query_text=query,
                            exclude_sensitive=memory_service.exclude_sensitive_for_query(query),
                        )
                    result = {
                        "content": wrap_untrusted("memory", memory[:1500], first_party=True)
                        if memory
                        else "No relevant saved context was found."
                    }
            elif not settings.web_search_enabled or is_lightweight_chat_turn(query):
                result = {"content": "Web search is unavailable or unnecessary for this question."}
            else:
                ctx = ToolContext(
                    user=user,
                    redis=redis,
                    chat_id=None,
                    user_timezone=user.timezone,
                    user_query=query,
                    tavily_budget=TurnTavilyBudget(settings=settings, user=user),
                )
                found = await WebSearchAdapter(settings).invoke({"query": query}, ctx)
                result = {
                    "content": found.content[:8000],
                    "sources": (found.data or {}).get("hits", []),
                }
                if not result["sources"]:
                    result["content"] = (
                        "No live results could be verified. Say so; do not guess current facts."
                    )
    except Exception:
        logger.warning("Live Talk lookup failed name=%s", name, exc_info=True)
        result = {
            "content": (
                "Lookup failed or timed out. Say what you could not verify; do not invent results."
            )
        }
    try:
        await redis.set(key, json.dumps(result), ex=_TTL)
    except Exception:
        logger.warning("Could not cache voice lookup result")
    return result


async def search_sources_for_turn(redis: Redis, user_id: UUID, call_id: str, turn_id: str) -> list:
    """Source chips for the turn's voice web search; the turn is saved without them on failure."""
    try:
        cached = await redis.get(_key(user_id, call_id, turn_id, "web_search"))
        return json.loads(cached).get("sources", []) if cached else []
    except Exception as exc:
        logger.warning(
            "Live Talk sources unreadable; saving the turn without them: %s", type(exc).__name__
        )
        return []
