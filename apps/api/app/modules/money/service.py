"""A money turn from message to card: read, look up today's average, work, write.

``prepare_money_turn`` runs while the prompt is built. It reads the request (or the
change a follow-up makes to the chat's last one, ``follow_up``, or an amount and a rate
for what the user's line before says they are buying, ``purchase``) and starts the
average-rate lookup at once. The lookup is awaited before the prompt only when the
numbers need it (the user gave no rate, or asked what rates are); otherwise it runs while
the reply streams, and ``finish_money_reply`` collects it to write the note and the
card's marker. A lookup that is late or finds nothing leaves both out; the turn never
waits on it past a few seconds.

A kind of product priced apart (a used car) also starts the product's own lookup, which
stands in, said as such, when the kind's finds nothing in time: the first live used-car
ask (2026-10-25) found no used-car average and got no numbers, where main had worked it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace

from redis.asyncio import Redis

from app.core.background_tasks import create_background_task
from app.core.config import Settings
from app.models.orm import User
from app.modules.money.agreement import card_figures
from app.modules.money.block import money_block, standing_block
from app.modules.money.currencies import country_for, currency_for
from app.modules.money.fence import calculator_fence, card_values
from app.modules.money.follow_up import (
    as_parts,
    follow_up_request,
    standing_request,
    switches_product,
)
from app.modules.money.note import market_note, reading_note
from app.modules.money.purchase import purchase_request
from app.modules.money.rates import MarketRate, current_average
from app.modules.money.read import MoneyRequest, read_money_request
from app.modules.money.solve import Worked, rate_name, work
from app.modules.money.standing import COMMON_TERMS, about_the_loan, figures
from app.modules.money.worked_problem import lays_out_working

logger = logging.getLogger(__name__)

# Waited before the prompt only when the numbers need the average.
_PROMPT_WAIT_SECONDS = 5.0
# Waited after the reply streamed; the lookup started with the turn, so it is usually done.
_FINISH_WAIT_SECONDS = 3.0
# A stand-in that finished while the kind's lookup ran out its time is still taken.
_LAST_LOOK_SECONDS = 0.05


@dataclass
class MoneyTurn:
    """What a money turn carries from its prompt to its finalize."""

    request: MoneyRequest
    worked: Worked | None
    # Read before the last user message: numbers to copy, and what the app adds.
    block: str
    average: MarketRate | None
    lookup: asyncio.Task[MarketRate | None] | None
    # The product's own average, started beside a variant's (``Variant.stand_in``).
    stand_in: asyncio.Task[MarketRate | None] | None = None
    # A turn about the chat's earlier loan (``standing``): its figures for the model, never
    # a card, a note or a money turn's routing.
    standing: bool = False
    # One part of a multi-part reply: the reply's other answers are never replaced.
    multi: bool = False


async def prepare_money_turn(
    text: str,
    settings: Settings,
    redis: Redis | None,
    *,
    user: User | None,
    location: str | None,
    earlier: Sequence[str | Sequence[str]] = (),
    last_reply: str = "",
) -> MoneyTurn | None:
    """The money turn ``text`` asks for, or None when it is not one.

    ``earlier`` is the user's lines before it, oldest first, each as its turn's parts:
    "what if 3 years instead" is the last request there with its term changed.
    ``last_reply`` is the reply before it, whose card shows the rate a follow-up is told
    about when its own rate differs.
    """
    if not settings.money_enabled:
        return None
    before = as_parts(earlier[-1]) if earlier else ()
    request = (
        follow_up_request(text, earlier)
        or read_money_request(text)
        or purchase_request(text, before)
    )
    if request is None:
        return None
    # The card and the prompt use one currency: the one named, else the user's place's.
    request = replace(request, currency=currency_for(request.currency, location))
    product = request.product
    # A follow-up's average is read again for its own kind and term.
    term = request.values.get("years", request.values.get("months"))
    if term is None:
        term = product.defaults.get("years", product.defaults.get("months"))
    lookup = stand_in = None
    country = country_for(request.currency, location)
    if product.rate_lookup(request.variant) is not None:
        lookup = create_background_task(
            current_average(
                product, term, country, settings, redis, user=user, variant=request.variant
            ),
            name="money_average",
        )
    if product.variant(request.variant) is not None and product.lookup is not None:
        stand_in = create_background_task(
            current_average(product, term, country, settings, redis, user=user),
            name="money_average_stand_in",
        )
    average = None
    if lookup is not None and (request.rates_only or rate_name(product) not in request.values):
        average = await _average(request, lookup, stand_in, _PROMPT_WAIT_SECONDS)
    worked = None if request.rates_only else work(request, average.value if average else None)
    shown = card_values(last_reply).get(rate_name(product)) if request.changed else None
    lesson = lays_out_working(text, request, worked)
    block = money_block(request, worked, average, shown_rate=shown, worked_problem=lesson)
    return MoneyTurn(request, worked, block, average, lookup, stand_in)


async def prepare_standing_turn(
    text: str,
    settings: Settings,
    redis: Redis | None,
    *,
    user: User | None,
    location: str | None,
    earlier: Sequence[str | Sequence[str]],
    last_reply: str,
) -> MoneyTurn | None:
    """The chat's earlier loan for a message about it that is no money request itself."""
    if not settings.money_enabled or not about_the_loan(text, last_reply):
        return None
    request = standing_request(earlier)
    # "The interest rate on a savings account" after a mortgage is about another product.
    if request is None or request.rates_only or switches_product(request.product, text):
        return None
    request = replace(request, currency=currency_for(request.currency, location))
    product = request.product
    average = None
    lookup = product.rate_lookup(request.variant)
    if rate_name(product) not in request.values and lookup is not None:
        term = request.values.get("years", request.values.get("months"))
        if term is None:
            term = product.defaults.get("years", product.defaults.get("months"))
        country = country_for(request.currency, location)
        task = create_background_task(
            current_average(
                product, term, country, settings, redis, user=user, variant=request.variant
            ),
            name="money_average_standing",
        )
        average = await _collect(task, _PROMPT_WAIT_SECONDS)
    worked = work(request, average.value if average else None)
    if worked is None:
        return None
    grid = figures(worked)
    own = worked.values.get(grid.term_name) if grid else None
    others = {
        term: grid.by_term[term]
        for term in COMMON_TERMS.get(product.key, ())
        if grid is not None and term != own and term in grid.by_term
    }
    block = standing_block(request, worked, others)
    return MoneyTurn(request, worked, block, None, None, standing=True)


