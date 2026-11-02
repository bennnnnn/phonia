"""Rate quantities are scanned once and remain owned by physics."""

from unittest.mock import patch

import pytest

from app.modules.physics.extractors.rates import extract_rate_intent
from app.services.unit_text import unit_after_quantity


@pytest.mark.parametrize("digits", [100, 10000])
def test_failed_unit_tail_is_attempted_once_for_a_whole_digit_run(digits: int) -> None:
    prompt = "average speed " + "9" * digits + " ??? 2 s"
    with patch(
        "app.modules.physics.extractors.rates.unit_after_quantity",
        wraps=unit_after_quantity,
    ) as read_unit:
        assert extract_rate_intent(prompt) is None
    assert read_unit.call_count == 1
    assert read_unit.call_args.args[1] == len("average speed ") + digits


def test_two_measurements_have_exactly_two_unit_checks() -> None:
    with patch(
        "app.modules.physics.extractors.rates.unit_after_quantity",
        wraps=unit_after_quantity,
    ) as read_unit:
        intent = extract_rate_intent("average speed .5 km in 2 hours")
    assert intent is not None
    assert intent.physics_units == {"d": "km", "t": "h"}
    assert read_unit.call_count == 2


@pytest.mark.parametrize("tail", [" m/s", " m^2", " m2", " cm/s", " bananas"])
def test_compound_or_unsupported_distance_units_are_rejected(tail: str) -> None:
    assert extract_rate_intent(f"average speed 100{tail} in 20 s") is None
