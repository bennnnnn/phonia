import asyncio
from contextlib import ExitStack, suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.gateways.stream_signals import StreamAttempt
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.conversation import chats_repository, messages_repository
from app.tests.modules.chat.chat_test_support import (
    FakeSessionCM as _FakeSessionCM,
)
from app.tests.modules.chat.chat_test_support import (
    grant_quota,
    offline_deps,
    stub_recent,
    turn_deps,
)
from app.tests.modules.chat.chat_test_support import (
    offline_session_patches as _offline_session_patches,
)

pytest_plugins = ("app.tests.modules.chat.chat_test_support",)


@pytest.mark.asyncio
async def test_stream_does_not_duplicate_user_message(fake_redis, stream_offline_io):
    from app.modules import chat as chat_module

    tokens = ["Hello", " there"]

    async def fake_stream(**kwargs):
        for t in tokens:
            yield t

    user_id = AsyncMock()
    chat_id = AsyncMock()

    mock_build = AsyncMock(
        return_value=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "question"},
        ]
    )

    fake_user = MagicMock()
    fake_user.id = user_id
    fake_user.default_model = "free-chat"
    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=1)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch("app.modules.chat.turn_prep.context.build_prompt_messages", mock_build),
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()),
    ):
        collected = []
        async for tok in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            user_id=user_id,
            chat_id=chat_id,
            content="question",
        ):
            collected.append(tok)

    assert collected == tokens
    assert mock_build.await_count == 1


@pytest.mark.asyncio
async def test_memory_extraction_runs_on_later_turn(fake_redis, stream_offline_io):
    from app.modules import chat as chat_module

    async def fake_stream(**kwargs):
        yield "answer"

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=stub_recent(3))),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=3)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
        ),
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()) as enqueue_job,
    ):
        outcome = TurnOutcome()
        async for _ in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(
                max_output_tokens=100,
                memory_extract_every_n_turns=1,
                mcp_tool_loop_enabled=False,
            ),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="second turn info",
            outcome=outcome,
        ):
            pass
        finalize = outcome.finalize_task
        if finalize is not None:
            await finalize

    # Explicit every-turn setting still enqueues memory on later turns.
    job_types = [call.args[1] for call in enqueue_job.call_args_list]
    assert job_types.count("memory") == 1
    assert "topic" not in job_types
    assert "todos" not in job_types
    assert "projects" not in job_types


@pytest.mark.asyncio
async def test_memory_extraction_skipped_when_memory_disabled(fake_redis, stream_offline_io):
    """When the user has memory_enabled=False, the memory job must not be
    enqueued at all — previously it was enqueued every N turns and the
    extraction worker no-op'd internally, wasting a stream-job cycle."""
    from app.modules import chat as chat_module

    async def fake_stream(**kwargs):
        yield "answer"

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_user.memory_enabled = False

    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=3)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
        ),
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()) as enqueue_job,
    ):
        outcome = TurnOutcome()
        async for _ in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="second turn info",
            outcome=outcome,
        ):
            pass
        finalize = outcome.finalize_task
        if finalize is not None:
            await finalize

    job_types = [call.args[1] for call in enqueue_job.call_args_list]
    assert "memory" not in job_types


@pytest.mark.asyncio
async def test_memory_extraction_throttled_when_every_n_gt_1(fake_redis, stream_offline_io):
    """Ops can still raise memory_extract_every_n_turns to skip intermediate turns."""
    from app.modules import chat as chat_module

    async def fake_stream(**kwargs):
        yield "answer"

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=stub_recent(2))),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=2)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
        ),
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()) as enqueue_job,
    ):
        outcome = TurnOutcome()
        async for _ in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(
                max_output_tokens=100, memory_extract_every_n_turns=3, mcp_tool_loop_enabled=False
            ),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="turn two chit chat",
            outcome=outcome,
        ):
            pass
        finalize = outcome.finalize_task
        if finalize is not None:
            await finalize

    job_types = [call.args[1] for call in enqueue_job.call_args_list]
    assert "memory" not in job_types


@pytest.mark.asyncio
async def test_a_reminder_reply_enqueues_no_background_write(fake_redis, stream_offline_io):
    """A reminder change in chat waits for a tap on its card: no job writes it behind
    the user's back (the background repair job is gone), and with nothing written the
    phone is not told to reload its list (code-health audit NET-14)."""
    from app.modules import chat as chat_module

    async def fake_stream(**kwargs):
        yield "I'll set a reminder for Call mom."

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=3)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
        ),
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()) as enqueue_job,
    ):
        outcome = TurnOutcome()
        async for _ in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="Sounds good for tomorrow",
            outcome=outcome,
        ):
            pass
        finalize = outcome.finalize_task
        if finalize is not None:
            await finalize

    job_types = [call.args[1] for call in enqueue_job.call_args_list]
    assert "todos" not in job_types
    assert not outcome.todos_changed


@pytest.mark.asyncio
async def test_stream_sets_final_content_on_cancel(fake_redis, stream_offline_io):
    """On a user-initiated stop, the server persists text the client may not have
    rendered yet; `outcome.final_content` carries the authoritative persisted
    text so the client can reconcile (stop/regenerate desync fix)."""
    from app.modules import chat as chat_module

    async def fake_stream(**kwargs):
        for w in ["one ", "two ", "three "]:
            yield w

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    cancel_after = {"n": 0}

    def should_cancel():
        cancel_after["n"] += 1
        return cancel_after["n"] > 1  # let the first token through, then cancel

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=3)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
        ),
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()),
    ):
        outcome = TurnOutcome()
        yielded: list[str] = []
        async for tok in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="question",
            should_cancel=should_cancel,
            outcome=outcome,
        ):
            yielded.append(tok)
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    # Only the first token was yielded before cancel broke the loop.
    assert yielded == ["one "]
    # The authoritative persisted text is exposed for client reconciliation.
    assert outcome.final_content == "one"


