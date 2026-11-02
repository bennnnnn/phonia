"""A definite integral's closed form is verified only once a numeric quadrature agrees with it."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sympy import Abs, Integral, Rational, S, Symbol, exp, log, oo, pi, sin, sqrt

from app.modules.math.calculus_applications import (
    arc_length,
    area_between_curves,
    volume_of_revolution,
)
from app.modules.math.formulas import average_value
from app.modules.math.schemas import MathIntent
from app.modules.math.solve import SolveServiceError, calculus, definite_integral
from app.modules.math.tools.block.integrals import _fundamental_theorem_working

_API_ROOT = Path(__file__).resolve().parents[4]
x = Symbol("x")


def _closed_form(monkeypatch: pytest.MonkeyPatch, definite: Any, antiderivative: Any) -> None:
    """SymPy's definite integral answers ``definite``; its antiderivative ``antiderivative``."""
    real = calculus.integrate

    def fake(integrand: Any, *limits: Any) -> Any:
        if isinstance(limits[0], tuple):
            return definite
        return real(integrand, *limits) if antiderivative is None else antiderivative

    monkeypatch.setattr(calculus, "integrate", fake)


# SymPy 1.14's route through a definite integral follows the string-hash seed; under these
# seeds it gave ∫₀¹ (9ˣ - 3ˣ) dx = -76/ln 3 before the check.
@pytest.mark.parametrize("seed", ["3", "6", "8", "11"])
def test_definite_integral_is_right_under_every_hash_seed(seed: str) -> None:
    code = (
        "from app.modules.math.solve import integrate_definite;"
        "print(integrate_definite('9^x - 3^x', 'x', '0', '1').result)"
    )
    run = subprocess.run(  # noqa: S603 - fixed argv: this interpreter and a literal script
        [sys.executable, "-c", code],
        capture_output=True,
        check=True,
        cwd=_API_ROOT,
        env={**os.environ, "PYTHONHASHSEED": seed},
        text=True,
        timeout=120,
    )
    assert run.stdout.strip() == "2/log(3)"


@pytest.mark.parametrize(
    "integrand, low, high, expected",
    [
        (x**2, 0, 3, S(9)),
        (exp(-(x**2)), -oo, oo, sqrt(pi)),
        (1 / sqrt(x), 0, 1, S(2)),
        (log(x), 0, 1, S(-1)),
        (sin(x) / x, 0, oo, pi / 2),
        (Abs(x), -1, 2, Rational(5, 2)),
        (1 / x, 1, oo, oo),
        (Symbol("a") * x, 0, 1, Symbol("a") / 2),
    ],
)
def test_definite_integral_keeps_a_right_closed_form(
    integrand: Any, low: Any, high: Any, expected: Any
) -> None:
    assert definite_integral(integrand, x, low, high) == expected


@pytest.mark.parametrize(
    "integrand, low, high",
    [(sin(x) / x, 0, oo), (Abs(x), -1, 2), (Symbol("a") * x, 0, 1), (1 / x, -1, 1)],
)
def test_quadrature_does_not_judge_what_it_cannot_resolve(
    integrand: Any, low: Any, high: Any
) -> None:
    """An oscillating tail, a kink, another symbol or a pole: no verdict, the closed form stands."""
    assert calculus._quadrature(integrand, x, S(low), S(high)) is None


def test_definite_integral_rebuilds_a_contradicted_closed_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _closed_form(monkeypatch, -76 / log(3), None)
    assert definite_integral(9**x - 3**x, x, 0, 1) == 2 / log(3)


@pytest.mark.parametrize("antiderivative", [Integral(x**2, x), x**3])
def test_definite_integral_refuses_a_closed_form_nothing_confirms(
    monkeypatch: pytest.MonkeyPatch, antiderivative: Any
) -> None:
    """No antiderivative, or one that disagrees too: no number reaches the answer card."""
    _closed_form(monkeypatch, S(5), antiderivative)
    with pytest.raises(SolveServiceError, match="numeric check"):
        definite_integral(x**2, x, 0, 3)


def _ftc_working() -> object:
    intent = MathIntent(
        kind="calculus",
        operation="integrate",
        expr="x^2",
        integral_lower="0",
        integral_upper="3",
        variable="x",
    )
    real_x = Symbol("x", real=True)
    working = _fundamental_theorem_working(intent, real_x**2, "I")
    if working is None:
        raise SolveServiceError("no working")
    return working


@pytest.mark.parametrize(
    "answer",
    [
        lambda: average_value("x^2", "x", "0", "3"),
        lambda: area_between_curves("x^2 + 1", "0", "0", "3"),
        lambda: arc_length("x^2", "0", "3"),
        lambda: volume_of_revolution("x^2", "0", "3"),
        lambda: volume_of_revolution("x^2", "0", "3", axis="y"),
        _ftc_working,
    ],
)
def test_every_definite_integral_answer_goes_through_the_check(
    monkeypatch: pytest.MonkeyPatch, answer: Callable[[], object]
) -> None:
    """With every closed form contradicted, no answer or worked line uses one."""
    _closed_form(monkeypatch, S(-5), Integral(x, x))
    with pytest.raises(SolveServiceError):
        answer()
