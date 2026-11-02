"""Closed formulas that the school catalog used to leave to the model."""

from __future__ import annotations

import pytest

from app.modules.physics.extract import extract_physics_intent
from app.tests.modules.physics.support import answer_number
from app.tests.modules.physics.test_physics_binding import _answer

_CASES = [
    (
        "A metal plate of area 0.2 m^2 has a linear expansivity of 1.2e-5 /K. "
        "Find the change in area when the temperature rises by 20 K.",
        "area_expansion",
        9.6e-5,
    ),
    (
        "A plate of area 0.0200 m^2 has linear expansivity 1.20e-5 per kelvin. "
        "The temperature rises by 50.0 K. Find the change in area.",
        "area_expansion",
        2.4e-5,
    ),
    (
        "A glass vessel of volume 0.5 m^3 has a volume expansivity of 2.7e-5 /K. "
        "Find the change in volume for a temperature rise of 10 K.",
        "volume_expansion",
        1.35e-4,
    ),
    (
        "A glass vessel of volume 0.5 m^3 has a linear expansivity of 1.2e-5 /K. "
        "Find the change in volume when the temperature rises by 20 K.",
        "volume_expansion",
        3.6e-4,
    ),
    (
        "2 mol of ideal gas expands isothermally at 300 K from 0.01 m^3 to 0.02 m^3. "
        "Find the work done by the gas.",
        "isothermal_work",
        3457.0,
    ),
    (
        "A gas has number density 2.5e25 /m^3 and molecular diameter 3e-10 m. "
        "Find the mean free path.",
        "mean_free_path",
        1.0006e-7,
    ),
    (
        "Gas molecules have diameter 3.00e-10 m and number density 2.50e25 per cubic meter. "
        "Find the mean free path.",
        "mean_free_path",
        1.0006e-7,
    ),
    (
        "A rocket exhausts gas at 2000 m/s. Its mass falls from 1000 kg to 400 kg. "
        "Find the change in speed.",
        "rocket_delta_v",
        1832.6,
    ),
    (
        "A rocket ejects gas at 2000 m/s. Its mass goes from 800 kg to 200 kg. "
        "Find the change in speed.",
        "rocket_delta_v",
        2772.6,
    ),
    (
        "A circular loop of radius 0.1 m carries 5 A. Find the magnetic field at its center.",
        "loop_magnetic_field",
        3.1416e-5,
    ),
    (
        "A toroid of 200 turns and radius 0.05 m carries 3 A. Find the magnetic field inside.",
        "toroid_field",
        0.0024,
    ),
    (
        "A solenoid of 500 turns, length 0.4 m and cross-sectional area 2e-4 m^2. "
        "Find its inductance.",
        "solenoid_inductance",
        1.5708e-4,
    ),
    (
        "An electron moves in a cyclotron in a 0.5 T field. Find the cyclotron frequency.",
        "cyclotron_frequency",
        1.4e10,
    ),
    (
        "A strip 1 mm thick carries 2 A in a 0.4 T field. The charge density is 1e28 /m^3. "
        "Find the Hall voltage.",
        "hall_voltage",
        4.99e-7,
    ),
    (
        "An electric field of 1000 N/C fills space. Find the electric energy density.",
        "electric_energy_density",
        4.427e-6,
    ),
    (
        "A magnetic field of 0.2 T fills space. Find the magnetic energy density.",
        "magnetic_energy_density",
        1.592e4,
    ),
    (
        "An electromagnetic wave has a peak electric field of 50 N/C. Find its intensity.",
        "em_wave_intensity",
        3.32,
    ),
    (
        "Light of wavelength 500 nm passes a circular aperture of diameter 2 mm. "
        "Find the Rayleigh criterion angle.",
        "rayleigh_angle",
        3.05e-4,
    ),
    (
        "Using the Rayleigh criterion, the wavelength is 550 nm and the aperture "
        "diameter is 2.00 mm. Find the angular separation.",
        "rayleigh_angle",
        3.355e-4,
    ),
    (
        "A solenoid has 500 turns, a length of 0.200 m, and a current of 3.00 A. "
        "Find the magnetic flux density.",
        "solenoid_field",
        9.425e-3,
    ),
    (
        "Two thin lenses in contact have powers 2 dioptres and 3 dioptres. Find the total power.",
        "lens_power_sum",
        5.0,
    ),
    (
        "A telescope has an objective focal length of 80 cm and an eyepiece focal length of 2 cm. "
        "Find the magnification.",
        "telescope_magnification",
        40.0,
    ),
    (
        "Masses of 3 kg and 6 kg orbit their center of mass. Find the reduced mass.",
        "reduced_mass",
        2.0,
    ),
    (
        "Two carts approach at 4 m/s and separate at 2 m/s. Find the coefficient of restitution.",
        "restitution",
        0.5,
    ),
    (
        "A torsional pendulum has moment of inertia 0.02 kg m^2 and torsion constant 0.5 N m/rad. "
        "Find the period.",
        "torsional_period",
        1.2566,
    ),
    (
        "A rod of mass 2 kg and length 0.6 m rotates about its center. Find its moment of inertia.",
        "rod_center_inertia",
        0.06,
    ),
    (
        "A rod of mass 2 kg and length 0.6 m rotates about one end. Find its moment of inertia.",
        "rod_end_inertia",
        0.24,
    ),
    (
        "A clock is 2000 m above another in a gravitational field of 9.81 m/s^2. "
        "Find the fractional frequency shift.",
        "gravitational_frequency_shift",
        2.183e-13,
    ),
    (
        "A sample has decay constant 0.01 Hz and falls from 1000 nuclei to 250. "
        "Find the time elapsed.",
        "decay_elapsed",
        138.6,
    ),
    (
        "A compound microscope has a tube length of 16 cm and a near point of 25 cm. "
        "The objective focal length is 2 cm and the eyepiece focal length is 5 cm. "
        "Find the magnification.",
        "microscope_magnification",
        40.0,
    ),
    (
        "A lens of refractive index 1.5 has radii 20 cm and -20 cm. Find the focal length.",
        "lens_maker",
        20.0,
    ),
    (
        "A biconvex lens of refractive index 1.5 has radii 20 cm and 20 cm. Find the focal length.",
        "lens_maker",
        20.0,
    ),
    (
        "Two springs in parallel have constants 200 N/m and 300 N/m. "
        "Find the equivalent spring constant.",
        "springs_parallel",
        500.0,
    ),
    (
        "Two springs in series have constants 200 N/m and 300 N/m. "
        "Find the equivalent spring constant.",
        "springs_series",
        120.0,
    ),
    (
        "A loop carries a current of 2 A through an area of 0.05 m^2. Find the magnetic moment.",
        "magnetic_moment",
        0.1,
    ),
    (
        "A magnetic moment of 0.2 A m^2 is in a 0.5 T field at 30 degrees. Find the torque.",
        "magnetic_moment_torque",
        0.05,
    ),
]


@pytest.mark.parametrize(("text", "operation", "value"), _CASES)
def test_a_missing_closed_formula_is_verified(text: str, operation: str, value: float) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == operation
    answer = _answer(text)
    assert answer is not None
    assert answer_number(answer) == pytest.approx(value, rel=0.02)


@pytest.mark.parametrize(
    "text",
    [
        "A rod of mass 2 kg and length 0.6 m. Find its moment of inertia.",
        "What is the moment of inertia of a 5 kg wheel of radius 2 m?",
    ],
)
def test_an_unstated_axis_or_shape_still_declines(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "A compound microscope has an objective focal length of 2 cm and an eyepiece "
        "focal length of 5 cm. Find the magnification.",
        "A magnetic moment of 0.2 A m^2 is in a 0.5 T field. Find the torque.",
        "Two plane mirrors face each other. Find the image after two reflections.",
        "A current of 3 A is enclosed by an arbitrary loop. Find the magnetic field.",
    ],
)
def test_a_law_with_a_missing_stated_input_still_declines(text: str) -> None:
    assert _answer(text) is None


def test_lens_powers_written_as_d_add() -> None:
    text = "Two thin lenses in contact have powers 4.00 D and 2.50 D. Find the total power."
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == "lens_power_sum"
    assert _answer(text) == "6.5 D"


def test_torque_on_a_stated_moment_stays_physics() -> None:
    from app.services.subjects.dispatch import detect_subject

    text = "A magnetic moment of 0.200 A m^2 is in a 0.500 T field at 30 degrees. Find the torque."
    assert detect_subject(text) == "physics"
    assert _answer(text) == "0.05 N·m"


def test_lens_powers_written_as_dioptres_show_as_d() -> None:
    answer = _answer(
        "Two thin lenses in contact have powers 2 dioptres and 3 dioptres. Find the total power."
    )
    assert answer == "5 D"
