"""The card's currency and the country a rate search names."""

from __future__ import annotations

import pytest

from app.modules.money.currencies import country_for, currency_for


@pytest.mark.parametrize(
    ("currency", "location", "country"),
    [
        ("", None, "the United States"),
        ("USD", "Austin, TX", "the United States"),
        ("USD", "Addis Ababa, Ethiopia", "Ethiopia"),
        ("", "Seattle, Washington, United States", "the United States"),
        ("", "Addis Ababa, Ethiopia", "Ethiopia"),
        ("ETB", None, "Ethiopia"),
        ("GBP", "Austin, TX", "the United Kingdom"),
    ],
)
def test_country_for_names_the_country_searched(
    currency: str, location: str | None, country: str
) -> None:
    assert country_for(currency, location) == country


@pytest.mark.parametrize(
    ("currency", "location", "expected"),
    [
        # Named in the message: that one, wherever the user lives.
        ("EUR", "Austin, TX", "EUR"),
        ("USD", "Addis Ababa, Ethiopia", "USD"),
        # Named nowhere: the saved place's currency.
        ("", "Addis Ababa, Ethiopia", "ETB"),
        ("", "Berlin, Germany", "EUR"),
        ("", "London, United Kingdom", "GBP"),
        ("", "Seattle, WA", "USD"),
        ("", "Toronto, Canada", "CAD"),
        # No place saved: US dollars.
        ("", None, "USD"),
        ("", "", "USD"),
        # A place this list does not know: no symbol rather than a wrong one.
        ("", "São Paulo, Brazil", ""),
    ],
)
def test_currency_for_falls_back_to_the_saved_place(
    currency: str, location: str | None, expected: str
) -> None:
    assert currency_for(currency, location) == expected
