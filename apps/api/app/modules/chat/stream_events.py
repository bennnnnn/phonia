"""Shared stream finalization helpers for WS and SSE transports.

Product-level decisions (what ``done`` contains, how exceptions map to
error payloads) live here once; routers only handle transport plumbing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Coroutine
from contextlib import suppress
from typing import Any, Literal

from pydantic import BaseModel, model_serializer

from app.core.background_tasks import create_background_task
from app.exceptions import (
    RATE_LIMITED_CODE,
    AttachmentValidationError,
    ChatBusyError,
    ChatNotFoundError,
    ChatServiceError,
    ConsentRequiredError,
    QuotaExceededError,
    RedisUnavailableError,
    SpendCapReachedError,
    TurnRefusedError,
    UnknownModelOverrideError,
)
from app.gateways.litellm_gateway import ModelUnavailableError
from app.modules.chat.stream_accum import Completion
from app.modules.chat.turn_outcome import TurnOutcome, TurnUsage
from app.modules.web_search import SearchSource

logger = logging.getLogger(__name__)


def clear_task_cancellation() -> None:
    """Let partial-reply cleanup await after a task cancel.

    Python 3.11 keeps the cancellation pending after ``CancelledError`` is
    caught, so the next ``await`` raises again and the save never runs.
    """
    task = asyncio.current_task()
    if task is None:
        return
    while task.cancelling():
        task.uncancel()


async def await_ignoring_cancel(coro: Coroutine[Any, Any, Any]) -> Any:
    """Finish ``coro`` even if this task is cancelled again while it runs.

    Stop closes the provider socket, and that close cancels the stream task
    a second time. The partial-reply save still has to run.
    """
    work = create_background_task(coro, name="partial_reply_save")
    while True:
        clear_task_cancellation()
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            if work.done():
                break
    return work.result()


async def finish_open_stream(stream: AsyncIterator[Any]) -> None:
    """Resume a chat generator left parked at ``yield`` so its save still runs.

    Breaking out of ``async for``, or cancelling the consumer while the
    generator is suspended, leaves it open. Nothing after the yield runs,
    so the partial reply is never written. Pull until it ends.
    """
    try:
        async for _ in stream:
            pass
    except asyncio.CancelledError:
        clear_task_cancellation()
        with suppress(Exception, asyncio.CancelledError):
            async for _ in stream:
                pass
    except Exception:
        # The turn reports its own failure; this only drains what was left.
        logger.debug("Stopped chat stream raised while it finished", exc_info=True)


# Failures a turn reports to its client without logging a traceback: the client
# shows each one's message (quota, an outage, a refused request, a failed model).
EXPECTED_TURN_ERRORS = (
    QuotaExceededError,
    RedisUnavailableError,
    ChatServiceError,
    ModelUnavailableError,
)

# How the turn's DB commit ended when ``done`` stopped waiting for it.
CommitStatus = Literal["committed", "timeout", "failed"]

# How long to hold `done` waiting on the DB commit before falling back to a
# best-effort `done`. Long enough for a normal Neon round trip + usage write,
# short enough that a wedged finalize doesn't pin the socket forever. If the
# commit FAILS (vs. is slow) we send an error instead of a ghost `done`.
DONE_COMMIT_WAIT_SECONDS = 10.0
REPLY_SAVE_FAILED_MESSAGE = "Failed to save the response. Please retry."
REPLY_NOT_SAVED_CODE = "reply_not_saved"
# A turn the server stopped (or refused) because the process is shutting down.
SERVER_RESTARTING_MESSAGE = "The server is restarting. Send again in a moment."
SERVER_RESTARTING_CODE = "server_restarting"
# A turn that failed for no reason the client can act on. These frames named no code, and
# the phone showed their English.
FAILED_CODE = "failed"


# A turn that is quiet this long (tool calls, a slow provider) sends a keepalive, so
# the phone can tell a slow turn from a dead connection: it gives up on a stream
# after 45 s with nothing (code-health audit NET-17).
TURN_KEEPALIVE_SECONDS = 15.0


def build_keepalive_event() -> dict[str, Any]:
    """Sent while a turn is quiet; carries nothing."""
    return {"type": "keepalive"}


def build_start_event() -> dict[str, Any]:
    """First frame of a turn; tells the client generation has begun."""
    return {"type": "start"}


def build_token_event(content: str) -> dict[str, Any]:
    """One chunk of assistant text."""
    return {"type": "token", "content": content}


def build_status_event(
    phase: str, detail: str | None = None, *, elapsed_ms: int | None = None
) -> dict[str, Any]:
    """Progress while the turn works (see stream_status.StreamStatusPhase).

    ``elapsed_ms`` is how long the phase had run when it was sent (``thinking``:
    since the model was asked), so a client counts from the phase's real start.
    """
    event: dict[str, Any] = {"type": "status", "phase": phase}
    if detail:
        event["detail"] = detail
    if elapsed_ms is not None:
        event["elapsed_ms"] = max(0, elapsed_ms)
    return event


def build_reasoning_event(content: str) -> dict[str, Any]:
    """One chunk of reasoning-model thinking text."""
    return {"type": "reasoning", "content": content}


def build_duplicate_event() -> dict[str, Any]:
    """In place of ``start``: an earlier send of this message (its ``client_message_id``)
    already reached a turn. No second turn runs; the client follows the first."""
    return {"type": "duplicate"}


def build_pong_event() -> dict[str, Any]:
    """The socket's answer to a client ``ping`` (WebSocket only): the connection is alive.

    The phone pings once on connect (an answer says this server can be probed) and
    again when a send goes unanswered.
    """
    return {"type": "pong"}


class StreamEndEvent(BaseModel):
    """The token stream is done; ``done`` waits on the commit.

    Sent before that wait, so clients can settle layout while ``done`` is pending.
    """

    type: Literal["stream_end"] = "stream_end"
    resolved_model: str | None = None
    fallback_used: bool = False

    @classmethod
    def from_outcome(cls, outcome: TurnOutcome) -> StreamEndEvent:
        return cls(resolved_model=outcome.resolved_model, fallback_used=outcome.fallback_used)

    @model_serializer
    def _wire(self) -> dict[str, Any]:
        """Absent fields are left out; ``fallback_used`` is the string ``"1"``."""
        event: dict[str, Any] = {"type": self.type}
        if self.resolved_model:
            event["resolved_model"] = self.resolved_model
        if self.fallback_used:
            event["fallback_used"] = "1"
        return event


class DoneEvent(BaseModel):
    """The turn's last event: the saved reply and what the client shows with it."""

    type: Literal["done"] = "done"
    # None while the commit is still running (``persisting``).
    message_id: str | None = None
    recalled: int = 0
    memory_hints: list[str] = []
    context_summarized: int = 0
    todos_changed: bool = False
    # The day's usage after this turn: the quota nudge reads it here, not with a GET.
    usage: TurnUsage | None = None
    search_sources: list[SearchSource] = []
    final_content: str | None = None
    resolved_model: str | None = None
    fallback_used: bool = False
    completion: Completion | None = None
    # The commit outlived the wait: the client keeps its bubble and refetches.
    persisting: bool = False

    @classmethod
    def from_outcome(cls, outcome: TurnOutcome, *, persisting: bool = False) -> DoneEvent:
        return cls(
            message_id=None if persisting else outcome.message_id,
            recalled=outcome.recalled,
            memory_hints=outcome.memory_hints,
            context_summarized=outcome.context_summarized,
            todos_changed=outcome.todos_changed,
            usage=outcome.usage,
            search_sources=outcome.search_sources,
            final_content=outcome.final_content,
            resolved_model=outcome.resolved_model,
            fallback_used=outcome.fallback_used,
            completion=outcome.completion,
            persisting=persisting,
        )

    @model_serializer
    def _wire(self) -> dict[str, Any]:
        """The shape installed clients read: absent fields left out, the rest as strings.

        ``todos_changed`` goes out as ``todos_sync: "1"`` and the lists as JSON text;
        ES-45 sends them typed once the clients that accept both are the ones in use.
        """
        event: dict[str, Any] = {"type": self.type}
        if self.message_id:
            event["message_id"] = self.message_id
        if self.recalled:
            event["recalled"] = str(self.recalled)
        if self.memory_hints:
            event["memory_hints"] = json.dumps(self.memory_hints)
        if self.context_summarized:
            event["context_summarized"] = str(self.context_summarized)
        if self.todos_changed:
            event["todos_sync"] = "1"
        if self.usage:
            event["used_tokens"] = str(self.usage.used_tokens)
            event["daily_limit"] = str(self.usage.daily_limit)
        if self.search_sources:
            event["search_sources"] = json.dumps(self.search_sources)
        # Empty is sent too: a fallback its safety passes emptied replaces the streamed text.
        if self.final_content is not None:
            event["final_content"] = self.final_content
        if self.resolved_model:
            event["resolved_model"] = self.resolved_model
        if self.fallback_used:
            event["fallback_used"] = "1"
        if self.completion:
            event["completion"] = self.completion
        if self.persisting:
            event["persisting"] = True
        return event


