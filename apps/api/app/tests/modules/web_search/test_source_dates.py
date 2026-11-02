"""Dates in a search result, read against the user's today: how long ago each day was,
and a note on a page that calls a time already past still to come."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways.web_search_gateway import WebSearchHit
from app.modules.web_search import WebSearchAdapter
from app.modules.web_search.formatting import format_search_block
from app.modules.web_search.source_dates import looked_ahead_to, mark_dates, stale_note
from app.tests.tool_context import tool_context

_TODAY = date(2026, 10, 24)
# Markets Insider, found for "is the Pixel 11 out yet" on 2026-10-24; beside it, pages gave
# the phone's August 20 release, and a reply opened "It's not out for general sale yet".
_PIXEL = (
    "Tech giant Google’s (GOOGL) upcoming Pixel 11 is expected to arrive sometime in the "
    "summer of 2026, most likely during an August launch event, according to Phone Arena. "
    "Interestingly, the phone could debut alongside several other models."
)


@pytest.mark.parametrize(
    "snippet, when",
    [
        (_PIXEL, "August 2026"),
        ("GTA 6 is slated for 2025 on PS5 and Xbox.", "2025"),
        ("Windows 12 could arrive by late 2025, sources say.", "2025"),
        (
            "Samsung's Galaxy S26 will go on sale on February 25, 2026, with preorders now.",
            "February 25, 2026",
        ),
        (
            "Preorders begin on Sept. 12, 2026, and the new iPhones will officially be released "
            "on Sept. 18, 2026.",
            "September 18, 2026",
        ),
        (
            "The 18 Pro and 18 Pro Max will be available on September 18, 2026, followed by "
            "the iPhone Duo on October 23.",
            "October 23, 2026",
        ),
        # The latest past time, of every sentence.
        (
            "Apple's event is set for September 9, 2026. The iPhone 19 is expected in "
            "September 2027.",
            "September 9, 2026",
        ),
        ("The update is due out on Oct. 20, 2026.", "October 20, 2026"),
    ],
)
def test_a_page_looking_ahead_to_a_past_time_is_a_forecast(snippet: str, when: str) -> None:
    assert looked_ahead_to(snippet, _TODAY) == when
    assert stale_note(snippet, _TODAY) == (
        f"[This page looks ahead to {when}, which has passed: what it calls coming may "
        "have happened since.] "
    )


@pytest.mark.parametrize(
    "snippet",
    [
        # No time, or one still ahead.
        "The iPhone 18 Pro and Pro Max are expected to feature Apple's A20 Pro chip.",
        "The Pixel 12 is expected to launch in August 2027.",
        "Galaxy S27 rumors: Samsung will likely unveil it in January 2027.",
        "The update is due out on Oct. 30, 2026.",
        "OpenAI's GPT-6 is expected later this year, and its successor in 2027.",
        # The time is told before the looking ahead: it happened.
        "Released August 20, 2026, and expected to get seven years of updates.",
        "GTA 6 launched in 2025 and is expected to get an update in 2027.",
        # An old forecast, reported.
        "The phone was expected to launch in August 2026 but slipped to October.",
        "On July 7, 2026, Google sent out invites for the next Made by Google event, set for "
        "August 12 in New York City.",
        # Another clause's year.
        "Apple is expected to release iOS 27 later this year; iOS 26 came out in 2025.",
        "The Switch 2 arrived on June 5, 2025. Nintendo plans more games for 2026.",
        # No year to place the day.
        "Note that the iPhone Duo is coming later, on Friday, Oct. 23, with pre-orders opening.",
        "It will be available on September 18.",
        # "May" the verb.
        "Apple may launch a cheaper MacBook in may.",
    ],
)
def test_a_page_that_does_not_look_ahead_to_a_past_time_gets_no_note(snippet: str) -> None:
    assert looked_ahead_to(snippet, _TODAY) is None
    assert stale_note(snippet, _TODAY) == ""


def test_the_search_block_notes_the_forecast() -> None:
    old = WebSearchHit("Pixel 9 rumors", "https://a.example/pixel", "It is expected in March 2020.")
    new = WebSearchHit("Pixel 99 rumors", "https://b.example/pixel", "It is expected in 2099.")
    block = format_search_block([old, new], user_timezone="Africa/Addis_Ababa")
    assert (
        "1. Pixel 9 rumors (https://a.example/pixel) — [This page looks ahead to March 2020, "
        "which has passed: what it calls coming may have happened since.] It is expected in "
        "March 2020."
    ) in block
    assert "2. Pixel 99 rumors (https://b.example/pixel) — It is expected in 2099." in block


@pytest.mark.asyncio
async def test_the_search_tool_result_notes_the_forecast() -> None:
    hit = WebSearchHit("Pixel 9 rumors", "https://a.example/pixel", "It is expected in March 2020.")
    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=True))
    with patch(
        "app.modules.web_search.tool.run_cached_search",
        AsyncMock(return_value=([hit], ["pixel 9"])),
    ):
        result = await adapter.invoke({"query": "pixel 9"}, tool_context())
    assert "  [This page looks ahead to March 2020, which has passed" in result.content
    # The phone's source card keeps the page's own words.
    assert result.data is not None
    assert result.data["hits"][0]["snippet"] == "It is expected in March 2020."


@pytest.mark.parametrize(
    "text, marked",
    [
        # "Is the Pixel 11 out yet?" was answered "No" on 10 turns in 12 from this line.
        (
            "with wide availability on August 20, 2026. There is no separate window",
            "with wide availability on August 20, 2026 (2 months ago). There is no separate window",
        ),
        (
            "| September 18, 2026 | iPhone 18 Pro |\n| October 23, 2026 | iPhone Duo |",
            "| September 18, 2026 (5 weeks ago) | iPhone 18 Pro |\n"
            "| October 23, 2026 (yesterday) | iPhone Duo |",
        ),
        ("Posted: 2026-09-16 Apple says", "Posted: 2026-09-16 (5 weeks ago) Apple says"),
        ("Launched on 26th February 2026.", "Launched on 26th February 2026 (8 months ago)."),
        ("Out October 24, 2026.", "Out October 24, 2026 (today)."),
        ("On sale October 25, 2026.", "On sale October 25, 2026 (tomorrow)."),
        ("The event is on November 3, 2026.", "The event is on November 3, 2026 (in 10 days)."),
        ("Due December 1, 2027.", "Due December 1, 2027 (in 1 year)."),
        ("It came out March 3, 2026.", "It came out March 3, 2026 (7 months ago)."),
        # Named twice in a row, marked once.
        ("January 9, 2007 (2007-01-09)", "January 9, 2007 (19 years ago) (2007-01-09)"),
        # No year, no day to count from; "may" the verb; a day that does not exist.
        ("set for August 12 in New York", "set for August 12 in New York"),
        ("we may 5 2026 go", "we may 5 2026 go"),
        ("February 30, 2026", "February 30, 2026"),
    ],
)
def test_each_dated_day_says_how_long_ago_it_was(text: str, marked: str) -> None:
    assert mark_dates(text, _TODAY) == marked


def test_the_search_block_marks_dates_and_keeps_the_source_card_words() -> None:
    hit = WebSearchHit("Pixel 9", "https://a.example/pixel", "Released August 20, 2024.")
    block = format_search_block([hit], user_timezone="Africa/Addis_Ababa")
    assert "— Released August 20, 2024 (" in block
    assert " years ago)." in block
