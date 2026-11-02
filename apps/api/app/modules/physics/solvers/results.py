"""What a physics solver returns: its quantities, working and pictures."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.math.schemas import GraphBlockSpec
from app.modules.physics.schemas import (
    SimulationBlockSpec,
)
from app.modules.physics.solvers.chip import render_chip, render_chip_latex


@dataclass(frozen=True, slots=True)
class QuantityResult:
    """One measured result. Notes such as gauge pressure live in ``detail``.

    The value is shown to three significant figures (``physics.display``);
    a solver never chooses its own number format.
    """

    symbol: str
    value: float
    unit: str = ""
    detail: str | None = None
    # "paren" -> "12 Pa (gauge)"; "suffix" -> "4 A leaving"; "at" -> "5 N at 30°".
    detail_style: str = "paren"


@dataclass(frozen=True)
class PhysicsResult:
    """Solver output. The chip is rendered from ``quantities``, never parsed back."""

    answer: str
    answer_value: str = ""
    answer_latex: str = ""
    quantities: tuple[QuantityResult, ...] = ()
    formulas: tuple[str, ...] = ()
    substitutions: tuple[str, ...] = ()
    joiner: str = " and "
    graph_specs: list[GraphBlockSpec] = field(default_factory=list)
    # A scene of moving bodies, where the graph is a plot of one. A solve may
    # emit both: the projectile's parabola *and* the ball flying along it.
    simulation_specs: list[SimulationBlockSpec] = field(default_factory=list)
    # A question in parts: each requested quantity with the working that gives it.
    parts: tuple[PartResult, ...] = ()

    def __post_init__(self) -> None:
        if self.quantities:
            object.__setattr__(self, "answer_value", render_chip(self.quantities, self.joiner))
            object.__setattr__(
                self, "answer_latex", render_chip_latex(self.quantities, self.joiner)
            )


@dataclass(frozen=True)
class PartResult:
    """One quantity of a question in parts: its operation, its labelled value, its working."""

    op: str
    quantity: QuantityResult
    result: PhysicsResult


def solved(
    *quantities: QuantityResult,
    answer: str,
    formula: str = "",
    substitution: str = "",
    formulas: tuple[str, ...] = (),
    substitutions: tuple[str, ...] = (),
    joiner: str = " and ",
    graph_specs: list[GraphBlockSpec] | None = None,
    simulation_specs: list[SimulationBlockSpec] | None = None,
) -> PhysicsResult:
    """Build the chip and keep the formula and the substitution unparsed."""
    formula_rows = formulas or ((formula,) if formula else ())
    substitution_rows = substitutions or ((substitution,) if substitution else ())
    return PhysicsResult(
        answer=answer,
        quantities=quantities,
        formulas=formula_rows,
        substitutions=substitution_rows,
        joiner=joiner,
        graph_specs=list(graph_specs or []),
        simulation_specs=list(simulation_specs or []),
    )
