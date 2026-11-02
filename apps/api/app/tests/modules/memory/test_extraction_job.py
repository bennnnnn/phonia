import asyncio
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import Memory
from app.models.schemas.common import MemoryType
from app.modules.memory.extraction_workflow import extract_and_store_memories, extract_history_chat
from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult
from app.modules.memory.text import embedding_text_hash
from app.modules.memory.writes_repository import MemoryFactWrite
from app.tests.fakes import FakeSessionCM, redis_mock
from app.tests.modules.memory.embedding_support import EMBED_MANY, embed_each

_CANDIDATE = "I like using Vim every day at work."


def _extraction_sessions(*, count: int = 1) -> tuple[AsyncMock, list[FakeSessionCM]]:
    session = AsyncMock()
    session.commit = AsyncMock()
    return session, [FakeSessionCM(session) for _ in range(count)]


def _ops(*ops: MemoryFactOp) -> MemoryFactUpdateResult:
    return MemoryFactUpdateResult(ops=list(ops))


def _add(memory_type: MemoryType, text: str, confidence: float = 0.9) -> MemoryFactOp:
    return MemoryFactOp(op="add", type=memory_type, text=text, confidence=confidence)


def _user() -> MagicMock:
    return MagicMock(memory_enabled=True, memory_include_sensitive=False)


@pytest.fixture
def _real_memory_lock():
    return True


@pytest.fixture(autouse=True)
def _memory_persistence_gate_enabled():
    with patch("app.modules.memory.repository.lock_memory_enabled", AsyncMock(return_value=True)):
        yield


@pytest.fixture
def embedding_write():
    with patch("app.modules.memory.repository.update_embedding_if_current", AsyncMock()) as write:
        yield write


@pytest.fixture(autouse=True)
def _memory_extract_backlog_noop():
    with (
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


@pytest.fixture(autouse=True)
def _memory_write_lock_always_free(request: pytest.FixtureRequest):
    if "_real_memory_lock" in request.fixturenames:
        yield
        return
    with (
        patch(
            "app.modules.memory.extraction_workflow.acquire_memory_write_lock",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.memory.extraction_workflow.release_memory_write_lock", AsyncMock()),
    ):
        yield


@contextmanager
def _extract_patches(
    *,
    session_locals: list[FakeSessionCM],
    extraction: MemoryFactUpdateResult | None,
    apply: AsyncMock,
    listed: list | None = None,
    user: MagicMock | None = None,
):
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.modules.memory.extraction_workflow.SessionLocal", side_effect=session_locals)
        )
        stack.enter_context(
            patch(
                "app.modules.memory.extraction_workflow.users_repo.get_by_id",
                AsyncMock(return_value=user or _user()),
            )
        )
        # A saved fact row has every column the snapshot reads.
        rows = [SimpleNamespace(**{"last_confirmed_at": None, **vars(row)}) for row in listed or []]
        stack.enter_context(
            patch(
                "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
                AsyncMock(return_value=rows),
            )
        )
        stack.enter_context(
            patch(
                "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
                AsyncMock(return_value=extraction),
            )
        )
        stack.enter_context(
            patch("app.modules.memory.extraction_workflow.apply_memory_facts", apply)
        )
        yield


@pytest.mark.asyncio
async def test_extract_and_store_all_sections_below_confidence_skips_upsert():
    settings = Settings(memory_min_confidence=0.7)
    extraction = _ops(
        _add("fact", "Low conf fact one.", 0.2),
        _add("fact", "Low conf fact two.", 0.3),
    )
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()

    with _extract_patches(session_locals=session_locals, extraction=extraction, apply=apply):
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript=_CANDIDATE
        )

    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_skips_when_user_missing():
    settings = Settings(memory_min_confidence=0.4)
    apply = AsyncMock()
    revise = AsyncMock()
    _, session_locals = _extraction_sessions()

    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", side_effect=session_locals),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            revise,
        ),
        patch("app.modules.memory.extraction_workflow.apply_memory_facts", apply),
    ):
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript=_CANDIDATE
        )

    apply.assert_not_awaited()
    revise.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_skips_non_candidate_small_talk():
    apply = AsyncMock()
    revise = AsyncMock()
    stamp = AsyncMock()
    _, session_locals = _extraction_sessions()
    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", side_effect=session_locals),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=_user()),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.expand_memory_extract_transcript",
            AsyncMock(return_value=("hey there", "cursor-1")),
        ),
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", revise),
        patch("app.modules.memory.extraction_workflow.apply_memory_facts", apply),
        patch("app.modules.memory.extraction_workflow.stamp_extract_cursor", stamp),
    ):
        await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript="hey there"
        )

    revise.assert_not_awaited()
    apply.assert_not_awaited()
    # The lines were read. Keeping the cursor would let a run of small talk fill
    # the backlog page and hide every later line in the chat.
    stamp.assert_awaited_once()
    assert stamp.await_args.args[2] == "cursor-1"


