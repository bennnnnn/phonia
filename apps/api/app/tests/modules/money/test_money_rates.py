"""Today's average from one search and one read, used only when every check passes."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.money import rates
from app.modules.money.catalog import RateLookup, product
from app.modules.money.rates import RateReading, checked, current_average
from app.tests.modules.money.money_support import HITS, TODAY


def _mortgage_lookup() -> RateLookup:
    lookup = product("mortgage").lookup
    assert lookup is not None
    return lookup


_LOOKUP = _mortgage_lookup()
assert _LOOKUP is not None


def _reading(**fields: Any) -> RateReading:
    base: dict[str, Any] = {
        "found": True,
        "rate_percent": 6.27,
        "as_of": "2026-10-16",
        "source_url": "https://www.freddiemac.com/pmms",
    }
    base.update(fields)
    return RateReading(**base)


def test_checked_keeps_a_reading_that_passes() -> None:
    rate = checked(_reading(), HITS, _LOOKUP, 30, "the United States", TODAY)
    assert rate is not None
    assert (rate.value, rate.as_of, rate.source_url) == (6.27, date(2026, 10, 16), HITS[0].url)
    assert rate.source_title == HITS[0].title and rate.name == "30-year fixed mortgage rate"


@pytest.mark.parametrize(
    "reading",
    [
        _reading(source_url="https://elsewhere.example/rates"),  # not a page the search returned
        _reading(rate_percent=0.4),  # below what a mortgage costs
        _reading(rate_percent=31.0),  # above it
        _reading(as_of="2026-08-01"),  # older than the row allows
        _reading(as_of="2027-01-01"),  # in the future
        _reading(as_of="last week"),  # not a date
        _reading(as_of=None),
        _reading(rate_percent=None),
        _reading(found=False),
        None,  # the read gave nothing usable
    ],
)
def test_checked_drops_a_reading_that_fails(reading: RateReading | None) -> None:
    assert checked(reading, HITS, _LOOKUP, 30, "the United States", TODAY) is None


def test_a_malformed_reading_never_validates() -> None:
    with pytest.raises(ValueError):
        RateReading.model_validate({"found": "maybe", "rate_percent": "six"})


def test_the_term_picks_the_nearest_published_bucket() -> None:
    assert (_LOOKUP.term_bucket(20), _LOOKUP.term_bucket(25), _LOOKUP.term_bucket(None)) == (
        15,
        30,
        30,
    )
    car = product("car").lookup
    assert car is not None and car.term_bucket(66) == 72


async def test_current_average_searches_reads_and_caches(monkeypatch, fake_redis) -> None:
    queries: list[list[str]] = []

    async def search(settings: Settings, found: list[str], **_: Any) -> tuple[list, list]:
        queries.append(found)
        return HITS, []

    async def read(**_: Any) -> RateReading:
        return _reading()

    monkeypatch.setattr(rates, "run_cached_search", search)
    monkeypatch.setattr(rates.litellm_gateway, "complete_structured", read)
    settings = Settings()
    first = await current_average(
        product("mortgage"), 30, "the United States", settings, fake_redis, today=TODAY
    )
    again = await current_average(
        product("mortgage"), 28, "the United States", settings, fake_redis, today=TODAY
    )
    assert first is not None and again == first
    assert queries == [["average 30-year fixed mortgage rate this week the United States"]]


async def test_current_average_is_none_when_the_search_fails(monkeypatch) -> None:
    async def broken(*_: Any, **__: Any) -> tuple[list, list]:
        raise RuntimeError("no providers")

    monkeypatch.setattr(rates, "run_cached_search", broken)
    assert (
        await current_average(product("card"), None, "Kenya", Settings(), None, today=TODAY) is None
    )


async def test_a_product_with_no_lookup_has_no_average() -> None:
    assert await current_average(product("loan"), 5, "the United States", Settings(), None) is None


async def test_a_used_car_has_its_own_average(monkeypatch, fake_redis) -> None:
    """Live (2026-10-25): a used car got the new-car average. Each kind searches and caches
    apart, and names itself in the reply's words. Used-car averages are published for all
    terms at once, so that lookup names no term."""
    queries: list[list[str]] = []

    async def search(settings: Settings, found: list[str], **_: Any) -> tuple[list, list]:
        queries.append(found)
        return HITS, []

    async def read(**_: Any) -> RateReading:
        return _reading(rate_percent=11.2)

    monkeypatch.setattr(rates, "run_cached_search", search)
    monkeypatch.setattr(rates.litellm_gateway, "complete_structured", read)
    car, country = product("car"), "the United States"
    used = await current_average(
        car, 60, country, Settings(), fake_redis, today=TODAY, variant="used"
    )
    new = await current_average(car, 60, country, Settings(), fake_redis, today=TODAY)
    again = await current_average(
        car, 60, country, Settings(), fake_redis, today=TODAY, variant="used"
    )
    assert used is not None and used.name == "used car loan rate"
    assert new is not None and new.name == "60-month new car loan rate"
    assert again == used
    assert queries == [
        ["average used car loan rate this week the United States"],
        ["average 60-month new car loan rate this week the United States"],
    ]


def test_each_kind_checks_its_own_plausible_range() -> None:
    car = product("car")
    new, used = car.rate_lookup(), car.rate_lookup("used")
    assert new is not None and new is car.lookup
    assert used is not None and used is not new
    high = _reading(rate_percent=27.0)
    assert checked(high, HITS, used, None, "the United States", TODAY) is not None
    assert checked(high, HITS, new, 60, "the United States", TODAY) is None
    assert car.rate_lookup("unknown") is car.lookup
