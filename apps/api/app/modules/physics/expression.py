"""Physics' notation for the shared expression evaluator: its constants and its numbers.

The evaluator is ``services.law_binding.expression``; a physics expression may name the
constants below, and its substitution prints a value with the figures the user wrote.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.modules.physics.constants import (
    BIG_G,
    BOHR_RADIUS,
    BOLTZMANN,
    COULOMB_K,
    ELECTRON_MASS,
    ELEMENTARY_CHARGE,
    EPSILON_0,
    GAS_CONSTANT,
    HBAR,
    MU_0,
    PLANCK_H,
    RYDBERG,
    SPEED_OF_LIGHT,
    STEFAN_BOLTZMANN,
)
from app.modules.physics.display import latex_given
from app.services.law_binding import expression as _shared
from app.services.law_binding.expression import ExpressionError, Notation, parse

__all__ = ["PHYSICS_NOTATION", "ExpressionError", "evaluate", "parse", "to_latex"]

# Physical constants by the name an expression uses, with the symbol the
# formula shows. The values are ``physics.constants`` (CODATA via Pint).
PHYSICS_NOTATION = Notation(
    constants={
        "mu_0": (MU_0, r"\mu_0"),
        "epsilon_0": (EPSILON_0, r"\varepsilon_0"),
        "k_e": (COULOMB_K, "k_e"),
        "G_grav": (BIG_G, "G"),
        "h_planck": (PLANCK_H, "h"),
        "c_light": (SPEED_OF_LIGHT, "c"),
        "e_charge": (ELEMENTARY_CHARGE, "e"),
        "m_e": (ELECTRON_MASS, "m_e"),
        "R_gas": (GAS_CONSTANT, "R"),
        "k_B": (BOLTZMANN, "k_B"),
        "hbar": (HBAR, r"\hbar"),
        "R_inf": (RYDBERG, r"R_\infty"),
        "a_0": (BOHR_RADIUS, "a_0"),
        "sigma": (STEFAN_BOLTZMANN, r"\sigma"),
    },
    number=latex_given,
)


def evaluate(expression: str, values: Mapping[str, float]) -> float:
    """The number a physics expression gives. A domain error is a ValueError."""
    return _shared.evaluate(expression, values, PHYSICS_NOTATION)


def to_latex(
    expression: str,
    symbols: Mapping[str, str],
    values: Mapping[str, float] | None = None,
) -> str:
    """A physics expression typeset: with the law's symbols, or with ``values`` plugged in.

    An angle (a name that starts with ``angle``) is in radians for the arithmetic and is
    shown in degrees, as the student wrote it.
    """
    angles = frozenset(name for name in values or () if name.startswith("angle"))
    return _shared.to_latex(expression, symbols, values, notation=PHYSICS_NOTATION, degrees=angles)
