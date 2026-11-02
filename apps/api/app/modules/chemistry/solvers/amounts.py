# ruff: noqa: RUF001 -- textbook formulas intentionally use multiplication symbols.
"""Chemical amounts, composition, yield, and equation calculations."""

from __future__ import annotations

from fractions import Fraction

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.formula import parse_formula
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import AVOGADRO
from app.modules.chemistry.solvers.display import (
    atomic_mass,
    const,
    inp,
    mean,
    molar_mass_text,
    molar_mass_working,
    num,
    qty,
    table_num,
    verified,
)
from app.modules.chemistry.solvers.params import require
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.stoichiometry import (
    formula_atoms,
    molar_mass,
)
from app.services.solving import SolveServiceError

# A mass in grams, in the unit a question asks it in.
_GRAMS_IN = {"mg": 1000.0, "kg": 0.001}


def _molar_mass(formula: str) -> float:
    try:
        return molar_mass(formula)
    except ValueError as exc:
        raise SolveServiceError(str(exc)) from exc


def _formula(intent: ChemistryIntent) -> str:
    if not intent.formula:
        raise SolveServiceError("a chemical formula is required")
    return intent.formula


def _mass_terms(formula: str) -> str | None:
    """Each element's atom count times its atomic mass: ``2(1.008) + 1(15.999)``."""
    terms = [
        f"{count}({atomic_mass(known.mass)})"
        for symbol, count in (formula_atoms(formula) or {}).items()
        if (known := BY_SYMBOL.get(symbol)) is not None
    ]
    return " + ".join(terms) or None


def solve_molar_mass(intent: ChemistryIntent) -> ChemistryResult:
    formula = _formula(intent)
    mass = _molar_mass(formula)
    substitution = _mass_terms(formula) or f"RDKit molecular mass for {formula}"
    result = f"{molar_mass_text(mass)} g/mol"
    return verified(
        title="Verified molar mass",
        given=(f"Formula = {formula}",),
        find="Molar mass, M",
        formula_name=stated("molar_mass")[0],
        formula=stated("molar_mass")[1],
        substitution=(f"M = {substitution}",),
        answer=f"M({formula}) = {result}",
        value=result,
    )


def _particles_per_formula(intent: ChemistryIntent, formula: str) -> tuple[int, str]:
    """Atoms per formula unit when the question counts atoms, else 1 particle each."""
    noun = intent.units.get("particle", "particles")
    if noun != "atoms":
        return 1, "particles"
    atoms = formula_atoms(formula)
    if not atoms:
        raise SolveServiceError(f"cannot count the atoms in {formula}")
    return sum(atoms.values()), "atoms"


def _per_unit(formula: str, per_formula: int) -> tuple[str, ...]:
    """The atom count an atom total multiplies by, named, so it is not a bare ``(3)``."""
    return () if per_formula == 1 else (f"atoms per {formula} = {per_formula}",)


