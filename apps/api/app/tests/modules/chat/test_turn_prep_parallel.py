"""turn_prep parallelization: fetches run concurrently and inject in stable order.

Guards the refactor that split fetch from inject in ``build_stream_prompt_context``:
- Phase A overlaps ``build_prompt_messages`` with instant-reply and fallback-model
  resolution.
- Phase B gathers the web+tools fetch and the web-search classifier concurrently.
- Phase C injects in the stable order (web -> math) so the final prompt is
  byte-identical to the prior serial pipeline.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.prompt_builder import SubjectFetch
from app.modules.chat.turn_prep.context import build_stream_prompt_context
from app.modules.chat.turn_prep.mode import _TurnMode
from app.modules.chat.turn_prep.request import TurnRequest
from app.services.time_context import format_date_answer, format_year_answer
from app.tests.fakes import FakeSessionCM, redis_mock


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.locale = "en"
    user.timezone = None
    user.memory_enabled = True
    user.location_enabled = False
    user.location = None
    return user


def _make_chat() -> MagicMock:
    chat = MagicMock()
    chat.id = uuid4()
    chat.summary = None
    return chat


def _rich_turn_mode() -> _TurnMode:
    return _TurnMode(
        lightweight=False,
        rich_context=True,
        minimal_personal=False,
        day_planning=False,
        day_reflection=False,
    )


def _slim_turn_mode() -> _TurnMode:
    return _TurnMode(
        lightweight=False,
        rich_context=False,
        minimal_personal=False,
        day_planning=False,
        day_reflection=False,
    )


# The expectations are callables, not values. pytest evaluates a parametrize
# list once at collection; calling format_date_answer(None) there froze "today"
# at collection time, so a suite that crossed UTC midnight asserted the previous
# day's date against a reply built after the rollover. Deferring the call to the
# assertion puts both sides on the same clock.
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,expected_instant_reply",
    [
        ("Again", lambda: None),
        ("tell me again", lambda: None),
        ("what time is it", lambda: "```clock\n```"),
        ("what year is it", lambda: format_year_answer(None)),
        ("what's the date", lambda: format_date_answer(None)),
    ],
    ids=["again", "tell-me-again", "what-time", "what-year", "whats-the-date"],
)
async def test_followup_keeps_conversation_context_instead_of_instant_clock(
    content, expected_instant_reply, fake_redis
):
    user = _make_user()
    chat = _make_chat()
    messages = [
        {"role": "system", "content": "BASE"},
        {"role": "user", "content": "Repeat the word pineapple"},
        {"role": "assistant", "content": "pineapple"},
        {"role": "user", "content": content},
    ]
    build_prompt = AsyncMock(return_value=list(messages))
    with (
        patch("app.modules.chat.turn_prep.context.build_prompt_messages", build_prompt),
        patch("app.services.model_health.enrich_models_health", AsyncMock(return_value={})),
        patch(
            "app.modules.chat.turn_prep.context.plan_service.chat_fallback_models",
            return_value=[],
        ),
    ):
        bundle = await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content=content,
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_slim_turn_mode(),
            ),
            Settings(
                _env_file=None,
                mcp_tool_loop_enabled=False,
                math_tools_enabled=False,
                web_search_enabled=False,
            ),
            fake_redis,
        )

    assert bundle.instant_reply == expected_instant_reply()
    assert bundle.prompt_messages == messages
    assert build_prompt.await_args.kwargs["query_text"] == content


@pytest.mark.asyncio
async def test_year_date_time_instant_reply_skipped_when_image_attached(fake_redis):
    """A photo of a clock/calendar/document must go to vision, not Instant year."""
    user = _make_user()
    chat = _make_chat()
    content = "what year is it"
    messages = [
        {"role": "system", "content": "BASE"},
        {"role": "user", "content": content},
    ]
    build_prompt = AsyncMock(return_value=list(messages))
    with (
        patch("app.modules.chat.turn_prep.context.build_prompt_messages", build_prompt),
        patch("app.services.model_health.enrich_models_health", AsyncMock(return_value={})),
        patch(
            "app.modules.chat.turn_prep.context.plan_service.chat_fallback_models",
            return_value=[],
        ),
    ):
        bundle = await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content=content,
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                has_image_attachment=True,
                user=user,
                chat=chat,
                turn_mode=_slim_turn_mode(),
            ),
            Settings(
                _env_file=None,
                mcp_tool_loop_enabled=False,
                math_tools_enabled=False,
                web_search_enabled=False,
            ),
            fake_redis,
        )

    assert bundle.instant_reply is None


@pytest.mark.parametrize(
    "content",
    [
        "if i make 3400 a every 2 weeks, how much money would i make untill dcember 11th from today",
        (
            "If i make 1500a week, how much would i make until December 11th? "
            "Please tell me the current date."
        ),
    ],
)
@pytest.mark.asyncio
async def test_recurring_pay_reply_skips_prompt_model_health_and_subject_fetch(fake_redis, content):
    user = _make_user()
    user.timezone = "America/Los_Angeles"
    chat = _make_chat()
    build_prompt = AsyncMock(side_effect=AssertionError("prompt should not be built"))
    with (
        patch("app.modules.chat.turn_prep.context.build_prompt_messages", build_prompt),
        patch("app.services.model_health.enrich_models_health", AsyncMock()) as health,
        patch("app.modules.chat.turn_prep.augment.fetch_subject", AsyncMock()) as subject,
    ):
        bundle = await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content=content,
                model="gpt-6-luna",
                client_timezone="America/Los_Angeles",
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_slim_turn_mode(),
            ),
            Settings(_env_file=None),
            fake_redis,
        )

    assert bundle.instant_reply is not None
    assert "**1. Count the time**" in bundle.instant_reply
    assert bundle.fallback_models == []
    build_prompt.assert_not_awaited()
    health.assert_not_awaited()
    subject.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetches_run_concurrently_not_serially():
    """Phase A (build_prompt | fallback-model health) overlaps, so it costs the slower
    of the two, not the sum; Phase B (the subject fetch) follows it."""
    user = _make_user()
    chat = _make_chat()

    base_messages = [{"role": "system", "content": "BASE"}, {"role": "user", "content": "hi"}]
    # Each Phase A fetch waits for the other to start: run one after the other, the
    # first times out alone.
    phase_a = asyncio.Barrier(2)
    finished: list[str] = []

    async def slow_prompt(*_a, **_kw):
        await asyncio.wait_for(phase_a.wait(), timeout=1)
        finished.append("prompt")
        return list(base_messages)

    async def slow_health(*_a, **_kw):
        await asyncio.wait_for(phase_a.wait(), timeout=1)
        finished.append("health")
        return {}

    async def slow_subject(*_a, **_kw):
        finished.append("subject")
        return SubjectFetch(None, None, False, None, None)

    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(side_effect=slow_prompt),
        ),
        patch("app.modules.billing.plan.model_pool", return_value=[]),
        patch("app.modules.billing.plan.chat_fallback_models", return_value=[]),
        patch(
            "app.services.model_health.enrich_models_health",
            AsyncMock(side_effect=slow_health),
        ),
        patch(
            "app.modules.chat.turn_prep.augment.fetch_subject",
            AsyncMock(side_effect=slow_subject),
        ),
        patch(
            "app.modules.chat.turn_prep.instant.extract_settings_changes",
            return_value=[],
        ),
    ):
        bundle = await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content="Who leads Acme Corporation?",
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_rich_turn_mode(),
            ),
            Settings(
                max_output_tokens=1000,
                mcp_tool_loop_enabled=False,
                math_tools_enabled=True,
                web_search_enabled=True,
            ),
            MagicMock(),
        )

    assert sorted(finished[:2]) == ["health", "prompt"]
    assert finished[2:] == ["subject"]
    assert bundle.instant_reply is None


@pytest.mark.asyncio
async def test_injects_the_subject_block_before_the_last_user_message():
    """The real inject places the subject block just before the last user message."""
    user = _make_user()
    chat = _make_chat()

    base_messages = [{"role": "system", "content": "BASE"}, {"role": "user", "content": "hi"}]

    async def fast_prompt(*_a, **_kw):
        return list(base_messages)

    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(side_effect=fast_prompt),
        ),
        # Only the FETCHES are mocked; the real inject functions run so we can
        # assert the final prompt shape end-to-end.
        patch(
            "app.modules.chat.turn_prep.augment.fetch_subject",
            AsyncMock(return_value=SubjectFetch("MATH_BLOCK", None, False, None, None)),
        ),
        patch(
            "app.modules.chat.turn_prep.instant.extract_settings_changes",
            return_value=[],
        ),
    ):
        bundle = await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content="explain photosynthesis",
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_rich_turn_mode(),
            ),
            Settings(
                max_output_tokens=1000,
                mcp_tool_loop_enabled=False,
                math_tools_enabled=True,
                web_search_enabled=True,
            ),
            redis_mock(),
        )

    messages = bundle.prompt_messages
    assert messages == [
        {"role": "system", "content": "BASE"},
        {"role": "system", "content": "MATH_BLOCK"},
        {"role": "user", "content": "hi"},
    ]


@pytest.mark.asyncio
async def test_slim_coaching_turn_skips_phase_b_fetches():
    """Help-me-think must not load web/math/chem prefetch."""
    user = _make_user()
    chat = _make_chat()
    base_messages = [{"role": "system", "content": "BASE"}, {"role": "user", "content": "hi"}]
    fetch_subject_mock = AsyncMock(return_value=SubjectFetch(None, None, False, None, None))

    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=list(base_messages)),
        ),
        patch(
            "app.modules.chat.turn_prep.augment.fetch_subject",
            fetch_subject_mock,
        ),
        patch(
            "app.modules.chat.turn_prep.instant.extract_settings_changes",
            return_value=[],
        ),
    ):
        await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content="I want to talk something through — ask me a good opening question.",
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_slim_turn_mode(),
            ),
            Settings(
                max_output_tokens=1000,
                mcp_tool_loop_enabled=False,
                math_tools_enabled=True,
                web_search_enabled=True,
            ),
            redis_mock(),
        )

    fetch_subject_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_web_augment_takes_priors_from_the_prompt():
    """Web/math prefetch names the search subject from the earlier user lines, read from
    the prompt's own history rather than the messages again."""
    user = _make_user()
    chat = _make_chat()
    base_messages = [
        {"role": "system", "content": "BASE"},
        {"role": "user", "content": "earlier question"},
        {"role": "user", "content": "explain photosynthesis"},
    ]
    fetch_subject_mock = AsyncMock(return_value=SubjectFetch(None, None, False, None, None))

    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=list(base_messages)),
        ),
        patch("app.modules.chat.turn_prep.augment.fetch_subject", fetch_subject_mock),
        patch(
            "app.modules.chat.turn_prep.instant.extract_settings_changes",
            return_value=[],
        ),
    ):
        await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content="explain photosynthesis",
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_rich_turn_mode(),
            ),
            Settings(
                max_output_tokens=1000,
                mcp_tool_loop_enabled=False,
                math_tools_enabled=True,
                web_search_enabled=True,
            ),
            redis_mock(),
        )

    assert fetch_subject_mock.await_args.kwargs["prior_user_messages"] == ["earlier question"]


