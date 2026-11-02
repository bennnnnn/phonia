"""One-expression laws past the undergraduate core."""

from __future__ import annotations

import pytest

from app.modules.physics.extract import extract_physics_intent
from app.tests.modules.physics.support import answer_number
from app.tests.modules.physics.test_physics_binding import _answer

_CASES = [
    (
        "A liquid has bulk modulus 2.20e9 Pa and density 1000 kg/m^3. Find the speed of sound.",
        "bulk_sound_speed",
        1483,
    ),
    (
        "The drag coefficient is 0.47, the density is 1.20 kg/m^3, the area is 0.400 m^2, "
        "and the speed is 30.0 m/s. Find the drag force.",
        "quadratic_drag_force",
        101.5,
    ),
    (
        "The Hubble constant is 2.27e-18 /s and a galaxy is at a distance of 3.086e22 m. "
        "Find the recessional speed.",
        "hubble_law",
        70052,
    ),
    (
        "The Hubble constant is 2.20e-18 per second. A galaxy is a distance of 1.00e25 m away. "
        "Find the recessional speed.",
        "hubble_law",
        2.20e7,
    ),
    (
        "The Hubble constant is 2.20e-18 per second. Find the critical density.",
        "critical_density",
        8.656e-27,
    ),
    (
        "The Hubble constant is 2.27e-18 /s. Find the critical density.",
        "critical_density",
        9.216e-27,
    ),
    (
        "A plasma has electron density 1.00e18 /m^3. Find the plasma frequency.",
        "plasma_frequency",
        5.641e10,
    ),
    (
        "A cold plasma has electron number density 1.00e18 per cubic meter. "
        "Find the plasma frequency.",
        "plasma_frequency",
        5.641e10,
    ),
    (
        "A plasma has electron density 1.00e18 /m^3 and temperature 10000 K. Find the Debye length.",
        "debye_length",
        6.901e-6,
    ),
    (
        "A plasma has number density 1.00e16 per cubic meter and temperature 10000 K. "
        "Find the Debye length.",
        "debye_length",
        6.901e-5,
    ),
    (
        "A plasma has magnetic field 0.0100 T and density 1.00e-6 kg/m^3. Find the Alfven speed.",
        "alfven_speed",
        8921,
    ),
    (
        "A star of radius 6.96e8 m has temperature 5772 K. Find the luminosity.",
        "stellar_luminosity",
        3.831e26,
    ),
    (
        "A star of luminosity 3.826e26 W is at a distance of 1.496e11 m. Find the radiant flux.",
        "luminosity_flux",
        1360,
    ),
    (
        "A nucleus has mass number 56. Find the nuclear radius.",
        "nuclear_radius",
        4.591e-15,
    ),
    (
        "Use the Drude model for electron density 8.50e28 /m^3 and scattering time 2.50e-14 s. "
        "Find the conductivity.",
        "drude_conductivity",
        5.988e7,
    ),
    (
        "Electron density 8.50e28 /m^3. Find the Hall coefficient.",
        "hall_coefficient",
        -7.343e-11,
    ),
    (
        "Find the Hawking temperature of the Sun.",
        "hawking_temperature",
        6.170e-8,
    ),
    (
        "A Bekenstein-Hawking horizon has area 1.00e4 m^2. Find the entropy.",
        "bekenstein_entropy",
        1.321e50,
    ),
    (
        "Find the gravitational time-dilation factor for the Sun at a distance of 15.0 km.",
        "gravitational_time_factor",
        0.896,
    ),
    (
        "In the Fermi-Dirac distribution, the energy is 0.100 eV, the chemical potential "
        "is 0.050 eV, and the temperature is 1000 K. Find the occupation number.",
        "fermi_dirac_occupation",
        0.359,
    ),
    (
        "In the Bose-Einstein distribution, the energy is 0.100 eV, the chemical potential "
        "is 0.050 eV, and the temperature is 1000 K. Find the occupation number.",
        "bose_einstein_occupation",
        1.272,
    ),
]


@pytest.mark.parametrize(("text", "operation", "value"), _CASES)
def test_a_later_form_is_verified(text: str, operation: str, value: float) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == operation
    answer = _answer(text)
    assert answer is not None
    assert answer_number(answer) == pytest.approx(value, rel=0.02)


def test_a_point_inside_the_horizon_declines() -> None:
    assert (
        _answer("Find the gravitational time-dilation factor for the Sun at a distance of 1.00 km.")
        is None
    )
