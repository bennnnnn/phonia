import re

import pytest

from app.gateways.web_search_gateway import WebSearchHit, mock_search_results
from app.modules.web_search import (
    build_search_queries,
    format_location_not_set_answer,
    format_search_block,
    format_search_empty_block,
    format_sources_fence,
    needs_web_search,
    resolve_search_subject,
    web_search_skip,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("search the web for iPhone 17 rumors", True),
        ("What's the latest news on SpaceX?", True),
        ("look up online who won the game last night", True),
        ("look it up", False),
        ("what's happening in the world today", True),
        ("what's cookin in the world", True),
        ("Show me yesterdays game", True),
        ("show me yesterday's game result", True),
        ("Ethiopias game score", True),
        (
            "Why does adding two positive numbers always result in a larger number "
            "than either of the original numbers?",
            False,
        ),
        ("explain Python decorators", False),
        ("what time is it", False),
        ("what year is it", False),
        ("what's the date", False),
        ("where am I?", False),
        ("Where am iI", False),
        ("help me write an email to my boss", False),
        ("remember that I like hiking", False),
        ("I work at Uber but I want to change to Google", False),
        (
            "Where do I work right now, and which company am I considering for the future?",
            False,
        ),
        ("Who do I work for?", False),
        ("What company do I work at?", False),
        ("Where am I currently employed?", False),
        ("What's my current employer?", False),
        ("What is my job?", False),
        ("Which company am I targeting?", False),
        ("What is my career goal?", False),
        ("Do you remember where I work?", False),
        ("What do you know about my career?", False),
        ("Best restaurants near me", True),
        ("where should I eat tonight?", True),
        ("What am I trying to get done today?", False),
        ("What's on my plate today?", False),
        ("How's my day looking so far?", False),
        ("What's still open for me to finish tonight?", False),
        ("help me prioritize my tasks", False),
    ],
)
def test_needs_web_search(text, expected):
    assert needs_web_search(text) is expected


def test_is_local_places_query():
    from app.modules.web_search import is_distance_query, is_geo_query
    from app.modules.web_search.geo_intent import is_proximity_query

    assert is_proximity_query("Best restaurants near me")
    assert is_proximity_query("coffee shops nearby")
    assert is_proximity_query("The nearest gas station")
    assert is_proximity_query("nearest hospital")
    assert is_proximity_query("closest casino")
    assert is_proximity_query("libraries around here")
    assert is_geo_query("The nearest gas station")
    assert is_distance_query("how far is the airport")
    assert is_distance_query("driving time to Golden Gate Bridge")
    assert is_distance_query("how long does it take to get to the airport")
    assert is_distance_query("how long is the drive")
    assert is_geo_query("how far is the airport")
    assert not is_geo_query("distance between NYC and LA")
    assert not is_geo_query(
        "A circle has radius 3 and a chord of length 8. Find distance from center to chord."
    )
    assert is_geo_query("distance from here to the airport")
    assert is_geo_query("What's the weather?")
    assert is_geo_query("weather tomorrow")
    assert not is_geo_query("What's the weather in London?")
    kinematics = (
        "A car starts from rest and accelerates at a constant rate of 1.2 m/s^2. "
        "How long does it take the car to travel a distance of 500 meters?"
    )
    assert not is_distance_query(kinematics)
    assert not is_geo_query(kinematics)
    assert not is_geo_query(
        "A 5 N force is 2 m from the pivot. "
        "How far must a 10 N force be from the pivot to balance the lever?"
    )
    assert not is_distance_query("How long does it take the ball to fall 20 meters?")
    assert not is_distance_query("A car accelerates at 2 m/s^2. How far does it travel in 10 s?")
    assert not is_proximity_query("explain Python decorators")
    assert not is_proximity_query("find the nearest prime number")
    assert not is_proximity_query("who is my closest friend")


