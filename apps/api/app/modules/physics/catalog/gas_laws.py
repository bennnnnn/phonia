"""Verified gas laws for a fixed amount of gas, and kinetic theory."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

# The state before and the state after: "occupies 4 L at 2 atm", "is
# compressed to 2 L". The words before each value say which state it is.
_BEFORE = ("initially", "initial", "originally", "at first", "from", "occupies", "at")
# A chemistry class labels the two states with subscripts: "P1 = 2 atm, V2 = 6 L".
_FIRST = {"pres1": ("p1",), "vol1": ("v1",), "temp_initial": ("t1",)}
_SECOND = {"pres2": ("p2",), "vol2": ("v2",), "temp_final": ("t2",)}
_AFTER = (
    "to",
    "new",
    "final",
    "finally",
    "becomes",
    "until",
    "increased to",
    "reduced to",
    "decreased to",
    "compressed to",
    "expands to",
    "raised to",
    "changed to",
)
_P1 = var("pres1", "P_1", "pascal", words=(*_FIRST["pres1"], *_BEFORE))
_P2 = var("pres2", "P_2", "pascal", words=(*_SECOND["pres2"], *_AFTER))
_V1 = var("vol1", "V_1", "meter ** 3", words=(*_FIRST["vol1"], *_BEFORE))
_V2 = var("vol2", "V_2", "meter ** 3", words=(*_SECOND["vol2"], *_AFTER))
_T1 = var("temp_initial", "T_1", "kelvin", words=(*_FIRST["temp_initial"], *_BEFORE))
_T2 = var("temp_final", "T_2", "kelvin", words=(*_SECOND["temp_final"], *_AFTER))
_SAME_TEMPERATURE = (
    "constant temperature",
    "temperature is constant",
    "temperature remains constant",
    "temperature is kept constant",
    "isothermal",
    "boyle",
)
_SAME_PRESSURE = (
    "constant pressure",
    "pressure is constant",
    "pressure remains constant",
    "pressure is kept constant",
    "charles",
)
_SAME_VOLUME = (
    "constant volume",
    "volume is constant",
    "fixed volume",
    "sealed",
    "rigid",
    "gay-lussac",
    "gay lussac",
)
_NEW_VOLUME = ("new volume", "final volume", "volume", "v2")
_NEW_PRESSURE = ("new pressure", "final pressure", "pressure", "p2")
_NEW_TEMPERATURE = ("new temperature", "final temperature", "temperature", "t2")
_TEMPERATURE = var("temp", "T", "kelvin")
_MOLAR_MASS = var("molar_mass", "M", "kilogram / mole")
_MOLECULE = ("molecule", "gas", "particle", "atom")


def _state_law(
    operation: str,
    law: str,
    symbol: str,
    base: str,
    expression: str,
    asks: tuple[str, ...],
    result: str,
    variables: tuple[str, ...],
    cues: tuple[str, ...],
) -> FormulaSpec:
    known = {spec.name: spec for spec in (_P1, _P2, _V1, _V2, _T1, _T2)}
    return formula(
        operation,
        "thermal",
        law,
        symbol,
        base_latex=base,
        assumptions=("a fixed amount of ideal gas, absolute temperatures",),
        expression=expression,
        variables=tuple(known[name] for name in variables),
        binding=Binding(
            asks=asks,
            result=(result,),
            inputs=(frozenset(variables),),
            cues=cues,
            nonnegative=True,
        ),
    )


SPECS: tuple[FormulaSpec, ...] = (
    _state_law(
        "boyle_volume",
        "Boyle's law",
        "V_2",
        "P_1 V_1 = P_2 V_2",
        "pres1*vol1/pres2",
        _NEW_VOLUME,
        "meter ** 3",
        ("pres1", "pres2", "vol1"),
        _SAME_TEMPERATURE,
    ),
    _state_law(
        "boyle_pressure",
        "Boyle's law",
        "P_2",
        "P_1 V_1 = P_2 V_2",
        "pres1*vol1/vol2",
        _NEW_PRESSURE,
        "pascal",
        ("pres1", "vol1", "vol2"),
        _SAME_TEMPERATURE,
    ),
    _state_law(
        "charles_volume",
        "Charles's law",
        "V_2",
        r"\frac{V_1}{T_1} = \frac{V_2}{T_2}",
        "vol1*temp_final/temp_initial",
        _NEW_VOLUME,
        "meter ** 3",
        ("temp_final", "temp_initial", "vol1"),
        _SAME_PRESSURE,
    ),
    _state_law(
        "charles_temperature",
        "Charles's law",
        "T_2",
        r"\frac{V_1}{T_1} = \frac{V_2}{T_2}",
        "temp_initial*vol2/vol1",
        _NEW_TEMPERATURE,
        "kelvin",
        ("temp_initial", "vol1", "vol2"),
        _SAME_PRESSURE,
    ),
    _state_law(
        "gay_lussac_pressure",
        "Gay-Lussac's law",
        "P_2",
        r"\frac{P_1}{T_1} = \frac{P_2}{T_2}",
        "pres1*temp_final/temp_initial",
        _NEW_PRESSURE,
        "pascal",
        ("pres1", "temp_final", "temp_initial"),
        _SAME_VOLUME,
    ),
    _state_law(
        "gay_lussac_temperature",
        "Gay-Lussac's law",
        "T_2",
        r"\frac{P_1}{T_1} = \frac{P_2}{T_2}",
        "temp_initial*pres2/pres1",
        _NEW_TEMPERATURE,
        "kelvin",
        ("pres1", "pres2", "temp_initial"),
        _SAME_VOLUME,
    ),
    # Every state value stated: nothing is held constant, so no cue is needed.
    _state_law(
        "combined_gas_volume",
        "Combined gas law",
        "V_2",
        r"\frac{P_1 V_1}{T_1} = \frac{P_2 V_2}{T_2}",
        "pres1*vol1*temp_final/(temp_initial*pres2)",
        _NEW_VOLUME,
        "meter ** 3",
        ("pres1", "pres2", "temp_final", "temp_initial", "vol1"),
        ("gas",),
    ),
    _state_law(
        "combined_gas_pressure",
        "Combined gas law",
        "P_2",
        r"\frac{P_1 V_1}{T_1} = \frac{P_2 V_2}{T_2}",
        "pres1*vol1*temp_final/(temp_initial*vol2)",
        _NEW_PRESSURE,
        "pascal",
        ("pres1", "temp_final", "temp_initial", "vol1", "vol2"),
        ("gas",),
    ),
    formula(
        "rms_speed",
        "thermal",
        "Kinetic theory of gases",
        r"v_{\mathrm{rms}}",
        base_latex=r"v_{\mathrm{rms}} = \sqrt{\frac{3RT}{M}}",
        assumptions=("an ideal gas; M is the molar mass",),
        expression="sqrt(3*R_gas*temp/molar_mass)",
        variables=(_MOLAR_MASS, _TEMPERATURE),
        binding=Binding(
            asks=("rms speed", "r.m.s. speed", "root mean square speed", "root-mean-square speed"),
            result=("meter / second",),
            inputs=(frozenset({"molar_mass", "temp"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "mean_molecular_speed",
        "thermal",
        "Kinetic theory of gases",
        r"\bar{v}",
        base_latex=r"\bar{v} = \sqrt{\frac{8RT}{\pi M}}",
        assumptions=("an ideal gas; M is the molar mass",),
        expression="sqrt(8*R_gas*temp/(pi*molar_mass))",
        variables=(_MOLAR_MASS, _TEMPERATURE),
        binding=Binding(
            asks=("mean speed", "average speed"),
            result=("meter / second",),
            inputs=(frozenset({"molar_mass", "temp"}),),
            cues=_MOLECULE,
            nonnegative=True,
        ),
    ),
    formula(
        "most_probable_speed",
        "thermal",
        "Kinetic theory of gases",
        r"v_p",
        base_latex=r"v_p = \sqrt{\frac{2RT}{M}}",
        assumptions=("an ideal gas; M is the molar mass",),
        expression="sqrt(2*R_gas*temp/molar_mass)",
        variables=(_MOLAR_MASS, _TEMPERATURE),
        binding=Binding(
            asks=("most probable speed",),
            result=("meter / second",),
            inputs=(frozenset({"molar_mass", "temp"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "mean_molecular_kinetic_energy",
        "thermal",
        "Kinetic theory of gases",
        r"\langle E_k \rangle",
        base_latex=r"\langle E_k \rangle = \frac{3}{2}k_B T",
        assumptions=("translational kinetic energy of one molecule of an ideal gas",),
        expression="3*k_B*temp/2",
        variables=(_TEMPERATURE,),
        binding=Binding(
            asks=(
                "average kinetic energy",
                "mean kinetic energy",
                "average translational kinetic energy",
                "mean translational kinetic energy",
            ),
            result=("joule",),
            inputs=(frozenset({"temp"}),),
            cues=_MOLECULE,
            nonnegative=True,
        ),
    ),
    formula(
        "diatomic_internal_energy",
        "thermal",
        "Equipartition of energy",
        "U",
        base_latex=r"U = \frac{5}{2}nRT",
        assumptions=("a diatomic ideal gas near room temperature (no vibration)",),
        expression="5*moles*R_gas*temp/2",
        variables=(var("moles", "n", "mole"), _TEMPERATURE),
        binding=Binding(
            asks=("internal energy",),
            result=("joule",),
            inputs=(frozenset({"moles", "temp"}),),
            cues=("diatomic",),
            nonnegative=True,
        ),
    ),
)
