"""A money turn from message to reply: when it waits for the average, and what it adds."""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import Settings
from app.modules.money import service
from app.modules.money.rates import MarketRate
from app.tests.modules.money.money_support import average

_SENTENCE = "what is my mortgage for 300k dollars house if mr rate is 1 percent"


def _lookup(monkeypatch, found: MarketRate | None, *, delay: float = 0.0) -> list[tuple]:
    calls: list[tuple] = []

    async def current_average(product, term, country, settings, redis, **_: Any):
        calls.append((product.key, term, country))
        await asyncio.sleep(delay)
        return found

    monkeypatch.setattr(service, "current_average", current_average)
    return calls


async def test_a_rate_given_does_not_wait_and_the_reply_gets_note_and_card(monkeypatch) -> None:
    calls = _lookup(monkeypatch, average(), delay=0.05)
    settings = Settings()
    turn = await service.prepare_money_turn(_SENTENCE, settings, None, user=None, location=None)
    assert turn is not None and turn.average is None and turn.worked is not None
    await asyncio.sleep(0)  # the lookup started with the turn, without being waited on
    assert calls == [("mortgage", 30, "the United States")]
    reply = await service.finish_money_reply(turn, "About $964.92 a month.", settings)
    assert reply.startswith("About $964.92 a month.\n\n**Note:** 1% is not a realistic")
    assert reply.rstrip().endswith("```") and "```calculator\n" in reply


async def test_no_rate_waits_for_the_average_and_uses_it(monkeypatch) -> None:
    _lookup(monkeypatch, average())
    turn = await service.prepare_money_turn(
        "monthly payment on a 250000 mortgage", Settings(), None, user=None, location=None
    )
    assert turn is not None and turn.worked is not None
    assert turn.worked.values["rate"] == 6.27 and "rate" in turn.worked.assumed


async def test_no_average_means_no_note_and_no_marker(monkeypatch) -> None:
    _lookup(monkeypatch, None)
    settings = Settings()
    turn = await service.prepare_money_turn(_SENTENCE, settings, None, user=None, location=None)
    assert turn is not None
    reply = await service.finish_money_reply(turn, "About $964.92 a month.", settings)
    assert "**Note:**" not in reply and '"marker"' not in reply and "```calculator" in reply


async def test_the_country_follows_the_currency(monkeypatch) -> None:
    calls = _lookup(monkeypatch, None)
    await service.prepare_money_turn(
        "mortgage of 2 million birr at 18% for 20 years", Settings(), None, user=None, location=None
    )
    await asyncio.sleep(0)
    assert calls == [("mortgage", 20, "Ethiopia")]


async def test_a_card_with_no_currency_named_uses_the_saved_place(monkeypatch) -> None:
    """ "I owe 5000 on my card" names no currency: the card is not left without one."""
    _lookup(monkeypatch, None)
    text = "I owe 5000 on my credit card at 22% APR and pay 200 a month"
    settings = Settings()
    for location, currency in ((None, "USD"), ("Addis Ababa, Ethiopia", "ETB")):
        turn = await service.prepare_money_turn(text, settings, None, user=None, location=location)
        assert turn is not None and turn.request.currency == currency
        assert f"Currency: {currency}." in turn.block
        reply = await service.finish_money_reply(turn, "About 34 months.", settings)
        assert f'"currency":"{currency}"' in reply


async def test_a_late_average_is_left_out(monkeypatch) -> None:
    _lookup(monkeypatch, average(), delay=10)
    monkeypatch.setattr(service, "_FINISH_WAIT_SECONDS", 0.01)
    settings = Settings()
    turn = await service.prepare_money_turn(_SENTENCE, settings, None, user=None, location=None)
    assert turn is not None
    reply = await service.finish_money_reply(turn, "About $964.92 a month.", settings)
    assert "**Note:**" not in reply
    assert turn.lookup is not None
    turn.lookup.cancel()


async def test_money_off_reads_nothing(monkeypatch) -> None:
    calls = _lookup(monkeypatch, None)
    settings = Settings(money_enabled=False)
    assert (
        await service.prepare_money_turn(_SENTENCE, settings, None, user=None, location=None)
        is None
    )
    assert calls == []


