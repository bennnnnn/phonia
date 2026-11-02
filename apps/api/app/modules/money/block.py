"""The money block the model reads before the user's message: numbers to copy, never redo.

The model writes the answer's words; the app worked the numbers and adds the market note
and the calculator card under the reply, so the block tells it not to write either. A
follow-up ("what if i only do 3 years instead") gets the earlier request worked again with
its change, and is told those are the answer: the free model once redid the change from
the earlier reply's numbers and was off by dollars (live, 2026-10-25).
"""

from __future__ import annotations

from app.modules.money.catalog import Product
from app.modules.money.numbers import day_text, money_text, percent_text
from app.modules.money.rates import MarketRate
from app.modules.money.read import MoneyRequest
from app.modules.money.solve import Worked, rate_name
from app.modules.money.standing import term_name

# Every money block opens with this: the turn's numbers are the app's.
MONEY_HEADER = "Money, worked by the app"
MONEY_REPLY_RULES = (
    "Answer in a few short lines: the main result first, then the other results, and say "
    "which values were assumed. Copy these numbers exactly; never recompute them. Under "
    "your reply the app adds a calculator card with sliders and, when it found one, a "
    "note with today's average rate: do not write your own calculator, scenario table, "
    "chart or market-rate note, and do not state any average or market rate yourself."
)
# A lesson's money problem (``worked_problem``): the working a student hands in.
MONEY_WORKED_RULES = (
    "This is a worked problem from a lesson: lay the answer out for the student. **Given**: "
    "the values from the question. **Formula**: the standard formula the result comes "
    "from, in LaTeX. **Substitution**: that formula with the given values put in. "
    "**Answer**: the result, in words that answer the question. Copy every number from "
    "Inputs and Results exactly; never work out an intermediate value or a result "
    "yourself. Say which values were assumed. Under your reply the app adds a calculator "
    "card with sliders and, when it found one, a note with today's average rate: do not "
    "write your own calculator, scenario table, chart or market-rate note, and do not "
    "state any average or market rate yourself."
)
MONEY_FOLLOW_UP = (
    "This message changes the user's earlier request: {changes}. The inputs and results "
    "below already include the change and are this turn's answer; never work the change "
    "out yourself or carry numbers over from an earlier reply."
)
# The average stands in for the kind asked: "used car" for the new-car average.
MONEY_STAND_IN = (
    "Today's average {name} is not a {kind} rate: {caveat} Say so in the reply, and "
    "never call it a {kind} rate."
)
# A follow-up whose rate (today's average for its own kind and term) is not the one the
# last reply showed: the change looks like it moved the rate on its own otherwise.
MONEY_RATE_CHANGED = (
    "The rate is {rate}, not the {shown} the last reply used: it is today's average {name} "
    "for this request. Say that the rate changed and why."
)
# A bare amount beside a price, read as the down payment or the loan (``purchase``).
MONEY_GUESSED = (
    "The amount the user gave was taken as the {what} on the {price} price. The app writes "
    "a note saying so under the reply; do not repeat it."
)
# A turn about the chat's loan with no card of its own (``standing``): a header of its own,
# since the turn is no money turn (no card, no note, a sum it asks is still solved).
MONEY_STANDING_HEADER = "Money discussed earlier, worked by the app"
MONEY_STANDING = (
    "The user's earlier {kind} is still being discussed; these are its figures, worked by "
    "the app. If your reply states a payment, interest or total for it, copy them from "
    "here exactly; never compute one yourself. For a term or rate not listed here, say the "
    "calculator card on the earlier reply gives it with its sliders; do not estimate it. "
    "Do not repeat the figures unless the message asks about them."
)
MONEY_RATE_MISSING = (
    "The user gave no interest rate and no current average was found. Ask one short "
    "question for the rate their lender or card quoted; do not guess one."
)
MONEY_RATES_FOUND = (
    "Answer with this rate, its date and its source link, in one or two lines; do not "
    "state any other rate as current."
)
MONEY_RATES_MISSING = (
    "No checked average was found for this. Give a current figure only from search "
    "results in this turn, with its date and source; otherwise say you could not find "
    "today's figure. Never estimate one."
)

_INPUT_WORDS = {
    "amount": "amount",
    "rate": "yearly rate",
    "apr": "APR",
    "years": "term in years",
    "months": "term in months",
    "balance": "balance",
    "payment": "monthly payment",
    "start": "starting amount",
    "deposit": "monthly deposit",
}
# How often savings compound (``per_year``), in the reply's words.
_COMPOUNDING_WORDS = {
    1: "yearly",
    2: "twice a year",
    4: "quarterly",
    12: "monthly",
    52: "weekly",
    365: "daily",
}
_OUTPUT_WORDS = {
    "payment": "monthly payment",
    "interest": "total interest",
    "total": "total paid",
    "months": "months to pay off",
    "balance": "final balance",
    "deposited": "total deposited",
}


