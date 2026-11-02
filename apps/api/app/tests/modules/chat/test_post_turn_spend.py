from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.exceptions import RedisUnavailableError
from app.modules.chat.post_turn import enqueue_post_turn_jobs
from app.modules.chat.turn_prep.context import StreamContext
from app.tests.modules.chat.chat_test_support import turn_deps


def _ctx(*, prior_count: int, run_title: bool = True) -> StreamContext:
    user = MagicMock()
    user.memory_enabled = True
    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[],
        run_title=run_title,
        user_message_content="hello",
        reserved_tokens=10,
        max_output_tokens=100,
        assistant_message_id=uuid4(),
        skip_memory_jobs=False,
        prior_count=prior_count,
        user=user,
    )


@pytest.mark.asyncio
async def test_default_memory_interval_runs_turn_two():
    ctx = _ctx(prior_count=2)  # turn_number = 2
    with patch("app.core.jobs.enqueue", AsyncMock()) as enqueue:
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(history_compression_enabled=False, chat_history_rag_enabled=False),
            ctx,
            "ok",
        )
    job_types = [c.args[1] for c in enqueue.call_args_list]
    assert "memory" in job_types


@pytest.mark.asyncio
async def test_default_memory_interval_runs_turn_three():
    ctx = _ctx(prior_count=4)  # turn_number = 3
    with patch("app.core.jobs.enqueue", AsyncMock()) as enqueue:
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(history_compression_enabled=False, chat_history_rag_enabled=False),
            ctx,
            "ok",
        )
    job_types = [c.args[1] for c in enqueue.call_args_list]
    assert "memory" in job_types
    memory_call = next(c for c in enqueue.call_args_list if c.args[1] == "memory")
    assert memory_call.kwargs["dedupe_key"] == f"memory:{ctx.assistant_message_id}"


@pytest.mark.asyncio
async def test_memory_job_strips_attachments_and_drops_assistant():
    ctx = _ctx(prior_count=0)  # turn 1 always extracts
    ctx.user_message_content = (
        "I live in Seattle\n"
        "[BEGIN UNTRUSTED CONTENT — user attachments]\n"
        "Prescription: lisinopril 10mg\n"
        "[END UNTRUSTED CONTENT — user attachments]\n"
        "[Image: rx.jpg]"
    )
    with patch("app.core.jobs.enqueue", AsyncMock()) as enqueue:
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(history_compression_enabled=False, chat_history_rag_enabled=False),
            ctx,
            "You live in Seattle and take lisinopril.",
        )
    memory_call = next(c for c in enqueue.call_args_list if c.args[1] == "memory")
    transcript = memory_call.args[2]["transcript"]
    assert transcript == "User: I live in Seattle"
    assert "Assistant" not in transcript
    assert "lisinopril" not in transcript
    assert "[Image:" not in transcript


@pytest.mark.asyncio
@pytest.mark.parametrize("memory_on", [True, False])
async def test_memory_off_indexes_no_turn_for_past_chat_recall(memory_on):
    """M14: with the memory switch off, no message_index job is queued."""
    ctx = _ctx(prior_count=2)
    ctx.user.memory_enabled = memory_on
    with (
        patch("app.core.jobs.enqueue", AsyncMock()) as enqueue,
        patch(
            "app.modules.chat.post_turn.quota_service.global_spend_exceeded",
            AsyncMock(return_value=False),
        ),
    ):
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(history_compression_enabled=False, chat_history_rag_enabled=True),
            ctx,
            "We picked the blue couch.",
        )
    job_types = [c.args[1] for c in enqueue.call_args_list]
    assert ("message_index" in job_types) is memory_on
    assert ("memory" in job_types) is memory_on


@pytest.mark.asyncio
async def test_throttled_interval_still_extracts_a_correction():
    """M9: "that's wrong, I'm at Stripe now" updates memory on this turn."""
    ctx = _ctx(prior_count=2)  # turn_number = 2
    ctx.user_message_content = "that's wrong, I'm at Stripe now"
    with patch("app.core.jobs.enqueue", AsyncMock()) as enqueue:
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(
                history_compression_enabled=False,
                chat_history_rag_enabled=False,
                memory_extract_every_n_turns=3,
            ),
            ctx,
            "Got it.",
        )
    assert "memory" in [c.args[1] for c in enqueue.call_args_list]


