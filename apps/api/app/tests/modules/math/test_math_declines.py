"""The maths decline helper: SymPy failures decline, programming errors raise in strict mode."""

from __future__ import annotations

import asyncio
import fractions
import logging
from collections import Counter
from collections.abc import Callable

import pytest
from sympy import Poly, Symbol, lambdify, sqrt, sympify
from sympy.polys.polyerrors import CoercionFailed, PolynomialError

from app.modules.math.solve.declines import (
    declines,
    is_programming_error,
    strict_declines,
    sympy_decline,
)

X = Symbol("x")
_LOGGER = "app.modules.math.solve.declines"


@pytest.fixture
def decline_counts(caplog) -> Callable[[], Counter[tuple[str, str]]]:
    """Every decline logs once at DEBUG with (where, exception type): count them back."""
    caplog.set_level(logging.DEBUG, logger=_LOGGER)

    def counts() -> Counter[tuple[str, str]]:
        return Counter(
            (str(record.args[0]), str(record.args[1]))
            for record in caplog.records
            if record.name == _LOGGER and isinstance(record.args, tuple)
        )

    return counts


@pytest.fixture(params=[True, False], ids=["strict", "production"])
def strict(request, monkeypatch) -> bool:
    monkeypatch.setenv("RECALL_STRICT_DECLINES", "1" if request.param else "0")
    return request.param


def _raise(error: BaseException) -> None:
    raise error


# Raised in our own code: a bug, which strict mode re-raises.
PROGRAMMING = [
    pytest.param(lambda: _raise(AttributeError("no attr")), AttributeError, id="AttributeError"),
    pytest.param(lambda: _raise(NameError("no name")), NameError, id="NameError"),
    pytest.param(
        lambda: _raise(UnboundLocalError("value")), UnboundLocalError, id="UnboundLocalError"
    ),
    pytest.param(lambda: dict[str, int]()["missing"], KeyError, id="KeyError"),
    pytest.param(lambda: _raise(ImportError("gone")), ImportError, id="ImportError"),
    pytest.param(
        lambda: _raise(ModuleNotFoundError("gone")), ModuleNotFoundError, id="ModuleNotFoundError"
    ),
    pytest.param(lambda: _raise(AssertionError("broken")), AssertionError, id="AssertionError"),
    pytest.param(lambda: None + 1, TypeError, id="TypeError"),  # type: ignore[operator]
    pytest.param(
        lambda: fractions.Fraction(object()),  # type: ignore[call-overload]
        TypeError,
        id="TypeError-via-stdlib",
    ),
]

# Maths that cannot be done here: declined in both modes.
MATHS = [
    pytest.param(lambda: _raise(ValueError("bad value")), ValueError, id="ValueError"),
    pytest.param(lambda: 1 / 0, ZeroDivisionError, id="ZeroDivisionError"),
    pytest.param(lambda: 10.0**400, OverflowError, id="OverflowError"),
    pytest.param(lambda: _raise(RecursionError("deep")), RecursionError, id="RecursionError"),
    pytest.param(lambda: _raise(NotImplementedError("no")), NotImplementedError, id="NotImpl"),
    pytest.param(lambda: [][0], IndexError, id="IndexError"),
    pytest.param(lambda: sympify("2x+"), Exception, id="SympifyError"),
    pytest.param(lambda: Poly(1 / X, X), PolynomialError, id="PolynomialError"),
    pytest.param(lambda: _raise(CoercionFailed("no")), CoercionFailed, id="CoercionFailed"),
    # TypeError and AttributeError raised inside SymPy: SymPy failing on the input.
    pytest.param(lambda: bool(X < 0), TypeError, id="TypeError-in-sympy"),
    pytest.param(lambda: sympify("x.foo"), AttributeError, id="AttributeError-in-sympy"),
    pytest.param(
        lambda: lambdify(X, sqrt(X), "math")("a"), TypeError, id="TypeError-in-lambdify-code"
    ),
]

# Never caught, in either mode.
PASS_THROUGH = [
    pytest.param(KeyboardInterrupt, id="KeyboardInterrupt"),
    pytest.param(SystemExit, id="SystemExit"),
    pytest.param(asyncio.CancelledError, id="CancelledError"),
    pytest.param(TimeoutError, id="TimeoutError"),
]


@pytest.mark.parametrize(("attempt", "error"), PROGRAMMING)
def test_declines_programming_error_raises_only_in_strict_mode(
    strict, attempt, error, decline_counts
) -> None:
    @declines(None)
    def wrapped() -> object:
        return attempt()

    if strict:
        with pytest.raises(error):
            wrapped()
        with pytest.raises(error), sympy_decline():
            attempt()
        assert not decline_counts()
    else:
        assert wrapped() is None
        with sympy_decline() as declined:
            attempt()
        assert declined
        assert sum(decline_counts().values()) == 2


