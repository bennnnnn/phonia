"""Two SUVAT unknowns share one card when one setup determines both."""

from app.modules.physics.extract import extract_physics_intent
from app.tests.modules.physics.test_physics_binding import _answer

_SPEED_AND_TIME = (
    "A car accelerates from rest at 2 m/s^2 for 20 m. Find the final speed and the time."
)


def test_speed_and_time_share_one_card() -> None:
    intent = extract_physics_intent(_SPEED_AND_TIME)
    assert intent is not None
    assert intent.requested_ops == ["suvat_velocity", "suvat_time"]
    answer = _answer(_SPEED_AND_TIME)
    assert answer is not None
    assert "8.94 m/s" in answer
    assert "4.47 s" in answer
    assert "```graph" not in answer


def test_an_extra_topic_stays_unverified() -> None:
    assert (
        _answer(
            "A car accelerates from rest at 2 m/s^2 for 20 m. "
            "Find the final speed and the kinetic energy."
        )
        is None
    )


def test_force_and_acceleration_stay_unverified() -> None:
    assert _answer("Find the force and the acceleration of a 2 kg block.") is None


def test_one_suvat_unknown_stays_a_single_answer() -> None:
    intent = extract_physics_intent(
        "A car accelerates from rest at 2 m/s^2 for 20 m. Find the final speed."
    )
    assert intent is not None
    assert intent.physics_op == "suvat_velocity"
    assert intent.requested_ops == []
