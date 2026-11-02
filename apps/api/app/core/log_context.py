"""Ids every log line in a chat turn or a background job carries.

A third of WARNING+ lines named nothing: "Chat stream failed" with a traceback could
not be tied to a user report, a chat, or the same turn's timing lines, and the
WebSocket path and the worker never had a request id. A turn binds ``chat_id`` and
``turn``, a socket ``user_id``, a job ``job`` and ``job_type``; the formatters print
them and Sentry tags its events with them. Ids only, never content.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

_log_ids: ContextVar[tuple[tuple[str, str], ...]] = ContextVar("log_ids", default=())


def current_log_ids() -> dict[str, str]:
    """The ids bound in this context, outermost first."""
    return dict(_log_ids.get())


def new_turn_id() -> str:
    """A short id for one chat turn: enough to find its lines, not a key to anything."""
    return uuid4().hex[:12]


@contextmanager
def bound_log_ids(**ids: object) -> Iterator[None]:
    """Add ``ids`` (None values skipped) to every log line inside the block.

    Tasks started inside inherit them. The reset is skipped when an async generator is
    closed from another context, which the generator's own context then discards.
    """
    added = tuple((key, str(value)) for key, value in ids.items() if value is not None)
    token = _log_ids.set((*_log_ids.get(), *added))
    try:
        yield
    finally:
        try:
            _log_ids.reset(token)
        except ValueError:
            pass
