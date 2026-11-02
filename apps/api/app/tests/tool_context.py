"""A turn's ``ToolContext`` for tests that call an adapter or the round loop directly."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.gateways.mcp.base import ToolContext
from app.modules.web_search import TurnTavilyBudget


def tool_context(
    *,
    user: Any = None,
    redis: Any = None,
    chat_id: UUID | None = None,
    user_timezone: str | None = None,
    user_query: str = "",
    settings: Settings | None = None,
) -> ToolContext:
    """One turn, built the way the tool loop builds it; nothing is bound by default."""
    return ToolContext(
        user=user,
        redis=redis,
        chat_id=chat_id,
        user_timezone=user_timezone,
        user_query=user_query,
        tavily_budget=TurnTavilyBudget(settings=settings or Settings(), user=user),
    )