@pytest.mark.asyncio
async def test_cancelled_stream_skips_model_health_sample(fake_redis, stream_offline_io):
    """User stop must not record a failed health sample (poisons fallback routing)."""
    from uuid import uuid4

    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**_kwargs):
        yield "one "
        yield "two "

    record = AsyncMock()
    cancel_after = {"n": 0}

    def should_cancel() -> bool:
        cancel_after["n"] += 1
        return cancel_after["n"] > 1

    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )

    outcome = TurnOutcome()
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(patch("app.services.model_health.record_samples", record))
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", AsyncMock())
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        async for _ in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=should_cancel,
            outcome=outcome,
        ):
            pass
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    record.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_and_finalize_asks_the_model_beside_the_user_row_commit(
    fake_redis, stream_offline_io
):
    """The model is asked while the user's row commits (no time-to-first-token
    cost), but its first token is sent only once the row is saved."""
    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    persist_hold = asyncio.Event()
    llm_started = asyncio.Event()
    finalize = AsyncMock()

    async def persist() -> None:
        await persist_hold.wait()

    async def fake_stream(**_kwargs: object):
        llm_started.set()
        yield "ok"

    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
        user_message_persist=asyncio.create_task(persist()),
    )
    outcome = TurnOutcome()
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        agen = stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=None,
            outcome=outcome,
        )
        first = asyncio.ensure_future(agen.__anext__())
        await asyncio.wait_for(llm_started.wait(), 5)
        for _ in range(5):
            await asyncio.sleep(0)
        assert not first.done()
        assert ctx.user_message_persist is not None
        assert ctx.user_message_persist.done() is False
        finalize.assert_not_awaited()
        persist_hold.set()
        assert await first == "ok"
        async for _ in agen:
            pass
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    finalize.assert_awaited()
    assert ctx.user_message_persist is None


def _turn_ctx(**fields: Any):
    from app.modules.chat.turn_prep import StreamContext

    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=0,
        max_output_tokens=50,
        skip_memory_jobs=True,
        **fields,
    )


def _stream_of(*tokens: str):
    async def fake_stream(**kwargs: object):
        # As the gateway does: the alias that answers is one attempt, not failed.
        attempts = kwargs.get("attempts")
        if isinstance(attempts, list):
            attempt = StreamAttempt(str(kwargs["model_alias"]))
            attempt.delta()
            attempt.end(failed=False)
            attempts.append(attempt)
        for token in tokens:
            yield token
            await asyncio.sleep(0)

    return fake_stream


@pytest.mark.asyncio
async def test_failed_user_row_save_sends_no_reply(fake_redis, stream_offline_io):
    """Regression: a failed user-message save surfaced only after every token had
    streamed, and the turn was never charged (a full answer for free). Now the
    first token is held until the row commits, so a failed save sends nothing
    and the turn fails as unsaved."""
    from app.modules.chat.stream_pipeline import stream_and_finalize

    async def failing_persist() -> list[str]:
        raise RuntimeError("database unavailable")

    finalize = AsyncMock()
    health = AsyncMock()
    ctx = _turn_ctx(user_message_persist=asyncio.create_task(failing_persist()))
    outcome = TurnOutcome()
    tokens: list[str] = []
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "app.gateways.litellm_gateway.stream_chat_completion",
                _stream_of("Full ", "answer ", "streamed."),
            )
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        stack.enter_context(patch("app.services.model_health.record_samples", health))
        with pytest.raises(RuntimeError, match="database unavailable"):
            async for token in stream_and_finalize(
                offline_deps(),
                fake_redis,
                Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
                ctx,
                should_cancel=None,
                outcome=outcome,
            ):
                tokens.append(token)

    assert tokens == []
    finalize.assert_not_awaited()
    assert outcome.finalize_db_task is None
    assert outcome.user_message_saved is False
    # The model answered; the failure was the save's.
    assert [sample.success for sample in health.await_args.args[1]] == [True]


@pytest.mark.asyncio
async def test_terminal_image_turn_counts_its_tool_rounds_toward_global_spend():
    """The tool rounds before a generated picture were never recorded: the turn's
    quota is refunded and nothing else counted their provider cost."""
    from app.modules.chat.stream_pipeline import finalize_terminal_image_turn

    spend = AsyncMock()
    estimate = MagicMock(return_value=0.0042)
    ctx = _turn_ctx()
    ctx.terminal_image_message_id = str(uuid4())
    ctx.terminal_image_content = "[Image: cat.png]"
    outcome = TurnOutcome()
    deps = offline_deps(chats={"touch_by_id": AsyncMock()})
    with (
        patch("app.modules.chat.stream_pipeline.enqueue_post_turn_jobs", AsyncMock()),
        patch("app.modules.chat.stream_pipeline.model_catalog.estimate_cost_usd", estimate),
        patch("app.modules.chat.stream_pipeline.quota_service.record_global_spend", spend),
    ):
        await finalize_terminal_image_turn(
            deps, AsyncMock(), Settings(), ctx, outcome, {"input": 1200, "output": 80}
        )
        assert outcome.finalize_task is not None
        await outcome.finalize_task

    estimate.assert_called_once_with("free-chat", input_tokens=1200, output_tokens=80)
    spend.assert_awaited_once()
    assert spend.await_args.args[1] == 0.0042


@pytest.mark.asyncio
async def test_stop_after_the_last_token_still_saves_the_reply(fake_redis, stream_offline_io):
    """Regression: a Stop that landed during the finalize passes (answer photo up
    to 6s, SymPy, the reminder write) cancelled the save: nothing was stored or
    charged, and the phone's streamed bubble vanished on the next refetch."""
    from app.modules.chat.stream_pipeline import stream_and_finalize

    entered = asyncio.Event()

    async def slow_enrich(*_args, assistant_text, **_kwargs):
        entered.set()
        await asyncio.sleep(0.2)
        return assistant_text

    finalize = AsyncMock()
    ctx = _turn_ctx()
    outcome = TurnOutcome()
    tokens: list[str] = []

    async def consume() -> None:
        async for token in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=None,
            outcome=outcome,
        ):
            tokens.append(token)

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "app.gateways.litellm_gateway.stream_chat_completion", _stream_of("full ", "answer")
            )
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.enrich_final_content", slow_enrich)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        stack.enter_context(patch("app.services.model_health.record_samples", AsyncMock()))
        task = asyncio.create_task(consume())
        await asyncio.wait_for(entered.wait(), 5)
        # The WS receive loop does exactly this on {"type": "cancel"}; twice, as
        # the provider-socket close after a Stop cancels the task again.
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert outcome.finalize_db_task is not None
        await outcome.finalize_db_task

    assert tokens == ["full ", "answer"]
    finalize.assert_awaited_once()
    assert finalize.await_args.kwargs["assistant_text"] == "full answer"
    assert outcome.message_id is not None
    # The reply was complete; the Stop only came during its finishing passes.
    assert outcome.completion is None