@pytest.mark.parametrize(("attempt", "error"), MATHS)
def test_declines_maths_failure_declines_in_both_modes(
    strict, attempt, error, decline_counts
) -> None:
    @declines(False)
    def wrapped() -> object:
        return attempt()

    with pytest.raises(error):
        attempt()
    assert wrapped() is False
    with sympy_decline() as declined:
        attempt()
    assert declined
    assert sum(decline_counts().values()) == 2


@pytest.mark.parametrize("error", PASS_THROUGH)
def test_declines_base_exception_and_pool_timeout_pass_through(
    strict, error, decline_counts
) -> None:
    @declines(None)
    def wrapped() -> None:
        raise error

    with pytest.raises(error):
        wrapped()
    with pytest.raises(error), sympy_decline():
        raise error
    assert not decline_counts()


def test_declines_strict_mode_reads_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("RECALL_STRICT_DECLINES", "1")
    assert strict_declines()
    for value in ("0", "", "true"):
        monkeypatch.setenv("RECALL_STRICT_DECLINES", value)
        assert not strict_declines()
    monkeypatch.delenv("RECALL_STRICT_DECLINES")
    assert not strict_declines()


def test_declines_is_programming_error_classifies_by_raising_frame() -> None:
    def caught(attempt) -> BaseException:
        try:
            attempt()
        except Exception as exc:
            return exc
        raise AssertionError("did not raise")

    assert is_programming_error(caught(lambda: None + 1))  # type: ignore[operator]
    assert not is_programming_error(caught(lambda: bool(X < 0)))
    assert not is_programming_error(caught(lambda: sympify("x.foo")))
    assert not is_programming_error(caught(lambda: 1 / 0))
    assert not is_programming_error(caught(lambda: Poly(1 / X, X)))


def test_declines_counts_and_logs_each_decline(monkeypatch, caplog, decline_counts) -> None:
    monkeypatch.setenv("RECALL_STRICT_DECLINES", "1")

    @declines(None)
    def parse_twice() -> object:
        return sympify("2x+")

    def degree() -> int | None:
        with sympy_decline() as declined:
            value = Poly(1 / X, X).degree()
        return None if declined else value

    with caplog.at_level(logging.DEBUG, logger="app.modules.math.solve.declines"):
        assert parse_twice() is None
        assert parse_twice() is None
        assert degree() is None
        with sympy_decline("named.attempt"):
            _ = 1 / 0

    here = __name__ + "."
    counts = decline_counts()
    assert (
        counts[
            (
                here + "test_declines_counts_and_logs_each_decline.<locals>.parse_twice",
                "SympifyError",
            )
        ]
        == 2
    )
    assert (
        counts[
            (here + "test_declines_counts_and_logs_each_decline.<locals>.degree", "PolynomialError")
        ]
        == 1
    )
    assert counts[("named.attempt", "ZeroDivisionError")] == 1
    assert sum(counts.values()) == 4
    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 4
    assert all(record.levelno == logging.DEBUG for record in caplog.records)
    assert messages[2].startswith("maths decline in ")
    assert "degree: PolynomialError: " in messages[2]
    assert messages[3].startswith("maths decline in named.attempt: ZeroDivisionError: ")
    assert all(len(message) < 400 for message in messages)


def test_declines_log_message_is_short(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="app.modules.math.solve.declines"):
        with sympy_decline("long"):
            raise ValueError("y" * 5000)
    (record,) = caplog.records
    assert record.getMessage() == "maths decline in long: ValueError: " + "y" * 120


def test_declines_success_is_not_a_decline(decline_counts) -> None:
    @declines(None)
    def double(value: int) -> int:
        """Doubles."""
        return value * 2

    assert double(4) == 8
    assert double.__name__ == "double"
    assert double.__doc__ == "Doubles."
    with sympy_decline() as declined:
        _ = Poly(X**2, X).degree()
    assert not declined
    assert not decline_counts()


def test_declines_return_inside_the_block_and_default_after() -> None:
    def first(values: list[int]) -> int | None:
        with sympy_decline():
            return values[0]
        return None

    assert first([3]) == 3
    assert first([]) is None


def test_declines_refuses_a_mutable_default() -> None:
    defaults: list[object] = [[], {}, set()]
    for default in defaults:
        with pytest.raises(TypeError):
            declines(default)
    assert declines(())(lambda: [][0])() == ()