_USED = (
    "i'm thinking of buying a used car for 14000, i can put 3000 down. what would my monthly "
    "payment be over 5 years?"
)


def _lookup_kinds(
    monkeypatch, found: dict[str, MarketRate | None], delay: dict[str, float] | None = None
) -> list[tuple]:
    """Each kind's lookup ("used", or "" for the product's own) answers from ``found``."""
    calls: list[tuple] = []

    async def current_average(product, term, country, settings, redis, **kwargs: Any):
        variant = kwargs.get("variant", "")
        calls.append((product.key, variant, term))
        await asyncio.sleep((delay or {}).get(variant, 0.0))
        return found.get(variant)

    monkeypatch.setattr(service, "current_average", current_average)
    return calls


_NEW_CAR = average(7.16, "60-month new car loan rate")
_STAND_IN = "No used-car average was found; used-car loans usually cost more."


async def test_a_used_car_looks_up_the_used_car_average(monkeypatch) -> None:
    """Live (2026-10-25): the used car was worked at the new-car average."""
    calls = _lookup_kinds(monkeypatch, {"used": average(11.2, "used car loan rate"), "": _NEW_CAR})
    turn = await service.prepare_money_turn(_USED, Settings(), None, user=None, location=None)
    assert turn is not None and turn.worked is not None
    # The product's own lookup starts beside it, in case it finds nothing.
    assert calls == [("car", "used", 60), ("car", "", 60)]
    assert turn.worked.values["rate"] == 11.2
    assert turn.block.startswith("Money, worked by the app: used car.")
    reply = await service.finish_money_reply(turn, "About $240 a month.", Settings())
    assert "today's average used car loan rate" in reply and _STAND_IN not in reply


async def test_no_used_average_lets_the_new_car_one_stand_in_said_as_such(monkeypatch) -> None:
    """Live (2026-10-25): the used lookup found nothing and the ask got no numbers at all;
    main had worked it at the new-car average. That average stands in, and says so."""
    _lookup_kinds(monkeypatch, {"used": None, "": _NEW_CAR})
    turn = await service.prepare_money_turn(_USED, Settings(), None, user=None, location=None)
    assert turn is not None and turn.worked is not None
    assert (
        turn.worked.values["rate"] == 7.16
        and round(turn.worked.outputs["payment"] or 0, 2) == 218.64
    )
    assert "Today's average 60-month new car loan rate is not a used car rate" in turn.block
    assert "never call it a used car rate" in turn.block
    reply = await service.finish_money_reply(turn, "About $218.64 a month.", Settings())
    assert "today's average 60-month new car loan rate" in reply and _STAND_IN in reply
    assert "used car loan rate" not in reply


async def test_a_slow_used_lookup_lets_the_stand_in_answer(monkeypatch) -> None:
    _lookup_kinds(
        monkeypatch, {"used": average(11.2, "used car loan rate"), "": _NEW_CAR}, {"used": 10}
    )
    monkeypatch.setattr(service, "_PROMPT_WAIT_SECONDS", 0.05)
    turn = await service.prepare_money_turn(_USED, Settings(), None, user=None, location=None)
    assert turn is not None and turn.average is not None
    assert turn.average.value == 7.16 and turn.average.caveat == _STAND_IN
    assert turn.lookup is not None
    turn.lookup.cancel()


async def test_a_given_rate_is_not_called_unrealistic_beside_a_stand_in(monkeypatch) -> None:
    """16 % is more than twice the new-car average, and an ordinary used-car rate."""
    _lookup_kinds(monkeypatch, {"used": None, "": average(7.0, "60-month new car loan rate")})
    turn = await service.prepare_money_turn(
        "buying a used car, car loan of 11000 at 16% for 60 months",
        Settings(),
        None,
        user=None,
        location=None,
    )
    assert turn is not None
    reply = await service.finish_money_reply(turn, "About $267 a month.", Settings())
    assert "for reference" in reply and _STAND_IN in reply and "not a realistic" not in reply


