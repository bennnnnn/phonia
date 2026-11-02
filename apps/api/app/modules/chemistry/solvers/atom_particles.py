# ruff: noqa: RUF001, RUF002 -- textbook formulas use the minus sign.
"""An atom's or ion's particles from any two facts about it: A = Z + N, electrons = Z − charge.

The school shell rule (2, 8, 8, 2) gives the electron arrangement up to calcium, and the
valence electrons and valency with it; past Z = 20 the arrangement declines.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.elements import BY_NUMBER, BY_SYMBOL, Element
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.display import verified
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError

_SHELLS = (2, 8, 8, 2)
_SCHOOL_SHELL_LIMIT = 20
_SUPERSCRIPT = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")


def _shells(electrons: int) -> list[int]:
    if not 0 < electrons <= _SCHOOL_SHELL_LIMIT:
        raise SolveServiceError("the school shell rule stops at calcium")
    shells: list[int] = []
    left = electrons
    for size in _SHELLS:
        if left <= 0:
            break
        shells.append(min(size, left))
        left -= shells[-1]
    return shells


def _int(params: dict[str, float], name: str) -> int | None:
    value = params.get(name)
    return None if value is None else int(value)


def _ion_name(symbol: str, name: str, charge: int) -> str:
    if charge == 0:
        return f"{name} atom ({symbol})"
    size = "" if abs(charge) == 1 else str(abs(charge))
    sign = "+" if charge > 0 else "-"
    kind = "cation" if charge > 0 else "anion"
    return f"{name} {kind} ({symbol}{(size + sign).translate(_SUPERSCRIPT)})"


@dataclass
class _Atom:
    """One atom or ion, its particles derived from the facts given."""

    z: int
    mass: int | None
    neutrons: int | None
    electrons: int
    charge: int
    element: Element | None


def _atomic_number(
    params: dict[str, float], element: Element | None, neutral: bool, rows: list[str]
) -> int:
    """Z from the atomic number, the protons or the element, else from a neutral atom's
    electrons, else from A − N. Two that disagree decline."""
    stated_z = {
        value
        for value in (
            _int(params, "atomic_number"),
            _int(params, "protons"),
            element.number if element else None,
        )
        if value is not None
    }
    if len(stated_z) > 1:
        raise SolveServiceError("the atomic number, protons and element disagree")
    if stated_z:
        return stated_z.pop()
    electrons = _int(params, "electrons")
    if electrons is not None and neutral and _int(params, "charge") in (None, 0):
        rows.append(f"protons = electrons (a neutral atom) = {electrons}")
        return electrons
    mass, neutrons = _int(params, "mass_number"), _int(params, "neutrons")
    if mass is None or neutrons is None:
        raise SolveServiceError("nothing gives the atomic number")
    rows.append(f"Z = A − N = {mass} − {neutrons} = {mass - neutrons}")
    return mass - neutrons


def _derive(
    params: dict[str, float],
    element: Element | None,
    neutral: bool,
    asked: list[str],
    rows: list[str],
) -> _Atom:
    z = _atomic_number(params, element, neutral, rows)
    if z <= 0:
        raise SolveServiceError("an atom has at least one proton")
    mass, neutrons = _int(params, "mass_number"), _int(params, "neutrons")
    if mass is not None and neutrons is not None and mass != z + neutrons:
        raise SolveServiceError("the mass number is not the protons and neutrons together")
    if mass is None and neutrons is not None:
        mass = z + neutrons
        rows.append(f"A = Z + N = {z} + {neutrons} = {mass}")
    elif mass is not None and neutrons is None:
        neutrons = mass - z
        rows.append(f"N = A − Z = {mass} − {z} = {neutrons}")
    if neutrons is not None and neutrons < 0:
        raise SolveServiceError("more protons than nucleons")
    charge, electrons = _int(params, "charge"), _int(params, "electrons")
    if electrons is None:
        if charge is None and (neutral or not {"kind", "charge"} & set(asked)):
            charge = 0
        if charge is None:
            raise SolveServiceError("an ion's electrons need its charge")
        electrons = z - charge
        rows.append(f"electrons = Z − charge = {z} − ({charge}) = {electrons}")
    elif charge is not None and electrons != z - charge:
        raise SolveServiceError("the electrons and the charge disagree")
    elif charge is None:
        charge = z - electrons
        rows.append(f"charge = protons − electrons = {z} − {electrons} = {charge:+d}")
    return _Atom(z, mass, neutrons, electrons, charge, element or BY_NUMBER.get(z))


def _answer(item: str, atom: _Atom, rows: list[str]) -> str:
    """The answer line for one asked quantity."""
    if item in ("configuration", "valence", "valency"):
        shells = _shells(atom.electrons)
        if item == "configuration":
            rows.append(f"{atom.electrons} electrons fill the shells K, L, M, N as 2, 8, 8, 2")
            return f"Electronic configuration = {', '.join(map(str, shells))}"
        if item == "valence":
            return f"Valence electrons = {shells[-1]}"
        outer = _shells(atom.z)[-1]
        full = outer == (2 if atom.z <= 2 else 8)
        return f"Valency = {0 if full else min(outer, 8 - outer)}"
    if item == "neutrons" and atom.neutrons is None:
        raise SolveServiceError("the neutrons need the mass number")
    if item == "mass_number" and atom.mass is None:
        raise SolveServiceError("the mass number needs the neutrons")
    if item == "name" and atom.element is None:
        raise SolveServiceError("no element has that atomic number")
    charge = atom.charge
    kind = "neutral atom" if charge == 0 else "cation" if charge > 0 else "anion"
    lines = {
        "protons": f"Protons = {atom.z}",
        "atomic_number": f"Atomic number Z = {atom.z}",
        "neutrons": f"Neutrons = {atom.neutrons}",
        "mass_number": f"Mass number A = {atom.mass}",
        "electrons": f"Electrons = {atom.electrons}",
        "charge": f"Charge = {charge:+d}" if charge else "Charge = 0 (neutral)",
        "kind": f"Type = {kind}",
    }
    if item == "name" and atom.element is not None:
        return f"Species = {_ion_name(atom.element.symbol, atom.element.name, charge)}"
    return lines[item]


def _given(params: dict[str, float], element: Element | None) -> list[str]:
    given = [f"element: {element.name} ({element.symbol}), Z = {element.number}"] if element else []
    for name, label in (
        ("atomic_number", "Z"),
        ("mass_number", "A"),
        ("protons", "protons"),
        ("neutrons", "neutrons"),
        ("electrons", "electrons"),
    ):
        if name in params:
            given.append(f"{label} = {int(params[name])}")
    if "charge" in params:
        given.append(f"charge = {int(params['charge']):+d}")
    return given


def solve_atom_particles(intent: ChemistryIntent) -> ChemistryResult:
    asked_text, _, neutral_word = (intent.target or "").partition("|")
    asked = [item for item in asked_text.split(",") if item]
    if not asked:
        raise SolveServiceError("nothing asked")
    element = BY_SYMBOL.get(intent.formula or "")
    rows: list[str] = []
    atom = _derive(intent.params, element, bool(neutral_word), asked, rows)
    answers = [_answer(item, atom, rows) for item in asked]
    law, formula = stated("atom_particles")
    shown = "\n".join(answers)
    return verified(
        "Verified atomic structure",
        tuple(_given(intent.params, element)),
        ", ".join(answer.split(" = ")[0] for answer in answers),
        law,
        formula,
        tuple(rows) or (f"protons = Z = {atom.z}",),
        shown,
        shown,
        verbatim=True,
    )
