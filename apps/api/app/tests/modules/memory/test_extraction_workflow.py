"""Memory extraction after a turn: what is learned, written, re-embedded or skipped."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.memory.text import embedding_text_hash
from app.tests.fakes import FakeSessionCM, fake_session, redis_mock
from app.tests.modules.memory.embedding_support import EMBED_MANY, embed_each


def _memory_extraction_sessions(*, count: int = 1) -> tuple[AsyncMock, list[FakeSessionCM]]:
    session = fake_session()
    return session, [FakeSessionCM(session) for _ in range(count)]


@pytest.fixture(autouse=True)
def _memory_persistence_gate_enabled():
    with patch("app.modules.memory.repository.lock_memory_enabled", AsyncMock(return_value=True)):
        yield


@pytest.fixture(autouse=True)
def _no_memory_areas():
    with patch("app.modules.memory.repository.list_areas", AsyncMock(return_value=[])):
        yield


@pytest.fixture
def embedding_write():
    with patch("app.modules.memory.repository.update_embedding_if_current", AsyncMock()) as write:
        yield write


@pytest.fixture(autouse=True)
def _memory_write_lock_always_free():
    """extract_and_store_memories now acquires memwrite:{user_id} before its
    read-modify-write section (guards against a concurrent consolidation
    pass racing it). These tests exercise extraction logic, not Redis
    locking, so default the lock to always-acquired;
    test_extract_and_store_skips_when_write_lock_held overrides this to test
    the lock-held path specifically."""
    with (
        patch(
            "app.modules.memory.extraction_workflow.acquire_memory_write_lock",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.memory.extraction_workflow.release_memory_write_lock", AsyncMock()),
        patch(
            "app.modules.memory.extract_backlog.chat_history.user_lines_since",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extract_backlog.get_redis_client",
            MagicMock(return_value=redis_mock(get=None)),
        ),
    ):
        yield


# ── background: memory extraction ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_and_store_no_result():
    from app.modules.memory.extraction_workflow import extract_and_store_memories

    settings = Settings(memory_min_confidence=0.5)
    _, session_locals = _memory_extraction_sessions()
    with (
        patch(
            "app.modules.memory.extraction_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True)),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
    ):
        # should not raise
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript="hello"
        )


@pytest.mark.asyncio
async def test_the_extraction_prompt_lists_each_saved_fact_without_its_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every turn's pass sends every saved fact. An op names the fact it changes by its
    text, so a row id (and JSON spacing) only cost tokens: about 34 a fact, a third of
    the call at 40 facts."""
    from app.gateways import litellm_gateway, mock_llm
    from app.modules.memory import llm as memory_llm
    from app.modules.memory.extraction_workflow import load_memory_snapshot

    rows = [
        SimpleNamespace(
            id=uuid4(), type="fact", topic="notes", text=f"User fact {i}", last_confirmed_at=None
        )
        for i in range(40)
    ]
    with (
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True)),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=rows),
        ),
    ):
        snapshot = await load_memory_snapshot(fake_session(), uuid4())
    captured: dict[str, Any] = {}

    async def complete(**call: Any) -> None:
        captured.update(call)

    monkeypatch.setattr(mock_llm, "should_mock_llm", lambda _settings: False)
    monkeypatch.setattr(litellm_gateway, "complete_structured", complete)
    await memory_llm.revise_memory_facts(
        Settings(),
        "User: I moved to Paris",
        existing_facts=snapshot.prompt_facts,
        existing_areas=snapshot.prompt_areas,
    )
    prompt = captured["messages"][1]["content"]
    facts = prompt.split("Existing facts JSON:\n", 1)[1].split("\n\n", 1)[0]
    assert json.loads(facts) == [
        {"type": "fact", "topic": "notes", "text": row.text} for row in rows
    ]
    assert not any(str(row.id) in prompt for row in rows)
    # The labels around each fact's text: 42 characters (94 with the id and spaces).
    assert len(facts) - sum(len(row.text) for row in rows) <= 43 * len(rows)


