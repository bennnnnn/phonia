"""A machine in a school book's terms: velocity ratio, work in and out, and efficiency.

"A 500 N car is pulled up a 20 m plank to a flat 5 m above the ground by an effort of
150 N parallel to the plank. Calculate: a. VR b. MA c. input work d. output work
e. efficiency" (a grade 7 physics book, 2026-10-29) had none of these laws, so it went
to the model unchecked. The effort moves along the plank; the load rises its height.
"""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, VariableSpec, formula, var

_ASKS_VR = ("velocity ratio", "v.r", "vr")
# "A ramp 2 m high": a noun before a value is the subject, not the value's name, so only
# "long" and "length" name the plank's length ("a 20 m plank" is read "a 20 m long plank").
_PLANK = ("long", "length", "along")
_HEIGHT = ("height", "high", "above", "rise", "raised", "lifted")
# The load: "a load of 500 N", or the weight of the thing moved ("a 500 N car").
_LOAD = (
    "load", "output", "weighs", "weight", "car", "box", "crate", "block", "stone", "sack",
    "barrel", "drum", "trolley", "cart", "body", "object", "bag", "rock", "log",
)  # fmt: skip
_EFFORT = ("effort", "input", "applied", "pushes", "pulls with")


# A lever's arm or a pulley's rope is no plank: their lengths are not the effort's path.
_NOT_A_PLANK = (
    "lever", "pulley", "rope", "gear", "wheel", "axle", "screw", "wedge",
    # The ideal advantage, however it is named, is the plank's geometry, not its forces.
    "ideal", "theoretical", "expected", "without friction", "frictionless", "no friction",
)  # fmt: skip


def _effort_force() -> VariableSpec:
    return var("F_in", "F_{in}", "newton", words=_EFFORT, needs_words=True)


def _load_force() -> VariableSpec:
    return var("F_out", "F_{out}", "newton", words=_LOAD, needs_words=True)


def _plank() -> VariableSpec:
    return var("incline_length", "L", "meter", words=_PLANK, needs_words=True)


def _height() -> VariableSpec:
    return var("incline_height", "h", "meter", words=_HEIGHT, needs_words=True)


def _machine() -> tuple[VariableSpec, ...]:
    """The load, the effort, the plank and the height: a law about the plank reads them
    all, since every value a question states must be one of its law's inputs."""
    return (_load_force(), _effort_force(), _plank(), _height())


_ALL = frozenset({"F_out", "F_in", "incline_length", "incline_height"})

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "machine_velocity_ratio_incline",
        "energy",
        "Velocity ratio of an inclined plane",
        "VR",
        base_latex=r"VR = \frac{L}{h}",
        expression="incline_length/incline_height",
        variables=_machine(),
        binding=Binding(
            asks=_ASKS_VR,
            result=("dimensionless",),
            inputs=(frozenset({"incline_length", "incline_height"}), _ALL),
            cues=("plank", "ramp", "inclined plane", "slope"),
            excludes=_NOT_A_PLANK,
            nonnegative=True,
        ),
    ),
    # The actual mechanical advantage, load over effort: 500 N / 150 N is 3.33, where the
    # plank's ideal one (L / h, machines.py) would say 4.
    formula(
        "machine_advantage_incline_forces",
        "energy",
        "Mechanical advantage from force",
        "MA",
        base_latex=r"MA = \frac{F_{out}}{F_{in}}",
        expression="F_out/F_in",
        variables=_machine(),
        binding=Binding(
            asks=("mechanical advantage", "m.a"),
            result=("dimensionless",),
            inputs=(_ALL,),
            cues=("effort",),
            excludes=_NOT_A_PLANK,
            nonnegative=True,
        ),
    ),
    formula(
        "machine_work_input_incline",
        "energy",
        "Work done by the effort",
        "W_{in}",
        base_latex=r"W_{in} = F_{in} L",
        expression="F_in*incline_length",
        variables=_machine(),
        binding=Binding(
            asks=("input work", "work input", "work done by the effort"),
            result=("joule",),
            inputs=(frozenset({"F_in", "incline_length"}), _ALL),
            cues=("effort",),
            excludes=_NOT_A_PLANK,
            nonnegative=True,
        ),
    ),
    formula(
        "machine_work_output_incline",
        "energy",
        "Work done on the load",
        "W_{out}",
        base_latex=r"W_{out} = F_{out} h",
        expression="F_out*incline_height",
        variables=_machine(),
        binding=Binding(
            asks=("output work", "work output", "useful work", "work done on the load"),
            result=("joule",),
            inputs=(frozenset({"F_out", "incline_height"}), _ALL),
            cues=("effort", "load"),
            excludes=_NOT_A_PLANK,
            nonnegative=True,
        ),
    ),
    formula(
        "machine_efficiency_incline",
        "energy",
        "Efficiency of a machine",
        r"\eta",
        base_latex=r"\eta = \frac{F_{out} h}{F_{in} L} \times 100\%",
        expression="100*F_out*incline_height/(F_in*incline_length)",
        variables=_machine(),
        binding=Binding(
            asks=("efficiency",),
            result=("percent",),
            inputs=(_ALL,),
            cues=("effort", "plank", "ramp", "inclined plane"),
            excludes=_NOT_A_PLANK,
            nonnegative=True,
            at_most=100.0,
        ),
    ),
)
