"""A source's table reaches the model one row per line, each row with its own date."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways.web_search_gateway import WebSearchHit
from app.modules.web_search import WebSearchAdapter
from app.modules.web_search.formatting import format_search_block
from app.modules.web_search.source_tables import flowed_snippet, tables_as_rows
from app.tests.tool_context import tool_context

# Wikipedia's iPhone page as the search returned it on 2026-10-24: the merged release-date
# and chip cells are gone, so the Pro Max row has neither, and the Duo row has no chip.
_IPHONE = (
    "| Release date | Model | System-on-a-chip |\n"
    "| September 20, 2024 | iPhone 16 | Apple A18 |\n"
    "| September 19, 2025 | iPhone 17 | Apple A19 |\n"
    "| iPhone Air | Apple A19 Pro |\n"
    "| March 11, 2026 | iPhone 17e | Apple A19 |\n"
    "| September 18, 2026 | iPhone 18 Pro | Apple A20 Pro |\n"
    "| iPhone 18 Pro Max |\n"
    "| October 23, 2026 | iPhone Duo |\n"
    "\n"
    "Availability and support lifespan of all iPhone models [...] On September 9, 2026, "
    "Apple announced the iPhone 18 Pro, iPhone 18 Pro Max, and the foldable iPhone Duo.\n"
)
_IPHONE_ROWS = [
    "Release date: September 20, 2024; Model: iPhone 16; System-on-a-chip: Apple A18",
    "Release date: September 19, 2025; Model: iPhone 17; System-on-a-chip: Apple A19",
    "Release date: September 19, 2025; Model: iPhone Air; System-on-a-chip: Apple A19 Pro",
    "Release date: March 11, 2026; Model: iPhone 17e; System-on-a-chip: Apple A19",
    "Release date: September 18, 2026; Model: iPhone 18 Pro; System-on-a-chip: Apple A20 Pro",
    "Release date: September 18, 2026; Model: iPhone 18 Pro Max; System-on-a-chip: Apple A20 Pro",
    "Release date: October 23, 2026; Model: iPhone Duo",
]


def test_a_row_that_lost_its_merged_date_carries_the_cells_above_it() -> None:
    """The flattened table gave a reply "iPhone 18 Pro Max: released October 23" (the Duo's).

    The Duo row has its own date, so it carries no chip: a short row with a date may be one
    cell across two columns."""
    lines = tables_as_rows(_IPHONE).split("\n")
    assert lines[: len(_IPHONE_ROWS)] == _IPHONE_ROWS
    # The prose after the table is copied as written.
    assert lines[len(_IPHONE_ROWS) :] == _IPHONE.split("\n")[8:]


def test_a_row_the_snippet_cut_off_is_left_out() -> None:
    cut = "\n".join(_IPHONE.split("\n")[:6]) + "\n| iPhone 18 "
    assert tables_as_rows(cut).split("\n") == _IPHONE_ROWS[:5]


def test_a_month_and_year_or_a_bare_year_is_a_date_column() -> None:
    table = (
        "| Year | Games | Host |\n"
        "| 2024 | Summer Olympics | Paris |\n"
        "| Summer Paralympics | Paris |\n"
        "| Feb 2026 | Winter Olympics | Milan and Cortina |"
    )
    assert tables_as_rows(table).split("\n") == [
        "Year: 2024; Games: Summer Olympics; Host: Paris",
        "Year: 2024; Games: Summer Paralympics; Host: Paris",
        "Year: Feb 2026; Games: Winter Olympics; Host: Milan and Cortina",
    ]


def test_a_date_in_a_later_column_places_the_cells_around_it() -> None:
    table = (
        "| Model | Announced | Chip |\n"
        "| Pixel 10 | August 20, 2025 | Tensor G5 |\n"
        "| Pixel 10 Pro | Tensor G5 |\n"
        "| Pixel 11 | August 12, 2026 |"
    )
    assert tables_as_rows(table).split("\n") == [
        "Model: Pixel 10; Announced: August 20, 2025; Chip: Tensor G5",
        "Model: Pixel 10 Pro; Announced: August 20, 2025; Chip: Tensor G5",
        "Model: Pixel 11; Announced: August 12, 2026",
    ]


def test_a_row_with_its_own_date_carries_nothing() -> None:
    """One cell across two columns ("Cancelled") is no merged cell from the row above."""
    table = (
        "| Year | Winner | Runner-up |\n"
        "| 2019 | Liverpool | Tottenham Hotspur |\n"
        "| 2020 | Cancelled |"
    )
    assert tables_as_rows(table).split("\n") == [
        "Year: 2019; Winner: Liverpool; Runner-up: Tottenham Hotspur",
        "Year: 2020; Winner: Cancelled",
    ]


def test_a_blank_date_cell_is_not_filled_in() -> None:
    """A cell that is there but empty is no merged cell: the row has no date."""
    table = "| Release date | Model |\n| September 18, 2026 | iPhone 18 Pro |\n|  | iPhone Fold |"
    assert tables_as_rows(table).split("\n") == [
        "Release date: September 18, 2026; Model: iPhone 18 Pro",
        "Model: iPhone Fold",
    ]


@pytest.mark.parametrize(
    "table",
    [
        # GSMArena's spec sheet: no header row, a date inside a value.
        "|  |  |  |\n| Launch | Announced | 2026, August 12 |\n"
        "| Status | Available. Released 2026, August 20 |",
        # A two-row header, then more cells than either names.
        "| Model | Announced | Release(d) |\n| With OS | Date | Latest OS |\n"
        '| iPhone "IPhone (1st generation)") | January 9, 2007 | iPhone OS 1.0 | June 29, 2007 |',
        # No date column.
        "| Country | Population |\n| Ethiopia | 132 million |\n| Kenya |",
        # A short row with two dates can't be placed.
        "| Release date | Model | Discontinued |\n| May 5, 2020 | Phone A | May 5, 2022 |\n"
        "| June 1, 2021 | June 1, 2023 |",
        # A short row with no date before any dated row has nothing to carry.
        "| Release date | Model |\n| Phone A |\n| May 5, 2020 | Phone B |",
    ],
)
def test_a_table_this_cannot_read_keeps_its_rows_as_written(table: str) -> None:
    assert tables_as_rows(table) == "\n".join(line.strip() for line in table.split("\n"))


@pytest.mark.parametrize(
    "snippet",
    [
        "Apple announced the iPhone 18 Pro.\n\nIt ships September 18.",
        "## Explore iPhone\n\n       Explore All iPhone\n       iPhone Duo\n",
        "Scores: Arsenal 2 | Chelsea 1 (full time)",
        "",
    ],
)
def test_a_snippet_without_a_table_reads_as_before(snippet: str) -> None:
    """The block flattened every snippet onto its line; one with no table still is."""
    assert flowed_snippet(snippet, indent="   ") == snippet.replace("\n", " ").strip()
    assert tables_as_rows(snippet) == snippet


def _unmarked(text: str, _today: object) -> str:
    """The table as written: how long ago each date was is ``test_source_dates``'s."""
    return text


def test_the_search_block_puts_each_row_on_its_own_line() -> None:
    hit = WebSearchHit("iPhone - Wikipedia", "https://en.wikipedia.org/wiki/IPhone", _IPHONE)
    with patch("app.modules.web_search.formatting.mark_dates", _unmarked):
        block = format_search_block([hit])
    lines = block.split("\n")
    first = lines.index(
        f"1. iPhone - Wikipedia (https://en.wikipedia.org/wiki/IPhone) — {_IPHONE_ROWS[0]}"
    )
    assert lines[first + 1 : first + len(_IPHONE_ROWS)] == [f"   {row}" for row in _IPHONE_ROWS[1:]]
    assert lines[first + len(_IPHONE_ROWS)].startswith("   Availability and support lifespan")
    assert "| iPhone 18 Pro Max |" not in block


@pytest.mark.asyncio
async def test_the_search_tool_result_reads_the_table_the_same_way() -> None:
    hit = WebSearchHit("iPhone - Wikipedia", "https://en.wikipedia.org/wiki/IPhone", _IPHONE)
    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=True))
    with (
        patch(
            "app.modules.web_search.tool.run_cached_search",
            AsyncMock(return_value=([hit], ["iphone release dates"])),
        ),
        patch("app.modules.web_search.tool.mark_dates", _unmarked),
    ):
        result = await adapter.invoke({"query": "iphone release dates"}, tool_context())
    assert "\n".join(_IPHONE_ROWS) in result.content
    assert "| iPhone 18 Pro Max |" not in result.content
    # The phone's source card keeps the page's own words.
    assert result.data is not None
    assert result.data["hits"][0]["snippet"].startswith("| Release date | Model |")