@pytest.mark.asyncio
@pytest.mark.parametrize("graph", [False, True], ids=["closed-answer", "cubic-graph"])
async def test_verified_closed_math_sets_instant_reply(fake_redis, graph) -> None:
    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep.context import StreamContext
    from app.modules.math.schemas import GraphBlockSpec
    from app.services.solving import VerifiedMathBlock

    user = _make_user()
    chat = _make_chat()
    content = "graph y = x^3" if graph else "1+1=x"
    model = "smart-chat" if graph else "free-chat"
    fence = (
        GraphBlockSpec(expr="x**3", points=[[-1, -1], [0, 0], [1, 1]]).model_dump()
        if graph
        else {"type": "answer", "content": "x = 2"}
    )
    verified = VerifiedMathBlock(
        text="verified",
        canonical_fence=fence,
        canonical_answer=None if graph else "x = 2",
    )
    messages = [{"role": "system", "content": "BASE"}, {"role": "user", "content": content}]
    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=list(messages)),
        ),
        patch(
            "app.modules.chat.turn_prep.augment.fetch_subject",
            AsyncMock(return_value=SubjectFetch("MATH_BLOCK", verified, False, None, None)),
        ),
        patch(
            "app.modules.chat.turn_prep.instant.extract_settings_changes",
            return_value=[],
        ),
        patch("app.services.model_health.enrich_models_health", AsyncMock(return_value={})),
        patch(
            "app.modules.chat.turn_prep.context.plan_service.chat_fallback_models",
            return_value=[],
        ),
    ):
        bundle = await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content=content,
                model=model,
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_slim_turn_mode(),
            ),
            Settings(
                mcp_tool_loop_enabled=False,
                math_tools_enabled=True,
                web_search_enabled=False,
            ),
            fake_redis,
        )

    assert bundle.verified_subject is verified
    assert bundle.instant_reply is not None
    assert ("```graph" if graph else "```answer") in bundle.instant_reply
    if graph:
        # Mobile's streaming fence scanner needs the closing line terminated.
        assert bundle.instant_reply.endswith("```\n")
    else:
        assert "x = 2" in bundle.instant_reply

    ctx = StreamContext(
        user_id=user.id,
        chat_id=chat.id,
        model=model,
        prompt_messages=bundle.prompt_messages,
        run_title=False,
        user_message_content=content,
        reserved_tokens=100,
        max_output_tokens=bundle.max_out,
        instant_reply=bundle.instant_reply,
        verified_subject=verified,
    )
    with (
        patch("app.modules.chat.stream_pipeline.run_tool_loop_path", AsyncMock()) as tools,
        patch("app.modules.chat.stream_pipeline.run_llm_token_stream") as llm,
    ):
        stream = stream_and_finalize(MagicMock(), fake_redis, Settings(), ctx, should_cancel=None)
        assert isinstance(stream, AsyncGenerator)
        try:
            # Available before finalization/DB persistence and with no model call.
            assert await anext(stream) == bundle.instant_reply
            tools.assert_not_awaited()
            llm.assert_not_called()
        finally:
            await stream.aclose()


