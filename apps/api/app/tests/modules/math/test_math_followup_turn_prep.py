"""The real current-user history shape must reach the short math follow-up policy."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.models.orm import Chat, User
from app.modules.chat.prompt_context import _PromptContextBlocks
from app.modules.chat.prompt_inject import conversation_turns
from app.modules.chat.turn_prep.context import build_stream_prompt_context
from app.modules.chat.turn_prep.mode import _TurnMode
from app.modules.chat.turn_prep.prepare import prepare_chat_turn
from app.modules.chat.turn_prep.request import TurnRequest
from app.modules.conversation import messages_repository
from app.modules.math.followup import MATH_FOLLOWUP_HINT
from app.modules.math.reply_policy import MATH_REPLY_POLICY
from app.tests.fakes import redis_mock
from app.tests.modules.chat.chat_test_support import system_prompt

_QUERY = "Sum 1/n^2 from n=1 to infinity"
_RESULT = r"\frac{\pi^{2}}{6}"
_EQUATION = "3x^2 + 3 = 5"
_EQUATION_RESULT = r"x = \pm \frac{\sqrt{6}}{3}"


class _Session:
    async def __aenter__(self) -> AsyncMock:
        return AsyncMock()

    async def __aexit__(self, *_args: object) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("overlap", [True, False])
async def test_actual_c12_how_through_prepare_context_and_prompt_builder(overlap: bool) -> None:
    user = User(
        id=uuid4(),
        name="Test",
        email="test@example.com",
        locale="en",
        timezone="UTC",
        memory_enabled=False,
    )
    chat = Chat(id=uuid4(), user_id=user.id, title="Test")
    history = [
        SimpleNamespace(id=uuid4(), role="user", content=_QUERY),
        SimpleNamespace(id=uuid4(), role="assistant", content=f"```answer\n{_RESULT}\n```"),
    ]
    original_history = list(history)
    release = asyncio.Event()
    if not overlap:
        release.set()
    persisted_ids: list[UUID] = []

    async def create_message(*_args: object, **kwargs: object) -> SimpleNamespace:
        await release.wait()
        message = SimpleNamespace(id=kwargs["message_id"], role="user", content=kwargs["content"])
        history.append(message)
        persisted_ids.append(message.id)
        return message

    async def context_blocks(*_args: object, **kwargs: object) -> _PromptContextBlocks:
        recent = kwargs["recent_messages"]
        assert recent is None or isinstance(recent, list)
        return _PromptContextBlocks(
            memory_block="",
            todos_section=None,
            recent_all=list(recent) if recent is not None else list(history),
            attachment_rag_block="",
            chat=chat,
        )

    settings = Settings(
        attachments_enabled=False,
        attachment_rag_enabled=False,
        mcp_tool_loop_enabled=False,
        math_tools_enabled=False,
        chemistry_enabled=False,
        web_search_enabled=False,
    )
    with (
        patch("app.modules.chat.turn_prep.persist.SessionLocal", return_value=_Session()),
        patch.object(messages_repository, "create", AsyncMock(side_effect=create_message)),
        patch(
            "app.modules.chat.prompt_builder._load_context_blocks",
            AsyncMock(side_effect=context_blocks),
        ),
        patch("app.services.model_health.enrich_models_health", AsyncMock(return_value={})),
        patch(
            "app.modules.chat.turn_prep.context.plan_service.chat_fallback_models", return_value=[]
        ),
    ):
        context = await asyncio.wait_for(
            prepare_chat_turn(
                user_id=user.id,
                chat_id=chat.id,
                content="how",
                model_alias=None,
                settings=settings,
                redis=redis_mock(),
                reserved_tokens=100,
                user=user,
                chat=chat,
                turn_mode=_TurnMode(
                    lightweight=False,
                    rich_context=False,
                    minimal_personal=False,
                    day_planning=False,
                    day_reflection=False,
                ),
                prior_count=2,
                recent_messages=original_history if overlap else None,
                resolved_model="free-chat",
            ),
            timeout=2,
        )
        try:
            # The policy closes the turn's context, after the history.
            assert context.prompt_messages[-2]["role"] == "system"
            assert context.prompt_messages[-2]["content"].endswith(
                f"{MATH_REPLY_POLICY}\n\n{MATH_FOLLOWUP_HINT}"
            )
            assert conversation_turns(context.prompt_messages)[-2:] == [
                {"role": "assistant", "content": f"Previous result:\n\\[\n{_RESULT}\n\\]"},
                {"role": "user", "content": "how"},
            ]
            assert MATH_FOLLOWUP_HINT in system_prompt(context.prompt_messages)
            if overlap:
                assert persisted_ids == []
        finally:
            release.set()
            if context.user_message_persist is not None:
                await context.user_message_persist
    assert len(persisted_ids) == 1
    assert history[-1].content == "how"


@pytest.mark.asyncio
async def test_how_replays_code_owned_steps_instead_of_calling_the_llm(
    thread_sympy_executor: None,
) -> None:
    user = User(
        id=uuid4(),
        name="Test",
        email="test@example.com",
        locale="en",
        timezone="UTC",
        memory_enabled=False,
    )
    chat = Chat(id=uuid4(), user_id=user.id, title="Test")
    current = SimpleNamespace(id=uuid4(), role="user", content="how")
    history = [
        SimpleNamespace(id=uuid4(), role="user", content=_EQUATION),
        SimpleNamespace(
            id=uuid4(), role="assistant", content=f"```answer\n{_EQUATION_RESULT}\n```"
        ),
        current,
    ]
    blocks = _PromptContextBlocks(
        memory_block="",
        todos_section=None,
        recent_all=history,
        attachment_rag_block="",
        chat=chat,
    )
    settings = Settings(
        attachments_enabled=False,
        attachment_rag_enabled=False,
        mcp_tool_loop_enabled=False,
        math_tools_enabled=True,
        chemistry_enabled=False,
        web_search_enabled=False,
    )
    with (
        patch(
            "app.modules.chat.prompt_builder._load_context_blocks",
            AsyncMock(return_value=blocks),
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
                content="how",
                model="free-chat",
                client_timezone=None,
                client_location=None,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=_TurnMode(
                    lightweight=False,
                    rich_context=False,
                    minimal_personal=False,
                    day_planning=False,
                    day_reflection=False,
                ),
                recent_messages=history,
                current_user_message_id=current.id,
            ),
            settings,
            AsyncMock(),
        )

    assert bundle.verified_subject is not None
    assert bundle.instant_reply is not None
    assert bundle.instant_reply.startswith("**Given**")
    assert "Subtract 3 from both sides" in bundle.instant_reply
    assert "Take the square root of both sides" in bundle.instant_reply
    assert "—" in bundle.instant_reply.split("```answer")[0]
    assert _EQUATION_RESULT in bundle.instant_reply