@pytest.mark.parametrize(
    "text",
    [
        "how many minutes to drive to the airport",
        "how many minutes to the airport",
        "how many mins away is the mall",
        "how many minutes from here to the stadium",
        "how many minutes does it take to get to work",
        "how many minutes is the walk to the station",
        "how many minutes to get there",
        "how many minutes to Bole",
        "how many miles to the airport",
        "how many km to Adama",
        "how many miles away is the closest gas station",
    ],
)
def test_is_distance_query_reads_how_many_of_a_trip(text: str) -> None:
    from app.modules.web_search import is_distance_query

    assert is_distance_query(text)


@pytest.mark.parametrize(
    "text",
    [
        "how many minutes in a good nap",
        "how many minutes in an hour?",
        "how many minutes should I boil an egg",
        "how many minutes to boil pasta",
        "how many minutes of exercise per day",
        "how many minutes should I walk a day",
        "how many minutes until midnight",
        "how many minutes to the end of the movie",
        "how many minutes to my next class",
        "how many miles is a 5k run?",
        "how many km in a mile",
        "how many miles do I run a week",
    ],
)
def test_is_distance_query_leaves_durations_and_lengths_alone(text: str) -> None:
    from app.modules.web_search import is_distance_query, is_geo_query

    assert not is_distance_query(text)
    assert not is_geo_query(text)


def test_is_ambiguous_local_places_query():
    from app.modules.web_search import is_ambiguous_local_places_query

    assert is_ambiguous_local_places_query("Nearest house")
    assert is_ambiguous_local_places_query("homes near me")
    assert not is_ambiguous_local_places_query("Places near me")
    assert is_ambiguous_local_places_query("closest property")
    assert not is_ambiguous_local_places_query("nearest house for sale")
    assert not is_ambiguous_local_places_query("nearest house near 123 Market St")
    assert not is_ambiguous_local_places_query("nearest gas station")
    assert not is_ambiguous_local_places_query("nearest hospital")


def test_build_search_queries_local_places_with_location():
    queries = build_search_queries(
        "Best restaurants near me",
        user_location="San Francisco, CA",
    )
    assert "San Francisco" in queries[0]
    assert "near me" not in queries[0].lower()
    assert any("official website" in q.lower() for q in queries)


def test_build_search_queries_local_places_with_coordinates():
    queries = build_search_queries(
        "Nearest gas station",
        user_location="San Francisco, CA",
        latitude=37.8044,
        longitude=-122.2712,
    )
    assert "37.80440,-122.27120" in queries[0]
    assert "near me" not in queries[0].lower()


def test_format_search_block_local_places_links():
    block = format_search_block(
        [
            WebSearchHit(
                title="Zuni Café",
                url="https://www.zunicafe.com",
                snippet="Market St, San Francisco.",
            )
        ],
        local_places=True,
    )
    assert "places fence" in block.lower()
    assert '"name"' in block
    assert "Zuni Café (https://www.zunicafe.com)" in block
    assert "Google Maps" in block


def test_places_payload_from_hits():
    from app.modules.web_search.formatting import places_payload_from_hits

    rows = places_payload_from_hits(
        [
            WebSearchHit(
                title="CODE Salon",
                url="https://www.yelp.com/search?find_desc=Hair+Salons",
                snippet="123 Market St, San Francisco.",
            )
        ]
    )
    assert rows[0]["name"] == "CODE Salon"
    assert rows[0]["url"].startswith("https://www.google.com/maps/search/")
    assert "CODE" in rows[0]["url"]
    assert rows[0]["address"] == "123 Market St, San Francisco"


def test_places_payload_keeps_direct_venue_url():
    from app.modules.web_search.formatting import places_payload_from_hits

    rows = places_payload_from_hits(
        [
            WebSearchHit(
                title="CODE Salon",
                url="https://www.yelp.com/biz/code-salon-san-francisco",
                snippet="Top rated salon.",
            )
        ]
    )
    assert rows[0]["url"] == "https://www.yelp.com/biz/code-salon-san-francisco"


