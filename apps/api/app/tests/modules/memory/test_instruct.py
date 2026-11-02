from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.memory import instruct as instruct_service
from app.modules.memory import locks
from app.modules.memory.pass_writes import MemorySnapshot
from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult
from app.modules.memory.writes_repository import MemoryFactWrite
from app.tests.fakes import FakeSessionCM


def _snapshot(*, enabled: bool = True) -> MemorySnapshot:
    fact_id = uuid4()
    return MemorySnapshot(
        memory_enabled=enabled,
        include_sensitive=False,
        existing_facts={fact_id: "User likes tea"},
        prompt_facts=[
            {"id": str(fact_id), "type": "fact", "topic": "notes", "text": "User likes tea"}
        ],
        prompt_areas=[{"topic": "area:recall", "title": "Recall", "summary": ""}],
    )


def _applies(ops: list[str] | None):
    """An apply_memory_facts double that reports ``ops`` as applied (all writes when None)."""

    async def apply(*_args, **kwargs):
        landed = [write.op for write in kwargs["writes"]] if ops is None else ops
        kwargs["applied"].extend(landed)

    return AsyncMock(side_effect=apply)


@contextmanager
def _patches(*, result, snapshot=None, lock="token", applied_ops=None):
    apply = _applies(applied_ops)
    instruct = AsyncMock(return_value=result)
    release = AsyncMock()
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(locks, "take_memory_write_lock", AsyncMock(return_value=lock))
        )
        stack.enter_context(patch.object(locks, "release_memory_write_lock", release))
        stack.enter_context(patch("app.modules.memory.instruct.SessionLocal", FakeSessionCM()))
        stack.enter_context(
            patch(
                "app.modules.memory.instruct.load_memory_snapshot",
                AsyncMock(return_value=snapshot or _snapshot()),
            )
        )
        stack.enter_context(
            patch("app.modules.memory.instruct.memory_llm.instruct_memory", instruct)
        )
        stack.enter_context(patch("app.modules.memory.instruct.apply_memory_facts", apply))
        yield apply, instruct, release


@pytest.mark.asyncio
async def test_an_instruction_is_saved_like_remember_this():
    result = MemoryFactUpdateResult(
        ops=[
            MemoryFactOp(
                op="add",
                type="fact",
                topic="preferences",
                text="User wants lists under five items.",
                confidence=0.3,
            ),
            MemoryFactOp(
                op="add",
                type="fact",
                topic="notes",
                text="User has been dating Sam.",
                confidence=0.9,
                sensitivity="relationship",
            ),
        ],
        reply="Saved two things.",
    )
    with _patches(result=result) as (apply, instruct, release):
        outcome = await instruct_service.apply_memory_instruction(
            Settings(),
            user_id=uuid4(),
            instruction="Keep lists under five things, and remember I'm dating Sam",
            focus_topic="Preferences",
        )

    assert outcome.applied == 2
    assert outcome.reply == "Saved two things."
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    # Low confidence and a sensitive topic both pass: the user asked for them.
    assert [(write.topic, write.type) for write in writes] == [
        ("preferences", "preference"),
        ("notes", "fact"),
    ]
    # A hand edit: if it changes saved facts, the history scan skips older lines.
    assert apply.await_args.kwargs["manual_edit"] is True
    assert instruct.await_args.kwargs["focus_topic"] == "preferences"
    assert instruct.await_args.kwargs["existing_areas"][0]["topic"] == "area:recall"
    release.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_instruction_with_nothing_to_change_only_replies():
    result = MemoryFactUpdateResult(ops=[], reply="That isn't something to remember.")
    with _patches(result=result) as (apply, _, _release):
        outcome = await instruct_service.apply_memory_instruction(
            Settings(), user_id=uuid4(), instruction="What's the weather?"
        )
    assert outcome.applied == 0
    assert outcome.reply == "That isn't something to remember."
    apply.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("landed", "reply"),
    [
        # The model said it removed the fact; the stale match dropped it.
        ([], instruct_service.NOTHING_CHANGED_REPLY),
        # One of two edits landed.
        (["delete"], "Memory updated: 1 removed."),
        (["delete", "add"], "Removed tea and saved coffee."),
    ],
)
async def test_the_reply_says_what_was_actually_applied(landed, reply):
    result = MemoryFactUpdateResult(
        ops=[
            MemoryFactOp(
                op="delete", type="fact", text="", confidence=1.0, match_text="User likes tea"
            ),
            MemoryFactOp(op="add", type="fact", text="User likes coffee", confidence=0.9),
        ],
        reply="Removed tea and saved coffee.",
    )
    with _patches(result=result, applied_ops=landed):
        outcome = await instruct_service.apply_memory_instruction(
            Settings(), user_id=uuid4(), instruction="I switched from tea to coffee"
        )
    assert outcome.applied == len(landed)
    assert outcome.reply == reply


@pytest.mark.asyncio
async def test_a_failed_model_call_raises_and_releases_the_lock():
    with _patches(result=None) as (apply, _, release):
        with pytest.raises(instruct_service.MemoryInstructionFailedError):
            await instruct_service.apply_memory_instruction(
                Settings(), user_id=uuid4(), instruction="Remember I like tea"
            )
    apply.assert_not_awaited()
    release.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_off_raises_before_calling_the_model():
    with _patches(result=None, snapshot=_snapshot(enabled=False)) as (_, instruct, _release):
        with pytest.raises(instruct_service.MemoryOffError):
            await instruct_service.apply_memory_instruction(
                Settings(), user_id=uuid4(), instruction="Remember I like tea"
            )
    instruct.assert_not_awaited()


@pytest.mark.asyncio
async def test_busy_memory_raises_without_calling_the_model():
    with _patches(result=None, lock=None) as (_, instruct, release):
        with pytest.raises(locks.MemoryWriteLockBusyError):
            await instruct_service.apply_memory_instruction(
                Settings(), user_id=uuid4(), instruction="Remember I like tea"
            )
    instruct.assert_not_awaited()
    release.assert_not_awaited()
