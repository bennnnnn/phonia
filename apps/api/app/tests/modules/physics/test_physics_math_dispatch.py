"""Broad subject words never send a request through the wrong peer pipeline."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools import _build_verified_block as build_math_block
from app.modules.math.tools import extract_math_intent
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.services.subjects.dispatch import detect_subject

_SETTINGS = Settings(math_tools_enabled=True)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("range of 1,2,3,4", [1, 2, 3, 4]),
        ("find the range of 1, 2, 3, 4", [1, 2, 3, 4]),
        ("range of 1/2,3/2", [0.5, 1.5]),
        ("range of 1e3,3e3", [1000, 3000]),
        ("range of -.5,.5", [-0.5, 0.5]),
    ],
)
def test_statistical_range_stays_in_math(text: str, expected: list[float]) -> None:
    assert detect_subject(text) == "math"
    assert extract_physics_intent(text) is None
    intent = extract_math_intent(text)
    assert intent is not None and intent.kind == "statistics"
    assert intent.stats_op == "range" and intent.stats_numbers == expected
    block = build_math_block(intent, _SETTINGS)
    assert block is not None and block.canonical_answer is not None
    assert float(block.canonical_answer) == pytest.approx(max(expected) - min(expected))


@pytest.mark.parametrize("order", [1, 2, 3])
def test_function_derivatives_stay_in_math(order: int) -> None:
    primes = "'" * order
    text = f"f(x) = x^3 - 3x, find f{primes}(x)"
    assert detect_subject(text) == "math"
    assert extract_physics_intent(text) is None
    intent = extract_math_intent(text)
    assert intent is not None and intent.kind == "calculus"
    block = build_math_block(intent, _SETTINGS)
    assert block is not None
    assert block.canonical_answer == {1: "3 x^{2} - 3", 2: "6 x", 3: "6"}[order]


def test_force_symbol_routes_directly_to_physics() -> None:
    text = "find f for a .5 kg object with acceleration 2 m/s^2"
    assert detect_subject(text) == "physics"
    assert extract_math_intent(text) is None
    intent = extract_physics_intent(text)
    assert intent is not None and intent.kind == "force"
    assert intent.physics_params == {"m": 0.5, "a": 2.0}
    block = build_verified_physics_block(intent, _SETTINGS)
    assert block is not None and block.canonical_answer == "1 N"


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("What is 2 to the power of 3?", "8"),
        ("what is the third power of 5?", "125"),
        ("Find the third power of 5", "125"),
        ("2 raised to the third power", "8"),
        ("Show steps: 2 to the power of 3", "8"),
    ],
)
def test_complete_math_power_request_beats_physics_keyword(text: str, answer: str) -> None:
    assert extract_physics_intent(text) is None
    assert detect_subject(text) == "math"
    intent = extract_math_intent(text)
    assert intent is not None and intent.kind == "arithmetic"
    block = build_math_block(intent, _SETTINGS)
    assert block is not None and block.canonical_answer == answer


@pytest.mark.parametrize("symbol", ["n", "W", "N", "J"])
def test_symbolic_power_request_is_not_stolen_by_physics_unit_symbols(symbol: str) -> None:
    text = f"What is the 3rd power of {symbol}?"
    assert extract_physics_intent(text) is None
    assert detect_subject(text) == "math"
    intent = extract_math_intent(text)
    assert intent is not None and intent.kind == "arithmetic"
    assert intent.expr == f"{symbol.lower()}^3"
    assert intent.school_op == "symbolic_power"
    block = build_math_block(intent, _SETTINGS)
    assert block is not None
    assert block.canonical_answer == f"{symbol.lower()}^{{3}}"
    assert block.direct_reply is not None and "**Power notation formula**" in block.direct_reply


def test_symbolic_power_steps_explain_the_exponent_before_the_answer() -> None:
    text = "Show steps: the third power of x"
    intent = extract_math_intent(text)
    assert intent is not None and intent.school_op == "symbolic_power"
    block = build_math_block(intent, _SETTINGS)
    assert block is not None

    reply = maybe_direct_math_reply(block, text)

    assert reply is not None
    assert "$x^3 = x \\times x \\times x = x^{3}$" in reply
    assert reply.rstrip().endswith("```answer\nx^{3}\n```")


def test_physics_data_does_not_answer_a_separate_exponent_request() -> None:
    text = "A motor does 100 J of work in 5 s. Find 2 raised to the third power."
    assert extract_physics_intent(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "A 60 W bulb runs for 2 hours. How much energy does it use?",
        "A 2 kg object accelerates at 3 m/s². What force acts on it?",
    ],
)
def test_complete_physics_request_still_beats_incidental_math(text: str) -> None:
    assert detect_subject(text) == "physics"
    assert extract_physics_intent(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "find f for a 1/2 kg object with acceleration 2 m/s^2",
        "find f for a 1.2.3 kg object with acceleration 2 m/s^2",
        "range of a projectile launched at 1,00 m/s at 30 degrees",
        "range of a projectile launched at 1e+ m/s at 30 degrees",
    ],
)
def test_malformed_physics_never_falls_through_to_math(text: str) -> None:
    assert extract_physics_intent(text) is None
    assert extract_math_intent(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "kinetic energy of a 1/2 kg object at 2 m/s, find f''(x)",
        "a 2 kg ball at 3 m/s hits a 1 kg ball elastically; find f''(x)",
        "kinetic energy of a 1/2 kg object at 2 m/s; range of 1,2,3,4",
    ],
)
def test_mixed_subject_fragments_fail_closed(text: str) -> None:
    assert detect_subject(text) == "physics"
    assert extract_physics_intent(text) is None