@contextmanager
def _cursor_patches(*, revise: AsyncMock, give_up: bool = False):
    stamp = AsyncMock()
    note_failed = AsyncMock(return_value=give_up)
    clear_failed = AsyncMock()
    _, session_locals = _extraction_sessions()
    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", side_effect=session_locals),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=_user()),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.expand_memory_extract_transcript",
            AsyncMock(return_value=("User: I build mobile apps with Expo", "cursor-2")),
        ),
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", revise),
        patch("app.modules.memory.extraction_workflow.apply_memory_facts", AsyncMock()),
        patch("app.modules.memory.extraction_workflow.stamp_extract_cursor", stamp),
        patch("app.modules.memory.extraction_workflow.note_failed_extract_pass", note_failed),
        patch("app.modules.memory.extraction_workflow.clear_failed_extract_passes", clear_failed),
    ):
        yield SimpleNamespace(stamp=stamp, note_failed=note_failed, clear_failed=clear_failed)


@pytest.mark.asyncio
async def test_extract_keeps_cursor_when_the_model_call_fails(caplog: pytest.LogCaptureFixture):
    with _cursor_patches(revise=AsyncMock(return_value=None)) as patched:
        with caplog.at_level("WARNING", logger="app.modules.memory.extraction_workflow"):
            await extract_and_store_memories(
                Settings(), user_id=uuid4(), chat_id=uuid4(), transcript="unused"
            )

    patched.note_failed.assert_awaited_once()
    patched.stamp.assert_not_awaited()
    patched.clear_failed.assert_not_awaited()
    assert "memory_extract_model_failed" in caplog.text


@pytest.mark.asyncio
async def test_extract_moves_on_after_repeated_model_failures():
    with _cursor_patches(revise=AsyncMock(return_value=None), give_up=True) as patched:
        await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript="unused"
        )

    patched.stamp.assert_awaited_once()
    assert patched.stamp.await_args.args[2] == "cursor-2"


@pytest.mark.asyncio
async def test_extract_resets_failures_after_a_good_pass():
    revise = AsyncMock(return_value=_ops(_add("project", "User builds mobile apps with Expo.")))
    with _cursor_patches(revise=revise) as patched:
        await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript="unused"
        )

    patched.note_failed.assert_not_awaited()
    patched.clear_failed.assert_awaited_once()
    patched.stamp.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_saves_working_on_project_when_model_returns_nothing():
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    with _extract_patches(session_locals=session_locals, extraction=None, apply=apply):
        await extract_and_store_memories(
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: I am working on a chemistry solver",
        )
    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert len(writes) == 1
    assert writes[0].type == "project"
    assert writes[0].op == "add"
    assert "chemistry solver" in writes[0].text.lower()


