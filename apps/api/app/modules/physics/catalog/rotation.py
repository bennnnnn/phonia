"""Verified rotation operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

# I/(mr²) of each body a question can name rolling. Longer names first: a hollow
# sphere is not a solid one. A ball or a wheel could be either, so it names none.
_SHAPES = (
    ("hollow sphere", 2 / 3),
    ("spherical shell", 2 / 3),
    ("thin-walled sphere", 2 / 3),
    ("hollow cylinder", 1.0),
    ("thin-walled cylinder", 1.0),
    ("cylindrical shell", 1.0),
    ("hoop", 1.0),
    ("ring", 1.0),
    ("solid sphere", 0.4),
    ("solid ball", 0.4),
    ("sphere", 0.4),
    ("solid cylinder", 0.5),
    ("solid disc", 0.5),
    ("solid disk", 0.5),
    ("cylinder", 0.5),
    ("disc", 0.5),
    ("disk", 0.5),
)
_ROLLING_LINE = r"K = \tfrac{1}{2}mv^2 + \tfrac{1}{2}I\omega^2,\quad \omega = \frac{v}{r}"


def _rolling(shape_k: float, inertia: str, total: str, expression: str) -> FormulaVariant:
    return FormulaVariant(
        lines=(_ROLLING_LINE, inertia, total),
        equals=(("shape_k", shape_k),),
        expression=expression,
    )


SPECS: tuple[FormulaSpec, ...] = (
    # A body rolling without slipping carries rotational energy as well:
    # ½mv² left out 2/7 of a rolling sphere's energy (9 J for 12.6 J).
    formula(
        "rolling_body_kinetic_energy",
        "rotation",
        "Rolling kinetic-energy formula",
        "K",
        base_latex=r"K = \tfrac{1}{2}mv^2 + \tfrac{1}{2}I\omega^2",
        assumptions=("rolling without slipping, so the radius cancels",),
        expression="m*v**2*(1 + shape_k)/2",
        variants=(
            _rolling(0.4, r"I = \tfrac{2}{5}mr^2", r"K = \tfrac{7}{10}mv^2", "7*m*v**2/10"),
            _rolling(0.5, r"I = \tfrac{1}{2}mr^2", r"K = \tfrac{3}{4}mv^2", "3*m*v**2/4"),
            _rolling(1.0, r"I = mr^2", r"K = mv^2", "m*v**2"),
            _rolling(2 / 3, r"I = \tfrac{2}{3}mr^2", r"K = \tfrac{5}{6}mv^2", "5*m*v**2/6"),
        ),
        variables=(
            var("m", "m", "kilogram"),
            var("v", "v", "meter / second"),
            var("r", "r", "meter", words=("radius",), needs_words=True),
            var("shape_k", "k", dimensionless=True, visible=False, implied=_SHAPES),
        ),
        binding=Binding(
            asks=("total kinetic energy", "kinetic energy", "total energy"),
            result=("joule",),
            inputs=(frozenset({"m", "v", "shape_k"}), frozenset({"m", "v", "r", "shape_k"})),
            cues=("roll", "rolling"),
            excludes=("moment of inertia", "rad/s", "slides", "sliding", "slipping and"),
            nonnegative=True,
        ),
    ),
    formula(
        "angular_displacement_rate",
        "rotation",
        "Angular-velocity definition",
        r"\omega",
        base_latex=r"\omega = \frac{\theta}{t}",
        variables=(
            var("t", "t", "second"),
            var("theta", r"\theta", "radian"),
        ),
    ),
    formula(
        "moment_of_inertia",
        "rotation",
        "Moment-of-inertia formula",
        "I",
        variables=(
            var("m", "m", "kilogram"),
            var("r", "r", "meter"),
            var("shape_factor", "shape_factor", dimensionless=True, visible=False),
        ),
    ),
    formula(
        "angular_momentum",
        "rotation",
        "Angular-momentum formula",
        "L",
        variables=(
            var("inertia", "I", "kilogram * meter ** 2"),
            var("omega", r"\omega", "radian / second"),
        ),
        # "Moment of inertia" without a shape is not this law's missing input.
        # The shape branch declines that sentence, so L = Iω needs the same
        # binding the kinetic-energy form already has.
        binding=Binding(
            asks=("angular momentum",),
            result=("kilogram * meter ** 2 / second",),
            inputs=(frozenset({"inertia", "omega"}),),
            excludes=("conserved", "isolated", "squared", "z component"),
            nonnegative=True,
        ),
    ),
    formula(
        "rotational_kinetic_energy",
        "rotation",
        "Rotational kinetic-energy formula",
        "E_k",
        variables=(
            var("inertia", "I", "kilogram * meter ** 2"),
            var("omega", r"\omega", "radian / second"),
        ),
        binding=Binding(
            asks=(
                "rotational kinetic energy",
                "rotational energy",
                "kinetic energy",
                "rotational ke",
                "rotational k.e.",
            ),
            result=("joule",),
            inputs=(frozenset({"inertia", "omega"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "rotational_omega",
        "rotation",
        "Rotational kinematic equation",
        r"\omega",
        base_latex=r"\omega = \omega_0 + \alpha t",
        assumptions=("constant angular acceleration",),
        variants=(
            FormulaVariant(
                latex=r"\omega^2 = \omega_0^2 + 2\alpha\Delta\theta \Rightarrow \omega",
                present=frozenset({"theta"}),
                absent=frozenset({"t"}),
                assumptions=("constant angular acceleration",),
            ),
        ),
        variables=(
            var("ang_alpha", r"\alpha", "radian / second ** 2"),
            var(
                "omega0",
                r"\omega_0",
                "radian / second",
                implied=(("from rest", 0.0), ("starts at rest", 0.0)),
            ),
            var("t", "t", "second"),
            var("theta", r"\theta", "radian"),
        ),
        binding=Binding(
            asks=("final angular velocity", "angular velocity", "angular speed"),
            result=("radian / second",),
            inputs=(frozenset({"ang_alpha", "omega0", "t"}),),
        ),
    ),
    formula(
        "rotational_theta",
        "rotation",
        "Rotational kinematic equation",
        r"\theta",
        base_latex=r"\theta = \theta_0 + \omega_0 t + \frac{1}{2}\alpha t^2",
        assumptions=(
            "constant angular acceleration",
            "angular displacement is measured from zero",
        ),
        variants=(
            # Displacement is the unknown, so the ω² branch is the one that
            # supplies ω and omits t. θ itself is not an input of this op.
            FormulaVariant(
                latex=r"\omega^2 = \omega_0^2 + 2\alpha\Delta\theta \Rightarrow \theta",
                present=frozenset({"omega"}),
                absent=frozenset({"t"}),
                assumptions=(
                    "constant angular acceleration",
                    "angular displacement is measured from zero",
                ),
            ),
            FormulaVariant(
                latex=r"\theta = \frac{\omega_0 + \omega}{2} t",
                present=frozenset({"omega", "omega0", "t"}),
                absent=frozenset({"ang_alpha"}),
                assumptions=(
                    "constant angular acceleration",
                    "angular displacement is measured from zero",
                ),
            ),
        ),
        variables=(
            var("ang_alpha", r"\alpha", "radian / second ** 2"),
            var("omega", r"\omega", "radian / second"),
            var("omega0", r"\omega_0", "radian / second"),
            var("t", "t", "second"),
        ),
    ),
    formula(
        "rotational_alpha",
        "rotation",
        "Rotational kinematic equation",
        r"\alpha",
        base_latex=r"\omega = \omega_0 + \alpha t",
        assumptions=("constant angular acceleration",),
        variants=(
            FormulaVariant(
                latex=r"\alpha = \frac{\omega^2 - \omega_0^2}{2\Delta\theta}",
                present=frozenset({"theta"}),
                absent=frozenset({"t"}),
                assumptions=("constant angular acceleration",),
            ),
        ),
        variables=(
            var("omega", r"\omega", "radian / second"),
            var("omega0", r"\omega_0", "radian / second"),
            var("t", "t", "second"),
            var("theta", r"\theta", "radian"),
        ),
    ),
    formula(
        "torque_inertia",
        "rotation",
        "Rotational Newton's second law",
        r"\alpha",
        base_latex=r"\tau = I\alpha",
        solve_for=(("tau", r"\tau"), ("inertia", "I"), ("ang_alpha", r"\alpha")),
        variables=(
            var("ang_alpha", r"\alpha", "radian / second ** 2"),
            var("inertia", "I", "kilogram * meter ** 2"),
            var("tau", r"\tau", "newton * meter"),
        ),
        binding=Binding(
            asks=("angular acceleration",),
            result=("radian / second ** 2",),
            inputs=(frozenset({"inertia", "tau"}),),
        ),
    ),
    formula(
        "torque_angular_impulse",
        "rotation",
        "Angular impulse-momentum theorem",
        r"\tau",
        base_latex=r"\tau = \frac{\Delta L}{\Delta t}",
        assumptions=("torque is the average torque over the interval",),
        solve_for=(
            ("tau", r"\tau"),
            ("L_i", "L_i"),
            ("L_f", "L_f"),
            ("t", r"\Delta t"),
        ),
        variables=(
            var("L_f", "L_f", "kilogram * meter ** 2 / second"),
            var("L_i", "L_i", "kilogram * meter ** 2 / second"),
            var("t", "t", "second"),
            var("tau", r"\tau", "newton * meter"),
        ),
    ),
    formula(
        "angular_momentum_conservation",
        "rotation",
        "Conservation of angular momentum",
        r"\omega_f",
        base_latex=r"I_i\omega_i = I_f\omega_f",
        assumptions=("the system is isolated",),
        solve_for=(
            ("inertia_i", "I_i"),
            ("omega_i", r"\omega_i"),
            ("inertia_f", "I_f"),
            ("omega_f", r"\omega_f"),
        ),
        variables=(
            var(
                "inertia_f",
                "I_f",
                "kilogram * meter ** 2",
                words=("so", "pulls", "arms in", "tucks", "becomes", "to", "final", "after"),
                needs_words=True,
            ),
            var(
                "inertia_i",
                "I_i",
                "kilogram * meter ** 2",
                words=("arms out", "initially", "initial", "at first", "first", "before", "with"),
                needs_words=True,
            ),
            var(
                "omega_f",
                r"\omega_f",
                "radian / second",
                words=("new", "final"),
                needs_words=True,
            ),
            var(
                "omega_i",
                r"\omega_i",
                "radian / second",
                words=("spins at", "spinning at", "initially", "at first", "rotates at"),
            ),
        ),
        # A skater pulls her arms in: no outside torque, so Iω stays the same.
        # From 2 rev/s at 4 kg·m² to 1.6 kg·m² is 5 rev/s (31.4 rad/s).
        binding=Binding(
            asks=(
                "new spin rate",
                "new angular velocity",
                "new angular speed",
                "new rate",
                "spin rate",
                "angular velocity",
                "angular speed",
            ),
            result=("radian / second",),
            inputs=(frozenset({"inertia_f", "inertia_i", "omega_i"}),),
            cues=(
                "pulls her arms",
                "pulls his arms",
                "pulls in",
                "arms in",
                "tucks",
                "angular momentum",
                "is conserved",
            ),
            excludes=("torque", "friction"),
            nonnegative=True,
        ),
    ),
    formula(
        "rolling_speed",
        "rotation",
        "Rolling-without-slipping condition",
        "v",
        base_latex=r"v = R\omega",
        assumptions=("rolling without slipping",),
        solve_for=(("v", "v"), ("omega", r"\omega"), ("r", "R")),
        variables=(
            var("omega", r"\omega", "radian / second"),
            var("r", "R", "meter"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "rolling_acceleration",
        "rotation",
        "Rolling-without-slipping condition",
        "a",
        base_latex=r"a = R\alpha",
        assumptions=("rolling without slipping",),
        solve_for=(("a", "a"), ("ang_alpha", r"\alpha"), ("r", "R")),
        variables=(
            var("a", "a", "meter / second ** 2"),
            var("ang_alpha", r"\alpha", "radian / second ** 2"),
            var("r", "R", "meter"),
        ),
    ),
    formula(
        "rolling_kinetic_energy",
        "rotation",
        "Rolling kinetic-energy formula",
        "K",
        base_latex=r"K = \frac{1}{2}Mv^2 + \frac{1}{2}I\omega^2",
        assumptions=("rolling without slipping",),
        variables=(
            var("inertia", "I", "kilogram * meter ** 2"),
            var("m", "M", "kilogram"),
            var("omega", r"\omega", "radian / second"),
            var("r", "R", "meter"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "parallel_axis",
        "rotation",
        "Parallel-axis theorem",
        "I",
        base_latex=r"I = I_{cm} + Md^2",
        assumptions=("the axis is parallel to an axis through the center of mass",),
        solve_for=(("inertia", "I"), ("inertia_cm", "I_{cm}"), ("m", "M"), ("d", "d")),
        variables=(
            var("d", "d", "meter"),
            var("inertia", "I", "kilogram * meter ** 2"),
            var("inertia_cm", "I_{cm}", "kilogram * meter ** 2"),
            var("m", "m", "kilogram"),
        ),
    ),
    formula(
        "rod_center_inertia",
        "rotation",
        "Thin rod about its center",
        "I",
        base_latex=r"I = \frac{1}{12}mL^2",
        assumptions=("the axis is perpendicular to the rod through its center",),
        expression="m*rod_length**2/12",
        variables=(
            var("m", "m", "kilogram"),
            var("rod_length", "L", "meter"),
        ),
        binding=Binding(
            asks=("moment of inertia",),
            result=("kilogram * meter ** 2",),
            inputs=(frozenset({"m", "rod_length"}),),
            cues=("rod",),
            excludes=("end",),
            nonnegative=True,
        ),
    ),
    formula(
        "rod_end_inertia",
        "rotation",
        "Thin rod about one end",
        "I",
        base_latex=r"I = \frac{1}{3}mL^2",
        assumptions=("the axis is perpendicular to the rod through one end",),
        expression="m*rod_length**2/3",
        variables=(
            var("m", "m", "kilogram"),
            var("rod_length", "L", "meter"),
        ),
        binding=Binding(
            asks=("moment of inertia",),
            result=("kilogram * meter ** 2",),
            inputs=(frozenset({"m", "rod_length"}),),
            cues=("rod",),
            excludes=("center", "centre"),
            nonnegative=True,
        ),
    ),
)