def pop_finalize_tasks(outcome: TurnOutcome) -> asyncio.Task[None] | None:
    """Clear the turn's finalize tasks; return the DB-commit task."""
    finalize_db_task = outcome.finalize_db_task
    outcome.finalize_db_task = None
    outcome.finalize_task = None
    return finalize_db_task


async def await_finalize_commit(
    finalize_db_task: asyncio.Task[None] | None,
) -> CommitStatus:
    """Wait (bounded) for the turn's DB commit before sending ``done``.

    Returns:
      - ``"committed"`` when the commit landed (or there was no task).
      - ``"timeout"`` when the wait timed out while the commit is still
        running under ``asyncio.shield``. The caller should send ``done``
        WITHOUT ``message_id`` (and with ``persisting: true``) so the client
        keeps the local bubble and refetches instead of trusting a row that
        may never persist.
      - ``"failed"`` when the finalize task actually raised, so the caller
        sends an error instead of a ghost ``done`` carrying a ``message_id``
        for a row that never persisted.

    The wait must use ``shield``: bare ``wait_for`` cancels the finalize task
    on timeout, which rolls back the assistant insert and strands reserved
    quota while the client still receives ``done``.
    """
    if finalize_db_task is None:
        return "committed"
    try:
        await asyncio.wait_for(asyncio.shield(finalize_db_task), DONE_COMMIT_WAIT_SECONDS)
        return "committed"
    except TimeoutError:
        logger.warning(
            "Finalize commit still running after %ss; sending done without "
            "message_id (commit continues under shield)",
            DONE_COMMIT_WAIT_SECONDS,
        )
        return "timeout"
    except Exception:
        logger.exception("Finalize commit failed before done")
        return "failed"


