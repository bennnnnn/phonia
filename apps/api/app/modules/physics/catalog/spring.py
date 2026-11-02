"""Verified spring operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

_G = var("g", "g", "meter / second ** 2", fallback="gravity")

# How far a mass on a spring swings: "amplitude 5 cm", "pulled 20 cm and released".
_AMPLITUDE = var(
    "amplitude",
    "A",
    "meter",
    words=(
        "amplitude",
        "pulled",
        "displaced",
        "stretched",
        "compressed",
        "pushed",
        "released",
    ),
    needs_words=True,
)
_SPRING_SHM = ("spring", "oscillat", "simple harmonic", "shm")
_MAX_SPEED_ASKS = (
    "maximum speed",
    "max speed",
    "maximum velocity",
    "max velocity",
    "peak speed",
    "greatest speed",
    "top speed",
)
_MAX_ACCELERATION_ASKS = (
    "maximum acceleration",
    "max acceleration",
    "peak acceleration",
    "greatest acceleration",
)


SPECS: tuple[FormulaSpec, ...] = (
    # A mass on a spring passes its centre at Aω, ω = √(k/m). Without this a
    # "max speed?" was answered with the period, 0.314 s.
    formula(
        "spring_max_speed",
        "spring",
        "Simple-harmonic-motion equation",
        "v_{max}",
        base_latex=r"v_{max} = A\omega = A\sqrt{\frac{k}{m}}",
        assumptions=("no friction or damping",),
        expression="amplitude*sqrt(k/m)",
        variables=(_AMPLITUDE, var("k", "k", "newton / meter"), var("m", "m", "kilogram")),
        binding=Binding(
            asks=_MAX_SPEED_ASKS,
            result=("meter / second",),
            inputs=(frozenset({"amplitude", "k", "m"}),),
            cues=_SPRING_SHM,
            nonnegative=True,
        ),
    ),
    # And it turns at the ends with Aω² = kA/m.
    formula(
        "spring_max_acceleration",
        "spring",
        "Simple-harmonic-motion equation",
        "a_{max}",
        base_latex=r"a_{max} = A\omega^2 = \frac{kA}{m}",
        assumptions=("no friction or damping",),
        expression="k*amplitude/m",
        variables=(_AMPLITUDE, var("k", "k", "newton / meter"), var("m", "m", "kilogram")),
        binding=Binding(
            asks=_MAX_ACCELERATION_ASKS,
            result=("meter / second ** 2",),
            inputs=(frozenset({"amplitude", "k", "m"}),),
            cues=_SPRING_SHM,
            nonnegative=True,
        ),
    ),
    formula(
        "spring_force",
        "spring",
        "Hooke's law",
        "F",
        variables=(
            var("k", "k", "newton / meter"),
            var("x", "x", "meter"),
        ),
    ),
    formula(
        "spring_energy",
        "spring",
        "Elastic potential-energy formula",
        "E_s",
        variables=(
            var("k", "k", "newton / meter"),
            var("x", "x", "meter"),
        ),
    ),
    formula(
        "shm_period",
        "spring",
        "Simple-harmonic-motion equation",
        "T",
        variables=(
            var("k", "k", "newton / meter"),
            var("m", "m", "kilogram"),
            var("x", "x", "meter"),
        ),
    ),
    formula(
        "pendulum_period",
        "spring",
        "Simple-harmonic-motion equation",
        "T",
        assumptions=("small-angle approximation",),
        variables=(
            var("L", "L", "meter"),
            var("g", "g", "meter / second ** 2"),
        ),
    ),
    formula(
        "shm_frequency",
        "spring",
        "Simple-harmonic-motion equation",
        "f",
        variables=(
            var("period", "T", "second"),
            var("k", "k", "newton / meter"),
            var("m", "m", "kilogram"),
        ),
    ),
    formula(
        "shm_max_speed",
        "spring",
        "Simple-harmonic-motion equation",
        "v_{max}",
        variables=(
            var("omega", r"\omega", "radian / second"),
            var("x", "x", "meter"),
        ),
    ),
    formula(
        "torsional_period",
        "spring",
        "Torsional-pendulum period",
        "T",
        base_latex=r"T = 2\pi\sqrt{I/\kappa}",
        expression="2*pi*sqrt(inertia/kappa)",
        variables=(
            var("inertia", "I", "kilogram * meter ** 2"),
            var(
                "kappa",
                r"\kappa",
                "newton * meter / radian",
                words=("torsion",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("period",),
            result=("second",),
            inputs=(frozenset({"inertia", "kappa"}),),
            cues=("torsional",),
            nonnegative=True,
        ),
    ),
    formula(
        "springs_parallel",
        "spring",
        "Springs in parallel",
        "k",
        base_latex="k = k_1 + k_2",
        expression="k1+k2",
        variables=(
            var("k1", "k_1", "newton / meter"),
            var("k2", "k_2", "newton / meter"),
        ),
        binding=Binding(
            asks=("spring constant", "equivalent spring constant", "effective spring constant"),
            result=("newton / meter",),
            inputs=(frozenset({"k1", "k2"}),),
            cues=("in parallel",),
            excludes=("series",),
            interchangeable=("k1", "k2"),
            nonnegative=True,
        ),
    ),
    formula(
        "springs_series",
        "spring",
        "Springs in series",
        "k",
        base_latex=r"\frac{1}{k} = \frac{1}{k_1}+\frac{1}{k_2}",
        expression="1/(1/k1+1/k2)",
        variables=(
            var("k1", "k_1", "newton / meter"),
            var("k2", "k_2", "newton / meter"),
        ),
        binding=Binding(
            asks=("spring constant", "equivalent spring constant", "effective spring constant"),
            result=("newton / meter",),
            inputs=(frozenset({"k1", "k2"}),),
            cues=("in series",),
            excludes=("parallel",),
            interchangeable=("k1", "k2"),
            nonnegative=True,
        ),
    ),
    formula(
        "physical_pendulum_period",
        "spring",
        "Physical-pendulum period",
        "T",
        base_latex=r"T = 2\pi\sqrt{\frac{I}{mgd}}",
        assumptions=("the swing is a small angle",),
        expression="2*pi*sqrt(inertia/(m*g*L))",
        variables=(
            var("inertia", "I", "kilogram * meter ** 2"),
            var("m", "m", "kilogram"),
            var("L", "d", "meter"),
            _G,
        ),
        binding=Binding(
            asks=("period",),
            result=("second",),
            inputs=(frozenset({"g", "inertia", "L", "m"}),),
            cues=("physical pendulum", "compound pendulum", "bar pendulum"),
            nonnegative=True,
        ),
    ),
    formula(
        "conical_pendulum_period",
        "spring",
        "Conical-pendulum period",
        "T",
        base_latex=r"T = 2\pi\sqrt{\frac{L\cos\theta}{g}}",
        expression="2*pi*sqrt(L*cos(angle_cone)/g)",
        variables=(
            var("L", "L", "meter"),
            var("angle_cone", r"\theta", dimensionless=True),
            _G,
        ),
        binding=Binding(
            asks=("period",),
            result=("second",),
            inputs=(frozenset({"angle_cone", "g", "L"}),),
            cues=("conical pendulum",),
            nonnegative=True,
        ),
    ),
    # A hanging mass stretches a spring until kx = mg.
    formula(
        "spring_constant_hanging",
        "spring",
        "Hooke's law",
        "k",
        base_latex=r"k = \frac{m g}{x}",
        expression="m*g/x",
        variables=(
            var("m", "m", "kilogram"),
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("x", "x", "meter"),
        ),
        binding=Binding(
            asks=("spring constant", "stiffness"),
            result=("newton / meter",),
            inputs=(frozenset({"m", "g", "x"}),),
            cues=("hang", "hangs", "hanging", "hung", "suspended"),
            nonnegative=True,
        ),
    ),
    formula(
        "spring_constant_force",
        "spring",
        "Hooke's law",
        "k",
        base_latex=r"k = \frac{F}{x}",
        expression="F/x",
        variables=(var("F", "F", "newton"), var("x", "x", "meter")),
        binding=Binding(
            asks=("spring constant", "stiffness"),
            result=("newton / meter",),
            inputs=(frozenset({"F", "x"}),),
            nonnegative=True,
        ),
    ),
    # A pendulum's length for a wanted period: L = g (T / 2 pi)^2.
    formula(
        "pendulum_length",
        "spring",
        "Simple pendulum",
        "L",
        base_latex=r"L = g\left(\frac{T}{2\pi}\right)^2",
        assumptions=("small swings",),
        expression="g*(period/(2*pi))**2",
        variables=(
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("period", "T", "second"),
        ),
        binding=Binding(
            asks=("length", "how long"),
            result=("meter",),
            inputs=(frozenset({"g", "period"}),),
            cues=("pendulum",),
            nonnegative=True,
        ),
    ),
    # A simple pendulum's frequency: f = (1/2π)√(g/L). 1.2 m swings at 0.455 Hz.
    formula(
        "pendulum_frequency",
        "spring",
        "Simple pendulum",
        "f",
        base_latex=r"f = \frac{1}{2\pi}\sqrt{\frac{g}{L}}",
        assumptions=("small swings",),
        expression="sqrt(g/L)/(2*pi)",
        variables=(
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("L", "L", "meter"),
        ),
        binding=Binding(
            asks=("frequency",),
            result=("hertz",),
            inputs=(frozenset({"g", "L"}),),
            cues=("pendulum",),
            excludes=("physical pendulum", "compound pendulum", "conical", "torsion", "angular"),
            nonnegative=True,
        ),
    ),
    # The mass a spring of stiffness k swings with a period T: m = k(T/2π)².
    formula(
        "spring_mass_from_period",
        "spring",
        "Mass-spring period",
        "m",
        base_latex=r"T = 2\pi\sqrt{\frac{m}{k}}",
        expression="k*(period/(2*pi))**2",
        variables=(var("k", "k", "newton / meter"), var("period", "T", "second")),
        binding=Binding(
            asks=("mass", "how heavy"),
            result=("kilogram",),
            inputs=(frozenset({"k", "period"}),),
            cues=("spring",),
            excludes=("pendulum",),
            nonnegative=True,
        ),
    ),
    # A count of oscillations in a stated time.
    formula(
        "frequency_from_count",
        "spring",
        "Frequency",
        "f",
        base_latex=r"f = \frac{n}{t}",
        expression="count/t",
        variables=(var("count", "n", dimensionless=True), var("t", "t", "second")),
        binding=Binding(
            asks=("frequency",),
            result=("hertz",),
            inputs=(frozenset({"count", "t"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "period_from_count",
        "spring",
        "Period",
        "T",
        base_latex=r"T = \frac{t}{n}",
        expression="t/count",
        variables=(var("count", "n", dimensionless=True), var("t", "t", "second")),
        binding=Binding(
            asks=("period",),
            result=("second",),
            inputs=(frozenset({"count", "t"}),),
            nonnegative=True,
        ),
    ),
)
