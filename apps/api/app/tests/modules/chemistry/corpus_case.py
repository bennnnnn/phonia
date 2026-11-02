"""One chemistry corpus row and the constants its answers are worked with.

Expected values are computed here from the textbook formula with IUPAC abridged atomic
weights and CODATA constants, never read back from the solver.
"""

from __future__ import annotations

from dataclasses import dataclass

# IUPAC abridged standard atomic weights, the ones a chemistry class uses.
H, C, O, NA, S, CL, CU = (1.008, 12.011, 15.999, 22.990, 32.06, 35.45, 63.546)  # noqa: E741
H2O = 2 * H + O
CO2 = C + 2 * O
O2 = 2 * O
NACL = NA + CL
AVOGADRO = 6.02214076e23
FARADAY = 96485.33212
R_GAS = 8.314462618  # J/(mol·K)
R_ATM = 0.082057366  # L·atm/(mol·K)


@dataclass(frozen=True, slots=True)
class Case:
    question: str
    # The answered value and the unit printed after it; None declines or checks text only.
    value: float | None = None
    unit: str = ""
    # A label the value is read after ("[HI]"), when the answer lists several values.
    label: str = ""
    # Text the answer must contain (a formula, a shape, a limiting reagent).
    text: str = ""


def q(question: str, value: float, unit: str = "", *, label: str = "", text: str = "") -> Case:
    return Case(question, value, unit, label, text)


def says(question: str, text: str) -> Case:
    return Case(question, text=text)