@pytest.mark.asyncio
async def test_extract_forget_does_not_save_the_project_being_forgotten():
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    with _extract_patches(session_locals=session_locals, extraction=None, apply=apply):
        await extract_and_store_memories(
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: Please forget that I am working on Recall",
        )
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_runs_on_favorite_color_self_fact():
    extraction = _ops(_add("fact", "Favorite color is blue."))
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    with _extract_patches(session_locals=session_locals, extraction=extraction, apply=apply):
        await extract_and_store_memories(
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="My favorite color is blue.",
        )
    apply.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transcript",
    [
        "As a software engineer at Uber, I work on mobile apps.",
        "I want short, direct answers with examples.",
        "Please keep replies concise and show the steps.",
    ],
)
async def test_extract_sends_natural_personal_statements_to_memory_model(transcript: str):
    _, session_locals = _extraction_sessions()
    revise = AsyncMock(return_value=None)
    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", side_effect=session_locals),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=_user()),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            revise,
        ),
    ):
        await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript=transcript
        )

    revise.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_and_store_drops_section_with_empty_summary_after_normalize():
    settings = Settings(memory_min_confidence=0.4)
    extraction = _ops(
        _add("fact", "..."),
        _add("fact", "Uses Vim daily."),
    )
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()

    with _extract_patches(session_locals=session_locals, extraction=extraction, apply=apply):
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript=_CANDIDATE
        )

    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert len(writes) == 1
    assert writes[0].text == "Uses Vim daily"
    assert not writes[0].text.startswith("As of ")


@pytest.mark.asyncio
async def test_extract_explicit_remember_adds_short_preference():
    settings = Settings(memory_min_confidence=0.4)
    pref_id = uuid4()
    prior = (
        "Bini prefers varied learning formats for English vocabulary sessions, "
        "alternating between teach then use, use then define, and occasional "
        "multiple-choice questions"
    )
    extraction = _ops(_add("preference", "Drinks oat milk."))
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()

    with _extract_patches(
        session_locals=session_locals,
        extraction=extraction,
        apply=apply,
        listed=[SimpleNamespace(id=pref_id, type="preference", text=prior, status="active")],
    ):
        await extract_and_store_memories(
            settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: Remember that I drink oat milk.",
        )

    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert len(writes) == 1
    assert writes[0].op == "add"
    assert "oat milk" in writes[0].text.lower()


@pytest.mark.asyncio
async def test_extract_and_store_deletes_fact_on_explicit_forget():
    settings = Settings(memory_min_confidence=0.4)
    fact_id = uuid4()
    extraction = _ops(
        MemoryFactOp(
            op="delete",
            type="fact",
            text="",
            confidence=0.9,
            match_text="Lives in Boston",
        )
    )
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()

    with _extract_patches(
        session_locals=session_locals,
        extraction=extraction,
        apply=apply,
        listed=[SimpleNamespace(id=fact_id, type="fact", text="Lives in Boston", status="active")],
    ):
        await extract_and_store_memories(
            settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: Please forget that I live in Boston",
        )

    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert writes[0].op == "delete"
    assert writes[0].match_text == "Lives in Boston"


@pytest.mark.asyncio
async def test_extract_forget_deletes_named_fact_when_the_model_returns_nothing():
    settings = Settings(memory_min_confidence=0.4)
    extraction = _ops()
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()

    with _extract_patches(
        session_locals=session_locals,
        extraction=extraction,
        apply=apply,
        listed=[
            SimpleNamespace(
                id=uuid4(),
                type="profile",
                text="Works as a nurse in Boston",
                status="active",
            ),
            SimpleNamespace(id=uuid4(), type="preference", text="Likes oat milk", status="active"),
        ],
    ):
        await extract_and_store_memories(
            settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: Forget that I'm a nurse",
        )

    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert len(writes) == 1
    assert writes[0].op == "delete"
    assert writes[0].match_text == "Works as a nurse in Boston"


