"""Stable dispatcher for typed chemistry calculations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from app.modules.chemistry.catalog import formula_spec
from app.modules.chemistry.formula_laws import FORMULA_LAWS
from app.modules.chemistry.scene import attach_scene
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.sig_figs import numbers_as_written
from app.modules.chemistry.solvers.acid_base import (
    solve_acid_base,
    solve_ka_kb,
    solve_strong_acid,
    solve_strong_base,
)
from app.modules.chemistry.solvers.acid_equilibria import (
    solve_amphiprotic,
    solve_buffer_addition,
    solve_conjugate_salt,
    solve_diprotic_a2,
    solve_polyprotic,
    solve_weak_acid,
    solve_weak_acid_ka,
    solve_weak_base,
)
from app.modules.chemistry.solvers.amounts import (
    solve_amount,
    solve_atom_economy,
    solve_average_atomic_mass,
    solve_molar_mass,
    solve_percent_composition,
)
from app.modules.chemistry.solvers.analytical import (
    solve_calibration,
    solve_capacity_factor,
    solve_chromatography_rf,
    solve_gravimetric,
    solve_lod,
    solve_loq,
    solve_percent_error,
    solve_plate_height,
    solve_plate_number,
    solve_relative_uncertainty,
    solve_resolution,
    solve_selectivity,
    solve_standard_addition,
    solve_standard_deviation,
    solve_standard_error,
)
from app.modules.chemistry.solvers.atom_particles import solve_atom_particles
from app.modules.chemistry.solvers.electrochemistry import (
    solve_cell_potential,
    solve_electrochemistry,
    solve_galvanic_cell,
    solve_galvanic_nernst,
)
from app.modules.chemistry.solvers.empirical import (
    solve_combustion,
    solve_empirical,
    solve_hydrate,
    solve_molecular,
)
from app.modules.chemistry.solvers.equilibrium import (
    solve_equilibrium,
    solve_kc_kp,
    solve_kp,
)
from app.modules.chemistry.solvers.formula import solve_formula_law
from app.modules.chemistry.solvers.gases import (
    solve_dalton,
    solve_gas_over_water,
    solve_graham,
    solve_henry,
    solve_partial_pressure,
)
from app.modules.chemistry.solvers.half_reaction import solve_half_reaction
from app.modules.chemistry.solvers.ice_table import (
    solve_ice,
)
from app.modules.chemistry.solvers.kinetics import (
    solve_kinetics,
    solve_second_half_life,
    solve_second_order,
    solve_zero_half_life,
    solve_zero_order,
)
from app.modules.chemistry.solvers.mass_stoichiometry import (
    solve_limiting_mass,
    solve_limiting_solution,
    solve_mass_stoichiometry,
    solve_reaction_percent_yield,
)
from app.modules.chemistry.solvers.nuclear import (
    solve_mass_defect,
    solve_nuclear_equation,
)
from app.modules.chemistry.solvers.organic import (
    solve_functional_groups,
    solve_isomers,
    solve_iupac_name,
    solve_named_reaction,
    solve_stereochemistry,
    solve_structure,
)
from app.modules.chemistry.solvers.rate_laws import (
    solve_arrhenius_two_point,
    solve_michaelis_menten,
    solve_rate_law,
)
from app.modules.chemistry.solvers.solubility import (
    solve_common_ion,
    solve_ksp,
    solve_precipitation,
)
from app.modules.chemistry.solvers.solutions import (
    solve_boiling,
    solve_freezing,
    solve_osmotic,
    solve_raoult,
    solve_solution,
)
from app.modules.chemistry.solvers.spectroscopy import (
    solve_beer_lambert,
    solve_ir_peak,
    solve_ir_ranges,
    solve_molecular_ion,
    solve_nmr_peak,
    solve_nmr_ranges,
    solve_nmr_splitting,
)
from app.modules.chemistry.solvers.stoichiometry import (
    solve_equation,
    solve_percent_yield,
    solve_stoichiometry,
)
from app.modules.chemistry.solvers.structure import (
    solve_coordination,
    solve_crystal_field,
    solve_electron_configuration,
    solve_formal_charge,
    solve_ionic_formula,
    solve_ionic_name,
    solve_oxidation_state,
    solve_valence_electrons,
    solve_vsepr,
)
from app.modules.chemistry.solvers.thermochemistry import (
    solve_bond_enthalpy,
    solve_calorimetry,
    solve_clausius,
    solve_formation,
    solve_hess,
    solve_thermochemistry,
)
from app.modules.chemistry.solvers.titration import solve_titration_strong, solve_titration_weak
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError

CHEMISTRY_SOLVERS: dict[str, Callable[[ChemistryIntent], ChemistryResult]] = {
    "empirical_formula": solve_empirical,
    "combustion_analysis": solve_combustion,
    "hydrate_water": solve_hydrate,
    "molecular_formula": solve_molecular,
    "mass_stoichiometry": solve_mass_stoichiometry,
    "solution_stoichiometry": solve_mass_stoichiometry,
    "gas_stoichiometry": solve_mass_stoichiometry,
    "limiting_mass": solve_limiting_mass,
    "limiting_solution": solve_limiting_solution,
    "reaction_percent_yield": solve_reaction_percent_yield,
    "strong_acid_ph": solve_strong_acid,
    "strong_acid_poh": solve_strong_acid,
    "strong_base_ph": solve_strong_base,
    "strong_base_poh": solve_strong_base,
    "weak_acid_ph": solve_weak_acid,
    "weak_base_ph": solve_weak_base,
    "ka_kb": solve_ka_kb,
    "titration_strong": solve_titration_strong,
    "titration_weak": solve_titration_weak,
    "buffer_addition": solve_buffer_addition,
    "polyprotic_ph": solve_polyprotic,
    "amphiprotic_ph": solve_amphiprotic,
    "diprotic_a2": solve_diprotic_a2,
    "dalton": solve_dalton,
    "partial_pressure": solve_partial_pressure,
    "gas_over_water": solve_gas_over_water,
    "graham": solve_graham,
    "calorimetry": solve_calorimetry,
    "hess": solve_hess,
    "formation_enthalpy": solve_formation,
    "bond_enthalpy": solve_bond_enthalpy,
    "clausius_clapeyron": solve_clausius,
    "ksp": solve_ksp,
    "precipitation": solve_precipitation,
    "common_ion": solve_common_ion,
    "kp": solve_kp,
    "kc_kp": solve_kc_kp,
    "ice_equilibrium": solve_ice,
    "zero_order": solve_zero_order,
    "second_order": solve_second_order,
    "zero_order_half_life": solve_zero_half_life,
    "second_order_half_life": solve_second_half_life,
    "rate_law": solve_rate_law,
    "arrhenius_two_point": solve_arrhenius_two_point,
    "cell_potential": solve_cell_potential,
    "galvanic_cell": solve_galvanic_cell,
    "galvanic_nernst": solve_galvanic_nernst,
    "nuclear_equation": solve_nuclear_equation,
    "oxidation_state": solve_oxidation_state,
    "vsepr": solve_vsepr,
    "valence_electrons": solve_valence_electrons,
    "ionic_formula": solve_ionic_formula,
    "ionic_name": solve_ionic_name,
    "formal_charge": solve_formal_charge,
    "functional_groups": solve_functional_groups,
    "stereochemistry": solve_stereochemistry,
    "isomers": solve_isomers,
    "coordination_complex": solve_coordination,
    "boiling_elevation": solve_boiling,
    "freezing_depression": solve_freezing,
    "solution_boiling_point": solve_boiling,
    "solution_freezing_point": solve_freezing,
    "osmotic_pressure": solve_osmotic,
    "raoult": solve_raoult,
    "henry": solve_henry,
    "calibration": solve_calibration,
    "gravimetric": solve_gravimetric,
    "standard_addition": solve_standard_addition,
    "mass_defect": solve_mass_defect,
    "crystal_field": solve_crystal_field,
    "standard_deviation": solve_standard_deviation,
    "standard_error": solve_standard_error,
    "percent_error": solve_percent_error,
    "relative_uncertainty": solve_relative_uncertainty,
    "chromatography_rf": solve_chromatography_rf,
    "lod": solve_lod,
    "loq": solve_loq,
    "capacity_factor": solve_capacity_factor,
    "selectivity": solve_selectivity,
    "resolution": solve_resolution,
    "plate_number": solve_plate_number,
    "plate_height": solve_plate_height,
    "iupac_name": solve_iupac_name,
    "structure": solve_structure,
    "named_reaction": solve_named_reaction,
    "ir_ranges": solve_ir_ranges,
    "ir_peak": solve_ir_peak,
    "nmr_ranges": solve_nmr_ranges,
    "nmr_peak": solve_nmr_peak,
    "nmr_splitting": solve_nmr_splitting,
    "molecular_ion": solve_molecular_ion,
    "michaelis_menten": solve_michaelis_menten,
    "average_atomic_mass": solve_average_atomic_mass,
    "electron_configuration": solve_electron_configuration,
    "atom_particles": solve_atom_particles,
    "balance": solve_equation,
    "half_reaction": solve_half_reaction,
    "molar_mass": solve_molar_mass,
    "mass_to_moles": solve_amount,
    "moles_to_mass": solve_amount,
    "moles_to_particles": solve_amount,
    "particles_to_moles": solve_amount,
    "mass_to_particles": solve_amount,
    "percent_composition": solve_percent_composition,
    "percent_yield": solve_percent_yield,
    "atom_economy": solve_atom_economy,
    "stoichiometry": solve_stoichiometry,
    "limiting_reagent": solve_stoichiometry,
    "molarity": solve_solution,
    "dilution": solve_solution,
    "molality": solve_solution,
    "mass_percent": solve_solution,
    "ph_from_h": solve_acid_base,
    "ph_from_poh": solve_acid_base,
    "h_from_ph": solve_acid_base,
    "poh_from_oh": solve_acid_base,
    "buffer_ph": solve_acid_base,
    "base_buffer_ph": solve_acid_base,
    "weak_acid_ka": solve_weak_acid_ka,
    "conjugate_salt_ph": solve_conjugate_salt,
    "gibbs": solve_thermochemistry,
    "equilibrium_constant": solve_equilibrium,
    "reaction_quotient": solve_equilibrium,
    "first_order_half_life": solve_kinetics,
    "first_order_concentration": solve_kinetics,
    "first_order_time": solve_kinetics,
    "arrhenius": solve_kinetics,
    "cell_gibbs": solve_electrochemistry,
    "nernst": solve_electrochemistry,
    "electrolysis_mass": solve_electrochemistry,
    "beer_lambert": solve_beer_lambert,
    **dict.fromkeys(FORMULA_LAWS, solve_formula_law),
}


def solve_chemistry(intent: ChemistryIntent) -> ChemistryResult:
    """Dispatch a validated intent to its subject-grouped pure solver."""
    with numbers_as_written(intent):
        result = attach_scene(intent, _solve(intent))
    spec = formula_spec(intent.chemistry_op)
    return replace(result, method=spec is not None and spec.method)


def _solve(intent: ChemistryIntent) -> ChemistryResult:
    solver = CHEMISTRY_SOLVERS.get(intent.chemistry_op)
    if solver is None:
        raise SolveServiceError(f"unsupported chemistry operation: {intent.chemistry_op}")
    return solver(intent)