@pytest.mark.asyncio
async def test_extract_and_store_filters_confidence():
    from app.modules.memory.extraction_workflow import extract_and_store_memories
    from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult

    settings = Settings(memory_min_confidence=0.7)
    extraction = MemoryFactUpdateResult(
        ops=[
            MemoryFactOp(op="add", type="fact", text="Uses Vim daily.", confidence=0.9),
            MemoryFactOp(op="add", type="fact", text="Low conf fact.", confidence=0.3),
        ]
    )
    apply = AsyncMock()
    _, session_locals = _memory_extraction_sessions()
    with (
        patch(
            "app.modules.memory.extraction_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True)),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(return_value=extraction),
        ),
        patch("app.modules.memory.extraction_workflow.apply_memory_facts", apply),
    ):
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript="I like using Vim daily."
        )
    apply.assert_awaited_once()
    writes = apply.await_args.kwargs["writes"]
    assert len(writes) == 1
    assert writes[0].text == "Uses Vim daily"


@pytest.mark.asyncio
async def test_extract_and_store_swallows_exception():
    from app.modules.memory.extraction_workflow import extract_and_store_memories

    settings = Settings()
    _, session_locals = _memory_extraction_sessions()
    with (
        patch(
            "app.modules.memory.extraction_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True)),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await extract_and_store_memories(
                settings, user_id=uuid4(), chat_id=uuid4(), transcript="I like Python a lot."
            )


@pytest.mark.parametrize("memory_enabled", [False, True])
@pytest.mark.asyncio
async def test_extract_and_store_learns_nothing_while_memory_is_off(memory_enabled):
    """A job queued before memory was switched off reads and writes nothing. The same
    lines with memory on are the control: they reach the model and the write."""
    from app.modules.memory.extraction_workflow import extract_and_store_memories
    from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult

    settings = Settings(memory_min_confidence=0.4)
    learned = MemoryFactUpdateResult(
        ops=[MemoryFactOp(op="add", type="fact", text="Works at Uber", confidence=0.9)]
    )
    revise = AsyncMock(return_value=learned)
    write = AsyncMock(return_value=[])
    _, session_locals = _memory_extraction_sessions(count=3)
    with (
        patch(
            "app.modules.memory.extraction_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=memory_enabled)),
        ),
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", revise),
        patch("app.modules.memory.extraction_workflow.apply_memory_facts", write),
    ):
        await extract_and_store_memories(
            settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="I live in Austin and work at Uber.",
        )

    assert revise.await_count == int(memory_enabled)
    assert write.await_count == int(memory_enabled)


@pytest.mark.asyncio
async def test_extract_and_store_skips_when_write_lock_held():
    """BUG FIX: without a lock, extraction and a concurrently-running
    consolidation pass for the same user can both read the same prior
    section text and whichever commits last silently discards the other's
    write. When memwrite:{user_id} is already held (by consolidation or
    another extraction), this run must skip entirely — no LLM call, no DB
    write — rather than proceed unprotected.

    Uses plain (non-raising) mocks and asserts they were never awaited,
    rather than side_effect=AssertionError, because extract_and_store_memories
    swallows all internal exceptions (Golden Rule 4) — a raised AssertionError
    would just be caught and logged, silently passing even pre-fix."""
    from app.modules.memory.extraction_workflow import extract_and_store_memories

    settings = Settings()
    get_by_id = AsyncMock()
    revise = AsyncMock()
    upsert = AsyncMock()
    with (
        patch(
            "app.modules.memory.extraction_workflow.acquire_memory_write_lock",
            AsyncMock(return_value=False),
        ),
        patch("app.modules.memory.extraction_workflow.users_repo.get_by_id", get_by_id),
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", revise),
        patch("app.modules.memory.extraction_workflow.apply_memory_facts", upsert),
    ):
        await extract_and_store_memories(settings, user_id=uuid4(), chat_id=uuid4(), transcript="t")

    get_by_id.assert_not_awaited()
    revise.assert_not_awaited()
    upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_and_store_reembeds_when_text_changed(embedding_write):
    from app.modules.memory.extraction_workflow import extract_and_store_memories
    from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult

    settings = Settings(memory_min_confidence=0.4)
    extraction = MemoryFactUpdateResult(
        ops=[
            MemoryFactOp(
                op="update",
                type="preference",
                text="likes TypeScript",
                confidence=0.9,
                match_text="likes Python",
            )
        ]
    )
    memory_id = uuid4()
    existing = MagicMock()
    existing.id = memory_id
    existing.type = "preference"
    existing.text = "likes Python"
    existing.embedding_json = "[0.1,0.2]"
    updated = MagicMock()
    updated.id = memory_id
    updated.type = "preference"
    updated.text = "likes TypeScript"
    updated.embedding_json = "[0.1,0.2]"
    updated.embedding = [0.1, 0.2]
    updated.embedding_text_hash = "stale"

    embed_calls = AsyncMock(return_value=[0.9, 0.8])
    _, session_locals = _memory_extraction_sessions(count=3)
    with (
        patch(
            "app.modules.memory.extraction_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True)),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[existing]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_embed_state",
            AsyncMock(
                return_value=[
                    (
                        updated.id,
                        updated.text,
                        updated.embedding is not None,
                        updated.embedding_text_hash,
                    )
                ]
            ),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(return_value=extraction),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.apply_writes",
            AsyncMock(return_value=[memory_id]),
        ),
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()),
        patch(EMBED_MANY, embed_each(embed_calls)),
    ):
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript="I like TypeScript now."
        )

    embed_calls.assert_awaited_once()
    embedding_write.assert_awaited_once()
    assert embedding_write.await_args.args[2:] == (
        updated.id,
        updated.text,
        [0.9, 0.8],
        embedding_text_hash(updated.text),
    )
    assert embedding_write.await_args.kwargs == {"commit": False}


