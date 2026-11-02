"""Verified coverage for advanced formula catalog expansion."""

from __future__ import annotations

import re

import pytest

from app.core.config import Settings
from app.modules.chat import tool_loop
from app.modules.physics.catalog import formula_spec
from app.modules.physics.law_titles import law_heading
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
    maybe_direct_physics_reply,
    needs_physics,
)

_SETTINGS = Settings(math_tools_enabled=True, mcp_tool_loop_enabled=True)


CASES: list[tuple[str, str, str]] = [
    (
        "Find the electric field 0.2 m from a point charge of 2 uC.",
        "electric_field",
        "4.49 × 10⁵ N/C",
    ),
    (
        "Find the electric potential 0.2 m from a point charge of 2 uC.",
        "electric_potential",
        "89876 V",
    ),
    (
        "Find the electric potential energy of two point charges 2 uC and -3 uC "
        "separated by 0.5 m.",
        "electric_potential_energy",
        "-0.108 J",
    ),
    (
        "Find the capacitance of a parallel plate capacitor with area 0.02 m^2 "
        "and plate separation 1 mm.",
        "parallel_plate_capacitance",
        "1.77 × 10⁻¹⁰ F",
    ),
    ("Find the energy stored by a 10 uF capacitor at 12 V.", "capacitor_energy", "7.2 × 10⁻⁴ J"),
    (
        "Find the time constant of an RC circuit with resistance 1000 ohm and capacitance 10 uF.",
        "rc_time_constant",
        "0.01 s",
    ),
    (
        "Find the charged particle radius for mass 2e-6 kg, charge 3 uC moving "
        "at 4 m/s perpendicular to a 0.5 T magnetic field.",
        "charged_particle_radius",
        "5.33 m",
    ),
    (
        "Find the motional emf of a 2 m rod moving at 3 m/s perpendicular to a "
        "0.5 T magnetic field.",
        "motional_emf",
        "3 V",
    ),
    (
        "Find the magnetic field 0.2 m from a long straight wire carrying 10 A.",
        "magnetic_field_wire",
        "1 × 10⁻⁵ T",
    ),
    ("Find the lens power for focal length 0.5 m.", "lens_power", "2 D"),
    (
        "A double-slit experiment has wavelength 600 nm, screen distance 2 m, "
        "and slit separation 0.5 mm. Find fringe spacing.",
        "double_slit_fringe_spacing",
        "0.0024 m",
    ),
    (
        "A double-slit experiment has wavelength 500 nm, a screen distance of 1.50 m, "
        "and a slit separation of 0.250 mm. Find the fringe spacing.",
        "double_slit_fringe_spacing",
        "0.003 m",
    ),
    (
        "A single-slit diffraction experiment has wavelength 500 nm, a screen distance "
        "of 1.50 m, and a slit width of 0.100 mm. Find the central width.",
        "diffraction_central_width",
        "0.015 m",
    ),
    (
        "A single-slit diffraction experiment has wavelength 600 nm, screen "
        "distance 2 m, and slit width 0.2 mm. Find central width.",
        "diffraction_central_width",
        "0.012 m",
    ),
    (
        "Using Malus law, find intensity for input intensity 100 W/m^2 at 60 degrees.",
        "malus_intensity",
        "25 W/m²",
    ),
    ("Find the Brewster angle when n1=1 and n2=1.5.", "brewster_angle", "56.3°"),
    (
        "Find Carnot efficiency for a hot reservoir at 500 K and a cold reservoir at 300 K.",
        "carnot_efficiency",
        "0.4 (40%)",
    ),
    (
        "Find the entropy change for reversible heat 1000 J at temperature 500 K.",
        "entropy_change",
        "2 J/K",
    ),
    (
        "Find heat conduction rate for thermal conductivity 0.5 W/m/K, area 2 m^2, "
        "temperature difference 20 K, and thickness 0.1 m.",
        "heat_conduction_rate",
        "200 W",
    ),
    (
        "Find mass flow rate for water density 1000 kg/m^3 through area 0.01 m^2 at speed 2 m/s.",
        "mass_flow_rate",
        "20 kg/s",
    ),
    ("Using Torricelli law, find exit speed for water depth 5 m.", "torricelli_speed", "9.9 m/s"),
    (
        "Using Stokes drag, find force for viscosity 0.2 Pa*s, sphere radius "
        "0.01 m, and speed 3 m/s.",
        "stokes_drag",
        "0.113 N",
    ),
    (
        "Find Reynolds number for density 1000 kg/m^3, speed 2 m/s, characteristic "
        "length 0.1 m, and viscosity 0.001 Pa*s.",
        "reynolds_number",
        "2 × 10⁵",
    ),
    (
        "Find surface tension if force is 0.14 N along contact length 2 m.",
        "surface_tension",
        "0.07 N/m",
    ),
    (
        "Find Laplace pressure in a droplet with surface tension 0.07 N/m and radius 0.001 m.",
        "laplace_pressure",
        "140 Pa",
    ),
    ("Find the Lorentz factor at 0.8 c.", "lorentz_factor", "1.67"),
    ("Find time dilation for proper time 10 s at 0.8 c.", "time_dilation", "16.7 s"),
    ("Find length contraction for proper length 100 m at 0.8 c.", "length_contraction", "60 m"),
    (
        "Find maximum photoelectric kinetic energy for frequency 1e15 Hz and work function 2 eV.",
        "photoelectric_kinetic_energy",
        "3.42 × 10⁻¹⁹ J (2.14 eV)",
    ),
    (
        "Find minimum momentum uncertainty for position uncertainty 1 nm.",
        "uncertainty_momentum",
        "5.27 × 10⁻²⁶ kg·m/s",
    ),
    (
        "Find energy for an electron in a particle in a box of width 1 nm at n=2.",
        "particle_box_energy",
        "2.41 × 10⁻¹⁹ J (1.5 eV)",
    ),
    ("Find the hydrogen energy at n=2.", "hydrogen_energy_level", "-3.4 eV"),
    ("Find the Compton wavelength shift at 90 degrees.", "compton_shift", "2.43 × 10⁻¹² m"),
    ("Using Wien's law, find peak wavelength at temperature 3000 K.", "wien_peak", "9.66 × 10⁻⁷ m"),
    (
        "Find Stefan-Boltzmann blackbody power for area 2 m^2, temperature "
        "500 K, and emissivity 0.8.",
        "stefan_boltzmann_power",
        "5670 W",
    ),
    (
        "Using Stefan's law, a blackbody of area 0.2 m^2 is at 500 K. Find the power.",
        "stefan_boltzmann_power",
        "709 W",
    ),
]


