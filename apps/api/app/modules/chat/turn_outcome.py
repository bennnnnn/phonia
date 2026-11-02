"""What one turn produced, for the transport that carries it.

The intercepts, the pipeline and the finalize passes fill a ``TurnOutcome``; the
transports read it once the token stream ends, wait on its tasks, and send the
``stream_end`` and ``done`` events built from it (``stream_events``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.modules.chat.stream_accum import Completion
from app.modules.web_search import SearchSource


class TurnUsage(BaseModel):
    """The day's usage after a turn, which ``done`` carries for the quota nudge."""

    used_tokens: int
    daily_limit: int


@dataclass
class TurnOutcome:
    """One turn's saved reply, what ``done`` says about it, and the work still running."""

    message_id: str | None = None
    # The reply as it persists, when that differs from the streamed text or the
    # reply was stopped.
    final_content: str | None = None
    resolved_model: str | None = None
    # The provider answered on another alias than the one asked for.
    fallback_used: bool = False
    # "interrupted" or "user_stop"; None when the reply completed.
    completion: Completion | None = None
    # How much of the reply the client had drawn when its user tapped Stop (a
    # UTF-16 length, from the cancel frame); a stopped reply saves no more.
    client_shown_chars: int | None = None
    recalled: int = 0
    memory_hints: list[str] = field(default_factory=list)
    context_summarized: int = 0
    search_sources: list[SearchSource] = field(default_factory=list)
    todos_changed: bool = False
    # The day's usage once the turn's charge settled; None until then, or on failure.
    usage: TurnUsage | None = None
    # The user message this turn answers is in the chat. An error frame says so
    # (``user_message_saved``): the phone offers Retry (resend) only when it is not,
    # and Regenerate only when it is. A regenerate answers a saved message.
    user_message_saved: bool = False
    # The commit ``done`` waits on, and the post-turn jobs that follow it.
    finalize_db_task: asyncio.Task[None] | None = None
    finalize_task: asyncio.Task[None] | None = None
    # The follow-up questions, sent after ``done``.
    related_task: asyncio.Task[dict[str, Any] | None] | None = None
    # While a new message's row is unsaved, a Stop's hard cancel waits here
    # (``hold_stops``); None when it runs at once.
    _held_stops: list[Callable[[], object]] | None = None

    def mark_user_message_saved(self) -> None:
        self.user_message_saved = True
        self.mark_stop_safe()

    def hold_stops(self) -> None:
        """A new message's turn: a Stop only asks it to end (``should_cancel``) until
        its user row is saved, then cancels it.

        A Stop tapped right after Send reached the turn before it wrote that row:
        cancelled there, the message the phone still shows was never saved.
        """
        if self._held_stops is None:
            self._held_stops = []

    def mark_stop_safe(self) -> None:
        """A hard cancel can no longer take back the user's message: it is in the
        chat, or what runs next (a photo, a picture) saves it with its reply."""
        held, self._held_stops = self._held_stops or [], None
        for stop in held:
            stop()

    def stop_when_safe(self, stop: Callable[[], object]) -> None:
        """Run ``stop`` (a transport's hard cancel) now, or once the turn is stop-safe."""
        if self._held_stops is None:
            stop()
        else:
            self._held_stops.append(stop)
