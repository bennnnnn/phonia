"""Typed teaching scenes. Solvers build these; the phone only draws them."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class BalanceRow(BaseModel):
    element: str
    left: int
    right: int


class ChargeTally(BaseModel):
    left: int
    right: int


class BalanceScene(BaseModel):
    kind: Literal["balance"] = "balance"
    title: str
    rows: list[BalanceRow]
    charge: ChargeTally


class StoichStep(BaseModel):
    label: str
    value: str


class StoichScene(BaseModel):
    kind: Literal["stoich"] = "stoich"
    title: str
    steps: list[StoichStep]


class VseprScene(BaseModel):
    kind: Literal["vsepr"] = "vsepr"
    title: str
    central: str
    terminals: list[str]
    lone_pairs: int
    geometry: str
    bond_angle: str
    electron_geometry: str
    ideal_angle: str


class TitrationAnchor(BaseModel):
    label: str
    ph: str | None = None
    volume: str | None = None
    detail: str | None = None
    value: str | None = None


class TitrationScene(BaseModel):
    kind: Literal["titration"] = "titration"
    title: str
    region: str
    anchors: list[TitrationAnchor]


class EquilibriumRow(BaseModel):
    species: str
    initial: str
    change: str
    equilibrium: str


class EquilibriumScene(BaseModel):
    kind: Literal["equilibrium"] = "equilibrium"
    title: str
    rows: list[EquilibriumRow]


class CellScene(BaseModel):
    kind: Literal["cell"] = "cell"
    title: str
    anode: str
    cathode: str
    potential: str
    electrons: str


ChemistryScene = Annotated[
    BalanceScene | StoichScene | VseprScene | TitrationScene | EquilibriumScene | CellScene,
    Field(discriminator="kind"),
]


def dump_scene(scene: ChemistryScene) -> dict[str, object]:
    """JSON object for a ```chem_scene fence. Absent optionals stay omitted."""
    return scene.model_dump(mode="json", exclude_none=True)