@pytest.mark.asyncio
async def test_extract_forget_without_a_named_fact_does_not_wipe_memory():
    settings = Settings(memory_min_confidence=0.4)
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()

    with _extract_patches(
        session_locals=session_locals,
        extraction=_ops(),
        apply=apply,
        listed=[
            SimpleNamespace(
                id=uuid4(),
                type="profile",
                text="Works as a nurse in Boston",
                status="active",
            )
        ],
    ):
        await extract_and_store_memories(
            settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: Forget that",
        )

    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_forget_does_not_clear_unrelated_nonempty_sections():
    settings = Settings(memory_min_confidence=0.4)
    fact_id = uuid4()
    pref_id = uuid4()
    extraction = _ops(
        MemoryFactOp(
            op="delete",
            type="fact",
            text="",
            confidence=0.9,
            match_text="Lives in Boston",
        ),
        _add("preference", "Tea."),
    )
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()

    with _extract_patches(
        session_locals=session_locals,
        extraction=extraction,
        apply=apply,
        listed=[
            SimpleNamespace(id=fact_id, type="fact", text="Lives in Boston", status="active"),
            SimpleNamespace(
                id=pref_id,
                type="preference",
                text="Drinks strong coffee every morning and afternoon.",
                status="active",
            ),
        ],
    ):
        await extract_and_store_memories(
            settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: Please forget that I live in Boston",
        )

    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert {write.op for write in writes} == {"delete", "add"}
    assert any(write.op == "delete" and write.match_text == "Lives in Boston" for write in writes)
    assert any(write.op == "add" and "Tea" in write.text for write in writes)


@pytest.mark.asyncio
async def test_extract_applies_add_without_rewriting_unrelated_facts():
    settings = Settings(memory_min_confidence=0.4)
    prior = "User's name is Bini. User works at Hooh. User is a developer."
    extraction = _ops(_add("profile", "Bini is building Recall."))
    apply = AsyncMock()
    existing = [SimpleNamespace(id=uuid4(), type="profile", text=prior, status="active")]
    _, session_locals = _extraction_sessions()

    with _extract_patches(
        session_locals=session_locals,
        extraction=extraction,
        apply=apply,
        listed=existing,
    ):
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript="I am building Recall"
        )

    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert writes[0].op == "add"
    assert "Recall" in writes[0].text
    assert "Hooh" not in writes[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sensitivity,text,transcript",
    [
        ("highly_sensitive", "User is Catholic.", "I am Catholic."),
        ("health", "User has a peanut allergy.", "I have a peanut allergy."),
        ("finance", "User salary is $200k.", "I am paid a $200k salary."),
        ("legal", "User is divorcing.", "I am divorcing."),
        ("relationship", "User has a girlfriend.", "I have a girlfriend."),
        ("identity", "User ethnicity is listed.", "I am Catholic."),
    ],
)
async def test_extract_skips_sensitive_unless_remember_or_opt_in(sensitivity, text, transcript):
    settings = Settings(memory_min_confidence=0.4)
    extraction = _ops(
        MemoryFactOp(
            op="add",
            type="fact",
            text=text,
            confidence=0.9,
            sensitivity=sensitivity,
        )
    )
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    with _extract_patches(session_locals=session_locals, extraction=extraction, apply=apply):
        await extract_and_store_memories(
            settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript=transcript,
        )
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_persists_health_when_include_sensitive():
    settings = Settings(memory_min_confidence=0.4)
    extraction = _ops(
        MemoryFactOp(
            op="add",
            type="fact",
            text="User has a peanut allergy.",
            confidence=0.9,
            sensitivity="health",
        )
    )
    apply = AsyncMock()
    user = _user()
    user.memory_include_sensitive = True
    _, session_locals = _extraction_sessions()
    with _extract_patches(
        session_locals=session_locals, extraction=extraction, apply=apply, user=user
    ):
        await extract_and_store_memories(
            settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="I have a peanut allergy.",
        )
    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert writes[0].sensitivity == "health"


@pytest.mark.asyncio
async def test_extract_persists_highly_sensitive_on_explicit_remember():
    settings = Settings(memory_min_confidence=0.4)
    extraction = _ops(
        MemoryFactOp(
            op="add",
            type="fact",
            text="User is Catholic.",
            confidence=0.9,
            sensitivity="highly_sensitive",
        )
    )
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    with _extract_patches(session_locals=session_locals, extraction=extraction, apply=apply):
        await extract_and_store_memories(
            settings,
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: Remember that I am Catholic.",
        )
    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert writes[0].sensitivity == "highly_sensitive"


