"""Circuits: Ohm's law, power, charge flow, energy and resistor networks."""

from __future__ import annotations

import re
from typing import Literal

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.circuit_patterns import (
    _CHARGE_FLOW_RE,
    _CIRCUIT_CUE_RES,
    _CIRCUIT_CUES,
    _CIRCUIT_TIME_UNITS,
    _COULOMB_PATTERN,
    _ELECTRICAL_ENERGY_RE,
    _FARAD_PATTERN,
    _MAX_COUNTED_RESISTORS,
    _MAX_NETWORK_RESISTORS,
    _TERMINAL_ASK_RE,
    _VOLT_PATTERN,
    _WATT_PATTERN,
    network_asks,
    resistor_values,
    unvalued_part,
    without_resistor_names,
)
from app.modules.physics.extractors.counted_parts import counted_resistors
from app.modules.physics.extractors.cues import (
    _has_cue_either_case,
)
from app.modules.physics.extractors.fluid_readings import AREA_PATTERN
from app.modules.physics.extractors.school_extensions import blocks_circuit
from app.modules.physics.extractors.series_parallel import series_parallel_intent
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    ordered_values,
)
from app.modules.physics.extractors.unit_patterns import (
    AMP_PATTERN,
    LENGTH_UNIT_PATTERN,
    OHM_PATTERN,
)
from app.modules.physics.givens import scan_givens
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

# The dimension of each Ohm's-law quantity, as the givens scan writes it.
_ELECTRICAL_DIMENSIONS = {
    "V": "[current]^-1 * [length]^2 * [mass]^1 * [time]^-3",
    "I": "[current]^1",
    "R": "[current]^-2 * [length]^2 * [mass]^1 * [time]^-3",
}


def _prefixed_value(cleaned: str, key: str) -> tuple[float, str] | None:
    """The one V, I or R stated with a prefix ("2 mA", "4.7 kΩ"), with its unit."""
    found = [
        given
        for given in scan_givens(cleaned)
        if given.dimension == _ELECTRICAL_DIMENSIONS[key] and given.unit
    ]
    if len(found) != 1:
        return None
    return found[0].value, found[0].unit


def _network_equivalent(values: list[float], *, series: bool) -> float | None:
    """Series sum, or the parallel reciprocal sum. Nonpositive parts decline."""
    if len(values) < 2 or any(value <= 0 for value in values):
        return None
    if series:
        return sum(values)
    return 1.0 / sum(1.0 / value for value in values)


# What a network's total answers: the whole circuit, never one resistor's share. "the
# current the 3 Ω resistor draws" and "the p.d. across the 50 Ω resistor" got the network's
# total; a list of one-resistor phrasings is never complete, so the whole is what is named.
_WHOLE_RESISTANCE_ASK = re.compile(
    r"\b(?:total|equivalent|combined|effective|net|overall)\s+resistance"
    r"|\bresistance\s+of\s+the\s+(?:combination|circuit|network|arrangement|whole)"
    r"|\bresistance\s*(?:[.?!]|$)|\b(?:the\s+)?(?:total|equivalent)\s*(?:[.?!,]|$)"
)
_WHOLE_CURRENT_ASK = re.compile(
    r"\btotal\s+current|\b(?:main|circuit|supply|line)\s+current"
    r"|\bcurrent\s+(?:drawn\s+|taken\s+)?(?:from|supplied\s+by|delivered\s+by|out\s+of"
    r"|in|through|round|around)\s+the\s+(?:battery|cell|supply|source|mains|circuit|network"
    r"|combination)\b|\bcurrent\s*(?:[.?!]|$)"
    r"|\bcurrent\s+(?:flows|is\s+drawn|is\s+supplied|passes)\s*(?:[.?!]|$)"
    r"|\bcurrent\s+(?:does|will|would)\s+the\s+(?:battery|cell|supply|source)"
    r"\s+(?:supply|deliver|provide|give|draw)\b"
)
# A meter's reading is a voltage across part of the circuit, not the supply's.
_METER_READING = re.compile(r"\bvoltmeter|\breads?\b|\breading")


