"""Physics' constants are CODATA values from the shared unit registry, pinned.

A Pint upgrade that moved one would move answers, so each magnitude is held here, and the
particles a question names carry the same charge and mass the solvers use.
"""

from __future__ import annotations

import pytest

from app.modules.physics import constants
from app.modules.physics.bodies import PARTICLE_CHARGES, PARTICLE_MASSES, SCHOOL_GRAVITY


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GAS_CONSTANT", 8.31446261815324),
        ("BIG_G", 6.6743e-11),
        ("PLANCK_H", 6.62607015e-34),
        ("SPEED_OF_LIGHT", 299792458.0),
        ("ELEMENTARY_CHARGE", 1.602176634e-19),
        ("EPSILON_0", 8.854187818792247e-12),
        ("MU_0", 1.2566370612696005e-06),
        ("HBAR", 1.0545718176461565e-34),
        ("ELECTRON_MASS", 9.1093837139e-31),
        ("PROTON_MASS", 1.67262192595e-27),
        ("NEUTRON_MASS", 1.67492750056e-27),
        ("STEFAN_BOLTZMANN", 5.670374419184431e-08),
        ("WIEN_B", 0.0028977719551851727),
        ("BOLTZMANN", 1.380649e-23),
        ("RYDBERG", 10973731.568157),
        ("BOHR_RADIUS", 5.291772105438828e-11),
        ("COULOMB_K", 8987551786.178669),
    ],
)
def test_a_physics_constant_is_the_registrys_codata_value(name: str, value: float) -> None:
    assert getattr(constants, name) == value


def test_a_named_particle_carries_the_constants_the_solvers_use() -> None:
    assert PARTICLE_CHARGES["electron"] == PARTICLE_CHARGES["proton"] == constants.ELEMENTARY_CHARGE
    assert PARTICLE_CHARGES["alpha particle"] == 2 * constants.ELEMENTARY_CHARGE
    assert PARTICLE_MASSES["electron"] == constants.ELECTRON_MASS
    assert PARTICLE_MASSES["proton"] == constants.PROTON_MASS
    assert PARTICLE_MASSES["neutron"] == constants.NEUTRON_MASS


def test_school_gravity_is_the_textbook_value() -> None:
    assert SCHOOL_GRAVITY["earth"] == 9.81