def solve_amount(intent: ChemistryIntent) -> ChemistryResult:
    op = intent.chemistry_op
    formula = _formula(intent)
    molar = _molar_mass(formula)
    if op == "mass_to_moles":
        mass = require(intent, "mass", non_negative=True)
        moles = mass / molar
        value = f"{num(moles)} mol"
        return verified(
            "Verified amount of substance",
            (f"mass = {inp(mass)} g", f"M({formula}) = {molar_mass_working(molar)} g/mol"),
            "Amount, n",
            *stated("mass_to_moles"),
            (f"n = {qty(mass, 'g')} / {molar_mass_working(molar)} g/mol",),
            f"n({formula}) = {value}",
            value,
        )
    if op == "moles_to_mass":
        moles = require(intent, "moles", non_negative=True)
        mass = moles * molar
        value = f"{num(mass)} g"
        rows = [f"m = ({qty(moles, 'mol')})({molar_mass_working(molar)} g/mol)"]
        asked = intent.units.get("answer")
        if asked in _GRAMS_IN:
            # "How many mg is 0.0150 mol of NaOH?": the grams, then the unit asked.
            rows.append(f"m = {value} = {num(mass * _GRAMS_IN[asked])} {asked}")
            value = f"{num(mass * _GRAMS_IN[asked])} {asked}"
        return verified(
            "Verified mass",
            (f"n = {inp(moles)} mol", f"M({formula}) = {molar_mass_working(molar)} g/mol"),
            "Mass, m",
            *stated("moles_to_mass"),
            rows,
            f"m({formula}) = {value}",
            value,
        )
    per_formula, noun = _particles_per_formula(intent, formula)
    if op == "moles_to_particles":
        moles = require(intent, "moles", non_negative=True)
        particles = moles * AVOGADRO * per_formula
        value = f"{num(particles)} {noun}"
        law_name, base_formula = stated("moles_to_particles")
        particle_formula = (
            base_formula if per_formula == 1 else "N = n Nₐ × (atoms per formula unit)"
        )
        return verified(
            "Verified particle count",
            (
                f"n = {inp(moles)} mol",
                f"Nₐ = {const(AVOGADRO)} mol⁻¹",
                *_per_unit(formula, per_formula),
            ),
            f"Number of {noun}, N",
            law_name,
            particle_formula,
            (
                f"N = ({qty(moles, 'mol')})({const(AVOGADRO)} mol⁻¹)"
                + ("" if per_formula == 1 else f" × ({per_formula} atoms per {formula})"),
            ),
            f"N({formula}) = {value}",
            value,
        )
    if op == "mass_to_particles":
        mass = require(intent, "mass", non_negative=True)
        moles = mass / molar
        particles = moles * AVOGADRO * per_formula
        law_name, base_formula = stated("mass_to_particles")
        value = f"{num(particles)} {noun}"
        return verified(
            "Verified particle count",
            (
                f"m = {inp(mass)} g",
                f"M({formula}) = {molar_mass_working(molar)} g/mol",
                f"Nₐ = {const(AVOGADRO)} mol⁻¹",
                *_per_unit(formula, per_formula),
            ),
            f"Number of {noun}, N",
            law_name,
            base_formula if per_formula == 1 else "N = (m / M)Nₐ × (atoms per formula unit)",
            (
                f"n = {qty(mass, 'g')} / {molar_mass_working(molar)} g/mol = {num(moles)} mol",
                f"N = ({num(moles)} mol)({const(AVOGADRO)} mol⁻¹)"
                + ("" if per_formula == 1 else f" × ({per_formula} atoms per {formula})"),
            ),
            f"N({formula}) = {value}",
            value,
        )
    if op == "particles_to_moles":
        particles = require(intent, "particles", non_negative=True)
        moles = particles / AVOGADRO / per_formula
        value = f"{num(moles)} mol"
        law_name, base_formula = stated("particles_to_moles")
        amount_formula = (
            base_formula if per_formula == 1 else "n = N / (Nₐ × atoms per formula unit)"
        )
        return verified(
            "Verified amount of substance",
            (
                f"N = {inp(particles)} {noun}",
                f"Nₐ = {const(AVOGADRO)} mol⁻¹",
                *_per_unit(formula, per_formula),
            ),
            "Amount, n",
            law_name,
            amount_formula,
            (
                f"n = {inp(particles)} / {const(AVOGADRO)} mol⁻¹"
                + ("" if per_formula == 1 else f" / ({per_formula} atoms per {formula})"),
            ),
            f"n({formula}) = {value}",
            value,
        )
    raise SolveServiceError(f"unsupported amount operation: {op}")


def _weighted(coefficient: int, molar: str) -> str:
    return molar if coefficient == 1 else f"{coefficient} × {molar}"


def _mass_symbol(coefficient: int, label: str) -> str:
    mass = f"M({label})"
    return mass if coefficient == 1 else f"{coefficient} {mass}"


