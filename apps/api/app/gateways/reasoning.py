"""The OpenRouter ``reasoning`` body for a turn's thinking level.

Each catalog model names one value per level, taken from the efforts OpenRouter
lists for it (GET /api/v1/models): ``thinking_off`` for an ordinary question,
``thinking_on`` for a genuinely hard one, ``thinking_escalate`` when the user
said the answer was wrong. So a level a model does not support is never sent.
"""

from __future__ import annotations

from typing import Any, Literal

from app.models.model_catalog import ChatModel

ThinkingLevel = Literal["off", "hard", "escalate"]
EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})


def thinking_value(route: ChatModel, thinking: bool | str | None) -> str | None:
    """The model's catalog value for this level. ``True`` is a hard question."""
    if thinking is None:
        return None
    if thinking is False or thinking == "off":
        return route.thinking_off
    if thinking == "escalate":
        return route.thinking_escalate or route.thinking_on
    return route.thinking_on


def reasoning_body(route: ChatModel, thinking: bool | str | None) -> dict[str, Any] | None:
    """``{"effort": ...}`` or ``{"enabled": false}``; None sends nothing."""
    value = thinking_value(route, thinking)
    if value == "off":
        return {"enabled": False}
    if value in EFFORTS:
        return {"effort": value}
    return None
