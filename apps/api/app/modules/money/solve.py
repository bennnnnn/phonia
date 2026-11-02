"""The numbers for the asked values, from the catalog's own formulas.

A value the user left out comes from the product's default (a 30-year mortgage) or,
for the rate, from today's average; each one is named in ``assumed`` so the reply says
it. A value that is still missing (a card payoff with no monthly payment) means there
is nothing to work, and the model asks for it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.modules.money.catalog import Product
from app.modules.money.read import MoneyRequest
from app.services.law_binding.expression import Notation, evaluate

# Money formulas name no constants; numbers print plainly where a formula is typeset.
NOTATION = Notation(constants={}, number=lambda value: f"{value:g}")


@dataclass(frozen=True)
class Worked:
    """Every input (asked or assumed) and every output at those inputs."""

    product: Product
    values: dict[str, float]
    # Inputs the user did not give, in catalog order: a default term, today's average rate.
    assumed: tuple[str, ...]
    # None is no number: a card payment that never clears the balance.
    outputs: dict[str, float | None]
    # The request's settings (``Product.settings``): how often savings compound.
    settings: dict[str, float] = field(default_factory=dict)

    def expressions(self) -> dict[str, str]:
        """Each output's formula with the settings written in, as the card sends it."""
        return {item.name: item.expression for item in self.product.outputs_at(self.settings)}


def rate_name(product: Product) -> str:
    return "apr" if product.family == "card_payoff" else "rate"


def work(request: MoneyRequest, average: float | None) -> Worked | None:
    """The request worked through, or None when an input is still missing."""
    product = request.product
    values = dict(request.values)
    assumed: list[str] = []
    for name, value in product.defaults.items():
        if name not in values:
            values[name] = value
            assumed.append(name)
    rate = rate_name(product)
    if rate not in values:
        if average is None:
            return None
        values[rate] = round(average, 2)
        assumed.append(rate)
    if any(item.name not in values for item in product.inputs):
        return None
    settings = dict(request.settings)
    outputs = {
        item.name: output_value(item.expression, values) for item in product.outputs_at(settings)
    }
    ordered = tuple(item.name for item in product.inputs if item.name in assumed)
    return Worked(product, values, ordered, outputs, settings)


def output_value(expression: str, values: dict[str, float]) -> float | None:
    """The formula's value, or None where it gives no finite number."""
    try:
        value = evaluate(expression, values, NOTATION)
    except (ValueError, OverflowError, ZeroDivisionError):
        return None
    return value if math.isfinite(value) else None
