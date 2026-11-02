"""Stream status phases emitted to clients while a turn works on its reply."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Literal, Protocol

from app.services.solving import SubjectName

StreamStatusPhase = Literal[
    "preparing",
    "remembering",
    "reading_files",
    "searching",
    "calculating",
    "physics",
    "chemistry",
    # The model is reasoning (its reasoning streams, or text is held as reasoning).
    "thinking",
    "composing",
    # Tool-loop activity: AI image generation, and a real reference-photo lookup.
    "image_gen",
    "finding_photo",
    # The tool-selection round: which tools, if any, the reply needs.
    "planning",
    # The streamed reply's answer is being checked before it saves.
    "checking",
    # The reply has streamed; the real photo above it is still being found.
    "answer_photo",
    # The step after the reply's text has ended: no label while the reply saves.
    "finishing",
]

# The status line a subject's solve shows, by the registry's names (``SubjectName``): the
# phone has a label for each phase.
_SUBJECT_STATUS_PHASE: dict[SubjectName, StreamStatusPhase] = {
    "math": "calculating",
    "physics": "physics",
    "chemistry": "chemistry",
}

# Status detail is rendered inline in the client label ("Searching — “…”"),
# so keep it short on the wire.
STATUS_DETAIL_MAX_CHARS = 80

# A step that waits this long is worth a label; a quicker one never flashes one.
SLOW_STEP_SECONDS = 1.0


def status_phase_for_subject(
    subject: SubjectName,
) -> StreamStatusPhase:
    """Bubble phase for one subject. Math keeps the calculating label."""
    return _SUBJECT_STATUS_PHASE[subject]


class StreamStatusFn(Protocol):
    """Status emitter; `detail` optionally carries turn context (e.g. the
    web-search query) so clients can render an activity-specific label, and
    `elapsed_ms` how long the phase had already run when it was sent, so a
    client can count on from it."""

    def __call__(
        self, phase: str, detail: str | None = None, *, elapsed_ms: int | None = None
    ) -> Awaitable[None]: ...


# One chunk of a reasoning model's thinking text, as it streams.
StreamReasoningFn = Callable[[str], Awaitable[None]]


def clip_status_detail(detail: str | None) -> str | None:
    """Normalize whitespace and bound the detail string for the wire."""
    if not detail:
        return None
    flattened = " ".join(detail.split()).strip()
    if not flattened:
        return None
    if len(flattened) > STATUS_DETAIL_MAX_CHARS:
        return flattened[: STATUS_DETAIL_MAX_CHARS - 1].rstrip() + "…"
    return flattened


def thinking_status(
    on_status: StreamStatusFn | None, asked_at: float
) -> Callable[[], Awaitable[None]] | None:
    """The model stream's thinking signal as one ``thinking`` status per turn.

    It carries how long the model has been working on the reply (since
    ``asked_at``, a ``time.perf_counter`` reading), so the client's count starts
    from the request, not from when the status reached it. A backup model that
    thinks too sends nothing more: the client's count runs on.
    """
    if on_status is None:
        return None
    sent = False

    async def emit() -> None:
        nonlocal sent
        if sent:
            return
        sent = True
        await on_status("thinking", elapsed_ms=int((time.perf_counter() - asked_at) * 1000))

    return emit


async def announced_if_slow[T](
    work: Awaitable[T],
    on_status: StreamStatusFn | None,
    phase: StreamStatusPhase,
    *,
    after_seconds: float | None = None,
    then: StreamStatusPhase | None = None,
) -> T:
    """Await ``work``, sending ``phase`` only once it has run ``after_seconds``
    (``SLOW_STEP_SECONDS`` by default), and ``then`` once it ends, when ``phase``
    went out: a label must not outlive its step."""
    if on_status is None:
        return await work
    task = asyncio.ensure_future(work)
    announced = False
    try:
        wait = SLOW_STEP_SECONDS if after_seconds is None else after_seconds
        done, _pending = await asyncio.wait({task}, timeout=wait)
        if not done:
            await on_status(phase)
            announced = True
        return await task
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        if announced and then is not None:
            await on_status(then)
