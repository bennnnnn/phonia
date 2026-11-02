"""message_index job: parse payload and call chat-history RAG."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.background.message_indexing import index_message_job
from app.core.config import Settings
from app.modules.memory.switch import memory_switch_on
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
async def test_index_message_job_calls_index_turn():
    settings = Settings(chat_history_rag_enabled=True)
    user_id = uuid4()
    chat_id = uuid4()
    assistant_id = uuid4()
    with patch(
        "app.modules.conversation.history_rag.index_turn_messages",
        AsyncMock(return_value=2),
    ) as index:
        await index_message_job(
            settings,
            {
                "user_id": str(user_id),
                "chat_id": str(chat_id),
                "assistant_message_id": str(assistant_id),
            },
        )
    index.assert_awaited_once()
    kwargs = index.await_args.kwargs
    assert kwargs["user_id"] == user_id
    assert kwargs["chat_id"] == chat_id
    assert kwargs["assistant_message_id"] == assistant_id
    # Memory off indexes nothing: the job hands conversation memory's own switch.
    assert kwargs["memory_on"] is memory_switch_on


@pytest.mark.asyncio
async def test_enqueue_post_turn_jobs_includes_message_index():
    from app.modules.chat.post_turn import enqueue_post_turn_jobs
    from app.modules.chat.turn_prep.context import StreamContext

    redis = redis_mock()
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[],
        run_title=False,
        user_message_content="what did we decide last month",
        reserved_tokens=10,
        max_output_tokens=100,
        assistant_message_id=uuid4(),
        skip_memory_jobs=False,
        prior_count=4,
    )
    with (
        patch("app.core.jobs.enqueue", AsyncMock()) as enqueue,
        patch("app.services.quota.global_spend_exceeded", AsyncMock(return_value=False)),
    ):
        await enqueue_post_turn_jobs(
            redis,
            Settings(chat_history_rag_enabled=True, history_compression_enabled=False),
            ctx,
            "We picked the blue couch.",
        )
    job_types = [call.args[1] for call in enqueue.call_args_list]
    assert "message_index" in job_types


@pytest.mark.asyncio
async def test_index_message_job_skips_when_disabled_or_bad_payload():
    with patch(
        "app.modules.conversation.history_rag.index_turn_messages",
        AsyncMock(),
    ) as index:
        await index_message_job(Settings(chat_history_rag_enabled=False), {"user_id": "x"})
        await index_message_job(Settings(chat_history_rag_enabled=True), {"user_id": "not-a-uuid"})
    index.assert_not_awaited()
