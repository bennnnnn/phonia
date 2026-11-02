"""What a chat line asks of memory, turn by turn, on the real database.

The memory model is faked: each pass returns the ops a model plausibly writes, and
the rest of the pass (backlog, sensitivity gate, writes) is the real code.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.orm import Chat, Memory, Message
from app.models.schemas.common import MemorySensitivity
from app.modules.memory.extraction_workflow import extract_and_store_memories
from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult
from app.repositories import users as users_repo

_T0 = datetime(2026, 10, 1, tzinfo=UTC)


class _Reuse:
    """Hand the test's session to code that opens its own sessions."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return None


class _MemoryModel:
    """Returns the ops queued for the next pass and records what each pass read."""

    def __init__(self) -> None:
        self.ops: list[MemoryFactOp] = []
        self.earlier: list[str] = []

    async def __call__(self, _settings, _transcript, **kwargs):
        self.earlier.append(kwargs.get("earlier", ""))
        ops, self.ops = self.ops, []
        return MemoryFactUpdateResult(ops=ops)


@pytest.fixture
def model(db_session):
    fake = _MemoryModel()
    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", lambda: _Reuse(db_session)),
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", fake),
    ):
        yield fake


async def _chat(session) -> Chat:
    user = await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    chat = Chat(user_id=user.id, title="Dinner")
    session.add(chat)
    await session.flush()
    return chat


async def _turn(session, chat: Chat, minute: int, line: str, reply: str = "Okay.") -> None:
    """One user line and its reply, then the memory pass that follows the turn."""
    for offset, (role, text) in enumerate((("user", line), ("assistant", reply))):
        session.add(
            Message(
                chat_id=chat.id,
                user_id=chat.user_id,
                role=role,
                content=text,
                created_at=_T0 + timedelta(minutes=minute, seconds=offset),
            )
        )
    await session.flush()
    await extract_and_store_memories(
        Settings(), user_id=chat.user_id, chat_id=chat.id, transcript=f"User: {line}"
    )


async def _active(session, chat: Chat) -> list[str]:
    rows = await session.execute(
        select(Memory.text).where(Memory.user_id == chat.user_id, Memory.status == "active")
    )
    return sorted(rows.scalars())


def _add(text: str, *, sensitivity: MemorySensitivity = "normal") -> MemoryFactOp:
    return MemoryFactOp(
        op="add",
        topic="preferences",
        type="preference",
        text=text,
        confidence=0.95,
        sensitivity=sensitivity,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("then", "kept"),
    [
        # "That" is what the line before asked to remember.
        ("Actually, forget that.", []),
        ("forget that please, I was joking", []),
        # A forget that names something else leaves it alone.
        ("Forget my old address", ["User is vegetarian"]),
    ],
)
async def test_a_bare_forget_drops_what_the_line_before_remembered(db_session, model, then, kept):
    chat = await _chat(db_session)
    model.ops = [_add("User is vegetarian")]
    await _turn(db_session, chat, 1, "Remember I'm vegetarian", "Got it, you're vegetarian.")
    assert await _active(db_session, chat) == ["User is vegetarian"]

    # The model names no fact: the line alone does not say what "that" is.
    await _turn(db_session, chat, 2, then, "Done.")

    assert await _active(db_session, chat) == kept
    # The model is shown the exchange the line points back at.
    assert "User: Remember I'm vegetarian" in model.earlier[-1]
    assert "Assistant: Got it, you're vegetarian." in model.earlier[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lines",
    [
        # "That" is the recipe, not the saved fact.
        ("Remember I'm vegetarian", "What's a good lentil recipe?"),
        ("Remember I'm vegetarian, and suggest a dinner for tonight",),
    ],
)
async def test_a_bare_forget_after_a_question_leaves_the_fact_to_the_model(
    db_session, model, lines
):
    chat = await _chat(db_session)
    model.ops = [_add("User is vegetarian")]
    for minute, line in enumerate(lines, start=1):
        await _turn(db_session, chat, minute, line, "Try a dal.")

    await _turn(db_session, chat, len(lines) + 1, "forget that, something with fish", "Sure.")

    assert await _active(db_session, chat) == ["User is vegetarian"]
    assert model.earlier[0] == ""  # an ordinary pass reads no earlier exchange


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("line", "saved"),
    [
        ("Remember, I'm allergic to peanuts.", True),
        ("remember: I'm allergic to peanuts", True),
        ("Remember I've got a peanut allergy", True),
        ("Save to memory that I'm allergic to peanuts", True),
        # Said in passing, a health fact is not stored unless the user opted in.
        ("I'm allergic to peanuts, what should I cook?", False),
    ],
)
async def test_an_asked_for_sensitive_fact_is_saved(db_session, model, line, saved):
    chat = await _chat(db_session)
    model.ops = [_add("User is allergic to peanuts", sensitivity="health")]

    await _turn(db_session, chat, 1, line)

    assert await _active(db_session, chat) == (["User is allergic to peanuts"] if saved else [])


@pytest.mark.asyncio
async def test_a_failed_pass_on_a_chats_last_line_is_saved_on_the_jobs_retry(db_session, model):
    """No next turn will read "remember …" again: the job's own retry does."""
    from app.background import handlers

    chat = await _chat(db_session)
    line = "Remember, I'm allergic to peanuts."
    db_session.add(Message(chat_id=chat.id, user_id=chat.user_id, role="user", content=line))
    await db_session.flush()
    payload = {"user_id": str(chat.user_id), "chat_id": str(chat.id), "transcript": f"User: {line}"}

    failed = AsyncMock(return_value=None)
    with (
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", failed),
        pytest.raises(RuntimeError),
    ):
        await handlers._handle_memory(Settings(), payload)
    assert await _active(db_session, chat) == []

    model.ops = [_add("User is allergic to peanuts", sensitivity="health")]
    await handlers._handle_memory(Settings(), payload)

    assert await _active(db_session, chat) == ["User is allergic to peanuts"]
