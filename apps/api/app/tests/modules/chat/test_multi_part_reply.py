"""The server's part of a multi-part reply: a settings card beside the answer.

"Switch to dark mode and tell me a joke" used to lose the switch, and "switch to dark
mode, and also what is the capital of France?" the question (I4).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.finalize_parts import add_settings_card
from app.modules.chat.finalize_passes import FinalizeState
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.chat.turn_prep.instant import resolve_instant_reply, settings_card
from app.modules.chat.turn_prep.intents import plan_turn

_CARD = 'I can switch that for you: Appearance → Dark.\n\n```settings_proposal\n{"proposal_id": "p"}\n```'


def _state(text: str, **ctx_fields: Any) -> FinalizeState:
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "x"}],
        run_title=False,
        user_message_content="x",
        reserved_tokens=0,
        max_output_tokens=0,
        **ctx_fields,
    )
    return FinalizeState(
        deps=MagicMock(),
        settings=Settings(),
        ctx=ctx,
        raw=text,
        text=text,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[text],
        should_cancel=None,
    )


def test_the_settings_card_goes_under_the_answer() -> None:
    state = _state("Why did the scarecrow win an award? He was outstanding in his field.")
    state.ctx.settings_card = _CARD
    text = add_settings_card(state)
    assert text.startswith("Why did the scarecrow")
    assert text.endswith("```")
    assert "```settings_proposal" in text
    assert state.committed == text


def test_a_card_the_model_wrote_is_dropped_for_the_servers() -> None:
    forged = 'Sure!\n\n```settings_proposal\n{"proposal_id": "made-up"}\n```\n\nA joke.'
    state = _state(forged, settings_card=_CARD)
    text = add_settings_card(state)
    assert "made-up" not in text
    assert text.count("```settings_proposal") == 1


def test_no_card_leaves_the_reply_alone() -> None:
    state = _state("Just an answer.")
    assert add_settings_card(state) == "Just an answer."
    assert state.committed is None


def _identity() -> Any:
    user = SimpleNamespace(id=uuid4(), locale="en", plan="free")
    return SimpleNamespace(user=user, local_tz="UTC", geo=SimpleNamespace(user_location=None))


@pytest.mark.asyncio
async def test_settings_card_for_the_settings_part() -> None:
    plan = plan_turn("switch to dark mode, and also what is the capital of France?")
    materialize = AsyncMock(return_value=_CARD)
    with patch(
        "app.modules.chat.turn_prep.instant.settings_proposal_service.materialize_settings_reply",
        materialize,
    ):
        card = await settings_card(_identity(), Settings(), AsyncMock(), plan)
    assert card == _CARD
    call = materialize.await_args
    assert call is not None
    changes = call.args[2]
    assert [(change.field, change.value) for change in changes] == [("appearance", "dark")]


@pytest.mark.asyncio
async def test_a_multi_part_message_gets_no_instant_reply() -> None:
    """The settings card used to be the whole reply and drop "what is the capital"."""
    text = "switch to dark mode, and also what is the capital of France?"
    request = SimpleNamespace(content=text, has_image_attachment=False, recent_messages=[])
    reply = await resolve_instant_reply(
        request,  # type: ignore[arg-type]
        _identity(),
        Settings(),
        AsyncMock(),
        plan_turn(text),
    )
    assert reply is None


@pytest.mark.asyncio
async def test_settings_card_is_none_for_one_request() -> None:
    assert (
        await settings_card(_identity(), Settings(), AsyncMock(), plan_turn("switch to dark mode"))
        is None
    )
