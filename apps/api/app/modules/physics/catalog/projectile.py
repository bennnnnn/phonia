"""Verified projectile operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

# A launch "horizontally" from a height states the angle (0°) without a number,
# and so does anything that rolls, slides or drives off an edge.
_LEVEL_LAUNCH = (
    "horizontally",
    "rolls off",
    "rolled off",
    "rolling off",
    "slides off",
    "slid off",
    "sliding off",
    "runs off",
    "ran off",
    "drives off",
    "drove off",
)
_LAUNCH = (
    var(
        "angle",
        r"\theta",
        dimensionless=True,
        implied=tuple((phrase, 0.0) for phrase in _LEVEL_LAUNCH),
    ),
    var("g", "g", "meter / second ** 2", fallback="gravity"),
    var("h0", "h_0", "meter"),
    var("v0", "v_0", "meter / second"),
)
_FROM_A_HEIGHT = (frozenset({"angle", "g", "h0", "v0"}),)


def _horizontal(asks: tuple[str, ...], result: str) -> Binding:
    return Binding(
        asks=asks,
        result=(result,),
        inputs=_FROM_A_HEIGHT,
        cues=_LEVEL_LAUNCH,
        nonnegative=True,
    )


SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "range",
        "projectile",
        "Projectile-motion equation",
        "R",
        assumptions=("constant g, no air resistance, and the same launch and landing height",),
        variants=(FormulaVariant(positive=frozenset({"h0"}), assumptions=()),),
        variables=_LAUNCH,
        binding=_horizontal(("how far", "range", "horizontal distance", "distance"), "meter"),
    ),
    formula(
        "max_height",
        "projectile",
        "Projectile-motion equation",
        "H_{max}",
        variables=(
            var("angle", r"\theta", dimensionless=True),
            var("g", "g", "meter / second ** 2"),
            var("h0", "h_0", "meter"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "time_of_flight",
        "projectile",
        "Projectile-motion equation",
        "t_{flight}",
        variables=_LAUNCH,
        binding=_horizontal(("time of flight", "how long", "time"), "second"),
    ),
    formula(
        "impact_speed",
        "projectile",
        "Projectile-motion equation",
        "v_{impact}",
        variables=_LAUNCH,
        binding=_horizontal(("impact speed", "speed", "how fast", "velocity"), "meter / second"),
    ),
    # The speed it left the edge at, from the height and where it landed:
    # the fall sets the time, √(2h/g), and the range over that time is v₀.
    # A marble off a 90 cm bench that lands 1.2 m out left at 2.80 m/s.
    formula(
        "level_launch_speed",
        "projectile",
        "Projectile-motion equation",
        "v_0",
        base_latex=r"v_0 = d\sqrt{\frac{g}{2h}}",
        assumptions=("launched horizontally; no air resistance",),
        expression="d*sqrt(g/(2*h0))",
        variables=(
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var(
                "h0",
                "h",
                "meter",
                words=("high", "height", "tall", "cliff", "table", "bench", "roof", "off a"),
                needs_words=True,
            ),
            var(
                "d",
                "d",
                "meter",
                words=("lands", "away", "from the", "horizontal", "out"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=(
                "how fast was it rolling",
                "how fast was it moving",
                "how fast was it going",
                "how fast was it travelling",
                "how fast was it traveling",
                "how fast was the",
                "launch speed",
                "initial speed",
                "speed when it left",
                "speed as it left",
                "speed at which it left",
                "speed off the",
                "speed at the edge",
            ),
            result=("meter / second",),
            inputs=(frozenset({"d", "g", "h0"}),),
            cues=_LEVEL_LAUNCH,
            # The speed at the ground is another speed.
            excludes=("hit", "impact", "just before", "when it lands", "strikes"),
            nonnegative=True,
        ),
    ),
    formula(
        "launch_angle",
        "projectile",
        "Projectile-motion equation",
        "\\theta",
        variables=(
            var("d", "d", "meter"),
            var("g", "g", "meter / second ** 2"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
)
