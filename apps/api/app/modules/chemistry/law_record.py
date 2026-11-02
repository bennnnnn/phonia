"""One chemistry law the shared binder can fill."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.law_binding.spec import Binding, FormulaSpec, VariableSpec

_MOLAR = "mole / liter"
_MOLAL = "mole / kilogram"
_PER_SECOND = "1 / second"
_PH_ASKS = ("p_h",)
# A mass asked in milligrams: the law's grams are converted for the answer.
_MILLIGRAM_ASKS = ("how many mg", "how many milligrams", "mass in mg", "mass in milligrams")
# The words beside a solute's and a solvent's mass ("10.0 g compound in 250 g of water").
_SOLUTE_WORDS = ("compound", "solute", "salt", "sugar")
_SOLVENT_WORDS = ("water", "solvent")
# A metal deposited by a current: "plate 5.00 g of silver", "electroplating", "is deposited".
# A cue matches from a word's start, so "plate" also reads "plated" and "plates".
_ELECTROLYSIS_CUES = ("deposit", "electrolysis", "electroplat", "plate", "plating")


@dataclass(frozen=True, slots=True)
class ChemistryLaw:
    """One law the binder can fill, and the solver operation that answers it."""

    op: str
    kind: str
    spec: FormulaSpec
    # The role of the substance the law is about ("acid_strong"); its formula goes on the intent.
    species: str | None = None
    # Inputs passed in the unit the question wrote, with that unit on the intent.
    keep_units: tuple[str, ...] = ()
    # Units the solver reads off the intent, as the converted inputs are in.
    labels: tuple[tuple[str, str], ...] = ()
    # A per-mole value (ΔH in kJ/mol) is per mole of the substance only when no equation is
    # written: "2H2 + O2 -> 2H2O, ΔH = -572 kJ/mol" is per mole of that reaction, two of H2.
    no_equation: bool = False


def _law(
    op: str,
    kind: str,
    asks: tuple[str, ...],
    result: str,
    variables: tuple[VariableSpec, ...],
    *,
    name: str | None = None,
    inputs: tuple[frozenset[str], ...] | None = None,
    cues: tuple[str, ...] = (),
    excludes: tuple[str, ...] = (),
    interchangeable: tuple[str, ...] = (),
    species: str | None = None,
    keep_units: tuple[str, ...] = (),
    labels: tuple[tuple[str, str], ...] = (),
    nonnegative: bool = True,
    no_equation: bool = False,
) -> ChemistryLaw:
    names = frozenset(variable.name for variable in variables)
    binding = Binding(
        asks=asks,
        result=(result,),
        inputs=inputs or (names,),
        cues=cues,
        excludes=excludes,
        interchangeable=interchangeable,
        nonnegative=nonnegative,
    )
    spec = FormulaSpec(
        id=name or op,
        kind=kind,
        law_name=op,
        result_symbol="",
        variables=variables,
        binding=binding,
    )
    return ChemistryLaw(op, kind, spec, species, keep_units, labels, no_equation)
