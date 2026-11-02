"""Regression matrix for the exploratory physics audit of 20 subject areas."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.catalog import CATALOG
from app.modules.physics.law_titles import law_heading
from app.modules.physics.schemas import PhysicsIntent
from app.services.workout import as_formula_heading
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
    maybe_direct_physics_reply,
)

_SETTINGS = Settings(math_tools_enabled=True)
_HEADINGS = ("**Given**", "**Required**", "**Formula**", "**Substitution**", "**Answer**")


@pytest.mark.parametrize(
    "query,kind,op",
    [
        (
            "A stone starts 60 m high with an initial velocity of 5 m/s downward. Find its impact speed.",
            "kinematics",
            "speed",
        ),
        (
            "A train slows from 20 m/s to rest at -4 m/s^2. Find the stopping time.",
            "suvat",
            "suvat_time",
        ),
        (
            "Velocity changes from 10 m/s to 30 m/s in 5 s. Find the acceleration.",
            "suvat",
            "suvat_acceleration",
        ),
        ("A machine does 3600 J of work in 12 s. Find its power.", "energy", "power"),
        (
            "A projectile is launched at 20 m/s at 35 degrees. Find its range.",
            "projectile",
            "range",
        ),
        (
            "A 2 kg cart at 6 m/s sticks together with a 4 kg cart at rest. Find the final velocity.",
            "momentum",
            "final_velocity",
        ),
        (
            "Find the coefficient of friction that just prevents sliding on a 25 degree incline.",
            "friction",
            "friction_coefficient",
        ),
        (
            "Find the minimum horizontal force needed to move a 12 kg block if mu = 0.30.",
            "friction",
            "minimum_force",
        ),
        (
            "A wheel rotates at 120 rpm. Find its angular velocity in rad/s.",
            "circular",
            "angular_velocity",
        ),
        (
            "A 0.5 kg mass moves in a circle with omega = 4 rad/s and radius 2 m. Find the centripetal force.",
            "circular",
            "centripetal_force",
        ),
        (
            "A spring with spring constant 200 N/m is stretched by 0.1 m. Find the force.",
            "spring",
            "spring_force",
        ),
        ("A 12 V battery drives a current of 3 A. Find the resistance.", "circuit", "resistance"),
        (
            "A 30 kg child sits 2 m from the pivot of a seesaw. Where should a 20 kg child sit to balance it?",
            "torque",
            "moment_balance",
        ),
        (
            "A 15 N force produces 6 N m of torque. Find the perpendicular lever arm.",
            "torque",
            "lever_arm",
        ),
        (
            "Two clockwise torques of 8 N m and 5 N m act against a 20 N m counterclockwise torque. Find net torque.",
            "torque",
            "net_torque",
        ),
        (
            "A converging lens has focal length 10 cm and an object is 30 cm away. Find image distance.",
            "optics",
            "image_distance",
        ),
        (
            "Light travels at 2.0e8 m/s in glass. Find the refractive index.",
            "optics",
            "refractive_index",
        ),
        (
            "A concave mirror has focal length 15 cm and object distance 45 cm. Find image distance.",
            "optics",
            "image_distance",
        ),
        ("A wave has wavelength 2 m and frequency 5 Hz. Find its speed.", "waves", "wave_speed"),
        (
            "How much heat is needed to raise 2 kg of water by 10 C if c = 4200 J/(kg C)?",
            "thermal",
            "heat_energy",
        ),
        (
            "How much heat is needed to raise 0.5 kg of aluminium by 40 C if c = 900 J/(kg C)?",
            "thermal",
            "heat_energy",
        ),
        (
            "Find escape velocity for a planet with M = 5.97e24 kg and R = 6.37e6 m.",
            "gravitation",
            "escape_velocity",
        ),
        (
            "Find the gravitational attraction between two 1000 kg satellites 100 m apart.",
            "gravitation",
            "gravitational_force",
        ),
        ("A sample has mass 12 kg and volume 0.004 m^3. Find its density.", "fluids", "density"),
        (
            "Find angular momentum when I = 3 kg m^2 and omega = 5 rad/s.",
            "rotation",
            "angular_momentum",
        ),
        (
            "Find rotational kinetic energy when I = 2 kg m^2 and omega = 6 rad/s.",
            "rotation",
            "rotational_kinetic_energy",
        ),
        (
            "A proton moves at 2e6 m/s perpendicular to a 0.1 T magnetic field. Find the force.",
            "magnetism",
            "magnetic_force_charge",
        ),
        ("A 1.5 m cable lengthens by 3 mm. Find the strain.", "materials", "strain"),
        (
            "An 80 g sample has a half-life of 5 years. How much remains after 15 years?",
            "modern",
            "half_life_remaining",
        ),
        ("Find the mass energy of 0.002 kg using E = mc^2.", "modern", "mass_energy"),
        ("Find photon energy for wavelength 500 nm.", "modern", "photon_energy"),
        (
            "A 5 kg block slides down a frictionless 25 degree incline. Find acceleration.",
            "friction",
            "incline_acceleration",
        ),
        (
            "A charge of 5 microcoulombs moves at 1000 m/s perpendicular to a 0.2 T magnetic field. Find the force.",
            "magnetism",
            "magnetic_force_charge",
        ),
        (
            "Find the force on a 4 kg object accelerating at 3 meters per second squared.",
            "force",
            "net_force",
        ),
        (
            "A force of 20 N acts over 4 m squared. Find the pressure.",
            "fluids",
            "pressure_from_force",
        ),
    ],
)
def test_audit_prompts_are_verified_instant_structured_physics(
    query: str, kind: str, op: str
) -> None:
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    assert (intent.kind, intent.physics_op) == (kind, op)
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    assert "verified law's heading" in verified.text
    assert "show its universal/base equation first" in verified.text
    reply = maybe_direct_physics_reply(verified, query)
    assert reply is not None
    assert reply.count("```answer") == 1
    # The law's own name heads its formulas, in the Formula slot.
    read = as_formula_heading(reply)
    assert [read.index(heading) for heading in _HEADINGS] == sorted(
        read.index(heading) for heading in _HEADINGS
    )
    assert f"**{law_heading(CATALOG[op].law_name)}**  \n" in reply


def test_every_supported_physics_operation_has_a_named_governing_law() -> None:
    assert all(
        spec.law_name.strip() and spec.law_name != "Physics formula" for spec in CATALOG.values()
    )
    assert all(spec.result_symbol.strip() for spec in CATALOG.values())


def test_named_base_law_keeps_the_equivalent_form_used_for_substitution() -> None:
    query = "power dissipated by a 4 ohm resistor carrying 3 A"
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    reply = maybe_direct_physics_reply(verified, query)
    assert reply is not None
    assert "**Electrical power formula**  \n$P = VI$" in reply
    assert "— the same law for these quantities" in reply
    assert "$P = I^2 R$" in reply
    assert "**Substitution**  \n$P = 3^{2} \\times 4$" in reply


def test_identical_base_law_is_not_repeated_as_an_equivalent_form() -> None:
    query = "a 5 kg mass accelerates at 2 m/s^2, what is the net force"
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    reply = maybe_direct_physics_reply(verified, query)

    assert reply is not None
    assert "$F = ma$" in reply
    assert "— the same law for these quantities" not in reply


def test_numbered_givens_and_degree_units_use_mathematical_notation() -> None:
    query = "a 3 N force east and a 4 N force north, what is the resultant"
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    reply = maybe_direct_physics_reply(verified, query)

    assert reply is not None
    assert "$F_1 = 3\\,\\mathrm{N}$" in reply
    assert "$F_2 = 4\\,\\mathrm{N}$" in reply
    assert "$\\theta = 90^\\circ$" in reply


def test_negative_wavelength_is_never_verified() -> None:
    query = "A wave has wavelength -2 m and frequency 5 Hz. Find speed."
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    assert build_verified_physics_block(intent, _SETTINGS) is None


@pytest.mark.parametrize(
    "query,expected",
    [
        (
            "A proton moves at 2e6 m/s perpendicular to a 0.1 T magnetic field. Find the force.",
            "3.2 × 10⁻¹⁴ N (field perpendicular to the motion)",
        ),
        (
            "A charge of 5 microcoulombs moves at 1000 m/s perpendicular to a 0.2 T magnetic field. Find the force.",
            "0.001 N (field perpendicular to the motion)",
        ),
        (
            "Two clockwise torques of 8 N m and 5 N m act against a 20 N m counterclockwise torque. Find net torque.",
            "7 N·m (counterclockwise)",
        ),
    ],
)
def test_small_and_directional_results_keep_meaning(query: str, expected: str) -> None:
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    assert verified.canonical_answer == expected


@pytest.mark.parametrize(
    "query,find_line,law_name,base_formula,rearranged_formula,substitution_line",
    [
        (
            "A 15 N force produces 6 N m of torque. Find the perpendicular lever arm.",
            "$d$",
            "Torque formula",
            r"$\tau = Fd\sin(\theta)$",
            r"$d = \frac{\tau}{F}$",
            r"$d = \frac{6}{15}$",
        ),
        (
            "A converging lens has focal length 10 cm and an object is 30 cm away. Find image distance.",
            "$v$",
            "Thin-lens and mirror equation",
            r"$\frac{1}{f} = \frac{1}{u} + \frac{1}{v}$",
            r"$v = \frac{uf}{u - f}$",
            # Given in cm, the working stays in cm.
            r"$v = \frac{30 \times 10}{30 - 10}$",
        ),
        (
            "A 30 kg child sits 2 m from the pivot of a seesaw. Where should a 20 kg child sit to balance it?",
            "$d_2$",
            "Principle of moments",
            r"$F_1d_1 = F_2d_2$",
            r"$d_2 = \frac{m_1 d_1}{m_2}$",
            r"$d_2 = \frac{30 \times 2}{20}$",
        ),
        (
            "A 50 N downward force acts 2 m to the left of a pivot. "
            "What downward force 4 m to the right balances the lever?",
            "$F_2$",
            "Principle of moments",
            r"$F_1d_1 = F_2d_2$",
            r"$F_2 = \frac{F_1 d_1}{d_2}$",
            r"$F_2 = \frac{50 \times 2}{4}$",
        ),
        (
            "a 3 N force east and a 4 N force north, what is the resultant",
            "$R$",
            "Vector addition and components",
            r"$R = \sqrt{F_1^2 + F_2^2 + 2F_1F_2\cos\phi}$",
            None,
            r"$R = \sqrt{3^{2} + 4^{2} + 2 \times 3 \times 4\cos(90^\circ)}$",
        ),
    ],
)
def test_worked_layout_names_the_requested_unknown(
    query: str,
    find_line: str,
    law_name: str,
    base_formula: str,
    rearranged_formula: str | None,
    substitution_line: str,
) -> None:
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    reply = maybe_direct_physics_reply(verified, query)
    assert reply is not None
    assert f"**Required**  \n{find_line}" in reply
    assert f"**{law_heading(law_name)}**  \n" in reply
    assert base_formula in reply
    if rearranged_formula is not None:
        # Solving for the unknown is a step of its own, over the rearranged formula.
        assert f"Solve for {find_line}  \n{rearranged_formula}" in reply
        assert "rearranged for" not in reply
    assert f"**Substitution**  \n{substitution_line}" in reply


def test_impact_speed_uses_height_formula_and_scientific_givens_stay_readable() -> None:
    query = "A stone starts 60 m high with an initial velocity of 5 m/s downward. Find its impact speed."
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    reply = maybe_direct_physics_reply(verified, query)
    assert reply is not None
    assert r"$v_{impact}$" in reply
    assert r"$v_{impact} = \sqrt{v_0^2 + 2gh_0}$" in reply
    assert r"$v_{impact} = \sqrt{(-5)^{2} + 2 \times 9.81 \times 60}$" in reply

    planet = "Find escape velocity for a planet with M = 5.97e24 kg and R = 6.37e6 m."
    planet_intent = extract_physics_intent(planet)
    assert isinstance(planet_intent, PhysicsIntent)
    planet_verified = build_verified_physics_block(planet_intent, _SETTINGS)
    assert planet_verified is not None
    planet_reply = maybe_direct_physics_reply(planet_verified, planet)
    assert planet_reply is not None
    assert r"$M = 5.97 \times 10^{24}\,\mathrm{kg}$" in planet_reply
    assert "5970000000000000281018368" not in planet_reply
