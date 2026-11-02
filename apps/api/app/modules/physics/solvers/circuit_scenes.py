"""Circuit schematics for the questions that describe a circuit.

The server says what is connected to what; the phone lays the schematic out.
A question about a resistor network gets the network, an Ohm's-law question a
battery and its one part, and each carries the values the question gave and
the one it asked for, highlighted.
"""

from __future__ import annotations

from typing import Literal

from app.modules.physics.display import GIVEN_FIGURES, plain_number
from app.modules.physics.schemas import (
    CircuitNode,
    CircuitSource,
    CircuitSpec,
    SimulationBlockSpec,
)
from app.modules.physics.solvers.resistor_network import RESISTOR_KEY_RE

_SUBSCRIPTS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


# The prefixes a schematic writes each unit with: 10 kΩ and 100 µF, not 10000 Ω
# and 1e-4 F.
_OHM_PREFIXES = ((1e6, "M"), (1e3, "k"), (1.0, ""))
_FARAD_PREFIXES = ((1.0, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"))


def _prefixed(
    value: float, unit: str, prefixes: tuple[tuple[float, str], ...], figures: int
) -> str:
    for scale, prefix in prefixes:
        if abs(value) >= scale * 0.9995:
            return f"{plain_number(value / scale, figures)} {prefix}{unit}"
    scale, prefix = prefixes[-1]
    return f"{plain_number(value / scale, figures)} {prefix}{unit}"


def _ohms(value: float, *, given: bool = True) -> str:
    return _prefixed(value, "Ω", _OHM_PREFIXES, GIVEN_FIGURES if given else 3)


def _farads(value: float, *, given: bool = True) -> str:
    return _prefixed(value, "F", _FARAD_PREFIXES, GIVEN_FIGURES if given else 3)


def _scene(spec: CircuitSpec, alt: str) -> list[SimulationBlockSpec]:
    return [
        SimulationBlockSpec(
            type="circuit", title="Circuit", title_key="circuit", circuit=spec, alt=alt
        )
    ]


def circuit_scene(op: str, p: dict[str, float], answer: float) -> list[SimulationBlockSpec]:
    """The schematic for one circuit operation, or nothing when it names no circuit."""
    if op in _NETWORK_OPERATIONS:
        return _network(op, p, answer)
    if op in ("series_parallel_resistance", "series_parallel_current"):
        return _series_parallel(op, p, answer)
    battery = CircuitSource(label=f"{plain_number(p['V'], GIVEN_FIGURES)} V" if "V" in p else None)
    if op == "current":
        resistor = CircuitNode(part="resistor", label=f"R = {_ohms(p['R'])}")
        return _scene(
            CircuitSpec(source=battery, load=resistor, current=f"I = {plain_number(answer)} A"),
            f"A {plain_number(p['V'], GIVEN_FIGURES)} V battery across {_ohms(p['R'])} "
            f"drives {plain_number(answer)} A.",
        )
    if op == "voltage":
        source = CircuitSource(label=f"V = {plain_number(answer)} V")
        resistor = CircuitNode(part="resistor", label=f"R = {_ohms(p['R'])}")
        return _scene(
            CircuitSpec(
                source=source,
                load=resistor,
                current=f"I = {plain_number(p['I'], GIVEN_FIGURES)} A",
            ),
            f"{plain_number(p['I'], GIVEN_FIGURES)} A through {_ohms(p['R'])} "
            f"needs {plain_number(answer)} V.",
        )
    if op == "resistance":
        resistor = CircuitNode(
            part="resistor", label=f"R = {_ohms(answer, given=False)}", role="result"
        )
        return _scene(
            CircuitSpec(
                source=battery,
                load=resistor,
                current=f"I = {plain_number(p['I'], GIVEN_FIGURES)} A",
            ),
            f"{plain_number(p['V'], GIVEN_FIGURES)} V driving "
            f"{plain_number(p['I'], GIVEN_FIGURES)} A means {_ohms(answer, given=False)}.",
        )
    if op == "electrical_power" and ("V" in p or "I" in p):
        part = CircuitNode(
            part="resistor",
            label=f"R = {_ohms(p['R'])}" if "R" in p else None,
            detail=f"P = {plain_number(answer)} W",
            role="result",
        )
        current = f"I = {plain_number(p['I'], GIVEN_FIGURES)} A" if "I" in p else None
        return _scene(
            CircuitSpec(source=battery, load=part, current=current),
            f"The part takes {plain_number(answer)} W.",
        )
    if op == "capacitance":
        capacitor = CircuitNode(
            part="capacitor",
            label=f"C = {_farads(answer, given=False)}",
            detail=f"Q = {plain_number(p['Q'], GIVEN_FIGURES)} C",
            role="result",
        )
        return _scene(
            CircuitSpec(source=battery, load=capacitor),
            f"A capacitor holding {plain_number(p['Q'], GIVEN_FIGURES)} C at "
            f"{plain_number(p['V'], GIVEN_FIGURES)} V has {_farads(answer, given=False)}.",
        )
    if op == "rc_time_constant":
        load = CircuitNode(
            series=[
                CircuitNode(part="resistor", label=f"R = {_ohms(p['R'])}"),
                CircuitNode(part="capacitor", label=f"C = {_farads(p['capacitance'])}"),
            ],
            label=f"τ = {plain_number(answer)} s",
            role="result",
        )
        return _scene(
            CircuitSpec(source=CircuitSource(), load=load),
            f"A resistor and a capacitor in series: time constant {plain_number(answer)} s.",
        )
    return []


_NETWORK_OPERATIONS = frozenset(
    {"series_resistance", "parallel_resistance", "series_current", "parallel_current"}
)


def _network(op: str, p: dict[str, float], answer: float) -> list[SimulationBlockSpec]:
    """Every resistor the question named, in series or in parallel, never one stand-in.

    Asked for the total resistance, the group's label is the answer; asked for the
    current, the group carries its total and the battery the current it drives.
    """
    keys = sorted(key for key in p if RESISTOR_KEY_RE.fullmatch(key))
    series = op.startswith("series")
    if len(keys) < 2 or len(keys) > (6 if series else 4):
        return []
    parts = [_resistor(key, p[key]) for key in keys]
    asks_current = op.endswith("_current")
    if asks_current:
        total = sum(p[key] for key in keys) if series else 1 / sum(1 / p[key] for key in keys)
    else:
        total = answer
    combined = f"R = {_ohms(total, given=False)}"
    role: Literal["given", "result"] = "given" if asks_current else "result"
    load = (
        CircuitNode(series=parts, label=combined, role=role)
        if series
        else CircuitNode(parallel=parts, label=combined, role=role)
    )
    values = ", ".join(_ohms(p[key]) for key in keys)
    network = (
        f"resistors of {values} in {'series' if series else 'parallel'}: "
        f"{_ohms(total, given=False)} in total"
    )
    if not asks_current:
        return _scene(CircuitSpec(source=CircuitSource(), load=load), f"R{network[1:]}.")
    volts = plain_number(p["V"], GIVEN_FIGURES)
    return _scene(
        CircuitSpec(
            source=CircuitSource(label=f"{volts} V"),
            load=load,
            current=f"I = {plain_number(answer)} A",
        ),
        f"A {volts} V battery across {network}, driving {plain_number(answer)} A.",
    )


def _resistor(key: str, value: float) -> CircuitNode:
    return CircuitNode(part="resistor", label=f"R{key[1:].translate(_SUBSCRIPTS)} = {_ohms(value)}")


def _series_parallel(op: str, p: dict[str, float], answer: float) -> list[SimulationBlockSpec]:
    """R₁ on the wire, then the parallel group with its own total, the whole labelled."""
    keys = sorted(key for key in p if RESISTOR_KEY_RE.fullmatch(key))
    if not 3 <= len(keys) <= 5:
        return []
    first, group = keys[0], keys[1:]
    parallel = 1 / sum(1 / p[key] for key in group)
    total = p[first] + parallel
    asks_current = op.endswith("_current")
    role: Literal["given", "result"] = "given" if asks_current else "result"
    load = CircuitNode(
        series=[
            _resistor(first, p[first]),
            CircuitNode(
                parallel=[_resistor(key, p[key]) for key in group],
                label=_ohms(parallel, given=False),
            ),
        ],
        label=f"R = {_ohms(total, given=False)}",
        role=role,
    )
    shape = (
        f"{_ohms(p[first])} in series with {', '.join(_ohms(p[key]) for key in group)} "
        f"in parallel: {_ohms(total, given=False)} in total"
    )
    if not asks_current:
        return _scene(CircuitSpec(source=CircuitSource(), load=load), f"{shape}.")
    volts = plain_number(p["V"], GIVEN_FIGURES)
    return _scene(
        CircuitSpec(
            source=CircuitSource(label=f"{volts} V"),
            load=load,
            current=f"I = {plain_number(answer)} A",
        ),
        f"A {volts} V battery across {shape}, driving {plain_number(answer)} A.",
    )