def test_format_search_empty_block_local_places():
    block = format_search_empty_block(["best restaurants San Francisco"], local_places=True)
    assert "Do NOT invent restaurant names" in block


def test_needs_web_search_look_it_up_with_prior():
    prior = ["Show me yesterdays game"]
    assert needs_web_search("Look it up", prior_user_messages=prior) is True
    assert needs_web_search("look it up", prior_user_messages=[]) is False


def test_needs_web_search_source_followup_uses_the_prior_question():
    prior = ["Who is the current president of France?"]
    assert needs_web_search("Where did you get that?", prior_user_messages=prior) is True
    assert needs_web_search("Where did you get that?", prior_user_messages=[]) is False
    assert (
        resolve_search_subject("Where did you get that?", prior_user_messages=prior)
        == "Who is the current president of France?"
    )


def test_needs_web_search_clarification_follow_up():
    prior = ["Show me yesterdays game", "Look it up"]
    assert needs_web_search("No, the ongoing one.", prior_user_messages=prior) is True


@pytest.mark.parametrize(
    "text",
    [
        "A",
        "B",
        "C",
        "D.",
        "Start an interactive vocabulary quiz for my English project",
    ],
)
def test_needs_web_search_skips_vocab_quiz(text):
    assert needs_web_search(text) is False
    assert needs_web_search(text, prior_user_messages=["Show me yesterdays game"]) is False


def test_needs_web_search_skips_lightweight_greeting():
    assert needs_web_search("thanks!") is False
    assert needs_web_search("hi") is False
    assert needs_web_search("yes") is False


def test_needs_web_search_yes_after_search_offer():
    prior = ["Show me yesterdays game"]
    offer = "Want me to check the current result?"
    assert needs_web_search("yes", prior_user_messages=prior, prior_assistant=offer) is True
    assert needs_web_search("go", prior_user_messages=prior, prior_assistant=offer) is True
    assert needs_web_search("thanks", prior_user_messages=prior, prior_assistant=offer) is False
    assert needs_web_search("yes", prior_user_messages=prior) is True


def test_build_search_query_clarification_world_cup():
    queries = build_search_queries(
        "No, the ongoing one.",
        user_timezone="UTC",
        prior_user_messages=["Show me World Cup scores"],
    )
    assert queries[0].startswith("FIFA World Cup 2026")
    assert "2026" in queries[0]


def test_build_search_query_team_score_not_world_cup():
    queries = build_search_queries("Ethiopias game score", user_timezone="UTC")
    assert queries[0].startswith("Ethiopia")
    assert "World Cup 2026 qualified" in queries[-1]
    assert not any(q.startswith("FIFA World Cup 2026 live") for q in queries)


def test_resolve_search_subject_follow_up():
    prior = ["Show me yesterdays game"]
    assert (
        resolve_search_subject("Look it up", prior_user_messages=prior) == "Show me yesterdays game"
    )


def test_build_search_query_strips_prefix():
    assert build_search_queries("search the web for tesla stock price")[0] == "tesla stock price"


def test_build_search_query_yesterday_sports():
    queries = build_search_queries("Show me yesterdays game", user_timezone="UTC")
    # Generic yesterday+sports must not hijack into World Cup.
    assert not any("World Cup" in q for q in queries)
    assert any("scores" in q.lower() or "result" in q.lower() for q in queries)


def test_build_search_query_team_yesterday_not_world_cup():
    queries = build_search_queries("did the Lakers win yesterday", user_timezone="UTC")
    assert not any("World Cup" in q for q in queries)
    assert any("Lakers" in q for q in queries)


def test_build_search_query_news_defaults():
    query = build_search_queries("what's happening in the world today", user_timezone="UTC")[0]

    assert query.startswith("top news today ")
    assert re.search(r"\b\d{4}-\d{2}-\d{2}\b", query)


def test_build_search_query_specific_today_news_keeps_subject_and_date():
    query = build_search_queries(
        "What's happening in the U.S. today? Give me three major developments with dates.",
        user_timezone="America/Los_Angeles",
    )[0]

    assert "U.S." in query
    assert re.search(r"\b\d{4}-\d{2}-\d{2}\b", query)