def _network_intent(
    lower: str,
    network: list[float],
    counted: tuple[int, float] | None,
    volts: list[tuple[float, str]],
    amps: list[tuple[float, str]],
) -> PhysicsIntent | None:
    """Two or more resistances in series or in parallel: their total, or the current
    a stated supply drives through them."""
    stated = 1 if counted is not None else len(network)
    if stated > _MAX_NETWORK_RESISTORS or len(network) > _MAX_COUNTED_RESISTORS:
        return None
    series = "series" in lower
    # "Find the current" with a supply voltage is Ohm's law on the
    # equivalent resistance. Answering the resistance sum is a different law.
    asks_current, asks_resistance = network_asks(lower)
    if asks_current and not asks_resistance:
        if not _WHOLE_CURRENT_ASK.search(lower) or _METER_READING.search(lower):
            return None
        # Every resistor stays a parameter, so the working and the schematic
        # show the network the user described, not one equivalent resistor.
        if len(volts) != 1 or amps or _network_equivalent(network, series=series) is None:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="series_current" if series else "parallel_current",
            physics_params={
                **{f"R{n}": value for n, value in enumerate(network, start=1)},
                "V": volts[0][0],
            },
            physics_units={
                **{f"R{n}": "ohm" for n in range(1, len(network) + 1)},
                "V": "volt",
            },
            operation="solve",
        )
    if not _WHOLE_RESISTANCE_ASK.search(lower):
        return None
    return PhysicsIntent(
        kind="circuit",
        physics_op="series_resistance" if series else "parallel_resistance",
        physics_params={f"R{n}": value for n, value in enumerate(network, start=1)},
        physics_units={f"R{n}": "ohm" for n in range(1, len(network) + 1)},
        operation="solve",
    )


def _ohm_givens(
    cleaned: str,
    volts: list[tuple[float, str]],
    amps: list[tuple[float, str]],
    ohms: list[tuple[float, str]],
) -> tuple[dict[str, float], dict[str, str]] | None:
    """The one V, I and R stated, each with its unit; None when one quantity has two values
    ("a 48 V battery … the voltmeter reads 9 V"): which one a law takes is a guess.

    ``ohms`` is the one resistor the network read left: two resistances past it are that
    resistor named again, never a set of values that happen to be equal."""
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    for key, found, unit in (("V", volts, "volt"), ("I", amps, "ampere"), ("R", ohms, "ohm")):
        if len({value for value, _ in found}) > 1:
            return None
        if found:
            params[key] = found[0][0]
            units[key] = unit
        elif (prefixed := _prefixed_value(cleaned, key)) is not None:
            # "2 mA", "4.7 kΩ": the unit is kept, and the solver works in SI.
            params[key], units[key] = prefixed
    return params, units


def _resistor_network(
    cleaned: str,
    lower: str,
    volts: list[tuple[float, str]],
    amps: list[tuple[float, str]],
    ohms: list[tuple[float, str]],
) -> tuple[bool, PhysicsIntent | None]:
    """(decided, card) for a resistor network: its card, or a decline. (False, None) when
    the question is no network and the single-resistor laws below may read it."""
    network = resistor_values(cleaned)
    counted = counted_resistors(cleaned)
    if counted is not None and not network:
        # Counted resistors beside others: a network this does not read.
        return True, None
    if len(network) >= 2 and ("series" in lower or "parallel" in lower):
        return True, _network_intent(lower, network, counted, volts, amps)
    # Two parts read with no wiring stated, two values not read as one resistor named again
    # (an internal resistance and a resistor, "a kettle of 30 Ω and an iron of 30 Ω"), or a
    # part with no value of its own ("an identical resistor"): Ohm's law on one of them is a
    # guess. "A resistor of 10 Ω and another of 10 Ω in parallel across 5 V" was certified
    # 0.5 A, one resistor (2026-11-01).
    if len(network) >= 2 or (len(ohms) >= 2 and len(network) != 1) or unvalued_part(lower):
        return True, None
    return False, None


def _readable_circuit_text(cleaned: str) -> str | None:
    """The question as the readers below take it: without its "R1 =" labels. None for
    a circuit this does not read (a blocked shape, a network wired by name, algebra)."""
    if blocks_circuit(cleaned):
        return None
    unnamed = without_resistor_names(cleaned)
    if unnamed is None or has_equation(strip_param_assignments(unnamed)):
        return None
    return unnamed


