"""One verified operation of a subject: the law, its variables, and its assumptions.

A subject's solvers own word-problem procedure. This record owns the identity those
procedures would otherwise repeat in their direct replies.

An operation with a ``binding`` can also be read straight from a question by
``law_binding.fit``: the binding says how a question asks for the result, and
each variable says how a question names it. An operation with an
``expression`` needs no solver of its own; ``law_binding.expression`` evaluates it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VariableSpec:
    """One named input of a formula.

    ``dimension`` is a Pint unit expression. A quantity with no dimension sets
    ``dimensionless`` instead of leaving the field blank.
    """

    name: str
    symbol: str
    dimension: str | None = None
    dimensionless: bool = False
    # Classifier flags such as elastic / mode_factor are inputs, not givens.
    visible: bool = True
    # Words written just before this input's value: "initial", "from", "reaches".
    # Only needed where two inputs share a dimension (u and v).
    words: tuple[str, ...] = ()
    # Phrases that state the value without a number: ("from rest", 0.0).
    implied: tuple[tuple[str, float], ...] = ()
    # Words before the value that make it negative: "decelerates at 2 m/s²".
    negating: tuple[str, ...] = ()
    # Where an unstated value comes from: "gravity" (9.81, or the named body's),
    # "body_mass" or "body_radius" (of the planet or star the question names),
    # "particle_charge" or "particle_mass" (of the particle it names),
    # "water_specific_heat" or "water_density" (when water is the only
    # substance named), "sea_level_pressure", or "incident_from_air" (a ray
    # that strikes a medium and is never said to start inside one).
    fallback: str | None = None
    # The value must be named by one of ``words``, before or after it, even
    # when it is the only input of its kind: an object's density is not the
    # fluid's, and a tube's diameter is not its radius.
    needs_words: bool = False

    def __post_init__(self) -> None:
        if self.dimensionless == (self.dimension is not None):
            raise ValueError(f"{self.name} needs a dimension or an explicit dimensionless flag")


@dataclass(frozen=True, slots=True)
class FormulaVariant:
    """A form of the law that is true only for some of its givens.

    The first variant whose conditions match is the one the reply shows.
    ``latex`` replaces the base equation. ``lines`` replaces it with several
    equations. ``assumptions`` replaces the law's assumptions for that case.
    """

    latex: str | None = None
    lines: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    present: frozenset[str] = frozenset()
    absent: frozenset[str] = frozenset()
    positive: frozenset[str] = frozenset()
    equals: tuple[tuple[str, float], ...] = ()
    # Find-line symbol when this case is the one that matched. None keeps the law's.
    result_symbol: str | None = None
    # The arithmetic of this case for an expression operation (``u = v - a*t``'s
    # right-hand side), in the names of the variables.
    expression: str | None = None


@dataclass(frozen=True, slots=True)
class Binding:
    """How a question asks for this operation, so the binder can read it.

    ``asks`` are phrases that name the result in the asked clause ("initial
    velocity", "how long"). ``result`` holds the Pint unit of each result, in
    order. ``inputs`` lists every set of givens the solver answers from; a
    question that binds to any other set is not this operation. One of
    ``cues`` must appear in the question when the law needs a situation the
    numbers cannot show ("horizontally", "pulley"). ``descending`` names
    same-dimension inputs filled largest first (the heavier Atwood mass);
    ``interchangeable`` names inputs that play the same part and are filled
    in the order stated (two capacitors in series).
    A contract test solves every input set with sample values, so a binding
    never promises a set its solver refuses.
    """

    asks: tuple[str, ...]
    result: tuple[str, ...]
    inputs: tuple[frozenset[str], ...]
    cues: tuple[str, ...] = ()
    # Words that rule the operation out: a discharge is not a charging.
    excludes: tuple[str, ...] = ()
    descending: tuple[str, ...] = ()
    interchangeable: tuple[str, ...] = ()
    # Words before a value that say it is the result itself ("reaches" for a
    # final speed): such a question already states what this operation finds.
    result_words: tuple[str, ...] = ()
    # A negative result is not an answer (a time, a height, a power).
    nonnegative: bool = False
    # A negative result is reported as its size with this note: cooling "releases" heat.
    negative_detail: str | None = None
    # A result above this is not an answer: a floating fraction above 1 sinks.
    at_most: float | None = None
    # Expressions in the variable names that must come out positive for the
    # law to hold at all: a rope steep enough to lift a crate off the floor
    # leaves no normal force for friction to scale ("m*g - F*sin(angle)").
    requires: tuple[str, ...] = ()
    # The unit the answer is printed in when it is not the SI spelling of
    # ``result[0]``: an activity in Bq, not 1/s.
    shown_unit: str | None = None


@dataclass(frozen=True, slots=True)
class FormulaSpec:
    """Identity of one operation (a ``physics_op``)."""

    id: str
    kind: str
    law_name: str
    result_symbol: str
    base_latex: str | None = None
    assumptions: tuple[str, ...] = ()
    variables: tuple[VariableSpec, ...] = ()
    variants: tuple[FormulaVariant, ...] = ()
    # Default assumptions are stated only when every one of these params was given.
    assumptions_require: frozenset[str] = frozenset()
    # Exactly one of these may be absent. That one is the quantity being solved.
    solve_for: tuple[tuple[str, str], ...] = ()
    binding: Binding | None = None
    # The arithmetic of the law for an expression operation; a variant's
    # expression replaces it for that variant's givens.
    expression: str | None = None


def var(
    name: str,
    symbol: str,
    dimension: str | None = None,
    *,
    dimensionless: bool = False,
    visible: bool = True,
    words: tuple[str, ...] = (),
    implied: tuple[tuple[str, float], ...] = (),
    negating: tuple[str, ...] = (),
    fallback: str | None = None,
    needs_words: bool = False,
) -> VariableSpec:
    return VariableSpec(
        name=name,
        symbol=symbol,
        dimension=dimension,
        dimensionless=dimensionless,
        visible=visible,
        words=words,
        implied=implied,
        negating=negating,
        fallback=fallback,
        needs_words=needs_words,
    )


def bind(
    asks: tuple[str, ...],
    result: str,
    *inputs: str,
    cues: tuple[str, ...] = (),
    excludes: tuple[str, ...] = (),
) -> Binding:
    """A binding with one input set and a result that is never negative."""
    return Binding(
        asks=asks,
        result=(result,),
        inputs=(frozenset(inputs),),
        cues=cues,
        excludes=excludes,
        nonnegative=True,
    )


def formula(
    operation: str,
    kind: str,
    law_name: str,
    result_symbol: str,
    base_latex: str | None = None,
    assumptions: tuple[str, ...] = (),
    variables: tuple[VariableSpec, ...] = (),
    variants: tuple[FormulaVariant, ...] = (),
    assumptions_require: frozenset[str] = frozenset(),
    solve_for: tuple[tuple[str, str], ...] = (),
    binding: Binding | None = None,
    expression: str | None = None,
) -> FormulaSpec:
    return FormulaSpec(
        id=operation,
        kind=kind,
        law_name=law_name,
        result_symbol=result_symbol,
        base_latex=base_latex,
        assumptions=assumptions,
        variables=variables,
        variants=variants,
        assumptions_require=assumptions_require,
        solve_for=solve_for,
        binding=binding,
        expression=expression,
    )


def matching_variant(spec: FormulaSpec, params: dict[str, float]) -> FormulaVariant | None:
    """The first variant whose givens match, if any."""
    for variant in spec.variants:
        if _variant_matches(variant, params):
            return variant
    return None


def _variant_matches(variant: FormulaVariant, params: dict[str, float]) -> bool:
    if not variant.present <= params.keys():
        return False
    if variant.absent & params.keys():
        return False
    if any(params.get(name, 0.0) <= 0 for name in variant.positive):
        return False
    return all(params.get(name) == value for name, value in variant.equals)


def select_formula(
    spec: FormulaSpec, params: dict[str, float]
) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    """Base equation, extra equation lines, and the assumptions that apply."""
    variant = matching_variant(spec, params)
    if variant is not None:
        latex = spec.base_latex if variant.latex is None else variant.latex
        return latex, variant.lines, variant.assumptions
    assumptions = spec.assumptions
    if spec.assumptions_require and not spec.assumptions_require <= params.keys():
        assumptions = ()
    return spec.base_latex, (), assumptions


def visible_assumptions(spec: FormulaSpec, params: dict[str, float]) -> tuple[str, ...]:
    """Assumptions that are true for this solve, not merely printed on the law."""
    return select_formula(spec, params)[2]


def variable_for(spec: FormulaSpec, name: str) -> VariableSpec | None:
    """The declared input with this parameter name, or nothing."""
    for variable in spec.variables:
        if variable.name == name:
            return variable
    return None


def symbol_for(spec: FormulaSpec, name: str) -> str | None:
    """Display symbol declared for this operation, or nothing."""
    variable = variable_for(spec, name)
    return None if variable is None else variable.symbol
