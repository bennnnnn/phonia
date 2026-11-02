"""A turn's documents are queued for indexing once its user message commits."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.attachments import jobs


def _patches(enqueue: AsyncMock, *, capped: bool = False):
    return (
        patch.object(jobs.jobs, "enqueue", enqueue),
        patch.object(jobs, "get_redis_client", return_value=AsyncMock()),
        patch.object(jobs.quota_service, "global_spend_exceeded", AsyncMock(return_value=capped)),
    )


async def test_library_reuse_in_another_chat_gets_an_independent_index_job() -> None:
    enqueue = AsyncMock()
    attachment_id = str(uuid4())
    first_chat, second_chat = uuid4(), uuid4()
    first, second, third = _patches(enqueue)
    with first, second, third:
        for chat_id in (first_chat, second_chat):
            await jobs.enqueue_index_jobs(
                Settings(), user_id=uuid4(), chat_id=chat_id, attachment_ids=[attachment_id]
            )

    assert [call.args[1] for call in enqueue.call_args_list] == [jobs.INDEX_JOB] * 2
    assert [call.kwargs["dedupe_key"] for call in enqueue.call_args_list] == [
        f"attachment_index:{attachment_id}:{first_chat}",
        f"attachment_index:{attachment_id}:{second_chat}",
    ]


@pytest.mark.parametrize(
    "settings, capped, attachment_ids",
    [
        (Settings(attachment_rag_enabled=False), False, ["a"]),
        (Settings(), True, ["a"]),  # global spend cap: background LLM work pauses
        (Settings(), False, []),
    ],
)
async def test_enqueue_index_jobs_skips(
    settings: Settings, capped: bool, attachment_ids: list[str]
) -> None:
    enqueue = AsyncMock()
    first, second, third = _patches(enqueue, capped=capped)
    with first, second, third:
        await jobs.enqueue_index_jobs(
            settings, user_id=uuid4(), chat_id=uuid4(), attachment_ids=attachment_ids
        )

    enqueue.assert_not_awaited()


async def test_enqueue_index_jobs_never_raises_into_the_turn() -> None:
    enqueue = AsyncMock(side_effect=ConnectionError("redis down"))
    first, second, third = _patches(enqueue)
    with first, second, third:
        await jobs.enqueue_index_jobs(
            Settings(), user_id=uuid4(), chat_id=uuid4(), attachment_ids=["a", "b"]
        )

    assert enqueue.await_count == 2
