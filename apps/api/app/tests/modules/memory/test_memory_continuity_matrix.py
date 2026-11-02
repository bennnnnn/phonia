"""Broad regressions for durable memory capture and contextual continuity."""

from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.gateways import litellm_gateway, mock_llm
from app.models.orm import Memory
from app.modules.memory import llm as memory_llm
from app.modules.memory.schemas import MemoryFactUpdateResult
from app.modules.memory.selection import select_memories_semantic
from app.modules.memory.text import is_memory_candidate
from app.modules.turn_reading.writing_kind import writing_request_kind
from app.tests.modules.memory.scoring import scored

CURRENT_EMPLOYER_QUERIES = [
    "I work at Uber but I want to move to Google",
    "Should I leave Uber for Google?",
    "What would working at Google be like for someone with my background?",
    "How can I position my current experience for Google?",
    "Which of my current skills would transfer to Google?",
    "What gaps should I close before applying to Google?",
    "Would Google be a sensible next step for me?",
    "Compare my current employer with Google for career growth",
    "How should I prepare for a Google engineering interview?",
    "What Google roles fit what I do now?",
    "Am I ready to target Google this year?",
    "What should my transition plan to Google look like?",
    "Would a move to Google improve my career path?",
    "How do my current responsibilities map to Google roles?",
    "What should I learn before trying for Google?",
    "Which achievements from my current job matter most to Google?",
    "How competitive is my profile for Google?",
    "What level should I target at Google?",
    "Would Google consider my present experience relevant?",
    "How can I turn my current work into strong interview stories?",
    "What system-design topics should I study for Google?",
    "What coding topics should I prioritize for Google?",
    "How long might a realistic move to Google take me?",
    "What are the risks of changing from my company to Google?",
    "What are the advantages of staying where I am instead?",
    "Help me decide whether Google is actually a better fit",
    "Which Google team types align with my experience?",
    "Could I qualify for a senior role at Google?",
    "What evidence would prove I am ready for Google?",
    "How should I evaluate a Google offer against my current job?",
    "What compensation factors should I compare if Google calls?",
    "Would moving to Google change my technical growth?",
    "How can I test my fit before submitting an application?",
    "What portfolio work would strengthen my Google candidacy?",
    "Which parts of my background might concern a Google recruiter?",
    "What should I emphasize in a Google recruiter conversation?",
    "How should I describe why I want Google?",
    "What is a credible reason for making this career change?",
    "How can I avoid underselling my current experience?",
    "What should I ask a Google hiring manager?",
    "What should I research about Google before interviewing?",
    "How should I practice behavioral questions for Google?",
    "Which leadership examples from my work should I prepare?",
    "What could make me regret moving to Google?",
    "Would a different big-tech company fit me better than Google?",
    "Compare Google with other next-step options for me",
    "Can my current domain experience help me switch to Google?",
    "How do I know whether now is the right time to move?",
    "What should my first month of Google preparation include?",
    "What should my three-month Google preparation plan include?",
    "Which weaknesses should I address first for this move?",
    "What strengths do I already bring to this transition?",
    "How can I make this move without damaging my current performance?",
    "If Google does not work out, what is my best alternative?",
    "Based on what you know about my work, what should I do next?",
]


DURABLE_MEMORY_STATEMENTS = [
    "Remember that I currently work at Uber",
    "Please remember I want to work at Google someday",
    "Don't forget that I prefer concise answers",
    "I am a backend software engineer",
    "As a software engineer at Uber, I work on distributed systems",
    "My target role is staff engineer",
    "I prefer examples before theory",
    "I learn best by building small projects",
    "I use Python and TypeScript at work",
    "My main project is called Recall",
    "I am preparing for system design interviews",
    "I usually study in the evening",
    "I want direct feedback without filler",
    "Call me Bini",
    "My current focus is improving architecture skills",
    "I prefer native mobile interfaces",
    "I do not like walls of text",
    "I want formulas shown before substitution",
    "I prefer final answers on their own line",
    "I am learning SwiftUI",
    "I am building an Expo app",
    "My app uses a FastAPI backend",
    "I care a lot about accessibility",
    "I prefer dark mode",
    "My next milestone is an App Store release",
    "I want to practice two coding problems each day",
    "I am interested in machine learning infrastructure",
    "My strongest language is Python",
    "I am less confident with graph algorithms",
    "I want to improve public speaking",
    "I prefer reminders in the morning",
    "My long-term goal is engineering leadership",
    "I enjoy debugging performance problems",
    "I prefer practical explanations",
    "My current priority is shipping the mobile app",
    "I use a Mac for development",
    "I test the app on an iPhone simulator",
    "I want job matches to include salary",
    "I prefer remote or hybrid roles",
    "My desired location is the Bay Area",
    "I want job fit explanations based on skills",
    "I am working on a chemistry solver",
    "I am refining a physics solver",
    "I am also testing the math experience",
    "I want animations to start automatically",
    "I prefer play and pause icons instead of words",
    "I want numeric answers without trailing zeroes",
    "I prefer editable content inline",
    "I do not want edit popups",
    "My scanner should support math, physics, and chemistry",
    "I want the camera torch near the shutter button",
    "My product should feel modern and native",
    "I prefer clean cards with compact actions",
    "I want memory to influence relevant answers naturally",
    "Remember that Uber is my current employer, not Google",
]


