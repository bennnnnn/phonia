# ruff: noqa: RUF002
"""Kinetics: integrated rate laws, half-lives, rate laws from data, Arrhenius, Michaelis–Menten."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    TIME_UNIT_PATTERN,
    TIME_UNITS,
    _floats,
    _search,
    k_time_unit_conflict,
    rate_constant,
    seconds_per,
    temperature_kelvin,
    timed,
)
from app.modules.chemistry.schemas import ChemistryIntent

_HALF_LIFE_VALUE = re.compile(
    rf"\bhalf[- ]life\b[^.\d]{{0,60}}?(?:=|is|of|was)\s*({_N})\s*({TIME_UNIT_PATTERN})\b",
    re.IGNORECASE,
)


_ASKS_RATE_CONSTANT = re.compile(
    r"\b(?:find|calculate|compute|determine|what\s+is)\s+(?:the\s+|its\s+)?"
    r"(?:(?:first[- ]order\s+)?rate\s+constant|(?-i:k))\b",
    re.IGNORECASE,
)


def _extract_first_order(text: str) -> ChemistryIntent | None:
    if re.search(r"\bfirst[- ]order\b", text, re.IGNORECASE) and re.search(
        r"half[- ]life", text, re.IGNORECASE
    ):
        # The half-life is in the time unit of k, so a k with no unit has no answer unit.
        rate = rate_constant(text)
        if rate is not None and rate[1] is not None:
            return ChemistryIntent(
                kind="kinetics",
                chemistry_op="first_order_half_life",
                params={"rate_constant": rate[0]},
                units={"rate_constant_time": rate[1]},
            )
        # "The half-life of a first-order reaction is 20 min. Find k."
        half_life = _HALF_LIFE_VALUE.search(text)
        if rate is None and half_life is not None and _ASKS_RATE_CONSTANT.search(text):
            return ChemistryIntent(
                kind="kinetics",
                chemistry_op="first_order_half_life",
                params={"half_life": float(half_life.group(1))},
                units={"half_life_time": TIME_UNITS[half_life.group(2).lower()][0]},
            )
    timed_fraction = _first_order_time(text)
    if timed_fraction is not None:
        return timed_fraction
    if re.search(r"\bfirst[- ]order\b", text, re.IGNORECASE):
        initial = _search(rf"\[A\](?:0|₀)\s*=\s*({_N})", text, flags=0)
        rate = rate_constant(text)
        elapsed = timed(text, r"\bt")
        if initial is not None and rate is not None and elapsed is not None:
            # k and t must share a time unit; convert k when the question mixes them.
            constant = rate[0]
            if rate[1] is not None and rate[1] != elapsed[1]:
                constant = rate[0] * seconds_per(elapsed[1]) / seconds_per(rate[1])
            return ChemistryIntent(
                kind="kinetics",
                chemistry_op="first_order_concentration",
                params={"initial": initial, "rate_constant": constant, "time": elapsed[0]},
                units={"time": elapsed[1]},
            )
    if re.search(r"\bArrhenius\b", text, re.IGNORECASE):
        factor = rate_constant(text, "A")
        energy = _search(rf"(?:Ea|Eₐ|activation energy)\s*(?:=|of)?\s*({_N})\s*(k?J)", text)
        energy_unit = re.search(
            r"(?:Ea|Eₐ|activation energy)\s*(?:=|of)?\s*" + _N + r"\s*(k?J)", text, re.IGNORECASE
        )
        temperature = temperature_kelvin(text)
        if factor is not None and energy is not None and isinstance(temperature, float):
            if energy_unit and energy_unit.group(1).lower() == "kj":
                energy *= 1000
            units = {"frequency_factor_time": factor[1]} if factor[1] else {}
            return ChemistryIntent(
                kind="kinetics",
                chemistry_op="arrhenius",
                params={
                    "pre_exponential": factor[0],
                    "activation_energy": energy,
                    "temperature": temperature,
                },
                units=units,
            )
    return None


_INTEGRATED_ORDERS: tuple[tuple[str, str, str], ...] = (
    ("zero", "zero_order", "zero_order_half_life"),
    ("second", "second_order", "second_order_half_life"),
)


def _extract_rate_laws(text: str) -> ChemistryIntent | None:
    for order, name, half_life_name in _INTEGRATED_ORDERS:
        if not re.search(rf"\b{order}[- ]order\b", text, re.IGNORECASE):
            continue
        initial = _search(rf"\[A\](?:0|₀)\s*=\s*({_N})", text, flags=0)
        rate = _search(rf"\bk\s*=\s*({_N})", text)
        if k_time_unit_conflict(text):
            return None  # k per minute with t in seconds cannot be combined unchecked
        if (
            initial is not None
            and rate is not None
            and re.search(r"half[- ]life", text, re.IGNORECASE)
        ):
            return ChemistryIntent(
                kind="kinetics",
                chemistry_op=half_life_name,
                params={"initial": initial, "rate_constant": rate},
            )
        elapsed = timed(text, r"\bt")
        if initial is not None and rate is not None and elapsed is not None and elapsed[1] == "s":
            return ChemistryIntent(
                kind="kinetics",
                chemistry_op=name,
                params={"initial": initial, "rate_constant": rate, "time": elapsed[0]},
                units={"time": "s"},
            )
    if re.search(r"\brate law\b", text, re.IGNORECASE):
        a1 = _search(rf"\ba1\s*=\s*({_N})", text)
        rate1 = _search(rf"\brate1\s*=\s*({_N})", text)
        a2 = _search(rf"\ba2\s*=\s*({_N})", text)
        rate2 = _search(rf"\brate2\s*=\s*({_N})", text)
        params = _floats(a1=a1, rate1=rate1, a2=a2, rate2=rate2)
        second = _floats(
            b1=_search(rf"\bb1\s*=\s*({_N})", text), b2=_search(rf"\bb2\s*=\s*({_N})", text)
        )
        if params is not None:
            return ChemistryIntent(
                kind="kinetics", chemistry_op="rate_law", params={**params, **(second or {})}
            )
    if re.search(r"\btwo-temperature Arrhenius\b", text, re.IGNORECASE):
        params = _floats(
            k1=_search(rf"\bk1\s*=\s*({_N})", text),
            t1=_search(rf"\bt1\s*=\s*({_N})", text),
            k2=_search(rf"\bk2\s*=\s*({_N})", text),
            t2=_search(rf"\bt2\s*=\s*({_N})", text),
        )
        if params is not None:
            return ChemistryIntent(
                kind="kinetics", chemistry_op="arrhenius_two_point", params=params
            )
    return None


# Concentrations a Km and an [S] are written in, in mol/L.
_CONCENTRATION = {
    "M": 1.0,
    "mol/L": 1.0,
    "mM": 1e-3,
    "mmol/L": 1e-3,
    "µM": 1e-6,
    "μM": 1e-6,
    "uM": 1e-6,
    "nM": 1e-9,
}


_CONCENTRATION_UNIT = "|".join(re.escape(unit) for unit in sorted(_CONCENTRATION, key=len)[::-1])


# A rate: an amount or a concentration per unit time ("10 μmol/min", "0.5 mM/s").
_RATE_UNIT = r"(?:[µμun]?mol|[mµμun]?M)\s*/\s*(?:s|min|h)\b"


def _michaelis_value(label: str, text: str, unit: str) -> tuple[float, str | None] | None:
    """``Km = 2 mM`` as (2.0, "mM"); a bare ``Km = 2`` as (2.0, None)."""
    match = re.search(rf"{label}\s*=\s*({_N})(?:\s*({unit})(?![A-Za-z]))?", text)
    if match is None:
        return None
    return float(match.group(1)), match.group(2)


def _extract_michaelis(text: str) -> ChemistryIntent | None:
    """Michaelis-Menten, named or recognized by its Vmax and Km, in the units it is written in.

    Km and [S] share one concentration unit (or are both bare); a mixed pair is converted to
    mol/L. The rate keeps the unit of the Vmax or v it is written with.
    """
    named = re.search(r"\bMichaelis[- ]Menten\b", text, re.IGNORECASE)
    if not named and not (re.search(r"\bVmax\b", text) and re.search(r"\bKm\b", text)):
        return None
    read = {
        "v": _michaelis_value(r"\bv(?!\s*=\s*[\d.]+\s*m?L\b)", text, _RATE_UNIT),
        "vmax": _michaelis_value(r"\bVmax", text, _RATE_UNIT),
        "km": _michaelis_value(r"\bKm", text, _CONCENTRATION_UNIT),
        "substrate": _michaelis_value(r"(?:\bS|\[S\])", text, _CONCENTRATION_UNIT),
    }
    present = {key: value for key, value in read.items() if value is not None}
    if len(present) != 3:
        return None
    rate_units = {present[key][1] for key in ("v", "vmax") if key in present}
    concentration_units = {present[key][1] for key in ("km", "substrate") if key in present}
    if len(rate_units) != 1 or (None in concentration_units and len(concentration_units) > 1):
        return None
    params = {key: value for key, (value, _unit) in present.items()}
    concentration = next(iter(concentration_units))
    if len(concentration_units) > 1:
        for key in ("km", "substrate"):
            if key in present:
                params[key] = present[key][0] * _CONCENTRATION[present[key][1] or "M"]
        concentration = "mol/L"
    units = {
        name: unit
        for name, unit in (("rate", next(iter(rate_units))), ("concentration", concentration))
        if unit is not None
    }
    return ChemistryIntent(
        kind="biochemistry", chemistry_op="michaelis_menten", params=params, units=units
    )


# "75% of the reactant is gone": what reacted. "fall to 25% of its initial value", "25%
# remains": what is left.
_GONE = re.compile(
    rf"({_N})\s*%\s*(?:of\s+(?:the\s+|its\s+)?[A-Za-z0-9]+\s+)?(?:is\s+|has\s+|have\s+|was\s+|to\s+be\s+)?"
    r"(?:been\s+)?(?:gone|consumed|reacted|decomposed|used\s+up|converted)\b",
    re.IGNORECASE,
)
_LEFT = re.compile(
    r"\b(?:fall|falls|drop|drops|decrease|decreases|decline|declines|reduced?|go(?:es)?\s+down)"
    rf"\s+to\s+({_N})\s*%"
    rf"|({_N})\s*%\s*(?:of\s+(?:the\s+|its\s+)?[A-Za-z0-9]+\s+)?(?:remains?|is\s+left|left|remaining)\b",
    re.IGNORECASE,
)
_TIME_ASK = re.compile(
    r"\bhow\s+(?:long|much\s+time)\b|\b(?:what|find|calculate)\b[^.?!]*\btime\b", re.I
)


def _first_order_time(text: str) -> ChemistryIntent | None:
    """t = ln([A]₀/[A]) / k for a first-order reaction to reach a stated fraction.

    The fraction is what is left: "fall to 25%" leaves 0.25, "75% is gone" leaves 0.25. One
    percentage, one reading of it, and a k with its time unit; anything else declines.
    """
    if not re.search(r"\bfirst[- ]order\b", text, re.IGNORECASE) or not _TIME_ASK.search(text):
        return None
    if re.search(r"half[- ]life", text, re.IGNORECASE) or len(re.findall(r"%", text)) != 1:
        return None
    gone, left = list(_GONE.finditer(text)), list(_LEFT.finditer(text))
    if len(gone) + len(left) != 1:
        return None
    if gone:
        remaining = 1 - float(gone[0].group(1)) / 100
    else:
        remaining = float(left[0].group(1) or left[0].group(2)) / 100
    rate = rate_constant(text)
    if rate is None or rate[1] is None or not 0 < remaining < 1:
        return None
    return ChemistryIntent(
        kind="kinetics",
        chemistry_op="first_order_time",
        params={"rate_constant": rate[0], "remaining": remaining},
        units={"rate_constant_time": rate[1]},
    )
