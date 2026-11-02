"""Structured math I/O — validated before SymPy and fence emission."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class EquationInput(BaseModel):
    lhs: str = Field(min_length=1, max_length=256)
    rhs: str = Field(min_length=1, max_length=256)
    variables: list[str] = Field(default_factory=lambda: ["x"], min_length=1, max_length=4)
    # School answers are real. Non-real roots are kept only when asked for, or
    # when the equation has no real root at all (``x^2 + 1 = 0``).
    complex_roots: bool = False


class SystemOfEquationsInput(BaseModel):
    # Each entry is one equation's (lhs, rhs) pair — bounded the same as
    # EquationInput's individual lhs/rhs fields. 2-4 equations: fewer isn't
    # a system, more isn't realistically something a chat turn hand-solves.
    equations: list[tuple[str, str]] = Field(min_length=2, max_length=4)
    variables: list[str] = Field(default_factory=lambda: ["x", "y"], min_length=1, max_length=4)

    @field_validator("equations")
    @classmethod
    def equation_sides_bounded(cls, value: list[tuple[str, str]]) -> list[tuple[str, str]]:
        for lhs, rhs in value:
            if not lhs.strip() or not rhs.strip() or len(lhs) > 256 or len(rhs) > 256:
                raise ValueError("invalid equation side")
        return value


_VALID_INEQUALITY_COMPARATORS = frozenset({"<", ">", "<=", ">="})
_VALID_CAMERA_CALC_OPS = frozenset({"simplify", "differentiate", "integrate", "factor", "expand"})
_VALID_CAMERA_STATS_OPS = frozenset(
    {"mean", "median", "mode", "variance", "stdev", "sample_stdev", "sample_variance"}
)


class MathImageExtract(BaseModel):
    """Vision-extracted math from a photo (validated before SymPy).

    `lhs`/`rhs` hold the first (or only) equation/inequality side — callers
    that only handled a single equation keep working. Structured kinds
    (system, inequality, calculus, limit, graph, rectangle, circle,
    triangle_sides, statistics) are additive so photographed homework beyond
    ``lhs=rhs`` still gets a verified SymPy path instead of unverified
    free-text."""

    kind: Literal[
        "equation",
        "system",
        "inequality",
        "calculus",
        "limit",
        "graph",
        "rectangle",
        "circle",
        "triangle_sides",
        "statistics",
    ] = "equation"
    # Defaults "0" let structured kinds omit equation sides in the vision JSON.
    lhs: str = Field(default="0", min_length=1, max_length=256)
    rhs: str = Field(default="0", min_length=1, max_length=256)
    variables: list[str] = Field(default_factory=lambda: ["x"], min_length=1, max_length=4)
    found: bool = True
    # Exact visible problem text retained for whole-request auditing. The
    # structured fields below intentionally cover only the verified solver's
    # closed grammar; source_text preserves constraints (for example x in Z)
    # that the grammar cannot yet represent so they cannot be silently lost.
    source_text: str | None = Field(default=None, min_length=1, max_length=2000)
    # A second independent OCR reading, when available. Disagreement is not
    # resolved by choosing one provider: both readings pass through the same
    # whole-request audit before any structured result can be certified.
    alternate_source_text: str | None = Field(default=None, min_length=1, max_length=2000)
    # kind == "system": every equation in the system as (lhs, rhs) pairs,
    # INCLUDING the first (so this is self-contained — callers don't need
    # to merge it with lhs/rhs above).
    equations: list[tuple[str, str]] | None = None
    # kind == "inequality": canonical comparator applied to lhs/rhs above.
    comparator: str | None = None
    # kind == "calculus" | "limit" | "graph": expression on the page.
    expr: str | None = Field(default=None, max_length=256)
    # kind == "calculus": simplify / differentiate / integrate / factor / expand.
    operation: str | None = None
    # kind == "limit": point approached (number or "infinity" / "oo").
    limit_point: str | None = Field(default=None, max_length=32)
    # kind == "calculus" + integrate: definite bounds (both required, or neither).
    integral_lower: str | None = Field(default=None, max_length=32)
    integral_upper: str | None = Field(default=None, max_length=32)
    # kind == "rectangle" | "circle": printed dimensions (never invent).
    width: float | None = Field(default=None, ge=0, le=1_000_000)
    height: float | None = Field(default=None, ge=0, le=1_000_000)
    radius: float | None = Field(default=None, ge=0, le=1_000_000)
    unit: str = Field(default="cm", max_length=16)
    # kind == "triangle_sides": printed SSS side lengths (never invent).
    tri_a: float | None = Field(default=None, ge=0, le=1_000_000)
    tri_b: float | None = Field(default=None, ge=0, le=1_000_000)
    tri_c: float | None = Field(default=None, ge=0, le=1_000_000)
    # kind == "statistics": printed data list + which summary was asked.
    stats_op: str | None = None
    stats_numbers: list[float] | None = Field(default=None, max_length=40)

    def _has_equation_sides(self) -> bool:
        return self.lhs.strip() not in ("", "0") or self.rhs.strip() not in ("", "0")

    @model_validator(mode="after")
    def normalize_kind(self) -> MathImageExtract:
        # Best-effort OCR hint from a vision model — a malformed/incomplete
        # kind must degrade gracefully rather than fail the whole extraction.
        if self.kind == "system" and (not self.equations or len(self.equations) < 2):
            self.kind = "equation"
        if self.kind == "inequality" and self.comparator not in _VALID_INEQUALITY_COMPARATORS:
            self.kind = "equation"
        # Defaults are "0"/"0" so structured kinds can omit sides. A bare
        # equation claim with both sides still at the placeholder is "not
        # found" (matches the vision prompt: found=false + lhs/rhs of "0").
        if (
            self.kind == "equation"
            and self.lhs.strip() in ("", "0")
            and self.rhs.strip() in ("", "0")
        ):
            self.found = False
        if self.kind == "calculus":
            op = (self.operation or "").strip().lower()
            if not (self.expr and self.expr.strip() and op in _VALID_CAMERA_CALC_OPS):
                self.kind = "equation" if self._has_equation_sides() else self.kind
                if self.kind == "calculus":
                    self.found = False
            else:
                self.operation = op
                # Definite integrals need BOTH bounds. A half-filled OCR
                # guess must not invent the missing endpoint — drop to
                # indefinite (same as heuristic when bounds parse fails).
                lower = (self.integral_lower or "").strip()
                upper = (self.integral_upper or "").strip()
                if op == "integrate" and lower and upper:
                    self.integral_lower = lower
                    self.integral_upper = upper
                else:
                    self.integral_lower = None
                    self.integral_upper = None
        if self.kind == "limit":
            if not (
                self.expr and self.expr.strip() and self.limit_point and self.limit_point.strip()
            ):
                self.kind = "equation" if self._has_equation_sides() else self.kind
                if self.kind == "limit":
                    self.found = False
        if self.kind == "graph":
            if not (self.expr and self.expr.strip()):
                self.kind = "equation" if self._has_equation_sides() else self.kind
                if self.kind == "graph":
                    self.found = False
        if self.kind == "rectangle":
            if self.width is None or self.height is None or self.width <= 0 or self.height <= 0:
                self.kind = "equation" if self._has_equation_sides() else self.kind
                if self.kind == "rectangle":
                    self.found = False
        if self.kind == "circle":
            if self.radius is None or self.radius <= 0:
                self.kind = "equation" if self._has_equation_sides() else self.kind
                if self.kind == "circle":
                    self.found = False
        if self.kind == "triangle_sides":
            sides = (self.tri_a, self.tri_b, self.tri_c)
            if any(s is None or s <= 0 for s in sides):
                self.kind = "equation" if self._has_equation_sides() else self.kind
                if self.kind == "triangle_sides":
                    self.found = False
        if self.kind == "statistics":
            op = (self.stats_op or "mean").strip().lower()
            nums = self.stats_numbers or []
            if op not in _VALID_CAMERA_STATS_OPS or len(nums) < 2:
                self.kind = "equation" if self._has_equation_sides() else self.kind
                if self.kind == "statistics":
                    self.found = False
            else:
                self.stats_op = op
        return self


class MathSolveResult(BaseModel):
    solutions_latex: list[str]
    # Compact ± / conjugate grouping for the ```answer pill. Empty → use solutions_latex.
    canonical_solutions_latex: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    lhs_latex: str = ""
    rhs_latex: str = ""
    # "none"/"infinite" only apply when solutions_latex is empty — distinguishes
    # a genuine contradiction (no solution) from a tautology (every value
    # satisfies the equation), which used to collapse into one ambiguous string.
    solution_kind: Literal["finite", "none", "infinite"] = "finite"
    # Conditions inherited from the original, unsimplified problem. These
    # remain structured so x/x=1 cannot simplify to 1=1 and lose x != 0.
    domain_conditions_latex: list[str] = Field(default_factory=list)
    # Parameter cases that qualify a symbolic solution (for example ax=5).
    alternate_cases_latex: list[str] = Field(default_factory=list)


class MathSystemSolveResult(BaseModel):
    # One dict of {variable: value_latex} per solution set — usually one for
    # a linear system, but sympy.solve on a nonlinear system can return
    # several (e.g. two intersection points).
    solutions: list[dict[str, str]] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    solution_kind: Literal["finite", "none", "infinite"] = "finite"


class NewtonMethodInput(BaseModel):
    expr: str = Field(min_length=1, max_length=256)
    variable: str = Field(default="x", min_length=1, max_length=8)
    initial_guess: float = Field(default=1.0, ge=-1_000_000, le=1_000_000)
    tolerance: float = Field(default=1e-6, gt=0, le=1)
    # Capped low: this bounds real per-request iteration work, not something
    # a user-supplied "solve to N decimal places" should ever need to raise.
    max_iterations: int = Field(default=50, ge=1, le=200)


class NewtonIterationStep(BaseModel):
    n: int
    x_n: float
    f_x_n: float


class NewtonMethodResult(BaseModel):
    # Derived from the same parsed function/derivative used by the iteration.
    function_latex: str | None = None
    derivative_latex: str | None = None
    recurrence_latex: str | None = None
    iterations: list[NewtonIterationStep] = Field(default_factory=list)
    converged: bool
    root: float | None = None
    iterations_used: int


class MathExprResult(BaseModel):
    result: str
    latex: str
    # False when SymPy couldn't find a closed form (integrate_expression can
    # return a literal unevaluated Integral(...) rather than raising) — the
    # verified block must not assert an unsolved expression as a fact.
    solved: bool = True
    # Verified worked steps (rule name + per-term derivative) so the model
    # can copy them instead of inventing its own derivation. Empty for
    # operations where SymPy doesn't expose intermediate steps.
    steps: list[str] = Field(default_factory=list)


class MathLimitResult(BaseModel):
    result: str
    latex: str
    # True for oo/-oo or zoo. Presentation must distinguish a signed infinite
    # limit from zoo (opposite one-sided limits), which has no two-sided value.
    is_infinite: bool


class MathSeriesResult(BaseModel):
    result: str
    latex: str
    is_infinite: bool
    solved: bool = True
    # None when SymPy can't determine convergence (rare); otherwise a
    # definite True/False for whether the (typically infinite) series
    # converges, and separately whether it converges absolutely.
    is_convergent: bool | None = None
    is_absolutely_convergent: bool | None = None