@pytest.mark.asyncio
async def test_a_server_stop_saves_the_partial_reply_as_interrupted(
    fake_redis, stream_offline_io, monkeypatch
):
    """At shutdown the turn is stopped through the user's Stop path; the saved
    partial reply says it was interrupted, not stopped by the user."""
    from app.core import shutdown
    from app.modules.chat.stream_pipeline import stream_and_finalize

    monkeypatch.setattr(shutdown, "_stopping", True)
    stopped = asyncio.Event()
    finalize = AsyncMock()
    outcome = TurnOutcome()
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "app.gateways.litellm_gateway.stream_chat_completion",
                _stream_of("one ", "two ", "three"),
            )
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        tokens: list[str] = []
        async for token in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            _turn_ctx(),
            should_cancel=stopped.is_set,
            outcome=outcome,
        ):
            tokens.append(token)
            stopped.set()  # the shutdown's Stop lands after the first token
        assert outcome.finalize_db_task is not None
        await outcome.finalize_db_task

    assert tokens == ["one "]
    finalize.assert_awaited_once()
    assert outcome.completion == "interrupted"


@pytest.mark.asyncio
async def test_hard_cancel_before_tokens_skips_model_health_sample(fake_redis, stream_offline_io):
    """Cancel while waiting on the provider must not record success=False."""
    import asyncio
    from uuid import uuid4

    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**_kwargs):
        raise asyncio.CancelledError()
        yield  # pragma: no cover

    record = AsyncMock()
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )

    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(patch("app.services.model_health.record_samples", record))
        with pytest.raises(asyncio.CancelledError):
            async for _ in stream_and_finalize(
                offline_deps(),
                fake_redis,
                Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
                ctx,
                should_cancel=None,
            ):
                pass

    record.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_chat_response_rejects_empty_content(fake_redis, stream_offline_io):
    from app.exceptions import ChatNotFoundError
    from app.modules.chat.stream_entry import stream_chat_response

    with pytest.raises(ChatNotFoundError, match="empty"):
        async for _ in stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(),
            user_id=uuid4(),
            chat_id=uuid4(),
            content="   ",
        ):
            pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    ["draw ethanol", "A lens has focal length 15 cm. Where's the image?"],
)
async def test_try_image_gen_leaves_a_stem_turn_to_its_subject(content: str):
    """A chemistry structure or an optics question is not a picture request, on any
    plan: generation would spend an image and skip the solver and its drawing."""
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    generate = AsyncMock()
    deps = turn_deps(
        plan={"can_use": MagicMock(return_value=True)},
        image_generation={"generate_for_chat": generate},
    )
    handled = await try_image_gen_for_turn(
        deps,
        Settings(),
        user=user,
        chat_id=uuid4(),
        content=content,
        outcome=None,
        create_user_message=True,
    )

    assert handled is False
    generate.assert_not_awaited()


def _image_gen_deps(**fields):
    """A Pro user's turn: image generation is on the plan."""
    return turn_deps(plan={"can_use": MagicMock(return_value=True)}, **fields)


@pytest.mark.asyncio
async def test_try_image_gen_skips_recent_lookup_when_text_cannot_be_revision():
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    list_recent = AsyncMock(return_value=[])
    long_text = "x" * 121

    handled = await try_image_gen_for_turn(
        _image_gen_deps(messages={"list_recent": list_recent}),
        Settings(),
        user=user,
        chat_id=uuid4(),
        content=long_text,
        outcome=None,
        create_user_message=True,
    )

    assert handled is False
    list_recent.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("greeting", ["hi", "hello", "thanks", "ok"])
async def test_try_image_gen_skips_recent_lookup_for_greeting(greeting: str):
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    list_recent = AsyncMock(return_value=[])

    handled = await try_image_gen_for_turn(
        _image_gen_deps(messages={"list_recent": list_recent}),
        Settings(),
        user=user,
        chat_id=uuid4(),
        content=greeting,
        outcome=None,
        create_user_message=True,
    )

    assert handled is False
    list_recent.assert_not_awaited()


@pytest.mark.asyncio
async def test_try_image_gen_looks_up_recent_when_text_could_be_revision():
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    list_recent = AsyncMock(return_value=[])

    handled = await try_image_gen_for_turn(
        _image_gen_deps(messages={"list_recent": list_recent}),
        Settings(),
        user=user,
        chat_id=uuid4(),
        content="make it blue",
        outcome=None,
        create_user_message=True,
    )

    assert handled is False
    list_recent.assert_awaited_once()


@pytest.mark.asyncio
async def test_try_image_gen_uses_preloaded_recent_without_lookup():
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    list_recent = AsyncMock(return_value=[])

    handled = await try_image_gen_for_turn(
        _image_gen_deps(messages={"list_recent": list_recent}),
        Settings(),
        user=user,
        chat_id=uuid4(),
        content="make it blue",
        outcome=None,
        create_user_message=True,
        recent_messages=[],
    )

    assert handled is False
    list_recent.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["what's 2+2", "help me think", "how are you"])
async def test_try_image_gen_skips_recent_lookup_for_chat_openers(text: str):
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    list_recent = AsyncMock(return_value=[])

    handled = await try_image_gen_for_turn(
        _image_gen_deps(messages={"list_recent": list_recent}),
        Settings(),
        user=user,
        chat_id=uuid4(),
        content=text,
        outcome=None,
        create_user_message=True,
    )

    assert handled is False
    list_recent.assert_not_awaited()


@pytest.mark.asyncio
async def test_try_image_gen_skips_recent_lookup_on_empty_chat():
    """A brand-new chat has no prior image — don't pay Neon list_recent."""
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    list_recent = AsyncMock(return_value=[])

    handled = await try_image_gen_for_turn(
        _image_gen_deps(messages={"list_recent": list_recent}),
        Settings(),
        user=user,
        chat_id=uuid4(),
        content="red",
        outcome=None,
        create_user_message=True,
        skip_revision_lookup=True,
    )

    assert handled is False
    list_recent.assert_not_awaited()


