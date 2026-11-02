"""Verified thermal operations."""

from __future__ import annotations

from app.services.law_binding.spec import (
    Binding,
    FormulaSpec,
    FormulaVariant,
    VariableSpec,
    bind,
    formula,
    var,
)

_GAS = ("gas",)
# A temperature change is named: "heated by 50 K". A lone "at 20 °C" is a
# temperature, and reading it as the change would answer another question.
_RISE = ("by", "rise", "change", "increase", "raised", "heated", "cooled", "difference")
_DELTA_TEMP = var("delta_temp", r"\Delta T", "kelvin", words=_RISE, needs_words=True)

_ALPHA = var(
    "alpha",
    r"\alpha",
    "1 / kelvin",
    words=("linear expansivity", "linear expansion", "coefficient of linear"),
    needs_words=True,
)

_MOLECULES = ("molecules", "particles")

_N = var(
    "molecule_count",
    "N",
    dimensionless=True,
    words=("molecules", "particles", "molecule"),
    needs_words=True,
)

_TEMP = var("temp", "T", "kelvin")

_VOLUME = var("volume", "V", "meter ** 3")

_PRESSURE = var("pres", "P", "pascal")


def _molecule_gas(
    operation: str,
    symbol: str,
    expression: str,
    asks: tuple[str, ...],
    result: str,
    variables: tuple[VariableSpec, ...],
    inputs: frozenset[str],
) -> FormulaSpec:
    return formula(
        operation,
        "thermal",
        "Ideal-gas law",
        symbol,
        base_latex=r"PV = N k_B T",
        assumptions=("an ideal gas",),
        expression=expression,
        variables=variables,
        binding=Binding(
            asks=asks,
            result=(result,),
            inputs=(inputs,),
            cues=_MOLECULES,
            excludes=("particle in a box", "infinite box"),
            nonnegative=True,
        ),
    )


SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "ideal_gas_pressure",
        "thermal",
        "Ideal-gas law",
        "P",
        base_latex="PV = nRT",
        expression="moles*R_gas*temp/volume",
        variables=(
            var("moles", "n", "mole"),
            var("temp", "T", "kelvin"),
            var("volume", "V", "meter ** 3"),
        ),
        binding=bind(("pressure",), "pascal", "moles", "temp", "volume", cues=_GAS),
    ),
    formula(
        "ideal_gas_volume",
        "thermal",
        "Ideal-gas law",
        "V",
        base_latex="PV = nRT",
        expression="moles*R_gas*temp/pres",
        variables=(
            var("moles", "n", "mole"),
            var("pres", "P", "pascal"),
            var("temp", "T", "kelvin"),
        ),
        binding=bind(("volume",), "meter ** 3", "moles", "pres", "temp", cues=_GAS),
    ),
    formula(
        "ideal_gas_amount",
        "thermal",
        "Ideal-gas law",
        "n",
        base_latex="PV = nRT",
        expression="pres*volume/(R_gas*temp)",
        variables=(
            var("pres", "P", "pascal"),
            var("temp", "T", "kelvin"),
            var("volume", "V", "meter ** 3"),
        ),
        binding=bind(
            ("number of moles", "amount of gas", "amount of substance", "moles", "amount"),
            "mole",
            "pres",
            "temp",
            "volume",
            cues=_GAS,
        ),
    ),
    formula(
        "ideal_gas_temperature",
        "thermal",
        "Ideal-gas law",
        "T",
        base_latex="PV = nRT",
        expression="pres*volume/(moles*R_gas)",
        variables=(
            var("moles", "n", "mole"),
            var("pres", "P", "pascal"),
            var("volume", "V", "meter ** 3"),
        ),
        binding=bind(("temperature",), "kelvin", "moles", "pres", "volume", cues=_GAS),
    ),
    formula(
        "monatomic_energy",
        "thermal",
        "Monatomic internal energy",
        "U",
        base_latex=r"U = \frac{3}{2}nRT",
        assumptions=("monatomic ideal gas",),
        variables=(
            var("moles", "n", "mole"),
            var("temp", "T", "kelvin"),
        ),
    ),
    formula(
        "isobaric_work",
        "thermal",
        "Isobaric work",
        "W",
        base_latex=r"W = P\Delta V",
        assumptions=("work done by the gas",),
        variables=(
            var("pres", "P", "pascal"),
            var("vol1", "V_1", "meter ** 3"),
            var("vol2", "V_2", "meter ** 3"),
        ),
        binding=Binding(
            asks=("work done by the gas", "work done", "work"),
            result=("joule",),
            inputs=(frozenset({"pres", "vol1", "vol2"}),),
            cues=("constant pressure", "isobaric"),
            # "from 0.01 m^3 to 0.03 m^3": the first volume is the start.
            interchangeable=("vol1", "vol2"),
            negative_detail="done on the gas",
        ),
    ),
    formula(
        "adiabatic_pressure",
        "thermal",
        "Adiabatic condition",
        "P_2",
        base_latex=r"P_1 V_1^\gamma = P_2 V_2^\gamma",
        assumptions=("reversible adiabatic process with gamma stated",),
        variables=(
            var("gamma_gas", r"\gamma", dimensionless=True),
            var("pres1", "P_1", "pascal"),
            var("vol1", "V_1", "meter ** 3"),
            var("vol2", "V_2", "meter ** 3"),
        ),
    ),
    formula(
        "adiabatic_volume",
        "thermal",
        "Adiabatic condition",
        "V_2",
        base_latex=r"P_1 V_1^\gamma = P_2 V_2^\gamma",
        assumptions=("reversible adiabatic process with gamma stated",),
        variables=(
            var("gamma_gas", r"\gamma", dimensionless=True),
            var("pres1", "P_1", "pascal"),
            var("pres2", "P_2", "pascal"),
            var("vol1", "V_1", "meter ** 3"),
        ),
    ),
    formula(
        "refrigerator_cop",
        "thermal",
        "Refrigerator coefficient of performance",
        "COP",
        base_latex=r"COP = \frac{T_C}{T_H - T_C}",
        assumptions=("Carnot refrigerator, absolute temperatures",),
        variables=(
            var("temp", "T_H", "kelvin"),
            var("temp_env", "T_C", "kelvin"),
        ),
    ),
    # A refrigerator's coefficient of performance from what it does, not its
    # reservoirs: the heat it moves per joule of work, Q_c/W. 300 J out for
    # 100 J of work is 3.
    formula(
        "refrigerator_cop_from_heat",
        "thermal",
        "Refrigerator coefficient of performance",
        "COP",
        base_latex=r"COP = \frac{Q_C}{W}",
        expression="q_cold/work_in",
        variables=(
            var(
                "q_cold",
                "Q_C",
                "joule",
                words=("removes", "extracts", "takes", "from inside", "absorbs", "heat"),
                needs_words=True,
            ),
            var(
                "work_in",
                "W",
                "joule",
                words=("work", "using", "uses", "consumes", "input"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("coefficient of performance", "cop"),
            result=("dimensionless",),
            inputs=(frozenset({"q_cold", "work_in"}),),
            cues=("refrigerator", "fridge", "freezer", "air conditioner"),
            excludes=("heat pump", "kelvin"),
            nonnegative=True,
        ),
    ),
    formula(
        "heat_pump_cop",
        "thermal",
        "Heat-pump coefficient of performance",
        "COP",
        base_latex=r"COP = \frac{T_H}{T_H - T_C}",
        assumptions=("Carnot heat pump, absolute temperatures",),
        variables=(
            var("temp", "T_H", "kelvin"),
            var("temp_env", "T_C", "kelvin"),
        ),
    ),
    formula(
        "thermal_efficiency",
        "thermal",
        "Thermal-efficiency formula",
        "\\eta",
        variables=(
            var("Q_in", r"Q_{\mathrm{in}}", "joule"),
            var("W_out", r"W_{\mathrm{out}}", "joule"),
        ),
    ),
    formula(
        "linear_expansion",
        "thermal",
        "Linear thermal-expansion law",
        "\\Delta L",
        base_latex="\\Delta L = \\alpha L_0\\Delta T",
        variables=(
            var("L0", "L_0", "meter"),
            var("alpha", r"\alpha", "1 / kelvin"),
            _DELTA_TEMP,
        ),
        binding=Binding(
            asks=(
                "change in length",
                "increase in length",
                "expansion",
                "extension",
                "how much longer",
                # "How much does a 2 m copper rod expand"
                "expand",
            ),
            result=("meter",),
            inputs=(frozenset({"L0", "alpha", "delta_temp"}),),
        ),
    ),
    # Linear expansion between two stated temperatures: ΔL = alpha L₀ (T₂ - T₁).
    formula(
        "linear_expansion_temperatures",
        "thermal",
        "Linear thermal-expansion law",
        r"\Delta L",
        base_latex=r"\Delta L = \alpha L_0 (T_2 - T_1)",
        expression="alpha*L0*(temp_final - temp_initial)",
        variables=(
            var("L0", "L_0", "meter"),
            var("alpha", r"\alpha", "1 / kelvin"),
            var("temp_initial", "T_1", "kelvin", words=("from", "initially", "at")),
            var("temp_final", "T_2", "kelvin", words=("to", "until", "reaches")),
        ),
        binding=Binding(
            asks=(
                "change in length",
                "increase in length",
                "expansion",
                "extension",
                "how much longer",
                "lengthen",
                "expand",
            ),
            result=("meter",),
            inputs=(frozenset({"L0", "alpha", "temp_final", "temp_initial"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "latent_heat",
        "thermal",
        "Latent-heat equation",
        "Q",
        base_latex="Q = mL",
        variables=(
            var("latent_heat", "L", "joule / kilogram"),
            var("m", "m", "kilogram"),
            # "Melt 2 kg of ice at 0 °C": the temperature of the change is
            # stated, and Q = mL does not use it.
            var("temp_phase", "T", "kelvin", words=("at",), needs_words=True),
        ),
        binding=Binding(
            asks=("heat energy", "energy", "heat"),
            result=("joule",),
            inputs=(
                frozenset({"latent_heat", "m"}),
                frozenset({"latent_heat", "m", "temp_phase"}),
            ),
            cues=("melt", "boil", "freez", "evaporat", "vapori", "condens", "latent", "solidif"),
            nonnegative=True,
        ),
    ),
    formula(
        "first_law_internal_energy",
        "thermal",
        "First law of thermodynamics",
        "\\Delta U",
        base_latex="\\Delta U = Q - W",
        variables=(
            var("W", "W", "joule"),
            var("heat", "Q", "joule"),
        ),
    ),
    formula(
        "carnot_efficiency",
        "thermal",
        "Carnot-efficiency equation",
        "\\eta_C",
        base_latex="\\eta_C = 1 - \\frac{T_C}{T_H}",
        variables=(
            var("temp", "T_H", "kelvin"),
            var("temp_env", "T_C", "kelvin"),
        ),
    ),
    formula(
        "entropy_change",
        "thermal",
        "Entropy-change equation",
        "\\Delta S",
        base_latex="\\Delta S = \\frac{Q_{rev}}{T}",
        variables=(
            var("heat", "Q", "joule"),
            var("temp", "T", "kelvin"),
        ),
    ),
    formula(
        "heat_conduction_rate",
        "thermal",
        "Fourier heat-conduction law",
        "Q/t",
        base_latex="\\frac{Q}{t} = kA\\frac{\\Delta T}{L}",
        variables=(
            var("L", "L", "meter", words=("thick", "thickness", "long", "length")),
            var("area", "A", "meter ** 2"),
            var("delta_temp", r"\Delta T", "kelvin"),
            var("thermal_conductivity", "k", "watt / meter / kelvin"),
        ),
        binding=Binding(
            asks=(
                "rate of heat transfer",
                "rate of heat flow",
                "heat flow rate",
                "heat transfer rate",
                "heat flows per second",
                "heat per second",
                "rate of conduction",
            ),
            result=("watt",),
            inputs=(frozenset({"L", "area", "delta_temp", "thermal_conductivity"}),),
            cues=("conduct", "conduction", "thermal conductivity"),
            nonnegative=True,
        ),
    ),
    formula(
        "adiabatic_temperature",
        "thermal",
        "Adiabatic temperature-volume relation",
        "T_2",
        base_latex=r"T_1 V_1^{\gamma-1} = T_2 V_2^{\gamma-1}",
        assumptions=("a reversible adiabatic process with gamma stated",),
        expression="temp_initial*(vol1/vol2)**(gamma_gas-1)",
        variables=(
            var("gamma_gas", r"\gamma", dimensionless=True, words=("gamma",), needs_words=True),
            var("temp_initial", "T_1", "kelvin", words=("initial",), needs_words=True),
            var("vol1", "V_1", "meter ** 3", words=("initial",), needs_words=True),
            var("vol2", "V_2", "meter ** 3", words=("final",), needs_words=True),
        ),
        binding=Binding(
            asks=("final temperature", "temperature"),
            result=("kelvin",),
            inputs=(frozenset({"gamma_gas", "temp_initial", "vol1", "vol2"}),),
            cues=("adiabatic",),
            excludes=("pressure",),
            nonnegative=True,
        ),
    ),
    formula(
        "mayer_cp",
        "thermal",
        "Mayer's relation",
        "C_p",
        base_latex=r"C_p - C_v = R",
        assumptions=("an ideal gas, molar heat capacities",),
        expression="cv_molar+R_gas",
        variables=(
            var(
                "cv_molar",
                "C_v",
                "joule / mole / kelvin",
                words=("cv", "constant volume"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("molar heat capacity at constant pressure", "cp"),
            result=("joule / mole / kelvin",),
            inputs=(frozenset({"cv_molar"}),),
            cues=("mayer",),
            nonnegative=True,
        ),
    ),
    formula(
        "mayer_cv",
        "thermal",
        "Mayer's relation",
        "C_v",
        base_latex=r"C_p - C_v = R",
        assumptions=("an ideal gas, molar heat capacities",),
        expression="cp_molar-R_gas",
        variables=(
            var(
                "cp_molar",
                "C_p",
                "joule / mole / kelvin",
                words=("cp", "constant pressure"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("molar heat capacity at constant volume",),
            result=("joule / mole / kelvin",),
            inputs=(frozenset({"cp_molar"}),),
            cues=("mayer",),
            nonnegative=True,
        ),
    ),
    formula(
        "area_expansion",
        "thermal",
        "Area thermal expansion",
        r"\Delta A",
        base_latex=r"\Delta A = 2\alpha A_0\Delta T",
        assumptions=("the linear expansivity is the same in both directions",),
        expression="2*alpha*area0*delta_temp",
        variables=(
            var("area0", "A_0", "meter ** 2", words=("area",), needs_words=True),
            _ALPHA,
            _DELTA_TEMP,
        ),
        binding=Binding(
            asks=("change in area", "increase in area", "area expansion"),
            result=("meter ** 2",),
            inputs=(frozenset({"alpha", "area0", "delta_temp"}),),
            cues=("area",),
            excludes=("volume",),
            nonnegative=True,
        ),
    ),
    formula(
        "volume_expansion",
        "thermal",
        "Volume thermal expansion",
        r"\Delta V",
        base_latex=r"\Delta V = \beta V_0\Delta T",
        expression="beta*volume0*delta_temp",
        variables=(
            var("volume0", "V_0", "meter ** 3", words=("volume",), needs_words=True),
            var(
                "beta",
                r"\beta",
                "1 / kelvin",
                words=("volume expansivity", "cubical expansivity", "volume expansion"),
                needs_words=True,
            ),
            _ALPHA,
            _DELTA_TEMP,
        ),
        variants=(
            FormulaVariant(
                present=frozenset({"alpha"}),
                absent=frozenset({"beta"}),
                latex=r"\Delta V = 3\alpha V_0\Delta T",
                expression="3*alpha*volume0*delta_temp",
                assumptions=("the volume expansivity is three times the linear one",),
            ),
        ),
        binding=Binding(
            asks=("change in volume", "increase in volume", "volume expansion"),
            result=("meter ** 3",),
            inputs=(
                frozenset({"beta", "delta_temp", "volume0"}),
                frozenset({"alpha", "delta_temp", "volume0"}),
            ),
            cues=("volume",),
            excludes=("area",),
            nonnegative=True,
        ),
    ),
    formula(
        "isothermal_work",
        "thermal",
        "Isothermal work of an ideal gas",
        "W",
        base_latex=r"W = nRT\ln\frac{V_2}{V_1}",
        assumptions=("the temperature is constant", "the gas is ideal"),
        expression="moles*R_gas*temp*log(vol_final/vol_initial)",
        variables=(
            var("moles", "n", "mole"),
            var("temp", "T", "kelvin", words=("at",), needs_words=True),
            var("vol_initial", "V_1", "meter ** 3", words=("from",), needs_words=True),
            var("vol_final", "V_2", "meter ** 3", words=("to",), needs_words=True),
        ),
        binding=Binding(
            asks=("work", "work done"),
            result=("joule",),
            inputs=(frozenset({"moles", "temp", "vol_final", "vol_initial"}),),
            cues=("isothermal", "isothermally"),
            negative_detail="done on the gas",
        ),
    ),
    formula(
        "mean_free_path",
        "thermal",
        "Mean free path",
        r"\lambda",
        base_latex=r"\lambda = \frac{1}{\sqrt{2}\pi d^2 n}",
        assumptions=("the molecules are hard spheres",),
        expression="1/(sqrt(2)*pi*diameter**2*number_density)",
        variables=(
            var("diameter", "d", "meter", words=("diameter",), needs_words=True),
            var("number_density", "n", "1 / meter ** 3", words=("density",), needs_words=True),
        ),
        binding=Binding(
            asks=("mean free path",),
            result=("meter",),
            inputs=(frozenset({"diameter", "number_density"}),),
            cues=("mean free path",),
            nonnegative=True,
        ),
    ),
    _molecule_gas(
        "molecule_gas_pressure",
        "P",
        "molecule_count*k_B*temp/volume",
        ("pressure",),
        "pascal",
        (_N, _TEMP, _VOLUME),
        frozenset({"molecule_count", "temp", "volume"}),
    ),
    _molecule_gas(
        "molecule_gas_volume",
        "V",
        "molecule_count*k_B*temp/pres",
        ("volume",),
        "meter ** 3",
        (_N, _TEMP, _PRESSURE),
        frozenset({"molecule_count", "pres", "temp"}),
    ),
    _molecule_gas(
        "molecule_gas_count",
        "N",
        "pres*volume/(k_B*temp)",
        ("number of molecules", "number of particles", "how many molecules", "how many particles"),
        "dimensionless",
        (_PRESSURE, _VOLUME, _TEMP),
        frozenset({"pres", "temp", "volume"}),
    ),
    _molecule_gas(
        "molecule_gas_temperature",
        "T",
        "pres*volume/(molecule_count*k_B)",
        ("temperature",),
        "kelvin",
        (_N, _PRESSURE, _VOLUME),
        frozenset({"molecule_count", "pres", "volume"}),
    ),
    formula(
        "ideal_gas_density",
        "thermal",
        "Ideal-gas density",
        r"\rho",
        base_latex=r"\rho = \frac{PM}{RT}",
        assumptions=("an ideal gas",),
        expression="pres*molar_mass/(R_gas*temp)",
        variables=(
            _PRESSURE,
            var("molar_mass", "M", "kilogram / mole", words=("molar",), needs_words=True),
            _TEMP,
        ),
        binding=Binding(
            asks=("density",),
            result=("kilogram / meter ** 3",),
            inputs=(frozenset({"molar_mass", "pres", "temp"}),),
            cues=("molar mass",),
            nonnegative=True,
        ),
    ),
    formula(
        "otto_efficiency",
        "thermal",
        "Otto-cycle efficiency",
        r"\eta",
        base_latex=r"\eta = 1 - r^{1-\gamma}",
        expression="1 - compression_ratio**(1 - gamma)",
        variables=(
            var(
                "compression_ratio",
                "r",
                dimensionless=True,
                words=("compression ratio", "compression"),
                needs_words=True,
            ),
            var("gamma", r"\gamma", dimensionless=True, words=("gamma",), needs_words=True),
        ),
        binding=Binding(
            asks=("efficiency",),
            result=("dimensionless",),
            inputs=(frozenset({"compression_ratio", "gamma"}),),
            cues=("otto",),
            excludes=("diesel", "carnot"),
            nonnegative=True,
            at_most=1.0,
        ),
    ),
)