@pytest.mark.asyncio
async def test_extract_and_store_stores_embedding_for_new_memory(embedding_write):
    settings = Settings(memory_min_confidence=0.4)
    extraction = _ops(_add("fact", "Owns a bicycle."))
    memory_id = uuid4()
    listed = SimpleNamespace(id=memory_id, text="Owns a bicycle")
    vector = [0.4, 0.5, 0.6]
    apply_writes = AsyncMock(return_value=[memory_id])
    _session, session_locals = _extraction_sessions(count=3)
    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", side_effect=session_locals),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=_user()),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_embed_state",
            AsyncMock(return_value=[(listed.id, listed.text, False, None)]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(return_value=extraction),
        ),
        patch("app.modules.memory.extraction_workflow.memories_repo.apply_writes", apply_writes),
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()),
        patch(EMBED_MANY, embed_each(AsyncMock(return_value=vector))),
    ):
        await extract_and_store_memories(
            settings, user_id=uuid4(), chat_id=uuid4(), transcript=_CANDIDATE
        )

    embedding_write.assert_awaited_once()
    assert embedding_write.await_args.args[2:] == (
        memory_id,
        listed.text,
        vector,
        embedding_text_hash(listed.text),
    )
    assert embedding_write.await_args.kwargs == {"commit": False}


@pytest.mark.asyncio
@pytest.mark.usefixtures("_real_memory_lock")
async def test_extraction_and_consolidation_do_not_race_the_same_user(fake_redis):
    from app.modules.memory.consolidation_workflow import consolidate_user_memory_sections

    user_id = uuid4()
    text = "Prefers concise answers."
    keep = SimpleNamespace(
        id=uuid4(),
        type="preference",
        text=text,
        status="active",
        last_confirmed_at=None,
        updated_at=0,
        embedding=[0.1, 0.2, 0.3],
        embedding_json="[0.1,0.2,0.3]",
        embedding_text_hash=embedding_text_hash(text),
    )
    extra = SimpleNamespace(
        id=uuid4(),
        type="preference",
        text=text,
        status="active",
        last_confirmed_at=None,
        updated_at=0,
        embedding=[0.1, 0.2, 0.3],
        embedding_json="[0.1,0.2,0.3]",
        embedding_text_hash=embedding_text_hash(text),
    )
    extraction_result = _ops(_add("fact", "Uses Vim daily."))

    async def _slow_revise(*_args: object, **_kwargs: object) -> MemoryFactUpdateResult:
        await asyncio.sleep(0.05)
        return extraction_result

    apply = AsyncMock()
    extraction_session, _ = _extraction_sessions()
    consolidation_session = AsyncMock()
    consolidation_session.commit = AsyncMock()

    with (
        patch(
            "app.modules.memory.extraction_workflow.SessionLocal",
            side_effect=lambda: FakeSessionCM(extraction_session),
        ),
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=lambda: FakeSessionCM(consolidation_session),
        ),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=_user()),
        ),
        patch(
            "app.modules.memory.consolidation_workflow.users_repo.get_by_id",
            AsyncMock(return_value=_user()),
        ),
        patch(
            "app.modules.memory.repository.list_for_user",
            AsyncMock(return_value=[keep, extra]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(side_effect=_slow_revise),
        ),
        patch("app.modules.memory.extraction_workflow.apply_memory_facts", apply),
        patch("app.modules.memory.consolidation_workflow.apply_memory_facts", apply),
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()),
    ):
        await asyncio.gather(
            extract_and_store_memories(
                Settings(memory_min_confidence=0.4),
                user_id=user_id,
                chat_id=uuid4(),
                transcript=_CANDIDATE,
            ),
            consolidate_user_memory_sections(Settings(memory_min_confidence=0.4), user_id=user_id),
        )

    assert apply.await_count == 1


