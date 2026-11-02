"""A yes/no question about whether Recall searches asks about the app, not for a search.

Live (2026-10-25): "Show me how u work", then "Can you search the web?". The question
read as a search request that names nothing, so the turn searched the line before it,
and its source chips were song lyrics.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.gateways.mcp import registry
from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.tool_loop import live_denial
from app.modules.chat.tool_loop.reply_calls import ReplyTurn, reply_tools
from app.modules.chat.turn_prep.context import StreamContext
from app.modules.web_search import (
    WebSearchAdapter,
    asks_only_whether_it_searches,
    asks_whether_it_searches,
)
from app.modules.web_search.command import asks_to_search
from app.modules.web_search.detection import needs_web_search, web_search_skip
from app.tests.fakes import isolated_settings

_SETTINGS = isolated_settings(web_search_enabled=True, mcp_tool_loop_enabled=True)
_PRIOR = ["Show me how u work"]
# The reply to it may end on a question: that is no offer to search.
_PRIOR_REPLY = "I'm Recall. Ask me questions or keep reminders. What would you like to try first?"
_SEARCH_FIRST = ["did the bears win today"]
_BEARS = ["who won the bears game yesterday"]
_DENIED = "I don't have yesterday's result in front of me."
_OFFER = f"{_DENIED} I can search the web for that if you'd like."

CAPABILITY_QUESTIONS = [
    "Can you search the web?",
    "can you search the web",
    "Can you search?",
    "could you search online?",
    "do you search online?",
    "are you able to browse the internet?",
    "can u google things?",
    "do you have web search?",
    "do you have access to the internet?",
    "Do you have the ability to search the web?",
    "can you browse the web?",
    "can you look things up online?",
    "can you look stuff up?",
    "can you access the internet?",
    "can you use google?",
    "can you go online?",
    "are you connected to the internet?",
    "you can search the internet?",
    "can you actually search the web?",
    "Thanks. Can you search the web?",
    "hey, can you search the internet too?",
    "So you can search the web?",
]
SEARCH_REQUESTS = [
    "can you search for the latest news on Tesla?",
    "can you look it up?",
    "can't you look it up? You looked up the weather",
    "search the web for flights to Paris",
    "can you google it",
    "can you search it?",
    "can you search the web for that?",
    "can you search the web for me",
    "would you search the web?",
    "can you search the web now?",
    "can you do a search",
    "can you look up the weather?",
    "search the web",
    "please search online",
    "can you browse for running shoes?",
]


@pytest.mark.parametrize("text", CAPABILITY_QUESTIONS)
def test_a_capability_question_is_no_search(text: str) -> None:
    assert asks_whether_it_searches(text)
    for prior, reply in ((None, None), (_PRIOR, None), (_PRIOR, _PRIOR_REPLY)):
        assert web_search_skip(text, prior_user_messages=prior, prior_assistant=reply)
        assert not needs_web_search(text, prior_user_messages=prior, prior_assistant=reply)


@pytest.mark.parametrize(
    "text, prior, reply",
    [
        # Review: after a question it could not answer, or an offer, the same words ask.
        ("could you search online?", _BEARS, _DENIED),
        ("can you search the web?", _BEARS, _OFFER),
        ("ok can you search online?", _BEARS, _OFFER),
        ("can you search?", _BEARS, None),
        ("can you google?", _BEARS, None),
        ("can you go online?", _BEARS, None),
        ("Can you search the web?", ["tell me about Purecart"], "Want me to look it up?"),
        ("can you search the web?", _PRIOR, "I can search the web for that if you'd like."),
    ],
)
def test_a_capability_question_after_something_to_search_searches(
    text: str, prior: list[str] | None, reply: str | None
) -> None:
    assert asks_whether_it_searches(text)
    assert not asks_only_whether_it_searches(text, prior_user_messages=prior, prior_assistant=reply)
    assert needs_web_search(text, prior_user_messages=prior, prior_assistant=reply)


@pytest.mark.parametrize(
    "prior, reply",
    [
        # Review: an older search topic is not the line a search would send.
        (["who won the bears game yesterday", "how do I boil an egg", "Show me how u work"], None),
        (["who won the bears game yesterday", "Show me how u work"], _PRIOR_REPLY),
        # An offer to search, with nothing that could stand as a query.
        (["hi"], "Hi! Should I check online for anything?"),
        (["hi"], "Hi! Want me to google that?"),
    ],
)
def test_a_capability_question_reads_the_line_a_search_would_send(
    prior: list[str], reply: str | None
) -> None:
    text = "can you search the web?"
    assert asks_only_whether_it_searches(text, prior_user_messages=prior, prior_assistant=reply)
    assert not needs_web_search(text, prior_user_messages=prior, prior_assistant=reply)


@pytest.mark.parametrize("text", SEARCH_REQUESTS)
def test_a_search_request_still_searches(text: str) -> None:
    assert not asks_whether_it_searches(text)
    assert asks_to_search(text)
    assert needs_web_search(text, prior_user_messages=_SEARCH_FIRST)


@pytest.mark.parametrize(
    "text",
    [
        "do you have a minute?",
        "do you have any news?",
        "can you access my files?",
        "can you look after my cat",
        "can you go out?",
        "can you get the weather?",
        "can you use a search engine to find flights?",
        "what can you do?",
        "",
    ],
)
def test_other_questions_are_not_capability_questions(text: str) -> None:
    assert not asks_whether_it_searches(text)


def _turn(content: str, prior: list[str] | None) -> ReplyTurn:
    return ReplyTurn(
        content=content,
        lightweight=False,
        has_instant_reply=False,
        has_verified_math=False,
        has_search_sources=False,
        prior_user_messages=prior,
        prior_assistant=None,
    )


@pytest.mark.parametrize("text", CAPABILITY_QUESTIONS[:6])
def test_the_reply_is_not_offered_search_on_a_capability_question(text: str) -> None:
    adapter = WebSearchAdapter(_SETTINGS)
    registry.register(adapter)
    assert reply_tools(_SETTINGS, _turn(text, _PRIOR)) == []


@pytest.mark.parametrize("text", ["Can you search the web?", "Can you search?", "can you google?"])
def test_the_reply_may_search_on_one_after_a_question_to_search(text: str) -> None:
    adapter = WebSearchAdapter(_SETTINGS)
    registry.register(adapter)
    assert reply_tools(_SETTINGS, _turn(text, _BEARS)) == [adapter.to_openai_tool()]


def _context(content: str, prior: list[str] | None = None) -> StreamContext:
    earlier = [{"role": "user", "content": line} for line in prior or []]
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[*earlier, {"role": "user", "content": content}],
        run_title=False,
        user_message_content=content,
        reserved_tokens=100,
        max_output_tokens=100,
    )
    ctx.denial_retry_tools = [{"type": "function"}]
    return ctx


@pytest.mark.parametrize(
    "text, prior, retried",
    [
        ("Can you search the web?", None, False),
        ("Can you search the web?", _PRIOR, False),
        ("do you have web search?", None, False),
        # After a question to search, the same words ask for the search.
        ("Can you search the web?", _BEARS, True),
        ("did the bears win today", None, True),
    ],
)
def test_a_denial_on_a_capability_question_is_not_retried_with_search(
    text: str, prior: list[str] | None, retried: bool
) -> None:
    accum = StreamAccum(parts=["I can't browse the web, sorry."])
    assert live_denial.asks_again(_context(text, prior), [], accum, 0) is retried
