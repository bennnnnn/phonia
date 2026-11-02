"""Verified circuit operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, bind, formula, var

# The members of a resistor network, in the order stated. Six covers "five 100 Ω
# resistors in series" and a count word's repeats.
_NETWORK = tuple(var(f"R{n}", f"R_{n}", "ohm") for n in range(1, 7))

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "voltage",
        "circuit",
        "Ohm's law",
        "V",
        base_latex="V = IR",
        variables=(
            var("I", "I", "ampere"),
            var("R", "R", "ohm"),
        ),
    ),
    formula(
        "current",
        "circuit",
        "Ohm's law",
        "I",
        base_latex="V = IR",
        variables=(
            var("R", "R", "ohm"),
            var("V", "V", "volt"),
        ),
    ),
    formula(
        "resistance",
        "circuit",
        "Ohm's law",
        "R",
        base_latex="V = IR",
        variables=(
            var("I", "I", "ampere"),
            var("V", "V", "volt"),
        ),
    ),
    formula(
        "electrical_power",
        "circuit",
        "Electrical-power formula",
        "P",
        base_latex="P = VI",
        variables=(
            var("I", "I", "ampere"),
            var("R", "R", "ohm"),
            var("V", "V", "volt"),
        ),
    ),
    # A battery's own resistance adds to the load's: I = ε/(R + r).
    formula(
        "current_with_internal_resistance",
        "circuit",
        "Ohm's law for the whole circuit",
        "I",
        base_latex=r"I = \frac{\mathcal{E}}{R + r}",
        expression="E_emf/(R + r_int)",
        variables=(
            var("E_emf", r"\mathcal{E}", "volt"),
            var(
                "R",
                "R",
                "ohm",
                words=("resistor", "load", "external", "connected to", "drives a", "lamp", "bulb"),
                needs_words=True,
            ),
            var("r_int", "r", "ohm", words=("internal",), needs_words=True),
        ),
        binding=Binding(
            asks=("current",),
            result=("ampere",),
            inputs=(frozenset({"E_emf", "R", "r_int"}),),
            cues=("internal resistance",),
            excludes=("terminal", "lost volts", "parallel", "series"),
            nonnegative=True,
        ),
    ),
    # The energy a steady power uses over a time: E = Pt. 60 W for a week is
    # 3.63e7 J, 10.1 kWh.
    formula(
        "energy_from_power_time",
        "circuit",
        "Electrical energy",
        "E",
        base_latex=r"E = P t",
        expression="P*t",
        variables=(var("P", "P", "watt"), var("t", "t", "second")),
        binding=Binding(
            asks=("how many kwh", "energy", "how much energy", "energy used", "electricity"),
            result=("joule",),
            inputs=(frozenset({"P", "t"}),),
            cues=("bulb", "lamp", "heater", "kettle", "appliance", "device", "left on", "runs"),
            excludes=(
                "a day",
                "per day",
                "each day",
                "every day",
                "daily",
                "cost",
                "price",
                "efficien",
                "lift",
                "raise",
            ),
            nonnegative=True,
        ),
    ),
    # A lamp's rating gives its resistance: R = V²/P. 60 W on 120 V is 240 Ω.
    formula(
        "resistance_from_power",
        "circuit",
        "Electrical-power formula",
        "R",
        base_latex=r"P = \frac{V^2}{R}",
        assumptions=("the device runs at its rated power on that voltage",),
        expression="V**2/power",
        variables=(var("V", "V", "volt"), var("power", "P", "watt")),
        binding=Binding(
            asks=("resistance",),
            result=("ohm",),
            inputs=(frozenset({"V", "power"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "series_resistance",
        "circuit",
        "Series-resistance law",
        "R_s",
        variables=(*_NETWORK,),
    ),
    formula(
        "parallel_resistance",
        "circuit",
        "Parallel-resistance law",
        "R_p",
        variables=(*_NETWORK,),
    ),
    # Ohm's law across a whole network: its equivalent resistance first, then
    # I = V/R. Two 3 Ω in parallel across 9 V draw 6 A, and the schematic keeps
    # both resistors instead of one 1.5 Ω stand-in.
    *(
        formula(
            operation,
            "circuit",
            "Ohm's law",
            "I",
            variables=(*_NETWORK, var("V", "V", "volt")),
        )
        for operation in ("series_current", "parallel_current")
    ),
    # One resistor in series with a parallel group (``extractors/series_parallel.py``):
    # R = R₁ + R_p, where 1/R_p sums the group. 4 Ω with 6 Ω ∥ 12 Ω is 8 Ω.
    formula(
        "series_parallel_resistance",
        "circuit",
        "Series-parallel network",
        "R",
        variables=(*_NETWORK,),
    ),
    formula(
        "series_parallel_current",
        "circuit",
        "Series-parallel network",
        "I",
        variables=(*_NETWORK, var("V", "V", "volt")),
    ),
    formula(
        "charge",
        "circuit",
        "Charge-current relation",
        "Q",
        variables=(
            var("I", "I", "ampere"),
            var("t", "t", "second"),
        ),
        binding=bind(("charge",), "coulomb", "I", "t"),
    ),
    formula(
        "electrical_energy",
        "circuit",
        "Electrical-energy formula",
        "E",
        variables=(
            var("power", "P", "watt"),
            var("t", "t", "second"),
        ),
    ),
    formula(
        "terminal_voltage",
        "circuit",
        "Terminal-voltage equation",
        "V_{terminal}",
        variables=(
            var("E_emf", r"\mathcal{E}", "volt"),
            var("I", "I", "ampere"),
            var("r_int", "r", "ohm"),
        ),
    ),
    formula(
        "kirchhoff_junction",
        "circuit",
        "Kirchhoff's junction rule",
        "I",
        base_latex=r"\sum I_{\mathrm{in}} = \sum I_{\mathrm{out}}",
        assumptions=("one junction and steady current",),
        variables=(
            var("i_enter", r"I_{\mathrm{in}}", "ampere"),
            var("i_leave", r"I_{\mathrm{out}}", "ampere"),
        ),
    ),
    formula(
        "kirchhoff_loop",
        "circuit",
        "Kirchhoff's loop rule",
        "I",
        base_latex=r"\sum \Delta V = 0",
        assumptions=("one battery and one series loop",),
        variables=(
            var("R1", "R_1", "ohm"),
            var("R2", "R_2", "ohm"),
            var("R3", "R_3", "ohm"),
            var("R4", "R_4", "ohm"),
            var("V", "V", "volt"),
        ),
    ),
    formula(
        "current_from_charge",
        "circuit",
        "Charge-current relation",
        "I",
        base_latex="Q = It",
        expression="Q/t",
        variables=(var("Q", "Q", "coulomb"), var("t", "t", "second")),
        binding=bind(("current",), "ampere", "Q", "t"),
    ),
    formula(
        "resistivity_resistance",
        "circuit",
        "Resistivity equation",
        "R",
        base_latex=r"R = \frac{\rho L}{A}",
        assumptions=("a uniform conductor",),
        expression="resistivity*L/area",
        variables=(
            var("L", "L", "meter"),
            var("area", "A", "meter ** 2"),
            var("resistivity", r"\rho", "ohm * meter"),
        ),
        binding=bind(("resistance",), "ohm", "L", "area", "resistivity"),
    ),
    formula(
        "transformer_voltage",
        "circuit",
        "Ideal transformer equation",
        "V_s",
        base_latex=r"\frac{V_s}{V_p} = \frac{N_s}{N_p}",
        assumptions=("an ideal transformer",),
        expression="v_primary*turns_secondary/turns_primary",
        variables=(
            var("turns_primary", "N_p", dimensionless=True, words=("primary",)),
            var("turns_secondary", "N_s", dimensionless=True, words=("secondary",)),
            var("v_primary", "V_p", "volt"),
        ),
        binding=bind(
            ("secondary voltage", "output voltage", "voltage"),
            "volt",
            "turns_primary",
            "turns_secondary",
            "v_primary",
            cues=("transformer",),
        ),
    ),
    formula(
        "drift_speed",
        "circuit",
        "Drift speed",
        "v_d",
        base_latex=r"v_d = \frac{I}{n e A}",
        assumptions=("one carrier density",),
        expression="I/(number_density*e_charge*area)",
        variables=(
            var("I", "I", "ampere"),
            var(
                "number_density",
                "n",
                "1 / meter ** 3",
                words=("density", "number density", "carrier"),
                needs_words=True,
            ),
            var("area", "A", "meter ** 2", words=("area",), needs_words=True),
        ),
        binding=Binding(
            asks=("drift speed", "drift velocity"),
            result=("meter / second",),
            inputs=(frozenset({"I", "area", "number_density"}),),
            cues=("drift",),
            excludes=("hall",),
            nonnegative=True,
        ),
    ),
    # P = VI, for the current a stated power draws.
    formula(
        "current_from_power",
        "circuit",
        "Electrical power",
        "I",
        base_latex=r"I = \frac{P}{V}",
        expression="power/V",
        variables=(var("power", "P", "watt"), var("V", "V", "volt")),
        binding=Binding(
            asks=("current", "how much current", "what current"),
            result=("ampere",),
            inputs=(frozenset({"power", "V"}),),
            nonnegative=True,
        ),
    ),
    # E = QV, for the charge a stated energy moves through a voltage.
    formula(
        "charge_from_energy",
        "circuit",
        "Energy transferred by a charge",
        "Q",
        base_latex=r"Q = \frac{E}{V}",
        expression="energy/V",
        variables=(var("energy", "E", "joule"), var("V", "V", "volt")),
        binding=Binding(
            asks=("charge", "how much charge"),
            result=("coulomb",),
            inputs=(frozenset({"energy", "V"}),),
            nonnegative=True,
        ),
    ),
    # E = QV, for the energy a battery gives the charge it moves.
    formula(
        "energy_from_charge_voltage",
        "circuit",
        "Energy transferred by a charge",
        "E",
        base_latex=r"E = Q V",
        expression="Q*V",
        variables=(var("Q", "Q", "coulomb"), var("V", "V", "volt")),
        binding=Binding(
            asks=("energy", "how much energy", "energy transferred", "work done"),
            result=("joule",),
            inputs=(frozenset({"Q", "V"}),),
            cues=("battery", "moves", "charge", "coulomb"),
            excludes=("accelerat", "electron", "proton", "ion"),
            nonnegative=True,
        ),
    ),
    # E = P t over a stated number of days: hours a day times days.
    formula(
        "energy_over_days",
        "circuit",
        "Electrical energy",
        "E",
        base_latex=r"E = P \, t_{\text{day}} \, n_{\text{days}}",
        expression="P*t_daily*(period/86400)",
        variables=(
            var("P", "P", "watt"),
            var(
                "t_daily",
                r"t_{\text{day}}",
                "second",
                words=("a day", "per day", "each day", "every day", "daily"),
                needs_words=True,
            ),
            var("period", r"n_{\text{days}}", "second"),
        ),
        binding=Binding(
            asks=(
                "energy",
                "how much energy",
                "electrical energy",
                "energy used",
                "energy does it use",
            ),
            result=("joule",),
            inputs=(frozenset({"P", "t_daily", "period"}),),
            cues=("a day", "per day", "each day", "every day", "daily"),
            nonnegative=True,
        ),
    ),
)
