# ruff: noqa: RUF001, RUF002
"""Rates from data: a rate law from initial rates, two-point Arrhenius, Michaelis–Menten."""

from __future__ import annotations

import math

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import GAS_R_J
from app.modules.chemistry.solvers.display import const, inp, num, verified
from app.modules.chemistry.solvers.params import require, require_all
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError

_ARRHENIUS = ("k1", "t1", "k2", "t2")


def _order_from_change(rate1: float, rate2: float, left: float, right: float) -> int:
    if left <= 0 or right <= 0 or rate1 <= 0 or rate2 <= 0 or left == right:
        raise SolveServiceError("rate-law experiments need positive changing concentrations")
    order = math.log(rate2 / rate1) / math.log(right / left)
    rounded = round(order)
    if abs(order - rounded) > 0.05:
        raise SolveServiceError("reaction order is not an integer")
    return int(rounded)


def solve_rate_law(intent: ChemistryIntent) -> ChemistryResult:
    a1, rate1, a2, rate2 = require_all(
        intent, "a1", "rate1", "a2", "rate2", message="rate law needs two experiments"
    )
    b1 = intent.params.get("b1")
    b2 = intent.params.get("b2")
    if b1 is not None and b2 is not None and abs(a1 - a2) > 1e-12:
        if abs(b1 - b2) > 1e-12:
            raise SolveServiceError("only one concentration may change between experiments")
        # Two points with [B] held do not measure the order in B.
        raise SolveServiceError("the order in B was not measured")
    if abs(a1 - a2) > 1e-12:
        order_a = _order_from_change(rate1, rate2, a1, a2)
        order_b = 0
        b_factor = 1.0
        changing, first, second = "A", a1, a2
    else:
        order_a = 0
        if b1 is None or b2 is None:
            raise SolveServiceError("the changing concentration is missing")
        order_b = _order_from_change(rate1, rate2, b1, b2)
        b_factor = b1**order_b
        changing, first, second = "B", b1, b2
    order = order_a or order_b
    denominator = a1**order_a * b_factor
    constant = rate1 / denominator
    terms = []
    if order_a:
        terms.append("[A]" if order_a == 1 else f"[A]^{order_a}")
    if order_b:
        terms.append("[B]" if order_b == 1 else f"[B]^{order_b}")
    body = " ".join(terms)
    shown = f"rate = {num(constant)} {body}".rstrip()
    if changing == "B":
        if b1 is None:
            raise SolveServiceError("the changing concentration is missing")
        held = b1
    else:
        held = first
    power = "" if order == 1 else f"^{order}"
    if b1 is not None and b2 is not None:
        given = (
            f"experiment 1: [A] = {inp(a1)}, [B] = {inp(b1)}, rate = {inp(rate1)}",
            f"experiment 2: [A] = {inp(a2)}, [B] = {inp(b2)}, rate = {inp(rate2)}",
        )
    else:
        given = (
            f"experiment 1: [A] = {inp(a1)}, rate = {inp(rate1)}",
            f"experiment 2: [A] = {inp(a2)}, rate = {inp(rate2)}",
        )
    return verified(
        "Verified rate law",
        given,
        "Rate law",
        *stated("rate_law"),
        (
            f"order in {changing} = log({inp(rate2)} / {inp(rate1)}) / log({inp(second)} / "
            f"{inp(first)}) = {order}",
            f"k = rate1 / [{changing}]{power} = {inp(rate1)} / ({inp(held)}){power} = "
            f"{num(constant)}",
        ),
        shown,
        shown,
    )


def solve_arrhenius_two_point(intent: ChemistryIntent) -> ChemistryResult:
    message = "two-point Arrhenius needs two positive rates and temperatures"
    k1, t1, k2, t2 = (require(intent, key, positive=True, message=message) for key in _ARRHENIUS)
    if t1 == t2:
        raise SolveServiceError(message)
    energy = -GAS_R_J * math.log(k2 / k1) / (1 / t2 - 1 / t1)
    shown = f"Ea = {num(energy / 1000)} kJ/mol"
    return verified(
        "Verified two-temperature Arrhenius",
        (
            f"k1 = {inp(k1)}",
            f"T1 = {inp(t1)} K",
            f"k2 = {inp(k2)}",
            f"T2 = {inp(t2)} K",
        ),
        "Activation energy",
        *stated("arrhenius_two_point"),
        (
            f"Ea = −({const(GAS_R_J)})ln({inp(k2)} / {inp(k1)}) / (1/{inp(t2)} − 1/{inp(t1)})"
            f" = {num(energy)} J/mol",
        ),
        shown,
        shown,
    )


def _with(value: str, unit: str) -> str:
    return f"{value} {unit}" if unit else value


def solve_michaelis_menten(intent: ChemistryIntent) -> ChemistryResult:
    velocity = intent.params.get("v")
    maximum = intent.params.get("vmax")
    km = intent.params.get("km")
    substrate = intent.params.get("substrate")
    present = {
        "v": velocity,
        "Vmax": maximum,
        "Km": km,
        "S": substrate,
    }
    missing = [name for name, value in present.items() if value is None]
    if len(missing) != 1:
        raise SolveServiceError("Michaelis–Menten needs exactly one of v, Vmax, Km, and S missing")
    if any(value is not None and value < 0 for value in present.values()):
        raise SolveServiceError("Michaelis–Menten values cannot be negative")
    target = missing[0]
    rate = intent.units.get("rate", "")
    concentration = intent.units.get("concentration", "")
    if target == "v":
        if maximum is None or km is None or substrate is None or km + substrate == 0:
            raise SolveServiceError("Michaelis–Menten denominator is zero")
        value = maximum * substrate / (km + substrate)
        shown = f"v = {_with(num(value), rate)}"
        working = f"v = ({inp(maximum)})({inp(substrate)}) / ({inp(km)} + {inp(substrate)})"
    elif target == "Vmax":
        if velocity is None or km is None or substrate is None or substrate == 0:
            raise SolveServiceError("Michaelis–Menten cannot solve Vmax from these values")
        value = velocity * (km + substrate) / substrate
        shown = f"Vmax = {_with(num(value), rate)}"
        working = f"Vmax = ({inp(velocity)})({inp(km)} + {inp(substrate)}) / {inp(substrate)}"
    elif target == "Km":
        if velocity is None or maximum is None or substrate is None or velocity <= 0:
            raise SolveServiceError("Michaelis–Menten cannot solve Km from these values")
        if not maximum > velocity:
            raise SolveServiceError("Michaelis–Menten needs Vmax greater than v")
        value = substrate * (maximum - velocity) / velocity
        shown = f"Km = {_with(num(value), concentration)}"
        working = f"Km = ({inp(substrate)})({inp(maximum)} − {inp(velocity)}) / {inp(velocity)}"
    else:
        if velocity is None or maximum is None or km is None or velocity <= 0:
            raise SolveServiceError("Michaelis–Menten cannot solve S from these values")
        if not maximum > velocity:
            raise SolveServiceError("Michaelis–Menten needs Vmax greater than v")
        value = velocity * km / (maximum - velocity)
        shown = f"S = {_with(num(value), concentration)}"
        working = f"S = ({inp(velocity)})({inp(km)}) / ({inp(maximum)} − {inp(velocity)})"
    given = tuple(
        f"{name} = {_with(inp(amount), rate if name in {'v', 'Vmax'} else concentration)}"
        for name, amount in present.items()
        if amount is not None
    )
    return verified(
        "Verified Michaelis–Menten",
        given,
        target,
        *stated("michaelis_menten"),
        (working,),
        shown,
        shown,
    )
