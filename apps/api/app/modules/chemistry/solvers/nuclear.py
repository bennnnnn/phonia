# ruff: noqa: RUF001
"""Nuclear chemistry: balanced nuclear equations and binding energy from the mass defect."""

from __future__ import annotations

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.nuclear import (
    balance_nuclear,
    conservation_lines,
    format_nuclear,
    parse_nuclide,
)
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import MEV_PER_U, NEUTRON_U, PROTON_U
from app.modules.chemistry.solvers.display import inp, num, verified
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError


def solve_nuclear_equation(intent: ChemistryIntent) -> ChemistryResult:
    if not intent.equation:
        raise SolveServiceError("a nuclear equation is required")
    balanced = balance_nuclear(intent.equation)
    if not balanced.balanced:
        raise SolveServiceError(balanced.error or "nuclear equation does not balance")
    shown = format_nuclear(balanced)
    return verified(
        "Verified nuclear equation",
        (intent.equation,),
        "Balanced nuclear equation",
        *stated("nuclear_equation"),
        conservation_lines(balanced),
        shown,
        shown,
    )


def solve_mass_defect(intent: ChemistryIntent) -> ChemistryResult:
    label = intent.formula or ""
    mass = intent.params.get("nuclear_mass")
    nuclide = parse_nuclide(label)
    if nuclide is None or nuclide.is_particle or mass is None or mass <= 0:
        raise SolveServiceError("mass defect needs a nuclide and its nuclear mass in u")
    symbol, mass_number, protons = nuclide.symbol, nuclide.mass_number, nuclide.protons
    neutrons = mass_number - protons
    defect = protons * PROTON_U + neutrons * NEUTRON_U - mass
    energy = defect * MEV_PER_U
    per_nucleon = energy / mass_number
    shown = "\n".join(
        (
            f"Δm = {num(defect)} u",
            f"E = {num(energy)} MeV",
            f"E/A = {num(per_nucleon)} MeV/nucleon",
        )
    )
    return verified(
        "Verified mass defect",
        (
            f"{mass_number}{symbol}",
            f"Z = {protons}",
            f"nuclear mass = {inp(mass)} u",
        ),
        "Mass defect, binding energy, and binding energy per nucleon",
        *stated("mass_defect"),
        (
            f"Δm = {protons}({inp(PROTON_U)}) + {neutrons}({inp(NEUTRON_U)}) − {inp(mass)} "
            f"= {num(defect)} u",
            f"E = Δm × {inp(MEV_PER_U)} = {num(defect)} × {inp(MEV_PER_U)} = {num(energy)} MeV",
            f"E/A = {num(energy)} / {mass_number} = {num(per_nucleon)} MeV/nucleon",
        ),
        shown,
        shown,
    )
