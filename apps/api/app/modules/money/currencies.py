"""Which currency a money card is in, and which country a rate search names.

A request that names its currency ("$300k", "5000 birr") uses that one. One that names none
("I owe 5000 on my card") uses the currency of the user's saved place, and the United States'
when no place is saved. A saved place this list does not know gets no currency: the card
shows plain numbers rather than a wrong symbol.
"""

from __future__ import annotations

import re

_US = "the United States"
# Currency -> the country a search for its rates names. Dollars are left to the saved place:
# a "$300k house" in Addis is priced in dollars but borrowed in Ethiopia.
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
# How a saved place names its country (lower case) -> that country's currency.
_PLACE_CURRENCY = {
    "united states": "USD",
    "usa": "USD",
    "us": "USD",
    "united kingdom": "GBP",
    "uk": "GBP",
    "england": "GBP",
    "scotland": "GBP",
    "wales": "GBP",
    "northern ireland": "GBP",
    "ethiopia": "ETB",
    "india": "INR",
    "nigeria": "NGN",
    "kenya": "KES",
    "japan": "JPY",
    "canada": "CAD",
    "australia": "AUD",
    **dict.fromkeys(
        (
            "austria",
            "belgium",
            "croatia",
            "cyprus",
            "estonia",
            "finland",
            "france",
            "germany",
            "greece",
            "ireland",
            "italy",
            "latvia",
            "lithuania",
            "luxembourg",
            "malta",
            "netherlands",
            "portugal",
            "slovakia",
            "slovenia",
            "spain",
        ),
        "EUR",
    ),
}
# A saved place in the US: the country named, or a state code after a comma ("Austin, TX").
_US_PLACE = re.compile(
    r"\b(?:united\s+states|usa|u\.s\.a?\.?)\b|,\s*(?:A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[ADLN]|"
    r"K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\s*$",
    re.I,
)


def _place_country(location: str) -> str:
    """The country part of a saved place ("Addis Ababa, Ethiopia" -> "Ethiopia")."""
    return location.rsplit(",", 1)[-1].strip()


def currency_for(currency: str, location: str | None) -> str:
    """The card's currency: the request's, else the saved place's, else US dollars."""
    if currency:
        return currency
    if not location:
        return "USD"
    if _US_PLACE.search(location):
        return "USD"
    return _PLACE_CURRENCY.get(_place_country(location).lower(), "")


def country_for(currency: str, location: str | None) -> str:
    """The country a rate search names: the currency's, the saved place's, or the US."""
    if currency in _SEARCH_COUNTRY:
        return _SEARCH_COUNTRY[currency]
    if location:
        if _US_PLACE.search(location):
            return _US
        return _place_country(location) or _US
    return _US
