"""On a searched turn a link is a source only if the search found it (T5.11)."""

from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways.web_search_gateway import WebSearchHit
from app.modules.chat.finalize_passes import FinalizeState
from app.modules.chat.search_links import unlink_unretrieved_links
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.chat.untrusted_media import neutralize_untrusted_media

_HITS = [
    WebSearchHit(title="Reuters", url="https://www.reuters.com/world/lisbon-2026", snippet="s"),
    WebSearchHit(title="BBC", url="https://bbc.com/news/123/", snippet="s"),
]


def _state(
    reply: str, *, hits: list[WebSearchHit] | None = None, message: str = "q"
) -> FinalizeState:
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="qwen-3.7-flash",
        prompt_messages=[{"role": "user", "content": message}],
        run_title=False,
        user_message_content=message,
        reserved_tokens=0,
        max_output_tokens=0,
        search_sources=_HITS if hits is None else hits,
    )
    return FinalizeState(
        deps=None,  # type: ignore[arg-type]  # these passes read no dependency
        settings=Settings(),
        ctx=ctx,
        raw=reply,
        text=reply,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[reply],
        should_cancel=None,
    )


def test_a_link_the_search_did_not_return_keeps_only_its_words() -> None:
    reply = (
        "According to [Reuters](https://reuters.com/world/lisbon-2026), it rained. "
        "See also [the city's page](https://lisbon-weather-facts.example/2026)."
    )
    out = unlink_unretrieved_links(_state(reply))
    assert "[Reuters](https://reuters.com/world/lisbon-2026)" in out
    assert "lisbon-weather-facts.example" not in out
    assert "See also the city's page." in out


@pytest.mark.parametrize(
    "link",
    [
        # The same page, written another way.
        "[BBC](http://www.bbc.com/news/123)",
        # The home page of a site a result came from.
        "[Reuters](https://www.reuters.com/)",
        # A map search for a place, which the places hint asks for.
        "[Café](https://www.google.com/maps/search/?api=1&query=Cafe+Lisboa)",
        # Not a web page.
        "[mail us](mailto:hi@example.com)",
    ],
)
def test_links_that_are_not_made_up_sources_stay(link: str) -> None:
    reply = f"Details: {link}."
    assert unlink_unretrieved_links(_state(reply)) == reply


def test_the_users_own_link_stays() -> None:
    message = "summarise https://example.org/report-2026 for me and search for reactions"
    reply = "The [report](https://example.org/report-2026) says rents rose."
    assert unlink_unretrieved_links(_state(reply, message=message)) == reply


def test_code_is_copied_as_written() -> None:
    reply = "Use `[x](https://made-up.example)` in markdown.\n\n```md\n[x](https://made-up.example)\n```"
    assert unlink_unretrieved_links(_state(reply)) == reply


def test_a_bare_url_as_the_words_becomes_the_site_name() -> None:
    reply = "Source: [https://made-up.example/a](https://made-up.example/a)"
    assert unlink_unretrieved_links(_state(reply)) == "Source: made-up.example"


def test_a_turn_with_no_search_results_is_left_alone() -> None:
    reply = "See [the docs](https://docs.python.org/3/library/json.html)."
    assert unlink_unretrieved_links(_state(reply, hits=[])) == reply


def test_a_model_image_turned_into_a_link_stays_a_link() -> None:
    """untrusted_media runs first and makes the image a tap-to-open link; it is not a source."""
    state = _state(
        "Here it is: ![a tram](https://img.example/tram.jpg) and [fake](https://x.example/p)"
    )
    state.text = neutralize_untrusted_media(state)
    out = unlink_unretrieved_links(state)
    assert "[a tram](https://img.example/tram.jpg)" in out
    assert "x.example" not in out and "and fake" in out