async def test_a_used_rates_question_says_the_average_stands_in(monkeypatch) -> None:
    _lookup_kinds(monkeypatch, {"used": None, "": _NEW_CAR})
    turn = await service.prepare_money_turn(
        "current car loan rates for buying a used car", Settings(), None, user=None, location=None
    )
    assert turn is not None and turn.request.rates_only
    assert "7.16% as of Oct 16, 2026" in turn.block and "not a used car rate" in turn.block


async def test_a_new_car_starts_one_lookup(monkeypatch) -> None:
    calls = _lookup_kinds(monkeypatch, {"": _NEW_CAR})
    text = "car loan 20000 at 7% for 5 years, what's the monthly payment"
    turn = await service.prepare_money_turn(text, Settings(), None, user=None, location=None)
    assert turn is not None and turn.stand_in is None
    await asyncio.sleep(0)
    assert calls == [("car", "", 60)]


async def test_a_what_if_after_a_money_reply_is_worked_by_the_server(monkeypatch) -> None:
    """Live (2026-10-25): the free model said $340.58 and $1,260.88 for this; the loan is
    11 000 at 7.16 % over 36 months: $340.45 a month, $1,256.32 interest."""
    calls = _lookup_kinds(monkeypatch, {"used": average(7.16, "used car loan rate")})
    turn = await service.prepare_money_turn(
        "hmm what if i only do 3 years instead",
        Settings(),
        None,
        user=None,
        location=None,
        earlier=[_USED],
    )
    assert turn is not None and turn.worked is not None
    # The average is read again for the follow-up's own kind and term.
    assert calls == [("car", "used", 36), ("car", "", 36)]
    assert turn.worked.values["months"] == 36 and turn.worked.values["rate"] == 7.16
    assert round(turn.worked.outputs["payment"] or 0, 2) == 340.45
    assert round(turn.worked.outputs["interest"] or 0, 2) == 1256.32
    reply = await service.finish_money_reply(turn, "About $340.45 a month.", Settings())
    assert "```calculator\n" in reply and '"value":36' in reply


async def test_a_what_if_with_no_money_before_it_is_no_money_turn(monkeypatch) -> None:
    calls = _lookup_kinds(monkeypatch, {})
    workout = ["give me a 4 day workout plan with 4 sets of each exercise"]
    for line, earlier in (
        ("what if i only do 3 sets instead", workout),
        ("3 years", []),
        ("what if it was 3 years ago", [_USED]),
    ):
        assert (
            await service.prepare_money_turn(
                line, Settings(), None, user=None, location=None, earlier=earlier
            )
            is None
        )
    assert calls == []


async def test_a_follow_up_says_when_its_rate_is_not_the_last_replys(monkeypatch) -> None:
    """Review (2026-10-25): the first ask took the new-car stand-in (6.9 %); by the follow-up
    the used-car average (11.5 %) had come in, and the block named only the term change."""
    used = average(11.5, "used car loan rate")
    _lookup_kinds(monkeypatch, {"used": None, "": average(6.9, "60-month new car loan rate")})
    first = await service.prepare_money_turn(_USED, Settings(), None, user=None, location=None)
    assert first is not None
    reply = await service.finish_money_reply(first, "About $217 a month.", Settings())
    _lookup_kinds(monkeypatch, {"used": used, "": average(6.9, "36-month new car loan rate")})
    turn = await service.prepare_money_turn(
        "hmm what if i only do 3 years instead",
        Settings(),
        None,
        user=None,
        location=None,
        earlier=[_USED],
        last_reply=reply,
    )
    assert turn is not None and turn.worked is not None and turn.worked.values["rate"] == 11.5
    assert "The rate is 11.5%, not the 6.9% the last reply used" in turn.block
    same = await service.prepare_money_turn(
        "and over 4 years?",
        Settings(),
        None,
        user=None,
        location=None,
        earlier=[_USED, "hmm what if i only do 3 years instead"],
        last_reply=await service.finish_money_reply(turn, "About $362 a month.", Settings()),
    )
    assert same is not None and "not the" not in same.block
