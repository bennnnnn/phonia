"""The terminal-image tool result both picture tools hand the chat tool loop.

A generated picture and a reference photo end the turn the same way: the
assistant row already holds the ``[Image: …]`` marker, and ``data`` tells the
loop to skip the visible LLM pass (never trust the model to invent attachment
URLs).
"""

from __future__ import annotations

from app.gateways.mcp.base import ToolResult
from app.models.orm import Message


def terminal_image_result(
    name: str,
    assistant_message: Message,
    *,
    attached: str,
    no_marker: str,
    default_model: str,
) -> ToolResult:
    """*attached* for the model when the row carries an image marker; else *no_marker*."""
    marker = (assistant_message.content or "").strip()
    if not marker.startswith("[Image:"):
        return ToolResult(name=name, content=no_marker)
    return ToolResult(
        name=name,
        content=attached,
        data={
            "terminal": True,
            "image_marker": marker,
            "assistant_message_id": str(assistant_message.id),
            "resolved_model": assistant_message.model or default_model,
        },
    )
