"""A message that works on the chat itself never searches the web; a live ask still does.

"Yes" to "Does that make sense? 😊" searched the band Yes; "sure give me a practice
problem" and "summarize what we covered" were wrapped in unrelated pages (2026-10-24).
The first draft skipped too much: a yes to "Want the full box score?" and "one more
question: what's the weather tomorrow?" stopped searching. Both sides are held here.
"""

from __future__ import annotations

import pytest

from app.gateways.web_search_gateway import WebSearchHit
from app.modules.web_search.chat_bound import ends_on_a_check, works_from_the_chat
from app.modules.web_search.detection import web_search_skip
from app.modules.web_search.source_quality import is_error_page

_PRIOR = ["an earlier question"]
_CHECK = "So V₂ = 2.34 L.\n\nDoes that make sense? 😊"


@pytest.mark.parametrize(
    ("text", "prior_assistant"),
    [
        # An answer to the reply's check.
        ("Yes", _CHECK),
        ("yeah that makes sense", _CHECK),
        ("yes it does", _CHECK),
        ("nope still confused", _CHECK),
        ("yes", "Want me to give you a practice problem?"),
        ("yes", "Ready for the next one?"),
        ("sure", "Want to try one yourself?"),
        ("yes", "Want to check your answer by plugging it back in?"),
        ("yes", "Want to try binary search on an example?"),
        # Something made from the chat.
        ("sure give me a practice problem", _CHECK),
        ("ok im done studying for today. can you summarize what we covered?", "He was French."),
        ("summarize what we covered so i can review before thursday", "Good luck!"),
        ("can you quiz me on gas laws? 3 quick questions", "Ready?"),
        ("i want a practice problem", None),
        ("practice problem please", None),
        ("ok give me another", None),
        ("another one", "Nice work!"),
        ("recap", None),
        ("repeat the last answer", None),
        ("explain that again simpler", "It runs out first."),
        ("walk me through an example", "Stoichiometry has four steps."),
        ("give me a practice problem on Charles's law", None),
    ],
)
def test_a_message_about_the_chat_never_searches(text: str, prior_assistant: str | None) -> None:
    assert web_search_skip(text, prior_user_messages=_PRIOR, prior_assistant=prior_assistant)


@pytest.mark.parametrize(
    ("text", "prior_assistant"),
    [
        # A yes to an offer to look something up, however it is worded.
        ("yes", "Want me to get the black-market rate too?"),
        ("yes", "Should I list showtimes near you?"),
        ("yes", "Would you like the latest reviews?"),
        ("yes", "Want to know who scored?"),
        ("yes", "They won 110-102. Want the full box score?"),
        # An answer to a check that asks to look something up, or asks something live.
        ("yes please search", _CHECK),
        ("yes google it", _CHECK),
        ("yes, what's the weather tomorrow?", _CHECK),
        # A live ask that opens like a request about the chat.
        ("one more question: what's the weather in Addis tomorrow?", None),
        ("another question, is the iPhone 17 out yet?", None),
        ("another question: who is the president of Kenya", None),
        ("walk me through the visa requirements for Kenya", None),
        ("walk me through what happened in the Lakers game last night", None),
        ("Do problems with the new iOS update drain battery?", None),
        ("show me problems people have with the Pixel 10", None),
        ("give me a practice problem. what's the weather tomorrow?", None),
        ("summarize today's news", None),
        ("quiz me on current events this week", None),
    ],
)
def test_a_live_ask_still_may_search(text: str, prior_assistant: str | None) -> None:
    assert not web_search_skip(text, prior_user_messages=_PRIOR, prior_assistant=prior_assistant)


@pytest.mark.parametrize(
    ("prior_assistant", "checks"),
    [
        (_CHECK, True),
        ("Got it?", True),
        ("Any questions so far?", True),
        ("Here are the steps. Can you find the limiting reactant in this one?", True),
        ("Want the full box score?", False),
        ("I can look up today's rate if you like. Want me to?", False),
        ("Ready to see the latest scores from tonight's game and the full standings?", False),
        ("No question here.", False),
        (None, False),
    ],
)
def test_a_check_is_the_replys_closing_question(prior_assistant: str | None, checks: bool) -> None:
    assert ends_on_a_check(prior_assistant) is checks


def test_a_request_is_read_whole() -> None:
    assert works_from_the_chat("one more question")
    assert not works_from_the_chat("summarize the news so i can catch up")
    assert not works_from_the_chat("quiz me on what happened today")


def _hit(title: str, snippet: str) -> WebSearchHit:
    return WebSearchHit(title=title, url="https://example.com/page", snippet=snippet)


@pytest.mark.parametrize(
    ("title", "snippet"),
    [
        # The live source chip.
        (
            "Weather API",
            "{'error': {'code': 2007, 'message': 'API key has reached maximum calls per "
            "month allowed limit.'}}",
        ),
        ("x", '{"message":"Unauthorized"}'),
        ("x", '{"detail":"Not found."}'),
        ("404 Not Found", ""),
        ("Error 403 - Forbidden", ""),
        ("401 Unauthorized", ""),
        ("429 Too Many Requests", ""),
        ("502 Bad Gateway", "502 Bad Gateway"),
        ("503 Service Temporarily Unavailable", ""),
        ("Just a moment...", ""),
        ("Attention Required! | Cloudflare", ""),
        ("x", "Checking your browser before accessing example.com."),
        ("x", "Sorry, you have been blocked"),
        ("x", "Access to this page has been denied."),
        ("x", "Please enable cookies."),
    ],
)
def test_an_error_page_is_no_source(title: str, snippet: str) -> None:
    assert is_error_page(_hit(title, snippet))


@pytest.mark.parametrize(
    ("title", "snippet"),
    [
        ("Forbidden City", "The Forbidden City is a palace complex in Beijing."),
        ("403(b) plans", "A 403(b) plan is a retirement plan for teachers and nonprofits."),
        ("API keys", "Authenticate requests by passing your API key in the header."),
        ("Rate limits", "The OpenAI API rate limit for GPT-4o is 30,000 tokens per minute."),
        ("reCAPTCHA", "reCAPTCHA is a free service that protects your site from spam."),
        ("HTTP 404 Not Found: what it means", "HTTP 404 Not Found means the page is gone."),
        ("Forbidden | Netflix", "A thriller about a forbidden love."),
        ("Paris weather", "Sunny, 18°C, light wind."),
    ],
)
def test_a_page_about_an_error_is_content(title: str, snippet: str) -> None:
    assert not is_error_page(_hit(title, snippet))
