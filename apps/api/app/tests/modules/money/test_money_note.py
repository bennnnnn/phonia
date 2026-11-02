"""The server's note comparing the user's rate with today's average."""

from __future__ import annotations

from app.modules.money.catalog import product
from app.modules.money.note import market_note
from app.modules.money.read import MoneyRequest
from app.modules.money.solve import Worked, work
from app.tests.modules.money.money_support import average


def _worked(**values: float) -> Worked:
    found = work(MoneyRequest(product("mortgage"), dict(values)), 6.27)
    assert found is not None
    return found


def test_a_rate_far_below_the_average_is_not_realistic() -> None:
    note = market_note(_worked(amount=300000, rate=1), average(), 2.0)
    assert note == (
        "**Note:** 1% is not a realistic 30-year fixed mortgage rate. As of Oct 16, 2026, the "
        "average in the United States is 6.27% ([Mortgage Rates - Freddie Mac]"
        "(https://www.freddiemac.com/pmms))."
    )


def test_a_rate_far_above_the_average_is_not_realistic_either() -> None:
    note = market_note(_worked(amount=300000, rate=14), average(), 2.0)
    assert note is not None and "14% is not a realistic" in note


def test_a_rate_near_the_average_gets_it_for_reference() -> None:
    note = market_note(_worked(amount=300000, rate=6.5), average(), 2.0)
    assert note is not None and note.startswith("**Note:** for reference, the average")


def test_a_rate_taken_from_the_average_says_so() -> None:
    note = market_note(_worked(amount=300000), average(), 2.0)
    assert note is not None and note.startswith("**Note:** this uses today's average")


def test_no_average_no_note() -> None:
    assert market_note(_worked(amount=300000, rate=1), None, 2.0) is None