@pytest.mark.asyncio
async def test_try_image_gen_dog_then_image_uses_prior_subject():
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    asst_msg = MagicMock()
    asst_msg.id = uuid4()
    asst_msg.content = "[Image: /attachments/x/file]"
    asst_msg.model = "image-gen-model"
    generate = AsyncMock(return_value=(MagicMock(), asst_msg))
    dog = MagicMock()
    dog.role = "user"
    dog.content = "Dog"

    handled = await try_image_gen_for_turn(
        _image_gen_deps(image_generation={"generate_for_chat": generate}),
        Settings(),
        user=user,
        chat_id=uuid4(),
        content="Image",
        outcome=None,
        create_user_message=True,
        recent_messages=[dog],
    )

    assert handled is True
    assert generate.await_args.kwargs["prompt"] == "Dog"


def _turn_row(role: str, content: str, model: str | None = None) -> MagicMock:
    row = MagicMock()
    row.role = role
    row.content = content
    row.model = model
    return row


_PICTURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_AFTER_PICTURE = (
    ("user", "draw me a dog", None),
    ("assistant", f"[Image: /attachments/{_PICTURE_ID}/file]", "image-gen-model"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content, recent, create_user_message, prompt, references",
    [
        # "that car" is the car named earlier, as the composer reads it.
        (
            "create a picture of that car",
            (("user", "draw a red sports car", None), ("assistant", "Which style?", None)),
            True,
            "red sports car",
            None,
        ),
        # An edit starts from the last picture; regenerating lets generation pick it.
        ("make it blue", _AFTER_PICTURE, True, "dog, blue", [UUID(_PICTURE_ID)]),
        ("make it blue", _AFTER_PICTURE, False, "dog, blue", None),
        # A new request after a picture is a new picture.
        ("draw a fox", _AFTER_PICTURE, True, "fox", None),
    ],
)
async def test_try_image_gen_reads_the_chat_like_the_composer(
    content: str,
    recent: tuple[tuple[str, str, str | None], ...],
    create_user_message: bool,
    prompt: str,
    references: list[UUID] | None,
):
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    asst_msg = MagicMock()
    asst_msg.id = uuid4()
    asst_msg.content = "[Image: /attachments/x/file]"
    asst_msg.model = "image-gen-model"
    generate = AsyncMock(return_value=(MagicMock(), asst_msg))

    handled = await try_image_gen_for_turn(
        _image_gen_deps(image_generation={"generate_for_chat": generate}),
        Settings(),
        user=user,
        chat_id=uuid4(),
        content=content,
        outcome=None,
        create_user_message=create_user_message,
        recent_messages=[_turn_row(*row) for row in recent],
    )

    assert handled is True
    call = generate.await_args
    assert call is not None
    assert call.kwargs["prompt"] == prompt
    assert call.kwargs["reference_attachment_ids"] == references


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "status_code", "raised", "code"),
    [
        ("daily_limit", 429, "TurnRefusedError", "daily_limit"),
        ("content_blocked", 422, "TurnRefusedError", "content_blocked"),
        ("spend_cap", 429, "SpendCapReachedError", "spend_cap"),
    ],
)
async def test_a_refused_picture_says_which_limit_not_the_chat_quota(
    error_code: str, status_code: int, raised: str, code: str
):
    """A picture's own cap or a provider refusal is not "out of messages" (quota_exceeded)."""
    from app import exceptions
    from app.modules.chat.stream_events import error_payload_for_exception
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn
    from app.modules.images.generation import ImageGenerationError

    user = MagicMock()
    user.id = uuid4()
    refusal = ImageGenerationError(
        "No more pictures today.", status_code=status_code, code=error_code
    )
    deps = _image_gen_deps(
        image_generation={"generate_for_chat": AsyncMock(side_effect=refusal)},
    )
    with pytest.raises(getattr(exceptions, raised)) as caught:
        await try_image_gen_for_turn(
            deps,
            Settings(),
            user=user,
            chat_id=uuid4(),
            content="Generate image: a cat",
            outcome=None,
            create_user_message=True,
        )
    payload = error_payload_for_exception(caught.value)
    assert payload["code"] == code and payload["message"] == "No more pictures today."
    # The phone words each as the picture's own (a picture's spend cap is not every
    # message paused), in its language.
    assert payload["feature"] == "image_generation"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [403, 404])
async def test_image_regen_soft_fail_keeps_prior_assistant(status_code: int):
    """403/404 must not delete the prior assistant (omit-until-success)."""
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn
    from app.modules.images.generation import ImageGenerationError

    user = MagicMock()
    user.id = uuid4()
    old_id = uuid4()
    delete_message = AsyncMock()
    deps = _image_gen_deps(
        messages={"delete_message": delete_message},
        image_generation={
            "generate_for_chat": AsyncMock(
                side_effect=ImageGenerationError("Not available", status_code=status_code)
            )
        },
    )

    handled = await try_image_gen_for_turn(
        deps,
        Settings(),
        user=user,
        chat_id=uuid4(),
        content="Generate image: a cat",
        outcome=None,
        create_user_message=False,
        replace_assistant_id=old_id,
    )

    assert handled is False
    delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_regen_deletes_prior_assistant_only_after_success():
    from app.modules.chat.turn_intercepts import try_image_gen_for_turn

    user = MagicMock()
    user.id = uuid4()
    old_id = uuid4()
    chat_id = uuid4()
    old = MagicMock()
    old.id = old_id
    old.role = "assistant"
    asst_msg = MagicMock()
    asst_msg.id = uuid4()
    asst_msg.content = "[Image: /attachments/x/file]"
    asst_msg.model = "image-gen-model"
    order: list[str] = []

    async def generate_for_chat(*_args, **_kwargs):
        order.append("generate")
        return MagicMock(), asst_msg

    async def delete_message(_session, message):
        order.append(f"delete:{message.id}")

    async def purge_attachments_for_messages(_session, _settings, message_ids):
        order.append(f"purge:{message_ids[0]}")

    get_by_id = AsyncMock(return_value=old)
    deps = _image_gen_deps(
        session_factory=_FakeSessionCM,
        messages={"get_by_id": get_by_id, "delete_message": delete_message},
        attachments={"purge_attachments_for_messages": purge_attachments_for_messages},
        image_generation={"generate_for_chat": generate_for_chat},
    )

    handled = await try_image_gen_for_turn(
        deps,
        Settings(),
        user=user,
        chat_id=chat_id,
        content="Generate image: a cat",
        outcome=TurnOutcome(),
        create_user_message=False,
        replace_assistant_id=old_id,
    )

    assert handled is True
    assert order == ["generate", f"purge:{old_id}", f"delete:{old_id}"]
    get_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_try_image_lookup_returns_false_when_disabled():
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn

    user = MagicMock()
    user.id = uuid4()

    with patch("app.modules.chat.turn_intercepts.extract_image_lookup_query", return_value="ear"):
        handled = await try_image_lookup_for_turn(
            turn_deps(),
            Settings(image_search_enabled=False),
            user=user,
            chat_id=uuid4(),
            content="show me an ear",
            outcome=None,
            create_user_message=True,
        )

    assert handled is False