def settled_turn_event(outcome: TurnOutcome, commit: CommitStatus) -> dict[str, Any]:
    """The event after ``stream_end``, once the commit wait ends.

    ``done`` when the reply committed; ``done`` without its id (``persisting``)
    while the commit still runs; an error when it failed, so no client is handed
    the id of a row that never saved. Follow-up questions go out only after a
    committed ``done``.
    """
    if commit == "failed":
        return turn_error_payload(
            None,
            user_message_saved=outcome.user_message_saved,
            message=REPLY_SAVE_FAILED_MESSAGE,
            code=REPLY_NOT_SAVED_CODE,
        )
    return DoneEvent.from_outcome(outcome, persisting=commit == "timeout").model_dump()


async def persist_finalize_if_pending(outcome: TurnOutcome) -> None:
    """Await a still-pending DB finalize after the transport drops.

    SSE and WS success paths pop and wait for ``done``. If the client closes
    first, that wait never runs — call this from a ``finally`` so a partial
    assistant row is still committed (quota refund + title job included).
    """
    finalize_db_task = pop_finalize_tasks(outcome)
    if finalize_db_task is None:
        return
    with suppress(Exception):
        await await_finalize_commit(finalize_db_task)


def build_related_prompts_event(message_id: str, prompts: list[str]) -> dict[str, Any]:
    """Follow-up questions for one assistant message. Sent after ``done``."""
    return {
        "type": "related_prompts",
        "message_id": message_id,
        "prompts": prompts,
    }


