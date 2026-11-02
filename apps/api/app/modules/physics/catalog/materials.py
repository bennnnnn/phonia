"""Verified materials operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "stress",
        "materials",
        "Stress formula",
        "\\sigma",
        variables=(
            var("F", "F", "newton"),
            var("area", "A", "meter ** 2"),
        ),
    ),
    formula(
        "strain",
        "materials",
        "Strain formula",
        "\\varepsilon",
        variables=(
            var("L0", "L_0", "meter"),
            var("dL", r"\Delta L", "meter"),
        ),
    ),
    formula(
        "youngs_modulus",
        "materials",
        "Young's modulus formula",
        "E",
        variables=(
            var("sigma", r"\sigma", "pascal"),
            var("strain", r"\epsilon", dimensionless=True),
        ),
    ),
    formula(
        "shear_modulus",
        "materials",
        "Shear-modulus formula",
        "G",
        base_latex=r"G = \frac{\tau}{\gamma}",
        expression="shear_stress/shear_strain",
        variables=(
            var("shear_stress", r"\tau", "pascal", words=("shear stress",), needs_words=True),
            var(
                "shear_strain",
                r"\gamma",
                dimensionless=True,
                words=("shear strain",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("shear modulus",),
            result=("pascal",),
            inputs=(frozenset({"shear_strain", "shear_stress"}),),
            cues=("shear modulus",),
            nonnegative=True,
        ),
    ),
    formula(
        "bulk_modulus",
        "materials",
        "Bulk-modulus formula",
        "B",
        base_latex=r"B = \frac{\Delta P}{\Delta V/V}",
        assumptions=("the volume change is a decrease",),
        expression="delta_pres*volume/dV",
        variants=(
            FormulaVariant(
                latex=r"B = \frac{\Delta P}{\Delta V/V}",
                present=frozenset({"volume_strain"}),
                absent=frozenset({"volume", "dV"}),
                expression="delta_pres/volume_strain",
            ),
        ),
        variables=(
            var("delta_pres", r"\Delta P", "pascal"),
            var("volume", "V", "meter ** 3", words=("original",), needs_words=True),
            var("dV", r"\Delta V", "meter ** 3", words=("change", "decrease"), needs_words=True),
            var(
                "volume_strain",
                r"\Delta V/V",
                dimensionless=True,
                words=("volume strain", "volumetric strain"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("bulk modulus",),
            result=("pascal",),
            inputs=(
                frozenset({"dV", "delta_pres", "volume"}),
                frozenset({"delta_pres", "volume_strain"}),
            ),
            cues=("bulk modulus",),
            nonnegative=True,
        ),
    ),
    formula(
        "poisson_ratio",
        "materials",
        "Poisson's ratio",
        r"\nu",
        base_latex=r"\nu = \frac{\varepsilon_{lat}}{\varepsilon_{axial}}",
        expression="lateral_strain/axial_strain",
        variables=(
            var(
                "lateral_strain",
                r"\varepsilon_{lat}",
                dimensionless=True,
                words=("lateral",),
                needs_words=True,
            ),
            var(
                "axial_strain",
                r"\varepsilon_{axial}",
                dimensionless=True,
                words=("axial", "longitudinal"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("poisson's ratio", "poissons ratio", "poisson ratio"),
            result=("dimensionless",),
            inputs=(frozenset({"axial_strain", "lateral_strain"}),),
            cues=("poisson",),
            nonnegative=True,
            at_most=0.5,
        ),
    ),
)
