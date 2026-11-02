"""Linear drag, quadratic drag, Stokes terminal speed, and the road formulas."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.extract import extract_physics_intent, needs_physics
from app.modules.physics.prompt import build_physics_augmentation
from app.tests.modules.physics.support import build_verified_physics_block

_DRAG_PROBLEM = (
    "A particle of mass m is dropped from rest in a fluid. As it falls under gravity (g), "
    "it experiences a velocity-dependent drag force F_drag = -kv, where k is a positive "
    "constant and v(t) is the downward velocity at time t.\n"
    "1. Set up the differential equation using Newton's Second Law and solve for v(t) "
    "as an explicit function of time.\n"
    "2. Determine the terminal velocity v_T as t → ∞.\n"
    "3. Verify what v(t) reduces to if there is no fluid resistance (k → 0), via series "
    "or limits. It must match classical free fall v = gt (downward positive)."
)


def test_digit_free_linear_drag_is_physics() -> None:
    text = "A particle of mass m is dropped from rest. The drag force is F = -kv. Solve v(t)."
    assert needs_physics(text) is True
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "linear_drag_fall"


def test_textbook_drag_block_has_the_three_results() -> None:
    intent = extract_physics_intent(_DRAG_PROBLEM)
    assert intent is not None
    assert intent.physics_op == "linear_drag_fall"
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    text = block.text
    assert r"m\frac{dv}{dt}=mg-kv" in text
    assert r"v(t)=\frac{mg}{k}\left(1-e^{-(k/m)t}\right)" in text
    assert r"v_{T}=\frac{mg}{k}" in text
    assert r"\lim_{k\to 0}v(t)=gt" in text
    assert "I couldn't automatically verify" not in text


@pytest.mark.asyncio
async def test_textbook_drag_prompt_is_a_verified_block() -> None:
    note, verified, failed = await build_physics_augmentation(
        _DRAG_PROBLEM, Settings(math_tools_enabled=True)
    )
    assert failed is False
    assert verified is not None
    assert note is not None
    assert r"v(t)=\frac{mg}{k}\left(1-e^{-(k/m)t}\right)" in note
    assert r"v_{T}=\frac{mg}{k}" in note
    assert r"\lim_{k\to 0}v(t)=gt" in note
    assert "I couldn't automatically verify" not in note


def test_numeric_linear_drag_at_four_seconds() -> None:
    text = (
        "A 2 kg particle is dropped from rest. F = -kv with k = 0.5 kg/s. "
        "Find the terminal velocity and the speed after 4 s."
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "39.2 m/s" in (block.canonical_answer or "")
    assert "24.8 m/s" in (block.canonical_answer or "")


def test_upward_linear_drag_at_launch_is_the_launch_speed() -> None:
    text = (
        "A 0.5 kg ball is thrown upward at 20 m/s. F = -kv with k = 0.2 kg/s. Find v(t) at t = 0 s."
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "linear_drag_upward"
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "v(t) = 20 m/s" in (block.canonical_answer or "")


def test_quadratic_drag_terminal_speed() -> None:
    text = (
        "A 2 kg particle falls from rest with quadratic drag F = -b v^2, b = 0.25 kg/m. "
        "Find the terminal velocity."
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "quadratic_drag_fall"
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "8.86 m/s" in (block.canonical_answer or "")


def test_stokes_terminal_velocity() -> None:
    text = (
        "Find the terminal velocity of a sphere of radius 2 mm and density 2500 kg/m^3 "
        "falling in a fluid of density 1000 kg/m^3 and viscosity 0.1 Pa*s."
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "stokes_terminal_velocity"
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "0.131 m/s" in (block.canonical_answer or "")


def test_stokes_force_stays_a_force() -> None:
    text = (
        "Using Stokes drag, find force for viscosity 0.2 Pa*s, sphere radius "
        "0.01 m, and speed 3 m/s."
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "stokes_drag"


def test_banked_frictionless_speed() -> None:
    text = "A frictionless banked curve has radius 50 m at 20 degrees. Find the speed."
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "banked_speed"
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "13.4 m/s" in (block.canonical_answer or "")


def test_banked_angle_from_speed() -> None:
    text = (
        "A motorcycle takes a frictionless banked curve of radius 80 m at 20 m/s. Find the angle."
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "banked_angle"
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "26.9" in (block.canonical_answer or "") or "27" in (block.canonical_answer or "")


def test_level_curve_max_speed() -> None:
    text = (
        "A car rounds a flat curve of radius 50 m. The coefficient of static friction "
        "is 0.4. Find the maximum speed without skidding."
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "level_curve_speed"
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "14 m/s" in (block.canonical_answer or "")


def test_contact_speed_at_the_top() -> None:
    text = (
        "A bucket of water swings in a vertical circle of radius 0.8 m. "
        "Find the minimum speed at the top."
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "contact_speed"
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "2.8 m/s" in (block.canonical_answer or "")


def test_free_fall_without_drag_stays_kinematics() -> None:
    text = "A ball is dropped from 20 m. How long until it hits the ground?"
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.kind == "kinematics"


def test_drag_fall_time_is_not_free_fall() -> None:
    text = "A ball is dropped from 20 m. F = -kv. How long until it hits the ground?"
    assert extract_physics_intent(text) is None


def test_dragging_a_block_is_not_fluid_drag() -> None:
    text = "Find the tension in a string dragging a 5 kg block along a horizontal table."
    intent = extract_physics_intent(text)
    assert intent is None or intent.physics_op not in {
        "linear_drag_fall",
        "linear_drag_upward",
        "quadratic_drag_fall",
    }


def test_nonpositive_drag_coefficient_is_not_a_template() -> None:
    text = "A 2 kg particle is dropped from rest. F = -kv with k = 0 kg/s. Find v(t)."
    assert extract_physics_intent(text) is None


def test_just_completes_the_loop_is_not_contact_speed() -> None:
    text = "A car just completes a loop-the-loop of radius 10 m. Find the minimum speed."
    intent = extract_physics_intent(text)
    assert intent is None or intent.physics_op != "contact_speed"