def test_curly_apostrophe_today_news_is_date_anchored():
    query = build_search_queries(
        "What’s happening in the U.S. today?",
        user_timezone="America/Los_Angeles",
    )[0]

    assert "U.S." in query
    assert re.search(r"\b\d{4}-\d{2}-\d{2}\b", query)


def test_filter_hits_to_today_removes_other_dates():
    from app.modules.web_search.query_builders import _today_label, filter_hits_to_today

    today = _today_label("America/Los_Angeles")
    hits = [
        WebSearchHit(
            title="Verified today",
            url="https://example.com/today",
            snippet=f"Published {today}.",
        ),
        WebSearchHit(
            title="Older result",
            url="https://example.com/older",
            snippet="Published September 22, 2026.",
        ),
    ]

    assert filter_hits_to_today(hits, "America/Los_Angeles") == [hits[0]]


def test_filter_hits_to_today_matches_a_zero_padded_first(monkeypatch):
    from datetime import datetime as real_datetime
    from datetime import tzinfo

    from app.modules.web_search import query_builders

    class _Clock:
        @staticmethod
        def now(tz: tzinfo | None = None) -> real_datetime:
            return real_datetime(2026, 10, 1, 15, tzinfo=tz)

    monkeypatch.setattr(query_builders, "datetime", _Clock)
    today = WebSearchHit(
        title="Verified today",
        url="https://example.com/today",
        snippet="Published October 01 2026.",
    )
    later = WebSearchHit(
        title="Later in the month",
        url="https://example.com/later",
        snippet="Published October 15, 2026.",
    )

    assert query_builders.filter_hits_to_today([today, later], "America/Los_Angeles") == [today]


def test_ai_developments_today_is_treated_as_same_day_news():
    from app.modules.web_search.query_builders import (
        is_current_news_request,
        is_news_today_request,
    )

    query = "What are the three most important AI developments today?"
    assert is_current_news_request(query) is True
    assert is_news_today_request(query) is True


def test_polite_current_date_question_never_needs_web_search():
    query = "Please tell me the current date."
    assert web_search_skip(query) is True
    assert needs_web_search(query) is False


def test_build_search_query_follow_up_uses_prior():
    queries = build_search_queries(
        "Look it up",
        user_timezone="UTC",
        prior_user_messages=["Show me yesterdays game"],
    )
    assert queries[0] != "Look it up"
    assert any("scores" in q.lower() for q in queries)


def test_format_search_block_includes_links():
    block = format_search_block(
        [
            WebSearchHit(
                title="Example",
                url="https://example.com/a",
                snippet="Snippet text.",
            )
        ]
    )
    assert "Example (https://example.com/a)" in block
    assert "Snippet text." in block


def test_format_search_empty_block_forbids_roleplay():
    block = format_search_empty_block(["top news today"])
    assert "returned no usable results" in block
    assert "could not verify that live" in block  # safety phrase
    assert "Do NOT invent tournament schedules" in block


def test_format_sources_fence_json():
    block = format_sources_fence(
        [WebSearchHit(title="Example", url="https://example.com/a", snippet="info")]
    )
    assert block.startswith("\n\n```sources\n")
    assert '"title": "Example"' in block
    assert '"url": "https://example.com/a"' in block


def test_strip_sources_from_text_removes_fence_and_bare_json():
    from app.modules.web_search.formatting import strip_sources_from_text

    fenced = 'Answer here.\n\n```sources\n[{"title":"A","url":"https://a.com","snippet":"x"}]\n```'
    assert strip_sources_from_text(fenced) == "Answer here."

    labeled = (
        "Afternoon in DC.\n\n**sources**\n```\n"
        '[{"title":"DC time","url":"https://example.com/dc"}]\n```'
    )
    assert strip_sources_from_text(labeled) == "Afternoon in DC."

    nav = (
        "Here is the config you asked for:\n\n"
        '```json\n[{"title":"Home","url":"/home"},{"title":"Docs","url":"/docs"}]\n```'
    )
    assert strip_sources_from_text(nav) == nav.strip()

    trailing = (
        'Answer here.\n\n[{"title":"World Cup","url":"https://example.com",'
        '"snippet":"Scores today."}]'
    )
    assert "World Cup" in strip_sources_from_text(trailing)


