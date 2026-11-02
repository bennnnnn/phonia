"""One school rounding rule: a 5 rounds up, on the number as a student wrote it.

Binary floats round ties to even and store 2.675 as 2.67499…, so ``round(2.675, 2)``
is 2.67. Each value below is a tie as written; every subject must round it up.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from app.modules.chemistry.solvers.types import format_number
from app.modules.math.formulas import round_decimal_places, round_significant_figures
from app.modules.math.solve.teaching_elementary import rounding_spec
from app.modules.physics.display import plain_number
from app.services.school_rounding import format_places, round_figures, round_places


@pytest.mark.parametrize(
    ("value", "places", "shown"),
    [
        (2.675, 2, "2.68"),
        (0.125, 2, "0.13"),
        (62.5, 0, "63"),
        (1.005, 2, "1.01"),
        (12.25, 1, "12.3"),
        (9.995, 2, "10.00"),
        (0.0001235, 6, "0.000124"),
        (-2.675, 2, "-2.68"),
        (3.999, 2, "4.00"),
        ("1250", -2, "1300"),
        (Fraction(1, 8), 2, "0.13"),
        (1e20, 12, "100000000000000000000.000000000000"),
    ],
)
def test_round_places_rounds_a_written_tie_up(
    value: float | str | Fraction, places: int, shown: str
) -> None:
    assert round_places(value, places) == Decimal(shown)
    assert format_places(value, places) == shown


@pytest.mark.parametrize(
    ("value", "figures", "mantissa", "exponent"),
    [
        (2.675, 3, "2.68", 0),
        (0.125, 2, "1.3", -1),
        (62.5, 2, "6.3", 1),
        (1.005, 3, "1.01", 0),
        (12.25, 3, "1.23", 1),
        (9.995, 3, "1.00", 1),
        (0.0001235, 3, "1.24", -4),
        (-62.5, 2, "-6.3", 1),
        (0.0, 3, "0", 0),
    ],
)
def test_round_figures_keeps_every_figure_and_carries(
    value: float, figures: int, mantissa: str, exponent: int
) -> None:
    rounded, power = round_figures(value, figures)
    assert (str(rounded), power) == (mantissa, exponent)


@pytest.mark.parametrize(
    ("value", "figures", "shown"),
    [
        (62.5, 2, "63"),
        (0.1225, 3, "0.123"),
        (1.005, 3, "1.01"),
        (12.25, 3, "12.3"),
        (2.675, 3, "2.68"),
        (0.125, 2, "0.13"),
        (9.995, 3, "10"),
        (-62.5, 2, "-63"),
    ],
)
def test_every_subject_rounds_a_tie_to_the_same_figures(
    value: float, figures: int, shown: str
) -> None:
    assert plain_number(value, figures) == shown
    assert format_number(value, significant=figures) == shown
    assert round_significant_figures(value, figures) == shown


@pytest.mark.parametrize(("value", "shown"), [(2.675, "2.68"), (0.125, "0.13"), (1.005, "1.01")])
def test_the_rounding_lesson_and_the_answer_card_agree(value: float, shown: str) -> None:
    lesson = rounding_spec(repr(value), "hundredths")
    assert lesson is not None
    assert lesson.answer == shown
    assert round_decimal_places(value, 2) == shown