@pytest.mark.asyncio
async def test_verified_chemistry_owns_turn_over_incidental_math(fake_redis) -> None:
    """Unit-bearing chemistry keeps one chemistry answer fence, not an algebra rewrite."""
    from app.modules.chemistry.block import build_verified_chemistry
    from app.modules.chemistry.extract import extract_chemistry_intent

    user = _make_user()
    chat = _make_chat()
    content = "Find Gibbs free energy when delta H=-40 kJ, delta S=-100 J and T=300 K"
    intent = extract_chemistry_intent(content)
    assert intent is not None
    verified_chemistry = build_verified_chemistry(intent)
    assert verified_chemistry is not None
    messages = [{"role": "system", "content": "BASE"}, {"role": "user", "content": content}]

    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=list(messages)),
        ),
        patch(
            "app.modules.chat.turn_prep.augment.fetch_subject",
            AsyncMock(
                return_value=SubjectFetch(
                    verified_chemistry.prompt_text,
                    verified_chemistry,
                    False,
                    None,
                    None,
                )
            ),
        ),
        patch(
            "app.modules.chat.turn_prep.instant.extract_settings_changes",
            return_value=[],
        ),
        patch("app.services.model_health.enrich_models_health", AsyncMock(return_value={})),
        patch(
            "app.modules.chat.turn_prep.context.plan_service.chat_fallback_models",
            return_value=[],
        ),
    ):
        bundle = await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content=content,
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_slim_turn_mode(),
            ),
            Settings(
                mcp_tool_loop_enabled=False,
                math_tools_enabled=True,
                chemistry_enabled=True,
                web_search_enabled=False,
            ),
            fake_redis,
        )

    assert bundle.verified_subject is verified_chemistry
    assert bundle.instant_reply is not None
    assert bundle.instant_reply.count("```answer") == 1
    assert "notation: chemistry\nΔG = −10 kJ/mol" in bundle.instant_reply
    assert "H = 2Sk/5" not in bundle.instant_reply
    assert "✅" not in bundle.instant_reply


