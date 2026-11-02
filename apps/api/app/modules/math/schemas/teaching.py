"""Typed teaching pictures. The client draws these; it does not recompute them."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TEACHING_TYPES = frozenset(
    {
        "place_value",
        "number_bond",
        "ten_frame",
        "array",
        "number_line_move",
        "fraction_bar",
        "fraction_line",
        "decimal_compare",
        "rounding",
        "polynomial_division",
        "unit_circle",
        "box_plot",
        "frequency_table",
        "stem_leaf",
        "histogram",
        "scatter",
        "probability_tree",
        "transformation",
        "counting",
    }
)


class PlaceColumn(BaseModel):
    place: str
    digit: int = Field(ge=0, le=9)
    value: str


class PlaceValueSpec(BaseModel):
    type: Literal["place_value"] = "place_value"
    number: str
    columns: list[PlaceColumn] = Field(min_length=1, max_length=12)
    expanded: str
    show_blocks: bool = False
    hundreds: int = Field(default=0, ge=0, le=9)
    tens: int = Field(default=0, ge=0, le=9)
    ones: int = Field(default=0, ge=0, le=9)
    answer: str
    speech: str


class NumberBondSpec(BaseModel):
    type: Literal["number_bond"] = "number_bond"
    whole: int = Field(ge=0, le=20)
    left: int = Field(ge=0, le=20)
    right: int = Field(ge=0, le=20)
    answer: str
    speech: str

    @model_validator(mode="after")
    def parts_make_the_whole(self) -> NumberBondSpec:
        if self.left + self.right != self.whole:
            raise ValueError("number-bond parts must add up to the whole")
        return self


class TenFrameSpec(BaseModel):
    type: Literal["ten_frame"] = "ten_frame"
    first: int = Field(ge=0, le=9)
    second: int = Field(ge=0, le=9)
    make_ten: bool
    fill: int = Field(ge=0, le=9)
    leftover: int = Field(ge=0, le=9)
    total: int = Field(ge=0, le=18)
    answer: str
    speech: str

    @model_validator(mode="after")
    def frame_accounts_for_both_addends(self) -> TenFrameSpec:
        if self.fill + self.leftover != self.second or self.first + self.second != self.total:
            raise ValueError("ten frame must use both addends")
        if self.make_ten and self.first + self.fill != 10:
            raise ValueError("make-ten fill must complete a ten")
        return self


class ArraySpec(BaseModel):
    type: Literal["array"] = "array"
    rows: int = Field(ge=1, le=10)
    columns: int = Field(ge=1, le=10)
    product: int = Field(ge=1, le=100)
    answer: str
    speech: str

    @model_validator(mode="after")
    def product_matches_the_grid(self) -> ArraySpec:
        if self.rows * self.columns != self.product:
            raise ValueError("array product must equal rows times columns")
        return self


class NumberLineMoveSpec(BaseModel):
    type: Literal["number_line_move"] = "number_line_move"
    start: int = Field(ge=-30, le=30)
    change: int = Field(ge=-30, le=30)
    end: int = Field(ge=-30, le=30)
    low: int
    high: int
    answer: str
    speech: str

    @model_validator(mode="after")
    def move_lands_on_the_end(self) -> NumberLineMoveSpec:
        if self.start + self.change != self.end or self.low > self.start or self.high < self.end:
            raise ValueError("number-line move must land inside its window")
        if self.low > self.end or self.high < self.start:
            raise ValueError("number-line window must cover the jump")
        return self


class FractionBarRow(BaseModel):
    label: str
    filled: int = Field(ge=0, le=24)
    slots: int = Field(ge=1, le=12)


class FractionBarSpec(BaseModel):
    type: Literal["fraction_bar"] = "fraction_bar"
    rows: list[FractionBarRow] = Field(min_length=2, max_length=3)
    answer: str
    speech: str


class FractionLineSpec(BaseModel):
    type: Literal["fraction_line"] = "fraction_line"
    numerator: int = Field(ge=0, le=12)
    denominator: int = Field(ge=1, le=12)
    answer: str
    speech: str

    @model_validator(mode="after")
    def mark_sits_on_the_segment(self) -> FractionLineSpec:
        if self.numerator > self.denominator:
            raise ValueError("fraction number line marks a fraction up to one")
        return self


class DecimalCompareSpec(BaseModel):
    type: Literal["decimal_compare"] = "decimal_compare"
    left: str
    right: str
    headers: list[str] = Field(min_length=1, max_length=8)
    left_digits: list[str] = Field(min_length=1, max_length=8)
    right_digits: list[str] = Field(min_length=1, max_length=8)
    relation: Literal["<", ">", "="]
    answer: str
    speech: str

    @model_validator(mode="after")
    def columns_line_up(self) -> DecimalCompareSpec:
        if len(self.headers) != len(self.left_digits) or len(self.headers) != len(
            self.right_digits
        ):
            raise ValueError("decimal columns must line up")
        return self


class RoundingSpec(BaseModel):
    type: Literal["rounding"] = "rounding"
    value: str
    place: str
    place_digit: int = Field(ge=0, le=9)
    follower: int = Field(ge=0, le=9)
    direction: Literal["up", "down"]
    rounded: str
    answer: str
    speech: str


class PolynomialTermStep(BaseModel):
    term: str
    product: str
    remainder: str


class PolynomialDivisionSpec(BaseModel):
    type: Literal["polynomial_division"] = "polynomial_division"
    method: Literal["long", "synthetic"]
    dividend: str
    divisor: str
    quotient: str
    remainder: str
    steps: list[PolynomialTermStep] = Field(default_factory=list, max_length=8)
    synthetic_root: str | None = None
    synthetic_top: list[str] = Field(default_factory=list, max_length=8)
    synthetic_multiply: list[str] = Field(default_factory=list, max_length=8)
    synthetic_bottom: list[str] = Field(default_factory=list, max_length=8)
    answer: str
    speech: str


class UnitCircleSpec(BaseModel):
    type: Literal["unit_circle"] = "unit_circle"
    degrees: int = Field(ge=-360, le=720)
    radians: str
    cosine: str
    sine: str
    tangent: str
    plot_x: float
    plot_y: float
    answer: str
    speech: str


class BoxPlotSpec(BaseModel):
    type: Literal["box_plot"] = "box_plot"
    minimum: str
    q1: str
    median: str
    q3: str
    maximum: str
    answer: str
    speech: str


class FrequencyRow(BaseModel):
    value: str
    count: int = Field(ge=1, le=40)


class FrequencyTableSpec(BaseModel):
    type: Literal["frequency_table"] = "frequency_table"
    rows: list[FrequencyRow] = Field(min_length=1, max_length=20)
    answer: str
    speech: str


class StemLeafRow(BaseModel):
    stem: str
    leaves: str


class StemLeafSpec(BaseModel):
    type: Literal["stem_leaf"] = "stem_leaf"
    rows: list[StemLeafRow] = Field(min_length=1, max_length=10)
    answer: str
    speech: str


class HistogramBin(BaseModel):
    label: str
    count: int = Field(ge=0, le=40)


class HistogramSpec(BaseModel):
    type: Literal["histogram"] = "histogram"
    bins: list[HistogramBin] = Field(min_length=1, max_length=16)
    answer: str
    speech: str


class ScatterPoint(BaseModel):
    x: str
    y: str


class ScatterSpec(BaseModel):
    type: Literal["scatter"] = "scatter"
    points: list[ScatterPoint] = Field(min_length=2, max_length=12)
    answer: str
    speech: str


class ProbabilityBranch(BaseModel):
    label: str
    probability: str
    children: list[ProbabilityBranch] = Field(default_factory=list, max_length=6)


class ProbabilityTreeSpec(BaseModel):
    type: Literal["probability_tree"] = "probability_tree"
    branches: list[ProbabilityBranch] = Field(min_length=2, max_length=6)
    answer: str
    speech: str


class TransformPoint(BaseModel):
    x: str
    y: str


class TransformationSpec(BaseModel):
    type: Literal["transformation"] = "transformation"
    kind: Literal["translation", "reflection", "rotation", "dilation"]
    rule: str
    before: list[TransformPoint] = Field(min_length=1, max_length=4)
    after: list[TransformPoint] = Field(min_length=1, max_length=4)
    answer: str
    speech: str

    @model_validator(mode="after")
    def images_match_the_originals(self) -> TransformationSpec:
        if len(self.before) != len(self.after):
            raise ValueError("each original point needs an image")
        return self


class CountingSpec(BaseModel):
    """Objects to count for a small whole-number fact: 3 apples, take away 3.

    ``first`` and ``second`` are the operands as asked. For multiply they are
    rows and objects per row; for divide, the total and the number of groups.
    """

    type: Literal["counting"] = "counting"
    operation: Literal["add", "subtract", "multiply", "divide"]
    first: int = Field(ge=0, le=30)
    second: int = Field(ge=0, le=10)
    result: int = Field(ge=0, le=30)
    object: str = Field(min_length=1, max_length=4)
    answer: str
    speech: str

    @model_validator(mode="after")
    def picture_matches_the_fact(self) -> CountingSpec:
        first, second, result = self.first, self.second, self.result
        valid = {
            "add": first <= 10 and first + second == result,
            "subtract": first <= 10 and second <= first and first - second == result,
            "multiply": 1 <= first <= 10 and second >= 1 and first * second == result <= 30,
            "divide": second >= 1 and first == second * result,
        }[self.operation]
        if not valid:
            raise ValueError("the counting picture must show the fact it answers")
        return self


TeachingSpec = (
    PlaceValueSpec
    | NumberBondSpec
    | TenFrameSpec
    | ArraySpec
    | NumberLineMoveSpec
    | FractionBarSpec
    | FractionLineSpec
    | DecimalCompareSpec
    | RoundingSpec
    | PolynomialDivisionSpec
    | UnitCircleSpec
    | BoxPlotSpec
    | FrequencyTableSpec
    | StemLeafSpec
    | HistogramSpec
    | ScatterSpec
    | ProbabilityTreeSpec
    | TransformationSpec
    | CountingSpec
)
