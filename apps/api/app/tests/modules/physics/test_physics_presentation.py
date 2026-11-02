"""What a physics reply shows: the asked unit, the SI step, and the answer card."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.direct import maybe_direct_physics_reply
from app.services.solving import VerifiedPhysicsBlock

_SETTINGS = Settings(math_tools_enabled=True)


def _verified(text: str) -> VerifiedPhysicsBlock:
    intent = extract_physics_intent(text)
    assert intent is not None
    block = build_verified_physics_block(intent, _SETTINGS)
    assert block is not None
    return block


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("A 2 kW heater runs for 3 hours. How much energy does it use in kWh?", "6 kWh"),
        (
            "A ball is dropped from 80 m. What is its speed just before it hits the ground in km/h?",
            "143 km/h",
        ),
        (
            "A 12 V battery drives a current through a 4 ohm resistor. Find the current in mA.",
            "3000 mA",
        ),
        # A note that only restated the value in the asked unit is dropped.
        ("Find the energy of a photon of wavelength 500 nm in eV.", "2.48 eV"),
        # A note that says something else stays.
        (
            "How much heat is released when 3 kg of water cools from 90 °C to 40 °C? Give it in kJ.",
            "627.9 kJ (released)",
        ),
    ],
)
def test_the_answer_is_in_the_asked_unit(text: str, answer: str) -> None:
    assert _verified(text).canonical_answer == answer


def test_two_results_that_share_a_value_both_stay() -> None:
    # 45° components are equal; "in N" used to keep only the horizontal one.
    text = "Resolve a force of 10 N at 45 degrees into horizontal and vertical components in N."
    assert _verified(text).canonical_answer == "7.07 N horizontally and 7.07 N vertically"


def test_one_result_given_in_two_units_is_one_result_in_the_asked_unit() -> None:
    text = (
        "Find maximum photoelectric kinetic energy for frequency 1e15 Hz "
        "and work function 2 eV in eV."
    )
    assert _verified(text).canonical_answer == "2.14 eV"


def test_a_unit_of_another_kind_is_not_the_asked_unit() -> None:
    text = "A force of 40 N pushes a box 5 m. How much work is done in a factory?"
    assert _verified(text).canonical_answer == "200 J"


def test_the_card_is_typeset_and_the_answer_is_plain() -> None:
    block = _verified("Find the energy of a photon of wavelength 500 nm.")
    assert block.canonical_answer == "3.97 × 10⁻¹⁹ J (2.48 eV)"
    assert block.display_answer == r"3.97 \times 10^{-19}\,\mathrm{J}\ (2.48\,\mathrm{eV})"
    assert block.canonical_fence == {"type": "answer", "content": block.display_answer}


@pytest.mark.parametrize(
    ("text", "row"),
    [
        ("Find the energy of a photon of wavelength 500 nm.", r"$\lambda = 500\,\mathrm{nm}"),
        (
            "Two point charges of 2 microcoulombs and 3 microcoulombs are separated by 0.5 m. "
            "Find the electric force.",
            r"$q_1 = 2\,\mathrm{µC}",
        ),
    ],
)
def test_a_value_not_in_si_shows_the_value_the_solver_used(text: str, row: str) -> None:
    reply = maybe_direct_physics_reply(_verified(text), text)
    assert reply is not None
    given = reply.split("**Required**", 1)[0]
    assert row in given
    assert r"\times 10^{-" in given


@pytest.mark.parametrize(
    ("text", "row"),
    [
        # The answer equals a given (λ = d at 30°): the answer's own conversion row
        # "λ = 2e-10 m = 0.2 nm" is not the given written into the arithmetic. The SI
        # value shares the given's row: on a row of its own it read as a second given.
        (
            "In Bragg reflection, crystal planes are 0.200 nm apart and the first-order angle "
            "is 30 degrees. Find the wavelength.",
            r"$d = 0.2\,\mathrm{nm} \times 10^{-9} = 2 \times 10^{-10}\,\mathrm{m}$",
        ),
        (
            "X-rays of wavelength 0.154 nm strike a crystal at a Bragg angle of 30 degrees in "
            "the first order. Find the plane spacing.",
            r"$\lambda = 0.154\,\mathrm{nm} \times 10^{-9} = 1.54 \times 10^{-10}\,\mathrm{m}$",
        ),
    ],
)
def test_an_answer_equal_to_a_given_does_not_hide_its_si_step(text: str, row: str) -> None:
    reply = maybe_direct_physics_reply(_verified(text), text)
    assert reply is not None
    assert row in reply.split("**Required**", 1)[0]


@pytest.mark.parametrize(
    "text",
    [
        # Solved in the written units, so a conversion would not match the working.
        "A car travels 150 km in 2 hours. What is its average speed?",
        # The formula converts rpm itself.
        "A wheel turns at 300 rpm. Find its angular velocity.",
    ],
)
def test_no_conversion_row_when_the_working_uses_the_written_unit(text: str) -> None:
    reply = maybe_direct_physics_reply(_verified(text), text)
    assert reply is not None
    given = reply.split("**Required**", 1)[0]
    assert "= 7200" not in given and "rad/s" not in given


@pytest.mark.parametrize(
    ("operation", "name", "symbol"),
    [
        ("suvat_time", "d", "s"),
        ("heat_pump_cop", "temp", "T_H"),
        ("refrigerator_cop", "temp", "T_H"),
        ("diffraction_central_width", "d", "a"),
        ("rolling_speed", "r", "R"),
        ("rolling_acceleration", "r", "R"),
        ("magnetic_force_charge", "Q", "q"),
        ("charged_particle_radius", "Q", "q"),
        ("doppler_frequency", "v_src", "v_s"),
    ],
)
def test_a_given_is_named_as_its_formula_names_it(operation: str, name: str, symbol: str) -> None:
    from app.modules.physics.catalog import CATALOG, symbol_for

    spec = CATALOG[operation]
    assert symbol_for(spec, name) == symbol
    forms = [spec.base_latex or "", *(variant.latex or "" for variant in spec.variants)]
    assert any(symbol in form for form in forms)