@pytest.mark.asyncio
async def test_throttled_interval_still_extracts_remember_this():
    ctx = _ctx(prior_count=2)  # turn_number = 2
    ctx.user_message_content = "Remember this: I am allergic to peanuts."
    with patch("app.core.jobs.enqueue", AsyncMock()) as enqueue:
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(
                history_compression_enabled=False,
                chat_history_rag_enabled=False,
                memory_extract_every_n_turns=3,
            ),
            ctx,
            "ok",
        )
    job_types = [c.args[1] for c in enqueue.call_args_list]
    assert "memory" in job_types


@pytest.mark.asyncio
async def test_memory_job_skips_when_user_text_is_only_an_attachment():
    ctx = _ctx(prior_count=0)
    ctx.user_message_content = "[Image: cat.jpg]"
    with patch("app.core.jobs.enqueue", AsyncMock()) as enqueue:
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(history_compression_enabled=False, chat_history_rag_enabled=False),
            ctx,
            "Cute cat.",
        )
    job_types = [c.args[1] for c in enqueue.call_args_list]
    assert "memory" not in job_types
    assert "topic" in job_types


# The cap reached, or Redis down at the spend read: nothing that spends is queued.
_CAPPED_OR_DOWN = [
    pytest.param(AsyncMock(return_value=True), id="capped"),
    pytest.param(AsyncMock(side_effect=RedisUnavailableError()), id="redis-down"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("spend_read", _CAPPED_OR_DOWN)
async def test_spend_cap_keeps_topic_drops_llm_jobs(spend_read):
    ctx = _ctx(prior_count=0, run_title=True)  # turn 1 would enqueue memory
    with (
        patch("app.core.jobs.enqueue", AsyncMock()) as enqueue,
        patch("app.services.quota.global_spend_exceeded", spend_read),
    ):
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(
                history_compression_enabled=True,
                chat_history_rag_enabled=True,
            ),
            ctx,
            "ok",
        )
    assert [c.args[1] for c in enqueue.call_args_list] == ["topic"]


@pytest.mark.asyncio
async def test_a_turn_enqueues_no_proactive_suggestions():
    """Follow-ups come from the reply itself (related prompts), not from a job
    that reads other chats: their chips were off the topic the user was on."""
    ctx = _ctx(prior_count=10, run_title=False)
    with patch("app.core.jobs.enqueue", AsyncMock()) as enqueue:
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(history_compression_enabled=False, chat_history_rag_enabled=False),
            ctx,
            "ok",
        )
    assert "suggestions" not in [c.args[1] for c in enqueue.call_args_list]


@pytest.mark.asyncio
async def test_day_planning_snapshot_skips_learning_extract():
    """Home 'anything left tonight' lists quiz progress — that is not a write."""
    ctx = _ctx(prior_count=0, run_title=True)
    ctx.user_message_content = "What's still open for me to finish tonight?"
    assistant = (
        "Here's what's still open for tonight:\n\n"
        "**Reminders**\n- Ggg at 7:00 PM (due today, repeats weekdays)\n\n"
        "**Learning**\n- English vocabulary quiz: 0/10 done"
    )
    with patch("app.core.jobs.enqueue", AsyncMock()) as enqueue:
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(history_compression_enabled=False, chat_history_rag_enabled=False),
            ctx,
            assistant,
        )
    job_types = [c.args[1] for c in enqueue.call_args_list]
    assert "projects" not in job_types
    assert "todos" not in job_types
    assert "topic" in job_types
    assert "memory" in job_types


