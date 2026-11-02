"""Physics QA corpus: school questions with independently computed answers.

Every expected value here was worked by hand from the textbook formula, with
g = 9.81 m/s² and CODATA constants, not read back from the solver. The test
in ``test_physics_corpus.py`` holds two lines:

* a verified answer is never wrong: a solve either matches or declines;
* coverage only goes up: ``COVERAGE_FLOOR`` counts the cases answered today.

Add a row whenever a phrasing is fixed or found wrong. ``None`` marks a
question that must decline because any single answer to it would mislead.
"""

from __future__ import annotations

from app.tests.modules.physics import corpus_thermal_modern
from app.tests.modules.physics.corpus_case import Case
from app.tests.modules.physics.corpus_case import decline as _decline
from app.tests.modules.physics.corpus_case import q as _q

MECHANICS: tuple[Case, ...] = (
    _q(
        "A car reaches 15 m/s after accelerating at 2 m/s^2 for 10 s. How far does it travel?",
        (62.5, "m"),
    ),
    _q(
        "A car accelerates uniformly from 10 m/s to 30 m/s in 5 s. Find its acceleration.",
        (4, "m/s^2"),
    ),
    _q(
        "A car starts from rest and accelerates at 3 m/s^2 for 8 s. How far does it travel?",
        (96, "m"),
    ),
    _q(
        "A train slows from 25 m/s to rest over a distance of 125 m. Find the deceleration.",
        (-2.5, "m/s^2"),
    ),
    _q(
        "A cyclist accelerates at 2 m/s^2 for 6 s and reaches 18 m/s. What was the initial velocity?",
        (6, "m/s"),
    ),
    _q(
        "A car reaches 20 m/s after accelerating at 2 m/s^2 for 4 s. How far does it travel?",
        (64, "m"),
    ),
    _q(
        "An object moves with initial velocity 5 m/s and acceleration 2 m/s^2. "
        "Find its displacement after 4 s.",
        (36, "m"),
    ),
    _q("How long does it take a car to accelerate from 0 to 27 m/s at 4.5 m/s^2?", (6, "s")),
    _q("A car travels 150 km in 2 hours. What is its average speed?", (75, "km/h")),
    _q("A runner covers 400 m in 50 s. Find the average speed.", (8, "m/s")),
    _q("A runner covers 100 m in 20 s. Find the speed.", (5, "m/s")),
    _q("How far does a plane travel in 3 hours at 800 km/h?", (2400, "km")),
    _q(
        "A ball is dropped from a height of 45 m. How long does it take to hit the ground?",
        (3.0289, "s"),
    ),
    _q(
        "A ball is thrown upward with a speed of 20 m/s. What is the maximum height?", (20.387, "m")
    ),
    _q(
        "A stone is dropped from a bridge and hits the water 3 s later. How high is the bridge?",
        (44.145, "m"),
    ),
    _q(
        "A ball is dropped from 80 m. What is its speed just before it hits the ground?",
        (39.618, "m/s"),
    ),
    _q(
        "A stone falls from a 45 m cliff. Find its velocity when it reaches the ground.",
        (-29.714, "m/s"),
    ),
    _q("A ball is kicked at 25 m/s at an angle of 40 degrees. Find the range.", (62.74, "m")),
    _q(
        "A projectile is launched at 30 m/s at 60 degrees above the horizontal. Find the maximum height.",
        (34.404, "m"),
    ),
    _q(
        "A ball is thrown horizontally at 15 m/s from a cliff 20 m high. "
        "How far from the base of the cliff does it land?",
        (30.29, "m"),
    ),
    _q(
        "A ball is thrown horizontally from a 45 m tall building at 12 m/s. Find the time of flight.",
        (3.0289, "s"),
    ),
    _q(
        "A cannon fires a shell at 100 m/s at 30 degrees. "
        "Find the time of flight, the maximum height and the range.",
        (10.194, "s"),
        (127.42, "m"),
        (882.8, "m"),
    ),
    _q(
        "At what angle must a projectile be launched at 20 m/s to land 30 m away?",
        (23.69, "deg"),
        (66.31, "deg"),
    ),
    _q("A 5 kg box is pushed with a net force of 20 N. What is its acceleration?", (4, "m/s^2")),
    _q("What is the weight of a 70 kg person on Earth?", (686.7, "N")),
    _q("A person weighs 686.7 N on Earth. Find their mass.", (70, "kg")),
    _q(
        "A 2000 kg elevator accelerates upward at 1.5 m/s^2. Find the tension in the cable.",
        (22620, "N"),
    ),
    _q(
        "Two masses of 3 kg and 5 kg hang over a frictionless pulley. Find the acceleration and the tension.",
        (2.4525, "m/s^2"),
        (36.7875, "N"),
    ),
    _q("Two forces of 30 N and 40 N act at right angles. Find the resultant force.", (50, "N")),
    _q(
        "A force of 50 N acts at 30 degrees to the horizontal. Find its horizontal and vertical components.",
        (43.301, "N"),
        (25, "N"),
    ),
    _q(
        "A 10 kg block on a horizontal surface has a coefficient of friction 0.3. Find the friction force.",
        (29.43, "N"),
    ),
    _q(
        "A 5 kg block slides down a 30 degree incline with coefficient of kinetic friction 0.2. "
        "Find its acceleration.",
        (3.2059, "m/s^2"),
    ),
    _q(
        "A 20 kg crate is pulled across a floor with a force of 100 N. "
        "The coefficient of friction is 0.25. Find the acceleration.",
        (2.5475, "m/s^2"),
    ),
    _q(
        "A block rests on a frictionless incline of 25 degrees. Find its acceleration down the slope.",
        (4.1459, "m/s^2"),
    ),
    _q("Find the kinetic energy of a 1200 kg car moving at 20 m/s.", (240000, "J")),
    _q(
        "What is the gravitational potential energy of a 2 kg book on a shelf 1.5 m high?",
        (29.43, "J"),
    ),
    _q("A force of 40 N pushes a box 5 m. How much work is done?", (200, "J")),
    _q("A 60 kg person climbs 3 m of stairs in 4 s. What is their power output?", (441.45, "W")),
    _q("A motor does 6000 J of work in 30 s. Find its power.", (200, "W")),
    _q(
        "A ball of mass 0.5 kg is dropped from 10 m. "
        "What is its speed when it reaches the ground, using energy conservation?",
        (14.007, "m/s"),
    ),
    _q(
        "A spring with k = 200 N/m is compressed 0.1 m. How much elastic potential energy is stored?",
        (1, "J"),
    ),
    _q(
        "A machine has an input energy of 500 J and useful output of 400 J. Find its efficiency.",
        (0.8, ""),
    ),
    _q("Find the momentum of a 0.15 kg ball moving at 40 m/s.", (6, "kg*m/s")),
    _q(
        "A 2 kg ball moving at 3 m/s collides with a 1 kg ball at rest and they stick together. "
        "Find their common velocity.",
        (2, "m/s"),
    ),
    _q(
        "A 3 kg trolley at 4 m/s collides elastically with a 1 kg trolley at rest. Find the final velocities.",
        (2, "m/s"),
        (6, "m/s"),
    ),
    _q("A force of 200 N acts on a ball for 0.05 s. Find the impulse.", (10, "N*s")),
    _q(
        "A 0.2 kg ball hits a wall at 10 m/s and rebounds at 8 m/s. Find the impulse.", (3.6, "N*s")
    ),
    _q(
        "A 2 kg mass moves in a circle of radius 0.5 m at 4 m/s. Find the centripetal force.",
        (64, "N"),
    ),
    _q(
        "Find the centripetal acceleration of a car going around a bend of radius 50 m at 20 m/s.",
        (8, "m/s^2"),
    ),
    _q("A wheel turns at 300 rpm. Find its angular velocity.", (31.416, "rad/s")),
    _q(
        "A force of 20 N is applied 0.3 m from a pivot at right angles. Find the torque.",
        (6, "N*m"),
    ),
    _q(
        "Find the moment of inertia of a solid disc of mass 2 kg and radius 0.5 m.",
        (0.25, "kg*m^2"),
    ),
    _q(
        "A flywheel with moment of inertia 4 kg m^2 spins at 10 rad/s. Find its rotational kinetic energy.",
        (200, "J"),
    ),
)

