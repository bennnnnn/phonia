"""Reaction-plus-braking stops stay on the physics solver."""

from __future__ import annotations

from app.core.config import Settings
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
    maybe_direct_physics_reply,
    needs_physics,
)

_SETTINGS = Settings(math_tools_enabled=True)

_REACTION_STOP = (
    "A car travels at a constant speed of 15 m/s. The driver takes 1.0 second "
    "to react before applying the brakes. Once applied, the brakes slow the car "
    "to a stop over 3.0 seconds. What is the total stopping distance?"
)
_BRAKE_ONLY = "A car at 15 m/s slows to a stop in 3.0 seconds. How far does it travel?"
_CONSTANT_SPEED = "A car travels at 15 m/s for 3 s. How far does it travel?"


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


def _reply(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    if block is None:
        return None
    return maybe_direct_physics_reply(block, text)


def test_reaction_braking_stop_is_verified() -> None:
    assert needs_physics(_REACTION_STOP)
    intent = extract_physics_intent(_REACTION_STOP)
    assert intent is not None
    assert intent.physics_op == "stopping_distance"
    assert intent.physics_params == {"v": 15.0, "t_react": 1.0, "t_brake": 3.0}
    reply = _reply(_REACTION_STOP)
    assert reply is not None
    assert "15" in reply
    assert "22.5" in reply
    assert "37.5" in reply
    assert "-5" in reply
    assert "```answer\n37.5\\,\\mathrm{m}\n```" in reply


def test_brake_to_stop_is_not_constant_speed() -> None:
    intent = extract_physics_intent(_BRAKE_ONLY)
    assert intent is not None
    assert intent.physics_op == "suvat_distance"
    assert _answer(_BRAKE_ONLY) == "22.5 m"


def test_constant_speed_distance_stays_a_rate() -> None:
    intent = extract_physics_intent(_CONSTANT_SPEED)
    assert intent is not None
    assert intent.physics_op == "rate_distance"
    assert _answer(_CONSTANT_SPEED) == "45 m"
