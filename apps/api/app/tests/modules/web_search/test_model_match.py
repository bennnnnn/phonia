"""A release question's sources are about the model it names, not other ones."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from redis.asyncio import Redis

from app.core.config import Settings
from app.gateways.web_search_gateway import WebSearchHit
from app.modules.web_search.model_match import asked_model, drop_other_models, is_another_model
from app.modules.web_search.search_cache import run_cached_search

# The five sources "Is iPhone 19 out?" got on 2026-10-23.
_IPHONE_19 = [
    WebSearchHit(
        "iPhone 19 | XX, Redesign, Glass",
        "https://appleinsider.com/inside/iphone-19",
        "Apple hasn't even announced the iPhone 18, but there are already rumors about an "
        "iPhone 19 that won't be revealed until 2027.",
    ),
    WebSearchHit(
        "20th Anniversary iPhone: Latest rumors and specs, release date | Macworld",
        "https://www.macworld.com/article/3206297/20th-anniversary-iphone.html",
        "For the 20th anniversary, Apple may simply call it iPhone 20. We might also get an "
        "iPhone 19 at the same event, just as Apple introduced the iPhone 8.",
    ),
    WebSearchHit(
        "iPhone 20 rumors: Why iPhone 19 might be skipped entirely | Mashable",
        "https://mashable.com/tech/apple-iphone-20-redesign-rumors-leaks",
        "Apple finally revealed the new iPhone 18 Pro and Pro Max at its Sept. 9 event.",
    ),
    WebSearchHit(
        "Apple to Release iPhone 6 Models Sept. 19 - Business Insider",
        "https://www.businessinsider.com/apple-to-release-iphone-6-models-sept-19-2014-9",
        "Apple is reportedly preparing to release two versions of the iPhone.",
    ),
    WebSearchHit(
        "Apple iPhone 3GS Sold Out? Nope!",
        "https://www.cnbc.com/2009/06/15/apple-iphone-3gs-sold-out-nope.html",
        "Shoppers can still reserve their 3GS's today.",
    ),
]


@pytest.mark.parametrize(
    ("query", "model"),
    [
        ("Is iPhone 19 out", ("iphone", "19")),
        ("has gta 6 been released", ("gta", "6")),
        ("GTA 6 release date", ("gta", "6")),
        ("release date of the iPhone 19", ("iphone", "19")),
        ("is PS6 out", ("ps", "6")),
        ("Is GPT-6 available yet", ("gpt", "6")),
        ("is python 3.14 out", ("python", "3.14")),
        ("is Stranger Things season 5 out on netflix yet", ("season", "5")),
        # No number, or not a release question: nothing to compare.
        ("when is the new Zelda coming out", None),
        ("weather in London 7 day forecast", None),
        ("iPhone 19 review", None),
    ],
)
def test_asked_model(query: str, model: tuple[str, str] | None) -> None:
    assert asked_model(query) == model


def test_other_iphones_leave_the_iphone_19_sources() -> None:
    kept = drop_other_models(_IPHONE_19, "Is iPhone 19 out")
    assert [hit.url for hit in kept] == [hit.url for hit in _IPHONE_19[:3]]


# What the same question found on a later search: every hit names an iPhone, none the 19.
_IPHONE_19_LATER = [
    _IPHONE_19[3],
    WebSearchHit(
        "iPhone - Wikipedia",
        "https://en.wikipedia.org/wiki/IPhone",
        "| September 20, 2024 | iPhone 16 | Apple A18 | | September 19, 2025 | iPhone 17 |",
    ),
    WebSearchHit(
        "Buy iPhone",
        "https://www.apple.com/shop/buy-iphone",
        "Explore All iPhone  iPhone Duo  iPhone 18 Pro  iPhone Air  iPhone 17  iPhone 16",
    ),
    _IPHONE_19[4],
]


def test_the_current_lineup_stays_when_no_hit_names_the_asked_model() -> None:
    # Dropping every other number left no hit: "I couldn't verify that live right now".
    kept = drop_other_models(_IPHONE_19_LATER, "Is iPhone 19 out")
    assert [hit.title for hit in kept] == ["iPhone - Wikipedia", "Buy iPhone"]


def test_every_hit_stays_when_all_would_go() -> None:
    old = [_IPHONE_19[3], _IPHONE_19[4]]
    assert drop_other_models(old, "Is iPhone 19 out") == old


@pytest.mark.parametrize(
    ("model", "text", "other"),
    [
        (("iphone", "19"), "Apple to Release iPhone 6 Models Sept. 19", True),
        (("iphone", "19"), "Apple iPhone 3GS Sold Out?", True),
        (("iphone", "19"), "iPhone 16 review", True),
        (("ios", "27"), "iOS 14 tips and tricks", True),
        # A near or newer model, the asked one, a point release of it, or no model.
        (("iphone", "19"), "iPhone 17 vs iPhone 18 Pro", False),
        (("iphone", "19"), "Why Apple may skip to the iPhone 20", False),
        (("gta", "6"), "GTA 5 online update", False),
        (("python", "3.14"), "Python 3.13 released", False),
        (("ios", "27"), "iOS 26.4 update", False),
        (("iphone", "19"), "the iPhone 19's design", False),
        (("iphone", "19"), "iPhone19 leaks", False),
        (("python", "3.14"), "Python 3.14.0 released", False),
        (("ios", "27"), "iOS 27.1 is out now", False),
        (("gta", "6"), "GTA VI trailer", False),
        (("iphone", "19"), "Apple's next iPhone arrives in September 2027", False),
    ],
)
def test_is_another_model(model: tuple[str, str], text: str, other: bool) -> None:
    assert is_another_model(WebSearchHit(text, "https://example.com", ""), model) is other


@pytest.mark.asyncio
async def test_a_search_drops_other_models_before_it_counts_results(fake_redis: Redis) -> None:
    settings = Settings(web_search_max_results=3)
    search = AsyncMock(return_value=_IPHONE_19)
    with patch("app.gateways.web_search_gateway.search_web", search):
        hits, queries = await run_cached_search(settings, ["Is iPhone 19 out"], redis=fake_redis)
    assert queries == ["Is iPhone 19 out"]
    assert {hit.url for hit in hits} == {hit.url for hit in _IPHONE_19[:3]}


@pytest.mark.asyncio
async def test_other_searches_keep_every_hit(fake_redis: Redis) -> None:
    settings = Settings(web_search_max_results=5)
    search = AsyncMock(return_value=_IPHONE_19)
    with patch("app.gateways.web_search_gateway.search_web", search):
        hits, _queries = await run_cached_search(settings, ["iphone history"], redis=fake_redis)
    assert len(hits) == 5
