"""A battery of school physics questions, each with its verified answer.

The mirror question went to the model, which answered 35 degrees for a ray at
35 degrees to the surface; the reflection is 55 degrees from the normal.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.extract import needs_physics
from app.services.subjects.dispatch import build_subject_augmentation


def _settings() -> Settings:
    return Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)


async def _answer(text: str) -> str | None:
    augmentation = await build_subject_augmentation(text, _settings())
    verified = augmentation.verified
    return getattr(verified, "canonical_answer", None) if verified is not None else None


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "A ray of light strikes a flat, plane mirror at an angle of 35 degrees relative to "
            "the surface of the mirror. What is the angle of reflection measured relative to "
            "the normal line?",
            "55°",
        ),
        (
            "A ray strikes a plane mirror with an angle of incidence of 35 degrees. "
            "What is the angle of reflection?",
            "35°",
        ),
        (
            "A light ray hits a mirror at 60 degrees to the normal. What is the angle between "
            "the reflected ray and the mirror surface?",
            "30°",
        ),
        (
            "A ray hits a plane mirror at 25° to its surface. What is the angle between the "
            "incident ray and the reflected ray?",
            "130°",
        ),
        (
            "Find the angle of reflection when a ray hits a plane mirror at 30 degrees to the "
            "mirror surface.",
            "60°",
        ),
        (
            "A ray of light is incident on a plane mirror at a glancing angle of 20 degrees. "
            "What is the angle of reflection?",
            "70°",
        ),
        (
            "If the angle of incidence on a plane mirror is 42.5 degrees, what is the angle of "
            "reflection?",
            "42.5°",
        ),
        (
            "A ray of light reflects off a plane mirror. The angle between the incident ray and "
            "the mirror is 50 degrees. What is the angle of reflection?",
            "40°",
        ),
        # Which line the 30 degrees is measured from is not said: no guess.
        ("A ray hits a mirror at 30 degrees. What is the angle of reflection?", None),
    ],
)
@pytest.mark.asyncio
async def test_law_of_reflection_reads_the_reference_line(question: str, answer: str) -> None:
    assert await _answer(question) == answer


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "Light passes from air into glass (n = 1.5) at an angle of incidence of 30 degrees. "
            "What is the angle of refraction?",
            "19.5°",
        ),
        # 30 degrees to the surface is 60 to the normal; read as 30 it gave 19.5.
        (
            "Light passes from air into glass (n = 1.5) at 30 degrees to the surface. "
            "What is the angle of refraction?",
            "35.3°",
        ),
        # "degree" was kept as radians and refused.
        (
            "Light passes from air into glass (n = 1.5) at an angle of incidence of 30 degree. "
            "What is the angle of refraction?",
            "19.5°",
        ),
    ],
)
@pytest.mark.asyncio
async def test_snell_reads_the_reference_line_and_singular_degree(
    question: str, answer: str
) -> None:
    assert await _answer(question) == answer


@pytest.mark.parametrize(
    "question",
    [
        "How much heat is needed to raise the temperature of 2 kg of water by 10 degrees C? "
        "(c = 4200 J/kg C)",
        "How much heat is needed to raise the temperature of 2 kg of water by 10 degrees C? "
        "(specific heat capacity = 4200 J/kg C)",
    ],
)
@pytest.mark.asyncio
async def test_a_stated_specific_heat_is_used_over_waters(question: str) -> None:
    # Water's 4186 replaced the stated 4200 and certified 83700 J.
    assert await _answer(question) == "84000 J"


@pytest.mark.parametrize(
    "text",
    ["I bought a bathroom mirror for 30 dollars", "My mirror is 2 m tall, where should I hang it?"],
)
def test_a_mirror_alone_is_not_physics(text: str) -> None:
    assert needs_physics(text) is False


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("A car accelerates from rest at 3 m/s^2 for 5 s. What is its final velocity?", "15 m/s"),
        ("A car accelerates from rest at 2 m/s^2 for 10 s. How far does it travel?", "100 m"),
        (
            "A ball is dropped from a height of 20 m. How long does it take to hit the ground? "
            "(g = 9.8 m/s^2)",
            "2.02 s",
        ),
        ("A car travels 150 km in 2.5 hours. What is its average speed?", "60 km/h"),
        ("A car slows from 25 m/s to 5 m/s in 4 s. What is its acceleration?", "-5 m/s²"),
        (
            "A projectile is launched at 20 m/s at 30 degrees above the horizontal. What is its "
            "maximum height? (g = 9.8 m/s^2)",
            "5.1 m",
        ),
        (
            "A projectile is launched at 20 m/s at 45 degrees above the horizontal. What is its "
            "range? (g = 9.8 m/s^2)",
            "40.8 m",
        ),
        ("What force is needed to accelerate a 5 kg mass at 3 m/s^2?", "15 N"),
        ("What is the weight of a 70 kg person? (g = 9.8 m/s^2)", "686 N"),
        (
            "A 10 kg box is pushed with a 50 N force on a floor with coefficient of friction 0.2. "
            "What is its acceleration? (g = 9.8 m/s^2)",
            "3.04 m/s²",
        ),
        (
            "A 2 kg block slides down a frictionless incline at 30 degrees. What is its "
            "acceleration? (g = 9.8 m/s^2)",
            "4.9 m/s²",
        ),
        ("What is the gravitational force between two 1000 kg masses 2 m apart?", "1.67 × 10⁻⁵ N"),
        ("A spring with spring constant 200 N/m is stretched 0.1 m. What is the force?", "20 N"),
        ("What is the kinetic energy of a 2 kg object moving at 3 m/s?", "9 J"),
        (
            "What is the potential energy of a 5 kg object 10 m above the ground? (g = 9.8 m/s^2)",
            "490 J",
        ),
        ("How much work is done pushing a box with a force of 20 N over 5 m?", "100 J"),
        ("A motor does 600 J of work in 12 s. What is its power?", "50 W"),
        (
            "A spring with spring constant 400 N/m is compressed 0.05 m. How much elastic "
            "potential energy does it store?",
            "0.5 J",
        ),
        (
            "A machine has an input energy of 500 J and a useful output of 400 J. What is its "
            "efficiency?",
            "0.8 (80%)",
        ),
        ("What is the momentum of a 3 kg ball moving at 4 m/s?", "12 kg·m/s"),
        ("A force of 10 N acts on a ball for 0.5 s. What is the impulse?", "5 N·s"),
        (
            "A 0.5 kg ball moves in a circle of radius 2 m at 4 m/s. What is the centripetal "
            "force?",
            "4 N",
        ),
        ("A 12 V battery is connected to a 4 ohm resistor. What is the current?", "3 A"),
        ("What is the power of a device drawing 2 A at 230 V?", "460 W"),
        ("What is the total resistance of a 4 ohm and a 6 ohm resistor in series?", "10 Ω"),
        ("What is the total resistance of a 4 ohm and a 6 ohm resistor in parallel?", "2.4 Ω"),
        ("How much charge flows when a current of 3 A flows for 20 s?", "60 C"),
        ("A 60 W bulb is on for 5 hours. How much energy does it use in kWh?", "0.3 kWh"),
        (
            "What is the force between two charges of 2 microcoulombs each separated by 0.3 m?",
            "0.399 N",
        ),
        ("A wave has a frequency of 50 Hz and a wavelength of 2 m. What is its speed?", "100 m/s"),
        ("What is the period of a wave with a frequency of 25 Hz?", "0.04 s"),
        ("What is the wavelength of a 100 MHz radio wave? (c = 3 x 10^8 m/s)", "3 m"),
        ("What is the critical angle for glass with a refractive index of 1.5?", "41.8°"),
        ("An object 2 cm tall forms an image 6 cm tall. What is the magnification?", "3"),
        (
            "How much energy is needed to melt 0.5 kg of ice? (specific latent heat of fusion = "
            "334000 J/kg)",
            "1.67 × 10⁵ J",
        ),
        (
            "A gas at 300 K and 100 kPa is heated to 600 K at constant volume. What is the new "
            "pressure?",
            "200 kPa",
        ),
        ("What is the density of a 2 kg object with a volume of 0.001 m^3?", "2000 kg/m³"),
        ("A force of 100 N acts on an area of 0.5 m^2. What is the pressure?", "200 Pa"),
        (
            "What is the pressure at a depth of 10 m in water? (density 1000 kg/m^3, "
            "g = 9.8 m/s^2)",
            "98000 Pa (gauge)",
        ),
        (
            "An object with a volume of 2 m^3 is fully submerged in water. What is the buoyant "
            "force? (g = 9.8 m/s^2)",
            "19600 N",
        ),
        ("What is the period of a simple pendulum of length 1 m? (g = 9.8 m/s^2)", "2.01 s"),
        (
            "What is the period of a 0.5 kg mass on a spring with spring constant 200 N/m?",
            "0.314 s",
        ),
        (
            "A radioactive sample has a half-life of 5 years. What fraction remains after "
            "15 years?",
            "0.125",
        ),
        (
            "What is the energy of a photon with a frequency of 5 x 10^14 Hz?",
            "3.31 × 10⁻¹⁹ J (2.07 eV)",
        ),
        ("What is the energy equivalent of 1 g of mass?", "8.99 × 10¹³ J"),
        ("A 20 N force acts 0.5 m from a pivot. What is the moment?", "10 N·m"),
        # Each of these returned no verified answer.
        ("A ball is thrown straight up at 15 m/s. How high does it go? (g = 9.8 m/s^2)", "11.5 m"),
        (
            "A ball is thrown vertically upward at 15 m/s. What is the maximum height? "
            "(g = 9.8 m/s^2)",
            "11.5 m",
        ),
        (
            "A 2 kg cart moving at 3 m/s collides with and sticks to a stationary 1 kg cart. "
            "What is their final velocity?",
            "2 m/s",
        ),
        (
            "A stationary 1 kg cart is hit by a 2 kg cart moving at 3 m/s and they stick "
            "together. What is their final velocity?",
            "2 m/s",
        ),
        (
            "A 10 microfarad capacitor is charged to 12 V. How much charge does it store?",
            "1.2 × 10⁻⁴ C",
        ),
        ("What is the speed of light in water (n = 1.33)?", "2.25 × 10⁸ m/s"),
        ("What is the speed of light in glass of refractive index 1.5?", "2 × 10⁸ m/s"),
        (
            "A concave mirror has a focal length of 10 cm. An object is placed 15 cm from the "
            "mirror. Where is the image?",
            "30 cm",
        ),
        (
            "An object is placed 30 cm in front of a converging lens of focal length 10 cm. "
            "Where is the image?",
            "15 cm",
        ),
        (
            "What is the orbital speed of a satellite at a radius of 7 x 10^6 m around Earth? "
            "(mass of Earth = 6 x 10^24 kg)",
            "7564 m/s",
        ),
        (
            "A satellite orbits Earth at a radius of 7 x 10^6 m. What is its orbital speed? "
            "(mass of Earth = 6 x 10^24 kg)",
            "7564 m/s",
        ),
        ("A satellite orbits 400 km above Earth's surface. What is its orbital speed?", "7673 m/s"),
        ("Convert 25 degrees Celsius to kelvin.", r"298.15\ \mathrm{K}"),
        # A second, harder battery: each returned no verified answer.
        (
            "A wheel accelerates from rest at 2 rad/s^2 for 5 s. What is its final angular "
            "velocity?",
            "10 rad/s",
        ),
        (
            "A wheel spinning at 4 rad/s accelerates at 2 rad/s^2 for 3 s. What is its final "
            "angular velocity?",
            "10 rad/s",
        ),
        (
            "A torque of 10 N m acts on a wheel with moment of inertia 2 kg m^2. What is its "
            "angular acceleration?",
            "5 rad/s²",
        ),
        # "Nm" is a newton metre; the caseless "nm" read it as a nanometre.
        (
            "A torque of 20 Nm acts on a wheel with moment of inertia 4 kg m^2. What is its "
            "angular acceleration?",
            "5 rad/s²",
        ),
        ("What is the reactance of a 10 mH inductor at 50 Hz?", "3.14 Ω"),
        ("What is the reactance of a 20 microfarad capacitor at 50 Hz?", "159 Ω"),
        (
            "A gas expands at a constant pressure of 200 kPa from 0.01 m^3 to 0.03 m^3. How much "
            "work does it do?",
            "4000 J",
        ),
        (
            "How much heat flows per second through a glass window of area 2 m^2 and thickness "
            "0.005 m with a temperature difference of 10 K? (thermal conductivity 0.8 W/m K)",
            "3200 W",
        ),
        (
            "Light of wavelength 400 nm shines on a metal with a work function of 2 eV. What is "
            "the maximum kinetic energy of the emitted electrons?",
            "1.1 eV",
        ),
        (
            "A 1000 kg car travelling at 20 m/s brakes to a stop. How much work is done by the "
            "brakes?",
            "-2 × 10⁵ J",
        ),
        (
            "A 60 kg person stands in an elevator accelerating upward at 2 m/s^2. What is the "
            "normal force on the person? (g = 9.8 m/s^2)",
            "708 N",
        ),
        (
            "A 60 kg person stands in a lift accelerating downward at 2 m/s^2. What is the normal "
            "force on the person? (g = 9.8 m/s^2)",
            "468 N",
        ),
        (
            "A 0.2 kg ball hits a wall at 10 m/s and rebounds at 8 m/s. What is the magnitude of "
            "the change in momentum?",
            "3.6 kg·m/s",
        ),
        (
            "Copper has a linear expansion coefficient of 1.7 x 10^-5 per K. How much does a 2 m "
            "copper rod expand when heated by 50 K?",
            "0.0017 m",
        ),
        (
            "What is the moment of inertia of a solid disc of mass 2 kg and radius 0.5 m?",
            "0.25 kg·m²",
        ),
        (
            "What is the rotational kinetic energy of a flywheel with moment of inertia 3 kg "
            "m^2 spinning at 4 rad/s?",
            "24 J",
        ),
        (
            "Water flows through a pipe at 2 m/s. The pipe narrows from an area of 0.04 m^2 "
            "to 0.01 m^2. What is the speed in the narrow section?",
            "8 m/s",
        ),
        (
            "A hydraulic press has pistons of area 0.01 m^2 and 0.5 m^2. A force of 100 N is "
            "applied to the small piston. What force is produced on the large piston?",
            "5000 N",
        ),
        (
            "A wire carrying a current of 3 A is 0.5 m long and lies perpendicular to a 0.2 T"
            " magnetic field. What is the force on the wire?",
            "0.3 N",
        ),
        (
            "A transformer has 100 turns on the primary and 500 turns on the secondary. The "
            "primary voltage is 12 V. What is the secondary voltage?",
            "60 V",
        ),
        (
            "A coil of 200 turns experiences a change in magnetic flux of 0.05 Wb in 0.1 s. "
            "What is the induced emf?",
            "100 V",
        ),
        (
            "What is the electric field strength 0.2 m from a point charge of 5 microcoulombs?",
            "1.12 × 10⁶ N/C",
        ),
        ("What is the energy stored in a 100 microfarad capacitor charged to 50 V?", "0.125 J"),
        ("What is the RMS voltage of an AC supply with a peak voltage of 325 V?", "230 V"),
        (
            "A Carnot engine operates between 500 K and 300 K. What is its maximum efficiency?",
            "0.4 (40%)",
        ),
        (
            "A sound wave has a frequency of 440 Hz and travels at 340 m/s. What is its "
            "wavelength?",
            "0.773 m",
        ),
        (
            "What is the fundamental frequency of a 0.5 m string fixed at both ends with a "
            "wave speed of 200 m/s?",
            "200 Hz",
        ),
        (
            "What is the de Broglie wavelength of an electron moving at 1 x 10^6 m/s?",
            "7.27 × 10⁻¹⁰ m",
        ),
        ("A particle moves at 0.8c. What is its Lorentz factor?", "1.67"),
        ("A 5 kg box is lifted 2 m in 4 s. What is the power? (g = 9.8 m/s^2)", "24.5 W"),
        (
            "A ball rolls off a 1.25 m high table at 3 m/s horizontally. How far from the "
            "table does it land? (g = 9.8 m/s^2)",
            "1.52 m",
        ),
        (
            "Two forces of 3 N and 4 N act at right angles. What is the resultant force?",
            "5 N at 53.1°",
        ),
        ("What is the escape velocity from Earth?", "11186 m/s"),
        (
            "How much of an 80 g sample of a radioactive isotope with a half-life of 10 days "
            "remains after 30 days?",
            "10 g",
        ),
    ],
)
@pytest.mark.asyncio
async def test_school_physics_battery(question: str, answer: str) -> None:
    assert await _answer(question) == answer


def test_a_refused_extractor_claim_falls_back_to_the_catalog() -> None:
    """The gravitation extractor claims this as planet radius plus altitude.

    That claim leaves the stated radius and mass unused and is refused; the
    first claim used to be final, so the catalog's v = sqrt(GM/r) never ran.
    """
    from app.modules.physics.extract import extract_physics_intent
    from app.modules.physics.extractors.gravitation import _extract_gravitation_intent

    question = (
        "A satellite orbits Earth at a radius of 7 x 10^6 m. What is its orbital speed? "
        "(mass of Earth = 6 x 10^24 kg)"
    )
    claim = _extract_gravitation_intent(question.replace("7 x 10^6", "7000000"))
    assert claim is not None and claim.physics_op == "orbital_velocity"
    intent = extract_physics_intent(question)
    assert intent is not None and intent.physics_op == "orbital_speed_radius"