@pytest.mark.asyncio
async def test_try_image_lookup_returns_false_when_no_query_match():
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn

    user = MagicMock()
    user.id = uuid4()

    with patch("app.modules.chat.turn_intercepts.extract_image_lookup_query", return_value=None):
        handled = await try_image_lookup_for_turn(
            turn_deps(),
            Settings(image_search_enabled=True),
            user=user,
            chat_id=uuid4(),
            content="what's the weather",
            outcome=None,
            create_user_message=True,
        )

    assert handled is False


@pytest.mark.asyncio
async def test_try_image_lookup_succeeds_and_populates_outcome():
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn

    user = MagicMock()
    user.id = uuid4()
    chat_id = uuid4()
    user_msg = MagicMock()
    asst_msg = MagicMock()
    asst_msg.id = uuid4()
    asst_msg.content = "[Image: /attachments/x/file]"
    asst_msg.model = "image-search-model"

    search_and_attach = AsyncMock(return_value=(user_msg, asst_msg))
    outcome = TurnOutcome()

    with patch(
        "app.modules.chat.turn_intercepts.extract_image_lookup_query", return_value="human ear"
    ):
        handled = await try_image_lookup_for_turn(
            turn_deps(image_search={"search_and_attach_for_chat": search_and_attach}),
            Settings(image_search_enabled=True),
            user=user,
            chat_id=chat_id,
            content="show me an ear",
            outcome=outcome,
            create_user_message=True,
        )

    assert handled is True
    assert outcome.message_id == str(asst_msg.id)
    assert outcome.final_content == asst_msg.content
    assert outcome.resolved_model == "image-search-model"
    search_and_attach.assert_awaited_once()
    _args, kwargs = search_and_attach.call_args
    assert kwargs["query"] == "human ear"
    assert kwargs["chat_id"] == chat_id
    assert kwargs["create_user_message"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [404, 429, 502, 503])
async def test_try_image_lookup_soft_fails_fall_through_to_chat(status_code: int):
    """No-results, provider-down and at-the-cap lookups fall through to a normal answer.

    A 429 is the photo cap (or the spend cap): the turn is answered in words instead of
    failing as if the chat quota were spent."""
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn
    from app.modules.images.search import ImageSearchError

    user = MagicMock()
    user.id = uuid4()

    search_and_attach = AsyncMock(
        side_effect=ImageSearchError("not found", status_code=status_code)
    )

    with patch("app.modules.chat.turn_intercepts.extract_image_lookup_query", return_value="ear"):
        handled = await try_image_lookup_for_turn(
            turn_deps(image_search={"search_and_attach_for_chat": search_and_attach}),
            Settings(image_search_enabled=True),
            user=user,
            chat_id=uuid4(),
            content="show me an ear",
            outcome=None,
            create_user_message=True,
        )

    assert handled is False


@pytest.mark.asyncio
async def test_try_image_lookup_other_error_raises_chat_service_error():
    from app.exceptions import ChatServiceError
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn
    from app.modules.images.search import ImageSearchError

    user = MagicMock()
    user.id = uuid4()

    search_and_attach = AsyncMock(side_effect=ImageSearchError("boom", status_code=500))

    with (
        patch("app.modules.chat.turn_intercepts.extract_image_lookup_query", return_value="ear"),
        pytest.raises(ChatServiceError),
    ):
        await try_image_lookup_for_turn(
            turn_deps(image_search={"search_and_attach_for_chat": search_and_attach}),
            Settings(image_search_enabled=True),
            user=user,
            chat_id=uuid4(),
            content="show me an ear",
            outcome=None,
            create_user_message=True,
        )


@pytest.mark.asyncio
async def test_hard_cancel_with_partial_reply_finalizes(fake_redis, stream_offline_io):
    """WS/SSE CancelledError after tokens must persist like soft stop (no full refund)."""
    import asyncio
    from uuid import uuid4

    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**_kwargs):
        yield "partial "
        raise asyncio.CancelledError()

    finalize = AsyncMock()
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )
    outcome = TurnOutcome()

    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        tokens: list[str] = []
        async for tok in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=None,
            outcome=outcome,
        ):
            tokens.append(tok)
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    assert tokens == ["partial "]
    assert outcome.final_content == "partial"
    assert outcome.completion == "user_stop"
    finalize.assert_awaited()


@pytest.mark.asyncio
async def test_task_cancel_after_tokens_still_finalizes(fake_redis, stream_offline_io):
    """Stopping the task after a token must still save that partial reply."""
    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**_kwargs):
        yield "partial "
        await asyncio.sleep(30)

    finalize = AsyncMock()
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )
    outcome = TurnOutcome()
    tokens: list[str] = []

    async def consume() -> None:
        async for tok in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=None,
            outcome=outcome,
        ):
            tokens.append(tok)

    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        task = asyncio.create_task(consume())
        for _ in range(50):
            if tokens:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        finalize_db = outcome.finalize_db_task
        if isinstance(finalize_db, asyncio.Task):
            await finalize_db

    assert tokens == ["partial "]
    assert outcome.final_content == "partial"
    assert outcome.completion == "user_stop"
    finalize.assert_awaited()


@pytest.mark.asyncio
async def test_hard_cancel_with_empty_reply_reraises(fake_redis, stream_offline_io):
    """CancelledError before any token must propagate so the caller refunds."""
    import asyncio
    from uuid import uuid4

    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**_kwargs):
        raise asyncio.CancelledError()
        yield  # pragma: no cover — async generator

    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )

    with (
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", AsyncMock()) as finalize,
        pytest.raises(asyncio.CancelledError),
    ):
        async for _ in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=None,
            outcome=TurnOutcome(),
        ):
            pass

    finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_fail_with_partial_reply_marks_interrupted(fake_redis, stream_offline_io):
    """A mid-stream provider error with tokens must finalize as interrupted, not complete."""
    from uuid import uuid4

    from app.gateways.litellm_gateway import ModelUnavailableError
    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**_kwargs):
        yield "partial "
        raise ModelUnavailableError("provider died", failed_alias="free-chat")

    finalize = AsyncMock()
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )
    outcome = TurnOutcome()

    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        tokens: list[str] = []
        async for tok in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=None,
            outcome=outcome,
        ):
            tokens.append(tok)
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    assert tokens == ["partial "]
    assert outcome.completion == "interrupted"
    finalize.assert_awaited()


