"""Apply the user's own memory edits ("keep lists under five things")."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.core.config import Settings
from app.core.db import SessionLocal
from app.exceptions import DomainError
from app.modules.memory import llm as memory_llm
from app.modules.memory import locks
from app.modules.memory import repository as memories_repo
from app.modules.memory.apply import apply_memory_facts
from app.modules.memory.extraction_workflow import load_memory_snapshot
from app.modules.memory.pass_writes import writes_from_ops
from app.modules.memory.topics import parse_topic

logger = logging.getLogger(__name__)


class MemoryOffError(DomainError):
    """Memory is turned off for this account."""

    status_code = 409
    default_code = "memory_off"

    def __init__(self, message: str = "Memory is off.") -> None:
        super().__init__(message)


class MemoryInstructionFailedError(DomainError):
    """The model could not turn the instruction into edits."""

    status_code = 502
    default_code = "memory_edit_failed"

    def __init__(self, message: str = "Memory couldn't be updated right now — try again.") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class MemoryInstructionOutcome:
    applied: int
    reply: str
    # Edits the model proposed that never landed: unreadable, filtered or stale.
    dropped: int = 0


_OP_WORDS = {
    "add": "added",
    "update": "changed",
    "supersede": "replaced",
    "delete": "removed",
    "mute": "muted",
}
NOTHING_CHANGED_REPLY = "Nothing in your memory changed. Try saying it another way."


def instruction_reply(model_reply: str, *, proposed: int, applied: list[str]) -> str:
    """What the user is told: the model's sentence only when every edit it made landed.

    The model writes its reply before the edits are checked, so "Done, I removed it"
    must not stand when a filter or a stale match dropped the change.
    """
    if not applied:
        return model_reply if proposed == 0 and model_reply else NOTHING_CHANGED_REPLY
    if len(applied) >= proposed and model_reply:
        return model_reply
    counts = {op: applied.count(op) for op in _OP_WORDS if op in applied}
    parts = [f"{count} {_OP_WORDS[op]}" for op, count in counts.items()]
    return f"Memory updated: {', '.join(parts)}."


async def apply_memory_instruction(
    settings: Settings,
    *,
    user_id: UUID,
    instruction: str,
    focus_topic: str | None = None,
) -> MemoryInstructionOutcome:
    """Edit memory as the user asked. Raises MemoryWriteLockBusyError while memory is busy,
    and ``RedisUnavailableError`` while Redis cannot say (503 unavailable, not busy)."""
    lock_token = await locks.take_memory_write_lock(user_id)
    if not lock_token:
        raise locks.MemoryWriteLockBusyError(user_id)
    try:
        # Short session: nothing stays open while the model works.
        async with SessionLocal() as session:
            snapshot = await load_memory_snapshot(session, user_id)
        if not snapshot.memory_enabled:
            raise MemoryOffError()
        result = await memory_llm.instruct_memory(
            settings,
            instruction,
            existing_facts=snapshot.prompt_facts,
            existing_areas=snapshot.prompt_areas,
            focus_topic=parse_topic(focus_topic),
        )
        if result is None:
            raise MemoryInstructionFailedError()
        # The user asked for this change, so it is saved like "remember this":
        # sensitive topics included and no confidence floor.
        writes, _ = writes_from_ops(
            result.ops,
            chat_id=None,
            explicit_remember=True,
            include_sensitive=snapshot.include_sensitive,
            min_confidence=0.0,
            transcript=f"User: {instruction}",
            existing_texts=snapshot.existing_facts.values(),
            profile_name=snapshot.profile_name,
        )
        applied: list[str] = []
        if writes:
            await apply_memory_facts(
                settings,
                user_id=user_id,
                writes=writes,
                session_factory=SessionLocal,
                memories=memories_repo,
                expected_facts=snapshot.existing_facts,
                manual_edit=True,
                applied=applied,
            )
        # An op that did not validate was still proposed: "Added it" must not stand.
        proposed = len(result.ops) + result.dropped
        logger.info(
            "memory_instruction user_id=%s applied=%s proposed=%s", user_id, len(applied), proposed
        )
        return MemoryInstructionOutcome(
            applied=len(applied),
            reply=instruction_reply(result.reply.strip(), proposed=proposed, applied=applied),
            dropped=max(proposed - len(applied), 0),
        )
    finally:
        await locks.release_memory_write_lock(user_id, lock_token)