@pytest.mark.asyncio
async def test_verified_math_keeps_llm_when_user_wants_steps(fake_redis) -> None:
    from app.services.solving import VerifiedMathBlock

    user = _make_user()
    chat = _make_chat()
    content = "Solve 1+1=x and explain every step"
    verified = VerifiedMathBlock(
        text="verified",
        canonical_fence={"type": "answer", "content": "x = 2"},
        canonical_answer="x = 2",
    )
    messages = [{"role": "system", "content": "BASE"}, {"role": "user", "content": content}]
    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=list(messages)),
        ),
        patch(
            "app.modules.chat.turn_prep.augment.fetch_subject",
            AsyncMock(return_value=SubjectFetch("MATH_BLOCK", verified, False, None, None)),
        ),
        patch(
            "app.modules.chat.turn_prep.instant.extract_settings_changes",
            return_value=[],
        ),
        patch("app.services.model_health.enrich_models_health", AsyncMock(return_value={})),
        patch(
            "app.modules.chat.turn_prep.context.plan_service.chat_fallback_models",
            return_value=[],
        ),
    ):
        bundle = await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content=content,
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_slim_turn_mode(),
            ),
            Settings(
                mcp_tool_loop_enabled=False,
                math_tools_enabled=True,
                web_search_enabled=False,
            ),
            fake_redis,
        )

    assert bundle.verified_subject is verified
    assert bundle.instant_reply is None


