"""Closed Kirchhoff, inductor, and RL templates."""

from __future__ import annotations

import re

from app.modules.physics.extractors.school_common import (
    _HENRY,
    _SECOND,
    _has_word,
    _henry_unit,
    _intent,
    _one,
    _sum_directed,
)
from app.modules.physics.extractors.stated_values import ordered_values
from app.modules.physics.extractors.unit_patterns import AMP_PATTERN, OHM_PATTERN
from app.modules.physics.schemas import PhysicsIntent


def extract_junction(text: str, lower: str) -> PhysicsIntent | None:
    if not any(word in lower for word in ("junction", "node", "kirchhoff")):
        return None
    if "loop" in lower and "junction" not in lower and "node" not in lower:
        return None
    entering = _sum_directed(text, r"enter(?:s|ing)?", "entering")
    leaving = _sum_directed(text, r"leave[s]?|leaving", "leaving")
    if entering is None and leaving is None:
        return None
    return _intent(
        "circuit",
        "kirchhoff_junction",
        {"i_enter": entering or 0.0, "i_leave": leaving or 0.0},
        {"i_enter": "A", "i_leave": "A"},
    )


def extract_loop(text: str, lower: str) -> PhysicsIntent | None:
    if "loop" not in lower:
        return None
    volts = ordered_values(text, r"V|volts?")
    resistors = [value for value, _unit in ordered_values(text, OHM_PATTERN)]
    if len(volts) != 1 or not 2 <= len(resistors) <= 4:
        return None
    params = {"V": volts[0][0]}
    units = {"V": "V"}
    for index, resistance in enumerate(resistors, start=1):
        params[f"R{index}"] = resistance
        units[f"R{index}"] = "ohm"
    return _intent("circuit", "kirchhoff_loop", params, units)


def extract_inductor(text: str, lower: str) -> PhysicsIntent | None:
    if "inductor" not in lower and "henry" not in lower and "henries" not in lower:
        return None
    inductance = _one(text, _HENRY)
    if inductance is None:
        return None
    henry = _henry_unit(inductance[1] or "H")
    if "energy" in lower:
        current = _one(text, AMP_PATTERN)
        if current is None:
            return None
        return _intent(
            "circuit",
            "inductor_energy",
            {"inductance": inductance[0], "I": current[0]},
            {"inductance": henry, "I": current[1] or "A"},
        )
    amps = ordered_values(text, AMP_PATTERN)
    seconds = _one(text, _SECOND, ("in", "over", "during"), require_keyword=True)
    if seconds is None or not amps:
        return None
    if len(amps) == 1:
        delta = amps[0][0]
    elif len(amps) == 2:
        delta = abs(amps[1][0] - amps[0][0])
    else:
        return None
    return _intent(
        "circuit",
        "inductor_emf",
        {"inductance": inductance[0], "delta_i": delta, "dt": seconds[0]},
        {"inductance": henry, "delta_i": "A", "dt": seconds[1] or "s"},
    )


def extract_rl(text: str, lower: str) -> PhysicsIntent | None:
    if re.search(r"\brl\b", lower) is None and "inductor" not in lower:
        return None
    inductance = _one(text, _HENRY)
    resistance = _one(text, OHM_PATTERN)
    if inductance is None or resistance is None:
        return None
    henry = _henry_unit(inductance[1] or "H")
    if "time constant" in lower:
        return _intent(
            "circuit",
            "rl_time_constant",
            {"inductance": inductance[0], "R": resistance[0]},
            {"inductance": henry, "R": resistance[1] or "ohm"},
        )
    volts = ordered_values(text, r"V|volts?")
    amps = ordered_values(text, AMP_PATTERN)
    seconds = _one(text, _SECOND, ("after", "in", "at"), require_keyword=True)
    if seconds is None:
        return None
    growing = _has_word(lower, ("closed", "grows", "growing", "rise", "rises", "rising"))
    decaying = _has_word(lower, ("opened", "decays", "decaying", "dies"))
    if growing == decaying:
        return None
    if growing:
        if len(volts) != 1:
            return None
        return _intent(
            "circuit",
            "rl_growth",
            {
                "V": volts[0][0],
                "R": resistance[0],
                "inductance": inductance[0],
                "t": seconds[0],
            },
            {
                "V": volts[0][1] or "V",
                "R": resistance[1] or "ohm",
                "inductance": henry,
                "t": seconds[1] or "s",
            },
        )
    if len(amps) != 1:
        return None
    return _intent(
        "circuit",
        "rl_decay",
        {
            "I0": amps[0][0],
            "R": resistance[0],
            "inductance": inductance[0],
            "t": seconds[0],
        },
        {
            "I0": amps[0][1] or "A",
            "R": resistance[1] or "ohm",
            "inductance": henry,
            "t": seconds[1] or "s",
        },
    )
