"""Distance-speed-time quantities preserve their actual supplied units."""

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent


@pytest.mark.parametrize(
    "prompt, answer",
    [
        ("Find the average speed for 100 m in 20 s.", "5 m/s"),
        ("A car travels 180 meters in 12 seconds. What is its average speed?", "15 m/s"),
        ("Find the average speed for 20 s over 100 m.", "5 m/s"),
        ("average speed 120 km in 2 hours", "60 km/h"),
        ("average speed 100 cm in 20 seconds", "5 cm/s"),
        ("average speed 100 feet in 20 minutes", "5 ft/min"),
        ("average speed .5 m in 2 s", "0.25 m/s"),
        ("average speed 0.5 m in 2 s", "0.25 m/s"),
        ("average speed 1.5 m in .5 s", "3 m/s"),
        ("average speed +.5 m in 2 s", "0.25 m/s"),
        # Asked for in another unit, it is converted rather than declined.
        ("Find the average speed for 100 m in 20 s in km/h.", "18 km/h"),
    ],
)
def test_rate_answer_retains_supplied_units(prompt: str, answer: str) -> None:
    intent = extract_physics_intent(prompt)
    assert intent is not None and intent.kind == "kinematics"
    block = build_verified_physics_block(intent, Settings())
    assert block is not None and block.canonical_answer == answer


@pytest.mark.parametrize(
    "prompt",
    [
        "Find the average speed for 100 kg in 20 s.",
        "Find the average speed for 100 m in 20 bananas.",
        "Find the average speed for 100 m/s in 20 s.",
        "Find the average speed for 100 m in 20 s and then 50 m in 10 s.",
        "Find the average speed for 100 m in 20 s and tell me a joke.",
        "average speed .5 m in -.5 s",
        "average speed -.5 m in 2 s",
    ],
)
def test_invalid_or_compound_rate_request_fails_closed(prompt: str) -> None:
    assert extract_physics_intent(prompt) is None


def _reply(prompt: str) -> str:
    from app.modules.physics.direct import format_direct_physics_working

    intent = extract_physics_intent(prompt)
    assert intent is not None
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    reply = format_direct_physics_working(block)
    assert reply is not None
    return reply


# 2026-11-01: "25m/s … cover 5km" substituted 5 km over 25 m/s while the solver worked from
# 5000 m. The substitution shows the numbers the rate was worked from, so the given's own line
# carries the conversion first.
@pytest.mark.parametrize(
    "prompt, given, substitution",
    [
        (
            "A bus is moving in a straight line at a speed of 25m/s. What time does the bus "
            "take to cover 5km?",
            r"$d = 5\,\mathrm{km} \times 1000 = 5000\,\mathrm{m}$",
            r"$t = \frac{5000\,\mathrm{m}}{25\,\mathrm{m/s}}$",
        ),
        (
            "A train travels at 72 km/h for 30 minutes. How far does it go?",
            r"$t = 30\,\mathrm{min} \times 60 = 1800\,\mathrm{s}$",
            r"$d = 20\,\mathrm{m/s} \times 1800\,\mathrm{s}$",
        ),
    ],
)
def test_mixed_units_are_converted_before_they_are_substituted(
    prompt: str, given: str, substitution: str
) -> None:
    reply = _reply(prompt)
    assert given in reply
    assert substitution in reply


def test_units_that_agree_are_worked_as_written() -> None:
    reply = _reply("A car travels 150 km in 2 h. What is its average speed?")
    assert r"$v = \frac{150\,\mathrm{km}}{2\,\mathrm{h}}$" in reply
    assert r"\times" not in reply