def money_block(
    request: MoneyRequest,
    worked: Worked | None,
    average: MarketRate | None,
    *,
    shown_rate: float | None = None,
    worked_problem: bool = False,
) -> str:
    product = request.product
    kind = " ".join(word for word in (request.variant, product.key.replace("_", " ")) if word)
    head = f"{MONEY_HEADER}: {kind}."
    if request.rates_only:
        return "\n".join((head, _rates_line(request, average)))
    if worked is None:
        return "\n".join((head, MONEY_RATE_MISSING))
    lines = [head]
    if request.changed:
        lines.append(MONEY_FOLLOW_UP.format(changes="; ".join(_changes(request, worked))))
    if request.guessed and request.price is not None:
        what = "down payment" if request.guessed == "down" else "loan"
        lines.append(MONEY_GUESSED.format(what=what, price=money_text(request.price)))
    if request.currency:
        lines.append(f"Currency: {request.currency}.")
    lines.append("Inputs: " + "; ".join(_inputs(product, worked)) + ".")
    lines.append("Results: " + "; ".join(_outputs(product, worked)) + ".")
    stand_in = _stand_in(request, average)
    assumed_rate = rate_name(product) in worked.assumed
    if stand_in and assumed_rate:
        lines.append(stand_in)
    rate = worked.values[rate_name(product)]
    if assumed_rate and average and shown_rate is not None and round(shown_rate, 2) != rate:
        lines.append(
            MONEY_RATE_CHANGED.format(
                rate=percent_text(rate), shown=percent_text(shown_rate), name=average.name
            )
        )
    lines.append(MONEY_WORKED_RULES if worked_problem else MONEY_REPLY_RULES)
    return "\n".join(lines)


def _changes(request: MoneyRequest, worked: Worked) -> list[str]:
    """What the follow-up changed, in the block's words ("term in months 36")."""
    product = request.product
    changes = []
    for name in request.changed:
        value = _value_text(name, worked.values[name], product)
        if name == "amount" and request.down is not None and request.price is not None:
            changes.append(
                f"a down payment of {money_text(request.down)} off the price "
                f"{money_text(request.price)}, so the amount borrowed is {value}"
            )
        else:
            changes.append(f"{_INPUT_WORDS.get(name, name)} {value}")
    return changes


def _stand_in(request: MoneyRequest, average: MarketRate | None) -> str:
    if average is None or not average.caveat:
        return ""
    kind = " ".join((request.variant, request.product.key.replace("_", " ")))
    return MONEY_STAND_IN.format(name=average.name, kind=kind, caveat=average.caveat)


def _rates_line(request: MoneyRequest, average: MarketRate | None) -> str:
    if average is None:
        return MONEY_RATES_MISSING
    line = (
        f"Today's average {average.name} in {average.country}: {percent_text(average.value)} "
        f"as of {day_text(average.as_of)}, from {average.source_title} ({average.source_url}). "
        f"{MONEY_RATES_FOUND}"
    )
    stand_in = _stand_in(request, average)
    return f"{line} {stand_in}" if stand_in else line


def _value_text(name: str, value: float, product: Product) -> str:
    item = product.input(name)
    if item is not None and item.format == "percent":
        return percent_text(value)
    if item is not None and item.format in ("years", "months"):
        return f"{value:g}"
    return money_text(value)


def _inputs(product: Product, worked: Worked) -> list[str]:
    parts = []
    for item in product.inputs:
        value = _value_text(item.name, worked.values[item.name], product)
        text = f"{_INPUT_WORDS.get(item.name, item.name)} {value}"
        if item.name in worked.assumed:
            text += " (assumed: the user did not say)"
        parts.append(text)
    if "per_year" in product.settings:
        per_year = worked.settings.get("per_year", product.settings["per_year"])
        times = _COMPOUNDING_WORDS[int(per_year)]
        said = "" if "per_year" in worked.settings else " (assumed: the user did not say)"
        parts.append(f"interest compounded {times}{said}")
    return parts


def _outputs(product: Product, worked: Worked) -> list[str]:
    parts = []
    for item in product.outputs:
        value = worked.outputs.get(item.name)
        words = _OUTPUT_WORDS.get(item.name, item.name)
        if value is None:
            parts.append(f"{words}: never, the payment does not cover the interest")
        elif item.format == "months":
            parts.append(f"{words} {value:.1f}")
        else:
            parts.append(f"{words} {money_text(value)}")
    return parts


def standing_block(
    request: MoneyRequest, worked: Worked, others: dict[float, dict[str, float]]
) -> str:
    """The chat's loan for a turn that talks about it: its figures, and at other terms."""
    product = worked.product
    kind = " ".join(word for word in (request.variant, product.key.replace("_", " ")) if word)
    lines = [f"{MONEY_STANDING_HEADER}: {kind}.", MONEY_STANDING.format(kind=kind)]
    if request.price is not None and request.down is not None:
        lines.append(f"Price {money_text(request.price)}; down payment {money_text(request.down)}.")
    if request.currency:
        lines.append(f"Currency: {request.currency}.")
    lines.append("Inputs: " + "; ".join(_inputs(product, worked)) + ".")
    lines.append("Results: " + "; ".join(_outputs(product, worked)) + ".")
    for term, outputs in others.items():
        at = Worked(product, worked.values, (), dict(outputs), worked.settings)
        words = _INPUT_WORDS.get(term_name(product) or "", "term")
        lines.append(f"With {words} {term:g}: " + "; ".join(_outputs(product, at)) + ".")
    return "\n".join(lines)
