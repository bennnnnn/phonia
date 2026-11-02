"""Round 3: the last three kinds.

Two collisions shaped this one, and neither is about physics:

- **"modulus" belongs to complex numbers first.** `SCHOOL_EXTRACTORS` run
  before `PHYSICS_EXTRACTORS`, so "the young modulus for a stress of 2e7 Pa"
  was read as |z| and failed as an unparseable expression. The elastic moduli
  are named explicitly there rather than left to ordering.
- **stress and pressure are the same arithmetic.** sigma = F/A and P = F/A
  differ by one word and nothing else, so `materials` runs before `fluids` and
  the two cue sets are kept disjoint by vocabulary. The pair of tests at the
  bottom is the only thing holding that line.

"half life" is ordinary English — a meme has one — so it is a co-occurrence cue
rather than a substring. The decoy table caught that directly.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools import extract_math_intent as extract_real_math_intent
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
    needs_physics,
)

PHYSICS_KINDS = {
    "kinematics",
    "suvat",
    "projectile",
    "force",
    "energy",
    "momentum",
    "friction",
    "circular",
    "spring",
    "circuit",
    "torque",
    "waves",
    "optics",
    "thermal",
    "gravitation",
    "fluids",
    "rotation",
    "magnetism",
    "materials",
    "modern",
}


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


VERIFIED: list[tuple[str, str, str, str]] = [
    # --- magnetism --------------------------------------------------------
    (
        "what is the force on a 2 m wire carrying 3 A in a 0.5 T magnetic field",
        "magnetism",
        "magnetic_force_wire",
        "3 N",
    ),
    (
        "a 4 m conductor carries 2 A in a 0.25 T magnetic field, what is the force",
        "magnetism",
        "magnetic_force_wire",
        "2 N",
    ),
    (
        "what is the force on a charge of 2 C moving at 10 m/s in a 0.4 T magnetic field",
        "magnetism",
        "magnetic_force_charge",
        "8 N (field perpendicular to the motion)",
    ),
    (
        "what is the magnetic flux through 0.2 m^2 in a 0.5 T field",
        "magnetism",
        "magnetic_flux",
        "0.1 Wb",
    ),
    (
        "Two point charges of 2 microcoulombs and 3 microcoulombs are separated by 0.5 m. "
        "Find the electric force.",
        "magnetism",
        "electric_force",
        "0.216 N",
    ),
    # --- materials --------------------------------------------------------
    (
        "what is the stress on a wire from a 200 N force over 0.01 m^2",
        "materials",
        "stress",
        "20000 Pa",
    ),
    ("what is the strain if a 2 m wire extends by 4 mm", "materials", "strain", "0.002"),
    (
        "what is the young modulus for a stress of 2e7 Pa and strain of 0.001",
        "materials",
        "youngs_modulus",
        "2 × 10¹⁰ Pa",
    ),
    # --- modern -----------------------------------------------------------
    (
        "what is the energy of a photon of frequency 5e14 Hz",
        "modern",
        "photon_energy",
        "3.31 × 10⁻¹⁹ J (2.07 eV)",
    ),
    (
        "what is the de broglie wavelength of an electron at 1e6 m/s",
        "modern",
        "de_broglie_wavelength",
        "7.27 × 10⁻¹⁰ m",
    ),
    (
        "how much is left after 3 half lives of a 80 g sample",
        "modern",
        "half_life_remaining",
        "10 g",
    ),
    (
        "after 2 half lives, how much of a 40 g radioactive sample remains",
        "modern",
        "half_life_remaining",
        "10 g",
    ),
    (
        "how much of a 80 g sample is left after 15 days if the half life is 5 days",
        "modern",
        "half_life_remaining",
        "10 g",
    ),
    (
        "what is the energy equivalent of 2 kg of mass",
        "modern",
        "mass_energy",
        "1.8 × 10¹⁷ J",
    ),
]


@pytest.mark.parametrize("text,kind,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_round_three_final_phrasings(text: str, kind: str, op: str, answer: str) -> None:
    assert needs_physics(text), "dropped by the pre-filter before extraction"
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent), "no intent extracted"
    assert intent.kind == kind
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


# ---------------------------------------------------------------------------
# The stress/pressure boundary, which only exists once both kinds are in.
# ---------------------------------------------------------------------------


def test_stress_and_pressure_are_the_same_arithmetic_and_different_kinds() -> None:
    """Identical numbers, one word apart, and each must go to its own kind.

    Nothing about the values can separate these — only the vocabulary can, so
    the ordering and the disjoint cue sets are what this pins.
    """
    stress = extract_physics_intent("what is the stress on a wire from a 200 N force over 0.01 m^2")
    pressure = extract_physics_intent("what is the pressure of a 200 N force over 0.01 m^2")
    assert stress is not None and pressure is not None
    assert stress.kind == "materials"
    assert pressure.kind == "fluids"
    # Same number, arrived at twice.
    assert _verified_answer("what is the stress on a wire from a 200 N force over 0.01 m^2") == (
        "20000 Pa"
    )
    assert _verified_answer("what is the pressure of a 200 N force over 0.01 m^2") == ("20000 Pa")


def test_an_elastic_modulus_is_not_a_complex_number() -> None:
    """The school extractors run first, and "modulus" is theirs by default."""
    intent = extract_physics_intent(
        "what is the young modulus for a stress of 2e7 Pa and strain of 0.001"
    )
    assert intent is not None
    assert intent.kind == "materials"


def test_the_modulus_of_a_complex_number_is_untouched() -> None:
    """The guard above must not take complex numbers with it."""
    intent = extract_real_math_intent("what is the modulus of 3 + 4i")
    assert intent is not None
    assert intent.kind == "complex"


# ---------------------------------------------------------------------------
# Physical relationships.
# ---------------------------------------------------------------------------


def test_photon_energy_is_proportional_to_frequency() -> None:
    low = _verified_answer("what is the energy of a photon of frequency 5e14 Hz")
    high = _verified_answer("what is the energy of a photon of frequency 1e15 Hz")
    assert low is not None and high is not None
    assert float(high.split()[0]) == pytest.approx(2 * float(low.split()[0]), rel=0.01)


def test_each_half_life_halves_what_is_left() -> None:
    two = _verified_answer("how much is left after 2 half lives of a 80 g sample")
    three = _verified_answer("how much is left after 3 half lives of a 80 g sample")
    assert two is not None and three is not None
    assert float(two.split()[0]) == pytest.approx(2 * float(three.split()[0]), rel=0.01)


@pytest.mark.parametrize(
    "text,answer",
    [
        (
            "Find the Coulomb force between charges -2 uC and 3 uC separated by 50 cm.",
            "0.216 N",
        ),
        (
            "Two charges of 1 microcoulomb each are 1 m apart. Find the electric force.",
            "0.00899 N",
        ),
    ],
)
def test_electric_force_unit_variants_and_magnitude(text: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent)
    assert intent.physics_op == "electric_force"
    assert _verified_answer(text) == answer


def test_electric_force_obeys_inverse_square_law() -> None:
    near = _verified_answer(
        "Two point charges of 2 uC and 3 uC are separated by 0.5 m. Find the electric force."
    )
    far = _verified_answer(
        "Two point charges of 2 uC and 3 uC are separated by 1 m. Find the electric force."
    )
    assert near is not None and far is not None
    # Three figures each: the ratio holds to the rounding, and 2x would miss by 50%.
    assert float(near.split()[0]) == pytest.approx(4 * float(far.split()[0]), rel=1e-2)


def test_electric_force_refuses_three_body_partial_answer() -> None:
    intent = extract_physics_intent(
        "Three point charges of 1 uC, 2 uC, and 3 uC are separated by 1 m. Find the force."
    )
    assert not isinstance(intent, PhysicsIntent) or intent.physics_op != "electric_force"


def test_the_answer_keeps_the_unit_the_question_used() -> None:
    """A sample given in grams should not come back in kilograms."""
    assert _verified_answer("how much is left after 3 half lives of a 80 g sample") == "10 g"


# ---------------------------------------------------------------------------
# Refusals.
# ---------------------------------------------------------------------------

REFUSED = [
    # A particle that is not an electron has to state its own mass.
    "what is the de broglie wavelength of a proton at 1e6 m/s",
    # "How long until safe" needs a threshold nobody stated.
    "how long until a 80 g radioactive sample is safe",
    # Strain needs both lengths.
    "what is the strain if a wire extends by 4 mm",
    # Young's modulus needs a stress and a strain, not one of them.
    "what is the young modulus for a stress of 2e7 Pa",
]


@pytest.mark.parametrize("text", REFUSED)
def test_questions_outside_the_solved_shape_are_refused(text: str) -> None:
    assert _verified_answer(text) is None


def test_a_modern_cue_with_only_a_mass_is_not_mass_energy() -> None:
    named = extract_physics_intent("Find the mass energy of 0.002 kg using E = mc^2.")
    assert named is not None and named.physics_op == "mass_energy"
    incomplete = "Using special relativity, an electron has a mass of 9.11e-31 kg. Find the speed."
    intent = extract_physics_intent(incomplete)
    assert intent is None or intent.physics_op != "mass_energy"
    photoelectric = "A photoelectric experiment mentions an electron mass of 9.11e-31 kg."
    photo = extract_physics_intent(photoelectric)
    assert photo is None or photo.physics_op != "mass_energy"


NOT_PHYSICS = [
    "she has a magnetic personality, 10 out of 10",
    "the field has 3 open roles",
    "charge my card for the 2 tickets",
    "the stress of 3 deadlines is a lot",
    "I strained my back lifting 20 kg",
    "the young team of 4 shipped it",
    "energy levels are low after 2 coffees",
    "the half life of this meme was 3 days",
    "the light in the 2nd photo is better",
    "tesla model 3 costs 40000",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_the_final_cues_do_not_steal_ordinary_english(text: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS
