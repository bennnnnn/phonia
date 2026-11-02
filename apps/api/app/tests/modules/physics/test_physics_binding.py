"""Questions read straight into a catalog operation, and the ones that must not be."""

from __future__ import annotations

import math

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent, solve_physics
from app.modules.physics.ask import result_dimension
from app.modules.physics.binding import bind_physics_intent
from app.modules.physics.catalog import CATALOG
from app.modules.physics.direct import maybe_direct_physics_reply
from app.modules.physics.display import si_symbol
from app.modules.physics.givens import unit_dimension
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.binding_samples import SAMPLES

_SETTINGS = Settings(math_tools_enabled=True)


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


# Each answer worked by hand: g = 9.81 m/s², G·M(Earth) from CODATA.
@pytest.mark.parametrize(
    ("text", "operation", "answer"),
    [
        (
            "A car accelerates uniformly from 10 m/s to 30 m/s in 5 s. Find its acceleration.",
            "suvat_acceleration",
            "4 m/s²",  # (30 - 10) / 5
        ),
        (
            "A cyclist accelerates at 2 m/s^2 for 6 s and reaches 18 m/s. "
            "What was the initial velocity?",
            "suvat_initial_velocity",
            "6 m/s",  # 18 - 2·6
        ),
        (
            "An object moves with initial velocity 5 m/s and acceleration 2 m/s^2. "
            "Find its displacement after 4 s.",
            "suvat_distance",
            "36 m",  # 5·4 + ½·2·16
        ),
        (
            "A car reaches 20 m/s after accelerating at 2 m/s^2 for 4 s. How far does it travel?",
            "suvat_distance",
            "64 m",  # 20*4 - 0.5*2*16
        ),
        (
            "How long does it take a car to accelerate from 0 to 27 m/s at 4.5 m/s^2?",
            "suvat_time",
            "6 s",  # 27 / 4.5; the bare 0 takes the m/s it runs to
        ),
        (
            "A car moving at 30 m/s decelerates at 5 m/s^2. How long does it take to come to rest?",
            "suvat_time",
            "6 s",  # (0 - 30) / -5
        ),
        ("How far does a plane travel in 3 hours at 800 km/h?", "rate_distance", "2400 km"),
        (
            "A stone is dropped from a bridge and hits the water 3 s later. "
            "How high is the bridge?",
            "drop_height",
            "44.1 m",  # ½·9.81·9
        ),
        (
            "A ball is thrown horizontally at 15 m/s from a cliff 20 m high. "
            "How far from the base of the cliff does it land?",
            "range",
            "30.3 m",  # 15·√(2·20/9.81)
        ),
        (
            "A ball is thrown horizontally from a 45 m tall building at 12 m/s. "
            "Find the time of flight.",
            "time_of_flight",
            "3.03 s",  # √(2·45/9.81)
        ),
        ("What is the weight of a 70 kg person on Earth?", "weight", "686.7 N"),
        ("What is the weight of a 70 kg astronaut on the Moon?", "weight", "113.4 N"),  # 70·1.62
        (
            "Two masses of 3 kg and 5 kg hang over a frictionless pulley. "
            "Find the acceleration and the tension.",
            "atwood",
            "2.45 m/s² and 36.8 N",  # 2·9.81/8; 2·15·9.81/8
        ),
        (
            "A 20 kg crate is pulled across a floor with a force of 100 N. "
            "The coefficient of friction is 0.25. Find the acceleration.",
            "applied_friction_acceleration",
            "2.55 m/s²",  # (100 - 0.25·20·9.81) / 20
        ),
        (
            "A 60 kg person climbs 3 m of stairs in 4 s. What is their power output?",
            "lifting_power",
            "441 W",  # 60·9.81·3 / 4
        ),
        (
            "Find the period of a satellite orbiting at a radius of 7000 km around Earth.",
            "kepler_period",
            "5829 s",  # 2π√(r³/GM)
        ),
        (
            "A flywheel with moment of inertia 4 kg m^2 spins at 10 rad/s. "
            "Find its rotational kinetic energy.",
            "rotational_kinetic_energy",
            "200 J",  # ½·4·100
        ),
        (
            "A flywheel has moment of inertia 0.500 kg m^2 and angular speed 4.00 rad/s. "
            "Find the angular momentum.",
            "angular_momentum",
            "2 kg·m²/s",  # 0.500·4.00
        ),
        ("A runner covers 100 m in 20 s. Find the speed.", "rate_speed", "5 m/s"),
        ("John drove 20 kms in 2 hours. What is his speed", "rate_speed", "10 km/h"),
        ("She cycled 30 kilometres in 2 hrs. What is her speed?", "rate_speed", "15 km/h"),
        (
            "A person weighs 686.7 N on Earth. Find their mass.",
            "mass_from_weight",
            "70 kg",
        ),
        (
            "First-order Bragg diffraction occurs at 30 degrees from crystal planes "
            "0.2 nm apart. Find the wavelength.",
            "bragg_wavelength",
            "0.2 nm",
        ),
        (
            "First-order Bragg diffraction uses X-rays of wavelength 0.2 nm at 30 degrees. "
            "Find the plane spacing.",
            "bragg_spacing",
            "0.2 nm",
        ),
        (
            "At constant pressure, a gas at 300 K occupies 2 L and expands to 4 L. "
            "Find its final temperature.",
            "charles_temperature",
            "600 K",
        ),
        (
            "At constant volume, a gas at 100 kPa and 300 K is heated until its pressure "
            "is 200 kPa. Find its final temperature.",
            "gay_lussac_temperature",
            "600 K",
        ),
        (
            "A gas changes from 100 kPa, 2 L and 300 K to 1 L and 600 K. Find its final pressure.",
            "combined_gas_pressure",
            "400 kPa",
        ),
        (
            "Find the mean speed of nitrogen molecules at 300 K. Molar mass is 0.028 kg/mol.",
            "mean_molecular_speed",
            "476 m/s",
        ),
        (
            "Find the most probable speed of nitrogen molecules at 300 K. "
            "Molar mass is 0.028 kg/mol.",
            "most_probable_speed",
            "422 m/s",
        ),
        (
            "How much does the temperature of 2 kg of water increase after absorbing 8360 J?",
            "temperature_change_from_heat",
            "0.999 K",
        ),
        (
            "What mass of water warms by 5 K after absorbing 41860 J?",
            "mass_from_heat",
            "2 kg",
        ),
        (
            "A 0.1 kg metal sample at 373 K is placed in 0.2 kg of water at 293 K. "
            "The final temperature is 298 K. Find the metal's specific heat capacity.",
            "calorimetry_specific_heat",
            "558 J/(kg·K)",
        ),
        (
            "What mass of ice melts when it absorbs 67000 J? "
            "Use a latent heat of fusion of 334000 J/kg.",
            "mass_from_latent_heat",
            "0.201 kg",
        ),
        (
            "A particle has rest mass 1 kg and relativistic momentum 3e8 kg m/s. "
            "Find its total energy.",
            "energy_momentum_relation",
            "1.27 × 10¹⁷ J",
        ),
    ],
)
def test_a_stated_law_is_read_and_verified(text: str, operation: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == operation
    assert _answer(text) == answer
    block = build_verified_physics_block(intent, _SETTINGS)
    assert block is not None and maybe_direct_physics_reply(block, text) is not None


@pytest.mark.parametrize(
    "text",
    [
        # Two speeds and no word saying which is the start: either guess misleads.
        "A car has speeds 10 m/s and 30 m/s over 5 s. Find its acceleration.",
        # "reaches 18 m/s" is the final speed, so a question for "the speed" is answered.
        "A cyclist accelerates at 2 m/s^2 for 6 s and reaches 18 m/s. What is its speed?",
        # "weight" here is the everyday mass, not a force.
        "My weight is 70 kg. What is my weight in pounds?",
        # A second request is not something the verified answer finishes.
        "A stone is dropped and falls for 3 s. Find how far it falls and explain it to me.",
        # A pull weaker than friction leaves the crate at rest.
        "A 20 kg crate is pulled with a force of 10 N. The coefficient of friction is 0.25. "
        "Find the acceleration.",
        # No horizontal launch: the angle is not stated, so it is not a horizontal throw.
        "A ball is thrown at 15 m/s from a cliff 20 m high. How far does it land?",
        # A height above the surface is not Kepler's r: 400 km gave 79.6 s.
        # A bare "at 400 km" says neither radius nor height: either misleads.
        "A satellite orbits Earth at 400 km. Find its period.",
        # Jupiter has no school value of g, and Earth's would answer another planet.
        "What is the weight of a 70 kg astronaut on Jupiter?",
        "A stone is dropped on the Sun and hits the ground 3 s later. How high was it dropped from?",
    ],
)
def test_a_question_the_catalog_cannot_read_exactly_declines(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Two masses of 5 kg and 3000 g hang over a frictionless pulley. "
        "Find the acceleration and the tension.",
        "Two masses of 3000 g and 5 kg hang over a frictionless pulley. "
        "Find the acceleration and the tension.",
    ],
)
def test_a_largest_first_pair_compares_in_si_and_keeps_its_units(text: str) -> None:
    # 5 kg is the heavier mass; 3000 g was once read as 3000 kg.
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_params == {"m1": 5.0, "m2": 3000.0}
    assert intent.physics_units == {"m1": "kg", "m2": "g"}
    assert _answer(text) == "2.45 m/s² and 36.8 N"