async def _graph_it_bundle(fake_redis, priors: list[str]):
    user = _make_user()
    chat = _make_chat()
    content = "graph it"
    messages = [{"role": "user", "content": prior} for prior in priors] + [
        {"role": "user", "content": content}
    ]
    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.chat.turn_prep.context.build_prompt_messages",
            AsyncMock(return_value=messages),
        ),
        patch("app.services.model_health.enrich_models_health", AsyncMock(return_value={})),
        patch(
            "app.modules.chat.turn_prep.context.plan_service.chat_fallback_models",
            return_value=[],
        ),
    ):
        return await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content=content,
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_slim_turn_mode(),
            ),
            Settings(
                mcp_tool_loop_enabled=False,
                math_tools_enabled=True,
                chemistry_enabled=False,
                web_search_enabled=False,
            ),
            fake_redis,
        )


@pytest.mark.asyncio
async def test_graph_it_after_a_quadratic_reaches_the_solver(fake_redis) -> None:
    bundle = await _graph_it_bundle(fake_redis, ["solve x^2 - 5x + 6 = 0"])

    assert bundle.solver_unverified is False
    rendered = "\n".join(message["content"] for message in bundle.prompt_messages)
    assert "x^2" in rendered or (
        bundle.verified_subject is not None and "x^2" in (bundle.verified_subject.text or "")
    )


@pytest.mark.asyncio
async def test_graph_it_with_no_equation_does_not_stamp_unverified(fake_redis) -> None:
    bundle = await _graph_it_bundle(fake_redis, ["what is a vagina"])

    assert bundle.solver_unverified is False
    rendered = "\n".join(message["content"] for message in bundle.prompt_messages)
    assert "Couldn't verify" not in rendered