GRAVITATION_AND_OSCILLATIONS: tuple[Case, ...] = (
    _q("Find the gravitational force between two 1000 kg masses 2 m apart.", (1.6685e-5, "N")),
    _q("Find the orbital speed of a satellite 400 km above Earth.", (7672, "m/s")),
    _q("Find the escape velocity from Earth.", (11186, "m/s")),
    _q(
        "What is the gravitational field strength on the surface of Mars?",
        (3.72, "m/s^2"),
        rel=0.02,
    ),
    _q("Find the period of a satellite orbiting at a radius of 7000 km around Earth.", (5828, "s")),
    _q("A mass of 0.5 kg oscillates on a spring with k = 50 N/m. Find the period.", (0.62832, "s")),
    _q("Find the period of a simple pendulum of length 2 m.", (2.8371, "s")),
)

WAVES_AND_OPTICS: tuple[Case, ...] = (
    _q("A wave has frequency 50 Hz and wavelength 4 m. Find its speed.", (200, "m/s")),
    _q("Sound travels at 340 m/s. Find the wavelength of a 680 Hz note.", (0.5, "m")),
    _q("A wave has a period of 0.02 s. Find its frequency.", (50, "Hz")),
    _q(
        "An ambulance siren emits 700 Hz and approaches a stationary observer at 30 m/s. "
        "The speed of sound is 340 m/s. Find the observed frequency.",
        (767.74, "Hz"),
    ),
    _q(
        "A string fixed at both ends is 0.8 m long and waves travel at 240 m/s. "
        "Find the fundamental frequency.",
        (150, "Hz"),
    ),
    _q(
        "An object is placed 30 cm from a converging lens of focal length 10 cm. Find the image distance.",
        (0.15, "m"),
    ),
    _q(
        "Light passes from air into glass with refractive index 1.5 at an angle of incidence of 40 degrees. "
        "Find the angle of refraction.",
        (25.374, "deg"),
    ),
    _q("Find the critical angle for glass with refractive index 1.5.", (41.81, "deg")),
    _q("Light travels at 2 × 10^8 m/s in a medium. Find the refractive index.", (1.499, "")),
    _q("A lens has focal length 0.25 m. Find its power.", (4, "1/m")),
    _q(
        "Light of wavelength 600 nm passes through a diffraction grating with 300 lines per mm. "
        "Find the angle of the first order maximum.",
        (10.37, "deg"),
    ),
    _q(
        "First-order Bragg diffraction occurs at 30 degrees from crystal planes "
        "0.2 nm apart. Find the wavelength.",
        (0.2, "nm"),
    ),
    _q(
        "First-order Bragg diffraction uses X-rays of wavelength 0.2 nm at 30 degrees. "
        "Find the plane spacing.",
        (0.2, "nm"),
    ),
    _q(
        "A siren of 500 Hz moves away from a stationary observer at 20 m/s. "
        "The speed of sound is 340 m/s. Find the frequency heard.",
        (472.22, "Hz"),
    ),
    _q(
        "An observer moves at 10 m/s toward a stationary siren of 500 Hz. "
        "The speed of sound is 340 m/s. Find the frequency heard.",
        (514.71, "Hz"),
    ),
    _q(
        "A train whistle of 400 Hz approaches at 72 km/h. Find the observed frequency.",
        (424.77, "Hz"),
    ),
    _q("A concave mirror has a radius of curvature of 40 cm. Find its focal length.", (0.2, "m")),
    _q(
        "An object is placed 30 cm from a lens and the image forms 60 cm from the lens. "
        "Find the magnification.",
        (-2, ""),
    ),
)

