"""Particle physics: pair production, the Higgs mass and the strong coupling."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "pair_production_threshold",
        "modern",
        "Pair-production threshold",
        "E",
        base_latex=r"E = 2mc^2",
        assumptions=("a particle and its antiparticle created at rest",),
        expression="2*m*c_light**2",
        variables=(var("m", "m", "kilogram", fallback="particle_mass"),),
        binding=Binding(
            asks=("threshold energy", "pair-production threshold"),
            result=("joule",),
            inputs=(frozenset({"m"}),),
            cues=("pair production", "pair-production"),
            nonnegative=True,
        ),
    ),
    formula(
        "higgs_mass",
        "modern",
        "Higgs mass",
        "m_H",
        base_latex=r"m_H = \frac{v\sqrt{2\lambda}}{c^2}",
        assumptions=("the Mexican-hat potential, mass in kilograms",),
        expression="vacuum_expectation*sqrt(2*self_coupling)/c_light**2",
        variables=(
            var(
                "vacuum_expectation",
                "v",
                "joule",
                words=("vacuum", "expectation"),
                needs_words=True,
            ),
            var(
                "self_coupling",
                r"\lambda",
                dimensionless=True,
                words=("coupling",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("higgs mass",),
            result=("kilogram",),
            inputs=(frozenset({"self_coupling", "vacuum_expectation"}),),
            cues=("higgs",),
            nonnegative=True,
        ),
    ),
    formula(
        "strong_coupling",
        "modern",
        "One-loop strong coupling",
        r"\alpha_s",
        base_latex=r"\alpha_s = \frac{12\pi}{(33-2n_f)\ln(Q^2/\Lambda^2)}",
        assumptions=("one-loop running with the stated flavor count",),
        expression="12*pi/((33-2*n_flavors)*log((momentum_scale/lambda_qcd)**2))",
        variables=(
            var(
                "momentum_scale",
                "Q",
                "joule",
                words=("momentum",),
                needs_words=True,
            ),
            var(
                "lambda_qcd",
                r"\Lambda",
                "joule",
                words=("lambda",),
                needs_words=True,
            ),
            var(
                "n_flavors",
                "n_f",
                dimensionless=True,
                words=("flavor", "flavour"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("strong coupling",),
            result=("dimensionless",),
            inputs=(frozenset({"lambda_qcd", "momentum_scale", "n_flavors"}),),
            cues=("qcd",),
            nonnegative=True,
        ),
    ),
)
