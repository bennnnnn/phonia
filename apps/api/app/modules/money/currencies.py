"""Which currency a money card is in, and which country a rate search names.

A request that names its currency ("$300k", "5000 birr") uses that one. One that names none
("I owe 5000 on my card") uses US dollars: the app does not know where the user is.
"""

from __future__ import annotations

_US = "the United States"
# Currency -> the country a search for its rates names. Dollars search the United States.
_SEARCH_COUNTRY = {
    "EUR": "the euro area",
    "GBP": "the United Kingdom",
    "ETB": "Ethiopia",
    "INR": "India",
    "NGN": "Nigeria",
    "KES": "Kenya",
    "JPY": "Japan",
    "CAD": "Canada",
    "AUD": "Australia",
}


def currency_for(currency: str) -> str:
    """The card's currency: the request's, else US dollars."""
    return currency or "USD"


def country_for(currency: str) -> str:
    """The country a rate search names: the currency's, else the US."""
    return _SEARCH_COUNTRY.get(currency, _US)
