"""Plasmas: the plasma frequency, the Debye length and the Alfvén speed."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "plasma_frequency",
        "magnetism",
        "Plasma frequency",
        r"\omega_p",
        base_latex=r"\omega_p = \sqrt{\frac{n e^2}{\varepsilon_0 m_e}}",
        assumptions=("electrons in a cold plasma",),
        expression="sqrt(number_density*e_charge**2/(epsilon_0*m_e))",
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
            asks=("plasma frequency", "angular frequency"),
            result=("radian / second",),
            inputs=(frozenset({"number_density"}),),
            cues=("plasma frequency",),
            nonnegative=True,
        ),
    ),
    formula(
        "debye_length",
        "magnetism",
        "Debye length",
        r"\lambda_D",
        base_latex=r"\lambda_D = \sqrt{\frac{\varepsilon_0 k_B T}{n e^2}}",
        assumptions=("one mobile species",),
        expression="sqrt(epsilon_0*k_B*temp/(number_density*e_charge**2))",
        variables=(
            var(
                "number_density",
                "n",
                "1 / meter ** 3",
                words=("density",),
                needs_words=True,
            ),
            var("temp", "T", "kelvin", words=("temperature",), needs_words=True),
        ),
        binding=Binding(
            asks=("debye length", "length"),
            result=("meter",),
            inputs=(frozenset({"number_density", "temp"}),),
            cues=("debye",),
            nonnegative=True,
        ),
    ),
    formula(
        "alfven_speed",
        "magnetism",
        "Alfvén speed",
        "v_A",
        base_latex=r"v_A = \frac{B}{\sqrt{\mu_0\rho}}",
        expression="b_field/sqrt(mu_0*rho)",
        variables=(
            var("b_field", "B", "tesla"),
            var("rho", r"\rho", "kilogram / meter ** 3", words=("density",), needs_words=True),
        ),
        binding=Binding(
            asks=("alfven speed", "speed"),
            result=("meter / second",),
            inputs=(frozenset({"b_field", "rho"}),),
            cues=("alfven", "alven"),
            nonnegative=True,
        ),
    ),
)
