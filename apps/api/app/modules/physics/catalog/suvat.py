"""Verified suvat operations."""

from __future__ import annotations

from app.services.law_binding.spec import (
    Binding,
    FormulaSpec,
    FormulaVariant,
    VariableSpec,
    formula,
    var,
)

_LAW = "SUVAT constant-acceleration equation"
_SPEED = "meter / second"
_ACCELERATION = "meter / second ** 2"

# The word just before a speed says which one it is: "from 10 m/s to 30 m/s".
_INITIAL = (
    "initial",
    "initially",
    "from",
    "starts at",
    "starting at",
    "at first",
    "moving at",
    "travelling at",
    "traveling at",
)
_FINAL = ("final", "finally", "to", "reaches", "reaching", "until", "up to", "becomes", "ends at")
_SLOWING = ("decelerat", "retard", "slows down at", "brakes at", "braking at")

# Two moving bodies: their two speeds are not one body's u and v. Two trains
# 2.1 km apart closing at 72 and 54 km/h meet after 60 s; read as one train
# speeding up from 54 to 72 km/h, they "met" after 120 s.
TWO_BODIES = (
    "each other",
    "meet",
    "catch up",
    "catches up",
    "catching up",
    "chasing",
    "chases",
    "overtake",
    "overtakes",
    "overtaking",
    "two cars",
    "two trains",
    "two cyclists",
    "two runners",
    "two buses",
    "two boats",
    "two planes",
    "two people",
    "relative to",
    "relative speed",
    "relative velocity",
)

_U = var("u", "u", _SPEED, words=_INITIAL, implied=(("from rest", 0.0),))
_V = var(
    "v",
    "v",
    _SPEED,
    words=_FINAL,
    # "brakes uniformly and stops in 25 m": the stop is the final speed.
    implied=(
        ("to rest", 0.0),
        ("to a stop", 0.0),
        ("to a halt", 0.0),
        ("stops in", 0.0),
        ("stops within", 0.0),
        ("stopping in", 0.0),
        ("stopped in", 0.0),
    ),
)
_A = var("a", "a", _ACCELERATION, negating=_SLOWING)
_D = var("d", "s", "meter")
_T = var("t", "t", "second")


def _inputs(*sets: str) -> tuple[frozenset[str], ...]:
    return tuple(frozenset(given) for given in sets)


def _with(*variables: VariableSpec) -> tuple[VariableSpec, ...]:
    return (
        *sorted(variables, key=lambda variable: variable.name),
        var("distance_path", "path", dimensionless=True, visible=False),
    )


SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "suvat_velocity",
        "suvat",
        _LAW,
        "v",
        base_latex="v = u + at",
        variants=(
            FormulaVariant(
                latex=r"v = \sqrt{u^2 + 2as}",
                present=frozenset({"d"}),
                absent=frozenset({"t"}),
            ),
            FormulaVariant(
                latex=r"v = \frac{2s}{t} - u",
                present=frozenset({"d", "t"}),
                absent=frozenset({"a"}),
            ),
        ),
        variables=_with(_A, _D, _T, _U),
        binding=Binding(
            asks=("final velocity", "final speed", "velocity", "speed", "how fast"),
            result=(_SPEED,),
            excludes=TWO_BODIES,
            inputs=_inputs("uat", "uad", "udt"),
            result_words=_FINAL,
        ),
    ),
    formula(
        "suvat_distance",
        "suvat",
        _LAW,
        "s",
        base_latex=r"s = ut + \tfrac{1}{2}at^2",
        variants=(
            FormulaVariant(
                latex=r"s = \int_0^t |u+a\tau|\,d\tau",
                equals=(("distance_path", 1.0),),
            ),
            FormulaVariant(
                latex=r"s = \int_0^t |u+a\tau|\,d\tau",
                absent=frozenset({"distance_path"}),
            ),
            FormulaVariant(
                latex=r"s = \frac{v^2 - u^2}{2a}",
                present=frozenset({"v"}),
                absent=frozenset({"t"}),
            ),
            FormulaVariant(
                latex=r"s = \tfrac{1}{2}(u + v)t",
                present=frozenset({"v", "t"}),
                absent=frozenset({"a"}),
            ),
            FormulaVariant(
                latex=r"s = vt - \tfrac{1}{2}at^2",
                present=frozenset({"v", "a", "t"}),
                absent=frozenset({"u"}),
            ),
        ),
        variables=_with(_A, _T, _U, _V),
        binding=Binding(
            asks=("displacement", "distance", "how far"),
            result=("meter",),
            excludes=TWO_BODIES,
            inputs=_inputs("uat", "uva", "uvt", "vat"),
        ),
    ),
    formula(
        "suvat_time",
        "suvat",
        _LAW,
        "t",
        base_latex="v = u + at",
        variants=(
            FormulaVariant(
                latex=r"\tfrac{1}{2}at^2 + ut - s = 0",
                present=frozenset({"d"}),
                absent=frozenset({"v"}),
            ),
            FormulaVariant(
                latex=r"t = \frac{2s}{u + v}",
                present=frozenset({"d", "v"}),
                absent=frozenset({"a"}),
            ),
        ),
        variables=_with(_A, _D, _U, _V),
        binding=Binding(
            asks=("how long", "time taken", "time"),
            result=("second",),
            excludes=TWO_BODIES,
            inputs=_inputs("uva", "uad", "uvd"),
        ),
    ),
    formula(
        "suvat_acceleration",
        "suvat",
        _LAW,
        "a",
        base_latex="v = u + at",
        variants=(
            FormulaVariant(
                latex=r"a = \frac{v^2 - u^2}{2s}",
                present=frozenset({"d"}),
                absent=frozenset({"t"}),
            ),
            FormulaVariant(
                latex=r"a = \frac{2(s - ut)}{t^2}",
                present=frozenset({"d", "t"}),
                absent=frozenset({"v"}),
            ),
        ),
        variables=_with(_D, _T, _U, _V),
        binding=Binding(
            asks=("acceleration", "deceleration", "retardation"),
            result=(_ACCELERATION,),
            excludes=TWO_BODIES,
            inputs=_inputs("uvt", "uvd", "udt"),
        ),
    ),
    # The starting speed, which no other operation solves for.
    formula(
        "suvat_initial_velocity",
        "suvat",
        _LAW,
        "u",
        base_latex="v = u + at",
        expression="v - a*t",
        variants=(
            FormulaVariant(
                latex=r"v^2 = u^2 + 2as",
                present=frozenset({"v", "a", "d"}),
                expression="sqrt(v**2 - 2*a*d)",
            ),
            FormulaVariant(
                latex=r"s = \tfrac{1}{2}(u + v)t",
                present=frozenset({"v", "d", "t"}),
                expression="2*d/t - v",
            ),
            FormulaVariant(
                latex=r"s = ut + \tfrac{1}{2}at^2",
                present=frozenset({"a", "d", "t"}),
                expression="d/t - a*t/2",
            ),
        ),
        variables=_with(_A, _D, _T, _V),
        binding=Binding(
            asks=("initial velocity", "initial speed", "starting speed", "starting velocity"),
            result=(_SPEED,),
            excludes=TWO_BODIES,
            inputs=_inputs("vat", "vad", "vdt", "adt"),
            result_words=_INITIAL,
        ),
    ),
)