@pytest.mark.asyncio
async def test_extract_files_facts_into_documents():
    extraction = _ops(
        MemoryFactOp(
            op="add",
            type="fact",
            text="User is building Recall, a personal AI chat app.",
            confidence=0.9,
            topic="area:recall",
            topic_title="Recall",
            topic_summary="Personal AI chat app built with Expo",
        ),
        MemoryFactOp(
            op="add",
            type="fact",
            text="User prefers short answers.",
            confidence=0.9,
            topic="preferences",
        ),
        MemoryFactOp(
            op="add",
            type="fact",
            text="User uses FastAPI for backends.",
            confidence=0.9,
            topic="not-a-topic",
            topic_title="ignored",
        ),
    )
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    with _extract_patches(session_locals=session_locals, extraction=extraction, apply=apply):
        await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript=_CANDIDATE
        )

    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    area, preference, unknown = writes[:3]
    assert (area.topic, area.type) == ("area:recall", "project")
    assert area.area_title == "Recall"
    assert area.area_summary == "Personal AI chat app built with Expo"
    # The document decides the type.
    assert (preference.topic, preference.type) == ("preferences", "preference")
    # No valid topic: keep the model's type and let the writer pick the default.
    assert (unknown.topic, unknown.type, unknown.area_title) == (None, "fact", None)


@pytest.mark.asyncio
async def test_extract_shows_the_model_existing_topics_and_areas():
    existing = [
        Memory(
            id=uuid4(),
            user_id=uuid4(),
            type="project",
            topic="area:recall",
            text="User is building Recall.",
            status="active",
        )
    ]
    area = SimpleNamespace(key="area:recall", title="Recall", summary="AI chat app")
    revise = AsyncMock(return_value=None)
    _, session_locals = _extraction_sessions()
    with (
        _extract_patches(
            session_locals=session_locals, extraction=None, apply=AsyncMock(), listed=existing
        ),
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", revise),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_areas",
            AsyncMock(return_value=[area]),
        ),
    ):
        await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript=_CANDIDATE
        )

    kwargs = revise.await_args.kwargs
    assert kwargs["existing_facts"][0]["topic"] == "area:recall"
    assert kwargs["existing_areas"] == [
        {"topic": "area:recall", "title": "Recall", "summary": "AI chat app"}
    ]


def _history_patches(stack: ExitStack, *, lines: list[str], revise: AsyncMock, apply: AsyncMock):
    """Drive a history pass: the chat's lines come from the messages table."""
    edited_at = datetime(2026, 9, 20, tzinfo=UTC)
    user = MagicMock(
        memory_enabled=True, memory_include_sensitive=False, memory_edited_at=edited_at
    )
    read_lines = AsyncMock(return_value=[SimpleNamespace(content=line) for line in lines])
    _, session_locals = _extraction_sessions()
    stack.enter_context(
        patch("app.modules.memory.extraction_workflow.SessionLocal", side_effect=session_locals)
    )
    stack.enter_context(
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=user),
        )
    )
    stack.enter_context(
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        )
    )
    stack.enter_context(
        patch(
            "app.modules.memory.extract_backlog.chat_history.user_lines_since",
            read_lines,
        )
    )
    stack.enter_context(
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", revise)
    )
    stack.enter_context(patch("app.modules.memory.extraction_workflow.apply_memory_facts", apply))
    return read_lines, edited_at


