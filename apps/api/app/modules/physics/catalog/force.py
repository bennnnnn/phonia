"""Verified force operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

_FORWARD = ("to the right", "right", "east", "eastward", "forward", "forwards", "ahead")
_BACKWARD = ("to the left", "left", "west", "westward", "backward", "backwards", "behind")
# Where the other mass of a pulley pair rests instead of hanging.
_RESTING_SIDE = (
    "table",
    "horizontal surface",
    "level surface",
    "smooth surface",
    "frictionless surface",
    "bench",
    "desk",
    "incline",
    "inclined",
    "ramp",
    "slope",
)
_ON_THE_TABLE = ("block", "box", "cart", "trolley", "on a", "on the", "table", "surface")
_HANGING = ("hanging", "hangs", "hung", "suspended", "dangling", "over the edge")

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "lift_normal_force",
        "force",
        "Newton's second law in a lift",
        "N",
        base_latex="N = m(g + a)",
        expression="m*(g + accel)",
        variants=(
            FormulaVariant(
                latex="N = m(g - a)",
                present=frozenset({"downward"}),
                expression="m*(g - accel)",
            ),
        ),
        variables=(
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("m", "m", "kilogram"),
            var("accel", "a", "meter / second ** 2", words=("accelerat",)),
            var(
                "downward",
                "",
                dimensionless=True,
                visible=False,
                implied=(
                    ("accelerating downward", 1.0),
                    ("accelerating downwards", 1.0),
                    ("accelerates downward", 1.0),
                    ("accelerates downwards", 1.0),
                ),
            ),
        ),
        binding=Binding(
            asks=(
                "normal force",
                "apparent weight",
                "scale reading",
                "reading on the scale",
                "scales read",
                "scale read",
                "scales show",
                "scale show",
            ),
            result=("newton",),
            inputs=(frozenset({"g", "m", "accel"}), frozenset({"g", "m", "accel", "downward"})),
            cues=("elevator", "lift"),
            nonnegative=True,
        ),
    ),
    formula(
        "net_force",
        "force",
        "Newton's second law",
        "F",
        base_latex="F = ma",
        solve_for=(("F", "F"), ("m", "m"), ("a", "a")),
        variables=(
            var("F", "F", "newton"),
            var("a", "a", "meter / second ** 2"),
            var("m", "m", "kilogram"),
        ),
    ),
    formula(
        "tension",
        "force",
        "Newton's second law",
        "T",
        variables=(
            var("a", "a", "meter / second ** 2"),
            var("g", "g", "meter / second ** 2", visible=False),
            var("m", "m", "kilogram"),
        ),
    ),
    formula(
        "atwood",
        "force",
        "Newton's second law",
        "a,\\ T",
        variables=(
            var("g", "g", "meter / second ** 2", visible=False),
            var("m1", "m_1", "kilogram"),
            var("m2", "m_2", "kilogram"),
        ),
        # Two masses over a pulley; the heavier is m₁, so the acceleration is its fall.
        binding=Binding(
            asks=("acceleration", "tension"),
            result=("meter / second ** 2", "newton"),
            inputs=(frozenset({"m1", "m2"}),),
            cues=("pulley", "atwood"),
            # One mass on a table or a slope is not hanging: not an Atwood machine.
            excludes=_RESTING_SIDE,
            descending=("m1", "m2"),
        ),
    ),
    # A block on a level, frictionless table pulled by a hanging mass. Only the
    # hanging weight drives both: a = m₂g/(m₁+m₂), T = m₁a. As an Atwood machine
    # a 5 kg block and a 2 kg hanging mass gave 4.2 m/s² instead of 2.80.
    formula(
        "table_pulley",
        "force",
        "Newton's second law",
        "a,\\ T",
        assumptions=("a frictionless level table and a light string over a light pulley",),
        variables=(
            var("g", "g", "meter / second ** 2", visible=False),
            var("m1", "m_1", "kilogram", words=_ON_THE_TABLE, needs_words=True),
            var("m2", "m_2", "kilogram", words=_HANGING, needs_words=True),
        ),
        binding=Binding(
            asks=("acceleration", "tension"),
            result=("meter / second ** 2", "newton"),
            inputs=(frozenset({"m1", "m2"}),),
            cues=("table", "surface", "bench", "desk"),
            excludes=("rough", "incline", "inclined", "ramp", "slope"),
        ),
    ),
    formula(
        "resultant_force",
        "force",
        "Vector addition and components",
        "R",
        variables=(
            var("F1", "F_1", "newton"),
            var("F2", "F_2", "newton"),
            var("angle", r"\theta", dimensionless=True),
        ),
    ),
    formula(
        "resolve_force",
        "force",
        "Vector addition and components",
        "F_x,\\ F_y",
        variables=(
            var("F", "F", "newton"),
            var("angle", r"\theta", dimensionless=True),
        ),
    ),
    formula(
        "weight",
        "force",
        "Weight equation",
        "W",
        base_latex="W = mg",
        expression="m*g",
        variables=(
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("m", "m", "kilogram"),
        ),
        binding=Binding(
            asks=("weight",),
            result=("newton",),
            inputs=(frozenset({"g", "m"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "mass_from_weight",
        "force",
        "Weight equation",
        "m",
        base_latex="W = mg",
        expression="weight/g",
        variables=(
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("weight", "W", "newton"),
        ),
        binding=Binding(
            asks=("mass",),
            result=("kilogram",),
            inputs=(frozenset({"g", "weight"}),),
            cues=("weigh",),
            nonnegative=True,
        ),
    ),
    # m = F/a and the force of a stated change of speed: two forms students
    # ask for as often as F = ma itself.
    formula(
        "mass_from_force",
        "force",
        "Newton's second law",
        "m",
        base_latex=r"m = \frac{F}{a}",
        expression="F/accel",
        variables=(var("F", "F", "newton"), var("accel", "a", "meter / second ** 2")),
        binding=Binding(
            asks=("mass",),
            result=("kilogram",),
            inputs=(frozenset({"F", "accel"}),),
            # A weight and a field strength are W = mg, the law the weight names.
            excludes=("weigh",),
            nonnegative=True,
        ),
    ),
    formula(
        "average_force_from_speeds",
        "force",
        "Newton's second law",
        "F",
        base_latex=r"F = \frac{m(v - u)}{t}",
        assumptions=("a constant force over the time stated",),
        expression="m*(v - u)/t",
        variables=(
            var("m", "m", "kilogram"),
            var(
                "u",
                "u",
                "meter / second",
                words=("from", "initial", "initially", "moving at", "travelling at"),
                implied=(("from rest", 0.0),),
            ),
            var(
                "v",
                "v",
                "meter / second",
                words=("to", "final", "reaches"),
                implied=(("to rest", 0.0), ("to a stop", 0.0), ("to a halt", 0.0)),
            ),
            var("t", "t", "second"),
        ),
        binding=Binding(
            asks=("average force", "braking force", "average braking force", "force"),
            result=("newton",),
            inputs=(frozenset({"m", "u", "v", "t"}),),
            negative_detail="opposing the motion",
        ),
    ),
    # A car towing another on a rope: the rope pulls only the towed one, so
    # T = m_towed a. The tow vehicle's mass is what the engine moves too, not
    # what the rope does.
    formula(
        "tow_tension",
        "force",
        "Newton's second law",
        "T",
        base_latex=r"T = m_2 a",
        assumptions=("no friction on the towed body, and a light rope",),
        expression="m_towed*a",
        variables=(
            var(
                "m_tower",
                "m_1",
                "kilogram",
                words=("truck", "tractor", "locomotive", "engine", "tow truck", "lorry"),
                needs_words=True,
            ),
            var(
                "m_towed",
                "m_2",
                "kilogram",
                words=("tows a", "tows an", "towing a", "towing an", "pulls a", "trailer", "towed"),
                needs_words=True,
            ),
            var("a", "a", "meter / second ** 2"),
        ),
        binding=Binding(
            asks=("tension",),
            result=("newton",),
            inputs=(frozenset({"a", "m_towed", "m_tower"}),),
            cues=("tows", "towing", "towed", "tow rope", "tow bar", "trailer"),
            excludes=("incline", "slope", "hill", "pulley", "hanging", "coefficient", "rough"),
            nonnegative=True,
        ),
    ),
    # An average force for a stated time changes a body's speed by Ft/m: a
    # racket's 240 N for 5 ms on a 58 g ball is 20.7 m/s.
    formula(
        "speed_change_from_force",
        "force",
        "Impulse-momentum theorem",
        r"\Delta v",
        base_latex=r"F t = m \Delta v",
        assumptions=("the force is the net force on the body, along its motion",),
        expression="F*t/m",
        variables=(var("F", "F", "newton"), var("t", "t", "second"), var("m", "m", "kilogram")),
        binding=Binding(
            asks=(
                "change in speed",
                "change in the speed",
                "change in its speed",
                "change in velocity",
                "change in the velocity",
                "change in its velocity",
                "change in the ball's speed",
                "change in the ball's velocity",
                "change in the object's speed",
                "change in the object's velocity",
            ),
            result=("meter / second",),
            inputs=(frozenset({"F", "t", "m"}),),
            excludes=("friction", "incline", "slope", "ramp"),
            nonnegative=True,
        ),
    ),
    # A net force acting from rest for a stated time: v = Ft/m.
    formula(
        "speed_from_net_force",
        "force",
        "Newton's second law",
        "v",
        base_latex=r"v = \frac{F t}{m}",
        assumptions=("the body starts from rest and the force is constant",),
        expression="F*t/m",
        variables=(var("F", "F", "newton"), var("t", "t", "second"), var("m", "m", "kilogram")),
        binding=Binding(
            asks=("how fast", "speed", "velocity"),
            result=("meter / second",),
            inputs=(frozenset({"F", "t", "m"}),),
            cues=("from rest", "starting from rest", "starts from rest"),
            nonnegative=True,
        ),
    ),
    # At terminal velocity the drag balances the weight.
    formula(
        "terminal_drag",
        "force",
        "Balanced forces",
        "F_d",
        base_latex=r"F_d = m g",
        assumptions=("at terminal velocity the drag equals the weight",),
        expression="m*g",
        variables=(
            var("m", "m", "kilogram"),
            var("g", "g", "meter / second ** 2", fallback="gravity"),
        ),
        binding=Binding(
            asks=("air resistance", "drag force", "drag", "air resistance force"),
            result=("newton",),
            inputs=(frozenset({"m", "g"}),),
            cues=("terminal", "constant velocity", "constant speed"),
            nonnegative=True,
        ),
    ),
    # The part of the weight that pulls along a slope.
    formula(
        "weight_along_slope",
        "force",
        "Resolving the weight",
        r"F_{\parallel}",
        base_latex=r"F_{\parallel} = m g \sin\theta",
        expression="m*g*sin(angle)",
        variables=(
            var("m", "m", "kilogram"),
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("angle", r"\theta", dimensionless=True),
        ),
        binding=Binding(
            asks=(
                "component",
                "parallel component",
                "force along the slope",
                "force down the slope",
            ),
            result=("newton",),
            inputs=(frozenset({"m", "g", "angle"}),),
            cues=("slope", "incline", "ramp"),
            excludes=("perpendicular", "normal"),
            nonnegative=True,
        ),
    ),
    # Two forces pulling opposite ways: the net force is their difference.
    formula(
        "acceleration_from_opposing_forces",
        "force",
        "Newton's second law",
        "a",
        base_latex=r"a = \frac{F_1 - F_2}{m}",
        assumptions=("the two forces act along one line, in opposite directions",),
        expression="(F_forward - F_back)/m",
        variables=(
            var("m", "m", "kilogram"),
            var("F_forward", "F_1", "newton", words=_FORWARD, needs_words=True),
            var("F_back", "F_2", "newton", words=_BACKWARD, needs_words=True),
        ),
        binding=Binding(
            asks=("acceleration", "accelerate"),
            result=("meter / second ** 2",),
            inputs=(frozenset({"m", "F_forward", "F_back"}),),
            negative_detail="toward the larger force",
        ),
    ),
    formula(
        "net_force_opposing",
        "force",
        "Resultant of two opposite forces",
        "F_{net}",
        base_latex=r"F_{net} = F_1 - F_2",
        assumptions=("the two forces act along one line, in opposite directions",),
        expression="F_forward - F_back",
        variables=(
            var("F_forward", "F_1", "newton", words=_FORWARD, needs_words=True),
            var("F_back", "F_2", "newton", words=_BACKWARD, needs_words=True),
        ),
        binding=Binding(
            asks=("net force", "resultant force", "resultant", "overall force", "unbalanced force"),
            result=("newton",),
            inputs=(frozenset({"F_forward", "F_back"}),),
            negative_detail="toward the larger force",
        ),
    ),
)