def _memory(memory_type: str, text: str, embedding: str) -> Memory:
    now = datetime.now(UTC)
    return Memory(
        type=memory_type,
        text=text,
        confidence=1.0,
        status="active",
        sensitivity="normal",
        importance=0.9,
        updated_at=now,
        last_confirmed_at=now,
        embedding_json=embedding,
    )


@pytest.mark.parametrize("query", CURRENT_EMPLOYER_QUERIES)
def test_current_employer_remains_available_for_related_google_questions(query: str) -> None:
    """A target company must not displace the user's established current employer.

    A career turn reads memory with the profile document (``with_profile``), so the
    job stays even when its vector misses the question.
    """
    settings = Settings(
        memory_min_confidence=0.0,
        memory_inject_limit=5,
        memory_min_similarity=0.99,
    )
    current_job = _memory("profile", "Bini currently works as a software engineer at Uber", "[0,1]")
    unrelated = _memory("fact", "Bini enjoys landscape photography", "[0,1]")

    selected = select_memories_semantic(
        scored([current_job, unrelated], [1.0, 0.0]),
        settings,
        query_text=query,
        with_profile=True,
    )

    assert current_job in selected
    assert unrelated not in selected
    assert writing_request_kind(query) is None


def test_job_and_city_stay_out_of_an_unrelated_question() -> None:
    """Only the name and reply preferences ride along on every memory turn."""
    settings = Settings(memory_min_confidence=0.0, memory_min_similarity=0.35)
    name = _memory("profile", "User's name is Bini", "[0,1]")
    job = _memory("profile", "Bini currently works as a nurse at a clinic", "[0,1]")
    city = _memory("profile", "Bini lives in Addis Ababa", "[0,1]")
    concise = _memory("preference", "Bini prefers concise answers", "[0,1]")

    selected = select_memories_semantic(
        scored([name, job, city, concise], [1.0, 0.0]),
        settings,
        query_text="what should I cook tonight?",
    )

    assert selected == [name, concise]


@pytest.mark.parametrize("statement", DURABLE_MEMORY_STATEMENTS)
def test_substantive_personal_facts_reach_memory_extraction(statement: str) -> None:
    """Natural disclosures and explicit remember requests must reach the memory model."""
    assert is_memory_candidate(statement)


def test_matrix_contains_at_least_fifty_distinct_cases_per_memory_seam() -> None:
    assert len(CURRENT_EMPLOYER_QUERIES) >= 50
    assert len(set(CURRENT_EMPLOYER_QUERIES)) == len(CURRENT_EMPLOYER_QUERIES)
    assert len(DURABLE_MEMORY_STATEMENTS) >= 50
    assert len(set(DURABLE_MEMORY_STATEMENTS)) == len(DURABLE_MEMORY_STATEMENTS)