async def finish_money_reply(
    turn: MoneyTurn, text: str, settings: Settings, *, english: bool = True
) -> str:
    """The reply with the market note and the calculator card under it.

    A reply whose stated payment is not the card's gets the card's figures in a line, at the
    top when it worked another loan, else above the note (``agreement``), when the chat is
    in English (the server writes English) and the reply answers this request alone. The
    model's words are never changed."""
    if turn.worked is None:
        return text
    if turn.standing:
        return text
    figures = card_figures(text, turn.request, turn.worked) if english and not turn.multi else None
    if figures is not None and figures.on_top:
        text = f"{figures.line}\n\n{text.lstrip()}"
    figures_line = figures.line if figures is not None and not figures.on_top else None
    average = turn.average
    if average is None and turn.lookup is not None:
        average = await _average(turn.request, turn.lookup, turn.stand_in, _FINISH_WAIT_SECONDS)
    pieces = [text.rstrip(), figures_line or "", reading_note(turn.request, text) or ""]
    note = market_note(turn.worked, average, settings.money_unrealistic_ratio)
    if note:
        pieces.append(note)
    card = calculator_fence(turn.worked, average, turn.request.currency)
    if card:
        pieces.append(card)
    return "\n\n".join(piece for piece in pieces if piece)


async def _average(
    request: MoneyRequest,
    lookup: asyncio.Task[MarketRate | None],
    stand_in: asyncio.Task[MarketRate | None] | None,
    seconds: float,
) -> MarketRate | None:
    """The kind's average within ``seconds``, else the product's own, said as standing in."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    found = await _collect(lookup, seconds)
    variant = request.product.variant(request.variant)
    if found is not None or stand_in is None or variant is None:
        return found
    plain = await _collect(stand_in, max(deadline - loop.time(), _LAST_LOOK_SECONDS))
    return replace(plain, caveat=variant.stand_in) if plain is not None else None


async def _collect(lookup: asyncio.Task[MarketRate | None], seconds: float) -> MarketRate | None:
    """The lookup's answer within ``seconds``; a late one keeps running to fill the cache."""
    try:
        return await asyncio.wait_for(asyncio.shield(lookup), timeout=seconds)
    except TimeoutError:
        return None
    except Exception:
        logger.info("money average lookup failed", exc_info=True)
        return None
