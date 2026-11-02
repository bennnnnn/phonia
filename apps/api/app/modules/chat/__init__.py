"""Chat — history over HTTP and the streamed turn (WebSocket and SSE).

``api`` / ``service`` serve ``/chats`` over the rows ``modules/conversation`` keeps.
``ws_api`` (preferred, supports stop) and ``stream_api`` (SSE fallback) carry a turn:
both call ``stream_entry`` with ``turn_deps.default_deps()``, and ``turn_prep`` →
``stream_pipeline`` → ``post_turn`` are the stages behind it (CLAUDE.md, "The chat
loop").

The package stays lazy. Other modules import a few small helpers from here —
reply presentation, stream status, the post-turn jobs — and that must not load the
stream stack, which itself imports those modules. Other modules import only the
names below; what a message says is ``modules/turn_reading``'s (structure ticket ST-04).
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.chat.post_turn import (
        finish_turn as finish_turn,
    )
    from app.modules.chat.presentation import (
        present_assistant_markdown as present_assistant_markdown,
    )
    from app.modules.chat.stream_entry import (
        stream_chat_response as stream_chat_response,
    )
    from app.modules.chat.stream_entry import (
        stream_regenerate_response as stream_regenerate_response,
    )
    from app.modules.chat.stream_status import (
        StreamStatusFn as StreamStatusFn,
    )
    from app.modules.chat.stream_status import (
        clip_status_detail as clip_status_detail,
    )
    from app.modules.chat.titles import (
        needs_generated_title as needs_generated_title,
    )
    from app.modules.chat.turn_prep import (
        RegenerateBackup as RegenerateBackup,
    )
    from app.modules.chat.turn_prep import (
        StreamContext as StreamContext,
    )
    from app.modules.chat.turn_prep.intents import (
        cuts_after_picture as cuts_after_picture,
    )

_EXPORTS = {
    "RegenerateBackup": ("turn_prep", "RegenerateBackup"),
    "StreamContext": ("turn_prep", "StreamContext"),
    "StreamStatusFn": ("stream_status", "StreamStatusFn"),
    "clip_status_detail": ("stream_status", "clip_status_detail"),
    "cuts_after_picture": ("turn_prep.intents", "cuts_after_picture"),
    "finish_turn": ("post_turn", "finish_turn"),
    "needs_generated_title": ("titles", "needs_generated_title"),
    "present_assistant_markdown": ("presentation", "present_assistant_markdown"),
    "stream_chat_response": ("stream_entry", "stream_chat_response"),
    "stream_regenerate_response": ("stream_entry", "stream_regenerate_response"),
}
_MODULE_EXPORTS = (
    "compaction",
    "service",
    "stream_entry",
    "stream_pipeline",
    "titles",
    "turn_resources",
)

__all__ = [*_EXPORTS, *_MODULE_EXPORTS]


def __getattr__(name: str) -> Any:
    if name in _MODULE_EXPORTS:
        value = import_module(f"app.modules.chat.{name}")
    else:
        target = _EXPORTS.get(name)
        if target is None:
            raise AttributeError(name)
        module_name, attribute = target
        value = getattr(import_module(f"app.modules.chat.{module_name}"), attribute)
    globals()[name] = value
    return value
