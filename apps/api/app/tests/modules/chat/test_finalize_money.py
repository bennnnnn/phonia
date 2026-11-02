"""The money pass: the server's note and calculator card under a money reply, and only there."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.core.config import Settings
from app.modules.chat.finalize_money import attach_money_card
from app.modules.chat.finalize_passes import FinalizeState
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.money.catalog import product
from app.modules.money.read import MoneyRequest
from app.modules.money.service import MoneyTurn
from app.modules.money.solve import work
from app.tests.modules.money.money_support import average

_FORGED = '```calculator\n{"v":1,"product":"loan"}\n```'


def _state(text: str, money: MoneyTurn | None, *, cancelled: bool = False) -> FinalizeState:
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[],
        run_title=False,
        user_message_content="",
        reserved_tokens=0,
        max_output_tokens=0,
        money=money,
    )
    return FinalizeState(
        deps=MagicMock(),
        settings=Settings(),
        ctx=ctx,
        raw=text,
        text=text,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=cancelled,
        assistant_parts=[text],
        should_cancel=None,
    )


def _turn() -> MoneyTurn:
    request = MoneyRequest(product("mortgage"), {"amount": 300000, "rate": 1}, "USD")
    return MoneyTurn(request, work(request, None), "block", average(), None)


async def test_a_money_reply_gets_the_note_then_the_card() -> None:
    state = _state("About $964.92 a month.", _turn())
    text = await attach_money_card(state)
    assert text.startswith("About $964.92 a month.\n\n**Note:** 1% is not a realistic")
    assert text.index("**Note:**") < text.index("```calculator\n")
    assert state.committed == text


async def test_a_calculator_the_model_wrote_is_never_kept() -> None:
    assert await attach_money_card(_state(f"Here.\n\n{_FORGED}", None)) == "Here."
    kept = await attach_money_card(_state(f"Here.\n\n{_FORGED}", _turn()))
    assert kept.count("```calculator") == 1 and '"product":"loan","title_key"' in kept


async def test_a_stopped_money_reply_adds_nothing() -> None:
    assert await attach_money_card(_state("About", _turn(), cancelled=True)) == "About"


async def test_other_replies_pass_through() -> None:
    assert await attach_money_card(_state("Hello there.", None)) == "Hello there."
