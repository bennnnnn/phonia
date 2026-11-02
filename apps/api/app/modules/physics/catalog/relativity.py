"""Verified special-relativity operations, and the Schwarzschild radius.

A speed written as a fraction of c ("0.8c") reads as the speed of light, so
these laws need no other cue; a car at 20 m/s is never answered with the Lorentz factor.
"""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

_RELATIVISTIC = ("relativistic", "relativity", "speed of light", "lorentz")
_MASS = var("m", "m", "kilogram", fallback="particle_mass")
_SPEED = var("v", "v", "meter / second")
_GAMMA = "sqrt(1 - v**2/c_light**2)"


def _moving(
    operation: str,
    law: str,
    symbol: str,
    base: str,
    expression: str,
    asks: tuple[str, ...],
    result: str,
) -> FormulaSpec:
    return formula(
        operation,
        "modern",
        law,
        symbol,
        base_latex=base,
        expression=expression,
        variables=(_MASS, _SPEED),
        binding=Binding(
            asks=asks,
            result=(result,),
            inputs=(frozenset({"m", "v"}),),
            cues=_RELATIVISTIC,
            nonnegative=True,
        ),
    )


_BOOST = "sqrt(1 - v**2/c_light**2)"


def _lorentz(
    operation: str,
    symbol: str,
    base: str,
    expression: str,
    asks: tuple[str, ...],
) -> FormulaSpec:
    return formula(
        operation,
        "modern",
        "Lorentz transformation",
        symbol,
        base_latex=base,
        assumptions=("a boost along one axis",),
        expression=expression,
        variables=(
            var("event_x", "x", "meter", words=("coordinate", "position"), needs_words=True),
            var("t", "t", "second", words=("time",), needs_words=True),
            var("v", "v", "meter / second"),
        ),
        binding=Binding(
            asks=asks,
            result=("meter" if operation.endswith("coordinate") else "second",),
            inputs=(frozenset({"event_x", "t", "v"}),),
            cues=("lorentz transformation",),
            nonnegative=False,
        ),
    )


SPECS: tuple[FormulaSpec, ...] = (
    _moving(
        "relativistic_momentum",
        "Relativistic momentum",
        "p",
        r"p = \gamma m v = \frac{mv}{\sqrt{1 - v^2/c^2}}",
        f"m*v/{_GAMMA}",
        ("relativistic momentum", "momentum"),
        "kilogram * meter / second",
    ),
    _moving(
        "relativistic_total_energy",
        "Relativistic energy",
        "E",
        r"E = \gamma m c^2 = \frac{mc^2}{\sqrt{1 - v^2/c^2}}",
        f"m*c_light**2/{_GAMMA}",
        ("total energy", "relativistic energy"),
        "joule",
    ),
    _moving(
        "relativistic_kinetic_energy",
        "Relativistic kinetic energy",
        "K",
        r"K = (\gamma - 1) m c^2, \quad \gamma = \frac{1}{\sqrt{1 - v^2/c^2}}",
        f"(1/{_GAMMA} - 1)*m*c_light**2",
        ("relativistic kinetic energy", "kinetic energy"),
        "joule",
    ),
    formula(
        "energy_momentum_relation",
        "modern",
        "Energy-momentum relation",
        "E",
        base_latex=r"E^2 = (pc)^2 + (mc^2)^2",
        expression="sqrt((p_momentum*c_light)**2 + (m*c_light**2)**2)",
        variables=(_MASS, var("p_momentum", "p", "kilogram * meter / second")),
        binding=Binding(
            asks=("total energy", "energy"),
            result=("joule",),
            inputs=(frozenset({"m", "p_momentum"}),),
            cues=(*_RELATIVISTIC, "rest mass"),
            nonnegative=True,
        ),
    ),
    # "fires a probe forward at 0.5c": the two speeds add along one line. A
    # probe fired backward subtracts, and that is not this reading.
    formula(
        "relativistic_velocity_addition",
        "modern",
        "Relativistic velocity addition",
        "u",
        base_latex=r"u = \frac{v_1 + v_2}{1 + v_1 v_2/c^2}",
        assumptions=("both speeds along the same line, adding",),
        expression="(v1 + v2)/(1 + v1*v2/c_light**2)",
        variables=(var("v1", "v_1", "meter / second"), var("v2", "v_2", "meter / second")),
        binding=Binding(
            asks=("relative speed", "relative velocity", "speed", "velocity"),
            result=("meter / second",),
            inputs=(frozenset({"v1", "v2"}),),
            cues=_RELATIVISTIC,
            excludes=("backward", "backwards", "opposite", "rearward", "behind"),
            interchangeable=("v1", "v2"),
            nonnegative=True,
        ),
    ),
    formula(
        "schwarzschild_radius",
        "gravitation",
        "Schwarzschild radius",
        "r_s",
        base_latex=r"r_s = \frac{2GM}{c^2}",
        assumptions=("a non-rotating, uncharged mass",),
        expression="2*G_grav*M/c_light**2",
        variables=(var("M", "M", "kilogram", fallback="body_mass"),),
        binding=Binding(
            asks=("schwarzschild radius", "event horizon", "radius"),
            result=("meter",),
            inputs=(frozenset({"M"}),),
            cues=("schwarzschild", "black hole", "event horizon"),
            nonnegative=True,
        ),
    ),
    formula(
        "gravitational_frequency_shift",
        "gravitation",
        "Gravitational frequency shift",
        r"\frac{\Delta f}{f}",
        base_latex=r"\frac{\Delta f}{f} = \frac{gh}{c^2}",
        assumptions=("a weak uniform field",),
        expression="g*h/c_light**2",
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("h", "h", "meter", words=("above", "height"), needs_words=True),
        ),
        binding=Binding(
            asks=("fractional frequency shift", "frequency shift"),
            result=("dimensionless",),
            inputs=(frozenset({"g", "h"}),),
            cues=("gravitational",),
            nonnegative=True,
        ),
    ),
    _lorentz(
        "lorentz_coordinate",
        "x'",
        r"x' = \gamma(x - vt)",
        f"(event_x - v*t)/{_BOOST}",
        ("transformed coordinate",),
    ),
    _lorentz(
        "lorentz_time",
        "t'",
        r"t' = \gamma(t - vx/c^2)",
        f"(t - v*event_x/c_light**2)/{_BOOST}",
        ("transformed time",),
    ),
    formula(
        "gravitational_time_factor",
        "gravitation",
        "Gravitational time dilation",
        r"d\tau/dt",
        base_latex=r"\frac{d\tau}{dt} = \sqrt{1-\frac{2GM}{rc^2}}",
        assumptions=("the Schwarzschild factor, outside the horizon",),
        expression="sqrt(1-2*G_grav*M/(radial_distance*c_light**2))",
        variables=(
            var("M", "M", "kilogram", fallback="body_mass"),
            var(
                "radial_distance",
                "r",
                "meter",
                words=("distance", "radius"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("time-dilation factor", "dilation factor"),
            result=("dimensionless",),
            inputs=(frozenset({"M", "radial_distance"}),),
            cues=("gravitational",),
            excludes=("velocity", "speed of light"),
            nonnegative=True,
            at_most=1.0,
        ),
    ),
)
