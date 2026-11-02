"""Validated written-arithmetic traces rendered by clients without solving."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AdditionColumn(BaseModel):
    position: int = Field(ge=0)
    place: str
    addends: list[int] = Field(min_length=2, max_length=6)
    carry_in: int = Field(ge=0, le=9)
    result_digit: int = Field(ge=0, le=9)
    carry_out: int = Field(ge=0, le=9)


class SubtractionColumn(BaseModel):
    position: int = Field(ge=0)
    place: str
    top_digit: int = Field(ge=0, le=9)
    bottom_digit: int = Field(ge=0, le=9)
    working_top: int = Field(ge=0, le=19)
    result_digit: int = Field(ge=0, le=9)
    regrouped_from: list[str] = Field(default_factory=list)


class MultiplicationColumn(BaseModel):
    position: int = Field(ge=0)
    place: str
    multiplicand_digit: int = Field(ge=0, le=9)
    carry_in: int = Field(ge=0)
    result_digit: int = Field(ge=0, le=9)
    carry_out: int = Field(ge=0)


class PartialProduct(BaseModel):
    position: int = Field(ge=0)
    place: str
    multiplier_digit: int = Field(ge=0, le=9)
    unshifted_product: str
    shifted_product: str
    columns: list[MultiplicationColumn] = Field(min_length=1)


class LongDivisionStep(BaseModel):
    index: int = Field(ge=0)
    column_end: int = Field(ge=0)
    partial_dividend: str
    quotient_digit: int = Field(ge=0, le=9)
    product: str
    remainder: str
    bring_down: int | None = Field(default=None, ge=0, le=9)
    next_partial: str | None = None


class ArithmeticWorkSpec(BaseModel):
    """Exact procedure data for one primary-school written algorithm."""

    type: Literal["arithmetic"] = "arithmetic"
    operation: Literal["addition", "subtraction", "multiplication", "division"]
    operator: Literal["+", "\u2212", "\u00d7", "\u00f7"]
    expression: str
    operands: list[str] = Field(min_length=2, max_length=6)
    working_operands: list[str] = Field(min_length=2, max_length=6)
    answer: str
    decimal_places: int = Field(default=0, ge=0, le=12)
    addition_columns: list[AdditionColumn] = Field(default_factory=list)
    subtraction_columns: list[SubtractionColumn] = Field(default_factory=list)
    regrouped_minuend: list[str] = Field(default_factory=list)
    partial_products: list[PartialProduct] = Field(default_factory=list)
    quotient: str | None = None
    remainder: str | None = None
    answer_mode: Literal["exact", "remainder", "fraction", "decimal", "round_up", "discard"] = (
        "exact"
    )
    division_steps: list[LongDivisionStep] = Field(default_factory=list)
    # A bounded 64-digit long-division trace can gain six places while
    # clearing divisor decimals, plus setup and rounding notes.
    explanations: list[str] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def trace_matches_operation(self) -> ArithmeticWorkSpec:
        traces = {
            "addition": bool(self.addition_columns),
            "subtraction": bool(self.subtraction_columns),
            "multiplication": bool(self.partial_products),
            "division": bool(self.division_steps) and self.quotient is not None,
        }
        if not traces[self.operation]:
            raise ValueError(f"missing {self.operation} procedure data")
        if sum(traces.values()) != 1:
            raise ValueError("written arithmetic must contain exactly one procedure trace")
        return self
