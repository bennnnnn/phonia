"""Which background jobs the global spend cap stops (``handlers._unless_spend_capped``)."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.background import handlers
from app.core.config import Settings
from app.core.jobs import JobSkipped, queue
from app.exceptions import RedisUnavailableError

_USER, _CHAT, _MESSAGE = str(uuid4()), str(uuid4()), str(uuid4())
_PAYLOAD = {
    "user_id": _USER,
    "chat_id": _CHAT,
    "assistant_message_id": _MESSAGE,
    "transcript": "user: hi",
}

# Job type -> the work it would do. Each makes a model or embedding call.
_CAPPED = {
    "memory": "app.background.handlers.memory_extraction.extract_and_store_memories",
    "memory_history_scan": "app.background.handlers.memory_history_scan.scan_recent_chats",
    "memory_consolidate": (
        "app.background.handlers.memory_consolidation.consolidate_user_memory_sections"
    ),
    "compress": "app.background.handlers.compaction.compress_chat_history",
    "topic": "app.background.handlers.chat_titles.generate_chat_title",
    "attachment_index": "app.background.handlers.attachment_indexing.index_attachment_job",
    "message_index": "app.background.handlers.message_indexing.index_message_job",
}


@pytest.fixture(autouse=True)
def _registered() -> None:
    handlers.register_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("job_type, work", sorted(_CAPPED.items()))
@pytest.mark.parametrize(
    "spend_read",
    [
        pytest.param(AsyncMock(return_value=True), id="capped"),
        # Redis down at the spend read: skipped as at the cap, never run blind.
        pytest.param(AsyncMock(side_effect=RedisUnavailableError()), id="redis-down"),
    ],
)
async def test_a_model_job_does_nothing_once_the_spend_cap_is_reached(
    job_type: str, work: str, spend_read: AsyncMock
) -> None:
    settings = Settings(daily_global_spend_usd=1.0)
    with (
        patch(work, AsyncMock()) as body,
        patch.object(handlers.quota_service, "global_spend_exceeded", spend_read),
        # Not done: the worker releases the job's key so a later request still runs.
        pytest.raises(JobSkipped),
    ):
        await queue._HANDLERS[job_type](settings, dict(_PAYLOAD))
    body.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("job_type, work", sorted(_CAPPED.items()))
async def test_a_model_job_runs_below_the_spend_cap(job_type: str, work: str) -> None:
    settings = Settings(daily_global_spend_usd=1.0)
    # A title job reports whether it applied one; the rest return nothing.
    result = True if job_type == "topic" else None
    with (
        patch(work, AsyncMock(return_value=result)) as body,
        patch.object(
            handlers.quota_service, "global_spend_exceeded", AsyncMock(return_value=False)
        ),
    ):
        await queue._HANDLERS[job_type](settings, dict(_PAYLOAD))
    body.assert_awaited_once()