@pytest.mark.asyncio
async def test_history_pass_reads_lines_after_the_last_hand_edit_and_leaves_cursors_alone():
    expand = AsyncMock()
    stamp = AsyncMock()
    note_failed = AsyncMock()
    revise = AsyncMock(return_value=None)
    chat_id = uuid4()
    with ExitStack() as stack:
        read_lines, edited_at = _history_patches(
            stack, lines=["I run every morning before work"], revise=revise, apply=AsyncMock()
        )
        stack.enter_context(
            patch("app.modules.memory.extraction_workflow.expand_memory_extract_transcript", expand)
        )
        stack.enter_context(
            patch("app.modules.memory.extraction_workflow.stamp_extract_cursor", stamp)
        )
        stack.enter_context(
            patch("app.modules.memory.extraction_workflow.note_failed_extract_pass", note_failed)
        )
        outcome = await extract_history_chat(Settings(), user_id=uuid4(), chat_id=chat_id)

    # The model gave nothing usable, so the scan must try this chat again.
    assert outcome == "model_failed"
    assert read_lines.await_args.args[1] == chat_id
    assert read_lines.await_args.kwargs["newer_than"] == edited_at
    expand.assert_not_awaited()
    assert revise.await_args.args[1] == "User: I run every morning before work"
    assert revise.await_args.kwargs["from_history"] is True
    note_failed.assert_not_awaited()
    stamp.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_pass_only_adds_what_memory_is_missing():
    revise = AsyncMock(
        return_value=_ops(
            _add("fact", "User is learning Rust on weekends."),
            MemoryFactOp(
                op="update",
                type="fact",
                text="User runs daily.",
                match_text="User runs weekly.",
                confidence=0.9,
            ),
            MemoryFactOp(
                op="delete", type="fact", text="", match_text="User likes chess.", confidence=0.9
            ),
        )
    )
    apply = AsyncMock()
    with ExitStack() as stack:
        _history_patches(
            stack, lines=["I have been learning Rust on weekends"], revise=revise, apply=apply
        )
        outcome = await extract_history_chat(Settings(), user_id=uuid4(), chat_id=uuid4())

    assert outcome is None
    kwargs = apply.await_args.kwargs
    writes: list[MemoryFactWrite] = kwargs["writes"]
    assert [(write.op, write.text) for write in writes] == [
        ("add", "User is learning Rust on weekends")
    ]
    # No saved fact to compare against, so an add that matches one leaves it alone.
    assert kwargs["expected_facts"] == {}
    assert kwargs["manual_edit"] is False


@pytest.mark.asyncio
async def test_history_pass_with_no_lines_after_the_last_edit_skips_the_model():
    revise = AsyncMock()
    with ExitStack() as stack:
        _history_patches(stack, lines=[], revise=revise, apply=AsyncMock())
        outcome = await extract_history_chat(Settings(), user_id=uuid4(), chat_id=uuid4())

    assert outcome is None
    revise.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transcript", "manual"),
    [("User: forget that I like chess", True), ("User: I stopped playing chess", False)],
)
async def test_a_forget_request_counts_as_a_hand_edit(transcript, manual):
    apply = AsyncMock()
    extraction = _ops(
        MemoryFactOp(
            op="delete", type="fact", text="", match_text="User likes chess.", confidence=0.9
        )
    )
    _, session_locals = _extraction_sessions()
    with _extract_patches(session_locals=session_locals, extraction=extraction, apply=apply):
        outcome = await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript=transcript
        )

    assert outcome is None
    kwargs = apply.await_args.kwargs
    assert [write.op for write in kwargs["writes"]] == ["delete"]
    assert kwargs["manual_edit"] is manual


def _listed(*texts: str) -> list[SimpleNamespace]:
    return [SimpleNamespace(id=uuid4(), type="fact", text=text, status="active") for text in texts]


@pytest.mark.asyncio
async def test_forget_word_does_not_delete_broader_fact():
    """M10: the backup delete needs the phrase, not one shared word."""
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    listed = _listed(
        "User uses React",
        "User builds Recall with React Native and FastAPI",
        "User's sister lives in Nairobi suburbs",
    )
    with _extract_patches(
        session_locals=session_locals, extraction=_ops(), apply=apply, listed=listed
    ):
        await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript="User: forget that I use React"
        )

    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert [(write.op, write.match_text) for write in writes] == [("delete", "User uses React")]


@pytest.mark.asyncio
async def test_forget_that_i_live_somewhere_leaves_my_sisters_home():
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    listed = _listed("User lives in Nairobi", "User's sister lives in Nairobi suburbs")
    with _extract_patches(
        session_locals=session_locals, extraction=_ops(), apply=apply, listed=listed
    ):
        await extract_and_store_memories(
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: forget that I live in Nairobi",
        )

    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert [write.match_text for write in writes] == ["User lives in Nairobi"]