@pytest.mark.asyncio
async def test_extractor_prompt_preserves_current_employer_when_target_is_aspirational(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_complete_structured(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(mock_llm, "should_mock_llm", lambda _settings: False)
    monkeypatch.setattr(
        litellm_gateway,
        "complete_structured",
        fake_complete_structured,
    )

    await memory_llm.revise_memory_facts(
        Settings(),
        "User: I work at Uber but want to move to Google",
        existing_facts=[
            {
                "id": "current-job",
                "type": "profile",
                "text": "Bini currently works at Uber",
            }
        ],
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    first_message = messages[0]
    assert isinstance(first_message, dict)
    system_prompt = first_message["content"]
    assert isinstance(system_prompt, str)
    assert "keeps Uber as the current employer" in system_prompt
    assert "must not claim the user works at Google" in system_prompt
    assert "4 in the evening is 16:00" in system_prompt


@pytest.mark.asyncio
async def test_extractor_prompt_keeps_everyday_profile_facts_normal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_complete_structured(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(mock_llm, "should_mock_llm", lambda _settings: False)
    monkeypatch.setattr(
        litellm_gateway,
        "complete_structured",
        fake_complete_structured,
    )

    await memory_llm.revise_memory_facts(
        Settings(),
        "User: I'm an engineer at Uber in Oakland, originally from Ethiopia",
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    system_prompt = messages[0]["content"]
    assert isinstance(system_prompt, str)
    # Profile is not described as "identity", so job and place facts are not
    # labelled with the sensitive identity category and dropped.
    assert "own identity" not in system_prompt
    assert (
        "normal: name, job, employer, school, city, home country, languages" in system_prompt
    )  # safety phrase
    assert (
        "identity: gender identity, immigration status, or disability" in system_prompt
    )  # safety phrase
    assert (
        "building a dating app or a health tracker is a normal project fact" in system_prompt
    )  # safety phrase


@pytest.mark.asyncio
async def test_extractor_prompt_keeps_how_the_user_wants_to_be_taught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_complete_structured(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(mock_llm, "should_mock_llm", lambda _settings: False)
    monkeypatch.setattr(litellm_gateway, "complete_structured", fake_complete_structured)
    preference = (
        "When teaching me, explain one concept at a time, use practical examples, and ask me "
        "to solve a short exercise before moving on."
    )

    # The line reaches the extractor at all, and its prompt files it under preferences.
    assert is_memory_candidate(f"User: {preference}")
    await memory_llm.revise_memory_facts(Settings(), f"User: {preference}")

    messages = captured["messages"]
    assert isinstance(messages, list)
    system_prompt = messages[0]["content"]
    assert isinstance(system_prompt, str)
    assert "How they want to be taught is a preferences fact even with no topic yet" in (
        system_prompt
    )
    assert "how they like to learn" in system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("from_history", [False, True])
async def test_extractor_prompt_lets_old_chats_only_fill_gaps(
    monkeypatch: pytest.MonkeyPatch, from_history: bool
) -> None:
    captured: dict[str, object] = {}

    async def fake_complete_structured(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(mock_llm, "should_mock_llm", lambda _settings: False)
    monkeypatch.setattr(litellm_gateway, "complete_structured", fake_complete_structured)

    await memory_llm.revise_memory_facts(
        Settings(), "User: I live in Paris", from_history=from_history
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]
    rule = "never update, supersede, or delete an existing fact because of these lines"
    assert (rule in system_prompt) is from_history
    assert ("Earlier conversation:" in user_prompt) is from_history
    assert ("New conversation:" in user_prompt) is not from_history


@pytest.mark.asyncio
async def test_instruct_prompt_names_the_open_document_and_asks_for_a_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_complete_structured(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(mock_llm, "should_mock_llm", lambda _settings: False)
    monkeypatch.setattr(litellm_gateway, "complete_structured", fake_complete_structured)

    await memory_llm.instruct_memory(
        Settings(),
        "Keep lists under five things",
        existing_facts=[],
        existing_areas=[{"topic": "area:recall", "title": "Recall", "summary": ""}],
        focus_topic="preferences",
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]
    assert "looking at the preferences document" in system_prompt
    assert '"reply": "one short sentence to the user"' in system_prompt
    assert "is a preferences fact" in system_prompt
    assert "area:recall" in user_prompt
    assert "Keep lists under five things" in user_prompt


def test_memory_op_salvage_keeps_the_reply() -> None:

    parsed = MemoryFactUpdateResult.salvage_partial(
        {
            "ops": [
                {"op": "add", "type": "fact", "text": "User likes tea", "confidence": 0.9},
                # An unknown type is typed by its topic now; a missing confidence still drops.
                {"op": "add", "type": "nonsense", "text": "dropped"},
            ],
            "reply": "Saved that you like tea." + " " * 3,
        }
    )
    assert parsed is not None
    assert [op.text for op in parsed.ops] == ["User likes tea"] and parsed.dropped == 1
    assert parsed.reply == "Saved that you like tea."
    # A reply alone is still an answer; nothing at all is a failure.
    only_reply = MemoryFactUpdateResult.salvage_partial({"ops": [], "reply": "Nothing to change."})
    assert only_reply is not None and only_reply.reply == "Nothing to change."
    assert MemoryFactUpdateResult.salvage_partial({"ops": [{"op": "bad"}]}) is None


async def _extractor_prompt(
    monkeypatch: pytest.MonkeyPatch, *, today: str | None = None, from_history: bool = False
) -> str:
    captured: dict[str, object] = {}

    async def fake_complete_structured(**call: object) -> None:
        captured.update(call)

    monkeypatch.setattr(mock_llm, "should_mock_llm", lambda _settings: False)
    monkeypatch.setattr(litellm_gateway, "complete_structured", fake_complete_structured)
    await memory_llm.revise_memory_facts(
        Settings(),
        "User: I have an anatomy exam next Friday",
        today=today,
        from_history=from_history,
    )
    messages = captured["messages"]
    assert isinstance(messages, list) and isinstance(messages[0], dict)
    system = messages[0]["content"]
    assert isinstance(system, str)
    return system


@pytest.mark.asyncio
async def test_a_live_pass_knows_the_user_s_date_so_next_friday_is_saved_as_a_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Live: "User has an anatomy exam next Friday" was saved as said; a week on it
    # names the wrong Friday.
    system = await _extractor_prompt(monkeypatch, today="Friday, Oct 23, 2026")
    assert "Today is Friday, Oct 23, 2026 for the user." in system


@pytest.mark.asyncio
async def test_an_earlier_chat_has_no_date_to_place_next_friday(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system = await _extractor_prompt(monkeypatch, from_history=True)
    assert "Today is" not in system
    assert "Leave out a relative date you cannot place." in system  # safety phrase


def test_local_today_names_the_day_as_the_rule_does() -> None:
    import re

    assert re.fullmatch(
        r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day, [A-Z][a-z]{2} \d{1,2}, \d{4}",
        memory_llm.local_today("America/Indiana/Indianapolis"),
    )