@pytest.mark.parametrize(
    ("text", "operation", "answer"),
    [
        (
            "A 1.00 kg mass is attached to a spring of constant 100 N/m. "
            "Find the frequency of oscillation.",
            "shm_frequency",
            "1.59 Hz",  # (1/2π)√(100/1)
        ),
        (
            "A solenoid has 2000 turns per meter and carries 3.00 A. "
            "Find the magnetic field inside.",
            "solenoid_field",
            "0.00754 T",  # μ0·2000·3
        ),
        (
            "Find the gravitational potential at the surface of Earth.",
            "gravitational_potential",
            "-6.26 × 10⁷ J/kg",  # -GM/R
        ),
        (
            "A pressure increase of 2.00e6 Pa produces a volume strain of 0.00100. "
            "Find the bulk modulus.",
            "bulk_modulus",
            "2 × 10⁹ Pa",  # 2e6/0.001
        ),
        (
            "The sound intensity is 1.00e-6 W/m^2. Find the sound level in decibels.",
            "sound_level",
            "60 dB",  # 10 log10(1e-6/1e-12)
        ),
        (
            "A refrigerator operates between 250 K and 300 K. Find the coefficient of performance.",
            "refrigerator_cop",
            "5",  # 250/(300-250)
        ),
        (
            "An ideal gas at 2.00 atm occupies 3.00 L. It is compressed adiabatically "
            "to 1.00 L with gamma 1.40. Find the final pressure.",
            "adiabatic_pressure",
            "9.31 atm",  # 2·3^1.40
        ),
    ],
)
def test_stated_forms_answer_the_law_that_was_asked(text: str, operation: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == operation
    assert _answer(text) == answer


def test_a_stated_g_answers_for_a_body_without_a_school_value() -> None:
    assert (
        _answer("What is the weight of a 70 kg astronaut on Jupiter where gravity is 24.8 m/s^2?")
        == "1736 N"
    )


def test_a_paste_with_more_values_than_a_question_is_not_bound() -> None:
    log = " ".join(f"lap {n} took {n + 10} s" for n in range(1, 10))
    assert bind_physics_intent(f"{log}. A runner covers 400 m in 50 s. Find the speed.") is None
    assert bind_physics_intent("A runner covers 400 m in 50 s. Find the speed.") is not None


def test_an_asked_phrase_that_labels_a_given_is_not_the_ask() -> None:
    # "an acceleration of 2 m/s²" is a given; the ask is the time.
    intent = bind_physics_intent(
        "How long does a car with an acceleration of 2 m/s^2 take to go from 0 to 20 m/s?"
    )
    assert intent is not None and intent.physics_op == "suvat_time"


def _sample(name: str) -> float:
    return SAMPLES[name]


def _bindings() -> list[tuple[str, frozenset[str]]]:
    return [
        (spec.id, inputs)
        for spec in CATALOG.values()
        if spec.binding is not None
        for inputs in spec.binding.inputs
    ]


@pytest.mark.parametrize(("operation", "inputs"), _bindings())
def test_every_promised_input_set_solves_to_the_promised_results(
    operation: str, inputs: frozenset[str]
) -> None:
    spec = CATALOG[operation]
    assert spec.binding is not None
    variables = {variable.name: variable for variable in spec.variables}
    units = {
        name: "deg" if name.startswith("angle") else si_symbol(variables[name].dimension or "")
        for name in inputs
    }
    intent = PhysicsIntent(
        kind=spec.kind,  # type: ignore[arg-type]
        physics_op=operation,
        physics_params={name: _sample(name) for name in sorted(inputs)},
        physics_units=units,
    )
    result = solve_physics(intent)
    promised = [unit_dimension(unit)[0] for unit in spec.binding.result]  # type: ignore[index]
    assert [result_dimension(item.unit) for item in result.quantities] == promised


@pytest.mark.parametrize(
    ("given", "values"),
    [
        ({"v": 20.0, "a": 2.0, "t": 3.0}, None),
        ({"v": 20.0, "a": 2.0, "d": 50.0}, None),
        ({"v": 20.0, "d": 50.0, "t": 3.0}, None),
        ({"a": 2.0, "d": 50.0, "t": 3.0}, None),
    ],
)
def test_the_initial_velocity_satisfies_every_suvat_equation(
    given: dict[str, float], values: None
) -> None:
    del values
    intent = PhysicsIntent(
        kind="suvat",
        physics_op="suvat_initial_velocity",
        physics_params=given,
        physics_units={
            name: {"v": "m/s", "a": "m/s^2", "d": "m", "t": "s"}[name] for name in given
        },
    )
    u = solve_physics(intent).quantities[0].value
    a, t, d, v = given.get("a"), given.get("t"), given.get("d"), given.get("v")
    if a is not None and t is not None:
        v = u + a * t if v is None else v
        assert math.isclose(v, u + a * t)
    if d is not None and t is not None and v is not None:
        assert math.isclose(d, (u + v) * t / 2)
    if a is not None and d is not None and v is not None:
        assert math.isclose(v * v, u * u + 2 * a * d)


# "… and write the correct unit of speed" (a Class 8 book, 2026-10-30): the unit is part
# of the answer, not a second request; a real second request still declines.
@pytest.mark.parametrize(
    ("text", "op"),
    [
        (
            "Raja travelled 15 kilometers in 3 hours. Calculate his average speed and "
            "write the correct unit of speed.",
            "rate_speed",
        ),
        (
            "A force of 20 N acts on a 4 kg mass. Find the acceleration and state its SI unit.",
            "net_force",
        ),
        ("A car moves 100 m in 20 s. Find its speed and write the unit.", "rate_speed"),
        ("A car moves 100 m in 20 s. Find its speed and write a poem about it.", None),
    ],
)
def test_asking_for_the_unit_is_part_of_the_answer(text: str, op: str | None) -> None:
    intent = extract_physics_intent(text)
    assert (intent.physics_op if intent else None) == op
