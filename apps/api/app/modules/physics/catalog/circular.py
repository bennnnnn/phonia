"""Verified circular operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

_G = var("g", "g", "meter / second ** 2", fallback="gravity")
# A vertical circle, or a point on one: the weight is part of the force there.
_VERTICAL_CIRCLE = (
    "vertical",
    "at the bottom",
    "at the top",
    "lowest point",
    "highest point",
    "loop",
)


SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "centripetal_force",
        "circular",
        "Circular-motion equation",
        "F_c",
        variables=(
            var("m", "m", "kilogram"),
            var("omega", r"\omega", "radian / second"),
            var("r", "r", "meter"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "centripetal_acceleration",
        "circular",
        "Circular-motion equation",
        "a_c",
        variables=(
            var("omega", r"\omega", "radian / second"),
            var("r", "r", "meter"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "orbital_period",
        "circular",
        "Orbital-motion equation",
        "T",
        variables=(
            var("omega", r"\omega", "radian / second"),
            var("r", "r", "meter"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "angular_velocity",
        "circular",
        "Circular-motion equation",
        "\\omega",
        variables=(
            var("period", "T", "second"),
            var("r", "r", "meter"),
            var("rpm", "n", "revolution / minute"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "banked_speed",
        "circular",
        "Frictionless banked curve",
        "v",
        base_latex=r"v=\sqrt{rg\tan\theta}",
        assumptions=("No friction", "The bank angle is the design angle"),
        variables=(
            var("angle", r"\theta", dimensionless=True),
            var("g", "g", "meter / second ** 2"),
            var("r", "r", "meter"),
        ),
    ),
    formula(
        "banked_angle",
        "circular",
        "Frictionless banked curve",
        r"\theta",
        base_latex=r"\theta=\arctan\frac{v^{2}}{rg}",
        assumptions=("No friction",),
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("r", "r", "meter"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "level_curve_speed",
        "circular",
        "Level curve limited by friction",
        "v",
        base_latex=r"v=\sqrt{\mu rg}",
        assumptions=("The road is level", "Friction supplies the centripetal force"),
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("mu", r"\mu", dimensionless=True),
            var("r", "r", "meter"),
        ),
    ),
    formula(
        "contact_speed",
        "circular",
        "Speed at which contact force vanishes",
        "v",
        base_latex=r"v=\sqrt{rg}",
        assumptions=("At the top, the normal force or tension is zero",),
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("r", "r", "meter"),
        ),
    ),
    formula(
        "loop_entry_speed",
        "circular",
        "Speed to complete a vertical loop",
        "v",
        base_latex=r"v = \sqrt{5gr}",
        assumptions=("the track is entered at the bottom", "the car just keeps contact at the top"),
        expression="sqrt(5*g*r)",
        variables=(var("r", "r", "meter"), _G),
        binding=Binding(
            asks=("speed", "minimum speed", "velocity"),
            result=("meter / second",),
            inputs=(frozenset({"g", "r"}),),
            cues=("just completes", "just complete"),
            excludes=("at the top",),
            nonnegative=True,
        ),
    ),
    # A point a radius r from the axis, once round every T: v = 2πr/T. Read as
    # d/t, "sits 2.5 m from the centre, turns once every 6 s" moved 0.417 m/s.
    formula(
        "speed_from_period",
        "circular",
        "Speed in uniform circular motion",
        "v",
        base_latex=r"v = \frac{2\pi r}{T}",
        assumptions=("one turn covers the circumference 2πr",),
        expression="2*pi*r/period",
        variables=(var("r", "r", "meter"), var("period", "T", "second")),
        binding=Binding(
            asks=("speed", "how fast", "linear speed", "tangential speed", "velocity"),
            result=("meter / second",),
            inputs=(frozenset({"r", "period"}),),
            cues=(
                "once every",
                "once in",
                "one revolution",
                "one rotation",
                "one turn",
                "one full turn",
                "turn every",
                "revolution every",
                "rotation every",
                "per revolution",
                "per rotation",
            ),
            # The length must be the radius: not a diameter, a track or a lap.
            excludes=("diameter", "circumference", "track", "lap", "perimeter", "around a"),
            nonnegative=True,
        ),
    ),
    # Over the top of a hump the road pushes up less than mg: part of the weight
    # turns the car on its circle. N = mg answered 9810 N for 4810 N.
    formula(
        "hump_normal_force",
        "circular",
        "Circular motion over a hump",
        "N",
        base_latex=r"N = m\left(g - \frac{v^2}{r}\right)",
        assumptions=("at the top of the hump, with the centre of its circle straight below",),
        expression="m*(g - v**2/r)",
        variables=(
            var("m", "m", "kilogram"),
            var("v", "v", "meter / second"),
            var("r", "r", "meter"),
            _G,
        ),
        binding=Binding(
            asks=(
                "normal force",
                "normal reaction",
                "reaction force",
                "contact force",
                "apparent weight",
            ),
            result=("newton",),
            inputs=(frozenset({"m", "v", "r", "g"}),),
            cues=("hump", "crest", "top of a hill", "top of the hill", "hilltop", "humpback"),
            excludes=("bottom", "dip", "valley", "loop"),
            nonnegative=True,
        ),
    ),
    # A turning rate in rpm or rad/s, as the time for one turn.
    formula(
        "period_from_rate",
        "circular",
        "Period of rotation",
        "T",
        base_latex=r"T = \frac{2\pi}{\omega}",
        expression="2*pi/omega",
        variables=(var("omega", r"\omega", "radian / second"),),
        binding=Binding(
            asks=("period", "time for one revolution", "time for one rotation"),
            result=("second",),
            inputs=(frozenset({"omega"}),),
            nonnegative=True,
        ),
    ),
    # A mass whirled on a string: the tension is the centripetal force.
    formula(
        "circle_string_tension",
        "circular",
        "Centripetal force",
        "T",
        base_latex=r"T = \frac{m v^2}{r}",
        assumptions=("a horizontal circle with gravity ignored",),
        expression="m*v**2/r",
        variables=(
            var("m", "m", "kilogram"),
            var("v", "v", "meter / second"),
            var("r", "r", "meter"),
        ),
        binding=Binding(
            asks=("tension", "centripetal force"),
            result=("newton",),
            inputs=(frozenset({"m", "v", "r"}),),
            cues=("circle", "circular", "swung", "whirled", "revolves"),
            # In a vertical circle the weight adds or subtracts: 8.33 N at the
            # bottom was the stone's 11.3 N less its weight.
            excludes=_VERTICAL_CIRCLE,
            nonnegative=True,
        ),
    ),
    # At the bottom of a vertical circle the string holds up the weight as well.
    formula(
        "vertical_circle_tension_bottom",
        "circular",
        "Circular motion in a vertical circle",
        "T",
        base_latex=r"T = m\left(\frac{v^2}{r} + g\right)",
        assumptions=("at the lowest point, where the centre is straight above",),
        expression="m*(v**2/r + g)",
        variables=(
            var("m", "m", "kilogram"),
            var("v", "v", "meter / second"),
            var("r", "r", "meter"),
            _G,
        ),
        binding=Binding(
            asks=("tension",),
            result=("newton",),
            inputs=(frozenset({"m", "v", "r", "g"}),),
            cues=("at the bottom", "lowest point"),
            excludes=("at the top", "highest point", "horizontal"),
            nonnegative=True,
        ),
    ),
)