@pytest.mark.asyncio
async def test_extract_and_store_reembeds_when_pgvector_missing(embedding_write):
    from app.modules.memory.extraction_workflow import extract_and_store_memories
    from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult

    settings = Settings(memory_min_confidence=0.4)
    extraction = MemoryFactUpdateResult(
        ops=[MemoryFactOp(op="add", type="preference", text="likes TypeScript", confidence=0.9)]
    )
    memory_id = uuid4()
    existing = MagicMock()
    existing.id = memory_id
    existing.type = "preference"
    existing.text = "likes TypeScript"
    existing.embedding_json = "[0.1,0.2]"
    updated = MagicMock()
    updated.id = memory_id
    updated.type = "preference"
    updated.text = "likes TypeScript"
    updated.embedding_json = "[0.1,0.2]"
    updated.embedding = None
    updated.embedding_text_hash = None

    embed_calls = AsyncMock(return_value=[0.9, 0.8])
    _, session_locals = _memory_extraction_sessions(count=3)
    with (
        patch(
            "app.modules.memory.extraction_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True)),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[existing]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_embed_state",
            AsyncMock(
                return_value=[
                    (
                        updated.id,
                        updated.text,
                        updated.embedding is not None,
                        updated.embedding_text_hash,
                    )
                ]
            ),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(return_value=extraction),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.apply_writes",
            AsyncMock(return_value=[memory_id]),
        ),
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()),
        patch(EMBED_MANY, embed_each(embed_calls)),
    ):
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript="I like TypeScript now."
        )

    embed_calls.assert_awaited_once()
    embedding_write.assert_awaited_once()
    assert embedding_write.await_args.args[2:] == (
        updated.id,
        updated.text,
        [0.9, 0.8],
        embedding_text_hash(updated.text),
    )
    assert embedding_write.await_args.kwargs == {"commit": False}


