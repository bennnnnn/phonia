"""Round 3: the first three new kinds outside mechanics.

Rounds 1 and 2 grew mechanics; every remaining gap was a different branch of
the subject. These three are one-line formulas behind the existing seam, so
the interesting part is not the arithmetic — it is what each one *refuses*.

Three refusals are the reason this file is longer than the formulas warrant:

  optics    sign conventions disagree for exactly the interesting cases, so
            only a converging lens forming a real image is solved. A diverging
            lens, or an object inside the focal length, is refused rather than
            answered with a sign the reader may not share.
  thermal   27 C and 27 K differ by a factor of eleven, and "degrees" means an
            *angle* everywhere else in this package, so an absolute temperature
            without an explicit scale is refused. Efficiency is claimed only
            from two energies: from two temperatures it is a Carnot question,
            a different formula wearing the same word.
  waves     approaching and receding give different answers from identical
            numbers, so an unstated direction is refused — the shape P4 used
            for an unstated collision type.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.support import (
    answer_number,
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
}


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


# (question, kind, op, answer)
VERIFIED: list[tuple[str, str, str, str]] = [
    # --- waves: v = f lambda --------------------------------------------
    (
        "what is the wavelength of a 50 Hz wave travelling at 340 m/s",
        "waves",
        "wavelength",
        "6.8 m",
    ),
    (
        "what is the speed of a wave of wavelength 2 m and frequency 5 Hz",
        "waves",
        "wave_speed",
        "10 m/s",
    ),
    (
        "what is the frequency of a wave with a wavelength of 4 m travelling at 20 m/s",
        "waves",
        "wave_frequency",
        "5 Hz",
    ),
    (
        "a sound wave of wavelength 0.5 m travels at 340 m/s, what is its frequency",
        "waves",
        "wave_frequency",
        "680 Hz",
    ),
    # --- waves: f = 1/T and T = 1/f -------------------------------------
    (
        "what is the frequency of a wave with period 0.02 s",
        "waves",
        "wave_frequency_from_period",
        "50 Hz",
    ),
    ("what is the period of a 50 Hz wave", "waves", "wave_period", "0.02 s"),
    ("what is the period of a 200 Hz wave", "waves", "wave_period", "0.005 s"),
    # --- waves: Doppler, both directions --------------------------------
    (
        "what is the observed frequency if a 400 Hz siren approaches at 30 m/s",
        "waves",
        "doppler_frequency",
        "438 Hz (approaching, sound at 343 m/s)",
    ),
    (
        "a 400 Hz siren moves away from you at 30 m/s, what frequency do you hear",
        "waves",
        "doppler_frequency",
        "368 Hz (receding, sound at 343 m/s)",
    ),
    (
        "an ambulance horn at 500 Hz is approaching at 20 m/s, what is the doppler frequency",
        "waves",
        "doppler_frequency",
        "531 Hz (approaching, sound at 343 m/s)",
    ),
    # --- optics ----------------------------------------------------------
    (
        "what is the image distance for a lens of focal length 10 cm and object at 30 cm",
        "optics",
        "image_distance",
        # Given in cm, answered in cm.
        "15 cm",
    ),
    (
        "a converging lens has focal length 5 cm and the object is 15 cm away, where is the image",
        "optics",
        "image_distance",
        "7.5 cm",
    ),
    (
        "what is the critical angle for a medium of refractive index 1.5",
        "optics",
        "critical_angle",
        "41.8°",
    ),
    (
        "find the critical angle for a refractive index of 2",
        "optics",
        "critical_angle",
        "30°",
    ),
    (
        "what is the refractive index if light bends from 30 to 20 degrees",
        "optics",
        "refractive_index",
        "1.46",
    ),
    (
        "what is the magnification of an image 6 cm tall from a 2 cm object",
        "optics",
        "magnification",
        "3",
    ),
    (
        "The object height is 2.00 cm and the image height is 6.00 cm. Find the magnification.",
        "optics",
        "magnification",
        "3",
    ),
    # --- thermal ---------------------------------------------------------
    ("how much heat to raise 2 kg of water by 20 K", "thermal", "heat_energy", "167440 J"),
    (
        "how much heat is needed to warm 0.5 kg of water by 10 K",
        "thermal",
        "heat_energy",
        "20930 J",
    ),
    (
        "what is the pressure of 2 moles of ideal gas at 300 K in 0.05 m^3",
        "thermal",
        "ideal_gas_pressure",
        "99774 Pa",
    ),
    (
        "what is the efficiency of an engine doing 300 J of work from 1000 J",
        "thermal",
        "thermal_efficiency",
        "0.3 (30%)",
    ),
    (
        "an engine supplied with 2000 J does 500 J of work, what is its efficiency",
        "thermal",
        "thermal_efficiency",
        "0.25 (25%)",
    ),
]


@pytest.mark.parametrize("text,kind,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_round_three_kind_phrasings(text: str, kind: str, op: str, answer: str) -> None:
    assert needs_physics(text), "dropped by the pre-filter before extraction"
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent), "no intent extracted"
    assert intent.kind == kind
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_every_new_op_has_a_phrasing() -> None:
    """The three-per-op contract applies to the ops with real phrasing spread.

    `wave_speed` and the two single-shape ops carry fewer because the question
    only has one natural wording; the v = f lambda family is covered as a set.
    """
    from collections import Counter

    counts = Counter(op for _, _, op, _ in VERIFIED)
    assert set(counts) == {
        "wavelength",
        "wave_speed",
        "wave_frequency",
        "wave_frequency_from_period",
        "wave_period",
        "doppler_frequency",
        "image_distance",
        "critical_angle",
        "refractive_index",
        "magnification",
        "heat_energy",
        "ideal_gas_pressure",
        "thermal_efficiency",
    }
    assert counts["doppler_frequency"] >= 3
    assert counts["heat_energy"] >= 2


# ---------------------------------------------------------------------------
# Physical relationships.
# ---------------------------------------------------------------------------


def test_doppler_raises_the_pitch_approaching_and_lowers_it_receding() -> None:
    """The sign *is* the answer, so it gets its own assertion."""
    nearer = _verified_answer(
        "what is the observed frequency if a 400 Hz siren approaches at 30 m/s"
    )
    further = _verified_answer(
        "a 400 Hz siren moves away from you at 30 m/s, what frequency do you hear"
    )
    assert nearer is not None and further is not None
    assert float(nearer.split()[0]) > 400 > float(further.split()[0])


def test_wavelength_and_frequency_are_reciprocal_at_fixed_speed() -> None:
    low = _verified_answer("what is the wavelength of a 50 Hz wave travelling at 340 m/s")
    high = _verified_answer("what is the wavelength of a 100 Hz wave travelling at 340 m/s")
    assert low is not None and high is not None
    assert answer_number(low) == pytest.approx(2 * answer_number(high), rel=5e-3)


def test_heat_scales_with_mass() -> None:
    light = _verified_answer("how much heat to raise 1 kg of water by 20 K")
    heavy = _verified_answer("how much heat to raise 2 kg of water by 20 K")
    assert light is not None and heavy is not None
    assert answer_number(heavy) == pytest.approx(2 * answer_number(light), rel=5e-3)


# ---------------------------------------------------------------------------
# The refusals. Each is a question that looks answerable and is not.
# ---------------------------------------------------------------------------

REFUSED = [
    # Optics: the sign conventions disagree here, so nothing is claimed.
    "what is the image distance for a diverging lens of focal length 10 cm and object at 30 cm",
    "what is the image distance for a concave lens of focal length 10 cm and object at 30 cm",
    # An index below 1 has no critical angle.
    "what is the critical angle for a medium of refractive index 0.8",
    # Thermal: an absolute temperature with no scale could be either.
    "what is the pressure of 2 moles of ideal gas at 300 degrees in 0.05 m^3",
    # No named substance and no stated capacity: c would be a guess.
    "how much heat to raise 2 kg of iron by 20 K",
    # Two temperatures is Carnot, a different formula.
    "what is the efficiency of an engine between 500 K and 300 K",
    # Waves: the direction decides whether the pitch rises or falls.
    "what is the observed frequency of a 400 Hz siren moving at 30 m/s",
    # Only one of the three in v = f lambda is given.
    "what is the wavelength of a 50 Hz wave",
]


@pytest.mark.parametrize("text", REFUSED)
def test_questions_outside_the_solved_shape_are_refused(text: str) -> None:
    assert _verified_answer(text) is None


NOT_PHYSICS = [
    "there were 3 waves of layoffs this year",
    "a wave of layoffs over a 3 week period hit the team",
    "play 2 tracks with a long period of silence",
    "the lens on my 2 year old camera is scratched",
    "keep the focus on the 3 main goals",
    "make the image 2 times bigger",
    "what is the critical path for these 4 tasks",
    "the heat in this 2 bedroom flat is unbearable",
    "improve the efficiency of my 3 step workflow",
    "set the oven to 200 degrees",
    "the gas bill is 80 pounds for 2 months",
    "my monitor is 144 hz",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_the_new_cues_do_not_steal_ordinary_english(text: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


# ---------------------------------------------------------------------------
# Wordings the sweep found after the kinds shipped. Each is the same class of
# defect the round kept turning up: a cue that does not fire, or a unit written
# once for a pair.
# ---------------------------------------------------------------------------


def test_a_temperature_rise_may_omit_its_scale() -> None:
    """The half of the temperature rule that is not ambiguous.

    A *difference* of 10 degrees is 10 K and 10 C alike, so "raise 2 kg of
    water by 10 degrees" is answerable where "at 300 degrees" is not.
    """
    assert _verified_answer("how much heat is needed to raise 2 kg of water by 10 degrees") == (
        "83720 J"
    )


def test_labeled_heat_sets_efficiency_and_an_unlabeled_pair_does_not() -> None:
    absorbed = "What is the thermal efficiency of an engine that absorbs 1000 J and rejects 600 J?"
    assert _verified_answer(absorbed) == "0.4 (40%)"
    unlabeled = "what is the efficiency of a heat engine with 300 J and 1000 J"
    assert extract_physics_intent(unlabeled) is None


def test_an_absolute_temperature_still_may_not() -> None:
    """The relaxation above must not reach the ideal gas law.

    27 C and 27 K differ by a factor of eleven, and PV = nRT needs the
    absolute one.
    """
    assert (
        _verified_answer("what is the pressure of 2 moles of ideal gas at 27 degrees in 0.05 m^3")
        is None
    )


def test_a_mole_count_beside_a_temperature_is_its_own_signature() -> None:
    """ "the pressure of 2 moles of gas at 300 K" names no thermal word."""
    assert needs_physics("what is the pressure of 2 moles of gas at 300 K in 0.05 m^3")
    assert _verified_answer("what is the pressure of 2 moles of gas at 300 K in 0.05 m^3") == (
        "99774 Pa"
    )


def test_latent_heat_is_still_a_gap() -> None:
    """Melting is not Q = mc dT, and guessing it with c would be wrong."""
    assert _verified_answer("what is the energy to melt 1 kg of ice") is None
