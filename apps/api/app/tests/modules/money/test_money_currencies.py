"""The card's currency and the country a rate search names."""

from __future__ import annotations

import pytest

from app.modules.money.currencies import country_for, currency_for


@pytest.mark.parametrize(
    ("currency", "country"),
    [
        ("", "the United States"),
        ("USD", "the United States"),
        ("ETB", "Ethiopia"),
        ("GBP", "the United Kingdom"),
    ],
)
def test_country_for_names_the_country_searched(currency: str, country: str) -> None:
    assert country_for(currency) == country


@pytest.mark.parametrize(
    ("currency", "expected"),
    [
        # Named in the message: that one.
        ("EUR", "EUR"),
        ("ETB", "ETB"),
        # Named nowhere: US dollars (the app does not know where the user is).
        ("", "USD"),
    ],
)
def test_currency_for_falls_back_to_us_dollars(currency: str, expected: str) -> None:
    assert currency_for(currency) == expected