@pytest.mark.asyncio
async def test_token_limit_finish_reason_marks_interrupted(fake_redis, stream_offline_io):
    """finish_reason=length is a truncated answer, not a completed one."""
    from uuid import uuid4

    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**kwargs):
        meta = kwargs.get("stream_meta")
        if isinstance(meta, dict):
            meta["finish_reason"] = "length"
        yield "cutoff"

    finalize = AsyncMock()
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )
    outcome = TurnOutcome()

    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        async for _ in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=None,
            outcome=outcome,
        ):
            pass
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    assert outcome.completion == "interrupted"
    finalize.assert_awaited()


@pytest.mark.asyncio
async def test_soft_cancel_mid_stream_marks_user_stop(fake_redis, stream_offline_io):
    from uuid import uuid4

    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    async def fake_stream(**_kwargs):
        yield "keep "
        yield "going"

    cancel_after_first = {"n": 0}

    def should_cancel() -> bool:
        cancel_after_first["n"] += 1
        return cancel_after_first["n"] > 1

    finalize = AsyncMock()
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )
    outcome = TurnOutcome()

    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        tokens: list[str] = []
        async for tok in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=should_cancel,
            outcome=outcome,
        ):
            tokens.append(tok)
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    assert tokens == ["keep "]
    assert outcome.completion == "user_stop"
    finalize.assert_awaited()


@pytest.mark.asyncio
async def test_stream_closes_llm_stream_on_cancel(fake_redis, stream_offline_io):
    """Stop generation must aclose the provider stream so upstream tokens stop accruing."""
    from app.modules import chat as chat_module

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    class TrackedStream:
        def __init__(self) -> None:
            self.aclose_called = False

        def __call__(self, **_kwargs):
            return self

        def __aiter__(self):
            self._remaining = ["one ", "two ", "three "]
            return self

        async def __anext__(self):
            if not self._remaining:
                raise StopAsyncIteration
            return self._remaining.pop(0)

        async def aclose(self) -> None:
            self.aclose_called = True

    tracked = TrackedStream()
    cancel_after = {"n": 0}

    def should_cancel():
        cancel_after["n"] += 1
        return cancel_after["n"] > 1

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=3)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
        ),
        patch("app.gateways.litellm_gateway.stream_chat_completion", tracked),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()),
    ):
        async for _ in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="question",
            should_cancel=should_cancel,
        ):
            pass

    assert tracked.aclose_called is True


@pytest.mark.asyncio
async def test_stream_places_query_without_location_prompts_to_enable(
    fake_redis, stream_offline_io
):
    """A 'near me' places query with no user.location should yield a deterministic
    'enable location' instant reply and skip web search (no guessing)."""
    from app.modules import chat as chat_module

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_user.location = ""  # no location set
    fake_user.location_enabled = False

    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=0)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
        ),
        patch("app.gateways.litellm_gateway.stream_chat_completion", AsyncMock()),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()),
    ):
        yielded: list[str] = []
        async for tok in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="best restaurants near me",
        ):
            yielded.append(tok)

    # The instant reply is the enable-location prompt (no guessing "near me").
    assert any("Settings" in t and "location" in t.lower() for t in yielded), yielded


@pytest.mark.asyncio
async def test_stream_places_query_with_client_location_skips_the_settings_prompt(
    fake_redis,
    stream_offline_io,
):
    """Opted-in client GPS (no saved profile city) answers, without the settings prompt."""
    from app.modules import chat as chat_module

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_user.location = ""
    fake_user.location_enabled = True

    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    async def fake_stream(**kwargs):
        yield "answer"

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch("app.repositories.users.update", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=0)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
        ),
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()),
    ):
        yielded: list[str] = []
        async for tok in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="best restaurants near me",
            client_location="San Francisco, CA",
        ):
            yielded.append(tok)

    assert not any("Settings" in t for t in yielded), yielded


@pytest.mark.asyncio
async def test_stream_persists_raw_text_when_enrichment_fails(fake_redis, stream_offline_io):
    """Post-stream enrichment (reminder fences, math fences, …) must not
    abort persistence — the user already saw streamed tokens."""
    from app.modules import chat as chat_module

    async def fake_stream(**kwargs):
        yield "hello "
        yield "world"

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    finalize = AsyncMock()

    with ExitStack() as stack:
        stack.enter_context(patch("app.services.quota.reserve_usage_up_to", grant_quota()))
        stack.enter_context(
            patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user))
        )
        stack.enter_context(
            patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat))
        )
        stack.enter_context(
            patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=3))
        )
        stack.enter_context(patch.object(messages_repository, "create", AsyncMock()))
        stack.enter_context(
            patch(
                "app.modules.chat.turn_prep.context.build_prompt_messages",
                AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
            )
        )
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(patch("app.services.quota.adjust_usage", AsyncMock()))
        stack.enter_context(patch("app.repositories.usage.add_tokens", AsyncMock()))
        stack.enter_context(patch.object(chats_repository, "touch_by_id", AsyncMock()))
        stack.enter_context(patch("app.core.jobs.enqueue", AsyncMock()))
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(
            patch(
                "app.modules.todos.materialize_reminder_fences",
                AsyncMock(side_effect=RuntimeError("enrichment boom")),
            )
        )

        outcome = TurnOutcome()
        collected: list[str] = []
        async for tok in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="question",
            outcome=outcome,
            user=fake_user,
        ):
            collected.append(tok)
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    assert collected == ["hello ", "world"]
    finalize.assert_awaited()
    assert finalize.await_args.kwargs["assistant_text"] == "hello world"


@pytest.mark.asyncio
async def test_stream_no_final_content_on_normal_completion(fake_redis, stream_offline_io):
    """`final_content` must NOT be set on a normal (non-cancelled) turn — keep
    `done` payloads small."""
    from app.modules import chat as chat_module

    async def fake_stream(**kwargs):
        yield "answer"

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    with (
        patch("app.services.quota.reserve_usage_up_to", grant_quota()),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user)),
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat)),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=3)),
        patch.object(messages_repository, "create", AsyncMock()),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
        ),
        patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream),
        patch("app.services.quota.adjust_usage", AsyncMock()),
        patch("app.repositories.usage.add_tokens", AsyncMock()),
        patch.object(chats_repository, "touch_by_id", AsyncMock()),
        patch("app.core.jobs.enqueue", AsyncMock()),
    ):
        outcome = TurnOutcome()
        async for _ in chat_module.stream_chat_response(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            user_id=fake_user.id,
            chat_id=MagicMock(),
            content="question",
            outcome=outcome,
        ):
            pass
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    assert outcome.final_content is None


@pytest.mark.asyncio
async def test_regenerate_keeps_assistant_when_stream_empty(fake_redis):
    """The model returns nothing on a regenerate: the turn fails and nothing is
    saved or deleted, so the prior reply (never removed before the stream) stays."""
    from app.modules import chat as chat_module

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_user.timezone = None

    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    fake_last = MagicMock()
    fake_last.role = "assistant"
    fake_last.id = MagicMock()
    fake_last.content = "prior answer"
    fake_last.model = "free-chat"

    fake_last_user = MagicMock()
    fake_last_user.role = "user"
    fake_last_user.content = "question"

    finalize = AsyncMock()
    delete = AsyncMock()

    async def empty_stream(**kwargs):
        if False:
            yield ""

    with ExitStack() as stack:
        for patcher in _offline_session_patches():
            stack.enter_context(patcher)
        stack.enter_context(
            patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user))
        )
        stack.enter_context(
            patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat))
        )
        stack.enter_context(
            patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=2))
        )
        # Every plan can generate images now, so a short regenerate reads the
        # thread for an image follow-up before it searches.
        stack.enter_context(
            patch.object(
                messages_repository,
                "list_recent",
                AsyncMock(return_value=[fake_last_user, fake_last]),
            )
        )
        stack.enter_context(
            patch(
                "app.modules.chat.turn_prep.context.build_prompt_messages",
                AsyncMock(return_value=[{"role": "system", "content": "sys"}]),
            )
        )
        stack.enter_context(
            patch(
                "app.modules.web_search.is_short_letter_answer",
                MagicMock(return_value=False),
            )
        )
        stack.enter_context(
            patch(
                "app.modules.web_search.is_places_list_query",
                MagicMock(return_value=False),
            )
        )
        stack.enter_context(patch("app.services.quota.reserve_usage_up_to", grant_quota()))
        stack.enter_context(patch("app.services.quota.refund_usage", AsyncMock()))
        stack.enter_context(
            patch(
                "app.modules.attachments.lifecycle.detach_attachments_for_messages",
                AsyncMock(return_value=[]),
            )
        )
        stack.enter_context(
            patch(
                "app.modules.attachments.lifecycle.delete_storage_keys",
                AsyncMock(),
            )
        )
        stack.enter_context(patch.object(messages_repository, "delete_message", delete))
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", empty_stream)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        from app.gateways.litellm_gateway import ModelUnavailableError

        with pytest.raises(ModelUnavailableError, match="isn't responding"):
            async for _ in chat_module.stream_regenerate_response(
                offline_deps(),
                fake_redis,
                Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
                user_id=fake_user.id,
                chat_id=MagicMock(),
            ):
                pass

    finalize.assert_not_awaited()
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_regenerate_omits_assistant_from_prompt_without_pre_delete(fake_redis):
    """Prior assistant stays in DB until finalize; prompt build must omit it."""
    from app.modules import chat as chat_module
    from app.modules.chat.prompt_builder import PromptStats
    from app.modules.chat.turn_prep import ClientGeoContext, TurnPromptBundle

    captured: dict[str, object] = {}

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_user.timezone = None

    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    fake_last = MagicMock()
    fake_last.role = "assistant"
    fake_last.id = MagicMock()
    fake_last.content = "prior answer"
    fake_last.model = "free-chat"

    fake_last_user = MagicMock()
    fake_last_user.role = "user"
    fake_last_user.content = "question"

    async def track_build(request, *_args):
        captured["omit"] = request.omit_message_ids
        return TurnPromptBundle(
            prompt_messages=[{"role": "system", "content": "sys"}],
            stats=PromptStats(),
            instant_reply=None,
            local_places=False,
            max_out=100,
            fallback_models=[],
            lightweight=False,
            rich_context=True,
            geo=ClientGeoContext(
                user_location=None,
                client_lat=None,
                client_lng=None,
                has_geo_fix=False,
                geo_query=False,
                ambiguous_nearby=False,
                local_places=False,
            ),
            local_tz="UTC",
            verified_subject=None,
        )

    async def empty_stream(**kwargs):
        if False:
            yield ""

    delete_mock = AsyncMock()

    with ExitStack() as stack:
        for patcher in _offline_session_patches():
            stack.enter_context(patcher)
        stack.enter_context(
            patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user))
        )
        stack.enter_context(
            patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat))
        )
        stack.enter_context(
            patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=2))
        )
        stack.enter_context(
            patch.object(
                messages_repository,
                "list_recent",
                AsyncMock(return_value=[fake_last_user, fake_last]),
            )
        )
        stack.enter_context(
            patch(
                "app.modules.chat.stream_entry.build_stream_prompt_context",
                side_effect=track_build,
            )
        )
        stack.enter_context(patch("app.services.quota.reserve_usage_up_to", grant_quota()))
        stack.enter_context(patch("app.services.quota.refund_usage", AsyncMock()))
        stack.enter_context(
            patch(
                "app.modules.attachments.lifecycle.detach_attachments_for_messages",
                AsyncMock(return_value=[]),
            )
        )
        stack.enter_context(
            patch(
                "app.modules.attachments.lifecycle.delete_storage_keys",
                AsyncMock(),
            )
        )
        stack.enter_context(
            patch.object(
                messages_repository,
                "delete_message",
                delete_mock,
            )
        )
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", empty_stream)
        )
        from app.gateways.litellm_gateway import ModelUnavailableError

        with pytest.raises(ModelUnavailableError):
            async for _ in chat_module.stream_regenerate_response(
                offline_deps(),
                fake_redis,
                Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
                user_id=fake_user.id,
                chat_id=MagicMock(),
            ):
                pass

    assert captured["omit"] == {fake_last.id}
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_regenerate_passes_client_geo_to_the_turn(fake_redis):
    """The device's place reaches the turn a regenerate builds (its searches use it)."""
    from app.modules import chat as chat_module

    fake_user = MagicMock()
    fake_user.id = MagicMock()
    fake_user.default_model = "free-chat"
    fake_user.timezone = None
    fake_user.locale = "en"

    fake_chat = MagicMock()
    fake_chat.model = "free-chat"
    fake_chat.summary = None

    fake_last = MagicMock()
    fake_last.role = "assistant"
    fake_last.id = MagicMock()
    fake_last.content = "old"
    fake_last.model = "free-chat"

    fake_last_user = MagicMock()
    fake_last_user.role = "user"
    fake_last_user.content = "Best restaurants near me"

    class _Built(Exception):
        pass

    captured: dict[str, Any] = {}

    async def build(request, *_args):
        captured["request"] = request
        raise _Built

    with ExitStack() as stack:
        for patcher in _offline_session_patches():
            stack.enter_context(patcher)
        stack.enter_context(
            patch("app.repositories.users.get_by_id", AsyncMock(return_value=fake_user))
        )
        stack.enter_context(
            patch.object(chats_repository, "get_by_id", AsyncMock(return_value=fake_chat))
        )
        stack.enter_context(
            patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=2))
        )
        stack.enter_context(
            patch.object(
                messages_repository,
                "list_recent",
                AsyncMock(return_value=[fake_last_user, fake_last]),
            )
        )
        stack.enter_context(
            patch("app.modules.chat.stream_entry.build_stream_prompt_context", build)
        )
        stack.enter_context(patch("app.services.quota.reserve_usage_up_to", grant_quota()))
        stack.enter_context(patch("app.services.quota.refund_usage", AsyncMock()))
        with pytest.raises(_Built):
            async for _ in chat_module.stream_regenerate_response(
                offline_deps(),
                fake_redis,
                Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
                user_id=fake_user.id,
                chat_id=MagicMock(),
                client_location="San Francisco, CA",
                client_latitude=37.77,
                client_longitude=-122.42,
            ):
                pass

    request = captured["request"]
    assert (request.client_latitude, request.client_longitude) == (37.77, -122.42)
    assert request.client_location == "San Francisco, CA"


