"""Prompt prep for a money turn: which part reads as money, and where its block goes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.readings import begin_turn
from app.modules.chat.turn_prep import money as money_prep
from app.modules.chat.turn_prep.reading import read_turn_message
from app.modules.money.block import MONEY_HEADER
from app.modules.money.service import MoneyTurn
from app.modules.turn_reading.plan import TurnPart, TurnPlan, single_plan
from app.tests import loop_guard

_SENTENCE = "what is my mortgage for 300k dollars house if mr rate is 1 percent"


def _request(text: str, *, image: bool = False, history: tuple[str, ...] = ()) -> Any:
    rows = [
        SimpleNamespace(role=role, content=line)
        for line in history
        for role, line in (("user", line), ("assistant", "About $340 a month."))
    ]
    return SimpleNamespace(content=text, has_image_attachment=image, recent_messages=rows)


def _identity() -> Any:
    return SimpleNamespace(user=None, geo=SimpleNamespace(user_location=None))


async def test_a_money_message_gets_its_turn_and_block(fake_redis: Redis) -> None:
    turn = await money_prep.money_turn(
        _request(_SENTENCE), _identity(), Settings(), fake_redis, single_plan(_SENTENCE)
    )
    assert turn is not None and turn.request.product.key == "mortgage"
    if turn.lookup is not None:
        turn.lookup.cancel()
    prompt = [{"role": "system", "content": "S"}, {"role": "user", "content": _SENTENCE}]
    placed = money_prep.with_money_block(prompt, turn)
    assert placed[1]["role"] == "system" and placed[1]["content"].startswith(MONEY_HEADER)
    assert placed[-1]["content"] == _SENTENCE


async def test_the_money_part_of_a_multi_part_message_is_found(fake_redis: Redis) -> None:
    plan = TurnPlan((TurnPart("tell me a joke"), TurnPart(_SENTENCE)))
    turn = await money_prep.money_turn(
        _request(f"tell me a joke and {_SENTENCE}"), _identity(), Settings(), fake_redis, plan
    )
    assert turn is not None and turn.request.values["amount"] == 300000
    if turn.lookup is not None:
        turn.lookup.cancel()


async def test_no_money_turn_with_a_photo_or_with_money_off(fake_redis: Redis) -> None:
    plan = single_plan(_SENTENCE)
    assert (
        await money_prep.money_turn(
            _request(_SENTENCE, image=True), _identity(), Settings(), fake_redis, plan
        )
        is None
    )
    off = Settings(money_enabled=False)
    assert (
        await money_prep.money_turn(_request(_SENTENCE), _identity(), off, fake_redis, plan) is None
    )


def test_no_turn_no_block() -> None:
    prompt = [{"role": "user", "content": "hi"}]
    assert money_prep.with_money_block(prompt, None) == prompt


_CAR = "car loan 14000 with 3000 down at 7.16% for 5 years, what's the monthly payment"
_WHAT_IF = "hmm what if i only do 3 years instead"


async def _money_turn(request: Any, plan: TurnPlan, redis: Redis) -> MoneyTurn | None:
    """The money turn as a real turn runs it: its message (and the earlier lines' plans)
    read in the pool first, then the money prep."""
    settings = Settings()
    begin_turn()
    await read_turn_message(request.content, request.recent_messages, settings)
    turn = await money_prep.money_turn(request, _identity(), settings, redis, plan)
    if turn is not None:
        for task in (turn.lookup, turn.stand_in):
            if task is not None:
                task.cancel()
    return turn


async def test_a_what_if_reads_the_users_earlier_lines(
    fake_redis: Redis, thread_sympy_executor: None
) -> None:
    """Live (2026-10-25): "what if i only do 3 years instead" got no card."""
    turn = await _money_turn(_request(_WHAT_IF, history=(_CAR,)), single_plan(_WHAT_IF), fake_redis)
    assert turn is not None and turn.request.values["months"] == 36
    assert turn.request.changed == ("months",)


async def test_a_regenerated_what_if_skips_its_own_stored_line(
    fake_redis: Redis, thread_sympy_executor: None
) -> None:
    """A regenerate's window ends with the line itself; it is not its own earlier request."""
    request = _request(_WHAT_IF, history=(_CAR,))
    request.recent_messages.append(SimpleNamespace(role="user", content=_WHAT_IF))
    turn = await _money_turn(request, single_plan(_WHAT_IF), fake_redis)
    assert turn is not None and turn.request.values["months"] == 36


async def test_a_what_if_part_of_a_multi_part_message_is_found(
    fake_redis: Redis, thread_sympy_executor: None
) -> None:
    plan = TurnPlan((TurnPart("tell me a joke"), TurnPart("what if i only do 3 years instead")))
    turn = await _money_turn(
        _request(f"tell me a joke and {_WHAT_IF}", history=(_CAR,)), plan, fake_redis
    )
    assert turn is not None and turn.request.values["months"] == 36


async def test_a_what_if_after_the_chat_moved_on_is_no_money_turn(
    fake_redis: Redis, thread_sympy_executor: None
) -> None:
    workout = ("give me a 4 day workout plan with 4 sets of each exercise",)
    line = "what if i only do 3 sets instead"
    assert await _money_turn(_request(line, history=workout), single_plan(line), fake_redis) is None
    # The car loan still stands past the lasagna: its figures, but no worked change or card.
    history = (_CAR, "how do I make lasagna?")
    turn = await _money_turn(_request(_WHAT_IF, history=history), single_plan(_WHAT_IF), fake_redis)
    assert turn is not None and turn.standing


async def test_an_earlier_multi_part_line_is_read_in_its_parts(
    fake_redis: Redis, thread_sympy_executor: None
) -> None:
    """Review (2026-10-25): "what about 3 years" after this line was worked on a loan of 9."""
    earlier = "set a reminder for 9 tomorrow and what's the payment on a 20000 car loan at 6%"
    line = "what about 3 years"
    turn = await _money_turn(_request(line, history=(earlier,)), single_plan(line), fake_redis)
    assert turn is not None
    assert turn.request.values == {"amount": 20000, "rate": 6, "months": 36}


async def test_earlier_lines_are_never_planned_on_the_loop(
    fake_redis: Redis, thread_sympy_executor: None
) -> None:
    """Golden rule 7. Review (2026-10-25): with more user lines in the window than the pool
    plans, or one with no text (a photo alone), the earlier lines were planned on the loop on
    every money turn. A line the pool did not plan now ends the money run instead."""
    user = lambda text: SimpleNamespace(role="user", content=text)  # noqa: E731
    reply = SimpleNamespace(role="assistant", content="ok")
    many = [user("a"), user("b"), user("c"), user("d"), user("e"), user(_CAR), reply]
    turn = await _money_turn(
        SimpleNamespace(content=_WHAT_IF, has_image_attachment=False, recent_messages=many),
        single_plan(_WHAT_IF),
        fake_redis,
    )
    assert turn is not None and turn.request.values["months"] == 36
    photo_only = [user(_CAR), reply, user(""), reply]
    turn = await _money_turn(
        SimpleNamespace(content=_WHAT_IF, has_image_attachment=False, recent_messages=photo_only),
        single_plan(_WHAT_IF),
        fake_redis,
    )
    # No worked change past the unplanned line; the loan's figures only (``standing``).
    assert turn is not None and turn.standing
    assert loop_guard.found == []


async def test_a_reminder_line_after_a_loan_gets_no_block(
    fake_redis: Redis, thread_sympy_executor: None
) -> None:
    line = "my car payment is due friday, remind me"
    turn = await _money_turn(_request(line, history=(_CAR,)), single_plan(line), fake_redis)
    assert turn is None