def solve_atom_economy(intent: ChemistryIntent) -> ChemistryResult:
    """Percent of reactant mass that ends in one product of an already balanced equation."""
    from app.modules.chemistry.equations import written_is_balanced
    from app.modules.chemistry.species import ReactionTerm, parse_reaction, parse_species

    equation = intent.equation
    target = intent.target
    if not equation or not target or not written_is_balanced(equation):
        raise SolveServiceError("atom economy needs a balanced equation and its desired product")
    reaction = parse_reaction(equation)
    if reaction is None:
        raise SolveServiceError("atom economy needs a balanced equation and its desired product")
    named: str = target

    def same_product(label: str) -> bool:
        if label == named:
            return True
        written = parse_species(label, coefficient_already_removed=True)
        asked = parse_species(named, coefficient_already_removed=True)
        return (
            written is not None
            and asked is not None
            and written.formula == asked.formula
            and written.charge == asked.charge
        )

    matches = [term for term in reaction.products if same_product(term.species.label)]
    if len(matches) != 1:
        raise SolveServiceError(f"{target} is not a product of the equation")
    product = matches[0]
    target = product.species.label

    def mass_of(term: ReactionTerm) -> tuple[str, float]:
        molar = _molar_mass(term.species.formula)
        return molar_mass_working(molar), term.coefficient * molar

    reactant_rows = [(term, *mass_of(term)) for term in reaction.reactants]
    product_text, product_mass = mass_of(product)
    total = sum(row[2] for row in reactant_rows)
    shown = f"{num(product_mass / total * 100)}%"
    reactant_sum = " + ".join(
        _weighted(term.coefficient, text) for term, text, _mass in reactant_rows
    )
    reactant_symbols = " + ".join(
        _mass_symbol(term.coefficient, term.species.label) for term in reaction.reactants
    )
    formula = (
        f"% atom economy = {_mass_symbol(product.coefficient, target)} / ({reactant_symbols}) × 100"
    )
    return verified(
        "Verified atom economy",
        (
            f"Equation = {equation}",
            f"Desired product = {target}",
            *(
                f"M({term.species.label}) = {text} g/mol"
                for term, text, _mass in (*reactant_rows, (product, product_text, product_mass))
            ),
        ),
        "Atom economy",
        stated("atom_economy")[0],
        formula,
        (
            "% atom economy = "
            f"{_weighted(product.coefficient, product_text)} / ({reactant_sum}) × 100",
        ),
        f"Atom economy of {target} = {shown}",
        shown,
    )


def solve_percent_composition(intent: ChemistryIntent) -> ChemistryResult:
    formula = _formula(intent)
    element = intent.target
    if not element:
        raise SolveServiceError("an element is required")
    atoms = parse_formula(formula)
    count = atoms.get(element)
    known = BY_SYMBOL.get(element)
    if count is None or known is None:
        raise SolveServiceError(f"{element} is not present in {formula}")
    total = _molar_mass(formula)
    percent = count * known.mass / total * 100
    value = f"{table_num(percent)}%"
    whole = molar_mass_working(total)
    terms = _mass_terms(formula)
    return verified(
        "Verified percent composition",
        (f"Formula = {formula}", f"{element} atoms per formula unit = {count}"),
        f"Mass percent of {element}",
        *stated("percent_composition"),
        (
            f"M({formula}) = {f'{terms} = ' if terms else ''}{whole} g/mol",
            f"% {element} = {count} × {atomic_mass(known.mass)} / {whole} × 100",
        ),
        f"{element} in {formula} = {value}",
        value,
    )


# Rounded abundances may miss 100% by a hundredth or so; more is a different question.
_ABUNDANCE_TOLERANCE = 0.1


def solve_average_atomic_mass(intent: ChemistryIntent) -> ChemistryResult:
    abundances = intent.species
    masses = intent.params
    if len(abundances) < 2 or set(abundances) != set(masses):
        raise SolveServiceError("an average atomic mass needs each isotope's mass and abundance")
    if any(value <= 0 for value in (*abundances.values(), *masses.values())):
        raise SolveServiceError("isotope masses and abundances must be positive")
    if abs(sum(abundances.values()) - 100) > _ABUNDANCE_TOLERANCE:
        raise SolveServiceError("isotope abundances must add up to 100%")
    # Summed exactly from the numbers as written: 6.02 at 7.5% and 7.02 at 92.5% is 6.945, which
    # rounds to 6.95; a float sum is 6.944999… and rounded down to 6.94.
    average = float(
        sum(
            Fraction(repr(masses[label])) * Fraction(repr(abundances[label]))
            for label in abundances
        )
        / 100
    )
    symbol = intent.target or ""
    shown = f"{mean(average)} u"
    terms = " + ".join(
        f"({inp(masses[label])} u)({inp(abundances[label] / 100)})" for label in abundances
    )
    return verified(
        "Verified average atomic mass",
        tuple(
            f"{label}: {inp(masses[label])} u, {inp(abundances[label])}%" for label in abundances
        ),
        "Average atomic mass",
        *stated("average_atomic_mass"),
        (f"A({symbol}) = {terms}",),
        f"A({symbol}) = {shown}",
        shown,
    )
