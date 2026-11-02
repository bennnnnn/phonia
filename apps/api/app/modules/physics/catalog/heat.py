"""Verified heat operations: Q = mcΔT for each unknown, mixtures and latent heat."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

_LAW = "Specific-heat equation"
_RISE = ("by", "rise", "change", "increase", "raised", "heated", "cooled", "difference")
_HEAT = var("heat", "Q", "joule")
_MASS = var("m", "m", "kilogram")
_C = var("c_heat", "c", "joule / kilogram / kelvin", fallback="water_specific_heat")
_DELTA_TEMP = var("delta_temp", r"\Delta T", "kelvin", words=_RISE, needs_words=True)
_LATENT = var("latent_heat", "L", "joule / kilogram")
_PHASE_CHANGE = ("melt", "boil", "freez", "evaporat", "vapori", "condens", "latent", "solidif")
# What a calorimetry question drops into the water.
_OBJECT = (
    "metal",
    "piece",
    "block",
    "sample",
    "ball",
    "object",
    "copper",
    "iron",
    "aluminium",
    "aluminum",
    "lead",
    "brass",
    "steel",
    "dropped",
    "heated to",
)


def _heat_law(
    operation: str,
    symbol: str,
    expression: str,
    asks: tuple[str, ...],
    result: str,
    *variables: str,
) -> FormulaSpec:
    known = {spec.name: spec for spec in (_HEAT, _MASS, _C, _DELTA_TEMP)}
    return formula(
        operation,
        "thermal",
        _LAW,
        symbol,
        base_latex=r"Q = mc\Delta T",
        expression=expression,
        variables=tuple(known[name] for name in variables),
        binding=Binding(
            asks=asks,
            result=(result,),
            inputs=(frozenset(variables),),
            excludes=_PHASE_CHANGE,
            nonnegative=True,
        ),
    )


# Laws that hold only when every sample is water. The binder drops them when the question names
# any other substance (``bodies.names_only_water``): water + ethanol was answered as water + water.
WATER_ONLY = frozenset({"water_mixture_temperature"})

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "heat_energy",
        "thermal",
        _LAW,
        "Q",
        base_latex=r"Q = mc\Delta T",
        expression="m*c_heat*delta_temp",
        variants=(
            FormulaVariant(
                present=frozenset({"temp_initial", "temp_final"}),
                expression="m*c_heat*(temp_final-temp_initial)",
            ),
        ),
        variables=(
            _C,
            _DELTA_TEMP,
            _MASS,
            var("temp_initial", "T_1", "kelvin", words=("from", "initially", "starting at")),
            var("temp_final", "T_2", "kelvin", words=("to", "until", "reaches", "final")),
        ),
        binding=Binding(
            asks=("heat energy", "thermal energy", "energy", "heat"),
            result=("joule",),
            inputs=(
                frozenset({"c_heat", "delta_temp", "m"}),
                frozenset({"c_heat", "m", "temp_initial", "temp_final"}),
            ),
            excludes=("melt", "boil", "freez", "evaporat", "condens", "latent"),
            negative_detail="released",
        ),
    ),
    _heat_law(
        "specific_heat_from_energy",
        "c",
        "heat/(m*delta_temp)",
        ("specific heat capacity", "specific heat"),
        "joule / kilogram / kelvin",
        "heat",
        "m",
        "delta_temp",
    ),
    _heat_law(
        "temperature_change_from_heat",
        r"\Delta T",
        "heat/(m*c_heat)",
        (
            "temperature rise",
            "temperature change",
            "temperature increase",
            "change in temperature",
            "rise in temperature",
            "increase in temperature",
        ),
        "kelvin",
        "heat",
        "m",
        "c_heat",
    ),
    _heat_law(
        "mass_from_heat",
        "m",
        "heat/(c_heat*delta_temp)",
        ("mass",),
        "kilogram",
        "heat",
        "c_heat",
        "delta_temp",
    ),
    # A heater's time to warm a mass: t = mcΔT/P, with no heat lost. A 2 kW
    # kettle warms 1.5 kg of water by 80 K in 251 s.
    formula(
        "heating_time",
        "thermal",
        "Electrical heating",
        "t",
        base_latex=r"P t = m c \Delta T",
        assumptions=("all the electrical energy heats the water; none is lost",),
        expression="m*c_heat*(temp_final - temp_initial)/power",
        variables=(
            _MASS,
            _C,
            var("power", "P", "watt"),
            var("temp_initial", "T_1", "kelvin", words=("from", "initially", "starting at")),
            var("temp_final", "T_2", "kelvin", words=("to", "until", "reaches", "final")),
        ),
        binding=Binding(
            asks=("how long", "time"),
            result=("second",),
            inputs=(frozenset({"c_heat", "m", "power", "temp_final", "temp_initial"}),),
            cues=("kettle", "heater", "heating element", "immersion", "heats"),
            excludes=_PHASE_CHANGE,
            nonnegative=True,
        ),
    ),
    # Two amounts of water mixed: the heat one loses the other gains. Both
    # are water, so c cancels; any other substance named rules this out (WATER_ONLY).
    formula(
        "water_mixture_temperature",
        "thermal",
        "Conservation of energy in mixing",
        "T",
        base_latex=r"m_1 c (T_1 - T) = m_2 c (T - T_2)",
        assumptions=("both are water and no heat is lost to the surroundings",),
        expression="(m1*temp_a + m2*temp_b)/(m1 + m2)",
        variables=(
            var("m1", "m_1", "kilogram"),
            var("m2", "m_2", "kilogram"),
            var("temp_a", "T_1", "kelvin"),
            var("temp_b", "T_2", "kelvin"),
        ),
        binding=Binding(
            asks=(
                "final temperature",
                "temperature of the mixture",
                "equilibrium temperature",
                "common temperature",
                "resulting temperature",
                "temperature",
                "final temp",
            ),
            result=("kelvin",),
            inputs=(frozenset({"m1", "m2", "temp_a", "temp_b"}),),
            cues=("water",),
            excludes=("block", "specific heat"),
            interchangeable=("m1", "m2", "temp_a", "temp_b"),
            nonnegative=True,
        ),
    ),
    # A hot object dropped into water: the heat the water gains is the heat the object loses,
    # m_w c_w (T_f - T_w) = m c (T - T_f), solved for the object's c.
    formula(
        "calorimetry_specific_heat",
        "thermal",
        "Calorimetry (heat lost = heat gained)",
        "c",
        base_latex=r"m c (T - T_f) = m_w c_w (T_f - T_w)",
        assumptions=("no heat is lost to the surroundings or the container",),
        expression="m_water*c_water*(temp_final - temp_water)/(m*(temp_object - temp_final))",
        variables=(
            var("m", "m", "kilogram", words=_OBJECT, needs_words=True),
            var("temp_object", "T", "kelvin", words=_OBJECT, needs_words=True),
            var("m_water", "m_w", "kilogram", words=("water",), needs_words=True),
            var("temp_water", "T_w", "kelvin", words=("water",), needs_words=True),
            var(
                "temp_final",
                "T_f",
                "kelvin",
                words=("final", "equilibrium", "reaches", "settles", "mixture"),
                needs_words=True,
            ),
            var("c_water", "c_w", "joule / kilogram / kelvin", fallback="calorimeter_water"),
        ),
        binding=Binding(
            asks=(
                "specific heat capacity of the metal",
                "specific heat of the metal",
                "specific heat capacity",
                "specific heat",
            ),
            result=("joule / kilogram / kelvin",),
            inputs=(
                frozenset({"m", "temp_object", "m_water", "temp_water", "temp_final", "c_water"}),
            ),
            cues=("water",),
            excludes=("ice", "steam"),
            nonnegative=True,
        ),
    ),
    formula(
        "latent_heat_from_energy",
        "thermal",
        "Latent-heat equation",
        "L",
        base_latex="Q = mL",
        expression="heat/m",
        variables=(_HEAT, _MASS),
        binding=Binding(
            asks=(
                "specific latent heat",
                "latent heat of fusion",
                "latent heat of vaporisation",
                "latent heat of vaporization",
                "latent heat",
            ),
            result=("joule / kilogram",),
            inputs=(frozenset({"heat", "m"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "mass_from_latent_heat",
        "thermal",
        "Latent-heat equation",
        "m",
        base_latex="Q = mL",
        expression="heat/latent_heat",
        variables=(_HEAT, _LATENT),
        binding=Binding(
            asks=("mass",),
            result=("kilogram",),
            inputs=(frozenset({"heat", "latent_heat"}),),
            cues=_PHASE_CHANGE,
            nonnegative=True,
        ),
    ),
    formula(
        "newton_cooling",
        "thermal",
        "Newton's law of cooling",
        "T",
        base_latex=r"T = T_e + (T_0 - T_e)e^{-t/\tau}",
        expression="temp_env + (temp - temp_env)*exp(-t/cool_time)",
        variables=(
            var(
                "temp",
                "T_0",
                "kelvin",
                words=("starts", "initial", "object"),
                needs_words=True,
            ),
            var(
                "temp_env",
                "T_e",
                "kelvin",
                words=("room", "ambient", "surrounding", "environment", "outside"),
                needs_words=True,
            ),
            var("t", "t", "second", words=("after", "later"), needs_words=True),
            var("cool_time", r"\tau", "second", words=("time constant",), needs_words=True),
        ),
        binding=Binding(
            asks=("temperature",),
            result=("kelvin",),
            inputs=(frozenset({"cool_time", "t", "temp", "temp_env"}),),
            cues=("law of cooling",),
            nonnegative=True,
        ),
    ),
)