ELECTRICITY: tuple[Case, ...] = (
    _q("A current of 2 A flows through a 6 ohm resistor. Find the voltage.", (12, "V")),
    _q("A 12 V battery drives a current through a 4 ohm resistor. Find the current.", (3, "A")),
    _q("Find the power of a 230 V kettle drawing 10 A.", (2300, "W")),
    _q("Find the total resistance of 4 ohm, 6 ohm and 12 ohm resistors in parallel.", (2, "ohm")),
    _q("Find the total resistance of 2 ohm, 3 ohm and 5 ohm resistors in series.", (10, "ohm")),
    _q("A charge of 30 C flows in 10 s. Find the current.", (3, "A")),
    _q("A 2 kW heater runs for 3 hours. How much energy does it use in kWh?", (21.6e6, "J")),
    _q("A 100 W bulb is on for 5 minutes. How much energy does it transfer?", (30000, "J")),
    _q(
        "Find the resistance of a copper wire 10 m long with cross-sectional area 1 mm^2. "
        "The resistivity is 1.7 × 10^-8 ohm m.",
        (0.17, "ohm"),
    ),
    _q("A capacitor of 100 µF is charged to 12 V. Find the charge stored.", (1.2e-3, "C")),
    _q(
        "A 10 µF capacitor discharges through a 1 kΩ resistor. Find the time constant.", (0.01, "s")
    ),
    _q(
        "A transformer has 100 turns on the primary and 500 turns on the secondary. "
        "The primary voltage is 230 V. Find the secondary voltage.",
        (1150, "V"),
    ),
    _q(
        "A battery of emf 12 V and internal resistance 0.5 ohm delivers 2 A. Find the terminal voltage.",
        (11, "V"),
    ),
    _q(
        "Two charges of 2 × 10^-6 C and 3 × 10^-6 C are 0.5 m apart. Find the electric force between them.",
        (0.21570, "N"),
    ),
    _q("Find the electric field 0.2 m from a 5 µC point charge.", (1.1235e6, "N/C")),
    _q(
        "A wire 0.5 m long carries 3 A at right angles to a 0.2 T field. Find the force on the wire.",
        (0.3, "N"),
    ),
    _q(
        "An electron moves at 2 × 10^6 m/s perpendicular to a 0.01 T magnetic field. Find the force on it.",
        (3.2044e-15, "N"),
    ),
    _q("Find the magnetic field 5 cm from a long straight wire carrying 10 A.", (4e-5, "T")),
    _q(
        "Two parallel plates 2 cm apart have a potential difference of 100 V. "
        "Find the electric field strength.",
        (5000, "V/m"),
    ),
    _q("Find the total capacitance of a 4 µF and a 6 µF capacitor in series.", (2.4e-6, "F")),
    _q("Find the total capacitance of a 4 µF and a 6 µF capacitor in parallel.", (1e-5, "F")),
    _q(
        "A capacitor of 50 µF stores a charge of 1 mC. Find the potential difference across it.",
        (20, "V"),
    ),
    _q(
        "A 100 µF capacitor is charging through a 10 kΩ resistor from a 12 V supply. "
        "Find the voltage after 1 s.",
        (7.5854, "V"),
    ),
    _q(
        "A 100 µF capacitor is discharged through a 10 kΩ resistor after being charged to 12 V. "
        "Find the voltage after 1 s.",
        (4.4146, "V"),
    ),
    _q(
        "A charge of 2 × 10^-6 C is in an electric field of 5000 N/C. Find the force on the charge.",
        (0.01, "N"),
    ),
    _q(
        "An electron is accelerated through a potential difference of 100 V. "
        "Find the energy gained.",
        (1.6022e-17, "J"),
    ),
    _q(
        "A solenoid of length 0.25 m has 500 turns and carries a current of 2 A. "
        "Find the magnetic field inside it.",
        (5.0265e-3, "T"),
    ),
)