async def take_related_prompts_event(
    task: asyncio.Task[Any] | None,
) -> dict[str, Any] | None:
    """Wait for the follow-up event. ``done`` is already on the wire."""
    if task is None:
        return None
    try:
        event = await asyncio.shield(task)
    except Exception:
        logger.warning("Related prompts failed", exc_info=True)
        return None
    if not isinstance(event, dict) or event.get("type") != "related_prompts":
        return None
    return event


# The socket's per-message and connect limits: coded, so the phone words them.
RATE_LIMITED_MESSAGE = "Too many requests. Try again shortly."


def rate_limited_payload() -> dict[str, Any]:
    """The socket refused a turn over its per-message limit: nothing was saved."""
    return turn_error_payload(
        None, user_message_saved=False, message=RATE_LIMITED_MESSAGE, code=RATE_LIMITED_CODE
    )


def rate_limited_connect_payload() -> dict[str, Any]:
    """The socket refused a connection over its connect limit (no turn to name)."""
    return {"type": "error", "code": RATE_LIMITED_CODE, "message": RATE_LIMITED_MESSAGE}


def restarting_payload(*, user_message_saved: bool) -> dict[str, Any]:
    """A turn the server refused or stopped because it is shutting down (a deploy)."""
    return turn_error_payload(
        None,
        user_message_saved=user_message_saved,
        message=SERVER_RESTARTING_MESSAGE,
        code=SERVER_RESTARTING_CODE,
    )


def turn_error_payload(
    exc: BaseException | None,
    *,
    user_message_saved: bool,
    message: str | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    """An error frame for a turn, saying whether its user message is in the chat.

    ``user_message_saved`` is what lets a client choose its recovery: resend the
    message when it was not saved (Retry), answer it again when it was
    (Regenerate). Clients that predate the field ignore it. ``message`` and ``code``
    say a failure that is not an exception (a reply that did not save, a restart);
    without a code it is ``failed``.
    """
    payload: dict[str, Any] = (
        error_payload_for_exception(exc)
        if exc is not None
        else {"type": "error", "code": FAILED_CODE}
    )
    if message is not None:
        payload["message"] = message
    if code is not None:
        payload["code"] = code
    payload["user_message_saved"] = user_message_saved
    return payload


def error_payload_for_exception(exc: BaseException) -> dict[str, Any]:
    """Map stream exceptions to the shared error event shape."""
    if isinstance(exc, QuotaExceededError):
        return {"type": "error", "code": "quota_exceeded", "message": exc.message}
    if isinstance(exc, RedisUnavailableError):
        return {"type": "error", "code": "unavailable", "message": exc.message}
    if isinstance(exc, ChatBusyError):
        return {"type": "error", "code": "busy", "message": exc.message}
    if isinstance(exc, AttachmentValidationError):
        return {"type": "error", "code": "attachment_rejected", "message": exc.message}
    if isinstance(exc, UnknownModelOverrideError):
        return {"type": "error", "code": "unknown_model", "message": exc.message}
    if isinstance(exc, SpendCapReachedError):
        return {"type": "error", "code": "spend_cap", "message": exc.message, **exc.fields}
    if isinstance(exc, ConsentRequiredError):
        return {"type": "error", "code": exc.code, "message": exc.message}
    if isinstance(exc, TurnRefusedError):
        return {"type": "error", "code": exc.code, "message": exc.message, **exc.fields}
    if isinstance(exc, ChatNotFoundError):
        # The chat, or the message to answer, is gone (deleted on another device).
        return {"type": "error", "code": "not_found", "message": exc.message}
    if isinstance(exc, ChatServiceError):
        return {"type": "error", "code": FAILED_CODE, "message": exc.message}
    if isinstance(exc, ModelUnavailableError):
        return {
            "type": "error",
            "code": exc.code,
            "message": exc.message,
            "failed_model": exc.failed_alias,
        }
    return {"type": "error", "code": FAILED_CODE, "message": "Something went wrong. Try again."}