@pytest.mark.asyncio
async def test_extract_and_store_reembeds_stale_hash_even_when_text_unchanged_this_pass(
    embedding_write,
):
    from app.modules.memory.extraction_workflow import extract_and_store_memories
    from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult

    settings = Settings(memory_min_confidence=0.4)
    extraction = MemoryFactUpdateResult(
        ops=[MemoryFactOp(op="add", type="preference", text="likes TypeScript", confidence=0.9)]
    )
    memory_id = uuid4()
    existing = MagicMock()
    existing.id = memory_id
    existing.type = "preference"
    existing.text = "likes TypeScript"
    existing.embedding_json = "[0.1,0.2]"
    updated = MagicMock()
    updated.id = memory_id
    updated.type = "preference"
    updated.text = "likes TypeScript"
    updated.embedding = [0.1, 0.2]
    updated.embedding_json = "[0.1,0.2]"
    updated.embedding_text_hash = "stale-hash-from-a-failed-embed"

    embed_calls = AsyncMock(return_value=[0.9, 0.8])
    _, session_locals = _memory_extraction_sessions(count=3)
    with (
        patch(
            "app.modules.memory.extraction_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True)),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[existing]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_embed_state",
            AsyncMock(
                return_value=[
                    (
                        updated.id,
                        updated.text,
                        updated.embedding is not None,
                        updated.embedding_text_hash,
                    )
                ]
            ),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(return_value=extraction),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.apply_writes",
            AsyncMock(return_value=[memory_id]),
        ),
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()),
        patch(EMBED_MANY, embed_each(embed_calls)),
    ):
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript="I like TypeScript now."
        )

    embed_calls.assert_awaited_once()
    embedding_write.assert_awaited_once()
    assert embedding_write.await_args.args[2:] == (
        updated.id,
        updated.text,
        [0.9, 0.8],
        embedding_text_hash(updated.text),
    )
    assert embedding_write.await_args.kwargs == {"commit": False}


@pytest.mark.asyncio
async def test_extract_and_store_releases_db_before_provider_io_without_write_commit():
    from app.modules.memory.extraction_workflow import extract_and_store_memories

    session = AsyncMock()
    session.commit = AsyncMock()
    db_open_during_extract: list[bool] = []

    class _OpenTrackingSessionCM(FakeSessionCM):
        open = False

        async def __aenter__(self) -> AsyncMock:
            self.open = True
            return await super().__aenter__()

        async def __aexit__(self, *args: object) -> bool:
            self.open = False
            return False

    load_cm = _OpenTrackingSessionCM(session)

    async def fake_revise(*_args: object, **_kwargs: object) -> None:
        db_open_during_extract.append(load_cm.open)
        return None

    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", return_value=load_cm),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True)),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(side_effect=fake_revise),
        ),
    ):
        await extract_and_store_memories(
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="I like short answers.",
        )

    assert db_open_during_extract == [False]
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("line", "reads_facts"),
    [("thanks!", False), ("ok", False), ("I just moved to Lisbon for work", True)],
)
async def test_a_pass_reads_the_saved_facts_only_for_lines_the_model_sees(
    line: str, reads_facts: bool
) -> None:
    """A "thanks" read the user's every fact and area (two statements, up to 150 rows)
    before the pass found nothing to learn and moved on."""
    from app.modules.memory.extraction_workflow import extract_and_store_memories

    facts = AsyncMock(return_value=[])
    areas = AsyncMock(return_value=[])
    revise = AsyncMock(return_value=None)
    _, session_locals = _memory_extraction_sessions()
    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", side_effect=session_locals),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True, memory_edited_at=None)),
        ),
        patch("app.modules.memory.extraction_workflow.memories_repo.list_for_user", facts),
        patch("app.modules.memory.extraction_workflow.memories_repo.list_areas", areas),
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", revise),
    ):
        await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript=f"User: {line}"
        )
    assert (facts.await_count, areas.await_count, revise.await_count) == (
        (1, 1, 1) if reads_facts else (0, 0, 0)
    )
