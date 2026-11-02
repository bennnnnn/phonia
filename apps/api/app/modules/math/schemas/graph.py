"""Structured math I/O — validated before SymPy and fence emission."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GraphSampleInput(BaseModel):
    expr: str = Field(min_length=1, max_length=256)
    variable: str = Field(default="x", min_length=1, max_length=8)
    x_min: float = -10.0
    x_max: float = 10.0
    n: int = Field(default=200, ge=10, le=500)


class GraphSampleResult(BaseModel):
    expr: str
    variable: str
    x_min: float
    x_max: float
    points: list[list[float]]
    # points split at likely vertical-asymptote gaps (see
    # math_solve._split_into_segments) so a renderer can draw each as its
    # own polyline instead of one continuous line straight across a
    # discontinuity (e.g. tan(x) at pi/2). Kept alongside `points` (not
    # instead of) for back-compat with fences the model already knows how
    # to emit with only `points`.
    segments: list[list[list[float]]] = Field(default_factory=list)
    # Open points where the original expression is undefined even though its
    # simplified limit is finite (for example (x^2-1)/(x-1) at x=1).
    holes: list[list[float]] = Field(default_factory=list, max_length=8)


class NumberLineInterval(BaseModel):
    """One piece of a 1-variable inequality on a number line.

    ``start``/``end`` of ``None`` mean -inf / +inf. A closed (filled) circle is
    ``inclusive``; an open circle is not.
    """

    start: float | None = None
    end: float | None = None
    start_inclusive: bool = False
    end_inclusive: bool = False

    @model_validator(mode="after")
    def ordered_bounds(self) -> NumberLineInterval:
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("interval start must be <= end")
        return self


class GraphBlockSpec(BaseModel):
    type: Literal["function", "vertical", "number_line", "trajectory", "inequality"] = "function"
    # Same bounds as every other math input model in this file (EquationInput,
    # GraphSampleInput, MathImageExtract) — this one was missing them, an
    # inconsistency worth closing even though this field is currently
    # display-only (math/fence.py never re-parses it through SymPy).
    expr: str = Field(default="", max_length=256)
    variable: str = Field(default="x", min_length=1, max_length=8)
    x_min: float = -10.0
    x_max: float = 10.0
    # True when the learner named the x-range (for example, "from -pi to
    # pi"). Renderers use that range as the initial viewport while still
    # allowing the learner to pan and zoom. False keeps the adaptive school
    # window used for ordinary "graph y=x^2" requests.
    domain_explicit: bool = False
    # Vertical-line fences (`type: "vertical"`) use `x` + y-range instead of
    # sampling y=f(x). Kept optional so ordinary function fences remain unchanged.
    x: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    # Affine half-plane: a*x + b*y comparator c. These coefficients come
    # from the solver; the renderer never evaluates an expression string.
    a: float | None = None
    b: float | None = None
    c: float | None = None
    comparator: Literal["<", "<=", ">", ">="] | None = None
    title: str | None = None
    # Matches GraphSampleInput.n's upper bound (le=500) — the model never
    # legitimately needs more points than the canonical sample it was given.
    points: list[list[float]] = Field(default_factory=list, max_length=500)
    # points split at likely vertical-asymptote gaps — optional and kept
    # alongside `points` (not instead of) so a fence the model emits with
    # only `points` (the common case — most functions have no asymptote)
    # still validates and renders exactly as before.
    segments: list[list[list[float]]] = Field(default_factory=list, max_length=500)
    holes: list[list[float]] = Field(default_factory=list, max_length=8)
    # Optional second curve for a direct comparison plot ("graph y=x^2 and
    # y=2x on the same axes") — entirely optional so every existing
    # single-function fence (no expr2) still validates and renders unchanged.
    expr2: str | None = Field(default=None, max_length=256)
    variable2: str | None = Field(default=None, max_length=8)
    points2: list[list[float]] | None = Field(default=None, max_length=500)
    segments2: list[list[list[float]]] | None = Field(default=None, max_length=500)
    holes2: list[list[float]] | None = Field(default=None, max_length=8)
    # Short legend labels (e.g. "y = x^2") for the two curves — only
    # meaningful once expr2/points2 make this a two-curve plot.
    label: str | None = Field(default=None, max_length=64)
    label2: str | None = Field(default=None, max_length=64)
    # 1-variable inequality on a number line (`type: "number_line"`). Empty
    # on function/vertical fences so existing dumps stay valid.
    intervals: list[NumberLineInterval] = Field(default_factory=list, max_length=8)
    # Trajectory plots (`type: "trajectory"`) — pre-computed points from the
    # physics solver (no function sampling). `points` is [[x, y], ...].
    # `trajectory_type` distinguishes time-series (height vs time) from
    # parametric (projectile x-y). Axis labels render on the SVG.
    x_label: str | None = Field(default=None, max_length=64)
    y_label: str | None = Field(default=None, max_length=64)
    trajectory_type: Literal["position_vs_time", "velocity_vs_time", "parametric"] | None = None

    @model_validator(mode="after")
    def vertical_or_function_shape(self) -> GraphBlockSpec:
        if self.type == "inequality":
            if not self.expr.strip() or self.comparator is None:
                raise ValueError("inequality graph requires expr and comparator")
            if self.y_min is None or self.y_max is None:
                raise ValueError("inequality graph requires y bounds")
            values = (self.a, self.b, self.c, self.x_min, self.x_max, self.y_min, self.y_max)
            if any(value is None or not math.isfinite(value) for value in values):
                raise ValueError("inequality graph requires finite coefficients and bounds")
            if self.a == 0 and self.b == 0:
                raise ValueError("inequality graph requires a nonconstant boundary")
            if self.x_max <= self.x_min or self.y_max <= self.y_min:
                raise ValueError("inequality graph requires ordered bounds")
            if not all(
                math.isfinite(span) for span in (self.x_max - self.x_min, self.y_max - self.y_min)
            ):
                raise ValueError("inequality graph requires finite spans")
            if not self.title:
                self.title = self.expr
            self.points = []
            self.segments = []
            self.holes = []
            return self
        if self.type == "number_line":
            if not self.expr.strip():
                raise ValueError("number_line requires expr")
            if not self.title:
                self.title = self.expr
            self.points = []
            self.segments = []
            self.holes = []
            return self
        if self.type == "trajectory":
            if len(self.points) < 2:
                raise ValueError("trajectory graph requires at least 2 points")
            if not self.title:
                self.title = "Trajectory"
            # Trajectory plots are pre-computed; no segments needed.
            self.segments = []
            self.holes = []
            return self
        if self.type == "vertical":
            if self.x is None:
                raise ValueError("vertical graph requires x")
            y_lo = -10.0 if self.y_min is None else float(self.y_min)
            y_hi = 10.0 if self.y_max is None else float(self.y_max)
            if y_hi <= y_lo:
                raise ValueError("vertical graph requires y_max > y_min")
            self.y_min = y_lo
            self.y_max = y_hi
            vx = float(self.x)
            # Include the origin and keep x = c in the middle of the view
            # (x=6 → 0..12). A ±5 window around x left 0 off-center and the
            # 8% axis pad then labeled ±12.
            if vx > 0:
                self.x_min = 0.0
                self.x_max = max(2.0 * vx, 10.0)
            elif vx < 0:
                self.x_min = min(2.0 * vx, -10.0)
                self.x_max = 0.0
            else:
                self.x_min = -5.0
                self.x_max = 5.0
            if not self.expr.strip():
                self.expr = f"x = {float(self.x):g}"
            if not self.title:
                self.title = self.expr
            if len(self.points) < 2:
                self.points = [[float(self.x), y_lo], [float(self.x), y_hi]]
            self.segments = []
            self.holes = []
            return self
        if not self.expr.strip():
            raise ValueError("function graph requires expr")
        if len(self.points) < 1:
            raise ValueError("graph points need at least one coordinate")
        for point in [*self.holes, *(self.holes2 or [])]:
            if len(point) != 2 or not all(math.isfinite(value) for value in point):
                raise ValueError("graph holes must be finite [x, y] coordinates")
        has_expr2 = bool(self.expr2 and self.expr2.strip())
        has_points2 = bool(self.points2)
        if has_expr2 != has_points2:
            raise ValueError("expr2 and points2 must both be provided together, or neither")
        return self
