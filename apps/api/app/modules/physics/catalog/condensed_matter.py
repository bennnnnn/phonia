"""Electrons in solids and quantum statistics: the Fermi energy, Drude
conductivity, the Hall coefficient, the BCS gap and the occupation numbers."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "fermi_energy",
        "modern",
        "Fermi energy",
        "E_F",
        base_latex=r"E_F = \frac{\hbar^2}{2m_e}(3\pi^2 n)^{2/3}",
        assumptions=("a three-dimensional free-electron gas",),
        expression="(hbar**2/(2*m_e))*(3*pi**2*number_density)**(2/3)",
        variables=(
            var(
                "number_density",
                "n",
                "1 / meter ** 3",
                words=("density",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("fermi energy", "energy"),
            result=("joule",),
            inputs=(frozenset({"number_density"}),),
            cues=("fermi",),
            nonnegative=True,
        ),
    ),
    formula(
        "bcs_gap",
        "modern",
        "BCS gap",
        r"\Delta",
        base_latex=r"\Delta = 1.764\,k_B T_c",
        assumptions=("the weak-coupling approximation",),
        expression="1.764*k_B*temp",
        variables=(var("temp", "T_c", "kelvin", words=("critical",), needs_words=True),),
        binding=Binding(
            asks=("energy gap", "gap"),
            result=("joule",),
            inputs=(frozenset({"temp"}),),
            cues=("bcs",),
            nonnegative=True,
        ),
    ),
    formula(
        "drude_conductivity",
        "modern",
        "Drude conductivity",
        r"\sigma",
        base_latex=r"\sigma = \frac{n e^2 \tau}{m_e}",
        assumptions=("electrons",),
        expression="number_density*e_charge**2*scattering_time/m_e",
        variables=(
            var(
                "number_density",
                "n",
                "1 / meter ** 3",
                words=("density",),
                needs_words=True,
            ),
            var(
                "scattering_time",
                r"\tau",
                "second",
                words=("scattering", "relaxation"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("conductivity",),
            result=("siemens / meter",),
            inputs=(frozenset({"number_density", "scattering_time"}),),
            cues=("drude",),
            nonnegative=True,
        ),
    ),
    formula(
        "hall_coefficient",
        "magnetism",
        "Hall coefficient",
        "R_H",
        base_latex=r"R_H = -\frac{1}{ne}",
        assumptions=("electrons; the sign is negative",),
        expression="-1/(number_density*e_charge)",
        variables=(
            var(
                "number_density",
                "n",
                "1 / meter ** 3",
                words=("density",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("hall coefficient",),
            result=("meter ** 3 / coulomb",),
            inputs=(frozenset({"number_density"}),),
            cues=("hall coefficient",),
            nonnegative=False,
        ),
    ),
    formula(
        "fermi_dirac_occupation",
        "modern",
        "Fermi-Dirac occupation",
        "f",
        base_latex=r"f = \frac{1}{e^{(E-\mu)/k_B T}+1}",
        expression="1/(exp((state_energy-chemical_potential)/(k_B*temp))+1)",
        variables=(
            var("state_energy", "E", "joule", words=("energy",), needs_words=True),
            var(
                "chemical_potential",
                r"\mu",
                "joule",
                words=("chemical potential", "potential"),
                needs_words=True,
            ),
            var("temp", "T", "kelvin", words=("temperature",), needs_words=True),
        ),
        binding=Binding(
            asks=("occupation number", "occupation"),
            result=("dimensionless",),
            inputs=(frozenset({"chemical_potential", "state_energy", "temp"}),),
            cues=("fermi-dirac", "fermi dirac"),
            nonnegative=True,
            at_most=1.0,
        ),
    ),
    formula(
        "bose_einstein_occupation",
        "modern",
        "Bose-Einstein occupation",
        "f",
        base_latex=r"f = \frac{1}{e^{(E-\mu)/k_B T}-1}",
        assumptions=("E is above the chemical potential",),
        expression="1/(exp((state_energy-chemical_potential)/(k_B*temp))-1)",
        variables=(
            var("state_energy", "E", "joule", words=("energy",), needs_words=True),
            var(
                "chemical_potential",
                r"\mu",
                "joule",
                words=("chemical potential", "potential"),
                needs_words=True,
            ),
            var("temp", "T", "kelvin", words=("temperature",), needs_words=True),
        ),
        binding=Binding(
            asks=("occupation number", "occupation"),
            result=("dimensionless",),
            inputs=(frozenset({"chemical_potential", "state_energy", "temp"}),),
            cues=("bose",),
            nonnegative=True,
        ),
    ),
)
