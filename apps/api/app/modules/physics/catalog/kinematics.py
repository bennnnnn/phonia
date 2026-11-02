"""Verified kinematics operations."""

from __future__ import annotations

from app.modules.physics.catalog.suvat import TWO_BODIES
from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

# A drop from a height and a sound's trip to a wall and back are not one
# distance covered at one speed: d = vt read "rolls off a 1.2 m high table at
# 3 m/s" as 0.4 s, and an echo heard after 0.6 s as a wall 204 m away. Nor are
# two bodies' speeds one speed, nor a radius one turn's distance.
_NOT_CONSTANT_SPEED = (
    "high",
    "tall",
    "height",
    "fall",
    "falls",
    "falling",
    "dropped",
    "rolls off",
    "thrown",
    "echo",
    "echoes",
    "sonar",
    *TWO_BODIES,
)
# A radius covered once a turn is 2πr, not r: "a child sits 2.5 m from the
# centre of a merry-go-round that turns once every 6 s" moves at 2.62 m/s, not
# 0.417 m/s. A lap that ends where it began has no displacement at all, so its
# average velocity is not d/t.
ONE_TURN = (
    "revolution",
    "rotation",
    "rotates",
    "rotating",
    "once every",
    "one turn",
    "turn every",
    "turns once",
    "spins",
    "spinning",
    "merry-go-round",
    "carousel",
    "circle",
    "circular",
    "whirled",
    "orbit",
)
CLOSED_PATH = (
    "lap",
    "round trip",
    "back to",
    "returns to",
    "full circle",
    "complete circle",
    "starting point",
    "where it started",
    "where she started",
    "where he started",
)

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "position",
        "kinematics",
        "Constant-acceleration equation",
        "h",
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("h0", "h_0", "meter"),
            var("t", "t", "second"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "velocity",
        "kinematics",
        "Constant-acceleration equation",
        "v",
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("h0", "h_0", "meter"),
            var("t", "t", "second"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "time_to_ground",
        "kinematics",
        "Constant-acceleration equation",
        "t",
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("h0", "h_0", "meter"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "speed",
        "kinematics",
        "Constant-acceleration equation",
        "v",
        variants=(FormulaVariant(absent=frozenset({"t"}), result_symbol="v_{impact}"),),
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("h0", "h_0", "meter"),
            var("t", "t", "second"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "acceleration",
        "kinematics",
        "Constant-acceleration equation",
        "a",
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("h0", "h_0", "meter"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "time_to_peak",
        "kinematics",
        "Constant-acceleration equation",
        "t_{\\text{top}}",
        base_latex=r"t_{\text{top}} = \frac{v_0}{g}",
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("h0", "h_0", "meter"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "vertical_max_height",
        "kinematics",
        "Constant-acceleration equation",
        "h_{\\max}",
        base_latex=r"h_{\max} = h_0 + \frac{v_0^2}{2g}",
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("h0", "h_0", "meter"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "average_speed",
        "kinematics",
        "Average speed formula",
        "v",
        base_latex="v = \\frac{d}{t}",
        variables=(
            var("d", "d", "meter"),
            var("t", "t", "second"),
        ),
    ),
    formula(
        "rate_speed",
        "kinematics",
        "Speed formula",
        "v",
        base_latex="v = \\frac{d}{t}",
        variables=(
            var("d", "d", "meter"),
            var("t", "t", "second"),
        ),
        binding=Binding(
            asks=("average speed", "average velocity", "speed", "how fast"),
            excludes=(*_NOT_CONSTANT_SPEED, *ONE_TURN, *CLOSED_PATH),
            result=("meter / second",),
            inputs=(frozenset({"d", "t"}),),
            nonnegative=True,
        ),
    ),
    # Two legs at two speeds: the average is the whole distance over the whole
    # time, never the mean of the speeds. 100 km at 50 km/h then 100 km at
    # 100 km/h is 66.7 km/h over the trip, not 75. The legs pair in the order
    # they are written: the first distance goes with the first speed.
    formula(
        "average_speed_two_legs",
        "kinematics",
        "Average speed",
        r"\bar{v}",
        base_latex=r"\bar{v} = \frac{d_1 + d_2}{t_1 + t_2}",
        variables=(
            var("d1", "d_1", "meter"),
            var("d2", "d_2", "meter"),
            var("v1", "v_1", "meter / second"),
            var("v2", "v_2", "meter / second"),
            # "for the 200 km trip": the total, stated beside the legs.
            var(
                "d_total",
                "d",
                "meter",
                words=("trip", "journey", "total", "whole", "entire", "altogether", "in all"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("average speed",),
            result=("meter / second",),
            inputs=(
                frozenset({"d1", "d2", "v1", "v2"}),
                frozenset({"d1", "d2", "v1", "v2", "d_total"}),
            ),
            interchangeable=("d1", "d2", "v1", "v2", "d_total"),
            nonnegative=True,
        ),
    ),
    # The same distance at each speed (a round trip, or two halves of the way):
    # the harmonic mean. 60 km/h there and 40 km/h back is 48 km/h, not 50.
    formula(
        "average_speed_equal_distances",
        "kinematics",
        "Average speed",
        r"\bar{v}",
        base_latex=r"\bar{v} = \frac{2 v_1 v_2}{v_1 + v_2}",
        variables=(
            var("v1", "v_1", "meter / second"),
            var("v2", "v_2", "meter / second"),
        ),
        binding=Binding(
            asks=("average speed",),
            result=("meter / second",),
            inputs=(frozenset({"v1", "v2"}),),
            cues=(
                "half the distance",
                "half of the distance",
                "half the way",
                "halfway",
                "returns",
                "return trip",
                "way back",
                "comes back",
                "drives back",
                "round trip",
            ),
            excludes=("half the time", "half of the time", "for equal times"),
            interchangeable=("v1", "v2"),
            nonnegative=True,
        ),
    ),
    # The same time at each speed: the plain mean. 40 km/h for half the time
    # and 60 km/h for the other half is 50 km/h.
    formula(
        "average_speed_equal_times",
        "kinematics",
        "Average speed",
        r"\bar{v}",
        base_latex=r"\bar{v} = \frac{v_1 + v_2}{2}",
        variables=(
            var("v1", "v_1", "meter / second"),
            var("v2", "v_2", "meter / second"),
        ),
        binding=Binding(
            asks=("average speed",),
            result=("meter / second",),
            inputs=(frozenset({"v1", "v2"}),),
            cues=("half the time", "half of the time", "for equal times"),
            interchangeable=("v1", "v2"),
            nonnegative=True,
        ),
    ),
    formula(
        "rate_distance",
        "kinematics",
        "Speed formula",
        "d",
        base_latex="v = \\frac{d}{t}",
        variables=(
            var("t", "t", "second"),
            var("v", "v", "meter / second"),
        ),
        binding=Binding(
            asks=("how far", "distance", "how many metres", "how many meters", "how much distance"),
            excludes=_NOT_CONSTANT_SPEED,
            result=("meter",),
            inputs=(frozenset({"t", "v"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "rate_time",
        "kinematics",
        "Speed formula",
        "t",
        base_latex="v = \\frac{d}{t}",
        variables=(
            var("d", "d", "meter"),
            var("v", "v", "meter / second"),
        ),
        binding=Binding(
            asks=("how long", "time taken", "time"),
            excludes=_NOT_CONSTANT_SPEED,
            result=("second",),
            inputs=(frozenset({"d", "v"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "stopping_distance",
        "kinematics",
        "Stopping distance",
        "d",
        variants=(
            # Braking at a stated rate: "reaction time 0.8 s, then brakes at 6 m/s²".
            FormulaVariant(
                present=frozenset({"decel"}),
                lines=(
                    r"d_r = v t_r",
                    r"d_b = \frac{v^2}{2a}",
                    r"d = d_r + d_b",
                ),
                assumptions=(
                    "Constant speed while reacting",
                    "Constant deceleration while braking",
                    "Final speed is zero",
                ),
            ),
            FormulaVariant(
                lines=(
                    r"d_r = v t_r",
                    r"d_b = \frac{v t_b}{2}",
                    r"d = d_r + d_b",
                    r"a = -\frac{v}{t_b}",
                ),
                assumptions=(
                    "Constant speed while reacting",
                    "Constant deceleration while braking",
                    "Final speed is zero",
                ),
            ),
        ),
        variables=(
            var("t_brake", "t_b", "second"),
            var("decel", "a", "meter / second ** 2"),
            var("t_react", "t_r", "second"),
            var("v", "v", "meter / second"),
        ),
    ),
    # Two stages from rest: speed up, then hold the speed or brake to a stop
    # (``extractors/two_stage.py``). Stage one is any two of a₁, t₁ and the
    # speed it reaches; stage two is a time at that speed, a braking rate or a
    # braking time, or the rest of a stated distance at that speed.
    *(
        formula(
            operation,
            "kinematics",
            "Two-stage motion",
            symbol,
            assumptions=(
                "starts from rest",
                "constant acceleration in each stage",
                "the second stage starts at the first stage's final speed",
            ),
            variables=(
                var("a1", "a_1", "meter / second ** 2"),
                var("t1", "t_1", "second"),
                var("v_top", "v", "meter / second"),
                var("t_cruise", "t_2", "second"),
                var("a_brake", "a_2", "meter / second ** 2"),
                var("t_brake", "t_2", "second"),
                var("d_total", "d", "meter"),
            ),
        )
        for operation, symbol in (("two_stage_distance", "d"), ("two_stage_time", "t"))
    ),
    # A faster chaser closes a gap at the difference of the speeds
    # (``extractors/relative_motion.py``): 30 m/s after 20 m/s, 100 m ahead,
    # catches up in 10 s.
    formula(
        "catch_up_time",
        "kinematics",
        "Relative velocity",
        "t",
        base_latex=r"t = \frac{d}{v_1 - v_2}",
        assumptions=("both move at constant speed along one line, the same way",),
        variables=(
            var("d", "d", "meter"),
            var("v_chaser", "v_1", "meter / second"),
            var("v_target", "v_2", "meter / second"),
        ),
    ),
    # Two legs on the two compass axes: the displacement's size and direction.
    formula(
        "displacement_two_legs",
        "kinematics",
        "Displacement",
        "d",
        base_latex=r"d = \sqrt{d_1^2 + d_2^2}",
        assumptions=("the two legs are at right angles",),
        variables=(
            var("d1", "d_1", "meter"),
            var("d2", "d_2", "meter"),
            var("heading1", "", dimensionless=True, visible=False),
            var("heading2", "", dimensionless=True, visible=False),
        ),
    ),
    # How far a dropped body falls in a time: h = ½gt² from rest.
    formula(
        "drop_height",
        "kinematics",
        "Free-fall equation",
        "h",
        base_latex=r"h = \tfrac{1}{2}gt^2",
        assumptions=("released from rest", "no air resistance"),
        expression="g*t**2/2",
        variables=(
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("t", "t", "second"),
        ),
        binding=Binding(
            asks=("how high", "how deep", "how far", "height", "depth", "distance"),
            result=("meter",),
            inputs=(frozenset({"g", "t"}),),
            cues=("dropped", "drops", "falls", "free fall", "released", "freely"),
            nonnegative=True,
        ),
    ),
    # t = d/c: light covers any stated distance at c.
    formula(
        "light_travel_time",
        "kinematics",
        "Speed of light",
        "t",
        base_latex=r"t = \frac{d}{c}",
        assumptions=("light in a vacuum (or air)",),
        expression="d/c_light",
        variables=(var("d", "d", "meter"),),
        binding=Binding(
            asks=("how long", "time", "how much time"),
            result=("second",),
            inputs=(frozenset({"d"}),),
            cues=("light", "laser", "radio signal", "radio wave"),
            excludes=("light year", "light-year", "lightning", "sound", "car", "train", "runner"),
            nonnegative=True,
        ),
    ),
    # Two bodies heading toward each other close the gap at the sum of their speeds.
    formula(
        "meeting_time",
        "kinematics",
        "Relative velocity",
        "t",
        base_latex=r"t = \frac{d}{v_1 + v_2}",
        assumptions=("both move at constant speed along one line, toward each other",),
        expression="d/(v1 + v2)",
        variables=(
            var("d", "d", "meter"),
            var("v1", "v_1", "meter / second"),
            var("v2", "v_2", "meter / second"),
        ),
        binding=Binding(
            asks=(
                "how long",
                "time",
                "how much time",
                "when do they meet",
                "when will they meet",
                "when do the two meet",
            ),
            result=("second",),
            inputs=(frozenset({"d", "v1", "v2"}),),
            cues=(
                "toward each other",
                "towards each other",
                "approach each other",
                "approaching each other",
                "head toward each other",
                "heading toward each other",
            ),
            excludes=("same direction", "chasing", "catch up", "overtake", "accelerat"),
            interchangeable=("v1", "v2"),
            nonnegative=True,
        ),
    ),
    # Two velocities at right angles add as the sides of a right triangle: a
    # boat heading straight across at 4 m/s in a 3 m/s current moves at 5 m/s
    # over the bank, and a plane flying north into a crosswind from the west
    # moves faster over the ground than its airspeed. A boat that aims
    # upstream so as to land opposite, or a plane that heads into the wind to
    # hold a course, is the other triangle, and is not this law.
    formula(
        "perpendicular_velocity_sum",
        "kinematics",
        "Relative velocity",
        "v",
        base_latex=r"v = \sqrt{v_1^2 + v_2^2}",
        assumptions=("the two velocities are at right angles",),
        expression="sqrt(v1**2 + v2**2)",
        variables=(
            var("v1", "v_1", "meter / second"),
            var("v2", "v_2", "meter / second"),
        ),
        binding=Binding(
            asks=(
                "resultant speed",
                "ground speed",
                "speed relative to the bank",
                "speed relative to the shore",
                "speed relative to the ground",
                "speed relative to the land",
                "speed relative to the earth",
                "speed over the ground",
                "actual speed",
                "true speed",
                "overall speed",
                "net speed",
                "magnitude of the resultant velocity",
                "magnitude of its resultant velocity",
                "magnitude of the boat's resultant velocity",
            ),
            result=("meter / second",),
            inputs=(frozenset({"v1", "v2"}),),
            # The current runs along the river, so a heading across it is a
            # right angle. "Straight across the bay" with a wind says no angle.
            cues=(
                "across the river",
                "across a river",
                "across the stream",
                "across a stream",
                "across the canal",
                "perpendicular",
                "right angles",
                "right angle",
                "crosswind",
                "cross wind",
                "crosswise",
            ),
            excludes=(
                "upstream",
                "downstream",
                "wants to",
                "needs to",
                "has to",
                "must",
                "so that",
                "in order to",
                "directly opposite",
                "straight opposite",
                "aims",
                "aim",
                "heading should",
                "which direction",
                "what direction",
                "what angle",
                "same direction",
                "opposite direction",
                "headwind",
                "tailwind",
                "head wind",
                "tail wind",
                "against the current",
                "with the current",
                "accelerat",
            ),
            interchangeable=("v1", "v2"),
            nonnegative=True,
        ),
    ),
)