THERMAL_FLUIDS_MODERN: tuple[Case, ...] = (
    _q(
        "How much energy is needed to heat 2 kg of water from 20 °C to 80 °C? "
        "The specific heat capacity is 4200 J/kg°C.",
        (504000, "J"),
    ),
    _q("How much heat is released when 3 kg of water cools from 90 °C to 40 °C?", (627900, "J")),
    _q(
        "Find the energy to raise 0.5 kg of copper by 10 K. Its specific heat is 0.385 kJ/kg/K.",
        (1925, "J"),
    ),
    _q(
        "How much energy is needed to melt 0.5 kg of ice? The latent heat of fusion is 334000 J/kg.",
        (167000, "J"),
    ),
    _q("A gas at 300 K and 100 kPa occupies 2 m^3. Find the number of moles.", (80.186, "mol")),
    _q(
        "A gas occupies 4 L at 2 atm. If the pressure is increased to 4 atm at constant temperature, "
        "find the new volume.",
        (2, "L"),
    ),
    _q("Find the efficiency of a Carnot engine operating between 500 K and 300 K.", (0.4, "")),
    _q("A Carnot engine works between 227 °C and 27 °C. Find its efficiency.", (0.39988, "")),
    _q(
        "A steel rod 2 m long is heated by 50 K. The expansion coefficient is 12 × 10^-6 per K. "
        "Find the change in length.",
        (1.2e-3, "m"),
    ),
    _q("Find the pressure at a depth of 10 m in water.", (98100, "Pa")),
    _q("A force of 500 N acts on an area of 0.25 m^2. Find the pressure.", (2000, "Pa")),
    _q("Find the density of a block of mass 3 kg and volume 0.002 m^3.", (1500, "kg/m^3")),
    _q(
        "A block of volume 0.01 m^3 is fully submerged in water. Find the buoyant force.",
        (98.1, "N"),
    ),
    _q("Find the energy of a photon of frequency 5 × 10^14 Hz.", (3.3131e-19, "J")),
    _q("Find the de Broglie wavelength of an electron moving at 3 × 10^6 m/s.", (2.4247e-10, "m")),
    _q(
        "A radioactive sample has a half-life of 5 days. What fraction remains after 20 days?",
        (0.0625, ""),
    ),
    _q("Find the energy equivalent of 1 g of mass.", (8.9876e13, "J")),
    _q(
        "Light of frequency 1.2 × 10^15 Hz shines on a metal with work function 2.3 eV. "
        "Find the maximum kinetic energy of the photoelectrons.",
        (4.2659e-19, "J"),
    ),
)

