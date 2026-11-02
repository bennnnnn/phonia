"""The ``calculator`` fence the server appends to a money reply (docs/money.md)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Format = Literal["money", "percent", "years", "months", "number"]


class Marker(BaseModel):
    """Today's average on the rate slider, with the day it describes and its source."""

    value: float
    label_key: str = "money.average"
    as_of: str
    source: str
    source_url: str | None = None


class Control(BaseModel):
    name: str
    label_key: str
    format: Format
    min: float
    max: float
    step: float = Field(gt=0)
    value: float
    marker: Marker | None = None


class Readout(BaseModel):
    name: str
    label_key: str
    format: Format
    tree: dict[str, Any]
    primary: bool = False
    # Shown when the tree gives no number: a payment that never clears the card.
    never_key: str | None = None


class CalculatorSpec(BaseModel):
    v: Literal[1] = 1
    product: Literal["loan", "card_payoff", "savings"]
    title_key: str
    # ISO 4217, or "" when the request named none (the phone shows its own currency).
    currency: str
    controls: list[Control] = Field(min_length=1)
    readouts: list[Readout] = Field(min_length=1)
