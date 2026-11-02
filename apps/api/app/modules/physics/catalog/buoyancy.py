"""Verified fluid operations: absolute pressure, buoyancy, floating and capillarity."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

_FLUID_WORDS = ("water", "liquid", "fluid", "oil", "sea", "mercury", "alcohol")
# The fluid's density, named as the fluid's: "a block of density 2700 kg/m³"
# is the object's, and reading it as the water's would float a stone.
_RHO_FLUID = var(
    "rho",
    r"\rho",
    "kilogram / meter ** 3",
    words=_FLUID_WORDS,
    fallback="water_density",
    needs_words=True,
)
_G = var("g", "g", "meter / second ** 2", fallback="gravity")
_SUBMERGED = ("submerged", "immersed", "under water", "underwater", "fully in")

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "absolute_pressure_at_depth",
        "fluids",
        "Hydrostatic pressure",
        "P",
        base_latex=r"P = P_0 + \rho g h",
        assumptions=("the surface is open to the atmosphere",),
        expression="pres_atm + rho*g*depth",
        variables=(
            var("depth", "h", "meter"),
            _G,
            var(
                "pres_atm",
                "P_0",
                "pascal",
                words=("atmospheric", "atmosphere", "surface"),
                fallback="sea_level_pressure",
            ),
            _RHO_FLUID,
        ),
        binding=Binding(
            asks=("absolute pressure", "total pressure"),
            result=("pascal",),
            inputs=(frozenset({"depth", "g", "pres_atm", "rho"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "apparent_weight_submerged",
        "fluids",
        "Archimedes' principle",
        "W'",
        base_latex=r"W' = mg - \rho g V",
        assumptions=("the object is fully submerged",),
        expression="m*g - rho*g*volume",
        variables=(
            var("m", "m", "kilogram"),
            _G,
            _RHO_FLUID,
            var("volume", "V", "meter ** 3"),
        ),
        binding=Binding(
            asks=("apparent weight",),
            result=("newton",),
            inputs=(frozenset({"g", "m", "rho", "volume"}),),
            cues=_SUBMERGED,
            # Below zero it floats up: the scale reads nothing.
            nonnegative=True,
        ),
    ),
    # What a submerged object lacks of its weight is the upthrust, rho g V: a
    # 3 kg object that weighs 18 N under water displaces (29.4 - 18)/(rho g).
    formula(
        "volume_from_apparent_weight",
        "fluids",
        "Archimedes' principle",
        "V",
        base_latex=r"\rho g V = mg - W'",
        assumptions=("the object is fully submerged",),
        expression="(m*g - weight_app)/(rho*g)",
        variables=(
            var("m", "m", "kilogram"),
            var(
                "weight_app",
                "W'",
                "newton",
                words=("weighs", "apparent weight", "reads", "scale", "weight of"),
                needs_words=True,
            ),
            _G,
            _RHO_FLUID,
        ),
        binding=Binding(
            asks=("volume",),
            result=("meter ** 3",),
            inputs=(frozenset({"g", "m", "rho", "weight_app"}),),
            cues=_SUBMERGED,
            excludes=("float", "floats", "floating"),
            nonnegative=True,
            # Weighing more under water than in air is no upthrust.
            requires=("m*g - weight_app",),
        ),
    ),
    formula(
        "floating_fraction",
        "fluids",
        "Archimedes' principle",
        r"\frac{V_{sub}}{V}",
        base_latex=r"\frac{V_{sub}}{V} = \frac{\rho_{obj}}{\rho_{fluid}}",
        assumptions=("the object floats at rest",),
        expression="rho_object/rho",
        variables=(
            var(
                "rho_object",
                r"\rho_{obj}",
                "kilogram / meter ** 3",
                words=("ice", "wood", "block", "object", "cube", "iceberg", "body", "cork"),
                needs_words=True,
            ),
            _RHO_FLUID,
        ),
        binding=Binding(
            asks=("fraction", "proportion"),
            result=("dimensionless",),
            inputs=(frozenset({"rho", "rho_object"}),),
            cues=("float",),
            nonnegative=True,
            # More than all of it under: it sinks, and "floats" was wrong.
            at_most=1.0,
        ),
    ),
    formula(
        "capillary_rise",
        "fluids",
        "Jurin's law",
        "h",
        base_latex=r"h = \frac{2\gamma\cos\theta}{\rho g r}",
        expression="2*surface_tension*cos(angle)/(rho*g*r)",
        variants=(
            FormulaVariant(
                absent=frozenset({"angle"}),
                latex=r"h = \frac{2\gamma}{\rho g r}",
                expression="2*surface_tension/(rho*g*r)",
                assumptions=("a contact angle of 0°, as for water in clean glass",),
            ),
        ),
        variables=(
            var("angle", r"\theta", dimensionless=True, words=("contact angle", "angle")),
            _G,
            # The tube's radius, named: a diameter is twice it.
            var("r", "r", "meter", words=("radius",), needs_words=True),
            _RHO_FLUID,
            var("surface_tension", r"\gamma", "newton / meter"),
        ),
        binding=Binding(
            asks=("height", "rise", "how high"),
            result=("meter",),
            inputs=(
                frozenset({"g", "r", "rho", "surface_tension"}),
                frozenset({"angle", "g", "r", "rho", "surface_tension"}),
            ),
            cues=("capillary", "tube"),
        ),
    ),
)