@pytest.mark.asyncio
async def test_stop_bringing_up_my_job_mutes_the_fact_not_deletes_it():
    """M11: the model's mute op reaches the writes, and counts as a hand edit."""
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    extraction = _ops(
        MemoryFactOp(
            op="mute", type="profile", text="", match_text="User works at Uber", confidence=0.9
        )
    )
    with _extract_patches(
        session_locals=session_locals,
        extraction=extraction,
        apply=apply,
        listed=_listed("User works at Uber"),
    ):
        await extract_and_store_memories(
            Settings(), user_id=uuid4(), chat_id=uuid4(), transcript="User: stop bringing up my job"
        )

    kwargs = apply.await_args.kwargs
    assert [(write.op, write.match_text) for write in kwargs["writes"]] == [
        ("mute", "User works at Uber")
    ]
    assert kwargs["manual_edit"] is True


@pytest.mark.asyncio
async def test_a_mute_the_model_missed_still_mutes_the_named_fact():
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    with _extract_patches(
        session_locals=session_locals,
        extraction=_ops(),
        apply=apply,
        listed=_listed("User has a dog named Max", "User walks every evening"),
    ):
        await extract_and_store_memories(
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: stop mentioning my dog Max",
        )

    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert [(write.op, write.match_text) for write in writes] == [
        ("mute", "User has a dog named Max")
    ]


@pytest.mark.asyncio
async def test_a_do_not_mention_preference_is_kept_even_when_sensitive():
    """M11: "don't bring up my divorce again" is saved like an explicit remember."""
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    extraction = _ops(
        MemoryFactOp(
            op="add",
            type="preference",
            topic="preferences",
            text="User does not want their divorce brought up",
            confidence=0.9,
            sensitivity="legal",
        )
    )
    with _extract_patches(session_locals=session_locals, extraction=extraction, apply=apply):
        await extract_and_store_memories(
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: don't bring up my divorce again",
        )

    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert [write.text for write in writes] == ["User does not want their divorce brought up"]
    # Asked for in so many words: the 150-fact cap never pushes it out (M8).
    assert writes[0].importance == 1.0


@pytest.mark.asyncio
async def test_forget_everything_is_left_to_the_card():
    """M10: "forget everything you know about me" deletes nothing on its own."""
    apply = AsyncMock()
    revise = AsyncMock(return_value=_ops())
    _, session_locals = _extraction_sessions()
    with (
        _extract_patches(
            session_locals=session_locals,
            extraction=_ops(),
            apply=apply,
            listed=_listed("User knows everything about chess"),
        ),
        patch("app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts", revise),
    ):
        await extract_and_store_memories(
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: forget everything you know about me",
        )

    revise.assert_not_awaited()
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_correction_supersedes_and_counts_as_a_hand_edit():
    """M9: "that's wrong, I'm at Stripe now" replaces Uber, and the history scan can't undo it."""
    apply = AsyncMock()
    _, session_locals = _extraction_sessions()
    extraction = _ops(
        MemoryFactOp(
            op="supersede",
            type="profile",
            topic="profile",
            text="User works at Stripe",
            match_text="User works at Uber",
            confidence=0.9,
        )
    )
    with _extract_patches(
        session_locals=session_locals,
        extraction=extraction,
        apply=apply,
        listed=_listed("User works at Uber"),
    ):
        await extract_and_store_memories(
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="User: that's wrong, I'm at Stripe now",
        )

    kwargs = apply.await_args.kwargs
    assert [(write.op, write.text) for write in kwargs["writes"]] == [
        ("supersede", "User works at Stripe")
    ]
    assert kwargs["manual_edit"] is True


@pytest.mark.asyncio
async def test_the_extraction_prompt_names_decisions_mutes_and_corrections(monkeypatch):
    """M1/M9/M11: the memory model is told to keep decisions, mute, and supersede."""
    from app.modules.memory import llm as memory_llm

    captured: dict[str, object] = {}

    async def fake_complete(**kwargs):
        captured.update(kwargs)
        return _ops()

    monkeypatch.setattr(memory_llm.litellm_gateway, "complete_structured", fake_complete)
    await memory_llm.revise_memory_facts(
        Settings(mock_llm_enabled=False), "User: For Recall I decided to use Neon"
    )
    system = captured["messages"][0]["content"]
    assert "Recall uses Neon (chosen over Supabase)" in system
    assert "op=mute" in system
    assert "that's wrong, I'm at Stripe now" in system
