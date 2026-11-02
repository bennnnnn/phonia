"""Turn preparation: attachments, the user's row, the prompt and its context.

The package exports what the stream stages and tests read; everything else is
imported from its own submodule. It stays lazy, like ``app.modules.chat``: the
SymPy pool's workers import ``turn_prep.intents`` to read a message, and must
not load the prompt, attachment and database stack behind ``context``.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.chat.turn_prep.attachments import (
        count_images,
        load_attachment_rows,
        vision_reserve_tokens,
    )
    from app.modules.chat.turn_prep.context import (
        RegenerateBackup,
        StreamContext,
        TurnPromptBundle,
        await_user_message_persist,
        build_stream_prompt_context,
        stream_context_from_bundle,
    )
    from app.modules.chat.turn_prep.prepare import prepare_chat_turn
    from app.modules.chat.turn_prep.request import (
        ClientGeoContext,
        TurnRequest,
        resolve_client_geo,
    )

_EXPORTS = {
    "ClientGeoContext": "request",
    "RegenerateBackup": "context",
    "StreamContext": "context",
    "TurnPromptBundle": "context",
    "TurnRequest": "request",
    "await_user_message_persist": "context",
    "build_stream_prompt_context": "context",
    "count_images": "attachments",
    "load_attachment_rows": "attachments",
    "prepare_chat_turn": "prepare",
    "resolve_client_geo": "request",
    "stream_context_from_bundle": "context",
    "vision_reserve_tokens": "attachments",
}

__all__ = [
    "ClientGeoContext",
    "RegenerateBackup",
    "StreamContext",
    "TurnPromptBundle",
    "TurnRequest",
    "await_user_message_persist",
    "build_stream_prompt_context",
    "count_images",
    "load_attachment_rows",
    "prepare_chat_turn",
    "resolve_client_geo",
    "stream_context_from_bundle",
    "vision_reserve_tokens",
]


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    value = getattr(import_module(f"app.modules.chat.turn_prep.{module}"), name)
    globals()[name] = value
    return value