@pytest.mark.asyncio
async def test_instant_reply_usage_uses_input_output_keys(fake_redis, stream_offline_io):
    """Instant replies must seed usage with ``input``/``output`` — the keys
    ``finalize_stream_turn_db`` reads. ``input_tokens``/``output_tokens`` were
    ignored, so quota fell back to full prompt re-estimation and overcharged."""
    from uuid import uuid4

    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    captured: dict[str, object] = {}

    async def capture_finalize(*_args, assistant_text, usage, outcome):
        captured["usage"] = dict(usage)
        captured["assistant_text"] = assistant_text

    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "what time is it?"}],
        run_title=False,
        user_message_content="what time is it?",
        reserved_tokens=100,
        max_output_tokens=50,
        instant_reply="It's 3:00 PM.",
        skip_memory_jobs=True,
    )

    outcome = TurnOutcome()
    with (
        patch(
            "app.modules.chat.stream_pipeline.finalize_stream_turn_db", side_effect=capture_finalize
        ),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)),
    ):
        tokens: list[str] = []
        async for tok in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            ctx,
            should_cancel=None,
            outcome=outcome,
        ):
            tokens.append(tok)
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    assert tokens == ["It's 3:00 PM."]
    assert "usage" in captured
    usage = captured["usage"]
    assert isinstance(usage, dict)
    assert "input" in usage and "output" in usage
    assert "input_tokens" not in usage and "output_tokens" not in usage
    # Instant replies skip the LLM entirely (canned time/location/not-connected
    # answers) — no provider token cost, so quota is not charged: 0/0 seeds
    # let finalize's adjust_usage refund the full reservation.
    assert usage["input"] == 0
    assert usage["output"] == 0


@pytest.mark.asyncio
async def test_web_search_tool_round_streams_final_instead_of_regenerating(
    fake_redis,
    stream_offline_io,
):
    """After web_search tools run, the visible answer is streamed — not a
    leftover complete_with_tools dumped as one instant_reply chunk."""
    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    query = "What's the latest news on SpaceX?"
    prompt = [{"role": "user", "content": query}]
    after_tools = [
        *prompt,
        {"role": "assistant", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "SpaceX landed Starship."},
    ]
    stream_messages: list[list[dict]] = []

    async def fake_stream(**kwargs):
        stream_messages.append(kwargs["messages"])
        yield "SpaceX "
        yield "landed."

    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=prompt,
        run_title=False,
        user_message_content=query,
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )
    outcome = TurnOutcome()
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "app.modules.chat.tool_loop.run_tool_rounds",
                AsyncMock(return_value=(after_tools, None, None, [])),
            )
        )
        stack.enter_context(
            patch("app.services.quota.global_spend_exceeded", AsyncMock(return_value=False))
        )
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", AsyncMock())
        )
        stack.enter_context(patch("app.services.model_health.record_samples", AsyncMock()))
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        yielded: list[str] = []
        async for tok in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=True),
            ctx,
            should_cancel=None,
            outcome=outcome,
        ):
            yielded.append(tok)
        finalize_db = outcome.finalize_db_task
        if finalize_db is not None:
            await finalize_db

    assert yielded == ["SpaceX ", "landed."]
    assert ctx.instant_reply is None
    assert stream_messages == [after_tools]


@pytest.mark.asyncio
async def test_a_photo_ask_with_no_photo_is_answered_in_words_not_drawn():
    """ "Show me a picture of Albert Einstein" found no usable photo and drew him."""
    from app.modules.chat.turn_intercepts import intercept_new_turn
    from app.modules.images.search import ImageSearchError

    user = MagicMock()
    user.id = uuid4()
    generate = AsyncMock()
    deps = _image_gen_deps(
        image_search={
            "search_and_attach_for_chat": AsyncMock(
                side_effect=ImageSearchError(
                    "Could not find a usable reference photo", status_code=502
                )
            )
        },
        image_generation={"generate_for_chat": generate},
    )
    handled = await intercept_new_turn(
        deps,
        Settings(image_search_enabled=True),
        user=user,
        chat_id=uuid4(),
        content="show me a picture of Albert Einstein",
        outcome=None,
        recent_messages=[],
        prior_count=0,
    )
    assert handled is False
    generate.assert_not_awaited()
