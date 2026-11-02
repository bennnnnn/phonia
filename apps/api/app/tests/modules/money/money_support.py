"""Shared builders for the money tests."""

from __future__ import annotations

from datetime import date

from app.gateways.web_search_gateway import WebSearchHit
from app.modules.money.rates import MarketRate

TODAY = date(2026, 10, 22)
HITS = [
    WebSearchHit(
        title="Mortgage Rates - Freddie Mac",
        url="https://www.freddiemac.com/pmms",
        snippet="30-year fixed-rate mortgage averaged 6.27% as of October 16, 2026.",
    ),
    WebSearchHit(title="Rates news", url="https://example.com/rates", snippet="Rates fell."),
]


def average(value: float = 6.27, name: str = "30-year fixed mortgage rate") -> MarketRate:
    return MarketRate(
        value=value,
        as_of=date(2026, 10, 16),
        source_title="Mortgage Rates - Freddie Mac",
        source_url="https://www.freddiemac.com/pmms",
        name=name,
        country="the United States",
    )