# Each of these once produced a verified number, or would with a careless
# extractor, that answered a different question.
MUST_DECLINE: tuple[Case, ...] = (
    # Two speeds, one answer: the second would be dropped.
    _decline("Find the kinetic energy of a 2 kg object moving at 3 m/s and at 4 m/s."),
    # The mass nearest the word "mass" belongs to the wrong body.
    _decline(
        "A 5 kg mass is nearby. A force of 20 N acts on a 3 kg cart. What is the acceleration?"
    ),
    # A launch height and a landing distance: two lengths for one h0.
    _decline(
        "A ball is launched at 20 m/s at 30 degrees from a 20 m cliff and lands 15 m away. "
        "What is the range?"
    ),
    # Asked for an energy, but the only template here answers a time.
    _decline("A ball is dropped from 20 m. How much energy does it have when it lands?"),
    # It "reaches 18 m/s": that speed is stated. Read as the start, it gave 30 m/s.
    _decline("A cyclist accelerates at 2 m/s^2 for 6 s and reaches 18 m/s. What is its speed?"),
    # "weight" in kg is the everyday mass; W = mg would answer a force.
    _decline("My weight is 70 kg. What is my weight in pounds?"),
    # Two speeds and nothing to say which is the start.
    _decline("A car has speeds 10 m/s and 30 m/s over 5 s. Find its acceleration."),
    # Asked for a price; the energy in joules was answered as the cost.
    _decline("A 2 kW heater runs for 3 hours. Electricity costs 15p per kWh. Find the cost."),
    # A source speed with no direction: toward and away disagree.
    _decline(
        "A siren of 500 Hz moves at 20 m/s. The speed of sound is 340 m/s. "
        "Find the frequency heard."
    ),
    # Series or parallel is not said.
    _decline("Find the total capacitance of a 4 µF and a 6 µF capacitor."),
    # A virtual image's distance carries the other sign.
    _decline(
        "An object is 30 cm from a lens and forms a virtual image 60 cm from the lens. "
        "Find the magnification."
    ),
    *corpus_thermal_modern.TRAPS,
)

NOT_PHYSICS: tuple[str, ...] = (
    "The quarterly report shows revenue grew 12 percent to 3.4 million while costs fell 5 percent.",
    "Book a table for 4 at 7 pm on Friday please.",
    "What is 2 to the power of 3?",
    "Solve x^2 - 5x + 6 = 0",
    "The project has momentum now.",
    "My phone battery is at 20 percent.",
    "The car battery died after 5 years.",
    "I do circuit training 3 times a week.",
    "Resistance band workout for 20 minutes, any tips?",
    "The stock has momentum, up 12 percent this week.",
    "I need new lamps for 3 rooms.",
)

ANSWERABLE: tuple[Case, ...] = (
    *MECHANICS,
    *GRAVITATION_AND_OSCILLATIONS,
    *WAVES_AND_OPTICS,
    *ELECTRICITY,
    *THERMAL_FLUIDS_MODERN,
    *corpus_thermal_modern.CASES,
)

# Every answerable row is verified today. Raise it whenever coverage grows; never lower it.
COVERAGE_FLOOR = 147
