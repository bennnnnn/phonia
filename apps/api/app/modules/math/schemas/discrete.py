"""Structured math I/O — validated before SymPy and fence emission."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.math.schemas.operations import CombinatoricsOp, MatrixOp, NumberTheorySolveOp


class StatisticsInput(BaseModel):
    numbers: list[float] = Field(min_length=1, max_length=200)

    @field_validator("numbers")
    @classmethod
    def reject_non_finite(cls, value: list[float]) -> list[float]:
        # nan/inf propagate silently through max-min/fsum and produce a
        # meaningless result; the matcher parses digits so this is mainly a
        # guard against OCR/structured stats carrying a non-finite value.
        for n in value:
            if not math.isfinite(n):
                raise ValueError("statistics values must be finite numbers")
        return value


class StatisticsResult(BaseModel):
    count: int
    numbers: list[float]
    sum: float
    mean: float
    median: float
    # Every value tied for the highest frequency — empty when every value in
    # the set appears exactly once (no meaningful "mode" to report).
    modes: list[float]
    range: float
    variance_population: float
    stdev_population: float
    # Sample variance/stdev use Bessel's correction (n-1) and are undefined
    # for a single data point.
    variance_sample: float | None = None
    stdev_sample: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class CombinatoricsInput(BaseModel):
    operation: CombinatoricsOp
    # Capped at 1000, not just "positive": math.comb/math.perm on an
    # unbounded n (e.g. a chat message asking for "1000000 choose 500000")
    # returns a correct but enormous integer — bounded here to keep the
    # verified block (and the model's reply) a sane size.
    n: int = Field(ge=0, le=1000)
    k: int | None = Field(default=None, ge=0, le=1000)


class CombinatoricsResult(BaseModel):
    operation: CombinatoricsOp
    n: int
    k: int | None
    result: int
    steps: list[str] = Field(default_factory=list)


class NumberTheoryInput(BaseModel):
    operation: NumberTheorySolveOp
    # factorize/is_prime bound to 1e8 specifically to keep sympy.factorint's
    # worst case (a large semiprime) fast — trial division up to sqrt(1e8)
    # is ~10k iterations, not a stall risk. gcd/lcm/mod share the same bound
    # for a single simple schema rather than a second near-identical one.
    a: int = Field(ge=-100_000_000, le=100_000_000)
    b: int | None = Field(default=None, ge=-100_000_000, le=100_000_000)
    # gcd/lcm of three or more numbers ("lcm of 12, 18 and 30"); ``a`` and
    # ``b`` repeat the first two.
    values: list[int] | None = Field(default=None, min_length=3, max_length=10)

    @field_validator("values")
    @classmethod
    def _values_in_range(cls, values: list[int] | None) -> list[int] | None:
        if values is not None and not all(1 <= value <= 100_000_000 for value in values):
            raise ValueError("gcd/lcm values must be whole numbers from 1 to 100000000")
        return values


class NumberTheoryResult(BaseModel):
    operation: NumberTheorySolveOp
    a: int
    b: int | None
    result_int: int | None = None
    result_bool: bool | None = None
    # Prime -> exponent (e.g. 60 -> {2: 2, 3: 1, 5: 1}) — only set for "factorize".
    factors: dict[int, int] | None = None
    steps: list[str] = Field(default_factory=list)


class MatrixInput(BaseModel):
    operation: MatrixOp
    rows: list[list[float]] = Field(min_length=2, max_length=4)
    rows_b: list[list[float]] | None = Field(default=None, min_length=2, max_length=4)

    @field_validator("rows")
    @classmethod
    def rows_bounded(cls, value: list[list[float]]) -> list[list[float]]:
        width = len(value[0])
        if width < 1 or width > 4 or any(len(row) != width for row in value):
            raise ValueError("matrix rows must be rectangular and at most 4 wide")
        return value

    @field_validator("rows_b")
    @classmethod
    def rows_b_bounded(cls, value: list[list[float]] | None) -> list[list[float]] | None:
        if value is None:
            return value
        width = len(value[0])
        if width < 1 or width > 4 or any(len(row) != width for row in value):
            raise ValueError("matrix rows must be rectangular and at most 4 wide")
        return value

    @model_validator(mode="after")
    def square_when_required(self) -> MatrixInput:
        size = len(self.rows)
        if self.operation in {
            "determinant",
            "inverse",
            "eigenvalues",
            "eigenvectors",
            "diagonalize",
        }:
            if any(len(row) != size for row in self.rows):
                raise ValueError("matrix must be square for this operation")
        if self.operation == "multiply":
            if self.rows_b is None:
                raise ValueError("multiply needs a second matrix")
            if len(self.rows[0]) != len(self.rows_b):
                raise ValueError("matrix multiply inner dimensions must agree")
        if self.operation == "add":
            if self.rows_b is None:
                raise ValueError("add needs a second matrix")
            if len(self.rows) != len(self.rows_b) or len(self.rows[0]) != len(self.rows_b[0]):
                raise ValueError("matrix add needs matching shapes")
        return self


class MatrixResult(BaseModel):
    operation: MatrixOp
    determinant: float | None = None
    inverse_latex: str | None = None
    result_latex: str | None = None
    steps: list[str] = Field(default_factory=list)
