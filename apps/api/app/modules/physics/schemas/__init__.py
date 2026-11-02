"""Structured physics I/O — validated before SymPy and fence emission."""

from __future__ import annotations

from app.modules.physics.schemas.intent import PhysicsIntent
from app.modules.physics.schemas.simulation import (
    CircuitNode,
    CircuitSource,
    CircuitSpec,
    OpticsArrow,
    OpticsRay,
    OpticsSpec,
    SimulationAngle,
    SimulationBlockSpec,
    SimulationBody,
    SimulationPlanet,
    SimulationPulley,
    SimulationSolid,
    SimulationTether,
    SimulationVector,
    WaveSpec,
)

__all__ = [
    "CircuitNode",
    "CircuitSource",
    "CircuitSpec",
    "OpticsArrow",
    "OpticsRay",
    "OpticsSpec",
    "PhysicsIntent",
    "SimulationAngle",
    "SimulationBlockSpec",
    "SimulationBody",
    "SimulationPlanet",
    "SimulationPulley",
    "SimulationSolid",
    "SimulationTether",
    "SimulationVector",
    "WaveSpec",
]