def _extract_circuit_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    # The same check the pre-filter runs, so the two cannot disagree about
    # whether this question is a circuit question.
    if not _has_cue_either_case(cleaned, _CIRCUIT_CUES, _CIRCUIT_CUE_RES):
        return None
    readable = _readable_circuit_text(cleaned)
    if readable is None:
        return None
    cleaned, lower = readable, readable.lower()

    volts = ordered_values(cleaned, _VOLT_PATTERN)
    amps = ordered_values(cleaned, AMP_PATTERN)
    ohms = ordered_values(cleaned, OHM_PATTERN)
    farads = ordered_values(cleaned, _FARAD_PATTERN)

    # --- parallel-plate capacitance: C = epsilon_0 A / d ----------------
    if "parallel plate" in lower:
        area = find_value_with_specific_unit(cleaned, AREA_PATTERN)
        spacing = find_value_with_specific_unit(
            cleaned,
            LENGTH_UNIT_PATTERN,
            ("separation", "spacing", "apart", "distance"),
            require_keyword=True,
        )
        if area is None or spacing is None:
            return None
        # A stated dielectric is C = κ ε0 A / d. The vacuum formula would drop κ.
        if "dielectric" in lower or "kappa" in lower:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="parallel_plate_capacitance",
            physics_params={"area": area[0], "d": spacing[0]},
            physics_units={"area": area[1] or "m^2", "d": spacing[1] or "m"},
            operation="solve",
        )

    # --- capacitor stored energy: U = C V^2 / 2 -------------------------
    if "capacitor" in lower and "energy" in lower:
        if len(farads) != 1 or len(volts) != 1:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="capacitor_energy",
            physics_params={"capacitance": farads[0][0], "V": volts[0][0]},
            physics_units={"capacitance": farads[0][1] or "F", "V": volts[0][1] or "V"},
            operation="solve",
        )

    # --- RC time constant: tau = RC -------------------------------------
    if "time constant" in lower or "rc circuit" in lower:
        if len(ohms) != 1 or len(farads) != 1:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="rc_time_constant",
            physics_params={"R": ohms[0][0], "capacitance": farads[0][0]},
            physics_units={"R": ohms[0][1] or "ohm", "capacitance": farads[0][1] or "F"},
            operation="solve",
        )

    # --- resistor networks: two or more resistances and a stated topology ---
    if "series" in lower and "parallel" in lower:
        # A series-parallel network is not one sum: 4 Ω in series with 6 Ω
        # and 12 Ω in parallel is 8 Ω, and the all-series reading said 22 Ω.
        return series_parallel_intent(cleaned, volts, amps)
    decided, network_card = _resistor_network(cleaned, lower, volts, amps, ohms)
    if decided:
        return network_card

    read = _ohm_givens(cleaned, volts, amps, ohms[:1])
    if read is None:
        return None
    params, units = read

    # --- terminal voltage: V = emf - I r ---------------------------------
    # Only when the question says both that there *is* an internal resistance
    # and that the terminal value is what it wants. Without the second half
    # this is an ordinary Ohm's law question and belongs below - choosing
    # between the EMF and the terminal voltage on the reader's behalf is the
    # kind of guess a verified block must not make.
    if "internal resistance" in lower and _TERMINAL_ASK_RE.search(cleaned):
        r_internal = find_value_with_specific_unit(
            cleaned, OHM_PATTERN, ("internal",), require_keyword=True
        )
        if r_internal is None or not volts or not amps:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="terminal_voltage",
            physics_params={
                "E_emf": volts[0][0],
                "I": amps[0][0],
                "r_int": r_internal[0],
            },
            physics_units={"E_emf": "volt", "I": "ampere", "r_int": "ohm"},
            operation="solve",
        )

    # --- capacitance: C = Q / V ------------------------------------------
    # Stored energy from Q and V is not this capacitance. The energy branch
    # above already declined when C was not stated.
    if "capacit" in lower and "energy" not in lower:
        coulombs = ordered_values(cleaned, _COULOMB_PATTERN)
        if not coulombs or not volts:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="capacitance",
            physics_params={"Q": coulombs[0][0], "V": volts[0][0]},
            physics_units={"Q": "coulomb", "V": "volt"},
            operation="solve",
        )

    # --- charge: Q = I t --------------------------------------------------
    if _CHARGE_FLOW_RE.search(cleaned):
        seconds = find_value_with_specific_unit(cleaned, _CIRCUIT_TIME_UNITS)
        if not amps or seconds is None:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="charge",
            physics_params={"I": amps[0][0], "t": seconds[0]},
            physics_units={"I": "ampere", "t": seconds[1] or "s"},
            operation="solve",
        )

    # --- electrical energy: E = P t ---------------------------------------
    if _ELECTRICAL_ENERGY_RE.search(cleaned):
        watts = find_value_with_specific_unit(cleaned, _WATT_PATTERN)
        seconds = find_value_with_specific_unit(cleaned, _CIRCUIT_TIME_UNITS)
        if watts is None or seconds is None:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="electrical_energy",
            physics_params={"power": watts[0], "t": seconds[0]},
            physics_units={"power": watts[1] or "W", "t": seconds[1] or "s"},
            operation="solve",
        )

    # Electrical power needs electrical units present, which is what keeps it
    # from colliding with the mechanical `power` op (P = F v, in newtons and
    # m/s). Two different quantities that share a name and a unit.
    if "power" in lower or "dissipat" in lower or "watt" in lower:
        if len(params) < 2:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="electrical_power",
            physics_params=params,
            physics_units=units,
            operation="solve",
        )

    # V = I R: whichever of the three is absent is the one being asked for.
    # That reads the question from its givens rather than from its wording,
    # so all three rearrangements work without three sets of phrasings.
    if len(params) != 2:
        return None
    missing = ({"V", "I", "R"} - set(params)).pop()
    asked_for: dict[str, Literal["voltage", "current", "resistance"]] = {
        "V": "voltage",
        "I": "current",
        "R": "resistance",
    }
    asked = asked_for[missing]
    return PhysicsIntent(
        kind="circuit",
        physics_op=asked,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
