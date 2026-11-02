"""Verified uniform-field operations: plates, a charge in a field, and qV."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

SPECS: tuple[FormulaSpec, ...] = (
    # The uniform field between parallel plates.
    formula(
        "plate_field",
        "magnetism",
        "Uniform electric field",
        "E",
        base_latex=r"E = \frac{V}{d}",
        assumptions=("a uniform field between parallel plates",),
        expression="V/d",
        variables=(var("V", "V", "volt"), var("d", "d", "meter")),
        binding=Binding(
            asks=("electric field strength", "field strength", "electric field"),
            result=("volt / meter",),
            inputs=(frozenset({"V", "d"}),),
            cues=("plate",),
            nonnegative=True,
        ),
    ),
    formula(
        "field_force_on_charge",
        "magnetism",
        "Electric force on a charge",
        "F",
        base_latex="F = qE",
        expression="Q*e_field",
        variables=(
            var("Q", "q", "coulomb", fallback="particle_charge"),
            var("e_field", "E", "volt / meter"),
        ),
        binding=Binding(
            asks=("force",),
            result=("newton",),
            inputs=(frozenset({"Q", "e_field"}),),
            cues=("field",),
        ),
    ),
    formula(
        "charge_energy",
        "magnetism",
        "Energy of a charge through a potential difference",
        "W",
        base_latex="W = qV",
        expression="Q*V",
        variables=(var("Q", "q", "coulomb", fallback="particle_charge"), var("V", "V", "volt")),
        binding=Binding(
            asks=("kinetic energy", "work done", "energy", "work"),
            result=("joule",),
            inputs=(frozenset({"Q", "V"}),),
            cues=(
                "accelerated through",
                "moved through",
                "through a potential",
                "potential difference",
            ),
        ),
    ),
    formula(
        "electric_energy_density",
        "magnetism",
        "Electric energy density",
        "u",
        base_latex=r"u = \frac{1}{2}\varepsilon_0 E^2",
        expression="epsilon_0*e_field**2/2",
        variables=(var("e_field", "E", "volt / meter"),),
        binding=Binding(
            asks=("energy density", "electric energy density"),
            result=("joule / meter ** 3",),
            inputs=(frozenset({"e_field"}),),
            cues=("electric",),
            excludes=("magnetic",),
            nonnegative=True,
        ),
    ),
    # The field of a point charge, by Coulomb's law.
    formula(
        "point_charge_field",
        "magnetism",
        "Coulomb's law",
        "E",
        base_latex=r"E = \frac{k_e q}{r^2}",
        expression="k_e*Q/r**2",
        variables=(
            var("Q", "q", "coulomb", fallback="particle_charge"),
            var("r", "r", "meter"),
        ),
        binding=Binding(
            asks=("electric field strength", "field strength", "electric field"),
            result=("volt / meter",),
            inputs=(frozenset({"Q", "r"}),),
            cues=("point charge", "charge"),
            excludes=("plate", "dipole"),
            nonnegative=True,
        ),
    ),
)