@pytest.mark.asyncio
@pytest.mark.parametrize("spend_read", _CAPPED_OR_DOWN)
async def test_tool_loop_path_skips_when_spend_capped(spend_read):
    """An admitted turn answers without tools: an outage here does not fail it."""
    from app.modules.chat.stream_paths import run_tool_loop_path

    ctx = MagicMock()
    ctx.instant_reply = None
    ctx.lightweight_turn = False
    ctx.verified_subject = None
    ctx.user_message_content = "What's the latest news on SpaceX?"
    ctx.search_sources = []
    ctx.user = None
    ctx.user_id = uuid4()
    ctx.chat_id = uuid4()
    ctx.prompt_messages = []
    deps = turn_deps(quota={"global_spend_exceeded": spend_read})
    with patch("app.modules.chat.tool_loop.run_tool_rounds", AsyncMock()) as run:
        await run_tool_loop_path(
            deps,
            AsyncMock(),
            Settings(mcp_tool_loop_enabled=True),
            ctx,
            usage={},
            on_status=None,
            should_cancel=None,
        )
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_loop_path_skips_when_heuristic_math_already_verified():
    """Regression: PR #690 enabled the owned tool loop by default, which added
    up to 3 non-streaming OpenRouter round-trips (~24s) before the first token
    even when turn_prep's heuristic math already produced a verified fence.
    The loop's sympy/graph adapter is redundant in that case — skip it so math
    turns stay on the fast 1-call path. Ordinary non-tool turns skip the loop
    too (see turn_needs_tool_loop)."""
    from app.modules.chat.stream_paths import run_tool_loop_path

    ctx = MagicMock()
    ctx.instant_reply = None
    ctx.lightweight_turn = False
    ctx.verified_subject = MagicMock()  # heuristic already produced a verified block
    ctx.user_id = uuid4()
    ctx.chat_id = uuid4()
    ctx.prompt_messages = []
    deps = turn_deps(quota={"global_spend_exceeded": AsyncMock(return_value=False)})
    with patch("app.modules.chat.tool_loop.run_tool_rounds", AsyncMock()) as run:
        await run_tool_loop_path(
            deps,
            AsyncMock(),
            Settings(mcp_tool_loop_enabled=True),
            ctx,
            usage={},
            on_status=None,
            should_cancel=None,
        )
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_loop_path_skips_ordinary_explain_turn():
    from app.modules.chat.stream_paths import run_tool_loop_path

    ctx = MagicMock()
    ctx.instant_reply = None
    ctx.lightweight_turn = False
    ctx.verified_subject = None
    ctx.user_message_content = "Explain photosynthesis in two sentences."
    ctx.search_sources = []
    ctx.user = None
    ctx.user_id = uuid4()
    ctx.chat_id = uuid4()
    ctx.prompt_messages = []
    deps = turn_deps(quota={"global_spend_exceeded": AsyncMock(return_value=False)})
    with patch("app.modules.chat.tool_loop.run_tool_rounds", AsyncMock()) as run:
        await run_tool_loop_path(
            deps,
            AsyncMock(),
            Settings(mcp_tool_loop_enabled=True),
            ctx,
            usage={},
            on_status=None,
            should_cancel=None,
        )
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_loop_path_does_not_dump_leftover_as_instant_reply():
    from app.modules.chat.stream_paths import run_tool_loop_path

    ctx = MagicMock()
    ctx.instant_reply = None
    ctx.lightweight_turn = False
    ctx.verified_subject = None
    ctx.user_message_content = "What's the latest news on SpaceX?"
    ctx.search_sources = []
    ctx.user = None
    ctx.user_id = uuid4()
    ctx.chat_id = uuid4()
    ctx.prompt_messages = [{"role": "user", "content": "What's the latest news on SpaceX?"}]
    tool_messages = [
        *ctx.prompt_messages,
        {"role": "assistant", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "hits"},
    ]
    deps = turn_deps(quota={"global_spend_exceeded": AsyncMock(return_value=False)})
    with (
        patch(
            "app.modules.chat.tool_loop.run_tool_rounds",
            AsyncMock(return_value=(tool_messages, None, None, [])),
        ) as run,
    ):
        await run_tool_loop_path(
            deps,
            AsyncMock(),
            Settings(mcp_tool_loop_enabled=True),
            ctx,
            usage={},
            on_status=None,
            should_cancel=None,
        )
    run.assert_awaited_once()
    assert ctx.instant_reply is None
    assert ctx.prompt_messages == tool_messages