@pytest.mark.parametrize("query,operation,answer", CASES)
def test_phase2_catalog_is_verified_and_uses_structured_working(
    query: str, operation: str, answer: str
) -> None:
    assert needs_physics(query)
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    assert intent.physics_op == operation
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    assert verified.canonical_answer == answer

    reply = maybe_direct_physics_reply(verified, query)
    assert reply is not None
    spec = formula_spec(operation)
    assert spec is not None
    law = f"**{law_heading(spec.law_name)}**"
    headings = ["**Given**", "**Required**", law, "**Substitution**", "**Answer**"]
    assert [reply.index(heading) for heading in headings] == sorted(
        reply.index(h) for h in headings
    )
    assert "Physics formula:" not in reply
    assert re.search(r"\d+\.\d*00(?=\D|$)", reply) is None
    if operation == "carnot_efficiency":
        assert "$T_H = 500\\,\\mathrm{K}$" in reply
        assert "$T_C = 300\\,\\mathrm{K}$" in reply


@pytest.mark.parametrize(
    "query",
    [
        "Find the Lorentz factor at 1.2 c.",
        "Find maximum photoelectric kinetic energy for frequency 1e14 Hz and work function 4 eV.",
        "Find the motional emf of a 2 m rod moving at 3 m/s in a 0.5 T magnetic field.",
        "Find Carnot efficiency for a hot reservoir at 200 C and a cold reservoir at 20 C.",
        "Find the fourth harmonic of a 0.5 m closed pipe with sound speed 340 m/s.",
    ],
)
def test_phase2_catalog_refuses_invalid_or_assumption_sensitive_inputs(query: str) -> None:
    intent = extract_physics_intent(query)
    if isinstance(intent, PhysicsIntent):
        assert build_verified_physics_block(intent, _SETTINGS) is None
    else:
        assert intent is None


@pytest.mark.parametrize(
    "query",
    [
        "Derive the time-dependent Schrodinger equation for this Hamiltonian.",
        "Use the Euler-Lagrange equation to derive the equations of motion.",
        "Solve Maxwell's equations with the stated boundary conditions.",
    ],
)
def test_advanced_theory_stays_in_physics_without_opening_an_external_tool_loop(query: str) -> None:
    assert needs_physics(query)
    assert extract_physics_intent(query) is None
    assert tool_loop.turn_needs_tool_loop(query, settings=_SETTINGS) is False