def test_format_sources_fence_sanitizes_backticks_in_snippets():
    from app.modules.web_search.formatting import format_sources_fence, strip_sources_from_text

    block = format_sources_fence(
        [
            WebSearchHit(
                title="Docs",
                url="https://example.com",
                snippet="Use ```python\nprint(1)\n``` in docs",
            )
        ]
    )
    assert "```python" not in block
    cleaned = strip_sources_from_text("Hello" + block)
    assert cleaned == "Hello"


def test_mock_search_results_respects_limit():
    hits = mock_search_results("query", max_results=1)
    assert len(hits) == 1


def test_format_places_fence():
    from app.modules.web_search import format_places_fence

    fence = format_places_fence(
        [
            WebSearchHit(
                title="Benu",
                url="https://www.yelp.com/biz/benu",
                snippet="3 Michelin stars at 22 Hawthorne St ($$$)",
            )
        ]
    )
    assert fence.startswith("\n\n```places\n")
    assert "Benu" in fence
    assert "$$$" in fence
    assert "22 Hawthorne St" in fence


def test_format_search_block_warns_when_location_missing():
    block = format_search_block(
        [WebSearchHit(title="Cafe", url="https://cafe.com", snippet="Nice spot")],
        local_places=True,
        user_location=None,
    )
    assert "User location is not set" in block


def test_format_location_not_set_answer_prompts_to_enable():
    answer = format_location_not_set_answer()
    assert "location" in answer.lower()
    assert "Settings" in answer
    # It invites the city: naming one answers the question there.
    assert "Tell me the city" in answer


def test_places_payload_extracts_price():
    from app.modules.web_search.formatting import places_payload_from_hits

    rows = places_payload_from_hits(
        [
            WebSearchHit(
                title="Nopa",
                url="https://www.nopasf.com",
                snippet="California cuisine ($$$) — 560 Divisadero St",
            )
        ]
    )
    assert rows[0]["price"] == "$$$"
    assert rows[0]["address"] == "560 Divisadero St"


def test_post_stream_fences_from_search_hits():
    """Sources + places fences match what chat appends after streaming."""
    hits = [
        WebSearchHit(title="Venue", url="https://venue.example", snippet="123 Main St"),
    ]
    sources = format_sources_fence(hits)
    from app.modules.web_search import format_places_fence

    places = format_places_fence(hits)
    assert "```sources" in sources
    assert "Venue" in sources
    assert "```places" in places
    assert "123 Main St" in places


@pytest.mark.parametrize("name", ["_TEAM_SCORE", "_TEAM_POSSESSIVE_SCORE"])
def test_team_score_patterns_cost_no_more_than_their_words(name: str) -> None:
    """Every turn asks these of its message. Opened with ``.{2,60}``, each tried up to sixty
    characters from every start: on pasted code they cost sixty times a search for their
    words alone (85 ms of a 16,000-character paste's turn)."""
    import time

    from app.modules.web_search import patterns

    pattern = getattr(patterns, name)
    words = re.compile(pattern.pattern.removeprefix("(?<=..)"), pattern.flags)
    paste = " ".join(("def read(rows):\n    return [row.strip() for row in rows]\n" * 600).split())

    def best(search: object) -> float:
        assert callable(search)
        times = []
        for _ in range(5):
            start = time.perf_counter()
            search(paste)
            times.append(time.perf_counter() - start)
        return min(times)

    assert pattern.search(paste) is None
    assert best(pattern.search) < 10 * best(words.search)
